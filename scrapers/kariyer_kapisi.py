from typing import List
from datetime import datetime
from email.utils import parsedate_to_datetime
from bs4 import BeautifulSoup
import requests
from loguru import logger

from .base import BaseScraper, ScrapedJob


class KariyerKapisiScraper(BaseScraper):
    """
    Cumhurbaşkanlığı İnsan Kaynakları Ofisi - Kariyer Kapısı
    Kamu İşe Alım İlanları Kazıyıcısı.
    
    Yalnızca resmi ve doğrulanmış kamu ilanlarını çeker.
    Takipçilere kurumsal 'T.C. Resmi Kurum Duyurusu' kimliği ile sunulur.
    """

    RSS_ENDPOINT = "https://kariyerkapisi.gov.tr/RSS/RssLinkiAl.t3kh3062ko.js"

    def __init__(self):
        super().__init__(source_name="T.C. Resmi Kurum Duyurusu", timeout=15)

    def fetch_jobs(self) -> List[ScrapedJob]:
        jobs: List[ScrapedJob] = []

        try:
            r = self.session.get(self.RSS_ENDPOINT, timeout=self.timeout, verify=False)
            if r.status_code != 200:
                logger.warning(f"Kariyer Kapısı yanıt kodu ({r.status_code})")
                return jobs

            soup = BeautifulSoup(r.content, "xml")
            items = soup.find_all("item")
            logger.info(f"Kariyer Kapısı üzerinden {len(items)} adet resmi kamu ilanı çekildi.")

            for it in items:
                raw_title = it.find("title").text.strip() if it.find("title") else ""
                link = it.find("link").text.strip() if it.find("link") else ""
                desc = it.find("description").text.strip() if it.find("description") else ""
                pub_date_str = it.find("pubDate").text.strip() if it.find("pubDate") else ""

                if not raw_title or not link:
                    continue

                # Kurum ve pozisyon ayrıştırma (genellikle "KURUM ADI - KADRO DETAYI" şeklinde)
                institution = "T.C. Kamu Kurumu"
                position = raw_title
                if " - " in raw_title:
                    parts = raw_title.split(" - ", 1)
                    institution = parts[0].strip()
                    position = parts[1].strip()

                pub_date = None
                if pub_date_str:
                    try:
                        pub_date = parsedate_to_datetime(pub_date_str)
                    except Exception:
                        pass

                raw_content = (
                    f"Kurum: {institution}\n"
                    f"Başlık: {raw_title}\n"
                    f"Açıklama: {desc}\n"
                    f"Resmi Bağlantı: {link}\n"
                    f"Kategori: Kamu İşe Alım (Kariyer Kapısı)"
                )

                job = ScrapedJob(
                    title=raw_title,
                    source_name=self.source_name,
                    source_url=link,
                    institution=institution,
                    position=position,
                    total_positions=1,
                    official_doc_url=link,
                    raw_content=raw_content,
                    publish_date=pub_date or datetime.utcnow(),
                    is_verified=True
                )
                jobs.append(job)

        except Exception as e:
            logger.error(f"Kariyer Kapısı kazıma hatası: {e}")

        return jobs
