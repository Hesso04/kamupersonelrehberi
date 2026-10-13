from typing import List, Dict, Tuple, Optional
from datetime import datetime
from loguru import logger

from config.settings import settings
from core.database import get_db, get_system_setting
from core.models import JobAnnouncement, JobStatus
from graphics.generator import JobCardGenerator
from graphics.modern_generator import ModernCardGenerator
from .base import BasePublisher
from .telegram import TelegramPublisher
from .whatsapp import WhatsAppPublisher
from .instagram import InstagramPublisher
from .facebook import FacebookPublisher


class PublisherManager:
    """
    Tüm sosyal medya kanallarına gönderimi koordine eden merkezi servis.
    Yeni nesil modern dikey afiş motoruyla görseli üretir,
    seçilen platformlara (Telegram, WhatsApp, Instagram, Facebook) dağıtır,
    başarısızlık teşhisini saklar ve veritabanı durumunu günceller.
    """

    def __init__(self):
        self.telegram = TelegramPublisher()
        self.whatsapp = WhatsAppPublisher()
        self.instagram = InstagramPublisher()
        self.facebook = FacebookPublisher()
        self.card_generator = JobCardGenerator()
        self.modern_card_generator = ModernCardGenerator()

    def publish_job(
        self,
        job_id: int,
        channels: Optional[List[str]] = None,
        theme: Optional[str] = None
    ) -> Dict[str, Tuple[bool, str]]:
        """
        Belirtilen ilanı seçilen kanallara gönderir.
        Görsel kartı istenen tema ile üretir.
        
        KRİTİK TASARIM: Tüm kanal sonuçları toplanır, DB güncellemesi en sonda
        TEK BİR atomik commit ile yapılır. _persist_success_immediately kaldırıldı
        çünkü get_db() context manager'ın çift commit'i rollback'e neden oluyordu.
        """
        if channels is None:
            channels = ["TELEGRAM"]
        results = {}

        with get_db() as db:
            job = db.query(JobAnnouncement).filter(JobAnnouncement.id == job_id).first()
            if not job:
                return {"error": (False, f"İlan bulunamadı: ID {job_id}")}

            # SAVUNMA HATTI: Bu ilan zaten PUBLISHED ise hiçbir şey yapma
            if job.status == JobStatus.PUBLISHED:
                cur_pub = [c.strip().upper() for c in (job.published_channels or "").split(",") if c.strip()]
                requested = [c.upper() for c in channels]
                missing = [c for c in requested if c not in cur_pub]
                if not missing:
                    logger.info(f"İlan #{job_id} tüm hedef kanallarda zaten PUBLISHED — atlanıyor.")
                    return {c: (True, "Zaten yayınlanmış") for c in requested}
                # Eksik kanal varsa sadece onları dene
                channels = missing

            # Pozisyon ve kontenjan kontrolü / onarımı
            import re
            from pathlib import Path
            from config.settings import settings
            from graphics.generator import to_turkish_date_str, tr_title
            website_domain = getattr(settings, "WEBSITE_URL", "kamupersonelrehberiniz.me").replace("https://", "").replace("http://", "").strip("/")

            if job.status in [JobStatus.DRAFT, JobStatus.PENDING_APPROVAL] and not job.social_post_text:
                pos_src = job.position if (job.position and job.position != "None") else job.title.split(" - ")[-1]
                pos_clean = re.sub(r"^\s*(\d+\s*)+", "", pos_src)
                pos_clean = re.sub(r"\s*(?:alacak|alımı|temin edilecek|alınacaktır|alınacak|alım ilanı).*$", "", pos_clean, flags=re.IGNORECASE)
                pos_clean = pos_clean.strip(" -:,")
                pos_clean = re.sub(r"\bpersoneli\b", "Personel", pos_clean, flags=re.IGNORECASE)
                job.position = tr_title(pos_clean) or "Kamu Personeli"

                all_nums = [int(n) for n in re.findall(r"\b(\d+)\b", job.title)]
                if len(all_nums) > 1 and ("," in job.title or " ve " in job.title):
                    job.total_positions = sum(all_nums)
                elif all_nums and all_nums[0] > 1:
                    job.total_positions = all_nums[0]
                elif not job.total_positions:
                    job.total_positions = 1

            has_pdf = bool(job.pdf_path and Path(job.pdf_path).exists())
            deadline_str = to_turkish_date_str(job.application_end_date)

            # İptal veya Düzeltme İlanı Kontrolü
            title_upper = (job.title or "").upper()
            pos_upper = (job.position or "").upper()
            is_cancellation = any(
                w in title_upper or w in pos_upper
                for w in ["İPTAL", "IPTAL", "DÜZELTME", "DUZELTME", "İLAN İPTALİ"]
            )

            # BUG-01: Başvuru süresi geçmiş normal ilanların paylaşımını kesin olarak engelle ve DB'de REJECTED yap
            if not is_cancellation and job.application_end_date and job.application_end_date.date() < datetime.now().date():
                warn_msg = f"İlanın son başvuru tarihi ({deadline_str}) geçmiş olduğundan yayınlanamaz."
                logger.warning(f"İlan #{job.id} engellendi: {warn_msg}")
                job.status = JobStatus.REJECTED
                job.admin_notes = f"[Süresi Doldu: {deadline_str}] Sistem tarafından otomatik arşivlendi."
                # get_db() context manager otomatik commit yapacak
                return {"error": (False, warn_msg)}

            # Sosyal medya metnini YALNIZCA boşsa üret (BUG-08: AI/admin düzenlemeleri korunsun)
            if not job.social_post_text:
                portal_base = "https://kamupersonelrehberiniz.me"
                portal_job_url = f"{portal_base}/?ilan={job.id}" if getattr(job, "id", None) else f"{portal_base}/"

                if is_cancellation:
                    pdf_info = "📄 <b>Resmi İptal Kararı (PDF):</b> Ekte sunulmuştur." if has_pdf else f"🌐 <b>İptal Detayları & Açıklama:</b> {portal_job_url}"
                    job.social_post_text = (
                        f"🚨 🛑 <b>[DİKKAT: İLAN İPTAL DUYURUSU]</b> 🛑 🚨\n\n"
                        f"🏛 <b>Kurum:</b> {job.institution or 'Kamu Kurumu'}\n"
                        f"❌ <b>Durum:</b> <b><u>ALIM SÜRECİ RESMEN İPTAL EDİLMİŞTİR</u></b>\n"
                        f"📋 <b>İptal Edilen Pozisyon:</b> {job.position}\n"
                        f"🗓 <b>Duyuru Tarihi:</b> {deadline_str}\n\n"
                        f"⚠️ <b>ÖNEMLİ BİLGİLENDİRME:</b> Bu duyuru yeni bir alım ilanı <u>DEĞİLDİR</u>! Daha önce yayımlanan personel alım süreci ilgili resmi kurum tarafından <b>RESMEN İPTAL EDİLMİŞTİR</b>. Yeni başvuru kabul edilmemektedir.\n\n"
                        f"{pdf_info}\n\n"
                        f"🌐 <b>Tüm Güncel İlanlar:</b> https://{website_domain}\n\n"
                        f"📲 <i>Adayların boşuna başvuru hazırlığı yapmaması için arkadaşlarınızla paylaşınız!</i>\n"
                        f"#KamuPersoneli #İptalİlanı #Duyuru #KamuHaber"
                    )
                else:
                    pdf_info = "📄 <b>Resmi Kılavuz & Başvuru:</b> Resmi alım şartnamesi ve kadro tablosu (PDF) ekte sunulmuştur." if has_pdf else f"🌐 <b>Resmi Kılavuz & Şartlar:</b> {portal_job_url}"
                    job.social_post_text = (
                        f"📢 <b>{job.institution or 'Kamu Kurumu'} Personel Alım İlanı</b>\n\n"
                        f"🏛 <b>Kurum:</b> {job.institution or 'Kamu Kurumu'}\n"
                        f"📋 <b>Kadro / Pozisyon:</b> {job.position}\n"
                        f"👥 <b>Kontenjan:</b> {job.total_positions or 1} Kişi\n"
                        f"🗓 <b>Son Başvuru:</b> {deadline_str}\n"
                        f"🎓 <b>Öğrenim:</b> {job.education_level or 'Kılavuzda belirtilen mezuniyet şartı'}\n"
                        f"🎯 <b>KPSS:</b> {job.kpss_requirement or 'Resmi ilanda belirtilen puan şartı'}\n\n"
                        f"{pdf_info}\n\n"
                        f"🌐 <b>Resmi Başvuru Ekranı & İlan Detayı:</b> {portal_job_url}\n\n"
                        f"⚠️ <i>Bilgi kirliliğine karşı %100 teyitli resmi kamu ilanıdır.</i>\n"
                        f"#KamuPersoneli #İlan #KamuAlımı"
                    )

            # 1. Görseli Yeni Nesil Modern Afiş Motoru ile Üret (yalnızca görsel yoksa)
            if not job.image_path or not Path(job.image_path).exists():
                try:
                    image_path = self.modern_card_generator.generate_modern_card(
                        job_id=job.id,
                        institution=job.institution or "Kamu Kurumu",
                        position=job.position or "Personel Alımı",
                        title=job.title or "",
                        total_positions=job.total_positions,
                        kpss_requirement=job.kpss_requirement,
                        education_level=job.education_level,
                        deadline=job.application_end_date,
                        website_url=website_domain
                    )
                    job.image_path = str(image_path)
                except Exception as me:
                    logger.warning(f"Modern görsel üretilemedi, klasik Pillow motoruna geçiliyor: {me}")
                    try:
                        card_theme = theme or get_system_setting("DEFAULT_CARD_THEME", "OFFICIAL_NAVY")
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
                            theme=card_theme,
                            title=job.title or ""
                        )
                        job.image_path = str(image_path)
                    except Exception as ce:
                        logger.error(f"Görsel üretimi tamamen başarısız: {ce}")

            upper_channels = [c.upper() for c in channels]
            successful_channels = []
            failed_channels_log = []

            # ========== KANAL DAĞITIMI (Sonuçlar toplanır, DB en sonda güncellenir) ==========

            # 2. Instagram Dağıtımı (Önce Instagram Carousel ve Story doğrulanır ve yayınlanır)
            if "INSTAGRAM" in upper_channels:
                try:
                    i_success, i_msg = self.instagram.publish(job)
                    results["INSTAGRAM"] = (i_success, i_msg)
                    if i_success:
                        successful_channels.append("INSTAGRAM")
                    else:
                        failed_channels_log.append(f"Instagram: {i_msg}")
                except Exception as ig_err:
                    results["INSTAGRAM"] = (False, f"Instagram Exception: {ig_err}")
                    failed_channels_log.append(f"Instagram: {ig_err}")
                    logger.error(f"Instagram yayın istisnası: {ig_err}")

            # 3. Telegram Dağıtımı (Anında kanala butonları ve PDF ile iletilir)
            if "TELEGRAM" in upper_channels:
                try:
                    t_success, t_msg = self.telegram.publish(job)
                    results["TELEGRAM"] = (t_success, t_msg)
                    if t_success:
                        successful_channels.append("TELEGRAM")
                    else:
                        failed_channels_log.append(f"Telegram: {t_msg}")
                except Exception as tg_err:
                    results["TELEGRAM"] = (False, f"Telegram Exception: {tg_err}")
                    failed_channels_log.append(f"Telegram: {tg_err}")
                    logger.error(f"Telegram yayın istisnası: {tg_err}")

            # 4. Facebook Sayfa Dağıtımı
            if "FACEBOOK" in upper_channels:
                try:
                    f_success, f_msg = self.facebook.publish(job)
                    results["FACEBOOK"] = (f_success, f_msg)
                    if f_success:
                        successful_channels.append("FACEBOOK")
                    else:
                        failed_channels_log.append(f"Facebook: {f_msg}")
                except Exception as fb_err:
                    results["FACEBOOK"] = (False, f"Facebook Exception: {fb_err}")
                    failed_channels_log.append(f"Facebook: {fb_err}")

            # 5. WhatsApp Dağıtımı
            if "WHATSAPP" in upper_channels:
                try:
                    w_success, w_msg = self.whatsapp.publish(job)
                    results["WHATSAPP"] = (w_success, w_msg)
                    if w_success:
                        successful_channels.append("WHATSAPP")
                    else:
                        failed_channels_log.append(f"WhatsApp: {w_msg}")
                except Exception as wa_err:
                    results["WHATSAPP"] = (False, f"WhatsApp Exception: {wa_err}")
                    failed_channels_log.append(f"WhatsApp: {wa_err}")

            # ========== TEK ATOMİK DB GÜNCELLEMESİ ==========
            # Tüm kanal sonuçları toplandıktan sonra DB'yi güncelle
            if successful_channels:
                # Mevcut published_channels ile birleştir
                cur_list = [c.strip().upper() for c in (job.published_channels or "").split(",") if c.strip()]
                for ch in successful_channels:
                    if ch not in cur_list:
                        cur_list.append(ch)
                job.published_channels = ",".join(cur_list)
                job.status = JobStatus.PUBLISHED
                if not job.published_at:
                    job.published_at = datetime.utcnow()

            # Son durum notu güncellemesi
            if failed_channels_log:
                err_summary = " | ".join(failed_channels_log)
                safe_summary = re.sub(r"[^\w\s\.,\-:;()\[\]/]", "", err_summary)
                job.admin_notes = f"[Kanal Hatası: {safe_summary[:300]}]"
            elif successful_channels:
                job.admin_notes = "Tüm hedeflenen kanallarda başarıyla yayınlandı."

            # get_db() context manager otomatik commit yapacak — TEK commit, TEK transaction
            # Bu sayede çift-commit rollback sorunu tamamen ortadan kalkar

        return results

    def publish_missing_channels(
        self,
        job_id: int,
        target_channels: Optional[List[str]] = None,
        theme: Optional[str] = None
    ) -> Dict[str, Tuple[bool, str]]:
        """
        Bir ilan için henüz yayınlanmamış eksik kanalları tespit edip sadece onlara dağıtım yapar.
        Örn: İlan Telegram'a gitmiş ama Instagram veya Facebook başarısız olmuşsa,
        sadece Instagram ve Facebook'u yeniden dener, Telegram'a mükerrer mesaj atmaz.
        """
        with get_db() as db:
            job = db.query(JobAnnouncement).filter(JobAnnouncement.id == job_id).first()
            if not job:
                return {"error": (False, f"İlan bulunamadı: ID {job_id}")}

            cur_pub = [c.strip().upper() for c in (job.published_channels or "").split(",") if c.strip()]
            
            if not target_channels:
                raw_ap = get_system_setting("AUTOPILOT_CHANNELS", "TELEGRAM,INSTAGRAM,FACEBOOK")
                target_channels = [c.strip().upper() for c in raw_ap.split(",") if c.strip()]

            missing = [c for c in target_channels if c not in cur_pub]
            if not missing:
                return {"info": (True, "Tüm hedeflenen kanallarda zaten yayınlanmış.")}

            logger.info(f"İlan #{job_id} için eksik kanallar tamamlanıyor: {missing}")
            return self.publish_job(job_id=job_id, channels=missing, theme=theme)
