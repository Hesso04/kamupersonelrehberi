import json
import re
import time
from typing import Dict, Any, Tuple, Optional
import requests
from loguru import logger

from config.settings import settings
from core.database import get_system_setting, set_system_setting
from .prompts import SYSTEM_PROMPT


class LLMClient:
    """
    Kamu Personel Rehberi - Çoklu Sağlayıcı Yapay Zeka Motoru (LLM Router).
    NVIDIA NIM, Groq Cloud ve Özel OpenAI-Uyumlu (DeepSeek, OpenRouter vb.)
    tüm API'leri tek merkezden yönetir, hız ölçümü ve canlı test imkanı sunar.
    """

    PROVIDERS = ["NVIDIA NIM", "Groq Cloud", "Özel / OpenAI Uyumlu"]

    def __init__(self):
        pass

    @property
    def active_provider(self) -> str:
        return get_system_setting("ACTIVE_AI_PROVIDER", "NVIDIA NIM")

    # =========================================================================
    # CANLI MODEL TEST METODU (Playground için)
    # =========================================================================

    def test_model_connection(
        self,
        provider: str,
        api_key: str,
        model: str,
        base_url: Optional[str] = None,
        custom_prompt: str = "Merhaba! Kamu Personel Rehberi test mesajı. Kendini ve hangi modeli kullandığını tek cümleyle Türkçe tanıt."
    ) -> Tuple[bool, str, float]:
        """
        Herhangi bir sağlayıcı ve model için canlı çağrı yapar.
        Dönüş: (Başarılı mı, Yanıt veya Hata Mesajı, Süre (saniye))
        """
        if not api_key or api_key.strip() == "":
            return False, "API Anahtarı girilmedi.", 0.0

        if not model or model.strip() == "":
            return False, "Model adı girilmedi.", 0.0

        start_time = time.perf_counter()

        try:
            # 1. NVIDIA NIM
            if provider == "NVIDIA NIM":
                target_url = "https://integrate.api.nvidia.com/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {api_key.strip()}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": model.strip(),
                    "messages": [{"role": "user", "content": custom_prompt}],
                    "temperature": 0.2,
                    "max_tokens": 150
                }
                response = requests.post(target_url, headers=headers, json=payload, timeout=20)

            # 2. Groq Cloud
            elif provider == "Groq Cloud":
                target_url = "https://api.groq.com/openai/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {api_key.strip()}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": model.strip(),
                    "messages": [{"role": "user", "content": custom_prompt}],
                    "temperature": 0.2,
                    "max_tokens": 150
                }
                response = requests.post(target_url, headers=headers, json=payload, timeout=20)

            # 3. Özel / OpenAI Uyumlu (DeepSeek, OpenRouter vb.)
            else:
                endpoint = (base_url or "https://api.deepseek.com/v1").rstrip("/")
                target_url = f"{endpoint}/chat/completions"
                headers = {
                    "Authorization": f"Bearer {api_key.strip()}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": model.strip(),
                    "messages": [{"role": "user", "content": custom_prompt}],
                    "temperature": 0.2,
                    "max_tokens": 150
                }
                response = requests.post(target_url, headers=headers, json=payload, timeout=20)

            elapsed = round(time.perf_counter() - start_time, 2)

            if response.status_code == 200:
                data = response.json()
                content = data["choices"][0]["message"]["content"].strip()
                return True, content, elapsed
            else:
                err_body = response.text
                return False, f"HTTP {response.status_code} Hatası: {err_body}", elapsed

        except requests.exceptions.Timeout:
            elapsed = round(time.perf_counter() - start_time, 2)
            return False, "İstek zaman aşımına uğradı (Timeout). Model çok yoğun olabilir.", elapsed
        except Exception as e:
            elapsed = round(time.perf_counter() - start_time, 2)
            return False, f"Bağlantı Hatası: {str(e)}", elapsed

    # =========================================================================
    # İLAN ANALİZİ VE JSON ÇIKARIMI (Uygulama İçi)
    # =========================================================================

    def analyze_announcement(
        self,
        title: str,
        raw_content: str,
        source_url: str
    ) -> Dict[str, Any]:
        """
        Aktif seçili yapay zeka sağlayıcısını kullanarak resmi ilanı analiz eder.
        Eğer aktif sağlayıcı hata verirse ikincil sağlayıcıyı dener.
        """
        provider = self.active_provider
        user_content = f"""
İLAN BAŞLIĞI: {title}
HAM İLAN DETAYI:
{raw_content}
RESMİ KAYNAK LİNKİ: {source_url}
"""

        # 1. Tercih Edilen Sağlayıcıyı Çalıştır
        result = self._dispatch_completion(provider, user_content)
        if result:
            return result

        # 2. Hata Durumunda Yedek Sağlayıcıyı Dene (Failover)
        alternate_providers = [p for p in self.PROVIDERS if p != provider]
        for alt in alternate_providers:
            logger.warning(f"{provider} başarısız oldu, alternatif deneniyor: {alt}")
            alt_res = self._dispatch_completion(alt, user_content)
            if alt_res:
                return alt_res

        # 3. Tüm API'ler başarısızsa kural tabanlı motor devreye girer
        logger.warning("Tüm yapay zeka API'leri erişilemez durumda. Heuristic motora dönülüyor.")
        return self._heuristic_fallback(title, raw_content, source_url)

    def _dispatch_completion(self, provider: str, user_content: str) -> Optional[Dict[str, Any]]:
        """Belirtilen sağlayıcıya JSON tamamlama isteği gönderir."""
        try:
            if provider == "NVIDIA NIM":
                key = get_system_setting("NVIDIA_API_KEY")
                model = get_system_setting("NVIDIA_MODEL", "meta/llama-3.2-11b-vision-instruct")
                if not key:
                    return None
                url = "https://integrate.api.nvidia.com/v1/chat/completions"
                headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
                payload = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_content}
                    ],
                    "temperature": 0.1,
                    "max_tokens": 800
                }
                r = requests.post(url, headers=headers, json=payload, timeout=25)
                if r.status_code == 200:
                    raw = r.json()["choices"][0]["message"]["content"]
                    return self._parse_json_reply(raw)

            elif provider == "Groq Cloud":
                key = get_system_setting("GROQ_API_KEY")
                model = get_system_setting("GROQ_MODEL", "llama-3.3-70b-versatile")
                if not key:
                    return None
                url = "https://api.groq.com/openai/v1/chat/completions"
                headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
                payload = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_content}
                    ],
                    "temperature": 0.1,
                    "response_format": {"type": "json_object"}
                }
                r = requests.post(url, headers=headers, json=payload, timeout=20)
                if r.status_code == 200:
                    raw = r.json()["choices"][0]["message"]["content"]
                    return self._parse_json_reply(raw)

            elif provider == "Özel / OpenAI Uyumlu":
                key = get_system_setting("CUSTOM_LLM_API_KEY")
                base_url = get_system_setting("CUSTOM_LLM_BASE_URL", "https://api.deepseek.com/v1").rstrip("/")
                model = get_system_setting("CUSTOM_LLM_MODEL", "deepseek-chat")
                if not key:
                    return None
                url = f"{base_url}/chat/completions"
                headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
                payload = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_content}
                    ],
                    "temperature": 0.1,
                    "max_tokens": 800
                }
                r = requests.post(url, headers=headers, json=payload, timeout=25)
                if r.status_code == 200:
                    raw = r.json()["choices"][0]["message"]["content"]
                    return self._parse_json_reply(raw)

        except Exception as e:
            logger.error(f"{provider} çağrı hatası: {e}")
        return None

    def _parse_json_reply(self, raw_reply: str) -> Optional[Dict[str, Any]]:
        """LLM çıktısından JSON objesini güvenli şekilde ayıklar."""
        try:
            return json.loads(raw_reply.strip())
        except Exception:
            # Markdown codefence temizliği (```json ... ```)
            match = re.search(r"\{.*\}", raw_reply, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except Exception:
                    pass
        return None

    def _heuristic_fallback(self, title: str, raw_content: str, source_url: str) -> Dict[str, Any]:
        """Kural tabanlı akıllı yedekleme."""
        parts = title.split(" - ")
        institution = parts[0].strip() if len(parts) > 1 else "Kamu Kurumu"
        position = parts[1].strip() if len(parts) > 1 else title

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
            f"📌 <b>Önemli Başvuru Şartları:</b>\n"
            f"• Başvurular resmi kamu kurumu portalı üzerinden alınacaktır.\n"
            f"• Adayların kılavuzdaki genel ve özel şartları taşıması gereklidir.\n\n"
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
