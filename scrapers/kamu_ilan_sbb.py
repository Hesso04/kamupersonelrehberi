import re
import io
import hashlib
from typing import List, Optional, Tuple
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from loguru import logger

from .base import BaseScraper, ScrapedJob

TURKISH_MONTHS = {
    "ocak": 1, "şubat": 2, "subat": 2, "mart": 3, "nisan": 4, "mayıs": 5, "mayis": 5,
    "haziran": 6, "temmuz": 7, "ağustos": 8, "agustos": 8, "eylül": 9, "eylul": 9,
    "ekim": 10, "kasım": 11, "kasim": 11, "aralık": 12, "aralik": 12
}


def parse_turkish_date_range(date_str: str) -> Tuple[Optional[datetime], Optional[datetime]]:
    """
    '2 Ekim - 16 Ekim' veya '20 Ekim - 22 Ekim' gibi metinleri
    datetime nesnelerine dönüştürür.
    """
    if not date_str or "-" not in date_str:
        return None, None

    now = datetime.now()
    parts = date_str.split("-")
    if len(parts) != 2:
        return None, None

    def parse_single(p_str: str) -> Optional[datetime]:
        p_str = p_str.strip().lower()
        match = re.search(r"(\d+)\s+([a-zçşğüöı]+)", p_str)
        if match:
            day = int(match.group(1))
            month_name = match.group(2)
            month = TURKISH_MONTHS.get(month_name)
            if month:
                year = now.year
                # Yıl sonu / başlangıcı geçiş kontrolü
                if now.month == 12 and month == 1:
                    year += 1
                try:
                    return datetime(year, month, day)
                except ValueError:
                    return None
        return None

    return parse_single(parts[0]), parse_single(parts[1])


