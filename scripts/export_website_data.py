"""
Kamu Personel Rehberi - Web Sitesi Veri İhracatçısı (JSON Data Exporter)
Veritabanındaki resmi alım ilanlarını parse ederek,
GitHub Pages web sitesi için optimize edilmiş jobs.json dosyasını üretir.
"""

import os
import sys
import json
import re
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

# Proje ana dizinini Python path'e ekle
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

from core.database import get_db
from core.models import JobAnnouncement, JobStatus

TR_MONTHS = {
    1: "Ocak", 2: "Şubat", 3: "Mart", 4: "Nisan", 5: "Mayıs", 6: "Haziran",
    7: "Temmuz", 8: "Ağustos", 9: "Eylül", 10: "Ekim", 11: "Kasım", 12: "Aralık"
}
TR_MONTHS_REV = {v.lower(): k for k, v in TR_MONTHS.items()}


def format_tr_date(dt: Optional[datetime]) -> str:
    """Datetime nesnesini Türkçe tarih formatına çevirir."""
    if not dt:
        return "Resmi Kılavuzda"
    m_name = TR_MONTHS.get(dt.month, "")
    return f"{dt.day:02d} {m_name} {dt.year}"


def parse_date_group_and_sort(raw_dates_str: str, end_dt: Optional[datetime]) -> tuple:
    """
    Başvuru tarihleri metninden (örn: '12 Ekim - 26 Ekim' veya '28 Eylül - 2 Ekim')
    SBB Kamu İlan tarzı tarih grubunu ('9 Ekim', '28 Eylül' vb.) ve sıralama anahtarını üretir.
    """
    if not raw_dates_str and not end_dt:
        return ("Süregelen İlanlar", 20261001)

    # raw_dates_str'den başlangıç tarihini yakala
    if raw_dates_str:
        parts = raw_dates_str.split("-")
        start_part = parts[0].strip()
        # Örnek: '28 Eylül', '2 Ekim', '3 Ağustos'
        m = re.match(r"^(\d{1,2})\s+([A-Za-zÇĞİÖŞÜçğıöşü]+)", start_part)
        if m:
            day = int(m.group(1))
            m_name = m.group(2).capitalize()
            m_num = TR_MONTHS_REV.get(m_name.lower(), 10)
            sort_key = 20260000 + (m_num * 100) + day
            return (f"{day} {m_name}", sort_key)

    if end_dt:
        m_name = TR_MONTHS.get(end_dt.month, "Ekim")
        sort_key = (end_dt.year * 10000) + (end_dt.month * 100) + end_dt.day
        return (f"{end_dt.day} {m_name}", sort_key)

    return ("Güncel İlanlar", 20261010)


def clean_institution_and_position(job: JobAnnouncement) -> tuple:
    """Kurum adı, pozisyon ve kontenjanı en doğru şekilde temizler."""
    title = (job.title or "").strip()
    inst = (job.institution or "").strip()
    position = (job.position or "").strip()

    # İptal / Düzeltme Kontrolü
    title_upper = title.upper()
    is_cancellation = any(k in title_upper for k in ["İPTAL", "IPTAL", "DÜZELTME", "DUZELTME"])

    # 1. Kurum Adı Çözümleme
    if not inst or inst == "Kamu Kurumu" or "ALACAK" in inst.upper() or len(inst) > 75:
        # Başlıktan kurum adını çek
        m = re.match(r"^(.+?)\s+(?:\d+\s+|SÖZLEŞMELİ|ÖĞRETİM|MEMUR|UZMAN|SÜREKLİ|DÜZELTME|İPTAL|ALACAK|ÖĞR|SÜREKLİ)", title, re.IGNORECASE)
        if m:
            inst = m.group(1).strip()
        else:
            # Alternatif: İlk birkaç kelime
            inst = " ".join(title.split()[:3])

    inst = re.sub(r"\s+(?:ALACAK|ALIMI|İPTALİ|İPTAL|DÜZELTME).*$", "", inst, flags=re.IGNORECASE).strip(" -:,")

    # 2. Pozisyon Çözümleme
    if not position or position == "Kamu Personeli" or position == "None":
        pos_part = title
        if inst and title.startswith(inst):
            pos_part = title[len(inst):].strip()
        pos_clean = re.sub(r"^\s*(\d+\s*)+", "", pos_part)
        pos_clean = re.sub(r"\s*(?:alacak|alımı|temin edilecek|alınacaktır|alım ilanı).*$", "", pos_clean, flags=re.IGNORECASE)
        pos_clean = re.sub(r"\s*\([^\)]*\)", "", pos_clean)
        position = pos_clean.strip(" -:,")
        if not position:
            position = "Kamu Personeli"

    # 3. Kontenjan (Total Positions) Çözümleme
    quota = job.total_positions or 1
    nums = [int(n) for n in re.findall(r"\b(\d+)\b", title)]
    if nums and nums[0] > 0 and nums[0] < 5000:
        quota = nums[0]

    return inst, position, quota, is_cancellation


