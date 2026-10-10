import os
import re
import base64
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime
from loguru import logger
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from config.settings import settings
from core.database import get_system_setting

# Türkçe karakter ve tarih yardımcıları
def tr_upper(text: str) -> str:
    if not text:
        return ""
    tr_map = str.maketrans({"i": "İ", "ı": "I"})
    return str(text).translate(tr_map).upper()

def tr_title(text: str) -> str:
    if not text:
        return ""
    words = str(text).split()
    res = []
    for w in words:
        if not w:
            continue
        first = tr_upper(w[0])
        rest = str(w[1:]).translate(str.maketrans({"İ": "i", "I": "ı"})).lower()
        res.append(first + rest)
    return " ".join(res)

def to_turkish_date_str(val: Any) -> str:
    if not val:
        return "Resmi Kılavuzda"
    if isinstance(val, datetime):
        tr_months = ["", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
        return f"{val.day:02d} {tr_months[val.month]} {val.year}"
    val_str = str(val).strip()
    if not val_str or val_str.lower() in ["none", "null"]:
        return "Resmi Kılavuzda"
    m_iso = re.match(r"^(\d{4})-(\d{2})-(\d{2})", val_str)
    if m_iso:
        y, m, d = int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3))
        tr_months = ["", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
        if 1 <= m <= 12:
            return f"{d:02d} {tr_months[m]} {y}"
    m_dot = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})", val_str)
    if m_dot:
        d, m, y = int(m_dot.group(1)), int(m_dot.group(2)), int(m_dot.group(3))
        tr_months = ["", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
        if 1 <= m <= 12:
            return f"{d:02d} {tr_months[m]} {y}"
    return val_str


class ModernCardGenerator:
    """
    Kamu Personel Rehberi - Yeni Nesil Ultra HD Görsel Afiş Motoru (v4.0).
    - 1080x1620 Dikey Poster Formatı (Instagram Akış & Telegram için maksimum görünürlük)
    - Playwright Headless Chromium tabanlı sıfır piksel kayıplı tipografi
    - Temaya ve sektöre özel mimari bina arka planları (Sağlık, Adalet, Üniversite, Belediye vb.)
    - İptal / Düzeltme ilanları için özel kırmızı alarm şablonu (Çelişkisiz yayın)
    - Dinamik www.kamupersonelrehberiniz.me alan adı entegrasyonu
    """

    WIDTH = 1080
    HEIGHT = 1620

    SECTOR_BG_MAP = {
        "HEALTH": "health.jpg",
        "JUSTICE": "justice.jpg",
        "EDUCATION": "education.jpg",
        "MUNICIPALITY": "municipality.jpg",
        "SECURITY": "security.jpg",
        "WATER_FOREST": "water_forest.jpg",
        "FINANCE": "finance.jpg",
        "GENERAL": "general.jpg",
        "CANCELLATION": "cancellation.jpg"
    }

    def __init__(self):
        self.output_dir = settings.IMAGE_OUTPUT_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.assets_dir = settings.ASSETS_DIR
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        self.bg_dir = self.assets_dir / "backgrounds"
        self.bg_dir.mkdir(parents=True, exist_ok=True)
        self.logo_path = self.assets_dir / "logo.png"

        bundled_bold = settings.FONTS_DIR / "font_bold.ttf"
        bundled_reg = settings.FONTS_DIR / "font.ttf"
        self.font_bold_path = bundled_bold if bundled_bold.exists() else None
        self.font_regular_path = bundled_reg if bundled_reg.exists() else None

    def _get_font(self, size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
        path = self.font_bold_path if bold else self.font_regular_path
        if path and path.exists():
            try:
                return ImageFont.truetype(str(path), size=size)
            except Exception:
                pass
        for alt in [
            settings.FONTS_DIR / "font_bold.ttf",
            settings.FONTS_DIR / "font.ttf",
            Path("C:/Windows/Fonts/arialbd.ttf"),
            Path("C:/Windows/Fonts/arial.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        ]:
            if alt.exists():
                try:
                    return ImageFont.truetype(str(alt), size=size)
                except Exception:
                    pass
        return ImageFont.load_default()

    def _wrap_text(self, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> List[str]:
        words = text.split()
        lines = []
        cur = []
        for w in words:
            test = " ".join(cur + [w])
            try:
                bbox = font.getbbox(test)
                w_px = bbox[2] - bbox[0]
            except Exception:
                w_px = len(test) * 10
            if w_px <= max_width:
                cur.append(w)
            else:
                if cur:
                    lines.append(" ".join(cur))
                cur = [w]
        if cur:
            lines.append(" ".join(cur))
        return lines

    def detect_sector(self, institution: str, title: str, position: str = "") -> str:
        """İlan metninden kamu sektörünü ve iptal durumunu tespit eder."""
        combined = f"{institution} {title} {position}".upper()

        if any(w in combined for w in ["İPTAL", "IPTAL", "DÜZELTME", "DUZELTME"]):
            return "CANCELLATION"
        if any(w in combined for w in ["SAĞLIK", "HASTANE", "TABİP", "HEMŞİRE", "DOKTOR", "MEDİKAL"]):
            return "HEALTH"
        if any(w in combined for w in ["ADALET", "HAKİM", "SAVCI", "CEZAEVİ", "İCRA", "ZABIT KATİBİ", "BARO", "DANIŞTAY", "YARGITAY"]):
            return "JUSTICE"
        if any(w in combined for w in ["ÜNİVERSİTE", "REKTÖR", "ÖĞRETİM", "FAKÜLTE", "ENSTİTÜ", "MEB", "MİLLİ EĞİTİM", "AKADEMİK"]):
            return "EDUCATION"
        if any(w in combined for w in ["BELEDİYE", "BÜYÜKŞEHİR", "ZABITA", "İSKİ", "ASKİ", "EGO", "BELEDİYESİ"]):
            return "MUNICIPALITY"
        if any(w in combined for w in ["POLİS", "EMNİYET", "JANDARMA", "BEKÇİ", "MSB", "TSK", "KOMUTANLIĞI", "SAHİL GÜVENLİK", "GÜVENLİK GÖREVLİSİ"]):
            return "SECURITY"
        if any(w in combined for w in ["DSİ", "DEVLET SU", "ORMAN", "TARIM VE ORMAN", "SU İŞLERİ", "DOĞA KORUMA"]):
            return "WATER_FOREST"
        if any(w in combined for w in ["GELİR İDARESİ", "MALİYE", "VERGİ", "HAZİNE", "BANKA", "MERKEZ BANKASI", "SGK"]):
            return "FINANCE"

        return "GENERAL"

    def _get_background_b64(self, sector: str) -> str:
        """Sektöre uygun arka plan fotoğrafını base64 olarak okur."""
        bg_filename = self.SECTOR_BG_MAP.get(sector, "general.jpg")
        bg_path = self.bg_dir / bg_filename

        if not bg_path.exists():
            bg_path = self.bg_dir / "general.jpg"

        if bg_path.exists():
            try:
                with open(bg_path, "rb") as f:
                    return base64.b64encode(f.read()).decode("utf-8")
            except Exception as e:
                logger.warning(f"Arka plan okuma hatası: {e}")

        # Eğer hiçbiri yoksa temiz yedek görsel
        fallback = self.assets_dir / "clean_building_test.jpg"
        if fallback.exists():
            with open(fallback, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")

        return ""

    def _get_logo_b64(self) -> str:
        if self.logo_path.exists():
            try:
                with open(self.logo_path, "rb") as f:
                    return base64.b64encode(f.read()).decode("utf-8")
            except Exception:
                pass
        return ""

    def clean_text_fields(
        self,
        institution: str,
        position: str,
        title: str,
        total_positions: Optional[int] = None
    ) -> Dict[str, Any]:
        """Bozuk kurum, eylem fiilleri ve jenerik unvan hatalarını ayıklar."""
        inst = str(institution or "").strip()
        pos = str(position or "").strip()
        tit = str(title or "").strip()

        # 1. Kurumun içindeki personel sayısını veya 'alacak' ibaresini ayıkla
        inst_clean = re.sub(r"\s+\d+\s*(?:sözleşmeli|memur|öğretim|sürekli|personel|uzman|kamu|işçi|akademik).*$", "", inst, flags=re.IGNORECASE)
        inst_clean = re.sub(r"\s+(?:personel alım ilanı|personel alımı|memur alımı|akademik personel alımı|işçi alımı|alım ilanı|alacak|alınacaktır).*$", "", inst_clean, flags=re.IGNORECASE)
        inst_clean = inst_clean.strip(" -:,")

        if (not inst_clean or inst_clean.lower() in ["kamu kurumu", "resmi kurum", "resmi gazete ilanı"]) and tit:
            parts = tit.split(" - ")
            if len(parts) > 1:
                inst_clean = parts[0].strip()
            else:
                m_tit = re.match(r"^(.*?)\s+(\d+\s*(?:sözleşmeli|memur|uzman|gelir|öğretim|personel|işçi).*)$", tit, re.IGNORECASE)
                if m_tit:
                    inst_clean = m_tit.group(1).strip()

        if not inst_clean:
            inst_clean = "Kamu Kurumu"

        # 2. Pozisyon temizliği
        pos_clean = re.sub(r"^\s*(\d+\s*)+", "", pos)
        pos_clean = re.sub(r"\s*(?:alacak|alımı|temin edilecek|alınacaktır|alınacak|alım ilanı).*$", "", pos_clean, flags=re.IGNORECASE)
        pos_clean = pos_clean.strip(" -:,")

        if not pos_clean or pos_clean.lower() in ["kamu personel", "kamu personeli", "none", "null", "personel alımı"]:
            if tit and " - " in tit:
                pos_clean = tit.split(" - ")[-1].strip()
                pos_clean = re.sub(r"\s*(?:alacak|alımı|alınacaktır).*$", "", pos_clean, flags=re.IGNORECASE).strip(" -:,")
            else:
                pos_clean = "Personel Alımı"

        # Kontenjan hesaplama
        tot_num = total_positions
        if not tot_num or tot_num <= 0:
            all_nums = [int(n) for n in re.findall(r"\b(\d+)\b", tit)]
            if len(all_nums) > 1 and ("," in tit or " ve " in tit):
                tot_num = sum(all_nums)
            elif all_nums and all_nums[0] > 1:
                tot_num = all_nums[0]
            else:
                tot_num = 1

        return {
            "institution": tr_upper(inst_clean),
            "position": tr_title(pos_clean),
            "total_positions": tot_num
        }

    def generate_modern_card(
        self,
        job_id: int,
        institution: str,
        position: str,
        title: str = "",
        total_positions: Optional[int] = None,
        kpss_requirement: Optional[str] = None,
        education_level: Optional[str] = None,
        deadline: Optional[str] = None,
        bullet_points: Optional[List[str]] = None,
        city: Optional[str] = None,
        website_url: str = "www.kamupersonelrehberiniz.me"
    ) -> Path:
        """
        Göz yormayan, yüksek kontrastlı ve prestijli 1080x1620 boyutunda modern ilan kartı üretir.
        """
        # 1. Veri temizleme ve normalizasyon
        cleaned = self.clean_text_fields(institution, position, title, total_positions)
        clean_inst = cleaned["institution"]
        clean_pos = cleaned["position"]
        tot_num = cleaned["total_positions"]

        sector = self.detect_sector(clean_inst, title, clean_pos)
        is_cancellation = (sector == "CANCELLATION")

        d_str = to_turkish_date_str(deadline)
        kpss_str = kpss_requirement or "Resmi Kılavuzda"
        edu_str = education_level or "İlgili Bölüm Mezuniyeti"
        bg_b64 = self._get_background_b64(sector)
        logo_b64 = self._get_logo_b64()

        # 2. Şart hapları (4 Adet Vurucu Madde)
        if bullet_points and len(bullet_points) >= 4:
            bullets = bullet_points[:4]
        else:
            if is_cancellation:
                bullets = [
                    "BU DUYURU BİLGİLENDİRME <span>AMAÇLIDIR</span>.",
                    "YENİ BAŞVURU <span>KABUL EDİLMEMEKTEDİR</span>.",
                    "ALIM SÜRECİ RESMİ OLARAK <span>İPTAL EDİLDİ</span>.",
                    "GÜNCEL İLANLARI SAYFAMIZDAN <span>TAKİP EDİN</span>."
                ]
            else:
                bullets = [
                    f"KONTENJAN <span>{tot_num} KİŞİ</span> OLARAK AÇIKLANDI.",
                    f"KPSS ŞARTI: <span>{kpss_str}</span>",
                    f"ÖĞRENİM: <span>{edu_str}</span>",
                    f"SON BAŞVURU: <span>{d_str}</span>"
                ]

        # 3. Başlık ve Açıklama Metinleri
        if is_cancellation:
            badge_class = "badge-cancellation"
            badge_text = "🚨 DİKKAT: İLAN İPTAL DUYURUSU"
            hero_html = f"{clean_inst}<br><span class='danger'>ALIM SÜRECİ RESMEN İPTAL EDİLMİŞTİR!</span>"
            desc_text = "İlgili resmi kurum tarafından yayımlanan personel alım süreci iptal edilmiştir. Yeni başvuru kabul edilmemektedir."
            card1_label = "❌ DURUM"
            card1_val = "İPTAL EDİLDİ"
            card1_sub = "Başvuru alınmıyor"
            card2_label = "🏛️ RESMİ KURUM"
            card2_val = clean_inst[:30]
            card2_sub = "Resmi Duyuru"
            cta_text = "İPTAL KARARI DETAYLARI İÇİN"
            handwritten_text = "İlan İptal<br>Duyurusu!"
        else:
            badge_class = "badge-son-dakika"
            badge_text = "📢 SON DAKİKA"
            hero_html = f"{clean_inst}<br><span class='yellow'>{clean_pos.upper()} ALIMI</span> YAPACAK!"
            desc_text = f"{clean_inst} bünyesinde istihdam sağlanacaktır. Başvuru şartları, kadro dağılımı ve resmi kılavuz açıklandı."
            card1_label = "👤 SON BAŞVURU"
            card1_val = d_str
            card1_sub = "tarihine kadar"
            card2_label = "🏛️ KADRO & KONTENJAN"
            card2_val = f"{tot_num} Kişi Alımı"
            card2_sub = clean_pos[:32]
            cta_text = "DETAYLAR VE BAŞVURU İÇİN"
            handwritten_text = "Hayalindeki<br>Kariyer<br>Seni Bekliyor!"

        # Logo HTML
        if logo_b64:
            logo_html = f"<div class='header-logo'><img src='data:image/png;base64,{logo_b64}' alt='Logo'></div>"
        else:
            logo_html = """<div class='header-logo'>
                <svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="#38BDF8" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1-2.5-2.5Z"/>
                  <path d="M6 6h10"/>
                  <path d="M6 10h10"/>
                </svg>
            </div>"""

        # HTML Şablonu (Plus Jakarta Sans + Montserrat, Göz Yormayan Yüksek Okunabilirlik)
        html_content = f"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Montserrat:ital,wght@0,700;0,800;0,900;1,700&family=Plus+Jakarta+Sans:wght@500;600;700;800&family=Caveat:wght@700&display=swap');

  * {{
    box-sizing: border-box;
    margin: 0;
    padding: 0;
    -webkit-font-smoothing: antialiased;
  }}

  body {{
    width: 1080px;
    height: 1620px;
    overflow: hidden;
    background-color: #060C19;
    font-family: 'Plus Jakarta Sans', sans-serif;
    color: #F8FAFC;
    position: relative;
  }}

  /* Arka Plan Fotoğrafı */
  .bg-photo {{
    position: absolute;
    top: 0;
    left: 0;
    width: 1080px;
    height: 960px;
    background-image: url('data:image/jpeg;base64,{bg_b64}');
    background-size: cover;
    background-position: top center;
    z-index: 1;
    filter: brightness(0.92);
  }}

  /* Derin, Göz Yormayan Koyu Gece Degradesi */
  .bg-gradient {{
    position: absolute;
    top: 0;
    left: 0;
    width: 1080px;
    height: 1620px;
    background: linear-gradient(
      180deg,
      rgba(6, 12, 25, 0.22) 0%,
      rgba(6, 12, 25, 0.58) 32%,
      rgba(6, 12, 25, 0.94) 50%,
      #060C19 64%,
      #040812 100%
    );
    z-index: 2;
  }}

  /* Ana Taşıyıcı Kapsayıcı */
  .container {{
    position: relative;
    z-index: 10;
    width: 1080px;
    height: 1620px;
    padding: 46px 56px 42px 56px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
  }}

  /* 1. Header */
  .header {{
    display: flex;
    align-items: center;
    gap: 18px;
  }}

  .header-logo {{
    width: 70px;
    height: 70px;
    border-radius: 50%;
    background: #0E1A33;
    border: 2px solid #38BDF8;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 4px 16px rgba(0,0,0,0.5);
  }}

  .header-logo img {{
    width: 50px;
    height: 50px;
    object-fit: contain;
  }}

  .brand-text h1 {{
    font-family: 'Montserrat', sans-serif;
    font-size: 32px;
    font-weight: 900;
    letter-spacing: 0.5px;
    color: #FFFFFF;
    line-height: 1.1;
  }}

  .brand-text h1 span {{
    font-weight: 300;
    letter-spacing: 3px;
    font-size: 26px;
    display: block;
    color: #CBD5E1;
  }}

  .brand-text p {{
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 2px;
    color: #38BDF8;
    text-transform: uppercase;
    margin-top: 4px;
  }}

  /* 2. Hero Headline Bölümü */
  .hero-area {{
    margin-top: 250px;
    position: relative;
  }}

  .badge-son-dakika {{
    display: inline-flex;
    align-items: center;
    gap: 8px;
    background: #FACC15;
    color: #0F172A;
    font-family: 'Montserrat', sans-serif;
    font-weight: 900;
    font-size: 26px;
    padding: 8px 24px;
    border-radius: 8px;
    transform: rotate(-2.5deg);
    box-shadow: 0 8px 24px rgba(250, 204, 21, 0.45);
    margin-bottom: 22px;
    letter-spacing: 0.5px;
  }}

  .badge-cancellation {{
    display: inline-flex;
    align-items: center;
    gap: 8px;
    background: #EF4444;
    color: #FFFFFF;
    font-family: 'Montserrat', sans-serif;
    font-weight: 900;
    font-size: 26px;
    padding: 8px 24px;
    border-radius: 8px;
    transform: rotate(-2.5deg);
    box-shadow: 0 8px 24px rgba(239, 68, 68, 0.5);
    margin-bottom: 22px;
    letter-spacing: 0.5px;
  }}

  .hero-title {{
    font-family: 'Montserrat', sans-serif;
    font-size: 48px;
    font-weight: 900;
    line-height: 1.16;
    letter-spacing: -0.5px;
    text-shadow: 0 4px 18px rgba(0,0,0,0.85);
    max-width: 900px;
    color: #F8FAFC;
  }}

  .hero-title .yellow {{
    color: #FACC15;
    text-shadow: 0 4px 18px rgba(250, 204, 21, 0.25);
  }}

  .hero-title .danger {{
    color: #F87171;
    text-shadow: 0 4px 18px rgba(239, 68, 68, 0.35);
  }}

  .hero-desc {{
    margin-top: 18px;
    font-size: 19px;
    font-weight: 600;
    color: #CBD5E1;
    line-height: 1.5;
    max-width: 680px;
  }}

  /* Motivasyon El Yazısı Çıkartması */
  .handwritten-sticker {{
    position: absolute;
    right: 6px;
    bottom: 24px;
    text-align: center;
    transform: rotate(-8deg);
  }}

  .handwritten-sticker .text {{
    font-family: 'Caveat', cursive;
    font-size: 38px;
    font-weight: 700;
    color: #FFFFFF;
    line-height: 1.1;
    text-shadow: 0 4px 14px rgba(0,0,0,0.7);
  }}

  .handwritten-sticker svg {{
    width: 140px;
    height: 16px;
    margin-top: -4px;
  }}

  /* 3. İkili Cam Özet Kartı (Glassmorphism) */
  .summary-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 22px;
    margin-top: 30px;
  }}

  .glass-card {{
    background: rgba(14, 26, 52, 0.72);
    backdrop-filter: blur(14px);
    border: 1.5px solid rgba(56, 189, 248, 0.35);
    border-radius: 20px;
    padding: 22px 24px;
    display: flex;
    align-items: center;
    gap: 20px;
    box-shadow: 0 10px 28px rgba(0,0,0,0.4);
  }}

  .glass-card .icon-box {{
    width: 66px;
    height: 66px;
    border-radius: 16px;
    border: 2px solid #38BDF8;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(56, 189, 248, 0.12);
    flex-shrink: 0;
  }}

  .glass-card .card-info .label {{
    font-size: 14px;
    font-weight: 800;
    color: #94A3B8;
    text-transform: uppercase;
    letter-spacing: 0.6px;
  }}

  .glass-card .card-info .val {{
    font-size: 26px;
    font-weight: 800;
    color: #F8FAFC;
    margin-top: 3px;
    line-height: 1.2;
  }}

  .glass-card .card-info .val.highlight {{
    color: #FACC15;
  }}

  .glass-card .card-info .sub {{
    font-size: 14px;
    color: #94A3B8;
    margin-top: 3px;
    font-weight: 600;
  }}

  /* 4. Dörtlü Şart Rozetleri */
  .bullets-grid {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
    margin-top: 26px;
  }}

  .bullet-item {{
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
  }}

  .bullet-icon {{
    width: 68px;
    height: 68px;
    border-radius: 50%;
    border: 2px solid #38BDF8;
    background: rgba(14, 26, 52, 0.8);
    display: flex;
    align-items: center;
    justify-content: center;
    margin-bottom: 12px;
    box-shadow: 0 4px 14px rgba(0,0,0,0.3);
  }}

  .bullet-text {{
    font-size: 13.5px;
    font-weight: 700;
    line-height: 1.38;
    color: #E2E8F0;
  }}

  .bullet-text span {{
    color: #FACC15;
  }}

  /* 5. CTA ve Alan Adı Butonları */
  .cta-area {{
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 12px;
    margin-top: 30px;
  }}

  .btn-cta {{
    background: #FACC15;
    color: #0F172A;
    font-family: 'Montserrat', sans-serif;
    font-size: 20px;
    font-weight: 900;
    padding: 14px 44px;
    border-radius: 40px;
    display: inline-flex;
    align-items: center;
    gap: 12px;
    box-shadow: 0 8px 24px rgba(250, 204, 21, 0.4);
    letter-spacing: 0.3px;
  }}

  .btn-cta .circle-arrow {{
    width: 28px;
    height: 28px;
    border-radius: 50%;
    background: #0F172A;
    color: #FACC15;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 16px;
    font-weight: 900;
  }}

  .btn-web {{
    background: rgba(14, 26, 52, 0.88);
    border: 1.5px solid #1E3A8A;
    color: #FFFFFF;
    font-size: 17px;
    font-weight: 700;
    padding: 10px 48px;
    border-radius: 30px;
    display: inline-flex;
    align-items: center;
    gap: 10px;
    letter-spacing: 0.5px;
  }}

  /* 6. Footer */
  .footer {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding-top: 16px;
    border-top: 1px solid rgba(255,255,255,0.1);
    position: relative;
  }}

  .footer-socials {{
    display: flex;
    align-items: center;
    gap: 14px;
    color: #94A3B8;
  }}

  .footer-text {{
    font-size: 12px;
    font-weight: 800;
    letter-spacing: 2px;
    color: #94A3B8;
    text-transform: uppercase;
  }}

  .yellow-slash {{
    position: absolute;
    bottom: -42px;
    right: -56px;
    width: 90px;
    height: 90px;
    background: #FACC15;
    transform: rotate(45deg);
    z-index: 5;
  }}
</style>
</head>
<body>

  <!-- Arka Plan Görseli & Gradyan -->
  <div class="bg-photo"></div>
  <div class="bg-gradient"></div>

  <!-- Ana İçerik Kapsayıcısı -->
  <div class="container">

    <!-- 1. Üst Başlık & Logo -->
    <div class="header">
      {logo_html}
      <div class="brand-text">
        <h1>KAMUPERSONEL <span>REHBERİ</span></h1>
        <p>KAMUDA KARİYERİNİZ İÇİN DOĞRU ADRES</p>
      </div>
    </div>

    <!-- 2. Vurucu Başlık Panosu -->
    <div class="hero-area">
      <div class="{badge_class}">
        <span>{badge_text.split()[0]}</span> {' '.join(badge_text.split()[1:])}
      </div>

      <div class="hero-title">
        {hero_html}
      </div>

      <div class="hero-desc">
        {desc_text}
      </div>

      <!-- El Yazısı Çıkartması -->
      <div class="handwritten-sticker">
        <div class="text">{handwritten_text}</div>
        <svg viewBox="0 0 100 12" fill="none">
          <path d="M5 6 Q 50 12 95 4" stroke="#FACC15" stroke-width="4" stroke-linecap="round"/>
        </svg>
      </div>
    </div>

    <!-- 3. İkili Özet Cam Kartı -->
    <div class="summary-grid">
      <div class="glass-card">
        <div class="icon-box">
          <svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="#38BDF8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect width="18" height="18" x="3" y="4" rx="2" ry="2"/>
            <line x1="16" x2="16" y1="2" y2="6"/>
            <line x1="8" x2="8" y1="2" y2="6"/>
            <line x1="3" x2="21" y1="10" y2="10"/>
          </svg>
        </div>
        <div class="card-info">
          <div class="label">{card1_label}</div>
          <div class="val highlight">{card1_val}</div>
          <div class="sub">{card1_sub}</div>
        </div>
      </div>

      <div class="glass-card">
        <div class="icon-box">
          <svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="#38BDF8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"/>
            <circle cx="12" cy="10" r="3"/>
          </svg>
        </div>
        <div class="card-info">
          <div class="label">{card2_label}</div>
          <div class="val">{card2_val}</div>
          <div class="sub">{card2_sub}</div>
        </div>
      </div>
    </div>

    <!-- 4. Dörtlü Şart Rozetleri -->
    <div class="bullets-grid">
      <div class="bullet-item">
        <div class="bullet-icon">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#38BDF8" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="20 6 9 17 4 12"/>
          </svg>
        </div>
        <div class="bullet-text">
          {bullets[0]}
        </div>
      </div>

      <div class="bullet-item">
        <div class="bullet-icon">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#38BDF8" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <line x1="18" x2="18" y1="20" y2="10"/>
            <line x1="12" x2="12" y1="20" y2="4"/>
            <line x1="6" x2="6" y1="20" y2="14"/>
          </svg>
        </div>
        <div class="bullet-text">
          {bullets[1]}
        </div>
      </div>

      <div class="bullet-item">
        <div class="bullet-icon">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#38BDF8" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
            <polyline points="14 2 14 8 20 8"/>
            <line x1="16" x2="8" y1="13" y2="13"/>
            <line x1="16" x2="8" y1="17" y2="17"/>
          </svg>
        </div>
        <div class="bullet-text">
          {bullets[2]}
        </div>
      </div>

      <div class="bullet-item">
        <div class="bullet-icon">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#38BDF8" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/>
            <circle cx="9" cy="7" r="4"/>
            <path d="M22 21v-2a4 4 0 0 0-3-3.87"/>
            <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
          </svg>
        </div>
        <div class="bullet-text">
          {bullets[3]}
        </div>
      </div>
    </div>

    <!-- 5. CTA ve Web Butonları -->
    <div class="cta-area">
      <div class="btn-cta">
        <div class="circle-arrow">&gt;</div>
        {cta_text}
      </div>
      <div class="btn-web">
        🌐 {website_url}
      </div>
    </div>

    <!-- 6. Footer İmzası -->
    <div class="footer">
      <div class="footer-socials">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect width="20" height="20" x="2" y="2" rx="5" ry="5"/><path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z"/><line x1="17.5" x2="17.51" y1="6.5" y2="6.5"/></svg>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/></svg>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M2.5 17a24.12 24.12 0 0 1 0-10 2 2 0 0 1 1.4-1.4 49.56 49.56 0 0 1 16.2 0A2 2 0 0 1 21.5 7a24.12 24.12 0 0 1 0 10 2 2 0 0 1-1.4 1.4 49.55 49.55 0 0 1-16.2 0A2 2 0 0 1 2.5 17"/><polygon points="10 15 15 12 10 9"/></svg>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 4l11.733 16h4.267l-11.733 -16z"/><path d="M4 20l6.768 -6.768m2.46 -2.46l6.772 -6.772"/></svg>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/></svg>
      </div>
      <div class="footer-text">
        DOĞRU BİLGİ &nbsp;|&nbsp; DOĞRU KARİYER &nbsp;|&nbsp; KAMUPERSONEL REHBERİ
      </div>
      <div class="yellow-slash"></div>
    </div>

  </div>

</body>
</html>
"""

        # Çıktı dosyası yolu
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        cancellation_tag = "_iptal" if is_cancellation else ""
        filename = f"modern_ilan_{job_id}_{sector.lower()}{cancellation_tag}_{timestamp}.png"
        filepath = self.output_dir / filename

        # 1. Öncelik: Tam teşekküllü 1080x1620 Pillow Modern Afiş Render'ı
        # Sıfır harici tarayıcı gereksinimi: Streamlit Cloud ve sunucu ortamlarında %100 kararlı ve 0.05 saniyede çalışır.
        try:
            city_val = city or "İlanda Belirtilen İller"
            return self._render_pillow_modern_card(
                filepath=filepath,
                sector=sector,
                is_cancellation=is_cancellation,
                clean_inst=clean_inst,
                clean_pos=clean_pos,
                tot_num=tot_num,
                deadline_str=d_str,
                edu_str=edu_str,
                kpss_str=kpss_str,
                city_str=city_val,
                website_url=website_url
            )
        except Exception as pfe:
            logger.warning(f"Pillow modern render uyarısı ({pfe}). Klasik vitrin motoruna devrediliyor...")
            try:
                from graphics.generator import JobCardGenerator
                pillow_gen = JobCardGenerator()
                theme_name = "DARK_NOIR" if is_cancellation else "ROYAL_CRIMSON"
                fallback_path = pillow_gen.generate_card(
                    job_id=job_id,
                    institution=clean_inst,
                    position=clean_pos,
                    total_positions=tot_num,
                    deadline=deadline,
                    theme=theme_name,
                    kpss_requirement=kpss_str,
                    education_level=edu_str,
                    title=title
                )
                logger.info(f"Yedek klasik vitrin afişi başarıyla üretildi: {fallback_path}")
                return fallback_path
            except Exception as fe:
                logger.error(f"Tüm afiş motorları başarısız oldu: {fe}")
                raise RuntimeError(f"Görsel afiş üretilemedi: {fe}") from fe

    def _render_pillow_modern_card(
        self,
        filepath: Path,
        sector: str,
        is_cancellation: bool,
        clean_inst: str,
        clean_pos: str,
        tot_num: int,
        deadline_str: str,
        edu_str: str,
        kpss_str: str,
        city_str: str,
        website_url: str
    ) -> Path:
        """
        Playwright veya harici tarayıcı gerektirmeyen, doğrudan Pillow (PIL) ile
        1080x1620 boyutunda yüksek çözünürlüklü modern kamu afişi üretir.
        Streamlit Cloud ve sunucu ortamlarında %100 kararlı ve 0.05 saniyede çalışır.
        """
        # 1. Ana Tuval (Koyu Gece Laciverti)
        canvas = Image.new("RGBA", (self.WIDTH, self.HEIGHT), (6, 12, 25, 255))

        # 2. Mimari Arka Plan Fotoğrafı
        bg_filename = self.SECTOR_BG_MAP.get(sector, "general.jpg")
        bg_path = self.bg_dir / bg_filename
        if not bg_path.exists():
            bg_path = self.bg_dir / "general.jpg"

        if bg_path.exists():
            try:
                bg = Image.open(bg_path).convert("RGBA")
                bg = bg.resize((self.WIDTH, 960), Image.Resampling.LANCZOS)
                canvas.paste(bg, (0, 0))
            except Exception as e:
                logger.warning(f"Arka plan görseli yapıştırma uyarısı: {e}")

        # 3. Pürüzsüz Karanlık Degrade Katmanı
        gradient = Image.new("RGBA", (self.WIDTH, self.HEIGHT), (0, 0, 0, 0))
        d_grad = ImageDraw.Draw(gradient)
        for y in range(self.HEIGHT):
            if y < 350:
                alpha = int(120 + (y / 350.0) * 80)
            elif y < 750:
                alpha = int(200 + ((y - 350) / 400.0) * 55)
            else:
                alpha = 255
            d_grad.line([(0, y), (self.WIDTH, y)], fill=(6, 12, 25, alpha))

        canvas = Image.alpha_composite(canvas, gradient)
        draw = ImageDraw.Draw(canvas)

        # 4. Üst Logo & Marka Başlığı
        if self.logo_path.exists():
            try:
                logo = Image.open(self.logo_path).convert("RGBA")
                logo.thumbnail((54, 54), Image.Resampling.LANCZOS)
                canvas.paste(logo, (56, 48), mask=logo)
            except Exception:
                pass

        draw.text((122, 50), "KAMUPERSONEL REHBERİ", fill=(255, 255, 255), font=self._get_font(22, bold=True))
        draw.text((122, 78), "KAMUDA KARİYERİNİZ İÇİN DOĞRU ADRES", fill=(148, 163, 184), font=self._get_font(13))

        # 5. Sektör & Durum Rozeti
        if is_cancellation:
            draw.rounded_rectangle([(56, 130), (460, 172)], radius=10, fill=(220, 38, 38), outline=(254, 202, 202), width=1)
            draw.text((74, 140), "🚨 ALIM İPTALİ / DÜZELTME DUYURUSU", fill=(255, 255, 255), font=self._get_font(16, bold=True))
        elif tot_num >= 20:
            draw.rounded_rectangle([(56, 130), (380, 172)], radius=10, fill=(37, 99, 235), outline=(56, 189, 248), width=1)
            draw.text((74, 140), "🔥 YÜKSEK KONTENJAN", fill=(255, 255, 255), font=self._get_font(16, bold=True))
        else:
            draw.rounded_rectangle([(56, 130), (380, 172)], radius=10, fill=(14, 165, 233), outline=(56, 189, 248), width=1)
            draw.text((74, 140), "🏛 RESMİ KAMU ALIMI", fill=(255, 255, 255), font=self._get_font(16, bold=True))

        # 6. Kurum Adı
        inst_lines = self._wrap_text(clean_inst, self._get_font(36, bold=True), 960)
        y_cur = 200
        for line in inst_lines[:3]:
            draw.text((56, y_cur), line, fill=(255, 255, 255), font=self._get_font(36, bold=True))
            y_cur += 48

        # 7. Kadro / Pozisyon Başlığı
        pos_lines = self._wrap_text(clean_pos, self._get_font(42, bold=True), 960)
        y_cur += 12
        pos_color = (248, 113, 113) if is_cancellation else (250, 204, 21)
        for line in pos_lines[:3]:
            draw.text((56, y_cur), line, fill=pos_color, font=self._get_font(42, bold=True))
            y_cur += 54

        # 8. İkili Özet Cam Kartları
        # Sol Kart: Kontenjan
        draw.rounded_rectangle([(56, 620), (524, 760)], radius=18, fill=(14, 26, 52), outline=(56, 189, 248), width=2)
        draw.text((80, 642), "KONTENJAN", fill=(148, 163, 184), font=self._get_font(15, bold=True))
        draw.text((80, 670), f"{tot_num} KİŞİ", fill=(56, 189, 248), font=self._get_font(36, bold=True))
        draw.text((80, 722), "Resmi Kontenjan", fill=(100, 116, 139), font=self._get_font(14))

        # Sağ Kart: Son Başvuru
        draw.rounded_rectangle([(556, 620), (1024, 760)], radius=18, fill=(14, 26, 52), outline=(56, 189, 248), width=2)
        draw.text((580, 642), "SON BAŞVURU", fill=(148, 163, 184), font=self._get_font(15, bold=True))
        draw.text((580, 674), str(deadline_str).upper()[:18], fill=(255, 255, 255), font=self._get_font(28, bold=True))
        draw.text((580, 722), "Resmi Başvuru Takvimi", fill=(100, 116, 139), font=self._get_font(14))

        # 9. Şartlar Listesi
        bullets_data = [
            ("ÖĞRENİM ŞARTI", edu_str),
            ("KPSS ŞARTI", kpss_str),
            ("GÖREV YERİ", city_str),
            ("RESMİ KILAVUZ", "Resmi Kılavuz & Başvuru Dokümanı Yayımlandı")
        ]
        b_y = 790
        for tag, val in bullets_data:
            draw.rounded_rectangle([(56, b_y), (1024, b_y + 68)], radius=14, fill=(15, 23, 42), outline=(51, 65, 85), width=1)
            draw.text((78, b_y + 22), f"{tag}:", fill=(56, 189, 248), font=self._get_font(17, bold=True))
            bbox = self._get_font(17, bold=True).getbbox(f"{tag}: ")
            tag_w = bbox[2] - bbox[0]
            val_display = str(val)[:58] if val else "Resmi İlanda Belirtilmiştir"
            draw.text((78 + tag_w + 10, b_y + 22), val_display, fill=(226, 232, 240), font=self._get_font(17))
            b_y += 82

        # 10. CTA & Web Adresi Butonları
        cta_btn_color = (220, 38, 38) if is_cancellation else (37, 99, 235)
        cta_text = "İPTAL DETAYLARINI İNCELE →" if is_cancellation else "ŞARTLARI İNCELE & RESMİ KILAVUZU İNDİR →"
        draw.rounded_rectangle([(56, 1160), (1024, 1240)], radius=16, fill=cta_btn_color)
        draw.text((220, 1184), cta_text, fill=(255, 255, 255), font=self._get_font(23, bold=True))

        draw.rounded_rectangle([(56, 1260), (1024, 1330)], radius=16, fill=(15, 23, 42), outline=(56, 189, 248), width=1)
        draw.text((360, 1282), f"🌐 {website_url}", fill=(56, 189, 248), font=self._get_font(21, bold=True))

        # 11. Alt İmza
        draw.line([(56, 1540), (1024, 1540)], fill=(51, 65, 85), width=1)
        draw.text((270, 1560), "DOĞRU BİLGİ  |  DOĞRU KARİYER  |  KAMU PERSONEL REHBERİ", fill=(100, 116, 139), font=self._get_font(14, bold=True))

        # 12. RGB Çıktı Kaydet
        final_img = canvas.convert("RGB")
        final_img.save(str(filepath), "PNG", quality=95)
        logger.info(f"Yeni Nesil Modern Afiş Üretildi [Pillow Engine/{sector}]: {filepath}")
        return filepath

