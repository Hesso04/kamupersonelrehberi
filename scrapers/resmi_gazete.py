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
    alım ilanlarını (Çeşitli İlanlar -4.htm) tarar.
    """

    BASE_URL = "https://www.resmigazete.gov.tr"

    # Personel alımı belirteç kelimeleri
    RECRUITMENT_KEYWORDS = [
        "personel alım",
        "sözleşmeli personel",
        "öğretim üyesi",
        "öğretim elemanı",
        "araştırma görevlisi",
        "müfettiş yardımc",
        "uzman yardımc",
        "memur alım",
        "işçi alım",
        "sürekli işçi",
        "bilişim personeli",
        "hakim ve savcı",
        "asistan alım",
        "başkanlığından:",
        "rektörlüğünden:",
        "bakanlığından:",
        "genel müdürlüğünden:",
        "komutanlığından:",
        "müdürlüğünden:"
    ]

    def __init__(self):
        super().__init__(source_name="Resmi Gazete", timeout=25)
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
        })

    def fetch_jobs(self) -> List[ScrapedJob]:
        """Son 5 günün Resmi Gazete Çeşitli İlanlar (-4.htm) sayılarını tarar."""
        jobs: List[ScrapedJob] = []

        today = datetime.now()
        dates_to_check = [today - timedelta(days=i) for i in range(5)]

        for target_date in dates_to_check:
            date_str = target_date.strftime("%Y%m%d")
            year_str = target_date.strftime("%Y")
            month_str = target_date.strftime("%m")

            # Resmi Gazete Çeşitli İlanlar Bölümü URL'si
            # Örnek: https://www.resmigazete.gov.tr/ilanlar/eskiilanlar/2026/10/20261016-4.htm
            issue_url = f"{self.BASE_URL}/ilanlar/eskiilanlar/{year_str}/{month_str}/{date_str}-4.htm"

            try:
                response = self.session.get(issue_url, timeout=self.timeout, verify=False)
                if response.status_code != 200:
                    continue

                # Resmi Gazete sayfaları Windows-1254 (ISO-8859-9) ile kodlanmıştır
                response.encoding = "windows-1254"
                soup = BeautifulSoup(response.text, "html.parser")

                # İlan PDF veya detay bağlantılarını bul
                links = soup.find_all("a", href=True)
                for a in links:
                    text = a.get_text(separator=" ", strip=True)
                    text_clean = " ".join(text.split())
                    text_lower = text_clean.lower()

                    # İlan anahtar kelimelerinden birini içeriyor mu veya PDF mi?
                    href = a["href"].strip()
                    if not href.lower().endswith(".pdf") and not any(kw in text_lower for kw in self.RECRUITMENT_KEYWORDS):
                        continue

                    full_url = urljoin(issue_url, href)

                    # Kurum adını başlıktan akıllıca ayıkla
                    institution = "T.C. Resmi Kurumu"
                    m_inst = re.search(r"^(.+?(?:BAŞKANLIĞINDAN|REKTÖRLÜĞÜNDEN|BAKANLIĞINDAN|GENEL MÜDÜRLÜĞÜNDEN|KOMUTANLIĞINDAN|MÜDÜRLÜĞÜNDEN)):?", text_clean, re.IGNORECASE)
                    if m_inst:
                        institution = m_inst.group(1).rstrip(":").strip()
                    elif ":" in text_clean:
                        parts = text_clean.split(":", 1)
                        if len(parts[0]) < 80:
                            institution = parts[0].strip()

                    # Başlık metnini düzenle
                    clean_title = text_clean.rstrip(":")
                    if not clean_title or len(clean_title) < 5:
                        continue

                    # İlanın başvuru süresi Resmi Gazete'de genel kural olarak 15 gündür
                    app_end_date = target_date + timedelta(days=15)

                    raw_content = (
                        f"Resmi Gazete Yayım Tarihi: {target_date.strftime('%d.%m.%Y')}\n"
                        f"Kurum: {institution}\n"
                        f"İlan Metni: {clean_title}\n"
                        f"Resmi Belge Bağlantısı: {full_url}\n"
                        f"Resmi Gazete Sayısı: {date_str}-4"
                    )

                    job = ScrapedJob(
                        title=clean_title[:340],
                        source_name=self.source_name,
                        source_url=full_url,
                        institution=institution[:240],
                        position=clean_title[:290],
                        total_positions=1,
                        official_doc_url=full_url,
                        raw_content=raw_content,
                        publish_date=target_date,
                        application_end_date=app_end_date,
                        is_verified=True
                    )
                    jobs.append(job)

                if jobs:
                    logger.info(f"Resmi Gazete ({date_str}-4) sayısından {len(jobs)} adet resmi ilan başarıyla çekildi.")
                    break  # En güncel günü yakaladıysak döngüden çık

            except Exception as e:
                logger.warning(f"Resmi Gazete ({date_str}-4) taranamadı: {e}")
                continue

        return jobs
