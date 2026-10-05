from typing import List, Dict, Any
from datetime import datetime
from loguru import logger
from sqlalchemy.orm import Session

from core.database import get_db
from core.models import JobAnnouncement, JobStatus
from .base import BaseScraper, ScrapedJob
from .kamu_ilan_sbb import SBBKamuIlanScraper
from .resmi_gazete import ResmiGazeteScraper


class ScraperManager:
    """
    Tüm resmi kazıyıcıları yöneten, mükerrer kayıtları (deduplication)
    engelleyen ve veritabanı senkronizasyonunu sağlayan merkezi servis.
    """

    def __init__(self):
        self.scrapers: List[BaseScraper] = [
            SBBKamuIlanScraper(),
            ResmiGazeteScraper(),
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

                        # 2. Mükerrer kontrolü: Benzersiz resmi belge linki veya tam başlık kontrolü
                        query_filter = (JobAnnouncement.title == job.title)
                        if job.official_doc_url:
                            query_filter = query_filter | (JobAnnouncement.official_doc_url == job.official_doc_url)
                        elif job.source_url:
                            query_filter = query_filter | (JobAnnouncement.source_url == job.source_url)

                        existing = db.query(JobAnnouncement).filter(query_filter).first()

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
                            application_end_date=job.publish_date if (job.publish_date and job.publish_date != datetime.utcnow()) else None,
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
