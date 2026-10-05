from typing import Optional, List
from datetime import datetime
from loguru import logger
from sqlalchemy.orm import Session

from core.database import get_db
from core.models import JobAnnouncement, JobStatus
from .llm_client import LLMClient


class AIProcessor:
    """
    Veritabanındaki ham kamu ilanlarını yapay zeka ile zenginleştiren,
    yapısal verilerini çıkaran ve sosyal medya metinlerini oluşturan servis.
    Çoklu sağlayıcı (NVIDIA NIM, Groq, DeepSeek) desteğine sahiptir.
    """

    def __init__(self):
        self.llm_client = LLMClient()

    def process_job(self, job_id: int) -> Optional[JobAnnouncement]:
        """
        Belirtilen ID'ye sahip ilanı analiz eder ve veritabanını günceller.
        """
        with get_db() as db:
            job = db.query(JobAnnouncement).filter(JobAnnouncement.id == job_id).first()
            if not job:
                logger.error(f"İlan bulunamadı: ID {job_id}")
                return None

            ai_data = self.llm_client.analyze_announcement(
                title=job.title,
                raw_content=job.raw_content or "",
                source_url=job.source_url
            )

            # Çıkarılan yapısal verileri veritabanı modeline yaz
            if ai_data.get("institution"):
                job.institution = ai_data["institution"][:240]

            if ai_data.get("position"):
                job.position = ai_data["position"][:290]

            if ai_data.get("cleaned_title"):
                job.title = ai_data["cleaned_title"][:340]

            if ai_data.get("total_positions"):
                try:
                    job.total_positions = int(ai_data["total_positions"])
                except Exception:
                    pass

            if ai_data.get("kpss_requirement"):
                job.kpss_requirement = ai_data["kpss_requirement"][:140]

            if ai_data.get("education_level"):
                job.education_level = ai_data["education_level"][:190]

            if ai_data.get("city"):
                job.city = ai_data["city"][:140]

            # Maddeli özet
            bullets = ai_data.get("bullet_summary", [])
            if isinstance(bullets, list):
                job.ai_summary = "\n".join([f"• {b}" for b in bullets])
            else:
                job.ai_summary = str(bullets)

            # Sosyal medya paylaşım metni
            if ai_data.get("telegram_post"):
                job.social_post_text = ai_data["telegram_post"]

            job.status = JobStatus.AI_PROCESSED
            job.updated_at = datetime.utcnow()

            db.commit()
            db.refresh(job)
            logger.info(f"İlan AI ile başarıyla zenginleştirildi: ID {job.id} - {job.institution}")
            return job

    def batch_process_pending(self, limit: int = 5) -> List[int]:
        """
        Henüz AI tarafından işlenmemiş ilanları toplu olarak işler.
        """
        processed_ids = []
        with get_db() as db:
            pending_jobs = db.query(JobAnnouncement).filter(
                (JobAnnouncement.social_post_text == None) |
                (JobAnnouncement.status == JobStatus.PENDING_APPROVAL)
            ).limit(limit).all()

            target_ids = [j.id for j in pending_jobs]

        for j_id in target_ids:
            res = self.process_job(j_id)
            if res:
                processed_ids.append(res.id)

        return processed_ids
