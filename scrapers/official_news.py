"""
T.C. Resmi Kamu Haberleri, Duyuruları ve Dezenformasyon Doğrulama Kazıyıcısı
Kaynaklar:
- T.C. Cumhurbaşkanlığı İletişim Başkanlığı (iletisim.gov.tr)
- Dezenformasyonla Mücadele Merkezi / DMM (dbs.iletisim.gov.tr)
- T.C. Çalışma ve Sosyal Güvenlik Bakanlığı (csgb.gov.tr)
- T.C. Hazine ve Maliye Bakanlığı (hmb.gov.tr, personel.hmb.gov.tr)
- Mevzuat Bilgi Sistemi (mevzuat.gov.tr)
"""
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import List, Dict, Any, Optional
import requests
from bs4 import BeautifulSoup
from loguru import logger

import os
import sys

# Proje kök dizinini sys.path'e ekle
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from core.database import get_db
from core.models import OfficialNews

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 (KamuPersonelRehberi-OfficialNewsBot/1.0)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
}


def clean_text(text: Optional[str]) -> str:
    if not text:
        return ""
    # HTML etiketlerini ve fazla boşlukları temizle
    soup = BeautifulSoup(text, "html.parser")
    cleaned = soup.get_text(separator=" ").strip()
    return re.sub(r"\s+", " ", cleaned)


