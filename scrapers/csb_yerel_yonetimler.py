from typing import List
from datetime import datetime
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from loguru import logger

from .base import BaseScraper, ScrapedJob


class CSBYerelYonetimlerScraper(BaseScraper):
    """
    Çevre, Şehircilik ve İklim Değişikliği Bakanlığı & Yerel Yönetimler
    Personel ve Memur Alım İlanları Kazıyıcısı.
    
    Takipçilere kurumsal 'Resmi Kamu İlan Portalı' kimliği ile sunulur.
    """

    URLS = [
        "https://csb.gov.tr/duyurular",
        "https://personel.csb.gov.tr/duyurular"
    ]

    def __init__(self):
        super().__init__(source_name="Resmi Kamu İlan Portalı", timeout=15)

    def fetch_jobs(self) -> List[ScrapedJob]:
        jobs: List[ScrapedJob] = []

        for target_url in self.URLS:
            try:
                r = self.session.get(target_url, timeout=self.timeout, verify=False)
                if r.status_code != 200:
                    continue

                soup = BeautifulSoup(r.text, "html.parser")
                links = soup.find_all("a", href=True)

                for a in links:
                    txt = a.text.strip()
                    href = a["href"]

                    # Sadece doğrudan duyuru veya ilan detay sayfalarını al
                    if not any(k in href.lower() for k in ["duyuru-", "ilan-", "/duyuru/", "/ilan/"]):
                        continue

                    # Personel, sınav, alım veya uzmanlık ile ilgili duyuruları filtrele
                    if len(txt) < 15:
                        continue
                    
                    lower_txt = txt.lower()
                    keywords = [
                        "alım", "alim", "personel", "memur", "uzman yardımc", "denetmen",
                        "sözleşmeli", "sozlesmeli", "sınav ilanı", "sinav ilani",
                        "zabita", "mühendis", "kadro", "tercih duyurusu"
                    ]
                    if not any(k in lower_txt for k in keywords):
                        continue

                    full_url = urljoin(target_url, href)
                    if not self.is_official_source(full_url):
                        continue

                    clean_title = " ".join(txt.split())
                    # Eğer başta tarih varsa (örn: "12 Ekim 2026 Pazartesi...") temizle
                    import re
                    clean_title = re.sub(r"^\d{1,2}\s+[A-Za-zÇĞİÖŞÜçğıöşü]+\s+\d{4}(?:\s+[A-Za-zÇĞİÖŞÜçğıöşü]+)?\s*", "", clean_title).strip()
                    if len(clean_title) > 200:
                        clean_title = clean_title[:197] + "..."

                    institution = "Çevre, Şehircilik ve İklim Değişikliği Bakanlığı"
                    if "belediye" in clean_title.lower():
                        institution = "Yerel Yönetimler / Mahalli İdareler"

                    raw_content = (
                        f"Kurum: {institution}\n"
                        f"Duyuru: {clean_title}\n"
                        f"Resmi Bağlantı: {full_url}\n"
                        f"Kategori: Yerel Yönetimler & Kamu Personeli Alımı"
                    )

                    job = ScrapedJob(
                        title=clean_title,
                        source_name=self.source_name,
                        source_url=full_url,
                        institution=institution,
                        position=clean_title,
                        total_positions=1,
                        official_doc_url=full_url,
                        raw_content=raw_content,
                        publish_date=datetime.utcnow(),
                        is_verified=True
                    )
                    jobs.append(job)

            except Exception as e:
                logger.error(f"CSB & Yerel Yönetimler tarama hatası ({target_url}): {e}")

        logger.info(f"Yerel Yönetimler & CSB kaynaklarından {len(jobs)} adet resmi ilan bulundu.")
        return jobs
