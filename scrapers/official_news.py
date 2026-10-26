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
from scrapers.content_filter import ContentFilterEngine, check_audience_relevance

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 (KamuPersonelRehberi-OfficialNewsBot/2.0)",
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
    Akıllı filtreleme kalkanı ile protokol/tören haberlerini eler, kitle odaklı haberleri önceler.
    """

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def fetch_all(self) -> List[Dict[str, Any]]:
        """Tüm resmi kaynakları sırayla tarar ve haber listesi döner."""
        news_items: List[Dict[str, Any]] = []

        # 1. ÖSYM Duyuruları (KPSS, Yerleştirme, Sınav Kılavuzları)
        try:
            items = self.fetch_osym_duyurular()
            news_items.extend(items)
            logger.info(f"ÖSYM Portalı: {len(items)} duyuru çekildi.")
        except Exception as e:
            logger.warning(f"ÖSYM tarama hatası: {e}")

        # 2. TOKİ Haberleri & Sosyal Konut Kuraları
        try:
            items = self.fetch_toki_haberler()
            news_items.extend(items)
            logger.info(f"TOKİ Portalı: {len(items)} haber/sosyal konut duyurusu çekildi.")
        except Exception as e:
            logger.warning(f"TOKİ tarama hatası: {e}")

        # 3. MEB Duyuruları & Öğretmen Atama / Sınav Haberleri
        try:
            items = self.fetch_meb_duyurular()
            news_items.extend(items)
            logger.info(f"MEB Portalı: {len(items)} haber/duyuru çekildi.")
        except Exception as e:
            logger.warning(f"MEB tarama hatası: {e}")

        # 4. İletişim Başkanlığı Haberleri (Filtre kalkanı ile elenerek)
        try:
            items = self.fetch_iletisim_baskanligi()
            news_items.extend(items)
            logger.info(f"İletişim Başkanlığı: {len(items)} haber çekildi.")
        except Exception as e:
            logger.warning(f"İletişim Başkanlığı tarama hatası: {e}")

        # 5. Dezenformasyonla Mücadele Merkezi (DMM)
        try:
            items = self.fetch_dmm_dezenformasyon()
            news_items.extend(items)
            logger.info(f"DMM Doğrulama Merkezi: {len(items)} bülten/haber çekildi.")
        except Exception as e:
            logger.warning(f"DMM tarama hatası: {e}")

        # 6. ÇSGB Duyuruları (Özlük ve Çalışma Hayatı)
        try:
            items = self.fetch_csgb_duyurular()
            news_items.extend(items)
            logger.info(f"ÇSGB Duyuruları: {len(items)} haber çekildi.")
        except Exception as e:
            logger.warning(f"ÇSGB tarama hatası: {e}")

        # 7. Hazine ve Maliye Bakanlığı Duyuruları
        try:
            items = self.fetch_hmb_duyurular()
            news_items.extend(items)
            logger.info(f"Hazine ve Maliye Bakanlığı: {len(items)} haber çekildi.")
        except Exception as e:
            logger.warning(f"HMB tarama hatası: {e}")

        # 8. Mevzuat Bilgi Sistemi Güncellemeleri
        try:
            items = self.fetch_mevzuat_updates()
            news_items.extend(items)
            logger.info(f"Mevzuat Bilgi Sistemi: {len(items)} duyuru çekildi.")
        except Exception as e:
            logger.warning(f"Mevzuat tarama hatası: {e}")

        # 9. memurlar.net RSS (Türkiye'nin en büyük kamu haberleri portalı)
        try:
            items = self.fetch_memurlernet_rss()
            news_items.extend(items)
            logger.info(f"memurlar.net RSS: {len(items)} haber çekildi.")
        except Exception as e:
            logger.warning(f"memurlar.net tarama hatası: {e}")

        # 10. Anadolu Ajansı - Eğitim & Kariyer Haberleri
        try:
            items = self.fetch_aa_egitim_kariyer()
            news_items.extend(items)
            logger.info(f"Anadolu Ajansı: {len(items)} eğitim/kariyer haberi çekildi.")
        except Exception as e:
            logger.warning(f"Anadolu Ajansı tarama hatası: {e}")

        # 11. SGK - Sosyal Güvenlik Kurumu Duyuruları
        try:
            items = self.fetch_sgk_duyurular()
            news_items.extend(items)
            logger.info(f"SGK Duyuruları: {len(items)} haber çekildi.")
        except Exception as e:
            logger.warning(f"SGK tarama hatası: {e}")

        # 12. DPB - Devlet Personel Başkanlığı Mevzuat/Görüş/Duyuruları
        try:
            items = self.fetch_dpb_duyurular()
            news_items.extend(items)
            logger.info(f"DPB Başkanlığı: {len(items)} haber çekildi.")
        except Exception as e:
            logger.warning(f"DPB tarama hatası: {e}")

        return news_items

    def fetch_osym_duyurular(self) -> List[Dict[str, Any]]:
        """ÖSYM Başkanlığı güncel sınav, kılavuz ve yerleştirme duyurularını çeker."""
        results = []
        url = "https://www.osym.gov.tr/"
        try:
            resp = self.session.get(url, timeout=12)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                seen_titles = set()
                # Ana sayfadaki tüm linkleri tara
                for a in soup.find_all("a", href=True):
                    title = clean_text(a.get_text())
                    href = a.get("href", "").strip()
                    # KPSS, Kılavuz, Başvuru veya Sınav içeren duyurular
                    lower_t = title.lower()
                    if len(title) > 15 and title not in seen_titles:
                        if any(k in lower_t for k in ["kpss", "başvuru kılavuzu", "kılavuz", "yerleştirme", "atama", "sınav takvimi", "sonuçları"]):
                            seen_titles.add(title)
                            full_url = href if href.startswith("http") else f"https://www.osym.gov.tr{href}"
                            results.append({
                                "title": f"🎯 {title}",
                                "institution": "T.C. Ölçme, Seçme ve Yerleştirme Merkezi (ÖSYM)",
                                "category": "ATAMA_KADRO",
                                "summary": f"ÖSYM Başkanlığı resmi duyurusu yayımlandı: {title}. Kılavuz ve başvuru ekranı erişime açılmıştır.",
                                "content": f"Ölçme, Seçme ve Yerleştirme Merkezi (ÖSYM) tarafından yayımlanan resmi duyuru metni: {title}. Adaylar AİS (ais.osym.gov.tr) üzerinden işlemlerini gerçekleştirebilirler.",
                                "source_name": "ÖSYM Resmi Duyurular",
                                "source_url": full_url,
                                "publish_date": datetime.utcnow()
                            })
                            if len(results) >= 8:
                                break
        except Exception as e:
            logger.warning(f"ÖSYM kazıma istisnası: {e}")
        return results

    def fetch_toki_haberler(self) -> List[Dict[str, Any]]:
        """TOKİ Sosyal Konut, Kura Çekimi ve İndirim Kampanyası haberlerini çeker."""
        results = []
        url = "https://www.toki.gov.tr/haberler"
        try:
            # SSL doğrulaması bazı kurum sunucularında hata verebiliyor
            resp = self.session.get(url, timeout=12, verify=False)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                seen = set()
                for a in soup.find_all("a", href=True):
                    href = a.get("href", "").strip()
                    if "/haber/" in href:
                        raw_title = clean_text(a.get_text())
                        # 'Devamı' kelimesini temizle
                        title = re.sub(r"(?i)\s*devamı\s*", "", raw_title).strip()
                        # Tarih önekini (örn: 26 Ekim 2026) ayıkla veya temizle
                        clean_title = re.sub(r"^\d{1,2}\s+[A-Za-zÇĞİÖŞÜçğıöşü]+\s+\d{4}", "", title).strip()
                        if len(clean_title) > 20 and clean_title not in seen:
                            seen.add(clean_title)
                            full_url = href if href.startswith("http") else f"https://www.toki.gov.tr{href}"
                            results.append({
                                "title": f"🏠 {clean_title}",
                                "institution": "T.C. Çevre, Şehircilik ve İklim Değişikliği Bakanlığı (TOKİ)",
                                "category": "SOSYAL_HAK_TOKI",
                                "summary": f"TOKİ resmi duyurusu: {clean_title}. Sosyal konut teslimleri, kura tarihleri ve başvuru süreci detayları.",
                                "content": f"Toplu Konut İdaresi Başkanlığı (TOKİ) tarafından paylaşılan resmi kamu duyurusu: {clean_title}. Detaylar ve takvim toki.gov.tr adresinde ilan edilmiştir.",
                                "source_name": "TOKİ Haber Portalı",
                                "source_url": full_url,
                                "publish_date": datetime.utcnow()
                            })
                            if len(results) >= 8:
                                break
        except Exception as e:
            logger.warning(f"TOKİ kazıma istisnası: {e}")
        return results

    def fetch_meb_duyurular(self) -> List[Dict[str, Any]]:
        """Milli Eğitim Bakanlığı öğretmen atama, sınav rehberi ve norm kadro haberlerini çeker."""
        results = []
        url = "https://www.meb.gov.tr/"
        try:
            resp = self.session.get(url, timeout=12)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                seen = set()
                for a in soup.find_all("a", href=True):
                    href = a.get("href", "").strip()
                    if any(k in href for k in ["/haber/", "/duyuru/"]):
                        title = clean_text(a.get_text())
                        if len(title) > 25 and title not in seen:
                            seen.add(title)
                            full_url = href if href.startswith("http") else f"https://www.meb.gov.tr{href}"
                            results.append({
                                "title": f"📚 {title}",
                                "institution": "T.C. Millî Eğitim Bakanlığı",
                                "category": "ATAMA_KADRO",
                                "summary": f"Millî Eğitim Bakanlığı resmi duyurusu: {title}",
                                "content": f"T.C. Millî Eğitim Bakanlığı tarafından yayımlanan güncel kamu bülteni: {title}",
                                "source_name": "MEB Haber Portalı",
                                "source_url": full_url,
                                "publish_date": datetime.utcnow()
                            })
                            if len(results) >= 8:
                                break
        except Exception as e:
            logger.warning(f"MEB kazıma istisnası: {e}")
        return results

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
        elif category == "ATAMA_KADRO":
            cat_tag = "#KPSS #ÖSYM #Atama"
            cat_badge = "🎯 SINAV, KILAVUZ & ATAMA BÜLTENİ"
        elif category == "SOSYAL_HAK_TOKI":
            cat_tag = "#TOKİ #SosyalKonut #Kura"
            cat_badge = "🏠 TOKİ SOSYAL KONUT & KURA GELİŞMESİ"
        elif category == "ISCI_SOZLESMELI":
            cat_tag = "#Sürekliİşçi #4B #Kadro"
            cat_badge = "👷 SÜREKLİ İŞÇİ & SÖZLEŞMELİ PERSONEL"
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
        """Akıllı filtre kalkanından geçen ve mükerrer olmayan haberleri veritabanına kaydeder."""
        saved_count = 0
        filtered_out_count = 0
        with get_db() as db:
            for item in items:
                # 1. Akıllı Editoryal Filtre Kalkanı Kontrolü (Kara Liste ve Kitle Uygunluğu)
                filter_res = ContentFilterEngine.filter_item(
                    title=item["title"],
                    content=item.get("content", ""),
                    summary=item.get("summary", ""),
                    institution=item.get("institution", "")
                )
                if not filter_res.is_allowed:
                    filtered_out_count += 1
                    logger.info(f"🚫 [FİLTRE ELENDİ] '{item['title'][:55]}' -> {filter_res.reject_reason}")
                    continue

                # Filtre kategorisi daha spesifikse kullan
                if filter_res.category and filter_res.category != "RESMI_HABER":
                    item["category"] = filter_res.category

                # 2. Başlık veya kaynak URL kontrolü
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
        if filtered_out_count > 0:
            logger.info(f"🛡️ Filtre Kalkanı Raporu: {filtered_out_count} protokol/bürokratik haber kitle ilgisi taşımadığı için elendi.")
        return saved_count


    def fetch_memurlernet_rss(self) -> List[Dict[str, Any]]:
        """
        memurlar.net — Türkiye'nin en büyük kamu haberleri ve kamu çalışanları portalı.
        RSS akışı üzerinden güncel maaş, atama, mevzuat ve kamu haberleri çeker.
        Filtre Motoru ile protokol haberleri elenir, yüksek ilgili haberler önceliklendirilir.
        """
        results = []
        rss_urls = [
            ("https://www.memurlar.net/haber/rss.xml", "memurlar.net Genel Haberler"),
            ("https://www.memurlar.net/haber/ekonomi/rss.xml", "memurlar.net Ekonomi & Maaş"),
        ]
        for rss_url, source_label in rss_urls:
            try:
                resp = self.session.get(rss_url, timeout=15)
                if resp.status_code != 200:
                    continue
                root = ET.fromstring(resp.content)
                for item in root.findall(".//item")[:15]:
                    title = clean_text(item.findtext("title"))
                    link = clean_text(item.findtext("link"))
                    desc = clean_text(item.findtext("description"))
                    if not title or not link:
                        continue
                    # Özet metni temizle (HTML etiketleri kaldır)
                    summary = BeautifulSoup(desc, "html.parser").get_text(separator=" ", strip=True)[:400]

                    results.append({
                        "title": title,
                        "institution": "memurlar.net",
                        "category": "RESMI_HABER",
                        "summary": summary or f"memurlar.net haberi: {title}",
                        "content": summary,
                        "source_name": source_label,
                        "source_url": link,
                        "publish_date": datetime.utcnow()
                    })
            except Exception as e:
                logger.warning(f"memurlar.net RSS ({rss_url}) hatası: {e}")
        return results

    def fetch_aa_egitim_kariyer(self) -> List[Dict[str, Any]]:
        """
        Anadolu Ajansı — Eğitim ve kariyer haberleri RSS akışı.
        KPSS, öğretmen ataması, üniversite sınavları ve kamu istihdam haberleri içerir.
        """
        results = []
        # AA eğitim kategorisi RSS
        rss_url = "https://www.aa.com.tr/tr/rss/default?cat=egitim"
        try:
            resp = self.session.get(rss_url, timeout=15)
            if resp.status_code == 200:
                root = ET.fromstring(resp.content)
                for item in root.findall(".//item")[:12]:
                    title = clean_text(item.findtext("title"))
                    link = clean_text(item.findtext("link"))
                    desc = clean_text(item.findtext("description"))
                    if not title or not link:
                        continue
                    summary = BeautifulSoup(desc, "html.parser").get_text(separator=" ", strip=True)[:350] if desc else ""
                    results.append({
                        "title": f"📰 {title}",
                        "institution": "Anadolu Ajansı",
                        "category": "RESMI_HABER",
                        "summary": summary or f"Anadolu Ajansı aktarımı: {title}",
                        "content": summary,
                        "source_name": "Anadolu Ajansı — Eğitim & Kariyer",
                        "source_url": link,
                        "publish_date": datetime.utcnow()
                    })
        except Exception as e:
            logger.warning(f"Anadolu Ajansı RSS hatası: {e}")
        return results

    def fetch_sgk_duyurular(self) -> List[Dict[str, Any]]:
        """
        SGK — Sosyal Güvenlik Kurumu Başkanlığı.
        Emeklilik, prim, bağkur, sağlık aktivasyonu ve istihdam teşviki duyurularını çeker.
        """
        results = []
        url = "https://www.sgk.gov.tr/duyurular"
        try:
            resp = self.session.get(url, timeout=12, verify=False)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                seen = set()
                # Genel link taraması (farklı kurumsal şablon yapılarını kapsıyor)
                for a in soup.find_all("a", href=True):
                    href = a.get("href", "").strip()
                    if "duyuru" not in href.lower() and "haber" not in href.lower():
                        continue
                    title = clean_text(a.get_text())
                    if len(title) > 25 and title not in seen:
                        seen.add(title)
                        full_url = href if href.startswith("http") else f"https://www.sgk.gov.tr{href}"
                        results.append({
                            "title": f"🏦 {title}",
                            "institution": "T.C. Sosyal Güvenlik Kurumu Başkanlığı (SGK)",
                            "category": "OZLUK_MAAS",
                            "summary": f"SGK resmi duyurusu: {title}. Emeklilik, sigortalılık ve sosyal güvence hakları hakkında.",
                            "content": title,
                            "source_name": "SGK Resmi Duyurular",
                            "source_url": full_url,
                            "publish_date": datetime.utcnow()
                        })
                        if len(results) >= 8:
                            break
        except Exception as e:
            logger.warning(f"SGK kazıma istisnası: {e}")
        return results

    def fetch_dpb_duyurular(self) -> List[Dict[str, Any]]:
        """
        DPB — Devlet Personel Başkanlığı.
        Kamu personel mevzuatı görüşleri, yönetmelik değişiklikleri, sınav ve atama duyurularını çeker.
        657 sayılı DMK uygulaması ve yorumları açısından kamu çalışanlarının birincil başvuru kaynağıdır.
        """
        results = []
        url = "https://www.dpb.gov.tr/tr-TR/bilgi-bankasi/duyurular"
        try:
            resp = self.session.get(url, timeout=12, verify=False)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                seen = set()
                for a in soup.find_all("a", href=True):
                    href = a.get("href", "").strip()
                    title = clean_text(a.get_text())
                    if len(title) > 20 and title not in seen and ("/duyuru" in href or "/bilgi" in href or "/haber" in href):
                        seen.add(title)
                        full_url = href if href.startswith("http") else f"https://www.dpb.gov.tr{href}"
                        results.append({
                            "title": f"📋 {title}",
                            "institution": "T.C. Devlet Personel Başkanlığı (DPB)",
                            "category": "MEVZUAT",
                            "summary": f"DPB resmi görüş veya mevzuat duyurusu: {title}. Kamu personel kanunu uygulamaları ve güncel yorumlar.",
                            "content": title,
                            "source_name": "Devlet Personel Başkanlığı",
                            "source_url": full_url,
                            "publish_date": datetime.utcnow()
                        })
                        if len(results) >= 8:
                            break
        except Exception as e:
            logger.warning(f"DPB kazıma istisnası: {e}")
        return results


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
