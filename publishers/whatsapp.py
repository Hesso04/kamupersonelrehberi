from typing import Tuple, Optional
import requests
from loguru import logger

from config.settings import settings
from core.models import JobAnnouncement
from .base import BasePublisher
from .whatsapp_web import WhatsAppWebPublisher


class WhatsAppPublisher(BasePublisher):
    """
    WhatsApp Kanalları (Channels) ve Dağıtım Yayıncısı.
    Öncelikli olarak yerel WhatsApp Web otomasyonunu (sıfır maliyet,
    Playwright persistent session, doğrudan kanala resim + metin) kullanır.
    İsteğe bağlı olarak Meta WhatsApp Cloud API ile de çalışabilir.
    """

    def __init__(self):
        super().__init__(platform_name="WhatsApp")
        self.web = WhatsAppWebPublisher()

    @property
    def token(self) -> Optional[str]:
        return settings.get_dynamic("WHATSAPP_ACCESS_TOKEN")

    @property
    def phone_number_id(self) -> Optional[str]:
        return settings.get_dynamic("WHATSAPP_PHONE_NUMBER_ID")

    def is_logged_in(self) -> bool:
        """WhatsApp Web oturumunun aktif olup olmadığını kontrol eder."""
        return self.web.is_logged_in()

    def start_login_window(self, max_wait: int = 100, on_qr_ready=None) -> Tuple[bool, str]:
        """Kullanıcının QR kod okutması için WhatsApp Web oturumunu açar/başlatır."""
        return self.web.start_login_window(max_wait=max_wait, on_qr_ready=on_qr_ready)

    def send_test_message(self) -> Tuple[bool, str]:
        """Kanala test mesajı gönderir."""
        return self.web.send_test_message()

    def logout(self) -> Tuple[bool, str]:
        """Yerel WhatsApp oturumunu kapatır."""
        return self.web.logout()

    def test_connection(self) -> Tuple[bool, str]:
        """WhatsApp kanal / oturum durumunu test eder."""
        if self.web.is_logged_in():
            channel_url = self.web.get_channel_url()
            return True, f"WhatsApp Web oturumu AKTİF ve bağlı! Hedef Kanal: {channel_url}"

        # Web oturumu yoksa Cloud API anahtarlarını kontrol et
        if self.token and self.phone_number_id:
            url = f"https://graph.facebook.com/v19.0/{self.phone_number_id}"
            headers = {"Authorization": f"Bearer {self.token}"}
            try:
                r = requests.get(url, headers=headers, timeout=10)
                if r.status_code == 200:
                    data = r.json()
                    display_name = data.get("verified_name") or data.get("display_phone_number") or "WhatsApp Cloud Hesabı"
                    return True, f"WhatsApp Cloud API Bağlantısı Başarılı: {display_name}"
                else:
                    return False, f"WhatsApp Cloud API Hatası (HTTP {r.status_code}): {r.text}"
            except Exception as e:
                return False, f"Bağlantı Hatası: {str(e)}"

        return False, "WhatsApp Web oturumu açılmamış. Lütfen 'Sistem & API Ayarları' bölümünden QR kod okutun."

    def publish(self, job: JobAnnouncement) -> Tuple[bool, str]:
        """
        Onaylanan ilanı WhatsApp kanalına yayınlar.
        Öncelikle WhatsApp Web otomasyonunu kullanır.
        """
        # 1. Yerel WhatsApp Web otomasyonu
        if self.web.is_logged_in():
            return self.web.publish_to_channel(job)

        # 2. Cloud API yedeği
        if self.token and self.phone_number_id:
            clean_url = job.source_url or "https://kamuilan.sbb.gov.tr/"
            if "ilanDetay.aspx" in clean_url:
                clean_url = "https://kamuilan.sbb.gov.tr/"

            text_content = (
                f"📢 *{job.institution or 'Kamu Alımı'}*\n"
                f"*{job.title}*\n\n"
                f"👥 *Kontenjan:* {job.total_positions or 1} Kişi\n"
                f"🎯 *KPSS Şartı:* {job.kpss_requirement or 'Resmi ilanda'}\n"
                f"🎓 *Mezuniyet:* {job.education_level or 'İlgili bölüm'}\n\n"
                f"🔗 *Resmi Portal:* {clean_url}\n\n"
                f"⚠️ _%100 Doğrulanmış Resmi Kaynaklıdır._\n"
                f"#KamuPersoneli #İlan"
            )

            url = f"https://graph.facebook.com/v19.0/{self.phone_number_id}/messages"
            headers = {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json"
            }
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "type": "text",
                "text": {"preview_url": True, "body": text_content}
            }

            try:
                r = requests.post(url, headers=headers, json=payload, timeout=15)
                if r.status_code in [200, 201]:
                    logger.info(f"WhatsApp Cloud mesajı başarıyla iletildi: ID {job.id}")
                    return True, "WhatsApp Cloud API üzerinden başarıyla yayınlandı."
                else:
                    return False, f"WhatsApp Hatası: {r.text}"
            except Exception as e:
                return False, f"Bağlantı Hatası: {str(e)}"

        return False, "WhatsApp Web oturumu açılmamış. Lütfen 'Sistem & API Ayarları' sekmesinden QR kodu taratın."
