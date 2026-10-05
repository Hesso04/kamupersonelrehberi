"""
Kurumsal İlan Vitrini Grafik Motoru (v3.0 Ultra HD & High-Contrast Typography)
=============================================================================
Sosyal medya (Telegram, Instagram, Facebook) için yüksek çözünürlüklü (1080x1080),
maksimum okunabilirlik sağlayan, kusursuz Türkçe karakter desteğine ve akıllı
içerik ayrıştırma yeteneğine sahip resmi ilan kartı üretici motoru.
"""

import re
import os
import math
from pathlib import Path
from typing import Optional, Tuple, List, Any, Dict
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter
from loguru import logger
import qrcode

from config.settings import settings
from core.database import get_system_setting


# =============================================================================
# KUSURSUZ TÜRKÇE KARAKTER DÖNÜŞÜM YARDIMCILARI (İ, I, Ş, Ğ, Ü, Ö, Ç)
# =============================================================================
def tr_upper(text: str) -> str:
    """Türkçe küçük i -> büyük İ ve ı -> I kurallarını koruyarak büyük harfe dönüştürür."""
    if not text:
        return ""
    tr_map = str.maketrans({"i": "İ", "ı": "I"})
    return str(text).translate(tr_map).upper()


def tr_lower(text: str) -> str:
    """Türkçe büyük İ -> küçük i ve I -> ı kurallarını koruyarak küçük harfe dönüştürür."""
    if not text:
        return ""
    tr_map = str.maketrans({"İ": "i", "I": "ı"})
    return str(text).translate(tr_map).lower()


def tr_title(text: str) -> str:
    """Türkçe başlık düzeni (Her kelimenin ilk harfi büyük, geri kalanı küçük)."""
    if not text:
        return ""
    words = str(text).split()
    res = []
    for w in words:
        if not w:
            continue
        first = tr_upper(w[0])
        rest = tr_lower(w[1:])
        res.append(first + rest)
    return " ".join(res)


