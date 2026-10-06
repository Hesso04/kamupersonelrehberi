import re
import os
import time
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime
import requests
from loguru import logger

from config.settings import settings


class MetaHelper:
    """
    Meta Graph API (Instagram Business & Facebook Pages) Entegrasyon Asistanı.
    - Token canlılık, geçerlilik ve son kullanma tarihi tespiti
    - User Token'dan otomatik Page Access Token çözümleme
    - Sayfaya bağlı Instagram Business hesaplarını otomatik keşfetme
    - 60 Günlük / Kalıcı Long-Lived Token dönüştürücü
    - Multi-Host Görsel Köprüsü (Instagram için kesintisiz CDN yükleme)
    """

    API_VERSION = "v19.0"
    BASE_URL = f"https://graph.facebook.com/{API_VERSION}"

    @classmethod
    def diagnose_token(cls, token: Optional[str]) -> Dict[str, Any]:
        """
        Herhangi bir Meta Access Token'ın durumunu, süresini ve geçerliliğini test eder.
        """
        if not token or not token.strip():
            return {
                "is_valid": False,
                "is_configured": False,
                "status_code": "EMPTY",
                "message": "Token tanımlanmamış.",
                "type": None,
                "expires_at": None,
                "scopes": []
            }

        token = token.strip()
        url = f"{cls.BASE_URL}/me"
        params = {"fields": "id,name", "access_token": token}

        try:
            r = requests.get(url, params=params, timeout=12)
            if r.status_code == 200:
                data = r.json()
                return {
                    "is_valid": True,
                    "is_configured": True,
                    "status_code": "ACTIVE",
                    "user_id": data.get("id"),
                    "name": data.get("name"),
                    "message": f"Token Aktif! Hesap: {data.get('name', 'Bilinmeyen')}",
                    "type": "USER"
                }
            else:
                err_data = {}
                try:
                    err_data = r.json().get("error", {})
                except Exception:
                    pass

                err_msg = err_data.get("message", r.text)
                err_code = err_data.get("code")
                err_subcode = err_data.get("error_subcode")

                is_expired = (
                    err_code == 190
                    or err_subcode == 463
                    or "expired" in err_msg.lower()
                    or "session has expired" in err_msg.lower()
                )

                # Süre bitiş tarihini mesajdan regex ile çek (Varsa: Monday, 05-Oct-26 09:00:00 PDT)
                exp_date_match = re.search(r"expired on ([^.]+)", err_msg, re.IGNORECASE)
                exp_str = exp_date_match.group(1).strip() if exp_date_match else None

                if is_expired:
                    msg = (
                        f"⚠️ Meta Erişim Belirtecinin (Access Token) süresi dolmuş! "
                        f"(Bitiş: {exp_str or 'Az önce'}). Meta for Developers panelinden yeni bir belirteç alınız."
                    )
                    return {
                        "is_valid": False,
                        "is_configured": True,
                        "status_code": "EXPIRED",
                        "error_code": err_code,
                        "error_subcode": err_subcode,
                        "message": msg,
                        "raw_error": err_msg,
                        "expired_on": exp_str
                    }
                else:
                    return {
                        "is_valid": False,
                        "is_configured": True,
                        "status_code": "ERROR",
                        "error_code": err_code,
                        "error_subcode": err_subcode,
                        "message": f"Meta API Hatası (Kod {err_code}): {err_msg}",
                        "raw_error": err_msg
                    }
        except Exception as e:
            return {
                "is_valid": False,
                "is_configured": True,
                "status_code": "NETWORK_ERROR",
                "message": f"Meta sunucularına bağlanılamadı: {str(e)}",
                "raw_error": str(e)
            }

    @classmethod
    def resolve_page_access_token(cls, token: str, page_id: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Kullanıcı belirtecinden Facebook Sayfası için kalıcı veya geçerli Page Access Token üretir/alır.
        Dönüş: (Başarılı mı, Page Token, Sayfa Adı veya Hata Mesajı)
        """
        if not token or not page_id:
            return False, None, "Token veya Sayfa ID eksik."

        # 1. Önce doğrudan sayfa ID'sinden page token iste
        url = f"{cls.BASE_URL}/{page_id}"
        params = {"fields": "access_token,name,link", "access_token": token}

        try:
            r = requests.get(url, params=params, timeout=12)
            if r.status_code == 200:
                data = r.json()
                page_token = data.get("access_token")
                page_name = data.get("name", "Facebook Sayfası")
                if page_token:
                    return True, page_token, page_name
                # Eğer access_token dönmediyse ama 200 döndüyse, mevcut token zaten bir Page Token olabilir!
                return True, token, page_name
        except Exception as e:
            logger.debug(f"Direct page token sorgu hatası: {e}")

        # 2. Alternatif: /me/accounts üzerinden sayfaları tara
        try:
            acc_url = f"{cls.BASE_URL}/me/accounts"
            r_acc = requests.get(acc_url, params={"access_token": token}, timeout=12)
            if r_acc.status_code == 200:
                pages = r_acc.json().get("data", [])
                for p in pages:
                    if str(p.get("id")) == str(page_id):
                        return True, p.get("access_token"), p.get("name")
                if pages:
                    # İlk sayfayı alternatif olarak sun
                    p0 = pages[0]
                    return True, p0.get("access_token"), f"{p0.get('name')} (ID: {p0.get('id')})"
        except Exception as ae:
            logger.debug(f"/me/accounts sorgu hatası: {ae}")

        return False, None, "Sayfa Erişim Belirteci alınamadı. 'pages_manage_posts' veya 'pages_read_engagement' izninin açık olduğundan emin olun."

    @classmethod
    def discover_connected_assets(cls, token: str) -> Dict[str, Any]:
        """
        Verilen belirtece bağlı tüm Facebook Sayfalarını ve Instagram Business hesaplarını otomatik bulur.
        Kullanıcının manuel ID arama zahmetini ortadan kaldırır!
        """
        result = {"pages": [], "instagram_accounts": [], "error": None}
        if not token:
            result["error"] = "Token boş."
            return result

        try:
            url = f"{cls.BASE_URL}/me/accounts"
            params = {
                "fields": "id,name,access_token,instagram_business_account{id,username,name,profile_picture_url}",
                "access_token": token
            }
            r = requests.get(url, params=params, timeout=15)
            if r.status_code == 200:
                data = r.json().get("data", [])
                for item in data:
                    page_info = {
                        "id": item.get("id"),
                        "name": item.get("name"),
                        "page_token": item.get("access_token"),
                    }
                    result["pages"].append(page_info)

                    ig_acc = item.get("instagram_business_account")
                    if ig_acc:
                        result["instagram_accounts"].append({
                            "id": ig_acc.get("id"),
                            "username": ig_acc.get("username"),
                            "name": ig_acc.get("name"),
                            "page_id": item.get("id"),
                            "page_name": item.get("name")
                        })
            else:
                result["error"] = r.text
        except Exception as e:
            result["error"] = str(e)

        return result

    @classmethod
    def exchange_to_long_lived_token(
        cls,
        short_token: str,
        app_id: str,
        app_secret: str
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Kısa ömürlü (1-2 saatlik) belirteci 60 günlük veya kalıcı Meta belirtecine dönüştürür.
        """
        if not short_token or not app_id or not app_secret:
            return False, "Kısa ömürlü Token, App ID ve App Secret alanları zorunludur.", None

        url = f"{cls.BASE_URL}/oauth/access_token"
        params = {
            "grant_type": "fb_exchange_token",
            "client_id": app_id.strip(),
            "client_secret": app_secret.strip(),
            "fb_exchange_token": short_token.strip()
        }

        try:
            r = requests.get(url, params=params, timeout=15)
            if r.status_code == 200:
                data = r.json()
                new_token = data.get("access_token")
                expires_in = data.get("expires_in", 5184000)  # ~60 gün
                days = int(expires_in) // 86400
                return True, f"Tebrikler! Belirteç başarıyla {days} günlük uzun ömürlü belirtece dönüştürüldü.", new_token
            else:
                err_msg = r.json().get("error", {}).get("message", r.text)
                return False, f"Dönüştürme Hatası: {err_msg}", None
        except Exception as e:
            return False, f"Bağlantı Hatası: {str(e)}", None

    @classmethod
    def upload_media_multi_host(cls, media_path: Path) -> Tuple[Optional[str], str]:
        """
        Instagram ve Facebook için yerel görsel veya MP4 videoyu çoklu sağlayıcı
        (Catbox -> Uguu -> ImgBB -> tmpfiles) zincirinden geçirerek Meta'nın anında
        indirebileceği direkt HTTPS URL'sine dönüştürür.
        """
        if not media_path or not media_path.exists():
            return None, "Medya dosyası yerel diskte bulunamadı."

        # Sağlayıcı 1: Catbox (Hızlı, Kalıcı, Meta Uyumlu - Hem Görsel Hem Video)
        try:
            with open(media_path, "rb") as f:
                r = requests.post(
                    "https://catbox.moe/user/api.php",
                    data={"reqtype": "fileupload"},
                    files={"fileToUpload": f},
                    timeout=25
                )
                if r.status_code == 200:
                    link = r.text.strip()
                    if link.startswith("http"):
                        logger.info(f"[Medya Köprüsü 1: Catbox] Başarılı: {link}")
                        return link, "Catbox CDN"
        except Exception as e:
            logger.warning(f"[Medya Köprüsü 1: Catbox] Başarısız: {e}")

        # Sağlayıcı 2: Uguu.se (Yedek Hızlı Host - Hem Görsel Hem Video)
        try:
            with open(media_path, "rb") as f:
                r_u = requests.post("https://uguu.se/upload?output=text", files={"files[]": f}, timeout=25)
                if r_u.status_code == 200:
                    link_u = r_u.text.strip()
                    if link_u.startswith("http"):
                        logger.info(f"[Medya Köprüsü 2: Uguu] Başarılı: {link_u}")
                        return link_u, "Uguu.se"
        except Exception as ue:
            logger.warning(f"[Medya Köprüsü 2: Uguu] Başarısız: {ue}")

        # Sağlayıcı 3: ImgBB (Sadece Görseller İçin ve API Anahtarı Tanımlıysa)
        if media_path.suffix.lower() in [".png", ".jpg", ".jpeg", ".webp"]:
            imgbb_key = settings.get_dynamic("IMGBB_API_KEY")
            if imgbb_key:
                try:
                    with open(media_path, "rb") as f:
                        r_i = requests.post(
                            "https://api.imgbb.com/1/upload",
                            data={"key": imgbb_key},
                            files={"image": f},
                            timeout=20
                        )
                        if r_i.status_code == 200:
                            link_i = r_i.json().get("data", {}).get("url")
                            if link_i:
                                logger.info(f"[Medya Köprüsü 3: ImgBB] Başarılı: {link_i}")
                                return link_i, "ImgBB Cloud"
                except Exception as ie:
                    logger.warning(f"[Medya Köprüsü 3: ImgBB] Başarısız: {ie}")

        # Sağlayıcı 4: Canlı Sunucu Genel URL'si (Varsa)
        server_url = settings.get_dynamic("SERVER_PUBLIC_URL")
        if server_url:
            public_link = f"{server_url.rstrip('/')}/static/{media_path.name}"
            return public_link, "Local Server"

        return None, "Hiçbir medya sağlayıcıya ulaşılamadı."

    @classmethod
    def upload_image_multi_host(cls, image_path: Path) -> Tuple[Optional[str], str]:
        """Görsel yükleyici (upload_media_multi_host için geriye dönük uyumluluk takma adı)."""
        return cls.upload_media_multi_host(image_path)

    @classmethod
    def save_post_job_mapping(cls, post_id: str, job_id: int):
        """Instagram gönderi ID'si ile veritabanındaki ilan ID'sini kalıcı olarak eşleştirir."""
        import json
        map_f = Path("data/ig_post_job_map.json")
        map_f.parent.mkdir(parents=True, exist_ok=True)
        current = {}
        if map_f.exists():
            try:
                with open(map_f, "r", encoding="utf-8") as f:
                    current = json.load(f)
            except Exception:
                current = {}
        current[str(post_id)] = int(job_id)
        try:
            with open(map_f, "w", encoding="utf-8") as f:
                json.dump(current, f, indent=2)
        except Exception:
            pass

