from typing import List
from datetime import datetime, timedelta
import requests
from loguru import logger

from .base import BaseScraper, ScrapedJob


class IlanGovTrScraper(BaseScraper):
    """
    Basın İlan Kurumu Resmi İlan Portalı (ilan.gov.tr)
    Kamu Personel Alımı Kazıyıcısı.
    
    Yalnızca resmi ve doğrulanmış kamu ilanlarını çeker.
    Takipçilere kurumsal ve yasal 'Resmi Kamu İlan Portalı' kimliği ile sunulur.
    """

    API_ENDPOINT = "https://www.ilan.gov.tr/api/api/services/app/Ad/AdsByFilter"

    def __init__(self):
        super().__init__(source_name="ilan.gov.tr (BİK)", timeout=15)
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json-patch+json",
            "Origin": "https://www.ilan.gov.tr",
            "Referer": "https://www.ilan.gov.tr/ilan/kategori/8/kamu-akademik-personel?ats=5",
            "X-Request-Origin": "IGT-UI",
            "X-Requested-With": "XMLHttpRequest"
        })

    def fetch_jobs(self) -> List[ScrapedJob]:
        jobs: List[ScrapedJob] = []
        payload = {
            "keys": {
                "txv": [8],
                "order": ["desc"],
                "field": ["publish_time"],
                "ats": [5]
            },
            "sorting": "publish_time desc",
            "skipCount": 0,
            "maxResultCount": 20
        }

        try:
            r = self.session.post(self.API_ENDPOINT, json=payload, timeout=self.timeout, verify=False)
            if r.status_code != 200:
                logger.warning(f"ilan.gov.tr API yanıt kodu ({r.status_code})")
                return jobs

            data = r.json()
            items = data.get("result", {}).get("ads", [])
            logger.info(f"Resmi Kamu İlan Portalı üzerinden {len(items)} adet doğrulanmış ilan çekildi.")

            for item in items:
                title = (item.get("title") or "").strip()
                if not title:
                    continue

                ad_id = item.get("id") or item.get("idInt") or item.get("adNo") or ""
                slug = item.get("slugifyTitle") or item.get("slug") or ""
                ad_url = f"https://www.ilan.gov.tr/ilan/{ad_id}/{slug}" if ad_id else "https://www.ilan.gov.tr/"

                institution = (item.get("advertiserName") or "").strip() or "Kamu Kurumu"
                city = item.get("addressCityName") or ""
                
                # Tarih ayrıştırma
                pub_date = None
                pub_date_str = item.get("publishStartDate")
                if pub_date_str:
                    try:
                        pub_date = datetime.fromisoformat(pub_date_str.replace("Z", "+00:00"))
                    except Exception:
                        pass

                raw_content = (
                    f"Kurum: {institution}\n"
                    f"Başlık: {title}\n"
                    f"Şehir: {city}\n"
                    f"İlan No: {item.get('adNo', '')}\n"
                    f"Resmi Bağlantı: {ad_url}"
                )

                # Son başvuru tarihi: Resmi İlanlarda genel kural 15 günlük başvuru süresidir
                app_end = (pub_date.replace(tzinfo=None) if pub_date else datetime.now()) + timedelta(days=15)

                from core.quota_validator import extract_verified_quota
                quota_info = extract_verified_quota(title, raw_content)

                job = ScrapedJob(
                    title=title,
                    source_name=self.source_name,
                    source_url=ad_url,
                    institution=institution,
                    position=title,
                    total_positions=quota_info["quota"],
                    official_doc_url=ad_url,
                    raw_content=raw_content,
                    publish_date=pub_date,
                    application_end_date=app_end,
                    is_verified=True
                )
                jobs.append(job)

        except Exception as e:
            logger.error(f"Resmi Kamu İlan Portalı kazıma hatası: {e}")

        return jobs
