"""
KAMU HABERLERİ & DOĞRULAMA AKIŞI SOSYAL MEDYA YAYINLAYICISI (NewsPublisher)
=============================================================================
ÖNEMLİ KURAL:
Bu servis varsayılan olarak PASİF (standby) durumdadır.
Yalnızca `AUTO_PUBLISH_NEWS_ENABLED` ayarı 'true' yapıldığında otopilot olarak
Telegram, Instagram vb. platformlara haber ağzıyla editoryal paylaşım yapar.
Hali hazırda çalışan ilan otomasyonunu asla etkilemez ve bozmaz.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
from loguru import logger

from core.database import get_db, get_system_setting, set_system_setting
from core.models import OfficialNews
from graphics.news_card_generator import NewsCardGenerator
from publishers.telegram import TelegramPublisher
from publishers.instagram import InstagramPublisher
from publishers.facebook import FacebookPublisher


class NewsPublisherManager:
    """
    Kamu haberleri ve Dezenformasyon Bültenlerini sosyal medyaya aktaran servis.
    """

    def __init__(self):
        self.telegram = TelegramPublisher()
        self.instagram = InstagramPublisher()
        self.facebook = FacebookPublisher()
        self.card_generator = NewsCardGenerator()

    @staticmethod
    def is_automation_enabled() -> bool:
        """Otomatik haber pilotunun aktif olup olmadığını kontrol eder."""
        val = get_system_setting("AUTO_PUBLISH_NEWS_ENABLED", "false")
        return str(val).strip().lower() in ["true", "1", "yes", "on", "aktif"]

    @staticmethod
    def enable_automation():
        """Otomatik haber pilotunu aktifleştirir."""
        set_system_setting("AUTO_PUBLISH_NEWS_ENABLED", "true", "Kamu haberleri otomatik pilot paylaşımı (true/false)")
        logger.info("✅ Kamu haberleri otomatik pilot paylaşımı AKTİFLEŞTİRİLDİ.")

    @staticmethod
    def disable_automation():
        """Otomatik haber pilotunu pasife alır."""
        set_system_setting("AUTO_PUBLISH_NEWS_ENABLED", "false", "Kamu haberleri otomatik pilot paylaşımı (true/false)")
        logger.info("⏸️ Kamu haberleri otomatik pilot paylaşımı PASİFE ALINDI (Standby).")

    def publish_pending_news(self, limit: int = 5, force: bool = False) -> Dict[str, Any]:
        """
        Paylaşılmayı bekleyen resmi kamu haberlerini yayınlar.
        Otomasyon kapalıysa ve force=False ise hiçbir işlem yapmaz.
        """
        if not self.is_automation_enabled() and not force:
            logger.info("ℹ️ Kamu haberleri otopilotu şu anda PASİF (standby) durumdadır. Paylaşım yapılmadı.")
            return {
                "status": "skipped",
                "reason": "automation_disabled",
                "message": "Otomasyon şu an pasif durumda. 'AUTO_PUBLISH_NEWS_ENABLED' true yapılınca aktifleşir."
            }

        target_channels_str = get_system_setting("AUTO_PUBLISH_NEWS_CHANNELS", "TELEGRAM,INSTAGRAM")
        channels = [c.strip().upper() for c in target_channels_str.split(",") if c.strip()]
        if not channels:
            channels = ["TELEGRAM"]

        published_count = 0
        errors = []

        with get_db() as db:
            pending_news = db.query(OfficialNews).filter(
                OfficialNews.is_social_published == False
            ).order_by(OfficialNews.publish_date.desc()).limit(limit).all()

            if not pending_news:
                logger.info("Paylaşılmayı bekleyen yeni resmi kamu haberi bulunmuyor.")
                return {"status": "ok", "published": 0, "message": "Yeni haber yok"}

            for news in pending_news:
                try:
                    logger.info(f"Haber #{news.id} hazırlanıyor: {news.title[:50]}...")

                    # 1. Editoryal Haber Kartı Üret
                    image_path = self.card_generator.generate(
                        news_id=news.id,
                        title=news.title,
                        institution=news.institution,
                        category=news.category or "RESMI_HABER",
                        summary=news.summary or "",
                        source_url=news.source_url or "https://kamupersonelrehberiniz.me",
                        publish_date=news.publish_date
                    )
                    news.image_card_path = image_path

                    post_text = news.social_post_text or f"🏛️ {news.institution}\n\n{news.title}\n\n{news.summary}\n\nDetaylar: {news.source_url}"
                    succ_channels = []

                    # 2. Telegram Gönderimi
                    if "TELEGRAM" in channels:
                        try:
                            # Markdown / HTML haber paylaşımı
                            tg_ok, tg_msg = self.telegram.publish(text=post_text, image_path=image_path)
                            if tg_ok:
                                succ_channels.append("TELEGRAM")
                            else:
                                errors.append(f"Telegram [Haber #{news.id}]: {tg_msg}")
                        except Exception as te:
                            errors.append(f"Telegram istisna [Haber #{news.id}]: {te}")

                    # 3. Instagram Gönderimi (Opsiyonel / Aktif Kanallarda)
                    if "INSTAGRAM" in channels:
                        try:
                            ig_ok, ig_msg = self.instagram.publish_news(news=news, image_path=image_path, text=post_text)
                            if ig_ok:
                                succ_channels.append("INSTAGRAM")
                            else:
                                errors.append(f"Instagram [Haber #{news.id}]: {ig_msg}")
                        except Exception as ie:
                            errors.append(f"Instagram istisna [Haber #{news.id}]: {ie}")

                    # 4. Durumu Güncelle
                    if succ_channels:
                        news.is_social_published = True
                        news.published_channels = ",".join(succ_channels)
                        published_count += 1
                        logger.info(f"✅ Haber #{news.id} başarıyla yayınlandı -> {succ_channels}")
                    else:
                        logger.warning(f"⚠️ Haber #{news.id} hiçbir kanala gönderilemedi.")

                except Exception as ex:
                    errors.append(f"Haber #{news.id} işleme hatası: {ex}")
                    logger.error(f"Haber yayınlama hatası: {ex}")

            db.commit()

        return {
            "status": "success" if published_count > 0 else "completed",
            "published": published_count,
            "errors": errors
        }


def toggle_news_autopilot(enable: bool) -> str:
    """Tek fonksiyonla haber otopilotunu açar veya kapatır."""
    if enable:
        NewsPublisherManager.enable_automation()
        return "Kamu haberleri otomatik pilotu AKTİF edildi. Yeni gelen resmi haberler otomatik paylaşılacak."
    else:
        NewsPublisherManager.disable_automation()
        return "Kamu haberleri otomatik pilotu PASİFE alındı (Standby). Paylaşım yapılmayacak."
