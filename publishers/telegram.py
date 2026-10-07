import json
import re
from pathlib import Path
from typing import Tuple, Optional
import requests
from loguru import logger

from config.settings import settings
from core.models import JobAnnouncement
from .base import BasePublisher


class TelegramPublisher(BasePublisher):
    """
    Telegram Bot API Yayıncısı.
    Doğrudan HTTP istekleri kullanarak Streamlit senkron iş parçacıklarında
    kararlı, hızlı ve asenkron çakışması olmadan çalışır.
    """

    def __init__(self):
        super().__init__(platform_name="Telegram")

    @property
    def token(self) -> Optional[str]:
        return settings.active_telegram_bot_token

    @property
    def channel_id(self) -> Optional[str]:
        return settings.active_telegram_channel_id

    @property
    def api_base(self) -> str:
        return f"https://api.telegram.org/bot{self.token}"

    def test_connection(self) -> Tuple[bool, str]:
        """Bot Token ve Kanal ID geçerliliğini test eder."""
        if not self.token or self.token == "your_telegram_bot_token_here":
            return False, "Telegram Bot Token tanımlı değil."

        if not self.channel_id:
            return False, "Telegram Kanal ID tanımlı değil."

        try:
            # 1. Bot kimlik kontrolü (getMe)
            r_me = requests.get(f"{self.api_base}/getMe", timeout=10)
            if r_me.status_code != 200:
                return False, f"Bot Token geçersiz! HTTP {r_me.status_code}: {r_me.text}"

            bot_data = r_me.json().get("result", {})
            bot_username = bot_data.get("username", "BilinmeyenBot")

            # 2. Kanal erişim kontrolü (getChat)
            r_chat = requests.get(
                f"{self.api_base}/getChat",
                params={"chat_id": self.channel_id},
                timeout=10
            )
            if r_chat.status_code != 200:
                return (
                    False,
                    f"@{bot_username} aktif fakat '{self.channel_id}' kanalına erişemedi. "
                    "Botu kanala YÖNETİCİ (Admin) olarak eklediğinizden emin olun."
                )

            chat_title = r_chat.json().get("result", {}).get("title", self.channel_id)
            return True, f"Bağlantı Başarılı! Bot: @{bot_username} ➔ Kanal: {chat_title}"

        except Exception as e:
            return False, f"Telegram bağlantı hatası: {str(e)}"

    def publish(self, job: JobAnnouncement) -> Tuple[bool, str]:
        """
        Onaylanan ilanı Telegram kanalına görseli, resmi bağlantı butonuyla ve
        varsa orijinal PDF kılavuzuyla birlikte gönderir.
        """
        if not self.token or not self.channel_id:
            return False, "Telegram Bot Token veya Kanal ID girilmemiş."

        pdf_file = Path(job.pdf_path) if job.pdf_path else None
        has_pdf = bool(pdf_file and pdf_file.exists())

        caption_text = job.social_post_text or job.title
        # Eski hatalı link kalıntılarını temizle
        caption_text = re.sub(r"https?://kamuilan\.sbb\.gov\.tr/ilanDetay\.aspx\S*", "", caption_text).strip()

        if has_pdf:
            # Kural: Alım PDF'i varsa link paylaşılmaz, doğrudan PDF eklenir
            if "Resmi" in caption_text or "Kılavuz" in caption_text or "Detay" in caption_text:
                caption_text = re.sub(
                    r"🔗\s*<b>[^<]*</b>:?\s*([^\n]+)?",
                    "📄 <b>Resmi Kılavuz & Başvuru:</b> Resmi alım şartnamesi ve başvuru tablosu (PDF) ekte sunulmuştur.",
                    caption_text
                )
            else:
                caption_text += "\n\n📄 <b>Resmi Kılavuz & Başvuru:</b> Resmi alım şartnamesi (PDF) ekte sunulmuştur."

        # Viral Kanal İmzası ve İletilme Çağrısı
        channel_handle = (self.channel_id or "kamupersonelrehberi").replace("@", "").strip()
        channel_link = f"https://t.me/{channel_handle}"
        clean_news_url = job.source_url or "https://kamuilan.sbb.gov.tr/"

        # İptal / Düzeltme Kontrolü
        title_upper = (job.title or "").upper()
        pos_upper = (job.position or "").upper()
        is_cancellation = any(
            w in title_upper or w in pos_upper
            for w in ["İPTAL", "IPTAL", "DÜZELTME", "DUZELTME", "İLAN İPTALİ"]
        )

        if is_cancellation:
            caption_text += (
                "\n\n📲 <i>Aday arkadaşlarına ilet, boşuna başvuru hazırlığı yapmasınlar!</i>\n"
                f"📌 <b>Resmi Gazete & SBB Teyitli İlanlar:</b> @{channel_handle}"
            )
        else:
            caption_text += (
                "\n\n📲 <i>İş arayan bir arkadaşına ilet, haberi olsun!</i>\n"
                f"📌 <b>Resmi Gazete & SBB Onaylı İlanlar:</b> @{channel_handle}"
            )

        # Güvenlik: Metin içindeki literal "None" kalıntılarını temizle
        caption_text = caption_text.replace("<b>Pozisyon:</b> None", f"<b>Pozisyon:</b> {job.position or 'Resmi Kılavuzda'}")
        caption_text = caption_text.replace("None Kişi", "1 Kişi").replace(": None", ": Belirtilmedi")

        # 2026 Viral İletme ve Hızlı Başvuru Butonları
        import urllib.parse
        if is_cancellation:
            share_summary = f"🚨 DİKKAT: {job.institution or 'Kamu'} {job.position or 'Personel Alımı'} İptal Edildi!\nDetaylar: {channel_link}"
            btn1_text = "📄 Resmi İptal Kararı"
            btn2_text = "📲 Adayları Bilgilendir"
        else:
            share_summary = f"📢 {job.institution or 'Kamu'} {job.position or 'Personel Alımı'}\nDetaylar & Başvuru İçin: {channel_link}"
            btn1_text = "🌐 Resmi Başvuru Ekranı"
            btn2_text = "📲 Arkadaşına İlet"

        share_btn_url = f"https://t.me/share/url?url={urllib.parse.quote(channel_link)}&text={urllib.parse.quote(share_summary)}"

        reply_markup = {
            "inline_keyboard": [
                [
                    {"text": btn1_text, "url": clean_news_url},
                    {"text": btn2_text, "url": share_btn_url}
                ],
                [
                    {"text": "📢 Kanalımıza Katıl & Takip Et", "url": channel_link}
                ]
            ]
        }

        try:
            image_file = Path(job.image_path) if job.image_path else None

            # 1. Görsel varsa Fotoğraf Olarak Gönder (sendPhoto)
            if image_file and image_file.exists():
                # Telegram sendPhoto caption limiti maksimum 1024 karakterdir
                safe_caption = caption_text
                if len(safe_caption) > 1020:
                    safe_caption = safe_caption[:1015] + "..."

                with open(image_file, "rb") as photo:
                    payload = {
                        "chat_id": self.channel_id,
                        "caption": safe_caption,
                        "parse_mode": "HTML"
                    }
                    # multipart form-data içinde Telegram JSON string bekler
                    if reply_markup:
                        payload["reply_markup"] = json.dumps(reply_markup)

                    files = {"photo": photo}
                    response = requests.post(
                        f"{self.api_base}/sendPhoto",
                        data=payload,
                        files=files,
                        timeout=25
                    )
            # 2. Görsel yoksa Düz Metin Olarak Gönder (sendMessage)
            else:
                payload = {
                    "chat_id": self.channel_id,
                    "text": caption_text,
                    "parse_mode": "HTML"
                }
                # requests.post json=payload kullandığında dict doğrudan JSON nesnesi olarak gider
                if reply_markup:
                    payload["reply_markup"] = reply_markup

                response = requests.post(
                    f"{self.api_base}/sendMessage",
                    json=payload,
                    timeout=15
                )

            if response.status_code == 200:
                logger.info(f"İlan Telegram kanalında paylaşıldı: ID {job.id}")

                # 3. Varsa Resmi PDF Kılavuzunu Kanala Doküman Olarak Gönder
                pdf_file = Path(job.pdf_path) if job.pdf_path else None
                if pdf_file and pdf_file.exists():
                    try:
                        with open(pdf_file, "rb") as doc:
                            requests.post(
                                f"{self.api_base}/sendDocument",
                                data={
                                    "chat_id": self.channel_id,
                                    "caption": f"📄 <b>{job.institution or 'Kamu İlanı'}</b>\nResmi İlan Kılavuzu & Başvuru Şartları (PDF)",
                                    "parse_mode": "HTML"
                                },
                                files={"document": doc},
                                timeout=30
                            )
                        logger.info(f"Resmi PDF kılavuzu Telegram kanalına yüklendi: ID {job.id}")
                    except Exception as pe:
                        logger.warning(f"Telegram PDF gönderme uyarısı: {pe}")

                return True, "İlan ve resmi kılavuz Telegram kanalında başarıyla yayınlandı."
            else:
                err_text = response.text
                logger.error(f"Telegram gönderim hatası (HTTP {response.status_code}): {err_text}")
                return False, f"Telegram Hatası: {err_text}"

        except Exception as e:
            logger.error(f"Telegram yayını istisna hatası: {e}")
            return False, f"Bağlantı Hatası: {str(e)}"