def determine_category(inst: str, title: str, position: str) -> tuple:
    """İlanın kategorisini ve kategori kısa adını (slug) belirler."""
    combined = f"{inst} {title} {position}".upper()

    if "BELEDİYE" in combined or "BELEDİYESİ" in combined:
        return ("Belediye Başkanlıkları", "belediye", "🏛")
    elif any(k in combined for k in ["ÖĞRETİM ÜYESİ", "ÖĞRETİM ELEMANI", "ARAŞTIRMA GÖREVLİSİ", "DOÇENT", "PROFESÖR", "ÜNİVERSİTE", "ÖĞR. GÖR."]):
        return ("Akademik Kadrolar", "akademik", "🎓")
    elif any(k in combined for k in ["BİLİŞİM", "YAZILIM", "MÜHENDİS", "MİMAR", "TEKNİKER", "TEKNİSYEN", "PROGRAMCI"]):
        return ("Bilişim & Teknik Kadrolar", "bilisim", "💻")
    elif any(k in combined for k in ["TABİP", "DİŞ TABİBİ", "HEMŞİRE", "EBELER", "SAĞLIK MEMURU", "HASTANE", "DİYETİSYEN"]):
        return ("Sağlık Personeli", "saglik", "🏥")
    elif any(k in combined for k in ["SUBAY", "ASTSUBAY", "JANDARMA", "EMNİYET", "POLİS", "BEKÇİ", "PİLOT", "MİLLİ SAVUNMA"]):
        return ("Askeri & Emniyet Personeli", "askeri", "🛡")
    elif any(k in combined for k in ["SÜREKLİ İŞÇİ", "İŞÇİ ALACAK", "İŞÇİ", "TEMİZLİK GÖREVLİSİ", "GÜVENLİK GÖREVLİSİ", "ŞOFÖR"]):
        return ("Sürekli İşçi Alımları", "isci", "⚙")
    elif any(k in combined for k in ["SÖZLEŞMELİ", "4/B", "DESTEK PERSONELİ", "BÜRO PERSONELİ"]):
        return ("Sözleşmeli Personel", "sozlesmeli", "📑")
    elif any(k in combined for k in ["MEMUR", "UZMAN", "MÜFETTİŞ", "KAYMAKAM", "İCRA MÜDÜR", "DENETÇİ"]):
        return ("Memur & Genel İdari Kadrolar", "memur", "👔")
    else:
        return ("Kamu Personeli / Diğer", "diger", "📋")


