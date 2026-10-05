from typing import Tuple, Optional
import base64
from pathlib import Path
import requests
from loguru import logger

from config.settings import settings
from core.models import JobAnnouncement
from .base import BasePublisher
from .whatsapp_web import WhatsAppWebPublisher


class WhatsAppPublisher(BasePublisher):
    """
    WhatsApp Kanalları (Channels) ve Dağıtım Yayıncısı.
    
    3 Farklı Modu Destekler:
    1. Yerel WhatsApp Web Otomasyonu (Playwright - Sıfır ek maliyet, ücretsiz)
    2. Whapi.cloud REST API Ağ Geçidi (Bulut Tabanlı, Sıfır Tarayıcı, %100 Kararlı)
    3. Green-API REST Gateway (Harici Bulut Oturumu)
    """

    def __init__(self):
        super().__init__(platform_name="WhatsApp")
        self.web = WhatsAppWebPublisher()

    @property
    def whapi_token(self) -> Optional[str]:
        return settings.get_dynamic("WHATSAPP_WHAPI_TOKEN")

    @property
    def green_api_id(self) -> Optional[str]:
        return settings.get_dynamic("GREEN_API_ID")

    @property
    def green_api_token(self) -> Optional[str]:
        return settings.get_dynamic("GREEN_API_TOKEN")

    @property
    def mode(self) -> str:
        if bool(self.whapi_token):
            return "whapi"
        elif bool(self.green_api_id and self.green_api_token):
            return "green_api"
        elif bool(self.token and self.phone_number_id and not str(self.phone_number_id).startswith("http")):
            return "cloud"
        else:
            return "web"

    @property
    def green_instance_id(self) -> Optional[str]:
        return self.green_api_id

    @property
    def token(self) -> Optional[str]:
        return settings.get_dynamic("WHATSAPP_ACCESS_TOKEN")

    @property
    def phone_number_id(self) -> Optional[str]:
        return settings.get_dynamic("WHATSAPP_PHONE_NUMBER_ID")

    @property
    def channel_url(self) -> str:
        return self.web.get_channel_url()

    def is_logged_in(self) -> bool:
        """Herhangi bir WhatsApp servisinin (Web, Whapi veya Green API) aktif olup olmadığını kontrol eder."""
        if bool(self.whapi_token):
            return True
        if bool(self.green_api_id and self.green_api_token):
            return True
        return self.web.is_logged_in()

    def start_login_window(self, max_wait: int = 100, on_qr_ready=None) -> Tuple[bool, str]:
        """Kullanıcının QR kod okutması için yerel WhatsApp Web oturumunu açar/başlatır."""
        return self.web.start_login_window(max_wait=max_wait, on_qr_ready=on_qr_ready)

    def logout(self) -> Tuple[bool, str]:
        """Yerel WhatsApp oturumunu kapatır."""
        return self.web.logout()

    def test_connection(self) -> Tuple[bool, str]:
        """WhatsApp kanal / oturum durumunu test eder."""
        # 1. Whapi REST API Ağ Geçidi Kontrolü
        if self.whapi_token:
            try:
                r = requests.get(
                    "https://gate.whapi.cloud/users/profile",
                    headers={"Authorization": f"Bearer {self.whapi_token}"},
                    timeout=10
                )
                if r.status_code == 200:
                    data = r.json()
                    name = data.get("name") or data.get("phone") or "Whapi Hesabı"
                    return True, f"Whapi.cloud REST API Bağlantısı Başarılı: {name}"
                else:
                    return False, f"Whapi Hatası (HTTP {r.status_code}): {r.text}"
            except Exception as e:
                return False, f"Whapi Bağlantı Hatası: {str(e)}"

        # 2. Green-API Ağ Geçidi Kontrolü
        if self.green_api_id and self.green_api_token:
            try:
                url = f"https://api.green-api.com/waInstance{self.green_api_id}/getStateInstance/{self.green_api_token}"
                r = requests.get(url, timeout=10)
                if r.status_code == 200:
                    state = r.json().get("stateInstance")
                    return True, f"Green-API Durumu: {state}"
                else:
                    return False, f"Green-API Hatası (HTTP {r.status_code}): {r.text}"
            except Exception as e:
                return False, f"Green-API Bağlantı Hatası: {str(e)}"

        # 3. Yerel WhatsApp Web Oturumu
        if self.web.is_logged_in():
            channel_url = self.web.get_channel_url()
            return True, f"WhatsApp Web oturumu AKTİF ve bağlı! Hedef Kanal: {channel_url}"

        return False, "WhatsApp Web oturumu açılmamış veya Gateway Token girilmemiş."

    def send_test_message(self) -> Tuple[bool, str]:
        """Kanala test mesajı gönderir (Web otomasyonu veya REST Gateway)."""
        test_text = (
            "✅ *Kamu Personel Rehberi - WhatsApp Kanal Entegrasyonu Testi*\n\n"
            "Bu mesaj, yapay zeka otomasyon sistemimiz tarafından başarıyla iletilmiştir.\n"
            "Resmi kamu personel alımları anlık olarak bu kanaldan paylaşılacaktır. 🏛️📢"
        )

        channel_code = self.web.get_channel_code()
        target_jid = f"{channel_code}@newsletter"

        # 1. Whapi REST API Ağ Geçidi
        if self.whapi_token:
            try:
                r = requests.post(
                    "https://gate.whapi.cloud/messages/text",
                    headers={"Authorization": f"Bearer {self.whapi_token}"},
                    json={"to": target_jid, "body": test_text},
                    timeout=15
                )
                if r.status_code in [200, 201]:
                    return True, "Whapi.cloud REST API üzerinden test mesajı başarıyla kanala gönderildi!"
                return False, f"Whapi Gönderim Hatası (HTTP {r.status_code}): {r.text}"
            except Exception as e:
                return False, f"Whapi Hatası: {str(e)}"

        # 2. Green-API Ağ Geçidi
        if self.green_api_id and self.green_api_token:
            try:
                url = f"https://api.green-api.com/waInstance{self.green_api_id}/sendMessage/{self.green_api_token}"
                r = requests.post(url, json={"chatId": target_jid, "message": test_text}, timeout=15)
                if r.status_code == 200:
                    return True, "Green-API üzerinden test mesajı başarıyla kanala gönderildi!"
                return False, f"Green-API Gönderim Hatası: {r.text}"
            except Exception as e:
                return False, f"Green-API Hatası: {str(e)}"

        # 3. Yerel WhatsApp Web Otomasyonu
        return self.web.send_test_message()

    def publish(self, job: JobAnnouncement) -> Tuple[bool, str]:
        """
        Onaylanan ilanı WhatsApp kanalına yayınlar.
        """
        channel_code = self.web.get_channel_code()
        target_jid = f"{channel_code}@newsletter"

        from graphics.generator import to_turkish_date_str
        deadline_str = to_turkish_date_str(job.application_end_date)
        clean_url = job.source_url or "https://kamuilan.sbb.gov.tr/"
        if "ilanDetay.aspx" in clean_url:
            clean_url = "https://kamuilan.sbb.gov.tr/"

        caption_text = (
            f"📢 *{job.institution or 'Kamu Alımı'}*\n"
            f"*{job.position or job.title}*\n\n"
            f"👥 *Kontenjan:* {job.total_positions or 1} Kişi\n"
            f"🗓 *Son Başvuru:* {deadline_str}\n"
            f"🎯 *KPSS Şartı:* {job.kpss_requirement or 'Resmi ilanda'}\n"
            f"🎓 *Mezuniyet:* {job.education_level or 'İlgili bölüm'}\n\n"
            f"🔗 *Resmi Başvuru / Kılavuz:* {clean_url}\n\n"
            f"⚠️ _%100 Doğrulanmış Resmi Kaynaklıdır._\n"
            f"#KamuPersoneli #İlan #KamuAlımı"
        )

        image_path = Path(job.image_path) if job.image_path else None

        # 1. Whapi REST API Ağ Geçidi
        if self.whapi_token:
            try:
                if image_path and image_path.exists():
                    with open(image_path, "rb") as f_img:
                        b64 = base64.b64encode(f_img.read()).decode("utf-8")
                    data_uri = f"data:image/png;base64,{b64}"
                    r = requests.post(
                        "https://gate.whapi.cloud/messages/image",
                        headers={"Authorization": f"Bearer {self.whapi_token}"},
                        json={"to": target_jid, "media": data_uri, "caption": caption_text},
                        timeout=25
                    )
                else:
                    r = requests.post(
                        "https://gate.whapi.cloud/messages/text",
                        headers={"Authorization": f"Bearer {self.whapi_token}"},
                        json={"to": target_jid, "body": caption_text},
                        timeout=15
                    )

                if r.status_code in [200, 201]:
                    logger.info(f"Whapi üzerinden WhatsApp kanalına ilan iletildi: ID {job.id}")
                    return True, "Whapi.cloud REST API üzerinden başarıyla yayınlandı!"
                return False, f"Whapi API Hatası (HTTP {r.status_code}): {r.text}"
            except Exception as e:
                return False, f"Whapi Yayınlama Hatası: {str(e)}"

        # 2. Green API Ağ Geçidi
        if self.green_api_id and self.green_api_token:
            try:
                if image_path and image_path.exists():
                    url_f = f"https://api.green-api.com/waInstance{self.green_api_id}/sendFileByUpload/{self.green_api_token}"
                    with open(image_path, "rb") as f_img:
                        files = {"file": f_img}
                        data = {"chatId": target_jid, "caption": caption_text}
                        r = requests.post(url_f, files=files, data=data, timeout=30)
                else:
                    url_t = f"https://api.green-api.com/waInstance{self.green_api_id}/sendMessage/{self.green_api_token}"
                    r = requests.post(url_t, json={"chatId": target_jid, "message": caption_text}, timeout=15)

                if r.status_code == 200:
                    return True, "Green-API üzerinden başarıyla yayınlandı!"
                return False, f"Green-API Hatası: {r.text}"
            except Exception as e:
                return False, f"Green-API Yayınlama Hatası: {str(e)}"

        # 3. Yerel WhatsApp Web Otomasyonu (Playwright)
        if self.web.is_logged_in():
            return self.web.publish_to_channel(job)

        return False, "WhatsApp Web oturumu açılmamış ve API Gateway anahtarı tanımlanmamış."
