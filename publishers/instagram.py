from typing import Tuple, Optional, List, Dict, Any
from pathlib import Path
import time
import requests
from loguru import logger

from config.settings import settings
from core.database import get_system_setting
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
        return MetaHelper.upload_media_multi_host(p)

    def build_instagram_caption(self, job: JobAnnouncement) -> str:
        """
        Instagram algoritması, Keşfet (Explore) ve In-App SEO için optimize edilmiş,
        viral 'Yoruma KILAVUZ yaz' çağrısı ve etiketler içeren zengin metin üretir.
        """
        from graphics.generator import to_turkish_date_str
        d_str = to_turkish_date_str(job.application_end_date)
        inst_clean = job.institution or "Kamu Kurumu"
        inst_tag = inst_clean.replace(" ", "").replace(".", "").replace("-", "")

        caption = (
            f"👇 RESMİ BAŞVURU EKRANI & KILAVUZ İÇİN:\n"
            f"Bu gönderinin altına \"KILAVUZ\" yazın; resmi başvuru ekranı linki ve "
            f"kadro şartnamesi saniyeler içinde DM kutunuza GELSİN! 📩\n"
            f"(⚠️ Botun linki iletebilmesi için sayfamızı TAKİP ETMEYİ unutmayın)\n\n"
            f"🏛 {inst_clean.upper()} PERSONEL ALIMI\n"
            f"📢 {job.position or job.title}\n\n"
            f"👥 Kontenjan: {job.total_positions or 1} Kişi\n"
            f"🗓 Son Başvuru: {d_str}\n"
            f"🎯 KPSS Şartı: {job.kpss_requirement or 'Resmi ilanda belirtilen'}\n"
            f"🎓 Mezuniyet: {job.education_level or 'Kılavuzda belirtilen'}\n\n"
            f"📌 İlanı kaydetmeyi ve iş arayan arkadaşınıza göndermeyi unutmayın!\n"
            f"🇹🇷 T.C. Resmi Gazete ve SBB Kamu İlan Portalı teyitli kamu ilanıdır. Sıfır bilgi kirliliği.\n\n"
            f"#KamuPersoneli #MemurAlımı #KPSS #PersonelAlımı #İşİlanları #Kamuİlanları #KariyerKapısı #{inst_tag}"
        )
        return caption

    def _wait_for_media_processing(self, creation_id: str, max_attempts: int = 15) -> Tuple[bool, str]:
        """Meta'nın görsel veya videoyu işlemesini bekler (FINISHED kontrolü)."""
        for attempt in range(max_attempts):
            time.sleep(2)
            try:
                st_res = requests.get(
                    f"https://graph.facebook.com/v19.0/{creation_id}",
                    params={"fields": "status_code", "access_token": self.access_token},
                    timeout=10
                ).json()
                status_code = st_res.get("status_code")
                if status_code == "FINISHED":
                    return True, "İşlem tamamlandı."
                elif status_code == "ERROR":
                    return False, f"Meta medya işleme hatası: {st_res}"
            except Exception as se:
                logger.debug(f"Status kontrol denemesi ({attempt+1}): {se}")
        return True, "Zaman aşımı (devam ediliyor)."

    def publish_carousel(
        self,
        job: JobAnnouncement,
        image_paths: List[Path],
        custom_caption: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Meta Graph API ile 4:5 Dikey Çoklu Kaydırmalı Gönderi (Carousel) yayınlar.
        Her slaytı is_carousel_item olarak yükler, ardından ana CAROUSEL container'ı oluşturup yayınlar.
        """
        if not self.access_token or not self.account_id:
            return False, "Instagram ayarları (Token / Account ID) eksik."

        diag = MetaHelper.diagnose_token(self.access_token)
        if not diag["is_valid"]:
            return False, diag["message"]

        if not image_paths or len(image_paths) < 2:
            return False, "Carousel için en az 2 slayt görseli gereklidir."

        caption = custom_caption or self.build_instagram_caption(job)

        try:
            # 1. Her bir slaytı CDN'e yükle ve child container oluştur
            child_ids = []
            for idx, p in enumerate(image_paths):
                img_url, prov = MetaHelper.upload_media_multi_host(p)
                if not img_url:
                    return False, f"Slayt {idx+1} yüklenemedi: {prov}"

                container_url = f"https://graph.facebook.com/v19.0/{self.account_id}/media"
                payload = {
                    "image_url": img_url,
                    "is_carousel_item": "true",
                    "access_token": self.access_token
                }
                r = requests.post(container_url, data=payload, timeout=25)
                if r.status_code not in [200, 201]:
                    return False, f"Slayt {idx+1} konteyner hatası ({r.status_code}): {r.text}"
                cid = r.json().get("id")
                if not cid:
                    return False, f"Slayt {idx+1} container_id alınamadı."
                child_ids.append(cid)

            # 2. Ana CAROUSEL container'ı oluştur
            parent_url = f"https://graph.facebook.com/v19.0/{self.account_id}/media"
            parent_payload = {
                "media_type": "CAROUSEL",
                "children": ",".join(child_ids),
                "caption": caption,
                "access_token": self.access_token
            }
            r_p = requests.post(parent_url, data=parent_payload, timeout=30)
            if r_p.status_code not in [200, 201]:
                return False, f"Carousel ana konteyner hatası ({r_p.status_code}): {r_p.text}"

            creation_id = r_p.json().get("id")
            if not creation_id:
                return False, f"Carousel creation_id alınamadı: {r_p.text}"

            # 3. İşlenmesini bekle
            ok_proc, proc_msg = self._wait_for_media_processing(creation_id, max_attempts=15)
            if not ok_proc:
                return False, proc_msg

            # 4. Yayınla
            pub_url = f"https://graph.facebook.com/v19.0/{self.account_id}/media_publish"
            pub_res = requests.post(pub_url, data={"creation_id": creation_id, "access_token": self.access_token}, timeout=25)
            if pub_res.status_code in [200, 201]:
                post_id = pub_res.json().get("id")
                logger.info(f"Carousel başarıyla Instagram'da yayınlandı! (İlan #{job.id}, Post ID: {post_id})")
                return True, f"Instagram Carousel başarıyla yayınlandı! ({len(child_ids)} Slayt, Post ID: {post_id})"
            else:
                return False, f"Carousel yayınlama hatası: {pub_res.text}"

        except Exception as e:
            logger.error(f"Carousel yayınlama istisnası: {e}")
            return False, f"Carousel İstisnası: {str(e)}"

    def publish_reels(
        self,
        job: JobAnnouncement,
        video_path: Path,
        custom_caption: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Meta Graph API ile 9:16 Dikey Reels Videosu (MP4) yayınlar.
        media_type=REELS ve share_to_feed=true standardını kullanır.
        """
        if not self.access_token or not self.account_id:
            return False, "Instagram ayarları (Token / Account ID) eksik."

        video_url, prov = MetaHelper.upload_media_multi_host(video_path)
        if not video_url:
            return False, f"Reels videosu CDN'e yüklenemedi: {prov}"

        caption = custom_caption or self.build_instagram_caption(job)

        try:
            container_url = f"https://graph.facebook.com/v19.0/{self.account_id}/media"
            payload = {
                "media_type": "REELS",
                "video_url": video_url,
                "caption": caption,
                "share_to_feed": "true",
                "access_token": self.access_token
            }
            r = requests.post(container_url, data=payload, timeout=35)
            if r.status_code not in [200, 201]:
                return False, f"Reels konteyner hatası ({r.status_code}): {r.text}"

            creation_id = r.json().get("id")
            if not creation_id:
                return False, f"Reels creation_id alınamadı: {r.text}"

            # Video işleme süresi görsele göre biraz daha uzun olabilir (Max 45 sn)
            ok_proc, proc_msg = self._wait_for_media_processing(creation_id, max_attempts=20)
            if not ok_proc:
                return False, proc_msg

            pub_url = f"https://graph.facebook.com/v19.0/{self.account_id}/media_publish"
            pub_res = requests.post(pub_url, data={"creation_id": creation_id, "access_token": self.access_token}, timeout=25)
            if pub_res.status_code in [200, 201]:
                post_id = pub_res.json().get("id")
                logger.info(f"Reels videosu başarıyla Instagram'da yayınlandı! (İlan #{job.id}, Post ID: {post_id})")
                return True, f"Instagram Reels başarıyla yayınlandı! (Post ID: {post_id})"
            else:
                return False, f"Reels yayınlama hatası: {pub_res.text}"

        except Exception as e:
            logger.error(f"Reels yayınlama istisnası: {e}")
            return False, f"Reels İstisnası: {str(e)}"

    def publish_story(
        self,
        job: JobAnnouncement,
        story_image_path: Path
    ) -> Tuple[bool, str]:
        """
        Meta Graph API ile 9:16 Dikey Hikaye (Story) yayınlar.
        """
        if not self.access_token or not self.account_id:
            return False, "Instagram ayarları (Token / Account ID) eksik."

        image_url, prov = MetaHelper.upload_media_multi_host(story_image_path)
        if not image_url:
            return False, f"Story görseli yüklenemedi: {prov}"

        try:
            container_url = f"https://graph.facebook.com/v19.0/{self.account_id}/media"
            payload = {
                "media_type": "STORIES",
                "image_url": image_url,
                "access_token": self.access_token
            }
            r = requests.post(container_url, data=payload, timeout=25)
            if r.status_code not in [200, 201]:
                return False, f"Story konteyner hatası ({r.status_code}): {r.text}"

            creation_id = r.json().get("id")
            self._wait_for_media_processing(creation_id, max_attempts=10)

            pub_url = f"https://graph.facebook.com/v19.0/{self.account_id}/media_publish"
            pub_res = requests.post(pub_url, data={"creation_id": creation_id, "access_token": self.access_token}, timeout=25)
            if pub_res.status_code in [200, 201]:
                post_id = pub_res.json().get("id")
                logger.info(f"Story başarıyla Instagram'da yayınlandı! (İlan #{job.id}, ID: {post_id})")
                return True, f"Instagram Story başarıyla yayınlandı! (Post ID: {post_id})"
            else:
                return False, f"Story yayınlama hatası: {pub_res.text}"

        except Exception as e:
            return False, f"Story İstisnası: {str(e)}"

    def publish(self, job: JobAnnouncement) -> Tuple[bool, str]:
        """
        Instagram ana yayınlama metodu.
        ÖNCELİK 1: Çoklu Kaydırmalı Gönderi (Carousel - 4:5 Dikey) üretir ve yayınlar.
        ÖNCELİK 2: Herhangi bir aksaklıkta tekil görsel akış gönderisine sorunsuz düşer.
        """
        if not self.access_token or not self.account_id:
            return False, "Instagram ayarları (Token / Account ID) eksik."

        diag = MetaHelper.diagnose_token(self.access_token)
        if not diag["is_valid"]:
            return False, diag["message"]

        ig_format = get_system_setting("AUTOPILOT_IG_FORMAT", "SMART_HYBRID")
        from graphics.generator import JobCardGenerator, to_turkish_date_str
        card_gen = JobCardGenerator()
        deadline_str = to_turkish_date_str(job.application_end_date)

        # 1. Reels Denemesi (Büyük Alımlar [>=50 Kişi] veya ALWAYS_REELS modunda)
        is_large_job = bool(job.total_positions and job.total_positions >= 50)
        if (ig_format == "SMART_HYBRID" and is_large_job) or ig_format == "ALWAYS_REELS":
            try:
                from graphics.reels_engine import ReelsVideoEngine
                reels_eng = ReelsVideoEngine()
                ok_r, v_path, r_msg = reels_eng.create_reels_video(
                    job_id=job.id,
                    institution=job.institution or "Kamu Kurumu",
                    position=job.position or job.title,
                    total_positions=job.total_positions,
                    kpss_requirement=job.kpss_requirement,
                    education_level=job.education_level,
                    deadline=deadline_str,
                    source_url=job.source_url,
                    title=job.title or "",
                    duration_seconds=10
                )
                if ok_r and v_path:
                    succ_r, msg_r = self.publish_reels(job, v_path)
                    if succ_r:
                        return succ_r, f"Büyük alım ({job.total_positions} kişi) otomatik Reels videosu olarak yayınlandı! ({msg_r})"
                    logger.warning(f"Reels yayını başarısız oldu, Carousel deneniyor: {msg_r}")
            except Exception as re_err:
                logger.warning(f"Reels üretme istisnası: {re_err}")

        # 2. Carousel Denemesi (4:5 Dikey Çoklu Slayt)
        if ig_format in ["SMART_HYBRID", "ALWAYS_CAROUSEL", "ALWAYS_REELS"]:
            try:
                slides = card_gen.generate_carousel_cards(
                    job_id=job.id,
                    institution=job.institution or "Kamu Kurumu",
                    position=job.position or job.title,
                    total_positions=job.total_positions,
                    kpss_requirement=job.kpss_requirement,
                    education_level=job.education_level,
                    deadline=deadline_str,
                    source_url=job.source_url,
                    title=job.title or "",
                    city=job.city
                )
                if slides and len(slides) >= 2:
                    succ, msg = self.publish_carousel(job, slides)
                    if succ:
                        return succ, msg
                    logger.warning(f"Carousel gönderimi başarısız oldu, tekil görsele dönülüyor: {msg}")
            except Exception as ce:
                logger.warning(f"Carousel üretme adımı hatası: {ce}, tekil görsel deneniyor...")

        # 2. Fallback: Tekil Görsel Gönderimi
        image_url, provider_info = self._get_public_image_url(job.image_path)
        if not image_url:
            return False, f"Görsel yüklenemedi: {provider_info}"

        caption = self.build_instagram_caption(job)

        try:
            container_url = f"https://graph.facebook.com/v19.0/{self.account_id}/media"
            container_payload = {
                "image_url": image_url,
                "caption": caption,
                "access_token": self.access_token
            }
            r_c = requests.post(container_url, data=container_payload, timeout=30)
            if r_c.status_code not in [200, 201]:
                return False, f"Instagram Medya Hatası ({r_c.status_code}): {r_c.text}"

            creation_id = r_c.json().get("id")
            if not creation_id:
                return False, f"Instagram creation_id alınamadı: {r_c.text}"

            self._wait_for_media_processing(creation_id, max_attempts=15)

            publish_url = f"https://graph.facebook.com/v19.0/{self.account_id}/media_publish"
            r_p = requests.post(publish_url, data={"creation_id": creation_id, "access_token": self.access_token}, timeout=25)
            if r_p.status_code in [200, 201]:
                post_id = r_p.json().get("id")
                logger.info(f"İlan başarıyla Instagram'da paylaşıldı: ID {job.id} (Post ID: {post_id})")
                return True, f"Instagram'da başarıyla yayınlandı! (Post ID: {post_id})"
            else:
                return False, f"Instagram Yayınlama Hatası: {r_p.text}"

        except Exception as e:
            return False, f"Instagram Gönderim Hatası: {str(e)}"

