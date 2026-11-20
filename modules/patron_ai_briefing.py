"""
Kamu Personel Rehberi — Patron Paneli NVIDIA Nemotron-3-Ultra-550B AI Brifing Motoru
=====================================================================================
Supabase site_analytics_events + jobs.json + editorial_news.json gerçek verilerini
analiz eder, NVIDIA NIM (nvidia/nemotron-3-ultra-550b-a55b) ile yönetici brifingi
üretir ve website/data/ai_briefing.json + docs/data/ai_briefing.json olarak kaydeder.
"""

import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

import requests

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


def load_local_env() -> None:
    env_path = ROOT_DIR / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and v and k not in os.environ:
                os.environ[k] = v


def detect_device(ua: str) -> str:
    u = (ua or "").lower()
    if "instagram" in u:
        return "Instagram Uygulama İçi"
    if "iphone" in u or "ipad" in u:
        return "Mobil (iOS)"
    if "android" in u:
        return "Mobil (Android)"
    if "windows" in u or "macintosh" in u or "linux" in u:
        return "Masaüstü"
    return "Diğer"


def fetch_analytics_events(limit: int = 2000) -> List[Dict[str, Any]]:
    supa_url = os.getenv("SUPABASE_URL", "https://lxffirosgbrfptnbjvdg.supabase.co").rstrip("/")
    supa_key = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_PUBLISHABLE_KEY") or "sb_publishable_VHW7Sg89AM9NV6DqOHLTzQ_BMO4BBV9"
    try:
        r = requests.get(
            f"{supa_url}/rest/v1/site_analytics_events?select=id,event_type,job_id,job_title,category,referrer,user_agent,created_at&order=created_at.desc&limit={limit}",
            headers={"apikey": supa_key, "Authorization": f"Bearer {supa_key}"},
            timeout=15,
        )
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"⚠️ Supabase analitik çekme hatası: {e}")
    return []


