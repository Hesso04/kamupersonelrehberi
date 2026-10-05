from typing import Tuple, Optional
from pathlib import Path
import requests
from loguru import logger

from config.settings import settings
from core.models import JobAnnouncement
from .base import BasePublisher


class FacebookPublisher(BasePublisher):
    """
    Facebook Sayfa Yayıncısı (Meta Graph API).
    Meta Graph API üzerinden onaylanan kamu ilanı kartlarını ve
    açıklama metinlerini resmi Facebook sayfasında otomatik paylaşır.
    """

    def __init__(self):
        super().__init__(platform_name="Facebook")

    @property
    def access_token(self) -> Optional[str]:
        return settings.get_dynamic("FACEBOOK_ACCESS_TOKEN") or settings.get_dynamic("INSTAGRAM_ACCESS_TOKEN")

    @property
    def page_id(self) -> Optional[str]:
        return settings.get_dynamic("FACEBOOK_PAGE_ID") or "1386232411235219"

    @property
    def is_configured(self) -> bool:
        return bool(self.access_token and self.page_id)

    def test_connection(self) -> Tuple[bool, str]:
        """Facebook Sayfası Graph API erişimini ve sayfa adını test eder."""
        if not self.access_token:
            return False, "Facebook Access Token tanımlı değil."
        if not self.page_id:
            return False, "Facebook Page ID tanımlı değil."

        url = f"https://graph.facebook.com/v19.0/{self.page_id}"
        params = {
            "fields": "id,name,link",
            "access_token": self.access_token
        }

        try:
            r = requests.get(url, params=params, timeout=10)
            if r.status_code == 200:
                data = r.json()
                page_name = data.get("name", "Bilinmeyen Sayfa")
                return True, f"Bağlantı Başarılı! Facebook Sayfası: {page_name}"
            else:
                err_data = {}
                try:
                    err_data = r.json().get("error", {})
                except Exception:
                    pass
                msg = err_data.get("message", r.text)
                code = err_data.get("code")
                if code == 190 or "expired" in msg.lower():
                    return False, f"Facebook Erişim Belirtecinizin süresi dolmuş. ({msg})"
                return False, f"Facebook Hatası (HTTP {r.status_code}): {msg}"
        except Exception as e:
            return False, f"Facebook Bağlantı Hatası: {str(e)}"

    def publish(self, job: JobAnnouncement) -> Tuple[bool, str]:
        """Kamu ilanını Facebook Sayfasında afişiyle birlikte yayınlar."""
        if not self.is_configured:
            return False, "Facebook erişim bilgileri (Sayfa ID veya Token) eksik."

        post_text = self._build_facebook_text(job)
        img_path = Path(job.image_path) if job.image_path else None

        # 1. Eğer afiş görseli varsa /{page_id}/photos ile doğrudan görsel olarak paylaş
        if img_path and img_path.exists():
            try:
                photo_url = f"https://graph.facebook.com/v19.0/{self.page_id}/photos"
                data = {
                    "caption": post_text,
                    "access_token": self.access_token
                }
                with open(img_path, "rb") as f_img:
                    files = {"source": f_img}
                    r = requests.post(photo_url, data=data, files=files, timeout=30)

                if r.status_code == 200:
                    res_data = r.json()
                    post_id = res_data.get("id") or res_data.get("post_id", "OK")
                    logger.info(f"Facebook sayfasında görselle paylaşıldı: Post ID {post_id}")
                    return True, f"Facebook'ta afişle paylaşıldı (Post ID: {post_id})"
                else:
                    err_data = {}
                    try:
                        err_data = r.json().get("error", {})
                    except Exception:
                        pass
                    err_msg = err_data.get("message", r.text)
                    logger.warning(f"Facebook görsel paylaşımı uyarısı: {err_msg} - Feed deneniyor...")
            except Exception as ex:
                logger.warning(f"Facebook fotoğraf yükleme istisnası: {ex}")

        # 2. Görsel yoksa veya fotoğraf yükleme başarısızsa /{page_id}/feed ile yayınla
        try:
            feed_url = f"https://graph.facebook.com/v19.0/{self.page_id}/feed"
            payload = {
                "message": post_text,
                "access_token": self.access_token
            }
            if job.source_url and "ilanDetay.aspx" not in job.source_url:
                payload["link"] = job.source_url

            r = requests.post(feed_url, data=payload, timeout=20)
            if r.status_code == 200:
                res_id = r.json().get("id", "OK")
                return True, f"Facebook'ta paylaşıldı (Post ID: {res_id})"
            else:
                err_data = {}
                try:
                    err_data = r.json().get("error", {})
                except Exception:
                    pass
                msg = err_data.get("message", r.text)
                if "pages_manage_posts" in msg:
                    return False, "Facebook Paylaşım İzni Eksik: Lütfen Graph API Explorer'da 'pages_manage_posts' iznini ekleyin."
                return False, f"Facebook Yayınlama Hatası: {msg}"
        except Exception as e:
            return False, f"Facebook API Hatası: {str(e)}"

    def _build_facebook_text(self, job: JobAnnouncement) -> str:
        from graphics.generator import to_turkish_date_str
        d_str = to_turkish_date_str(job.application_end_date)
        clean_url = job.source_url or "https://kamuilan.sbb.gov.tr/"
        if "ilanDetay.aspx" in clean_url:
            clean_url = "https://kamuilan.sbb.gov.tr/"

        text = (
            f"📢 {job.institution or 'Kamu Kurumu'} Personel Alım İlanı\n\n"
            f"🏛 Kurum: {job.institution or 'Kamu Kurumu'}\n"
            f"📋 Kadro / Pozisyon: {job.position or 'Kamu Personeli'}\n"
            f"👥 Kontenjan: {job.total_positions or 1} Kişi\n"
            f"🗓 Son Başvuru Tarihi: {d_str}\n"
            f"🎓 Öğrenim Şartı: {job.education_level or 'Kılavuzda belirtilen'}\n"
            f"🎯 KPSS Şartı: {job.kpss_requirement or 'Resmi ilanda belirtilen'}\n\n"
            f"🔗 Resmi Başvuru & Detaylar:\n{clean_url}\n\n"
            f"🇹🇷 T.C. Resmi Gazete ve SBB Kamu İlan Portalı teyitli kamu personel alımıdır.\n"
            f"#KamuPersoneli #MemurAlımı #Kamuİlanları #PersonelAlımı #İşİlanları"
        )
        return text
