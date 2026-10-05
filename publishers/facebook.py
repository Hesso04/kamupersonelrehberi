from typing import Tuple, Optional
from pathlib import Path
import requests
from loguru import logger

from config.settings import settings
from core.models import JobAnnouncement
from .base import BasePublisher
from .meta_helper import MetaHelper


class FacebookPublisher(BasePublisher):
    """
    Facebook Resmi Sayfa Yayıncısı (Meta Graph API).
    Meta Graph API üzerinden onaylanan veya otopilot kamu ilanı kartlarını ve
    açıklama metinlerini resmi Facebook sayfasında profesyonelce paylaşır.
    Akıllı Token Çözümleme: User Access Token girilse dahi otomatik olarak
    ilgili Facebook Sayfasının Page Access Token'ını türetir.
    """

    def __init__(self):
        super().__init__(platform_name="Facebook")
        self._cached_page_token: Optional[str] = None
        self._cached_page_id: Optional[str] = None

    @property
    def raw_token(self) -> Optional[str]:
        """Veritabanındaki Facebook veya ortak Instagram belirtecini döner."""
        return settings.get_dynamic("FACEBOOK_ACCESS_TOKEN") or settings.get_dynamic("INSTAGRAM_ACCESS_TOKEN")

    @property
    def page_id(self) -> Optional[str]:
        return settings.get_dynamic("FACEBOOK_PAGE_ID") or "1386232411235219"

    @property
    def is_configured(self) -> bool:
        return bool(self.raw_token and self.page_id)

    def get_effective_page_token(self) -> Tuple[Optional[str], Optional[str]]:
        """
        Sayfa paylaşımı için geçerli Page Access Token'ı çözümler.
        Eğer token zaten Page Token ise kendisini, User Token ise /page_id üzerinden
        Page Access Token'ı türetip döner.
        """
        if not self.raw_token or not self.page_id:
            return None, "Token veya Sayfa ID eksik."

        if self._cached_page_token and self._cached_page_id == self.page_id:
            return self._cached_page_token, None

        ok, page_tok, page_name_or_err = MetaHelper.resolve_page_access_token(self.raw_token, self.page_id)
        if ok and page_tok:
            self._cached_page_token = page_tok
            self._cached_page_id = self.page_id
            return page_tok, None

        # Çözümlenemezse raw token ile dene
        return self.raw_token, page_name_or_err

    def test_connection(self) -> Tuple[bool, str]:
        """Facebook Sayfası Graph API erişimini, sayfa adını ve belirteç durumunu test eder."""
        if not self.raw_token:
            return False, "Facebook Access Token tanımlı değil."
        if not self.page_id:
            return False, "Facebook Page ID tanımlı değil."

        # 1. Belirteç canlılık kontrolü
        diag = MetaHelper.diagnose_token(self.raw_token)
        if not diag["is_valid"]:
            return False, f"Facebook Erişim Belirteci Geçersiz: {diag['message']}"

        # 2. Sayfa erişimini test et
        page_token, resolve_err = self.get_effective_page_token()
        url = f"https://graph.facebook.com/v19.0/{self.page_id}"
        params = {
            "fields": "id,name,link,fan_count",
            "access_token": page_token or self.raw_token
        }

        try:
            r = requests.get(url, params=params, timeout=12)
            if r.status_code == 200:
                data = r.json()
                page_name = data.get("name", "Bilinmeyen Sayfa")
                link = data.get("link", f"https://facebook.com/{self.page_id}")
                return True, f"Bağlantı Başarılı! Facebook Sayfası: {page_name} (ID: {self.page_id})"
            else:
                err_data = {}
                try:
                    err_data = r.json().get("error", {})
                except Exception:
                    pass
                msg = err_data.get("message", r.text)
                code = err_data.get("code")
                if code == 190 or "expired" in msg.lower():
                    return False, f"Facebook Erişim Belirtecinizin süresi dolmuş. Meta panelinden yenileyiniz. ({msg})"
                return False, f"Facebook API Hatası (HTTP {r.status_code}): {msg}"
        except Exception as e:
            return False, f"Facebook Bağlantı Hatası: {str(e)}"

    def publish(self, job: JobAnnouncement) -> Tuple[bool, str]:
        """Kamu ilanını Facebook Sayfasında afişiyle birlikte yayınlar."""
        if not self.is_configured:
            return False, "Facebook erişim bilgileri (Sayfa ID veya Token) eksik."

        # Ön teşhis
        diag = MetaHelper.diagnose_token(self.raw_token)
        if not diag["is_valid"]:
            return False, diag["message"]

        effective_token, _ = self.get_effective_page_token()
        if not effective_token:
            effective_token = self.raw_token

        post_text = self._build_facebook_text(job)
        img_path = Path(job.image_path) if job.image_path else None

        # 1. Eğer afiş görseli varsa /{page_id}/photos ile doğrudan görsel olarak paylaş
        if img_path and img_path.exists():
            try:
                photo_url = f"https://graph.facebook.com/v19.0/{self.page_id}/photos"
                data = {
                    "caption": post_text,
                    "access_token": effective_token
                }
                with open(img_path, "rb") as f_img:
                    files = {"source": f_img}
                    r = requests.post(photo_url, data=data, files=files, timeout=35)

                if r.status_code == 200:
                    res_data = r.json()
                    post_id = res_data.get("id") or res_data.get("post_id", "OK")
                    logger.info(f"Facebook sayfasında görselle paylaşıldı: Post ID {post_id}")
                    return True, f"Facebook'ta afişle paylaşıldı! (Post ID: {post_id})"
                else:
                    err_data = {}
                    try:
                        err_data = r.json().get("error", {})
                    except Exception:
                        pass
                    err_msg = err_data.get("message", r.text)
                    logger.warning(f"Facebook yerel fotoğraf yükleme uyarısı: {err_msg} - CDN URL veya Feed deneniyor...")
            except Exception as ex:
                logger.warning(f"Facebook fotoğraf yükleme istisnası: {ex}")

            # 1.1 Alternatif: CDN linki üzerinden /{page_id}/photos (url parametresi ile)
            try:
                public_img_url, _ = MetaHelper.upload_image_multi_host(img_path)
                if public_img_url:
                    photo_url = f"https://graph.facebook.com/v19.0/{self.page_id}/photos"
                    r_cdn = requests.post(
                        photo_url,
                        data={
                            "url": public_img_url,
                            "caption": post_text,
                            "access_token": effective_token
                        },
                        timeout=30
                    )
                    if r_cdn.status_code == 200:
                        p_id = r_cdn.json().get("id") or r_cdn.json().get("post_id", "OK")
                        logger.info(f"Facebook sayfasında CDN URL ile paylaşıldı: Post ID {p_id}")
                        return True, f"Facebook'ta afişle paylaşıldı (CDN: {p_id})"
            except Exception as ce:
                logger.debug(f"Facebook CDN URL ile paylaşım hatası: {ce}")

        # 2. Görsel yoksa veya fotoğraf yükleme başarısızsa /{page_id}/feed ile yayınla
        try:
            feed_url = f"https://graph.facebook.com/v19.0/{self.page_id}/feed"
            payload = {
                "message": post_text,
                "access_token": effective_token
            }
            if job.source_url and "ilanDetay.aspx" not in job.source_url:
                payload["link"] = job.source_url

            r = requests.post(feed_url, data=payload, timeout=25)
            if r.status_code == 200:
                res_id = r.json().get("id", "OK")
                return True, f"Facebook'ta metin olarak paylaşıldı! (Post ID: {res_id})"
            else:
                err_data = {}
                try:
                    err_data = r.json().get("error", {})
                except Exception:
                    pass
                msg = err_data.get("message", r.text)
                if "pages_manage_posts" in msg:
                    return False, "Facebook Paylaşım İzni Eksik: Belirtecinizde 'pages_manage_posts' izni bulunmuyor. Lütfen Meta panelinden ekleyiniz."
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
            f"🔗 Resmi Başvuru & Şartname Detayları:\n{clean_url}\n\n"
            f"🇹🇷 T.C. Resmi Gazete ve SBB Kamu İlan Portalı teyitli kamu personel alımıdır. Sıfır bilgi kirliliği.\n\n"
            f"#KamuPersoneli #MemurAlımı #Kamuİlanları #PersonelAlımı #İşİlanları #KPSS"
        )
        return text