def summarize_metrics(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    cutoff_24h = now - timedelta(hours=24)
    cutoff_7d = now - timedelta(days=7)

    ev_counts = Counter()
    ev_24h = Counter()
    ref_counts = Counter()
    dev_counts = Counter()
    job_counts = Counter()
    cat_counts = Counter()
    search_counts = Counter()

    for ev in events:
        etype = ev.get("event_type") or "UNKNOWN"
        ev_counts[etype] += 1
        ref_counts[ev.get("referrer") or "Doğrudan (Direct)"] += 1
        dev_counts[detect_device(ev.get("user_agent") or "")] += 1

        if ev.get("job_title"):
            if etype == "SEARCH":
                search_counts[ev["job_title"].strip()] += 1
            else:
                job_counts[ev["job_title"].strip()] += 1
        if ev.get("category"):
            cat_counts[ev["category"].strip()] += 1

        ts = ev.get("created_at") or ""
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt >= cutoff_24h:
                ev_24h[etype] += 1
        except Exception:
            pass

    jobs_path = ROOT_DIR / "website" / "data" / "jobs.json"
    news_path = ROOT_DIR / "website" / "data" / "editorial_news.json"
    jobs_meta = {}
    news_meta = {}
    if jobs_path.exists():
        jd = json.loads(jobs_path.read_text(encoding="utf-8"))
        jobs_meta = {
            "total_jobs": len(jd.get("jobs", [])),
            "total_quota": jd.get("meta", {}).get("total_quota", 0),
            "generated_at": jd.get("meta", {}).get("generated_at", ""),
        }
    if news_path.exists():
        nd = json.loads(news_path.read_text(encoding="utf-8"))
        news_meta = {
            "total_approved_news": len(nd.get("articles", [])),
            "generated_at": nd.get("meta", {}).get("generated_at", ""),
        }

    return {
        "total_events_analyzed": len(events),
        "event_counts": dict(ev_counts),
        "last_24h_counts": dict(ev_24h),
        "top_referrers": ref_counts.most_common(6),
        "device_breakdown": dev_counts.most_common(5),
        "top_jobs": job_counts.most_common(8),
        "top_categories": cat_counts.most_common(6),
        "top_searches": search_counts.most_common(8),
        "jobs_meta": jobs_meta,
        "news_meta": news_meta,
    }


def generate_nvidia_briefing(metrics: Dict[str, Any]) -> Dict[str, Any]:
    api_key = os.getenv("NVIDIA_API_KEY", "").strip()
    model = os.getenv("NVIDIA_MODEL", "nvidia/nemotron-3-ultra-550b-a55b").strip()

    if not api_key:
        return {
            "model": "local_analytics_engine",
            "executive_summary": "NVIDIA_API_KEY tanımlı olmadığı için temel veri özeti oluşturuldu.",
            "traffic_insight": "Canlı Supabase verileri panele aktarılmıştır.",
            "action_items": [
                "Google Search Console indeksleme durumunu haftalık takip edin.",
                "En çok ilgi gören kategorilerde yeni rehber içerikleri yayınlayın.",
            ],
        }

    prompt = f"""
Sen Kamu Personel Rehberi (kamupersonelrehberiniz.me) web sitesinin kıdemli Veri Analisti ve Yönetici Asistanısın.
Aşağıdaki %100 gerçek canlı verileri analiz et ve site sahibine (Patrona) kısa, net, rakamlara dayalı Türkçe bir yönetici brifingi hazırla.
Kesinlikle uydurma rakam yazma; sadece aşağıdaki JSON verilerini yorumla.

Veriler:
{json.dumps(metrics, ensure_ascii=False)}

Çıktıyı SADECE geçerli bir JSON objesi olarak döndür (markdown ```json kullanma):
{{
  "executive_summary": "3-4 cümlelik genel durum ve dönüşüm değerlendirmesi",
  "traffic_insight": "Ziyaretçilerin nereden geldiği (referrer) ve cihaz dağılımı hakkında 2-3 cümlelik analiz",
  "content_insight": "En çok ilgi gören ilan/kategori ve arama trendleri hakkında 2-3 cümlelik analiz",
  "action_items": ["Somut aksiyon 1", "Somut aksiyon 2", "Somut aksiyon 3"]
}}
"""
    try:
        r = requests.post(
            "https://integrate.api.nvidia.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": "Sadece geçerli JSON döndüren kıdemli Türkçe web analitik ve SEO asistanısın."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.3,
                "max_tokens": 900,
                "chat_template_kwargs": {"enable_thinking": False},
            },
            timeout=35,
        )
        if r.status_code == 200:
            raw = (r.json()["choices"][0]["message"].get("content") or "").strip()
            raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.I)
            raw = re.sub(r"\s*```$", "", raw)
            parsed = json.loads(raw)
            parsed["model"] = model
            return parsed
    except Exception as e:
        print(f"⚠️ NVIDIA brifing üretim hatası: {e}")

    return {
        "model": "fallback_analytics_engine",
        "executive_summary": f"Toplam {metrics['total_events_analyzed']} canlı ziyaretçi hareketi analiz edildi.",
        "traffic_insight": "Trafik kaynakları ve cihaz kırılımı panel grafiklerinde canlı olarak görüntülenmektedir.",
        "content_insight": "En çok incelenen ilanlar ve arama trendleri anlık güncellenmektedir.",
        "action_items": [
            "Telegram ve Instagram kanallarından en çok tıklanan ilan kategorilerine yönlendirme artırılabilir.",
            "Google Search Console'da indekslenen sayfa sayısını haftalık takip edin.",
        ],
    }


def run_briefing() -> None:
    load_local_env()
    events = fetch_analytics_events(limit=2000)
    metrics = summarize_metrics(events)
    ai_report = generate_nvidia_briefing(metrics)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_at_tr": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "model": ai_report.get("model", "nvidia/nemotron-3-ultra-550b-a55b"),
        "briefing": ai_report,
        "snapshot": metrics,
    }

    for out_path in [
        ROOT_DIR / "website" / "data" / "ai_briefing.json",
        ROOT_DIR / "docs" / "data" / "ai_briefing.json",
    ]:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"🤖 NVIDIA AI Yönetici Brifingi kaydedildi: {out_path}")


if __name__ == "__main__":
    run_briefing()