def export_data(output_paths: List[Path]) -> None:
    """Veritabanından tüm ilanları çekip jobs.json oluşturur."""
    print("🔄 Veritabanından ilanlar okunuyor...")

    with get_db() as db:
        jobs = db.query(JobAnnouncement).order_by(JobAnnouncement.id.desc()).all()
        print(f"✅ Toplam {len(jobs)} ilan bulundu.")

        exported_jobs = []
        category_counts = {}
        date_groups_dict = {}
        total_quotas = 0
        featured_candidates = []

        for j in jobs:
            inst, pos, quota, is_canc = clean_institution_and_position(j)
            cat_name, cat_slug, cat_icon = determine_category(inst, j.title, pos)

            # Tarih Çıkarımı
            raw = j.raw_content or ""
            m_dates = re.search(r"Başvuru Tarihleri:\s*([^\n\r]+)", raw)
            dates_interval = m_dates.group(1).strip() if m_dates else ""
            if not dates_interval and j.application_end_date:
                dates_interval = f"Son Başvuru: {format_tr_date(j.application_end_date)}"

            date_group, sort_val = parse_date_group_and_sort(dates_interval, j.application_end_date)

            total_quotas += quota
            category_counts[cat_name] = category_counts.get(cat_name, 0) + 1
            date_groups_dict[date_group] = date_groups_dict.get(date_group, 0) + 1

            # Durum Tespiti
            status_text = "BAŞVURUYA AÇIK"
            if is_canc:
                status_text = "İPTAL / DÜZELTME"
            elif j.application_end_date and j.application_end_date.date() < datetime.now().date():
                status_text = "SÜRESİ DOLDU"

            # Resmi Kılavuz (PDF) Doğrudan Yerel Dosya Eşleştirmesi
            # 404 hatasını önlemek için doğrudan documents/ klasöründeki yerel PDF bağlanır
            pdf_filename = f"sbb_{j.id}.pdf"
            docs_pdf_dest = ROOT_DIR / "docs" / "documents" / pdf_filename

            # Eğer docs/documents içinde henüz yoksa ama yerel bir PDF indirilmişse otomatik kopyala
            if not docs_pdf_dest.exists():
                src_cand = None
                for candidate in [j.pdf_path, ROOT_DIR / "data" / "documents" / pdf_filename, ROOT_DIR / "data" / "documents" / f"{j.id}.pdf"]:
                    if candidate and Path(candidate).exists() and Path(candidate).stat().st_size > 100:
                        src_cand = Path(candidate)
                        break
                if src_cand:
                    try:
                        docs_pdf_dest.parent.mkdir(parents=True, exist_ok=True)
                        import shutil
                        shutil.copy2(src_cand, docs_pdf_dest)
                    except Exception:
                        pass

            local_pdf_exists = docs_pdf_dest.exists()
            direct_pdf_url = f"documents/{pdf_filename}" if local_pdf_exists else None
            portal_url = "https://kamuilan.sbb.gov.tr/"

            # İlan Özeti
            edu_req = j.education_level or "Resmi Kılavuzda Belirtilmiştir"
            kpss_req = j.kpss_requirement or "Resmi İlanda Belirtilmiştir"
            city_name = j.city or "Türkiye Geneli / İlanda Belirtilen İller"

            item = {
                "id": j.id,
                "institution": inst,
                "title": j.title,
                "position": pos,
                "total_positions": quota,
                "category": cat_name,
                "category_slug": cat_slug,
                "category_icon": cat_icon,
                "date_interval": dates_interval,
                "pub_date_group": date_group,
                "sort_key": sort_val,
                "end_date_str": format_tr_date(j.application_end_date),
                "is_cancellation": is_canc,
                "status": status_text,
                "education_level": edu_req,
                "kpss_requirement": kpss_req,
                "city": city_name,
                "has_pdf": local_pdf_exists,
                "pdf_url": direct_pdf_url,
                "source_url": portal_url,
                "is_featured": quota >= 20 or any(b in inst.upper() for b in ["BAKANLIĞI", "GELİR İDARESİ", "SAVUNMA SANAYİİ", "BDDK", "SPK", "YARGITAY"]),
            }
            exported_jobs.append(item)

            if item["is_featured"] and not is_canc and len(featured_candidates) < 6:
                featured_candidates.append(item)

        # Tarih gruplarını sıralı liste haline getir
        # En yeni tarihler en üstte
        unique_groups = sorted(
            [{"name": k, "count": v, "sort_key": max([x["sort_key"] for x in exported_jobs if x["pub_date_group"] == k])}
             for k, v in date_groups_dict.items()],
            key=lambda x: x["sort_key"],
            reverse=True
        )

        # Meta Veri
        payload = {
            "meta": {
                "portal_name": "Kamu Personel Rehberi",
                "tagline": "Türkiye Cumhuriyeti Resmi Kamu Personel Alım İlanları Portalı",
                "domain": "kamupersonelrehberiniz.me",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "total_active_jobs": len(exported_jobs),
                "total_quotas": total_quotas,
                "active_visitors": 2071,
                "telegram_channel": "https://t.me/kamupersonelrehberi",
                "instagram_account": "https://instagram.com/kamupersonelrehberi",
                "categories": [
                    {"name": k, "count": v} for k, v in sorted(category_counts.items(), key=lambda x: x[1], reverse=True)
                ],
                "date_groups": unique_groups,
                "featured_jobs": featured_candidates[:6]
            },
            "jobs": exported_jobs
        }

        # Dosyaları yaz
        for out_path in output_paths:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            print(f"💾 JSON başarıyla kaydedildi: {out_path} ({len(exported_jobs)} ilan)")


def sync_and_push(auto_push: bool = True) -> bool:
    """
    Veritabanındaki güncel ilanları JSON'a aktarır ve
    otomatik olarak GitHub Pages deposuna (origin main) push eder.
    """
    import subprocess
    out_files = [
        ROOT_DIR / "website" / "data" / "jobs.json",
        ROOT_DIR / "docs" / "data" / "jobs.json"
    ]
    export_data(out_files)

    if not auto_push:
        return True

    try:
        # Değişiklikleri stage'e al (Veri JSON'ları + Yeni İndirilen PDF Kılavuzları)
        subprocess.run(["git", "add", "docs/data/jobs.json", "website/data/jobs.json", "docs/documents/"], cwd=str(ROOT_DIR), check=True)

        # Stage'de değişiklik var mı kontrol et
        diff_res = subprocess.run(["git", "diff", "--staged", "--quiet"], cwd=str(ROOT_DIR))
        if diff_res.returncode == 0:
            print("ℹ️ Veri dosyalarında yeni bir değişiklik yok, git push atlanıyor.")
            return True

        # Commit at ve push et
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        subprocess.run(
            ["git", "commit", "-m", f"chore(data): auto-sync live jobs [{now_str}] [skip ci]"],
            cwd=str(ROOT_DIR),
            check=True
        )
        push_res = subprocess.run(["git", "push", "origin", "main"], cwd=str(ROOT_DIR), check=True)
        print("🚀 Güncel ilan verileri başarıyla GitHub Pages'e push edildi!")
        return True
    except Exception as e:
        print(f"⚠️ Git otomatik senkronizasyon uyarısı: {e}")
        return False


if __name__ == "__main__":
    sync_and_push(auto_push=False)

