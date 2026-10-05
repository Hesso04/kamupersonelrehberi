from typing import Tuple, Optional
import requests
from loguru import logger

from config.settings import settings
from core.models import JobAnnouncement
from .base import BasePublisher


class InstagramPublisher(BasePublisher):
    """
    Instagram Graph API Yayıncısı (Business / Creator Hesaplar).
    Meta Graph API üzerinden onaylanan kamu ilanı kartlarını ve
    açıklama metinlerini Instagram akışında otomatik paylaşır.
    """

    def __init__(self):
        super().__init__(platform_name="Instagram")

    @property
    def access_token(self) -> Optional[str]:
        return settings.get_dynamic("INSTAGRAM_ACCESS_TOKEN")

    @property
    def account_id(self) -> Optional[str]:
        return settings.get_dynamic("INSTAGRAM_ACCOUNT_ID")

    def test_connection(self) -> Tuple[bool, str]:
        """Instagram Graph API erişimini ve hesap adını test eder."""
        if not self.access_token:
            return False, "Instagram Access Token tanımlı değil."
        if not self.account_id:
            return False, "Instagram Business Account ID tanımlı değil."

        url = f"https://graph.facebook.com/v19.0/{self.account_id}"
        params = {
            "fields": "username,name",
            "access_token": self.access_token
        }

        try:
            r = requests.get(url, params=params, timeout=10)
            if r.status_code == 200:
                data = r.json()
                username = data.get("username", "Bilinmeyen")
                return True, f"Bağlantı Başarılı! Instagram Hesabı: @{username}"
            else:
                return False, f"Instagram Hatası (HTTP {r.status_code}): {r.text}"
        except Exception as e:
            return False, f"Instagram Bağlantı Hatası: {str(e)}"

    def _get_public_image_url(self, local_path: Optional[str]) -> Optional[str]:
        """
        Yerel görseli Meta Instagram API'sinin okuyabilmesi için genel bir HTTPS URL'ye dönüştürür.
        """
        if not local_path:
            return None
        
        from pathlib import Path
        p = Path(local_path)
        if not p.exists():
            return None

        # 1. Otomatik Hızlı Görsel Köprüsü (Sıfır Ayar - Meta'nın İndirebileceği Direkt HTTPS Linki)
        try:
            with open(p, "rb") as f:
                r_u = requests.post("https://uguu.se/upload?output=text", files={"files[]": f}, timeout=15)
                if r_u.status_code == 200:
                    direct_link = r_u.text.strip()
                    if direct_link.startswith("http"):
                        logger.info(f"Instagram için görsel köprüsü oluşturuldu: {direct_link}")
                        return direct_link
        except Exception as ue:
            logger.warning(f"Otomatik görsel köprüsü uyarısı: {ue}")

        # 2. IMGBB_API_KEY tanımlıysa ImgBB ile yükle
        imgbb_key = settings.get_dynamic("IMGBB_API_KEY")
        if imgbb_key:
            try:
                with open(p, "rb") as f:
                    r = requests.post("https://api.imgbb.com/1/upload", data={"key": imgbb_key}, files={"image": f}, timeout=20)
                    if r.status_code == 200:
                        img_url = r.json().get("data", {}).get("url")
                        if img_url:
                            return img_url
            except Exception as e:
                logger.warning(f"ImgBB yükleme uyarısı: {e}")

        # 3. Canlı sunucu ortamındaysa (HuggingFace / Render / VPS public URL)
        server_url = settings.get_dynamic("SERVER_PUBLIC_URL")
        if server_url:
            return f"{server_url.rstrip('/')}/static/{p.name}"

        return None

    def publish(self, job: JobAnnouncement) -> Tuple[bool, str]:
        """
        Görsel kartı ve açıklamayı Instagram hesabında akış gönderisi olarak yayınlar.
        Meta Content Publishing API: Container -> Publish iki aşamalı standardını kullanır.
        """
        if not self.access_token or not self.account_id:
            return False, "Instagram ayarları (Token / Account ID) eksik."

        image_url = self._get_public_image_url(job.image_path)
        if not image_url:
            return False, (
                "Instagram API'si görselin internete açık bir HTTPS bağlantısını gerektirir. "
                "Ayarlar menüsünden ücretsiz ImgBB API anahtarı ekleyebilir veya canlı sunucu URL'nizi girebilirsiniz."
            )

        caption = (
            f"🏛 {job.institution or 'Kamu Personel Alımı'}\n"
            f"📢 {job.title}\n\n"
            f"👥 Kontenjan: {job.total_positions or 1} Kişi\n"
            f"🎯 KPSS: {job.kpss_requirement or 'Detaylar resmi ilanda'}\n"
            f"🎓 Mezuniyet: {job.education_level or 'İlgili bölüm mezunu'}\n\n"
            f"📌 Başvuru ve tüm detaylar için görseldeki QR kodu okutabilir veya profilimizdeki Telegram linkine tıklayabilirsiniz.\n\n"
            f"⚠️ %100 Resmi Kaynaklıdır. Sıfır Bilgi Kirliliği.\n"
            f"#kamupersoneli #memuralımı #kpss #işilanları #{job.institution.replace(' ', '') if job.institution else 'kamu'}"
        )

        try:
            # 1. Aşama: Medya konteyneri oluştur (media container)
            container_url = f"https://graph.facebook.com/v19.0/{self.account_id}/media"
            container_payload = {
                "image_url": image_url,
                "caption": caption,
                "access_token": self.access_token
            }
            r_c = requests.post(container_url, data=container_payload, timeout=25)
            if r_c.status_code not in [200, 201]:
                logger.error(f"Instagram medya oluşturma hatası: {r_c.text}")
                return False, f"Instagram Medya Hatası (HTTP {r_c.status_code}): {r_c.text}"

            creation_id = r_c.json().get("id")
            if not creation_id:
                return False, f"Instagram creation_id alınamadı: {r_c.text}"

            # 2. Aşama: Meta'nın görseli işlemesini bekle (Asenkron İşleme - Max 25 sn)
            import time
            for attempt in range(12):
                time.sleep(2)
                try:
                    st_res = requests.get(
                        f"https://graph.facebook.com/v19.0/{creation_id}",
                        params={"fields": "status_code", "access_token": self.access_token},
                        timeout=10
                    ).json()
                    status_code = st_res.get("status_code")
                    if status_code == "FINISHED":
                        break
                    elif status_code == "ERROR":
                        return False, f"Instagram görsel işleme hatası: {st_res}"
                except Exception as se:
                    logger.debug(f"Status kontrol denemesi: {se}")

            # 3. Aşama: Gönderiyi Instagram akışında yayınla (media_publish)
            publish_url = f"https://graph.facebook.com/v19.0/{self.account_id}/media_publish"
            pub_payload = {
                "creation_id": creation_id,
                "access_token": self.access_token
            }
            r_p = requests.post(publish_url, data=pub_payload, timeout=25)
            if r_p.status_code in [200, 201]:
                post_id = r_p.json().get("id")
                logger.info(f"İlan başarıyla Instagram'da paylaşıldı: ID {job.id} (Post ID: {post_id})")
                return True, f"Instagram'da başarıyla yayınlandı! (Post ID: {post_id})"
            else:
                logger.error(f"Instagram yayınlama hatası: {r_p.text}")
                return False, f"Instagram Yayınlama Hatası: {r_p.text}"

        except Exception as e:
            logger.error(f"Instagram gönderim istisnası: {e}")
            return False, f"Instagram Gönderim Hatası: {str(e)}"
