"""
Kamu Personel Rehberi - Resmi Kazıyıcı (Scraper) Modülleri
Tüm kaynaklar %100 yasal ve onaylı kamu portallarıdır.
"""
from .base import BaseScraper, ScrapedJob
from .resmi_gazete import ResmiGazeteScraper
from .kamu_ilan_sbb import SBBKamuIlanScraper
from .ilan_gov_tr import IlanGovTrScraper
from .kariyer_kapisi import KariyerKapisiScraper
from .iskur_kamu import IskurKamuScraper
from .csb_yerel_yonetimler import CSBYerelYonetimlerScraper
from .manager import ScraperManager

__all__ = [
    "BaseScraper",
    "ScrapedJob",
    "ResmiGazeteScraper",
    "SBBKamuIlanScraper",
    "IlanGovTrScraper",
    "KariyerKapisiScraper",
    "IskurKamuScraper",
    "CSBYerelYonetimlerScraper",
    "ScraperManager",
]
