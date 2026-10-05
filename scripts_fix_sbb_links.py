import io
import re
import sys
import requests
import urllib3
from pathlib import Path
from pypdf import PdfReader
from loguru import logger

from core.database import get_db
from core.models import JobAnnouncement
from scrapers.kamu_ilan_sbb import parse_turkish_date_range

urllib3.disable_warnings()

doc_dir = Path("data/documents")
doc_dir.mkdir(parents=True, exist_ok=True)

s = requests.Session()
BASE_URL = "https://kamuilan.sbb.gov.tr/"

def backfill_and_fix_sbb_jobs():
    logger.info("Mevcut SBB ilanlarının linkleri düzeltiliyor ve PDF'leri indiriliyor...")
    
    with get_db() as db:
        jobs = db.query(JobAnnouncement).filter(
            JobAnnouncement.source_name.like("%SBB%")
        ).all()
        
        logger.info(f"Toplam {len(jobs)} adet SBB ilanı kontrol ediliyor.")
        fixed_count = 0
        pdf_downloaded = 0
        
        for job in jobs:
            # 1. Link Mantık Düzeltmesi (404 hatasını kalıcı engelle)
            old_url = job.source_url
            if old_url and "ilanDetay.aspx" in old_url:
                job.official_doc_url = old_url
                job.source_url = BASE_URL
                fixed_count += 1
            
            # Sosyal medya metnindeki linki temizle
            if job.social_post_text and "ilanDetay.aspx" in job.social_post_text:
                job.social_post_text = re.sub(
                    r"https?://kamuilan\.sbb\.gov\.tr/ilanDetay\.aspx\S*",
                    "https://kamuilan.sbb.gov.tr/",
                    job.social_post_text
                )
                if "kılavuz" not in job.social_post_text.lower():
                    job.social_post_text += "\n📎 <i>Resmi ilan kılavuzu ve başvuru şartnamesi (PDF) ekte sunulmuştur.</i>"

            # 2. Tarih ayrıştırması
            if job.raw_content and not job.application_end_date:
                match = re.search(r"Başvuru Tarihleri:\s*(\d+\s+[A-Za-zÇŞĞÜÖİçşğüöı]+\s*-\s*\d+\s+[A-Za-zÇŞĞÜÖİçşğüöı]+)", job.raw_content)
                if match:
                    s_dt, e_dt = parse_turkish_date_range(match.group(1))
                    if e_dt:
                        job.application_end_date = e_dt

            # 3. PDF İndirme (Eğer henüz indirilmediyse)
            target_detail_url = job.official_doc_url or old_url
            pdf_path = doc_dir / f"sbb_{job.id}.pdf"
            
            if not pdf_path.exists() and target_detail_url and "ilanDetay.aspx" in target_detail_url:
                try:
                    r = s.get(
                        target_detail_url,
                        verify=False,
                        headers={"Referer": BASE_URL},
                        timeout=15
                    )
                    if r.status_code == 200 and r.content.startswith(b"%PDF"):
                        pdf_path.write_bytes(r.content)
                        job.pdf_path = str(pdf_path)
                        pdf_downloaded += 1
                        
                        # Metin çıkarımı
                        try:
                            reader = PdfReader(io.BytesIO(r.content))
                            pdf_text = ""
                            for p in reader.pages[:3]:
                                pt = p.extract_text()
                                if pt:
                                    pdf_text += pt + "\n"
                            if pdf_text and "RESMİ KILAVUZ METNİ" not in (job.raw_content or ""):
                                job.raw_content = (job.raw_content or "") + f"\n\n--- RESMİ KILAVUZ METNİ ({len(reader.pages)} Sayfa) ---\n" + pdf_text[:3000]
                        except Exception:
                            pass
                except Exception as ex:
                    logger.debug(f"PDF indirme atlandı (İlan #{job.id}): {ex}")
            elif pdf_path.exists():
                job.pdf_path = str(pdf_path)

        db.commit()
        logger.info(f"İşlem Tamamlandı! {fixed_count} link düzeltildi, {pdf_downloaded} yeni resmi PDF indirildi.")

if __name__ == "__main__":
    backfill_and_fix_sbb_jobs()