class SBBKamuIlanScraper(BaseScraper):
    """
    T.C. Cumhurbaşkanlığı Strateji ve Bütçe Başkanlığı (SBB)
    Kamu İlan Portalı (kamuilan.sbb.gov.tr) Resmi Kazıyıcısı.

    ÖNEMLİ MİMARİ NOT:
    SBB kamuilan.sbb.gov.tr/ilanDetay.aspx?kod=... bağlantıları bir web sayfası DEĞİL,
    ASP.NET session/referer korumalı resmi PDF dokümanı indirme uç noktasıdır.
    Dışarıdan (Referer başlığı kamuilan.sbb.gov.tr olmadan) doğrudan tıklandığında
    SBB sunucusu '404 Aradığınız Sayfa Bulunamadı' hatası verir.
    Bu nedenle kazıyıcımız:
    1. Resmi kaynak bağlantısı (source_url) olarak 'https://kamuilan.sbb.gov.tr/' verir (Asla 404 vermez).
    2. Dahili belge bağlantısı (official_doc_url) olarak kodlu linki saklar.
    3. Referer başlığıyla resmi PDF dosyasını indirir, metnini ayrıştırır ve sisteme kaydeder.
    """

    BASE_URL = "https://kamuilan.sbb.gov.tr/"

    INSTITUTION_KEYWORDS = [
        "BELEDİYE BAŞKANLIĞI",
        "ÜNİVERSİTESİ",
        "BAKANLIĞI",
        "GENEL MÜDÜRLÜĞÜ",
        "BAŞKANLIĞI",
        "KALKINMA AJANSI",
        "KOMUTANLIĞI",
        "KURUMU",
        "MÜDÜRLÜĞÜ",
        "VALİLİĞİ",
        "KAYMAKAMLIĞI",
        "DAİRESİ BAŞKANLIĞI"
    ]

    def __init__(self):
        super().__init__(source_name="SBB Kamu İlan", timeout=25)
        self.doc_dir = Path("data/documents")
        self.doc_dir.mkdir(parents=True, exist_ok=True)

    def download_pdf(self, detail_url: str) -> Tuple[Optional[Path], Optional[str]]:
        """
        SBB ilanDetay.aspx adresinden Referer başlığıyla resmi PDF'i indirir,
        dosyayı yerel önbelleğe kaydeder ve metnini pypdf ile ayrıştırır.
        """
        try:
            url_hash = hashlib.md5(detail_url.encode()).hexdigest()[:12]
            pdf_filename = f"sbb_doc_{url_hash}.pdf"
            pdf_file_path = self.doc_dir / pdf_filename
            if pdf_file_path.exists() and pdf_file_path.stat().st_size > 500:
                return pdf_file_path, ""

            r = self.session.get(
                detail_url,
                verify=False,
                headers={"Referer": self.BASE_URL},
                timeout=20
            )
            if r.status_code == 200 and r.content.startswith(b"%PDF"):
                pdf_file_path.write_bytes(r.content)

                # PDF metin çıkarımı
                extracted_text = ""
                try:
                    from pypdf import PdfReader
                    reader = PdfReader(io.BytesIO(r.content))
                    for page in reader.pages[:4]:  # İlk 4 sayfadaki detayları al
                        t = page.extract_text()
                        if t:
                            extracted_text += t + "\n"
                except Exception as ex:
                    logger.debug(f"PDF metin okuma istisnası: {ex}")

                return pdf_file_path, extracted_text.strip()
        except Exception as e:
            logger.warning(f"SBB PDF indirme hatası ({detail_url[:60]}...): {e}")

        return None, None

    def fetch_jobs(self) -> List[ScrapedJob]:
        """SBB Kamu İlan portalındaki tüm aktif resmi duyuruları çeker."""
        jobs: List[ScrapedJob] = []
        try:
            response = self.session.get(self.BASE_URL, verify=False, timeout=self.timeout)
            if response.status_code != 200:
                logger.error(f"SBB portalı yanıt vermedi. Kod: {response.status_code}")
                return jobs

            # Sayfa içeriğini UTF-8 ile parse et
            html_content = response.content.decode("utf-8", "ignore")
            soup = BeautifulSoup(html_content, "html.parser")

            # Sayfadaki TÜM ilanDetay.aspx bağlantılarını topla
            all_links = soup.find_all("a", href=lambda h: h and "ilanDetay.aspx" in h)
            logger.info(f"SBB sayfasında toplam {len(all_links)} adet ilanDetay bağlantısı tespit edildi.")

            seen_urls = set()

            for a_tag in all_links:
                raw_href = a_tag["href"].strip()
                detail_url = urljoin(self.BASE_URL, raw_href)

                if detail_url in seen_urls:
                    continue
                seen_urls.add(detail_url)

                # 1. Metin çıkarımı
                full_text = a_tag.get_text(separator=" ", strip=True)
                if not full_text or len(full_text) < 5:
                    continue

                # İptal ilanlarını filtrele
                if "İPTAL İLANI" in full_text.upper():
                    continue

                # 2. Tarih aralığını yakala (Örn: "2 Ekim - 16 Ekim" veya "( 20 Ekim - 22 Ekim)")
                date_match = re.search(
                    r"\(?\s*(\d+\s+[A-Za-zÇŞĞÜÖİçşğüöı]+\s*-\s*\d+\s+[A-Za-zÇŞĞÜÖİçşğüöı]+)\s*\)?",
                    full_text
                )
                date_str = date_match.group(1).strip() if date_match else "İlanda belirtilmiştir"
                start_dt, end_dt = parse_turkish_date_range(date_str)

                # Başlık metninden tarihi temizle
                if date_match:
                    title_part = full_text[:date_match.start()].strip(" ()-")
                else:
                    title_part = full_text

                # Kelime yapışıklığını düzelt (Örn: ÜNİVERSİTESİ97 -> ÜNİVERSİTESİ 97)
                title_part = re.sub(r"([A-ZÇŞĞÜÖİa-zçşğüöı])(\d+)", r"\1 \2", title_part)

                # 3. Kurum adı, pozisyon ve kontenjanı ayrıştır
                parts = [p.strip() for p in title_part.split(" - ") if p.strip()]
                if len(parts) >= 2 and parts[0].upper() == parts[1].upper():
                    institution = parts[0]
                    remaining = " - ".join(parts[2:]) if len(parts) > 2 else parts[1]
                elif len(parts) >= 2:
                    institution = parts[0]
                    remaining = " - ".join(parts[1:])
                else:
                    institution = parts[0] if parts else "Kamu Kurumu"
                    remaining = parts[0] if parts else ""

                if remaining.upper().startswith(institution.upper()):
                    remaining = remaining[len(institution):].strip(" -:")

                # Kontenjan sayısını yakala
                all_nums = [int(n) for n in re.findall(r"\b(\d+)\b", remaining)]
                total_pos = sum(all_nums) if len(all_nums) > 1 and ("," in remaining or " ve " in remaining) else (all_nums[0] if all_nums else 1)

                # Temiz kadro / pozisyon adı
                pos_clean = re.sub(r"^\d+\s*", "", remaining)
                pos_clean = re.sub(r"\s*(?:alacak|alımı|temin edilecek|alınacaktır).*$", "", pos_clean, flags=re.IGNORECASE)
                pos_clean = pos_clean.strip(" -:,")
                if not pos_clean or len(pos_clean) < 3:
                    pos_clean = remaining or "Kamu Personeli"

                # Resmi PDF dosyasını önbellekten kontrol et veya indir
                pdf_path, _ = self.download_pdf(detail_url)

                # Temiz başlık
                clean_title = f"{institution} - {remaining}" if remaining else institution

                # Ham özet
                raw_summary = (
                    f"Kurum: {institution}\n"
                    f"Pozisyon / Kadro: {pos_clean}\n"
                    f"Kontenjan: {total_pos}\n"
                    f"Başvuru Tarihleri: {date_str}\n"
                    f"Son Başvuru Tarihi: {end_dt.strftime('%d.%m.%Y') if end_dt else 'İlan detayında'}\n"
                    f"Resmi Portal: {self.BASE_URL}\n"
                    f"Tam Başlık: {full_text}"
                )

                # 5. İlan Modeli
                job = ScrapedJob(
                    title=clean_title[:340],
                    source_name=self.source_name,
                    source_url=self.BASE_URL,
                    institution=institution[:240],
                    position=pos_clean[:290],
                    total_positions=total_pos,
                    official_doc_url=detail_url,
                    pdf_path=str(pdf_path) if pdf_path else None,
                    raw_content=raw_summary,
                    publish_date=end_dt or datetime.utcnow(),
                    is_verified=True  # kamuilan.sbb.gov.tr resmi devlet portalıdır
                )
                jobs.append(job)

            logger.info(f"SBB Kamu İlan portalından toplam {len(jobs)} adet benzersiz resmi ilan çekildi.")

        except Exception as e:
            logger.error(f"SBB Kamu İlan kazıma hatası: {e}")

        return jobs
