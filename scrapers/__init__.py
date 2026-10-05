"""
Kamu Personel Rehberi - Kazıyıcı (Scraper) Modülü
"""
from .base import BaseScraper, ScrapedJob
from .resmi_gazete import ResmiGazeteScraper
from .kamu_ilan_sbb import SBBKamuIlanScraper
from .manager import ScraperManager

__all__ = [
    "BaseScraper",
    "ScrapedJob",
    "ResmiGazeteScraper",
    "SBBKamuIlanScraper",
    "ScraperManager",
]
