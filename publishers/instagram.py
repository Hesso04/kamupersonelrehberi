from typing import Tuple, Optional
from pathlib import Path
import time
import requests
from loguru import logger

from config.settings import settings
from core.models import JobAnnouncement
from .base import BasePublisher
from .meta_helper import MetaHelper


class InstagramPublisher(BasePublisher):
    """
    Instagram Graph API Profesyonel Yayıncısı (Business / Creator Hesaplar).
    Meta Content Publishing API üzerinden onaylanan veya otopilot kamu ilanlarını
    yüksek çözünürlüklü afişiyle birlikte Instagram akışında otomatik paylaşır.
    """

    def __init__(self):
        super().__init__(platform_name="Instagram")

    @property
    def access_token(self) -> Optional[str]:
        return settings.get_dynamic("INSTAGRAM_ACCESS_TOKEN")

    @property
    def account_id(self) -> Optional[str]:
        return settings.get_dynamic("INSTAGRAM_ACCOUNT_ID")

    @property
    def is_configured(self) -> bool:
        return bool(self.access_token and self.account_id)

    def test_connection(self) -> Tuple[bool, str]:
        """Instagram Graph API erişimini, hesap adını ve belirteç geçerliliğini test eder."""
        if not self.access_token:
            return False, "Instagram Access Token (Erişim Belirteci) tanımlı değil."
        if not self.account_id:
            return False, "Instagram Business Account ID tanımlı değil."

        # 1. Belirteç canlılık kontrolü
        diag = MetaHelper.diagnose_token(self.access_token)
        if not diag["is_valid"]:
            return False, diag["message"]

        # 2. Instagram İşletme Hesabı kontrolü
        url = f"https://graph.facebook.com/v19.0/{self.account_id}"
        params = {
            "fields": "username,name,profile_picture_url",
            "access_token": self.access_token
        }

        try:
            r = requests.get(url, params=params, timeout=12)
            if r.status_code == 200:
                data = r.json()
                username = data.get("username", "Bilinmeyen")
                name = data.get("name", "")
                name_str = f" ({name})" if name else ""
                return True, f"Bağlantı Başarılı! Instagram Hesabı: @{username}{name_str}"
            else:
                err_data = {}
                try:
                    err_data = r.json().get("error", {})
                except Exception:
                    pass
                msg = err_data.get("message", r.text)
                code = err_data.get("code")
                if code == 190 or "expired" in msg.lower():
                    return False, f"Instagram Erişim Belirtecinizin süresi dolmuş. Meta panelinden yenileyiniz. ({msg})"
                return False, f"Instagram API Hatası (HTTP {r.status_code}): {msg}"
        except Exception as e:
            return False, f"Instagram Bağlantı Hatası: {str(e)}"

    def _get_public_image_url(self, local_path: Optional[str]) -> Tuple[Optional[str], str]:
        """Yerel görseli çoklu CDN köprüsü ile Meta'nın erişebileceği HTTPS linkine dönüştürür."""
        if not local_path:
            return None, "Görsel yolu bulunamadı."
        p = Path(local_path)
        return MetaHelper.upload_image_multi_host(p)

    def publish(self, job: JobAnnouncement) -> Tuple[bool, str]:
        """
        Görsel kartı ve açıklamayı Instagram hesabında akış gönderisi olarak yayınlar.
        Meta Content Publishing API: Container -> Publish iki aşamalı standardını kullanır.
        """
        if not self.access_token or not self.account_id:
            return False, "Instagram ayarları (Token / Account ID) eksik."

        # Ön teşhis: Token süresi dolmuşsa gereksiz istek yapıp hata logunu şişirme
        diag = MetaHelper.diagnose_token(self.access_token)
        if not diag["is_valid"]:
            return False, diag["message"]

        image_url, provider_info = self._get_public_image_url(job.image_path)
        if not image_url:
            return False, (
                f"Instagram API'si görselin internete açık bir HTTPS bağlantısını gerektirir. "
                f"Görsel yüklenemedi: {provider_info}"
            )

        from graphics.generator import to_turkish_date_str
        d_str = to_turkish_date_str(job.application_end_date)
        clean_url = job.source_url or "https://kamuilan.sbb.gov.tr/"
        if "ilanDetay.aspx" in clean_url:
            clean_url = "https://kamuilan.sbb.gov.tr/"

        # Instagram için optimize edilmiş zengin metin
        inst_tag = job.institution.replace(" ", "").replace(".", "") if job.institution else "kamu"
        caption = (
            f"🏛 {job.institution or 'Kamu Personel Alımı'}\n"
            f"📢 {job.position or job.title}\n\n"
            f"👥 Kontenjan: {job.total_positions or 1} Kişi\n"
            f"🗓 Son Başvuru: {d_str}\n"
            f"🎯 KPSS Şartı: {job.kpss_requirement or 'Resmi ilanda belirtilen'}\n"
            f"🎓 Mezuniyet: {job.education_level or 'Kılavuzda belirtilen'}\n\n"
            f"📌 Başvuru ve tüm detaylar için görseldeki QR kodu okutabilir veya profilimizdeki Telegram bağlantısına tıklayabilirsiniz.\n\n"
            f"🇹🇷 T.C. Resmi Gazete ve SBB Kamu İlan Portalı teyitli kamu personel alımıdır. Sıfır bilgi kirliliği.\n\n"
            f"#KamuPersoneli #MemurAlımı #KPSS #PersonelAlımı #İşİlanları #{inst_tag}"
        )

        try:
            # 1. Aşama: Medya konteyneri oluştur (media container)
            container_url = f"https://graph.facebook.com/v19.0/{self.account_id}/media"
            container_payload = {
                "image_url": image_url,
                "caption": caption,
                "access_token": self.access_token
            }
            r_c = requests.post(container_url, data=container_payload, timeout=30)
            if r_c.status_code not in [200, 201]:
                err_text = r_c.text
                logger.error(f"Instagram medya konteyneri hatası: {err_text}")
                return False, f"Instagram Medya Hatası (HTTP {r_c.status_code}): {err_text}"

            creation_id = r_c.json().get("id")
            if not creation_id:
                return False, f"Instagram creation_id alınamadı: {r_c.text}"

            # 2. Aşama: Meta'nın görseli işlemesini bekle (Asenkron İşleme - Max 30 sn)
            for attempt in range(15):
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
                    logger.debug(f"Status kontrol denemesi ({attempt+1}): {se}")

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
