"""
Kamu Personel Rehberi - AI Görsel Üretim Motoru (Pollinations Flux Integration)
=============================================================================
Haberin başlığına, kurumuna ve kategorisine göre konsept mimari ve tematik
AI arka planı üretir, önbelleğe alır ve NewsCardGenerator ile ModernCardGenerator'a besler.
"""
import os
import re
import urllib.parse
from pathlib import Path
from typing import Optional
import requests
from loguru import logger
from config.settings import settings

class AIGeneratorService:
    BASE_URL = "https://image.pollinations.ai/prompt"

    CATEGORY_PROMPTS = {
        "SOSYAL_HAK_TOKI": "Modern Turkish residential architecture, TOKI contemporary apartment buildings, clean blue sky, high quality architectural photography, photorealistic 8k, cinematic morning light",
        "ATAMA_KADRO": "Prestigious Turkish government ministry building, marble entrance, Turkish flag waving, students and applicants, professional editorial photography, sharp focus 8k",
        "OZLUK_MAAS": "Modern government finance and treasury district, corporate architecture, sleek glass facade, dramatic golden hour lighting, 8k ultra detailed",
        "MEVZUAT": "Supreme court of Turkey architecture, justice palace, elegant stone columns, dignified institutional atmosphere, ultra realistic photorealistic",
        "DEZENFORMASYON": "High-tech media verification center, digital cyber security control room, dark sleek interface, blue and red ambient glow, 8k cinematic",
        "RESMI_HABER": "Modern Turkish government administrative complex, sleek architectural photography, prestigious institutional design, cinematic daytime"
    }

    def __init__(self):
        self.cache_dir = Path("graphics/assets/backgrounds/ai_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.api_key = os.environ.get("POLLINATIONS_API_KEY", "sk_w8ZXyOFPOIDueTktlotzVGfA3pO9PZs1")

    def _build_prompt(self, title: str, institution: str, category: str) -> str:
        base_style = self.CATEGORY_PROMPTS.get(category, self.CATEGORY_PROMPTS["RESMI_HABER"])
        
        # Özel kurum ve anahtar kelime zenginleştirmesi
        t_low = title.lower()
        if "toki" in t_low or "konut" in t_low:
            spec = "modern residential community housing project in Turkey"
        elif "öğretmen" in t_low or "meb" in t_low or "eğitim" in t_low:
            spec = "modern Turkish academy campus, prestigious education building"
        elif "sağlık" in t_low or "hastane" in t_low or "doktor" in t_low:
            spec = "ultra modern state city hospital building exterior, modern medical complex"
        elif "polis" in t_low or "bekçi" in t_low or "emniyet" in t_low:
            spec = "modern police academy headquarters exterior, dignified security building"
        elif "yargı" in t_low or "katip" in t_low or "adalet" in t_low:
            spec = "Turkish palace of justice, grand legal palace exterior"
        else:
            clean_inst = re.sub(r"T\.C\.|\(.*\)", "", institution).strip()
            spec = f"modern institutional exterior of {clean_inst}"

        full_prompt = f"{spec}, {base_style}, no text, no watermark, professional architectural masterpiece, octane render, 8k resolution"
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
        Pollinations Flux üzerinden haber veya ilana özel 8K sinematik arka plan üretir.
        """
        safe_id = f"ai_bg_{category}_{news_id}_{width}x{height}.jpg"
        cached_file = self.cache_dir / safe_id
        if cached_file.exists() and cached_file.stat().st_size > 15000:
            return cached_file

        prompt = self._build_prompt(title, institution, category)
        encoded_prompt = urllib.parse.quote(prompt)

        url = (
            f"{self.BASE_URL}/{encoded_prompt}"
            f"?width={width}&height={height}&model=flux&nologo=true&seed={news_id + 100}"
        )

        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        logger.info(f"🎨 Pollinations AI Arka Plan Üretiliyor (Haber #{news_id})...")
        try:
            resp = requests.get(url, headers=headers, timeout=30)
            if resp.status_code == 200 and len(resp.content) > 10000:
                with open(cached_file, "wb") as f:
                    f.write(resp.content)
                logger.success(f"✓ AI Arka plan başarıyla kaydedildi: {cached_file.name} ({len(resp.content)//1024} KB)")
                return cached_file
            elif resp.status_code == 402:
                # Key kredisi sınırlıysa ücretsiz standart modelle devam et
                free_url = f"{self.BASE_URL}/{encoded_prompt}?width={width}&height={height}&nologo=true&seed={news_id + 100}"
                r_free = requests.get(free_url, timeout=30)
                if r_free.status_code == 200 and len(r_free.content) > 10000:
                    with open(cached_file, "wb") as f:
                        f.write(r_free.content)
                    logger.success(f"✓ AI Arka plan (Standart) başarıyla kaydedildi: {cached_file.name}")
                    return cached_file
            else:
                logger.warning(f"Pollinations yanıt kodu: {resp.status_code}, boyut: {len(resp.content)}")
        except Exception as e:
            logger.warning(f"Pollinations görsel üretim hatası: {e}")

        return None
