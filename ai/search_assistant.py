from typing import List, Dict, Any, Optional
from loguru import logger
import requests

from core.database import get_db, get_system_setting
from core.models import JobAnnouncement
from .llm_client import LLMClient


class AISearchAssistant:
    """
    SBB Kamu İlan ve Resmi Gazete doğrulanmış ilan havuzunu
    doğal dil ile sorgulayan ve adaylara %100 resmi kaynaklı rehberlik sunan
    Yapay Zeka İlan Danışmanı.
    """

    def __init__(self):
        self.llm_client = LLMClient()

    def search_and_answer(self, user_query: str) -> Dict[str, Any]:
        """
        Kullanıcının doğal dil sorusunu veritabanındaki 170+ resmi ilanla eşleştirir
        ve AI destekli yanıt üretir.
        """
        if not user_query or user_query.strip() == "":
            return {
                "answer": "Lütfen aramak istediğiniz pozisyon, kurum veya şartı belirtiniz.",
                "matched_jobs": []
            }

        # 1. Veritabanından anahtar kelime ve metin bazlı ön filtreleme yap
        keywords = [k.strip() for k in user_query.split() if len(k) > 2]
        
        with get_db() as db:
            query = db.query(JobAnnouncement)
            # İptal olmayan ve doğrulanmış ilanlar
            query = query.filter(JobAnnouncement.is_verified == True)

            all_jobs = query.order_by(JobAnnouncement.id.desc()).all()

            # Eşleşenleri puanla
            scored_jobs = []
            for job in all_jobs:
                score = 0
                job_text = f"{job.title} {job.institution} {job.position} {job.raw_content}".lower()
                for kw in keywords:
                    if kw.lower() in job_text:
                        score += 1
                if score > 0:
                    scored_jobs.append((score, job))

            # Puan sırasına göre en ilgili ilk 15 ilanı seç
            scored_jobs.sort(key=lambda x: x[0], reverse=True)
            relevant_jobs = [j[1] for j in scored_jobs[:15]]

            # Eğer anahtar kelime eşleşmediyse en güncel 10 ilanı bağlama ver
            if not relevant_jobs:
                relevant_jobs = all_jobs[:10]

        # 2. İlan bağlamını (Context) oluştur
        context_lines = []
        for j in relevant_jobs:
            clean_link = j.source_url or "https://kamuilan.sbb.gov.tr/"
            if "ilanDetay.aspx" in clean_link:
                clean_link = "https://kamuilan.sbb.gov.tr/"
            context_lines.append(
                f"- ID: {j.id} | Kurum: {j.institution} | Pozisyon: {j.position or j.title} | "
                f"Kontenjan: {j.total_positions or 1} | KPSS: {j.kpss_requirement or 'Resmi ilanda'} | "
                f"Tarih: {j.raw_content or ''} | Resmi Portal: {clean_link}"
            )
        context_str = "\n".join(context_lines)

        # 3. LLM'e Prompt Gönder
        prompt = f"""
Sen "Kamu Personel Rehberi" projesinin Resmi İlan Arama ve Danışmanlık Yapay Zekasısın.
Aşağıda T.C. Strateji ve Bütçe Başkanlığı (kamuilan.sbb.gov.tr) ve Resmi Gazete'den çekilmiş %100 DOĞRULANMIŞ güncel resmi kamu ilanları yer almaktadır:

GÜNCEL RESMİ İLAN HAVUZU:
{context_str}

KULLANICININ ARAMA / SORUSU:
"{user_query}"

TALİMATLAR:
1. SADECE yukarıdaki resmi ilan havuzunda bulunan gerçek bilgilere dayanarak yanıt ver.
2. Kullanıcının sorusuyla eşleşen kurumları, kadroları, kontenjan sayılarını ve resmi bağlantıları maddeler halinde net ve şeffafça belirt.
3. Asla tık tuzağı veya uydurma bilgi kullanma.
4. Linklerde doğrudan 404 veren adresleri (ilanDetay.aspx vb.) asla kullanma; resmi portalı (https://kamuilan.sbb.gov.tr/ veya Resmi Gazete) belirt. Adaylara ilan kılavuzlarının PDF olarak sistemde/Telegram kanalında yer aldığını hatırlat.
"""

        # Aktif LLM üzerinden yanıt al
        provider = self.llm_client.active_provider
        try:
            ok, reply, elapsed = self.llm_client.test_model_connection(
                provider=provider,
                api_key=self._get_active_key(provider),
                model=self._get_active_model(provider),
                base_url=self._get_active_url(provider),
                custom_prompt=prompt
            )
            if ok:
                ai_answer = reply
            else:
                ai_answer = self._format_fallback_search(relevant_jobs, user_query)
        except Exception as e:
            logger.error(f"AI arama hatası: {e}")
            ai_answer = self._format_fallback_search(relevant_jobs, user_query)

        return {
            "answer": ai_answer,
            "matched_jobs": relevant_jobs
        }

    def _get_active_key(self, provider: str) -> str:
        if provider == "NVIDIA NIM":
            return get_system_setting("NVIDIA_API_KEY", "")
        elif provider == "Groq Cloud":
            return get_system_setting("GROQ_API_KEY", "")
        return get_system_setting("CUSTOM_LLM_API_KEY", "")

    def _get_active_model(self, provider: str) -> str:
        if provider == "NVIDIA NIM":
            return get_system_setting("NVIDIA_MODEL", "meta/llama-3.2-11b-vision-instruct")
        elif provider == "Groq Cloud":
            return get_system_setting("GROQ_MODEL", "llama-3.3-70b-versatile")
        return get_system_setting("CUSTOM_LLM_MODEL", "deepseek-chat")

    def _get_active_url(self, provider: str) -> Optional[str]:
        if provider == "Özel / OpenAI Uyumlu":
            return get_system_setting("CUSTOM_LLM_BASE_URL", "https://api.deepseek.com/v1")
        return None

    def _format_fallback_search(self, jobs: List[JobAnnouncement], query: str) -> str:
        lines = [f"**'{query}' ile ilgili tespit edilen resmi kamu alımları:**\n"]
        for j in jobs[:6]:
            clean_link = j.source_url or "https://kamuilan.sbb.gov.tr/"
            if "ilanDetay.aspx" in clean_link:
                clean_link = "https://kamuilan.sbb.gov.tr/"
            lines.append(f"• **{j.institution}**: {j.title} (Kontenjan: {j.total_positions or 1}) - [Resmi Portal]({clean_link})")
        return "\n".join(lines)