def to_turkish_date_str(val: Any) -> str:
    """Tarih girdilerini eksiksiz Türkçe ay isimlerine dönüştürür (Örn: 09 Ekim 2026)."""
    if not val:
        return "Resmi Kılavuzda"
    if isinstance(val, datetime):
        tr_months = ["", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
        return f"{val.day:02d} {tr_months[val.month]} {val.year}"
    
    val_str = str(val).strip()
    if not val_str or val_str.lower() in ["none", "null"]:
        return "Resmi Kılavuzda"

    # ISO formatı: YYYY-MM-DD
    m_iso = re.match(r"^(\d{4})-(\d{2})-(\d{2})", val_str)
    if m_iso:
        y, m, d = int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3))
        tr_months = ["", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
        if 1 <= m <= 12:
            return f"{d:02d} {tr_months[m]} {y}"

    # DD.MM.YYYY formatı
    m_dot = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})", val_str)
    if m_dot:
        d, m, y = int(m_dot.group(1)), int(m_dot.group(2)), int(m_dot.group(3))
        tr_months = ["", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
        if 1 <= m <= 12:
            return f"{d:02d} {tr_months[m]} {y}"

    # İngilizce Ay İsimlerini Türkçeye Çevir
    eng_to_tr = {
        "january": "Ocak", "february": "Şubat", "march": "Mart", "april": "Nisan",
        "may": "Mayıs", "june": "Haziran", "july": "Temmuz", "august": "Ağustos",
        "september": "Eylül", "october": "Ekim", "november": "Kasım", "december": "Aralık",
        "jan": "Ocak", "feb": "Şubat", "mar": "Mart", "apr": "Nisan",
        "jun": "Haziran", "jul": "Temmuz", "aug": "Ağustos", "sep": "Eylül",
        "oct": "Ekim", "nov": "Kasım", "dec": "Aralık"
    }
    for eng, tr in eng_to_tr.items():
        val_str = re.sub(rf"\b{eng}\b", tr, val_str, flags=re.IGNORECASE)

    return val_str


def clean_inst_and_pos(institution: str, position: str, title: str = "") -> Tuple[str, str]:
    """
    Kurum ve Pozisyon alanlarındaki karışıklığı (Örn: Kurum adında ilan başlığının olması,
    veya pozisyonda genel 'Kamu Personeli' yazması durumunu) akıllıca ayrıştırır.
    """
    inst = (institution or "").strip()
    pos = (position or "").strip()
    tit = (title or "").strip()

    # 1. Kurumun içindeki personel sayısını veya 'alacak' ibaresini ayıkla
    m = re.match(r"^(.*?)\s+(\d+\s*(?:sözleşmeli|memur|öğretim|sürekli|personel|uzman|kamu|işçi|akademik).*)$", inst, re.IGNORECASE)
    if m:
        inst = m.group(1).strip()
        if not pos or pos.lower() in ["kamu personel", "kamu personeli", "personel alımı"]:
            pos = m.group(2).strip()

    m2 = re.match(r"^(.*?)\s+(?:personel alım ilanı|personel alımı|memur alımı|akademik personel alımı|işçi alımı|alım ilanı|alacak).*$", inst, re.IGNORECASE)
    if m2:
        inst = m2.group(1).strip()

    # 2. Eğer kurum jenerikse title'dan çek
    if (not inst or inst.lower() in ["kamu kurumu", "resmi kurum"]) and tit:
        m_tit = re.match(r"^(.*?)\s+(\d+\s*(?:sözleşmeli|memur|uzman|gelir|öğretim|personel|işçi).*)$", tit, re.IGNORECASE)
        if m_tit:
            inst = m_tit.group(1).strip()
            if not pos or pos.lower() in ["kamu personel", "kamu personeli"]:
                pos = m_tit.group(2).strip()

    # 3. Pozisyon temizliği (alacak, alımı vb. ekleri kaldır)
    pos = re.sub(r"\s*(?:alacak|alımı|alınacaktır|alınacak|alım ilanı|ilanı).*$", "", pos, flags=re.IGNORECASE).strip(" -:,")
    if not pos or pos.lower() in ["kamu personel", "kamu personeli"]:
        pos = "Personel Alımı"

    return tr_upper(inst), tr_title(pos)


# =============================================================================
# ULTRA-YÜKSEK KONTRASTLI KURUMSAL RENK PALETLERİ (HIGH-CONTRAST PALETTES)
# =============================================================================
CARD_THEMES: Dict[str, Dict[str, Any]] = {
    "OFFICIAL_NAVY": {
        "id": "OFFICIAL_NAVY",
        "name": "🏛️ Kurumsal Lacivert & Altın (Resmi Standart)",
        "desc": "Ağırbaşlı devlet kurumu prestiji, derin gece laciverti, parlak altın sarısı ve kristal beyaz yazı",
        "bg_top": (10, 18, 38),
        "bg_bottom": (16, 28, 60),
        "panel": (18, 34, 68),
        "panel_hero": (22, 42, 84),
        "border": (48, 76, 135),
        "hero_border": (56, 189, 248),
        "hero_stripe": (245, 158, 11),
        "hero_tag": (251, 191, 36),
        "hero_val": (255, 255, 255),
        "badge_bg": (18, 38, 76),
        "badge_border": (245, 158, 11),
        "badge_text": (255, 255, 255),
        "badge_dot": (34, 197, 94),
        "tag_color_1": (245, 158, 11),
        "tag_color_2": (244, 63, 94),
        "tag_color_3": (56, 189, 248),
        "tag_color_4": (34, 197, 94),
        "val_color_1": (255, 255, 255),
        "val_color_2": (255, 255, 255),
        "pdf_banner_bg": (24, 48, 96),
        "pdf_banner_border": (245, 158, 11),
        "accent_glow": (56, 189, 248),
        "text_primary": (255, 255, 255),
        "text_secondary": (56, 189, 248),
        "text_muted": (148, 163, 184),
    },
    "ROYAL_CRIMSON": {
        "id": "ROYAL_CRIMSON",
        "name": "🔴 Kraliyet Bordo & Altın (Lüks Vitrin)",
        "desc": "Zengin kadife bordo degrade, asil altın ışıltısı ve kristal beyaz yazı",
        "bg_top": (28, 8, 18),
        "bg_bottom": (48, 12, 28),
        "panel": (60, 16, 36),
        "panel_hero": (76, 20, 44),
        "border": (130, 40, 70),
        "hero_border": (251, 191, 36),
        "hero_stripe": (251, 191, 36),
        "hero_tag": (253, 186, 116),
        "hero_val": (255, 255, 255),
        "badge_bg": (56, 14, 32),
        "badge_border": (251, 191, 36),
        "badge_text": (255, 255, 255),
        "badge_dot": (251, 191, 36),
        "tag_color_1": (251, 191, 36),
        "tag_color_2": (251, 146, 60),
        "tag_color_3": (253, 186, 116),
        "tag_color_4": (34, 197, 94),
        "val_color_1": (255, 255, 255),
        "val_color_2": (255, 255, 255),
        "pdf_banner_bg": (54, 14, 30),
        "pdf_banner_border": (251, 191, 36),
        "accent_glow": (251, 191, 36),
        "text_primary": (255, 255, 255),
        "text_secondary": (254, 205, 211),
        "text_muted": (190, 140, 155),
    },
    "DARK_NOIR": {
        "id": "DARK_NOIR",
        "name": "⬛ Minimalist Noir & Titanyum (Ultra Modern)",
        "desc": "Ultra modern monokrom titanyum, siyah üzeri saf beyaz kontrast",
        "bg_top": (12, 14, 20),
        "bg_bottom": (20, 24, 34),
        "panel": (30, 36, 50),
        "panel_hero": (38, 46, 64),
        "border": (70, 84, 112),
        "hero_border": (255, 255, 255),
        "hero_stripe": (255, 255, 255),
        "hero_tag": (203, 213, 225),
        "hero_val": (255, 255, 255),
        "badge_bg": (28, 34, 48),
        "badge_border": (226, 232, 240),
        "badge_text": (255, 255, 255),
        "badge_dot": (255, 255, 255),
        "tag_color_1": (255, 255, 255),
        "tag_color_2": (245, 158, 11),
        "tag_color_3": (56, 189, 248),
        "tag_color_4": (34, 197, 94),
        "val_color_1": (255, 255, 255),
        "val_color_2": (255, 255, 255),
        "pdf_banner_bg": (32, 38, 52),
        "pdf_banner_border": (255, 255, 255),
        "accent_glow": (255, 255, 255),
        "text_primary": (255, 255, 255),
        "text_secondary": (203, 213, 225),
        "text_muted": (148, 163, 184),
    },
    "EMERALD_MINT": {
        "id": "EMERALD_MINT",
        "name": "🟢 Zümrüt Yeşili & Kamu (Executive Mint)",
        "desc": "Taze, resmi, %100 onaylı derin orman ve zümrüt yeşili tasarımı",
        "bg_top": (8, 28, 20),
        "bg_bottom": (12, 48, 34),
        "panel": (16, 58, 42),
        "panel_hero": (22, 78, 56),
        "border": (34, 110, 78),
        "hero_border": (52, 211, 153),
        "hero_stripe": (52, 211, 153),
        "hero_tag": (167, 243, 208),
        "hero_val": (255, 255, 255),
        "badge_bg": (14, 52, 38),
        "badge_border": (52, 211, 153),
        "badge_text": (255, 255, 255),
        "badge_dot": (52, 211, 153),
        "tag_color_1": (52, 211, 153),
        "tag_color_2": (251, 191, 36),
        "tag_color_3": (110, 231, 183),
        "tag_color_4": (251, 146, 60),
        "val_color_1": (255, 255, 255),
        "val_color_2": (255, 255, 255),
        "pdf_banner_bg": (18, 62, 46),
        "pdf_banner_border": (52, 211, 153),
        "accent_glow": (52, 211, 153),
        "text_primary": (255, 255, 255),
        "text_secondary": (167, 243, 208),
        "text_muted": (140, 185, 160),
    },
    "CYBER_VIOLET": {
        "id": "CYBER_VIOLET",
        "name": "🟣 Gece Moru & Neon Siber (Orijinal Marka)",
        "desc": "Marka logosuyla kusursuz eşleşen neon mor, elektrik mavisi ve altın vurgular",
        "bg_top": (14, 12, 30),
        "bg_bottom": (26, 18, 52),
        "panel": (32, 26, 66),
        "panel_hero": (42, 34, 88),
        "border": (84, 56, 138),
        "hero_border": (168, 85, 247),
        "hero_stripe": (251, 191, 36),
        "hero_tag": (251, 191, 36),
        "hero_val": (255, 255, 255),
        "badge_bg": (38, 24, 74),
        "badge_border": (168, 85, 247),
        "badge_text": (255, 255, 255),
        "badge_dot": (168, 85, 247),
        "tag_color_1": (251, 191, 36),
        "tag_color_2": (244, 63, 94),
        "tag_color_3": (56, 189, 248),
        "tag_color_4": (34, 197, 94),
        "val_color_1": (255, 255, 255),
        "val_color_2": (255, 255, 255),
        "pdf_banner_bg": (36, 26, 70),
        "pdf_banner_border": (168, 85, 247),
        "accent_glow": (168, 85, 247),
        "text_primary": (255, 255, 255),
        "text_secondary": (216, 180, 254),
        "text_muted": (160, 145, 180),
    }
}


class JobCardGenerator:
    """
    Yeni Nesil Yüksek Çözünürlüklü Kurumsal İlan Vitrini Motoru (v3.0 Ultra HD).
    - 1080x1080 Kare (Instagram Akış, Facebook, Telegram için kusursuz)
    - Büyük, okunabilir, göz alıcı tipografi (mobilde bile anında fark edilen puntolar)
    - Tofu/kutu hatası oluşturmayan saf vektörel rozetler
    - Akıllı kurum & unvan ayrıştırma algoritması
    - Yüksek kontrastlı, asla solmayan ve çamurlu görünmeyen renk düzeni
    """

    WIDTH = 1080
    HEIGHT = 1080

    def __init__(self):
        self.fonts_dir = settings.FONTS_DIR
        self.output_dir = settings.IMAGE_OUTPUT_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.assets_dir = Path("graphics/assets")
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        self.logo_path = self.assets_dir / "logo.png"

        # Font Tanımları (Öncelik: Proje içi gömülü fontlar -> Windows fontları -> Linux fontları)
        bundled_bold = self.assets_dir / "fonts" / "font_bold.ttf"
        bundled_reg = self.assets_dir / "fonts" / "font.ttf"

        if bundled_bold.exists() and bundled_reg.exists():
            self.font_bold_path = bundled_bold
            self.font_regular_path = bundled_reg
        elif Path("C:/Windows/Fonts/segoeuib.ttf").exists():
            self.font_bold_path = Path("C:/Windows/Fonts/segoeuib.ttf")
            self.font_regular_path = Path("C:/Windows/Fonts/segoeui.ttf")
        elif Path("C:/Windows/Fonts/arialbd.ttf").exists():
            self.font_bold_path = Path("C:/Windows/Fonts/arialbd.ttf")
            self.font_regular_path = Path("C:/Windows/Fonts/arial.ttf")
        elif Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf").exists():
            self.font_bold_path = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
            self.font_regular_path = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
        else:
            self.font_bold_path = bundled_bold
            self.font_regular_path = bundled_reg

    def _get_font(self, size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
        path = self.font_bold_path if bold else self.font_regular_path
        try:
            return ImageFont.truetype(str(path), size=size)
        except Exception:
            for alt in [
                self.assets_dir / "fonts" / "font_bold.ttf",
                self.assets_dir / "fonts" / "font.ttf",
                Path("C:/Windows/Fonts/arialbd.ttf"),
                Path("C:/Windows/Fonts/arial.ttf"),
                Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
            ]:
                if alt.exists():
                    try:
                        return ImageFont.truetype(str(alt), size=size)
                    except Exception:
                        pass
            return ImageFont.load_default()

    def _wrap_text(self, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> List[str]:
        """Metni piksel sınırına göre düzgünce satırlara böler."""
        words = text.split()
        lines = []
        current_line = []

        for word in words:
            current_line.append(word)
            test_line = " ".join(current_line)
            bbox = font.getbbox(test_line)
            width = bbox[2] - bbox[0]
            if width > max_width:
                current_line.pop()
                if current_line:
                    lines.append(" ".join(current_line))
                current_line = [word]

        if current_line:
            lines.append(" ".join(current_line))

        return lines

    def _draw_lux_background(
        self,
        draw: ImageDraw.ImageDraw,
        img: Image.Image,
        c_top: Tuple[int, int, int],
        c_bottom: Tuple[int, int, int],
        accent: Tuple[int, int, int]
    ) -> None:
        """Pürüzsüz lüks dikey degrade ve yumuşak atmosferik ışıltı çizer."""
        for y in range(self.HEIGHT):
            ratio = y / self.HEIGHT
            r = int(c_top[0] * (1 - ratio) + c_bottom[0] * ratio)
            g = int(c_top[1] * (1 - ratio) + c_bottom[1] * ratio)
            b = int(c_top[2] * (1 - ratio) + c_bottom[2] * ratio)
            draw.line([(0, y), (self.WIDTH, y)], fill=(r, g, b, 255))

        # Yumuşak Vurgu Ambient Işıltısı
        glow_layer = Image.new("RGBA", (self.WIDTH, self.HEIGHT), (0, 0, 0, 0))
        d_glow = ImageDraw.Draw(glow_layer)
        d_glow.ellipse(
            [(self.WIDTH - 420, -100), (self.WIDTH + 150, 450)],
            fill=(accent[0], accent[1], accent[2], 35)
        )
        d_glow.ellipse(
            [(-120, 200), (350, 680)],
            fill=(245, 158, 11, 20)
        )
        glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(60))
        img.alpha_composite(glow_layer)

    def generate_card(
        self,
        job_id: int,
        institution: str,
        position: str,
        total_positions: Optional[int] = None,
        kpss_requirement: Optional[str] = None,
        education_level: Optional[str] = None,
        deadline: Optional[str] = None,
        source_url: Optional[str] = None,
        has_pdf: bool = True,
        theme: Optional[str] = None,
        title: str = ""
    ) -> Path:
        """
        1080x1080 boyutunda seçilen tema paletiyle üst düzey kurumsal ilan vitrini afişi üretir.
        """
        theme_key = theme or get_system_setting("DEFAULT_CARD_THEME", "OFFICIAL_NAVY")
        pal = CARD_THEMES.get(theme_key, CARD_THEMES["OFFICIAL_NAVY"])

        # Akıllı metin ayrıştırma ve Türkçe karakter formatlama
        clean_inst, clean_pos = clean_inst_and_pos(institution, position, title)

        img = Image.new("RGBA", (self.WIDTH, self.HEIGHT), (0, 0, 0, 255))
        draw = ImageDraw.Draw(img)

        # 1. Atmosferik Lüks Degrade ve Derinlik Işıltısı
        self._draw_lux_background(draw, img, pal["bg_top"], pal["bg_bottom"], pal["accent_glow"])
        draw = ImageDraw.Draw(img)

        # Üst neon altın ışıltı çizgisi
        for i in range(4):
            alpha = int(255 * (1 - i / 4))
            draw.line([(0, i), (self.WIDTH, i)], fill=(pal["hero_stripe"][0], pal["hero_stripe"][1], pal["hero_stripe"][2], alpha))

        # Dış Çift Zarif Çerçeve
        draw.rounded_rectangle([(20, 20), (self.WIDTH - 20, self.HEIGHT - 20)], radius=24, outline=(pal["border"][0], pal["border"][1], pal["border"][2], 140), width=1)
        draw.rounded_rectangle([(28, 28), (self.WIDTH - 28, self.HEIGHT - 28)], radius=20, outline=pal["hero_border"], width=2)

        # 2. ŞEFFAF FİLİGRAN (WATERMARK)
        if self.logo_path.exists():
            try:
                logo_raw = Image.open(self.logo_path).convert("RGBA")
                wm_size = (560, 560)
                wm = logo_raw.resize(wm_size, Image.Resampling.LANCZOS)
                r, g, b, alpha = wm.split()
                alpha = alpha.point(lambda p: int(p * 0.05))
                wm.putalpha(alpha)
                img.alpha_composite(wm, ((self.WIDTH - wm_size[0]) // 2, (self.HEIGHT - wm_size[1]) // 2 + 30))
            except Exception as e:
                logger.debug(f"Filigran uyarısı: {e}")

        # 3. ÜST HEADER ALANI
        lh = 80
        if self.logo_path.exists():
            try:
                logo_crop = logo_raw.resize((lh, lh), Image.Resampling.LANCZOS)
                mask = Image.new("L", (lh, lh), 0)
                d_mask = ImageDraw.Draw(mask)
                d_mask.ellipse((0, 0, lh, lh), fill=255)
                logo_circ = ImageOps.fit(logo_crop, mask.size, centering=(0.5, 0.5))
                logo_circ.putalpha(mask)

                # Logo halkası
                draw.ellipse([(50, 44), (50 + lh + 8, 44 + lh + 8)], outline=pal["hero_stripe"], width=2)
                img.alpha_composite(logo_circ, (54, 48))
            except Exception as le:
                logger.debug(f"Logo uyarısı: {le}")

        draw.text((150, 48), "KAMU PERSONEL REHBERİ", fill=pal["text_primary"], font=self._get_font(28, bold=True))
        draw.text((152, 86), "GÜNCEL • DOĞRU • %100 DEVLET TEYİTLİ İLANLAR", fill=pal["hero_tag"], font=self._get_font(14, bold=True))

        # Sağ Üst Doğrulanmış Rozeti (Pill)
        badge_text = "RESMİ DEVLET İLANI"
        f_badge = self._get_font(16, bold=True)
        bw = f_badge.getbbox(badge_text)[2] - f_badge.getbbox(badge_text)[0] + 56
        bx = self.WIDTH - 50 - bw
        draw.rounded_rectangle([(bx, 54), (bx + bw, 104)], radius=16, fill=pal["badge_bg"], outline=pal["badge_border"], width=2)
        draw.ellipse([(bx + 16, 73), (bx + 28, 85)], fill=pal["badge_dot"])
        draw.text((bx + 36, 68), badge_text, fill=pal["badge_text"], font=f_badge)

        # Ayırıcı Çizgi
        draw.line([(50, 144), (self.WIDTH - 50, 144)], fill=pal["border"], width=2)

        # 4. KAMU KURUMU BAŞLIĞI (BÜYÜK, NET, KRİSTAL BEYAZ)
        draw.ellipse([(55, 168), (67, 180)], fill=pal["hero_stripe"])
        draw.text((76, 165), "KAMU KURUMU / BAKANLIK", fill=pal["hero_border"], font=self._get_font(16, bold=True))

        inst_font_size = 42 if len(clean_inst) < 40 else 35
        f_inst = self._get_font(inst_font_size, bold=True)
        inst_lines = self._wrap_text(clean_inst, f_inst, max_width=970)
        curr_y = 196
        for line in inst_lines[:2]:
            # Hafif gölge ve saf beyaz yazı
            draw.text((56, curr_y + 2), line, fill=(0, 0, 0, 160), font=f_inst)
            draw.text((54, curr_y), line, fill=pal["text_primary"], font=f_inst)
            curr_y += (inst_font_size + 6)

        # 5. POZİSYON HERO KARTI (BÜYÜK VURGU PANOSU)
        hero_y = curr_y + 12
        hero_h = 118
        draw.rounded_rectangle([(50, hero_y), (self.WIDTH - 50, hero_y + hero_h)], radius=18, fill=pal["panel_hero"], outline=pal["hero_border"], width=2)
        # Sol amber dikey şerit
        draw.rounded_rectangle([(50, hero_y), (64, hero_y + hero_h)], radius=6, fill=pal["hero_stripe"])

        draw.text((82, hero_y + 16), "ALIM YAPILACAK KADRO / POZİSYON", fill=pal["hero_tag"], font=self._get_font(15, bold=True))
        
        pos_font_size = 38 if len(clean_pos) < 36 else 30
        f_pos = self._get_font(pos_font_size, bold=True)
        pos_lines = self._wrap_text(clean_pos, f_pos, max_width=910)
        py = hero_y + 46 if len(pos_lines) == 1 else hero_y + 40
        for pline in pos_lines[:2]:
            draw.text((82, py), pline, fill=pal["hero_val"], font=f_pos)
            py += (pos_font_size + 6)

        # 6. DÖRT TEMEL BİLGİ KARTI (2x2 GRID - BÜYÜK PUNTOLU METRİKLER)
        grid_top = hero_y + hero_h + 20
        col_w = 465
        row_h = 138
        gap_x = 50
        gap_y = 16
        c1 = 50
        c2 = c1 + col_w + gap_x

        pos_str = f"{total_positions} Kişi" if total_positions else "İlanda Belirtildi"
        kpss_str = kpss_requirement or "Resmi İlanda Belirtildi"
        edu_str = education_level or "İlgili Bölüm Mezuniyeti"
        deadline_str = to_turkish_date_str(deadline)

        cards = [
            {
                "box": [(c1, grid_top), (c1 + col_w, grid_top + row_h)],
                "tag": "KONTENJAN",
                "val": pos_str,
                "accent": pal["tag_color_1"],
                "val_size": 42 if len(pos_str) < 12 else 34,
            },
            {
                "box": [(c2, grid_top), (c2 + col_w, grid_top + row_h)],
                "tag": "SON BAŞVURU TARİHİ",
                "val": deadline_str,
                "accent": pal["tag_color_2"],
                "val_size": 34,
            },
            {
                "box": [(c1, grid_top + row_h + gap_y), (c1 + col_w, grid_top + 2 * row_h + gap_y)],
                "tag": "KPSS ŞARTI",
                "val": kpss_str,
                "accent": pal["tag_color_3"],
                "val_size": 28,
            },
            {
                "box": [(c2, grid_top + row_h + gap_y), (c2 + col_w, grid_top + 2 * row_h + gap_y)],
                "tag": "ÖĞRENİM DÜZEYİ",
                "val": edu_str,
                "accent": pal["tag_color_4"],
                "val_size": 28,
            }
        ]

        f_card_tag = self._get_font(16, bold=True)
        for card in cards:
            bx = card["box"]
            draw.rounded_rectangle(bx, radius=16, fill=pal["panel"], outline=pal["border"], width=2)
            
            # Canlı etiket rozeti
            draw.ellipse([(bx[0][0] + 20, bx[0][1] + 20), (bx[0][0] + 32, bx[0][1] + 32)], fill=card["accent"])
            draw.text((bx[0][0] + 40, bx[0][1] + 16), card["tag"], fill=card["accent"], font=f_card_tag)

            # Büyük Değer Metni (Saf Beyaz)
            f_v = self._get_font(card["val_size"], bold=True)
            v_lines = self._wrap_text(card["val"], f_v, max_width=col_w - 40)
            vy = bx[0][1] + 58 if len(v_lines) == 1 else bx[0][1] + 48
            for vl in v_lines[:2]:
                draw.text((bx[0][0] + 22, vy), vl, fill=(255, 255, 255), font=f_v)
                vy += (card["val_size"] + 4)

        # 7. RESMİ KILAVUZ BANT ŞERİDİ
        banner_y = grid_top + 2 * row_h + gap_y + 18
        banner_fill = pal["pdf_banner_bg"]
        banner_outline = pal["pdf_banner_border"]
        banner_text = "RESMİ BAŞVURU KILAVUZU & ŞARTNAME (PDF) EKLENMİŞTİR" if has_pdf else "RESMİ BAŞVURU VE DUYURU SİSTEMDE MEVCUTTUR"

        draw.rounded_rectangle([(50, banner_y), (self.WIDTH - 50, banner_y + 54)], radius=14, fill=banner_fill, outline=banner_outline, width=2)
        draw.ellipse([(72, banner_y + 20), (86, banner_y + 34)], fill=banner_outline)
        f_banner = self._get_font(18, bold=True)
        draw.text((98, banner_y + 16), banner_text, fill=(255, 255, 255), font=f_banner)

        # 8. ALT BİLGİ & ÇALINMAYA KARŞI MARKA İMZASI (FOOTER - SIFIR TOFU / KUTU HATASI)
        footer_y = banner_y + 68
        draw.line([(50, footer_y), (self.WIDTH - 50, footer_y)], fill=pal["border"], width=2)

        # Telegram Vektörel Hap Rozet & Metin
        draw.rounded_rectangle([(52, footer_y + 15), (88, footer_y + 39)], radius=6, fill=(14, 165, 233))
        draw.text((58, footer_y + 19), "TG", fill=(255, 255, 255), font=self._get_font(13, bold=True))
        draw.text((98, footer_y + 14), "Telegram: @kamupersonelrehberi", fill=pal["text_primary"], font=self._get_font(21, bold=True))

        # Instagram Vektörel Hap Rozet & Metin
        draw.rounded_rectangle([(52, footer_y + 49), (88, footer_y + 73)], radius=6, fill=(225, 48, 108))
        draw.text((59, footer_y + 53), "IG", fill=(255, 255, 255), font=self._get_font(13, bold=True))
        draw.text((98, footer_y + 48), "Instagram: @kamupersonelrehberi", fill=pal["text_secondary"], font=self._get_font(17, bold=True))

        # Telif Satırı
        draw.text((54, footer_y + 78), "Telif Hakları Saklıdır • Doğrulanmış Resmi Kamu İlanı • İzinsiz Alınamaz", fill=pal["text_muted"], font=self._get_font(13))

        # Sağ Dinamik QR Kod
        qr_target = source_url or "https://t.me/kamupersonelrehberi"
        if "ilanDetay.aspx" in qr_target:
            qr_target = "https://kamuilan.sbb.gov.tr/"

        try:
            qr = qrcode.QRCode(version=1, box_size=3, border=2)
            qr.add_data(qr_target)
            qr.make(fit=True)
            qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
            qw, qh = qr_img.size

            qx = self.WIDTH - 52 - qw
            qy = footer_y + 8

            draw.rounded_rectangle([(qx - 6, qy - 6), (qx + qw + 6, qy + qh + 6)], radius=10, fill=(255, 255, 255), outline=pal["hero_stripe"], width=2)
            img.paste(qr_img, (qx, qy, qx + qw, qy + qh))

            draw.text((qx - 195, footer_y + 24), "RESMİ KILAVUZ", fill=pal["text_muted"], font=self._get_font(14, bold=True))
            draw.text((qx - 195, footer_y + 46), "QR KODU OKUTUN", fill=pal["hero_tag"], font=self._get_font(16, bold=True))
        except Exception as qe:
            logger.warning(f"QR kod oluşturulamadı: {qe}")

        # 9. RGB'ye Dönüştür ve Kaydet
        final_img = img.convert("RGB")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"ilan_kart_{job_id}_{theme_key.lower()}_{timestamp}.png"
        filepath = self.output_dir / filename
        final_img.save(str(filepath), "PNG", quality=98)

        logger.info(f"Yeni kurumsal marka ilan vitrini üretildi [{pal['name']}]: {filepath}")
        return filepath

    def get_theme_sample(self, theme_key: str, force_refresh: bool = False) -> Path:
        """Belirtilen tema için kalıcı bir örnek vitrin kartı döner."""
        import shutil
        sample_dir = self.assets_dir / "theme_previews"
        sample_dir.mkdir(parents=True, exist_ok=True)
        sample_path = sample_dir / f"sample_{theme_key.lower()}.png"
        if force_refresh or not sample_path.exists():
            gen_path = self.generate_card(
                job_id=999,
                institution="GİRESUN ÜNİVERSİTESİ",
                position="Öğretim Üyesi Alımı",
                total_positions=11,
                kpss_requirement="Resmi İlanda Belirtilmiştir",
                education_level="Kılavuzda Belirtilen Şartlar",
                deadline="09 Ekim 2026",
                source_url="https://kamuilan.sbb.gov.tr/",
                has_pdf=True,
                theme=theme_key,
                title="GİRESUN ÜNİVERSİTESİ Personel Alım İlanı"
            )
            shutil.copyfile(gen_path, sample_path)
        return sample_path
