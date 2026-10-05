from typing import List, Dict, Tuple, Optional
from datetime import datetime
from loguru import logger

from core.database import get_db
from core.models import JobAnnouncement, JobStatus
from graphics.generator import JobCardGenerator
from .base import BasePublisher
from .telegram import TelegramPublisher
from .whatsapp import WhatsAppPublisher
from .instagram import InstagramPublisher
from .facebook import FacebookPublisher


class PublisherManager:
    """
    Tüm sosyal medya kanallarına gönderimi koordine eden merkezi servis.
    Eğer ilan görseli henüz üretilmemişse dinamik QR kod ile anında üretir,
    seçilen platformlara (Telegram, WhatsApp, Instagram, Facebook) dağıtır
    ve veritabanı durumunu günceller.
    """

    def __init__(self):
        self.telegram = TelegramPublisher()
        self.whatsapp = WhatsAppPublisher()
        self.instagram = InstagramPublisher()
        self.facebook = FacebookPublisher()
        self.card_generator = JobCardGenerator()

    def publish_job(
        self,
        job_id: int,
        channels: List[str] = ["TELEGRAM"],
        theme: Optional[str] = None
    ) -> Dict[str, Tuple[bool, str]]:
        """
        Belirtilen ilanı seçilen kanallara gönderir.
        Görsel kartı istenen tema ile (varsayılan: DARK_NOIR veya ayarlardaki tema) üretir.
        """
        results = {}

        with get_db() as db:
            job = db.query(JobAnnouncement).filter(JobAnnouncement.id == job_id).first()
            if not job:
                return {"error": (False, f"İlan bulunamadı: ID {job_id}")}

            # Pozisyon ve kontenjan kontrolü / onarımı
            import re
            from pathlib import Path
            from graphics.generator import to_turkish_date_str, tr_title
            from core.database import get_system_setting

            # Unvan ve pozisyon temizliği (Örn: "23 SÖZLEŞMELİ PERSONEL Alımı" -> "Sözleşmeli Personel")
            pos_src = job.position if (job.position and job.position != "None") else job.title.split(" - ")[-1]
            pos_clean = re.sub(r"^\s*(\d+\s*)+", "", pos_src)
            pos_clean = re.sub(r"\s*(?:alacak|alımı|temin edilecek|alınacaktır|alınacak|alım ilanı).*$", "", clean_pos if 'clean_pos' in locals() else pos_clean, flags=re.IGNORECASE)
            pos_clean = pos_clean.strip(" -:,")
            pos_clean = re.sub(r"\bpersoneli\b", "Personel", pos_clean, flags=re.IGNORECASE)
            job.position = tr_title(pos_clean) or "Kamu Personeli"

            # Kontenjan sayısı
            all_nums = [int(n) for n in re.findall(r"\b(\d+)\b", job.title)]
            if len(all_nums) > 1 and ("," in job.title or " ve " in job.title):
                job.total_positions = sum(all_nums)
            elif all_nums and all_nums[0] > 1:
                job.total_positions = all_nums[0]
            elif not job.total_positions:
                job.total_positions = 1

            has_pdf = bool(job.pdf_path and Path(job.pdf_path).exists())
            deadline_str = to_turkish_date_str(job.application_end_date)

            # Sosyal medya metnini her zaman kurumsal ve güncel olarak hazırla
            pdf_info = "📄 <b>Resmi Kılavuz & Başvuru:</b> Resmi alım şartnamesi ve kadro tablosu (PDF) ekte sunulmuştur." if has_pdf else f"🔗 <b>Resmi İlan Linki:</b> {job.source_url or 'https://kamuilan.sbb.gov.tr/'}"
            job.social_post_text = (
                f"📢 <b>{job.institution or 'Kamu Kurumu'} Personel Alım İlanı</b>\n\n"
                f"🏛 <b>Kurum:</b> {job.institution or 'Kamu Kurumu'}\n"
                f"📋 <b>Kadro / Pozisyon:</b> {job.position}\n"
                f"👥 <b>Kontenjan:</b> {job.total_positions or 1} Kişi\n"
                f"🗓 <b>Son Başvuru:</b> {deadline_str}\n"
                f"🎓 <b>Öğrenim:</b> {job.education_level or 'Kılavuzda belirtilen mezuniyet şartı'}\n"
                f"🎯 <b>KPSS:</b> {job.kpss_requirement or 'Resmi ilanda belirtilen puan şartı'}\n\n"
                f"{pdf_info}\n\n"
                f"⚠️ <i>Bilgi kirliliğine karşı %100 teyitli resmi kamu ilanıdır.</i>\n"
                f"#KamuPersoneli #İlan #KamuAlımı"
            )

            # 1. Otopilot ve her yayında görseli seçili temayla TAZE üret
            try:
                card_theme = theme or get_system_setting("DEFAULT_CARD_THEME", "DARK_NOIR")
                image_path = self.card_generator.generate_card(
                    job_id=job.id,
                    institution=job.institution or "Kamu Kurumu",
                    position=job.position,
                    total_positions=job.total_positions,
                    kpss_requirement=job.kpss_requirement,
                    education_level=job.education_level,
                    deadline=deadline_str,
                    source_url=job.source_url,
                    has_pdf=has_pdf,
                    theme=card_theme
                )
                job.image_path = str(image_path)
            except Exception as e:
                logger.warning(f"Görsel üretilemedi: {e}")

            db.commit()

            upper_channels = [c.upper() for c in channels]
            successful_channels = []

            # 2. Telegram Dağıtımı
            if "TELEGRAM" in upper_channels:
                t_success, t_msg = self.telegram.publish(job)
                results["TELEGRAM"] = (t_success, t_msg)
                if t_success:
                    successful_channels.append("TELEGRAM")

            # 3. WhatsApp Dağıtımı
            if "WHATSAPP" in upper_channels:
                w_success, w_msg = self.whatsapp.publish(job)
                results["WHATSAPP"] = (w_success, w_msg)
                if w_success:
                    successful_channels.append("WHATSAPP")

            # 4. Instagram Dağıtımı
            if "INSTAGRAM" in upper_channels:
                i_success, i_msg = self.instagram.publish(job)
                results["INSTAGRAM"] = (i_success, i_msg)
                if i_success:
                    successful_channels.append("INSTAGRAM")

            # 5. Facebook Sayfa Dağıtımı
            if "FACEBOOK" in upper_channels:
                f_success, f_msg = self.facebook.publish(job)
                results["FACEBOOK"] = (f_success, f_msg)
                if f_success:
                    successful_channels.append("FACEBOOK")

            # Eğer en az bir kanalda başarıyla yayınlandıysa durumu PUBLISHED yap
            if successful_channels:
                current_channels = job.published_channels.split(",") if job.published_channels else []
                for sc in successful_channels:
                    if sc not in current_channels:
                        current_channels.append(sc)
                job.published_channels = ",".join(current_channels)
                job.status = JobStatus.PUBLISHED
                job.published_at = datetime.utcnow()
                db.commit()

        return results
