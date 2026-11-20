"""
Kamu Personel Rehberi — Otonom Ajan Telemetri & Takip Raporlayıcısı
====================================================================
Tüm 5 otonom ajanın (Muhabir, Editör, Görsel, Kalite Kapısı, SSG & Brifing)
%100 gerçek dosya/veri çıktılarını okuyarak Patron Paneli "Ajan Takibi" sekmesi
için website/data/agent_runs.json ve docs/data/agent_runs.json üretir.
Sıfır sahte veri.
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def build_agent_telemetry() -> Dict[str, Any]:
    website_dir = ROOT_DIR / "website"
    raw_news = _read_json(website_dir / "data" / "news.json")
    editorial = _read_json(website_dir / "data" / "editorial_news.json")
    jobs = _read_json(website_dir / "data" / "jobs.json")
    briefing = _read_json(website_dir / "data" / "ai_briefing.json")

    raw_list = raw_news.get("news", [])
    articles = editorial.get("articles", [])
    ed_meta = editorial.get("meta", {})
    jobs_list = [j for j in jobs.get("jobs", []) if not j.get("is_cancellation")]

    # Benzersiz kaynak URL sayısı (Muhabir Ajanı tekilleştirme verisi)
    unique_urls = len({(x.get("source_url") or "").strip() for x in raw_list if x.get("source_url")})
    duplicates_removed = max(0, len(raw_list) - unique_urls)

    # Kelime istatistikleri (Editör Ajanı)
    wcs = [int(a.get("word_count") or 0) for a in articles if a.get("word_count")]
    avg_wc = round(sum(wcs) / len(wcs)) if wcs else 0
    min_wc = min(wcs) if wcs else 0
    max_wc = max(wcs) if wcs else 0

    # Görsel Ajanı gerçek WebP taraması
    covers_dir = website_dir / "assets" / "img" / "covers"
    cover_files = list(covers_dir.glob("*.webp")) if covers_dir.exists() else []
    total_cover_kb = round(sum(f.stat().st_size for f in cover_files) / 1024, 1)

    # Sitemap gerçek sayfa sayısı (SSG Ajanı)
    sitemap_path = website_dir / "sitemap.xml"
    sitemap_urls = 0
    if sitemap_path.exists():
        sitemap_urls = len(re.findall(r"<loc>([^<]+)</loc>", sitemap_path.read_text(encoding="utf-8")))

    approved_cnt = ed_meta.get("total_approved", len(articles))
    rejected_cnt = ed_meta.get("total_rejected", 0)
    pass_rate = round((approved_cnt / (approved_cnt + rejected_cnt)) * 100, 1) if (approved_cnt + rejected_cnt) else 100.0

    agents: List[Dict[str, Any]] = [
        {
            "id": "fetcher",
            "name": "Muhabir Ajanı",
            "module": "ArticleFetcherAgent",
            "role": "Resmi kurumlardan tam metin çekimi ve mükerrer kayıt eleme",
            "status": "active",
            "last_run": raw_news.get("meta", {}).get("generated_at") or ed_meta.get("generated_at") or "",
            "metrics": {
                "Taranan Ham Bülten": len(raw_list),
                "Benzersiz Kaynak": unique_urls,
                "Elenen Mükerrer": duplicates_removed,
            },
        },
        {
            "id": "editor",
            "name": "Editör Ajanı (LLM)",
            "module": "EditorialWriterAgent",
            "role": "NVIDIA Nemotron-3-Ultra-550B ile özgün Türkçe haber üretimi",
            "status": "active",
            "model": "nvidia/nemotron-3-ultra-550b-a55b",
            "last_run": ed_meta.get("generated_at") or "",
            "metrics": {
                "Üretilen Makale": len(articles),
                "Ort. Kelime": avg_wc,
                "Min / Max Kelime": f"{min_wc} / {max_wc}",
            },
        },
        {
            "id": "visual",
            "name": "Görsel Ajanı",
            "module": "VisualCuratorAgent",
            "role": "1200x675 telifsiz WebP kapak üretimi ve SEO alt etiketi",
            "status": "active",
            "last_run": ed_meta.get("generated_at") or "",
            "metrics": {
                "WebP Kapak": len(cover_files),
                "Toplam Boyut": f"{total_cover_kb} KB",
                "Ort. Boyut": f"{round(total_cover_kb / len(cover_files), 1) if cover_files else 0} KB",
            },
        },
        {
            "id": "qa",
            "name": "Kalite Kapısı Ajanı",
            "module": "QualityGateAgent",
            "role": "Kelime, kesik metin ([...]), encoding ve görsel yayın denetimi",
            "status": "active",
            "last_run": ed_meta.get("generated_at") or "",
            "metrics": {
                "Onaylanan": approved_cnt,
                "Reddedilen": rejected_cnt,
                "Onay Oranı": f"%{pass_rate}",
            },
        },
        {
            "id": "publisher",
            "name": "SSG & Brifing Ajanı",
            "module": "SSGBuilder + PatronAIBriefing",
            "role": "Statik HTML derleme, temiz sitemap ve NVIDIA yönetici brifingi",
            "status": "active",
            "last_run": briefing.get("generated_at") or jobs.get("meta", {}).get("generated_at") or "",
            "metrics": {
                "Statik Sayfa (Sitemap)": sitemap_urls,
                "Aktif İlan": len(jobs_list),
                "Brifing Modeli": (briefing.get("model") or "nemotron-550b").split("/")[-1],
            },
        },
    ]

    recent_outputs = [
        {
            "headline": a.get("headline", ""),
            "institution": a.get("institution", ""),
            "slug": a.get("slug", ""),
            "word_count": a.get("word_count", 0),
            "generated_by": a.get("generated_by", ""),
            "publish_date": a.get("publish_date_formatted", ""),
        }
        for a in articles[:20]
    ]

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_at_tr": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "schedule": "Günde 3 kez otomatik (09:00 / 14:00 / 19:00 TSİ — GitHub Actions)",
        "agents": agents,
        "recent_outputs": recent_outputs,
    }

    for out_path in [
        ROOT_DIR / "website" / "data" / "agent_runs.json",
        ROOT_DIR / "docs" / "data" / "agent_runs.json",
    ]:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"📊 Ajan Telemetri raporu kaydedildi: {out_path}")

    return payload


if __name__ == "__main__":
    build_agent_telemetry()