class OfficialNewsScraper:
    """
    Resmi devlet portallarından reklamsız, teyitli kamu haberleri toplayan servis.
    """

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def fetch_all(self) -> List[Dict[str, Any]]:
        """Tüm resmi kaynakları sırayla tarar ve haber listesi döner."""
        news_items: List[Dict[str, Any]] = []

        # 1. İletişim Başkanlığı Haberleri
        try:
            items = self.fetch_iletisim_baskanligi()
            news_items.extend(items)
            logger.info(f"İletişim Başkanlığı: {len(items)} haber çekildi.")
        except Exception as e:
            logger.warning(f"İletişim Başkanlığı tarama hatası: {e}")

        # 2. Dezenformasyonla Mücadele Merkezi (DMM)
        try:
            items = self.fetch_dmm_dezenformasyon()
            news_items.extend(items)
            logger.info(f"DMM Doğrulama Merkezi: {len(items)} bülten/haber çekildi.")
        except Exception as e:
            logger.warning(f"DMM tarama hatası: {e}")

        # 3. ÇSGB Duyuruları
        try:
            items = self.fetch_csgb_duyurular()
            news_items.extend(items)
            logger.info(f"ÇSGB Duyuruları: {len(items)} haber çekildi.")
        except Exception as e:
            logger.warning(f"ÇSGB tarama hatası: {e}")

        # 4. Hazine ve Maliye Bakanlığı Duyuruları
        try:
            items = self.fetch_hmb_duyurular()
            news_items.extend(items)
            logger.info(f"Hazine ve Maliye Bakanlığı: {len(items)} haber çekildi.")
        except Exception as e:
            logger.warning(f"HMB tarama hatası: {e}")

        # 5. Mevzuat Bilgi Sistemi Güncellemeleri
        try:
            items = self.fetch_mevzuat_updates()
            news_items.extend(items)
            logger.info(f"Mevzuat Bilgi Sistemi: {len(items)} duyuru çekildi.")
        except Exception as e:
            logger.warning(f"Mevzuat tarama hatası: {e}")

        return news_items

    def fetch_iletisim_baskanligi(self) -> List[Dict[str, Any]]:
        """İletişim Başkanlığı RSS akışını veya haber portalını çeker."""
        results = []
        rss_url = "https://www.iletisim.gov.tr/turkce/haberler/rss"
        try:
            resp = self.session.get(rss_url, timeout=12)
            if resp.status_code == 200:
                root = ET.fromstring(resp.content)
                for item in root.findall(".//item")[:10]:
                    title = clean_text(item.findtext("title"))
                    link = clean_text(item.findtext("link"))
                    desc = clean_text(item.findtext("description"))
                    pub_date = item.findtext("pubDate")
                    
                    if title and link:
                        results.append({
                            "title": title,
                            "institution": "T.C. İletişim Başkanlığı",
                            "category": "RESMI_HABER",
                            "summary": desc[:320] + "..." if len(desc) > 320 else desc,
                            "content": desc,
                            "source_name": "İletişim Başkanlığı Haber Portalı",
                            "source_url": link,
                            "publish_date": datetime.utcnow()
                        })
        except Exception:
            # RSS alternatifi: Haber ana sayfası
            web_url = "https://www.iletisim.gov.tr/turkce/haberler"
            resp = self.session.get(web_url, timeout=12)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                for card in soup.select("a[href*='/turkce/haberler/']")[:8]:
                    href = card.get("href", "")
                    title = clean_text(card.get_text())
                    if len(title) > 20:
                        full_url = href if href.startswith("http") else f"https://www.iletisim.gov.tr{href}"
                        results.append({
                            "title": title,
                            "institution": "T.C. İletişim Başkanlığı",
                            "category": "RESMI_HABER",
                            "summary": f"T.C. Cumhurbaşkanlığı İletişim Başkanlığı resmi açıklaması: {title}",
                            "content": title,
                            "source_name": "İletişim Başkanlığı Haber Portalı",
                            "source_url": full_url,
                            "publish_date": datetime.utcnow()
                        })
        return results

    def fetch_dmm_dezenformasyon(self) -> List[Dict[str, Any]]:
        """Dezenformasyonla Mücadele Merkezi bültenlerini çeker."""
        results = []
        url = "https://www.iletisim.gov.tr/turkce/dezenformasyon-bulteni"
        resp = self.session.get(url, timeout=12)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            links = soup.select("a[href*='dezenformasyon']")
            for a in links[:6]:
                title = clean_text(a.get_text())
                href = a.get("href", "")
                if len(title) > 15 and "bülten" in title.lower():
                    full_url = href if href.startswith("http") else f"https://www.iletisim.gov.tr{href}"
                    results.append({
                        "title": f"🛡️ [DMM DOĞRULAMA] {title}",
                        "institution": "Dezenformasyonla Mücadele Merkezi (DMM)",
                        "category": "DEZENFORMASYON",
                        "summary": "Kamuoyundaki asılsız iddialara ve kamu kurumlarıyla ilgili dezenformasyonlara karşı resmi gerçekler ve doğrulama raporu.",
                        "content": f"{title} kapsamında kamuoyunu yanıltmaya yönelik haberlerin resmi doğrulaması ve gerçekler.",
                        "source_name": "Dezenformasyonla Mücadele Merkezi",
                        "source_url": full_url,
                        "publish_date": datetime.utcnow()
                    })
        return results

    def fetch_csgb_duyurular(self) -> List[Dict[str, Any]]:
        """Çalışma ve Sosyal Güvenlik Bakanlığı duyurularını çeker."""
        results = []
        url = "https://www.csgb.gov.tr/duyurular/"
        resp = self.session.get(url, timeout=12)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.select("a[href*='/duyurular/']")
            seen_titles = set()
            for c in cards[:8]:
                title = clean_text(c.get_text())
                href = c.get("href", "")
                if len(title) > 20 and title not in seen_titles:
                    seen_titles.add(title)
                    full_url = href if href.startswith("http") else f"https://www.csgb.gov.tr{href}"
                    results.append({
                        "title": f"📊 {title}",
                        "institution": "T.C. Çalışma ve Sosyal Güvenlik Bakanlığı",
                        "category": "OZLUK_MAAS",
                        "summary": f"Çalışma hayatı, kamu çalışanları, sendikal haklar ve sosyal güvenlik mevzuatına ilişkin bakanlık resmi duyurusu: {title}",
                        "content": title,
                        "source_name": "ÇSGB Resmi Duyurular",
                        "source_url": full_url,
                        "publish_date": datetime.utcnow()
                    })
        return results

    def fetch_hmb_duyurular(self) -> List[Dict[str, Any]]:
        """Hazine ve Maliye Bakanlığı genel ve personel duyurularını çeker."""
        results = []
        url = "https://www.hmb.gov.tr/bakanlik-duyurulari"
        try:
            resp = self.session.get(url, timeout=12)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                cards = soup.select("a[href*='duyuru']")
                seen = set()
                for c in cards[:6]:
                    title = clean_text(c.get_text())
                    href = c.get("href", "")
                    if len(title) > 20 and title not in seen:
                        seen.add(title)
                        full_url = href if href.startswith("http") else f"https://www.hmb.gov.tr{href}"
                        results.append({
                            "title": f"💰 {title}",
                            "institution": "T.C. Hazine ve Maliye Bakanlığı",
                            "category": "OZLUK_MAAS",
                            "summary": f"Mali konular, memur maaş katsayıları, genelgeler ve merkezi sınav duyuruları: {title}",
                            "content": title,
                            "source_name": "Hazine ve Maliye Bakanlığı",
                            "source_url": full_url,
                            "publish_date": datetime.utcnow()
                        })
        except Exception:
            pass
        return results

    def fetch_mevzuat_updates(self) -> List[Dict[str, Any]]:
        """Mevzuat Bilgi Sistemi duyuru ve değişikliklerini simüle/entegre eder."""
        results = []
        # Mevzuat sistemi doğrudan kamu çalışanlarını ilgilendiren kanun değişiklikleri
        sample_items = [
            {
                "title": "📜 Kamu Görevlileri ve Sözleşmeli Personel Mevzuatında Güncel Değişiklikler",
                "institution": "Mevzuat Bilgi Sistemi",
                "category": "MEVZUAT",
                "summary": "Resmi Gazete'de yayımlanarak yürürlüğe giren 657 Sayılı DMK, 4/B Sözleşmeli Personel Esasları ve Cumhurbaşkanlığı Kararnameleri güncel tam metinleri.",
                "content": "Kamu görevlilerinin mali, sosyal ve özlük haklarını düzenleyen kanun ve yönetmeliklerin güncellenmiş tam metinlerine mevzuat.gov.tr üzerinden erişebilirsiniz.",
                "source_name": "Mevzuat Bilgi Sistemi (mevzuat.gov.tr)",
                "source_url": "https://www.mevzuat.gov.tr",
                "publish_date": datetime.utcnow()
            }
        ]
        return sample_items

    def generate_social_post_text(self, item: Dict[str, Any]) -> str:
        """
        Sosyal medya kanalları için editoryal haber diliyle (Haber Ağzı) metin üretir.
        İlan paylaşımlarından tamamen farklıdır.
        """
        title = item.get("title", "")
        institution = item.get("institution", "")
        summary = item.get("summary", "")
        url = item.get("source_url", "")
        category = item.get("category", "")

        cat_tag = "#KamuHaberleri"
        cat_badge = "📢 RESMİ AÇIKLAMA"
        if category == "DEZENFORMASYON":
            cat_tag = "#Doğrulama #DMM"
            cat_badge = "🛡️ DEZENFORMASYONLA MÜCADELE MERKEZİ DOĞRULAMASI"
        elif category == "OZLUK_MAAS":
            cat_tag = "#MemurMaaşları #ÖzlükHakları"
            cat_badge = "📊 ÖZLÜK & MALİ HAKLAR BÜLTENİ"
        elif category == "MEVZUAT":
            cat_tag = "#Mevzuat #ResmiGazete"
            cat_badge = "📜 YASAL MEVZUAT DEĞİŞİKLİĞİ"

        lines = [
            f"🏛️ <b>{cat_badge}</b>",
            f"📍 <b>Kurum:</b> {institution}",
            "",
            f"<b>{title}</b>",
            "",
            f"📝 <b>Resmi Açıklama Özeti:</b>\n{summary}",
            "",
            "ℹ️ <i>Kamu çalışanları ve adaylar için doğrudan birinci elden resmi teyitli bilgidir. Reklamsız ve aracısız devlet kaynağıdır.</i>",
            "",
            f"🔗 <b>Resmi Kaynak Bağlantısı:</b> {url}",
            f"🌐 <b>Tüm Kamu Haberleri & İlanlar:</b> https://kamupersonelrehberiniz.me",
            "",
            f"{cat_tag} #KamuPersoneli #Memur #Haber"
        ]
        return "\n".join(lines)

    def save_to_db(self, items: List[Dict[str, Any]]) -> int:
        """Mükerrer olmayan haberleri veritabanına kaydeder."""
        saved_count = 0
        with get_db() as db:
            for item in items:
                # Başlık veya kaynak URL kontrolü
                existing = db.query(OfficialNews).filter(
                    (OfficialNews.title == item["title"]) |
                    (OfficialNews.source_url == item["source_url"])
                ).first()

                if not existing:
                    social_text = self.generate_social_post_text(item)
                    news_entry = OfficialNews(
                        title=item["title"],
                        institution=item["institution"],
                        category=item.get("category", "RESMI_HABER"),
                        summary=item.get("summary", ""),
                        content=item.get("content", ""),
                        source_name=item["source_name"],
                        source_url=item["source_url"],
                        image_url=item.get("image_url"),
                        social_post_text=social_text,
                        publish_date=item.get("publish_date", datetime.utcnow()),
                        is_verified=True,
                        is_social_published=False
                    )
                    db.add(news_entry)
                    saved_count += 1
            db.commit()
        return saved_count


def run_news_scraper() -> int:
    """Tek fonksiyonla taramayı çalıştırıp yeni haber sayısını döner."""
    logger.info("Resmi kamu haberleri taraması başlatılıyor...")
    scraper = OfficialNewsScraper()
    items = scraper.fetch_all()
    count = scraper.save_to_db(items)
    logger.info(f"Kamu haberleri taraması tamamlandı: {count} yeni haber eklendi.")
    return count


if __name__ == "__main__":
    count = run_news_scraper()
    print(f"Toplam {count} yeni resmi haber kaydedildi.")
