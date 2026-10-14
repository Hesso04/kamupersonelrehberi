from typing import List, Dict, Any
from datetime import datetime
from loguru import logger
from sqlalchemy.orm import Session

from core.database import get_db
from core.models import JobAnnouncement, JobStatus
from .base import BaseScraper, ScrapedJob
from .kamu_ilan_sbb import SBBKamuIlanScraper
from .resmi_gazete import ResmiGazeteScraper
from .ilan_gov_tr import IlanGovTrScraper
from .kariyer_kapisi import KariyerKapisiScraper
from .iskur_kamu import IskurKamuScraper
from .csb_yerel_yonetimler import CSBYerelYonetimlerScraper


import re

def make_title_fingerprint(text: str) -> str:
    """Başlıktan harf/rakam özeti çıkararak küçük yazım farklarında dahi mükerrerliği yakalar."""
    if not text:
        return ""
    t = text.lower().replace("İ", "i").replace("I", "i").replace("ı", "i").replace("i̇", "i")
    t = re.sub(r"(?:alimi|alacak|alinacaktir|alacaktir|personel|sozlesmeli|sinavi|basvurulari|duyurusu)", "", t)
    t = re.sub(r"[^a-z0-9]", "", t)
    return t


class ScraperManager:
    """
    Tüm resmi kazıyıcıları yöneten, mükerrer kayıtları (deduplication)
    engelleyen ve veritabanı senkronizasyonunu sağlayan merkezi servis.
    Tüm kaynaklar resmi, yasal ve teyitli kamu alım portallarıdır.
    """

    def __init__(self):
        self.scrapers: List[BaseScraper] = [
            SBBKamuIlanScraper(),
            ResmiGazeteScraper(),
            IlanGovTrScraper(),
            KariyerKapisiScraper(),
            IskurKamuScraper(),
            CSBYerelYonetimlerScraper(),
        ]

    def run_all(self) -> Dict[str, Any]:
        """
        Tüm aktif kazıyıcıları sırayla çalıştırır ve yeni ilanları veritabanına ekler.
        """
        total_found = 0
        new_added = 0
        duplicates = 0
        errors = []

        logger.info("Resmi kaynak tarama işlemi başlatıldı...")

        for scraper in self.scrapers:
            try:
                logger.info(f"{scraper.source_name} taranıyor...")
                jobs = scraper.fetch_jobs()
                total_found += len(jobs)

                with get_db() as db:
                    for job in jobs:
                        # 1. URL'nin resmi kurum alan adı olup olmadığını doğrula
                        if not scraper.is_official_source(job.source_url):
                            logger.warning(f"Resmi olmayan şüpheli kaynak atlandı: {job.source_url}")
                            continue

                        # 2. Mükerrer kontrolü: Çok Katmanlı Güçlü Deduplication
                        existing = None
                        if job.official_doc_url:
                            existing = db.query(JobAnnouncement).filter(JobAnnouncement.official_doc_url == job.official_doc_url).first()

                        if not existing:
                            existing = db.query(JobAnnouncement).filter(JobAnnouncement.title == job.title).first()

                        # Akıllı Parmak İzi & Kurum Kontrolü (Başlıktaki küçük yazım farklarına rağmen aynı ilanı yakalar)
                        if not existing:
                            fp_new = make_title_fingerprint(job.title)
                            from sqlalchemy import or_
                            today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
                            
                            # Son başvuru tarihi dolmamış güncel ilanları tara
                            active_candidates = db.query(JobAnnouncement).filter(
                                or_(
                                    JobAnnouncement.application_end_date.is_(None),
                                    JobAnnouncement.application_end_date >= today_start
                                )
                            ).all()

                            for cand in active_candidates:
                                # Aynı kurum ve aynı parmak izi eşleşmesi
                                if make_title_fingerprint(cand.title) == fp_new and len(fp_new) >= 8:
                                    existing = cand
                                    break
                                # Veya aynı kurum ve aynı pozisyon eşleşmesi
                                if (
                                    job.institution and job.institution != "Kamu Kurumu" and
                                    cand.institution and cand.institution != "Kamu Kurumu" and
                                    cand.institution.strip().upper() == job.institution.strip().upper() and
                                    job.position and cand.position and
                                    cand.position.strip().upper() == job.position.strip().upper()
                                ):
                                    existing = cand
                                    break

                        if existing:
                            duplicates += 1
                            continue

                        # 3. Yeni ilanı veritabanına ekle (Onay Bekliyor statüsünde)
                        new_announcement = JobAnnouncement(
                            title=job.title[:340],
                            institution=job.institution[:240] if job.institution else "Kamu Kurumu",
                            position=job.position[:290] if job.position else None,
                            total_positions=job.total_positions or 1,
                            source_name=job.source_name,
                            source_url=job.source_url,
                            official_doc_url=job.official_doc_url,
                            pdf_path=job.pdf_path,
                            is_verified=job.is_verified,
                            raw_content=job.raw_content,
                            application_end_date=job.application_end_date if getattr(job, "application_end_date", None) else (job.publish_date if job.publish_date else None),
                            status=JobStatus.PENDING_APPROVAL,
                            created_at=datetime.utcnow()
                        )
                        db.add(new_announcement)
                        new_added += 1

            except Exception as e:
                err_msg = f"{scraper.source_name} taramasında hata: {str(e)}"
                logger.error(err_msg)
                errors.append(err_msg)

        summary = {
            "total_found": total_found,
            "new_added": new_added,
            "duplicates": duplicates,
            "errors": errors,
            "timestamp": datetime.utcnow()
        }
        logger.info(
            f"Tarama tamamlandı: {total_found} bulundu, "
            f"{new_added} yeni eklendi, {duplicates} mükerrer atlandı."
        )
        return summary
