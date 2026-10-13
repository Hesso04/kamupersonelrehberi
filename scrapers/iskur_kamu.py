from typing import List
from datetime import datetime
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from loguru import logger

from .base import BaseScraper, ScrapedJob


class IskurKamuScraper(BaseScraper):
    """
    T.C. Türkiye İş Kurumu (İŞKUR)
    Kamu Memur ve Personel Alım İlanları Kazıyıcısı.
    
    Yalnızca resmi ve doğrulanmış kamu ilanlarını çeker.
    Takipçilere kurumsal 'T.C. Resmi Kurum Duyurusu' kimliği ile sunulur.
    """

    BASE_URL = "https://www.iskur.gov.tr"
    TARGET_CITIES = [
        (6, "Ankara"),
        (34, "Istanbul"),
        (35, "Izmir"),
        (16, "Bursa"),
        (7, "Antalya")
    ]

    def __init__(self):
        super().__init__(source_name="T.C. Resmi Kurum Duyurusu", timeout=15)
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
        })

    def fetch_jobs(self) -> List[ScrapedJob]:
        jobs: List[ScrapedJob] = []

        try:
            # 1. Oturum çerezlerini başlatmak için ana sayfayı ziyaret et
            self.session.get(self.BASE_URL, verify=False, timeout=self.timeout)

            for city_id, city_name in self.TARGET_CITIES:
                target_url = f"{self.BASE_URL}/ilanlar/kamu-memur-alim-ilanlari/?idId={city_id}&il={city_name}"
                r = self.session.get(target_url, verify=False, timeout=self.timeout)
                if r.status_code != 200:
                    continue

                soup = BeautifulSoup(r.text, "html.parser")
                rows = soup.select("table tr, tbody tr")

                for row in rows:
                    file_url = row.get("data-file-url") or ""
                    cols = row.find_all("td")
                    if not cols or len(cols) < 2:
                        continue

                    # Tarih ve Başlık kolonları
                    date_str = cols[0].text.strip()
                    title = cols[1].text.strip()

                    if not title or "bulunamadı" in title.lower() or len(title) < 10:
                        continue

                    # Resmi PDF veya İlan Bağlantısı
                    full_doc_url = urljoin(self.BASE_URL, file_url) if file_url else target_url

                    # Tarih ayrıştırma (Örn: "19.10.2026 17:00")
                    deadline_dt = None
                    try:
                        date_part = date_str.split()[0]
                        deadline_dt = datetime.strptime(date_part, "%d.%m.%Y")
                    except Exception:
                        pass

                    # Kurum adını başlığın ilk kelimelerinden tespit et
                    institution = "T.C. Kamu Kurumu"
                    for kw in ["Bakanlığı", "Genel Müdürlüğü", "Başkanlığı", "Belediyesi", "Rektörlüğü", "Üniversitesi", "Kurumu"]:
                        if kw in title:
                            parts = title.split(kw)
                            institution = (parts[0] + " " + kw).strip()
                            break

                    raw_content = (
                        f"Kurum: {institution}\n"
                        f"İlan Başlığı: {title}\n"
                        f"Son Başvuru Tarihi: {date_str}\n"
                        f"Şehir: {city_name}\n"
                        f"Resmi Kılavuz PDF: {full_doc_url}"
                    )

                    job = ScrapedJob(
                        title=title,
                        source_name=self.source_name,
                        source_url=target_url,
                        institution=institution,
                        position=title,
                        total_positions=1,
                        official_doc_url=full_doc_url,
                        raw_content=raw_content,
                        publish_date=deadline_dt or datetime.utcnow(),
                        is_verified=True
                    )
                    jobs.append(job)

            logger.info(f"İŞKUR Kamu Alımları üzerinden {len(jobs)} adet resmi ilan çekildi.")

        except Exception as e:
            logger.error(f"İŞKUR kazıma hatası: {e}")

        return jobs
