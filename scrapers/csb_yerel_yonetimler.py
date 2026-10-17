from typing import List
from datetime import datetime, timedelta
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from loguru import logger
import re

from .base import BaseScraper, ScrapedJob


class CSBYerelYonetimlerScraper(BaseScraper):
    """
    Çevre, Şehircilik ve İklim Değişikliği Bakanlığı & Yerel Yönetimler
    Personel ve Memur Alım İlanları Kazıyıcısı.
    """

    URLS = [
        "https://csb.gov.tr/duyurular",
        "https://personel.csb.gov.tr/duyurular"
    ]

    # Alım niteliği taşımayan sınav sonucu / mülakat duyurularını kesinlikle engelle
    EXCLUDE_KEYWORDS = [
        "sonuçları", "sonuclari", "sonucu", "tercih duyurusu", "giriş belgesi",
        "yerleştirme sonuç", "asıl yedek", "nihai liste", "mülakat sonuç",
        "sözlü sınavı sonuç", "yazılı sınavı sonuç", "kura sonuç", "atamaya hak"
    ]

    def __init__(self):
        super().__init__(source_name="Yerel Yönetimler & ÇSB", timeout=15)

    def fetch_jobs(self) -> List[ScrapedJob]:
        jobs: List[ScrapedJob] = []
        seen_urls = set()

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

                    # Sınav sonucu veya tercih duyurusu ise ATLA (Adayları yanıltmamak için)
                    if any(bad in lower_txt for bad in self.EXCLUDE_KEYWORDS):
                        continue

                    keywords = [
                        "alım", "alim", "personel alımı", "memur alımı", "uzman yardımc", "denetmen",
                        "sözleşmeli", "sozlesmeli", "sınav ilanı", "sinav ilani",
                        "zabita", "mühendis", "kadro"
                    ]
                    if not any(k in lower_txt for k in keywords):
                        continue

                    full_url = urljoin(target_url, href)
                    if full_url in seen_urls:
                        continue
                    seen_urls.add(full_url)

                    if not self.is_official_source(full_url):
                        continue

                    clean_title = " ".join(txt.split())
                    # Eğer başta tarih varsa (örn: "12 Ekim 2026 Pazartesi...") temizle
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
                        title=clean_title[:340],
                        source_name=self.source_name,
                        source_url=full_url,
                        institution=institution[:240],
                        position=clean_title[:290],
                        total_positions=1,
                        official_doc_url=full_url,
                        raw_content=raw_content,
                        publish_date=datetime.utcnow(),
                        application_end_date=datetime.utcnow() + timedelta(days=15),
                        is_verified=True
                    )
                    jobs.append(job)

            except Exception as e:
                logger.error(f"CSB & Yerel Yönetimler tarama hatası ({target_url}): {e}")

        logger.info(f"Yerel Yönetimler & CSB kaynaklarından {len(jobs)} adet gerçek resmi ilan bulundu.")
        return jobs
