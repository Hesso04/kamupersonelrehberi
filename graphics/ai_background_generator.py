"""
Kamu Personel Rehberi - AI Görsel Üretim Motoru (Pollinations Flux Integration v2.0)
=====================================================================================
Stratejik Kurallar:
1. Haber ve İlan Verisine Duyarlı Sektörel Prompt Mimarisi:
   - Sağlık / Hastane / Tıp
   - Orman / Tarım / Doğa
   - Üniversite / Eğitim
   - Diğer tüm kamu kurumları
   - Kesin Negatif Filtre: 'no text, no words, no letters, no logos, no distorted human limbs, no icons'
2. Önbellekleme (Cache) & Kesintisiz Fallback mekanizması.
"""
import os
import re
import urllib.parse
from pathlib import Path
from typing import Optional
import requests
from loguru import logger


class AIGeneratorService:
    BASE_URL = "https://image.pollinations.ai/prompt"

    # Negatif prompt kuralları: Yapay zeka ASLA metin veya logo çizmemeli
    NEGATIVE_PROMPT = "no text, no words, no letters, no typography, no logos, no watermarks, no distorted human limbs, no icons, no badges, ultra realistic, professional editorial photography, sharp focus, 8k"

    def __init__(self):
        self.cache_dir = Path("graphics/assets/backgrounds/ai_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.api_key = os.environ.get("POLLINATIONS_API_KEY", "sk_w8ZXyOFPOIDueTktlotzVGfA3pO9PZs1")

    def _build_prompt(self, title: str, institution: str, category: str) -> str:
        """
        Kurum ve başlığı analiz ederek sektörel sinematik arka plan promptu oluşturur.
        """
        t_low = f"{title} {institution} {category}".lower()

        # 1. Sağlık / Hastane / Tıp
        if any(w in t_low for w in ["sağlık", "hastane", "tıp", "doktor", "hemşire", "tabip", "medikal", "acil"]):
            scene = "Modern medical clinic interior, professional healthcare atmosphere, clean surgical steel and soft blue lighting, shallow depth of field, realistic editorial photography"

        # 2. Orman / Tarım / Doğa / Çevre
        elif any(w in t_low for w in ["orman", "tarım", "doğa", "ağaç", "çevre", "milli park", "ogm", "fidan"]):
            scene = "Cinematic photography of a lush green Turkish forest with official forestry vehicles, morning mist, sharp volumetric godrays, realistic nature environment"

        # 3. Üniversite / Eğitim / MEB
        elif any(w in t_low for w in ["üniversite", "eğitim", "öğretmen", "kampüs", "fakülte", "meb", "rektörlük", "akademik"]):
            scene = "Grand modern university campus library architecture, elegant glass facade, sunny day, editorial university photography"

        # 4. Adalet / Yargı / Hukuk
        elif any(w in t_low for w in ["adalet", "mahkeme", "yargı", "katip", "mübaşir", "infaz", "cezaevi", "hukuk"]):
            scene = "Grand Turkish palace of justice exterior, magnificent classical marble columns, dignified institutional atmosphere, realistic legal architecture photography"

        # 5. Emniyet / Polis / Güvenlik
        elif any(w in t_low for w in ["polis", "emniyet", "bekçi", "güvenlik", "jandarma", "asayiş"]):
            scene = "Modern Turkish police headquarters exterior with official patrol vehicles parked, professional civic security atmosphere, clean daylight photography"

        # 6. TOKİ / Konut / Şehircilik
        elif any(w in t_low for w in ["toki", "konut", "kura", "sosyal konut", "şehircilik", "imar"]):
            scene = "Brand new modern Turkish residential apartment buildings complex, landscaped community garden, clean blue sky, architectural real estate photography"

        # 7. Diğer Tüm Kamu Kurumları (Genel Kurumsal / Bakanlık)
        else:
            scene = "Sophisticated modern glass government building headquarters exterior, professional real-estate and corporate news photography style, architectural focus, dramatic lighting"

        full_prompt = f"{scene}, {self.NEGATIVE_PROMPT}"
        return full_prompt

    def generate_background(
        self,
        news_id: int,
        title: str,
        institution: str,
        category: str,
        width: int = 1080,
        height: int = 1350
    ) -> Optional[Path]:
        """
        Pollinations üzerinden kuruma ve başlığa duyarlı arka plan üretir.
        """
        # Dosya adı güvenliği
        clean_cat = re.sub(r"[^\w]", "_", category)
        safe_id = f"ai_{clean_cat}_{news_id}_{width}x{height}.jpg"
        cached_file = self.cache_dir / safe_id
        if cached_file.exists() and cached_file.stat().st_size > 15000:
            return cached_file

        prompt = self._build_prompt(title, institution, category)
        encoded_prompt = urllib.parse.quote(prompt)

        # Pollinations Flux veya Standart Model
        url_with_key = f"{self.BASE_URL}/{encoded_prompt}?width={width}&height={height}&model=flux&nologo=true&seed={news_id + 50}"
        url_free = f"{self.BASE_URL}/{encoded_prompt}?width={width}&height={height}&nologo=true&seed={news_id + 50}"

        logger.info(f"🎨 Sektörel AI Arka Plan Üretiliyor (Haber #{news_id} - {institution[:30]})...")

        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        # 1. Öncelikli olarak API anahtarıyla dene
        try:
            resp = requests.get(url_with_key, headers=headers, timeout=25)
            if resp.status_code == 200 and len(resp.content) > 10000:
                with open(cached_file, "wb") as f:
                    f.write(resp.content)
                logger.success(f"✓ AI Arka plan başarıyla kaydedildi: {cached_file.name} ({len(resp.content)//1024} KB)")
                return cached_file
        except Exception as e:
            logger.debug(f"Anahtarlı Pollinations isteği: {e}")

        # 2. Ücretsiz standart endpoint fallback
        try:
            resp = requests.get(url_free, timeout=25)
            if resp.status_code == 200 and len(resp.content) > 10000:
                with open(cached_file, "wb") as f:
                    f.write(resp.content)
                logger.success(f"✓ AI Arka plan (Standart) başarıyla kaydedildi: {cached_file.name} ({len(resp.content)//1024} KB)")
                return cached_file
        except Exception as e:
            logger.warning(f"Pollinations ücretsiz endpoint hatası: {e}")

        return None
