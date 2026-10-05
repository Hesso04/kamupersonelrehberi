from typing import List
from datetime import datetime, timedelta
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from loguru import logger

from .base import BaseScraper, ScrapedJob


class ResmiGazeteScraper(BaseScraper):
    """
    T.C. Resmi Gazete - Çeşitli İlanlar (Kamu Personel Alımları) Kazıyıcısı.
    Resmi Gazete'de yayımlanan bakanlık, üniversite ve kamu kurumu
    alım ilanlarını tarar.
    """

    BASE_URL = "https://www.resmigazete.gov.tr"

    # Personel alımı belirteç kelimeleri
    RECRUITMENT_KEYWORDS = [
        "personel alım",
        "sözleşmeli personel",
        "öğretim üyesi",
        "öğretim elemanı",
        "müfettiş yardımc",
        "uzman yardımc",
        "memur alım",
        "işçi alım",
        "sürekli işçi",
        "bilişim personeli",
        "hakim ve savcı",
        "asistan alım"
    ]

    def __init__(self):
        super().__init__(source_name="Resmi Gazete", timeout=12)

    def fetch_jobs(self) -> List[ScrapedJob]:
        """Bugünkü veya dünkü Resmi Gazete ilanlarını tarar."""
        jobs: List[ScrapedJob] = []

        # Son 3 günün Resmi Gazete sayılarını dene
        today = datetime.now()
        dates_to_check = [today - timedelta(days=i) for i in range(3)]

        for target_date in dates_to_check:
            date_str = target_date.strftime("%Y%m%d")
            year_str = target_date.strftime("%Y")
            month_str = target_date.strftime("%m")
            # Örnek URL: https://www.resmigazete.gov.tr/eskiler/2026/10/20261002.htm
            issue_url = f"{self.BASE_URL}/eskiler/{year_str}/{month_str}/{date_str}.htm"

            try:
                response = self.session.get(issue_url, timeout=self.timeout)
                if response.status_code != 200:
                    continue

                response.encoding = "utf-8"
                soup = BeautifulSoup(response.text, "html.parser")

                # İlan bağlantılarını bul
                links = soup.find_all("a", href=True)
                for a in links:
                    text = a.get_text(strip=True)
                    text_lower = text.lower()

                    # İlan anahtar kelimelerinden birini içeriyor mu?
                    if any(kw in text_lower for kw in self.RECRUITMENT_KEYWORDS):
                        href = a["href"].strip()
                        full_url = urljoin(issue_url, href)

                        # Başlıktan kurum adını ayıklamaya çalış (Örn: "ANKARA ÜNİVERSİTESİ REKTÖRLÜĞÜNDEN: Sözleşmeli Personel...")
                        institution = "Resmi Gazete İlanı"
                        if "REKTÖRLÜĞÜNDEN" in text.upper() or "BAKANLIĞINDAN" in text.upper():
                            parts = re.split(r"REKTÖRLÜĞÜNDEN|BAKANLIĞINDAN|GENEL MÜDÜRLÜĞÜNDEN", text, flags=re.IGNORECASE)
                            if len(parts) > 0:
                                institution = parts[0].strip()

                        job = ScrapedJob(
                            title=text,
                            source_name=self.source_name,
                            source_url=full_url,
                            institution=institution,
                            official_doc_url=full_url,
                            raw_content=f"Resmi Gazete Tarihi: {target_date.strftime('%d.%m.%Y')}\nİlan: {text}\nBağlantı: {full_url}",
                            publish_date=target_date,
                            is_verified=True
                        )
                        jobs.append(job)

                if jobs:
                    logger.info(f"Resmi Gazete ({date_str}) sayısından {len(jobs)} adet ilan yakalandı.")
                    break  # En güncel günü yakaladıysak döngüden çık

            except Exception as e:
                logger.warning(f"Resmi Gazete ({date_str}) taranamadı: {e}")
                continue

        return jobs
