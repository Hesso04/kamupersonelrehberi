import json
import re
from typing import Dict, Any, Tuple
from loguru import logger

from config.settings import settings
from .prompts import SYSTEM_PROMPT


class GroqClient:
    """
    Groq Cloud LLM İstemcisi.
    Veritabanındaki dinamik ayarları kullanır.
    API anahtarı girilmemişse veya ağ hatası olursa akıllı yedekleme (fallback)
    sayesinde sistemin aksamasını önler.
    """

    def __init__(self):
        self._client = None

    def _get_client(self):
        """Her çağrıda veritabanındaki en güncel API anahtarını kullanır."""
        api_key = settings.active_groq_api_key
        if not api_key or api_key == "gsk_your_groq_api_key_here":
            return None

        try:
            from groq import Groq
            return Groq(api_key=api_key)
        except Exception as e:
            logger.error(f"Groq istemcisi başlatılamadı: {e}")
            return None

    def test_connection(self) -> Tuple[bool, str]:
        """Admin panelinden API anahtarı ve modelin geçerliliğini test eder."""
        client = self._get_client()
        if not client:
            return False, "Groq API anahtarı girilmemiş veya geçersiz."

        model = settings.active_groq_model
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "user", "content": "Merhaba, bağlantı testi. Sadece 'OK' yaz."}
                ],
                max_tokens=10,
                temperature=0.1
            )
            reply = response.choices[0].message.content.strip()
            return True, f"Bağlantı Başarılı! Model: {model} (Yanıt: {reply})"
        except Exception as e:
            return False, f"Bağlantı Hatası: {str(e)}"

    def analyze_announcement(
        self,
        title: str,
        raw_content: str,
        source_url: str
    ) -> Dict[str, Any]:
        """
        Ham ilan duyurusunu Groq LLM ile analiz eder ve yapısal JSON döner.
        """
        client = self._get_client()
        model = settings.active_groq_model

        if not client:
            logger.warning("Groq API anahtarı tanımlı değil. Akıllı yedek şablon kullanılıyor.")
            return self._heuristic_fallback(title, raw_content, source_url)

        user_content = f"""
İLAN BAŞLIĞI: {title}
HAM İLAN DETAYI:
{raw_content}
RESMİ KAYNAK LİNKİ: {source_url}
"""

        try:
            logger.info(f"Groq ({model}) ile ilan analiz ediliyor: {title[:60]}...")
            chat_completion = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_content}
                ],
                temperature=0.2,
                response_format={"type": "json_object"}
            )

            raw_reply = chat_completion.choices[0].message.content.strip()
            data = json.loads(raw_reply)
            return data

        except Exception as e:
            logger.error(f"Groq API çağrısında hata ({e}). Yedek şablona dönülüyor.")
            return self._heuristic_fallback(title, raw_content, source_url)

    def _heuristic_fallback(
        self,
        title: str,
        raw_content: str,
        source_url: str
    ) -> Dict[str, Any]:
        """
        API anahtarı olmadığı veya hata verdiği durumlarda kurumsal standartta
        yapısal veri ve paylaşım metni üreten kural tabanlı motor.
        """
        # Başlıktan kurum ve pozisyon tahmini
        parts = title.split(" - ")
        institution = parts[0].strip() if len(parts) > 1 else "Kamu Kurumu"
        position = parts[1].strip() if len(parts) > 1 else title

        # Sayı tahmini (Örn: "97 SÖZLEŞMELİ" -> 97)
        numbers = re.findall(r"\b(\d+)\b", title)
        total_positions = int(numbers[0]) if numbers else 1

        dates_match = re.search(r"(\d+\s+[A-Za-zÇŞĞÜÖİçşğüöı]+\s*-\s*\d+\s+[A-Za-zÇŞĞÜÖİçşğüöı]+)", raw_content or "")
        application_dates = dates_match.group(1) if dates_match else "İlan detayında belirtilmiştir"

        telegram_post = (
            f"📢 <b>{institution} Personel Alım İlanı</b>\n\n"
            f"🏛 <b>Kurum:</b> {institution}\n"
            f"📋 <b>Kadro / Pozisyon:</b> {position}\n"
            f"👥 <b>Kontenjan:</b> {total_positions} Kişi\n"
            f"🗓 <b>Başvuru Tarihleri:</b> {application_dates}\n\n"
            f"📌 <b>Başvuru ve Detaylar:</b>\n"
            f"• Başvurular resmi kurum portalı üzerinden kabul edilecektir.\n"
            f"• Detaylı başvuru kılavuzu ve şartlar için resmi bağlantıyı ziyaret ediniz.\n\n"
            f"🔗 <b>Resmi İlan Bağlantısı:</b>\n{source_url}\n\n"
            f"⚠️ <i>Bilgi kirliliğine karşı %100 resmi kaynaklıdır.</i>\n"
            f"#KamuPersoneli #İlan #{institution.replace(' ', '')[:20]}"
        )

        return {
            "institution": institution,
            "cleaned_title": title,
            "position": position,
            "total_positions": total_positions,
            "kpss_requirement": "Resmi ilanda belirtilen şartlar",
            "education_level": "İlgili bölüm mezuniyeti",
            "city": "İlanda belirtilmiştir",
            "application_dates": application_dates,
            "bullet_summary": [
                "Başvurular resmi kurum sistemi üzerinden yapılacaktır.",
                "Son başvuru tarihine kadar evrakların eksiksiz teslimi gereklidir."
            ],
            "telegram_post": telegram_post
        }
