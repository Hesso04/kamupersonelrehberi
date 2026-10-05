from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime
from urllib.parse import urlparse
import requests
from loguru import logger


@dataclass
class ScrapedJob:
    """Kazıyıcı tarafından elde edilen ham ve doğrulanmış ilan verisi"""
    title: str
    source_name: str
    source_url: str
    institution: Optional[str] = None
    position: Optional[str] = None
    total_positions: Optional[int] = 1
    official_doc_url: Optional[str] = None
    pdf_path: Optional[str] = None
    raw_content: Optional[str] = None
    publish_date: Optional[datetime] = None
    is_verified: bool = False


class BaseScraper(ABC):
    """Tüm resmi kaynak kazıyıcıları için temel soyut sınıf"""

    OFFICIAL_DOMAINS = [
        "resmigazete.gov.tr",
        "kamuilan.sbb.gov.tr",
        "iskur.gov.tr",
        "kariyerkapisi.cbiko.gov.tr",
        "osym.gov.tr",
        "yok.gov.tr"
    ]

    def __init__(self, source_name: str, timeout: int = 15):
        self.source_name = source_name
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36 (KamuPersonelRehberi Bot)"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
        })

    def is_official_source(self, url: str) -> bool:
        """
        URL'nin resmi bir devlet kurumuna (.gov.tr) veya
        güvenli resmi portala ait olup olmadığını sıkı denetler.
        """
        if not url:
            return False
        try:
            parsed = urlparse(url)
            hostname = parsed.netloc.lower()
            if hostname.startswith("www."):
                hostname = hostname[4:]

            # .gov.tr uzantılı tüm resmi kurumlar doğrudan geçer
            if hostname.endswith(".gov.tr") or hostname == "gov.tr":
                return True

            # Tanımlı resmi portallar
            for domain in self.OFFICIAL_DOMAINS:
                if hostname == domain or hostname.endswith("." + domain):
                    return True

            return False
        except Exception as e:
            logger.warning(f"URL doğrulama hatası ({url}): {e}")
            return False

    @abstractmethod
    def fetch_jobs(self) -> List[ScrapedJob]:
        """Kaynak siteden son ilanları çeker ve döner."""
        pass
