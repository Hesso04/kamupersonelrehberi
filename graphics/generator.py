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

        self.assets_dir = settings.ASSETS_DIR
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
        accent: Tuple[int, int, int],
        width: Optional[int] = None,
        height: Optional[int] = None
    ) -> None:
        """Pürüzsüz lüks dikey degrade ve yumuşak atmosferik ışıltı çizer."""
        w = width or self.WIDTH
        h = height or self.HEIGHT
        for y in range(h):
            ratio = y / h
            r = int(c_top[0] * (1 - ratio) + c_bottom[0] * ratio)
            g = int(c_top[1] * (1 - ratio) + c_bottom[1] * ratio)
            b = int(c_top[2] * (1 - ratio) + c_bottom[2] * ratio)
            draw.line([(0, y), (w, y)], fill=(r, g, b, 255))

        # Yumuşak Vurgu Ambient Işıltısı
        glow_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d_glow = ImageDraw.Draw(glow_layer)
        d_glow.ellipse(
            [(w - 420, -100), (w + 150, int(h * 0.42))],
            fill=(accent[0], accent[1], accent[2], 35)
        )
        d_glow.ellipse(
            [(-120, int(h * 0.2)), (350, int(h * 0.65))],
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

    def generate_carousel_cards(
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
        title: str = "",
        bullet_points: Optional[List[str]] = None,
        city: Optional[str] = None
    ) -> List[Path]:
        """
        Instagram için 4:5 Dikey (1080x1350) formatında 3 slaytlık yüksek etkileşimli
        Çoklu Kaydırmalı Gönderi (Carousel) seti üretir:
          - Slayt 1: Vurucu Kapak & Kontenjan (Hook Slide)
          - Slayt 2: Kadro Dağılımı & Başvuru Şartları (Details Slide)
          - Slayt 3: Başvuru Adımları & Viral 'Yoruma KILAVUZ Yaz' CTA (Conversion Slide)
        """
        w, h = 1080, 1350
        theme_key = theme or get_system_setting("DEFAULT_CARD_THEME", "OFFICIAL_NAVY")
        pal = CARD_THEMES.get(theme_key, CARD_THEMES["OFFICIAL_NAVY"])
        clean_inst, clean_pos = clean_inst_and_pos(institution, position, title)

        tot_num = total_positions if (total_positions and total_positions > 0) else 1
        pos_badge = f"{tot_num:,} PERSONEL ALIMI".replace(",", ".")
        kpss_str = kpss_requirement or "Resmi Kılavuzda"
        edu_str = education_level or "Resmi Kılavuzda"
        d_str = to_turkish_date_str(deadline)
        city_str = city or "Türkiye Geneli"

        output_paths: List[Path] = []
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Ortak Filigran Çizim Yardımcısı
        def apply_watermark(target_img: Image.Image):
            if self.logo_path.exists():
                try:
                    logo_raw = Image.open(self.logo_path).convert("RGBA")
                    wm_size = (620, 620)
                    wm = logo_raw.resize(wm_size, Image.Resampling.LANCZOS)
                    r, g, b, alpha = wm.split()
                    alpha = alpha.point(lambda p: int(p * 0.05))
                    wm.putalpha(alpha)
                    target_img.alpha_composite(wm, ((w - wm_size[0]) // 2, (h - wm_size[1]) // 2 + 50))
                except Exception:
                    pass

        # Ortak Logo Çizim Yardımcısı
        def draw_header_logo(target_img: Image.Image, d: ImageDraw.ImageDraw, y_offset: int = 50):
            lh = 76
            if self.logo_path.exists():
                try:
                    logo_raw = Image.open(self.logo_path).convert("RGBA")
                    logo_crop = logo_raw.resize((lh, lh), Image.Resampling.LANCZOS)
                    mask = Image.new("L", (lh, lh), 0)
                    ImageDraw.Draw(mask).ellipse((0, 0, lh, lh), fill=255)
                    logo_circ = ImageOps.fit(logo_crop, mask.size, centering=(0.5, 0.5))
                    logo_circ.putalpha(mask)
                    d.ellipse([(50, y_offset), (50 + lh + 8, y_offset + lh + 8)], outline=pal["hero_stripe"], width=2)
                    target_img.alpha_composite(logo_circ, (54, y_offset + 4))
                except Exception:
                    pass
            d.text((146, y_offset + 6), "KAMU PERSONEL REHBERİ", fill=pal["text_primary"], font=self._get_font(26, bold=True))
            d.text((148, y_offset + 42), "T.C. RESMİ GAZETE & SBB ONAYLI İLANLAR", fill=pal["hero_tag"], font=self._get_font(13, bold=True))

            # Sağ Üst Rozet
            badge_text = "RESMİ DEVLET İLANI"
            fb = self._get_font(15, bold=True)
            bb = d.textbbox((0, 0), badge_text, font=fb)
            bw = (bb[2] - bb[0]) + 36
            bx = w - 50 - bw
            d.rounded_rectangle([(bx, y_offset + 10), (w - 50, y_offset + 56)], radius=23, fill=pal["badge_bg"], outline=pal["badge_border"], width=2)
            d.ellipse([(bx + 14, y_offset + 28), (bx + 24, y_offset + 38)], fill=pal["badge_dot"])
            d.text((bx + 32, y_offset + 23), badge_text, fill=pal["badge_text"], font=fb)

        # Ortak Alt Bar (Footer) Çizim Yardımcısı
        def draw_carousel_footer(d: ImageDraw.ImageDraw, slide_num: int, total_slides: int = 3):
            fy = h - 90
            d.line([(50, fy), (w - 50, fy)], fill=pal["border"], width=2)
            # Sol imza
            d.text((54, fy + 24), "Instagram & Telegram: @kamupersonelrehberi", fill=pal["text_secondary"], font=self._get_font(18, bold=True))
            d.text((54, fy + 52), "%100 Teyitli Resmi İlan • Tık Tuzağı ve Reklam İçermez", fill=pal["text_muted"], font=self._get_font(13))

            # Sağ Slayt Numaratörü Rozeti
            slide_tag = f"{slide_num} / {total_slides}"
            s_font = self._get_font(18, bold=True)
            s_bbox = d.textbbox((0, 0), slide_tag, font=s_font)
            sw = (s_bbox[2] - s_bbox[0]) + 30
            sx = w - 50 - sw
            d.rounded_rectangle([(sx, fy + 20), (w - 50, fy + 65)], radius=12, fill=pal["panel_hero"], outline=pal["hero_stripe"], width=2)
            d.text((sx + 15, fy + 29), slide_tag, fill=pal["hero_tag"], font=s_font)

        # =====================================================================
        # 1. SLAYT: VURUCU KAPAK (HOOK SLIDE - 1080x1350)
        # =====================================================================
        img1 = Image.new("RGBA", (w, h), (0, 0, 0, 255))
        d1 = ImageDraw.Draw(img1)
        self._draw_lux_background(d1, img1, pal["bg_top"], pal["bg_bottom"], pal["accent_glow"], width=w, height=h)
        d1 = ImageDraw.Draw(img1)

        # Çift çerçeve
        d1.rounded_rectangle([(20, 20), (w - 20, h - 20)], radius=24, outline=(pal["border"][0], pal["border"][1], pal["border"][2], 140), width=1)
        d1.rounded_rectangle([(28, 28), (w - 28, h - 28)], radius=20, outline=pal["hero_border"], width=2)
        apply_watermark(img1)
        draw_header_logo(img1, d1, y_offset=54)

        # Kurum Başlığı Şeridi
        f_inst = self._get_font(34, bold=True)
        inst_lines = self._wrap_text(clean_inst, f_inst, max_width=w - 120)
        y_cursor = 175
        for il in inst_lines[:2]:
            d1.text((54, y_cursor), il, fill=pal["text_primary"], font=f_inst)
            y_cursor += 44

        # Hero Kontenjan Vitrin Kutusu (Büyük Vurgulu Rozet)
        hero_top = y_cursor + 20
        hero_h = 240
        d1.rounded_rectangle([(50, hero_top), (w - 50, hero_top + hero_h)], radius=22, fill=pal["panel_hero"], outline=pal["hero_border"], width=2)
        d1.rounded_rectangle([(50, hero_top), (66, hero_top + hero_h)], radius=10, fill=pal["hero_stripe"])

        d1.text((86, hero_top + 28), "TOPLAM PERSONEL ALIM KONTENJANI", fill=pal["hero_tag"], font=self._get_font(20, bold=True))
        d1.text((86, hero_top + 64), pos_badge, fill=pal["hero_val"], font=self._get_font(52, bold=True))
        d1.text((86, hero_top + 145), "⚡ Şartlar, Branşlar ve Başvuru Takvimi Belli Oldu!", fill=pal["tag_color_2"], font=self._get_font(22, bold=True))
        d1.text((86, hero_top + 185), f"🗓 Son Başvuru: {d_str}", fill=pal["text_secondary"], font=self._get_font(20, bold=True))

        # Kadro / Pozisyon Vitrin Kutusu
        pos_top = hero_top + hero_h + 30
        pos_h = 240
        d1.rounded_rectangle([(50, pos_top), (w - 50, pos_top + pos_h)], radius=22, fill=pal["panel"], outline=pal["border"], width=2)
        d1.rounded_rectangle([(50, pos_top), (64, pos_top + pos_h)], radius=10, fill=pal["tag_color_3"])
        d1.text((86, pos_top + 24), "ALIM YAPILACAK BAŞLICA KADROLAR", fill=pal["tag_color_3"], font=self._get_font(20, bold=True))

        f_pos = self._get_font(32, bold=True)
        pos_lines = self._wrap_text(clean_pos, f_pos, max_width=w - 140)
        py = pos_top + 65
        for pl in pos_lines[:3]:
            d1.text((86, py), pl, fill=(255, 255, 255), font=f_pos)
            py += 44

        # 3'lü Güven & Özellik Rozetleri
        badge_row_y = pos_top + pos_h + 30
        col_w = (w - 100 - 30) // 2
        
        d1.rounded_rectangle([(50, badge_row_y), (50 + col_w, badge_row_y + 80)], radius=16, fill=pal["panel"], outline=pal["border"], width=2)
        d1.ellipse([(68, badge_row_y + 30), (84, badge_row_y + 46)], fill=pal["tag_color_4"])
        d1.text((94, badge_row_y + 18), "KPSS & MEZUNİYET", fill=pal["tag_color_4"], font=self._get_font(15, bold=True))
        d1.text((94, badge_row_y + 42), kpss_str[:22], fill=(255, 255, 255), font=self._get_font(18, bold=True))

        c2_x = 50 + col_w + 30
        d1.rounded_rectangle([(c2_x, badge_row_y), (c2_x + col_w, badge_row_y + 80)], radius=16, fill=pal["panel"], outline=pal["border"], width=2)
        d1.ellipse([(c2_x + 18, badge_row_y + 30), (c2_x + 34, badge_row_y + 46)], fill=pal["tag_color_2"])
        d1.text((c2_x + 44, badge_row_y + 18), "GÖREV YERİ", fill=pal["tag_color_2"], font=self._get_font(15, bold=True))
        d1.text((c2_x + 44, badge_row_y + 42), city_str[:22], fill=(255, 255, 255), font=self._get_font(18, bold=True))

        # Kaydırma Eylemi Çağrısı (Swipe CTA Button)
        swipe_y = badge_row_y + 110
        d1.rounded_rectangle([(50, swipe_y), (w - 50, swipe_y + 90)], radius=24, fill=pal["pdf_banner_bg"], outline=pal["hero_stripe"], width=2)
        d1.text((80, swipe_y + 20), "KADRO DAĞILIMI & ŞARTLAR İÇİN KAYDIRIN", fill=(255, 255, 255), font=self._get_font(24, bold=True))
        d1.text((w - 140, swipe_y + 18), "➡️", fill=pal["hero_stripe"], font=self._get_font(36, bold=True))
        d1.text((82, swipe_y + 56), "Resmi başvuru kılavuzu şartları 2. ve 3. slaytta yer almaktadır.", fill=pal["text_secondary"], font=self._get_font(15))

        draw_carousel_footer(d1, slide_num=1, total_slides=3)
        path1 = self.output_dir / f"carousel_{job_id}_slide_1_{timestamp}.png"
        img1.convert("RGB").save(str(path1), "PNG", quality=98)
        output_paths.append(path1)

        # =====================================================================
        # 2. SLAYT: KADRO & ŞARTLAR DETAYI (DETAILS SLIDE - 1080x1350)
        # =====================================================================
        img2 = Image.new("RGBA", (w, h), (0, 0, 0, 255))
        d2 = ImageDraw.Draw(img2)
        self._draw_lux_background(d2, img2, pal["bg_top"], pal["bg_bottom"], pal["accent_glow"], width=w, height=h)
        d2 = ImageDraw.Draw(img2)
        d2.rounded_rectangle([(20, 20), (w - 20, h - 20)], radius=24, outline=(pal["border"][0], pal["border"][1], pal["border"][2], 140), width=1)
        d2.rounded_rectangle([(28, 28), (w - 28, h - 28)], radius=20, outline=pal["hero_border"], width=2)
        apply_watermark(img2)
        draw_header_logo(img2, d2, y_offset=54)

        # Slayt Başlığı Şeridi
        d2.text((54, 175), "KADRO DAĞILIMI VE BAŞVURU ŞARTLARI", fill=pal["hero_tag"], font=self._get_font(28, bold=True))
        d2.text((54, 215), clean_inst[:65], fill=pal["text_secondary"], font=self._get_font(20, bold=True))

        # 4'lü Temel Şart Grid Kartı (2x2)
        grid_top = 270
        card_h = 135
        c_w = (w - 100 - 24) // 2
        cards_data = [
            {"tag": "KONTENJAN", "val": f"{tot_num:,} Kişi".replace(",", "."), "accent": pal["hero_stripe"], "desc": "Resmi Kontenjan"},
            {"tag": "KPSS ŞARTI", "val": kpss_str[:28], "accent": pal["tag_color_3"], "desc": "Puan Türü & Taban"},
            {"tag": "ÖĞRENİM DÜZEYİ", "val": edu_str[:28], "accent": pal["tag_color_4"], "desc": "Mezuniyet Şartı"},
            {"tag": "GÖREV YERİ / ŞEHİR", "val": city_str[:28], "accent": pal["tag_color_2"], "desc": "Atama Bölgesi"}
        ]

        for idx, cd in enumerate(cards_data):
            row = idx // 2
            col = idx % 2
            cx = 50 + col * (c_w + 24)
            cy = grid_top + row * (card_h + 20)

            d2.rounded_rectangle([(cx, cy), (cx + c_w, cy + card_h)], radius=18, fill=pal["panel"], outline=pal["border"], width=2)
            d2.ellipse([(cx + 20, cy + 22), (cx + 34, cy + 36)], fill=cd["accent"])
            d2.text((cx + 44, cy + 18), cd["tag"], fill=cd["accent"], font=self._get_font(16, bold=True))
            d2.text((cx + 20, cy + 50), cd["val"], fill=(255, 255, 255), font=self._get_font(24, bold=True))
            d2.text((cx + 20, cy + 92), cd["desc"], fill=pal["text_muted"], font=self._get_font(15))

        # Özel Şartlar & Kılavuz Maddeleri Paneli
        req_panel_top = grid_top + 2 * (card_h + 20) + 10
        req_panel_h = 370
        d2.rounded_rectangle([(50, req_panel_top), (w - 50, req_panel_top + req_panel_h)], radius=22, fill=pal["panel_hero"], outline=pal["border"], width=2)
        d2.rounded_rectangle([(50, req_panel_top), (64, req_panel_top + req_panel_h)], radius=10, fill=pal["tag_color_2"])

        d2.text((86, req_panel_top + 24), "ÖNEMLİ BAŞVURU ŞARTLARI & ÖZEL NOTLAR", fill=pal["tag_color_2"], font=self._get_font(20, bold=True))

        bullets = bullet_points or [
            "657 Sayılı Devlet Memurları Kanununun 48. maddesinde belirtilen genel şartları taşımak.",
            "Belirtilen öğrenim düzeyinden mezun olmak ve istenen KPSS taban puanını sağlamış olmak.",
            "Son başvuru tarihi itibarıyla ilgili kurumun yaş ve branş şartlarını karşılıyor olmak.",
            "Herhangi bir kamu kurumunda sözleşmeli pozisyonda çalışırken fesih şartlarına takılmamış olmak.",
            "Mülakat veya yazılı sınav gerektiren kadrolarda resmi ilan kılavuzundaki sınav adımları geçerlidir."
        ]

        by_cur = req_panel_top + 70
        f_bullet = self._get_font(19)
        for b_text in bullets[:5]:
            d2.ellipse([(86, by_cur + 8), (98, by_cur + 20)], fill=pal["hero_stripe"])
            wrapped_b = self._wrap_text(b_text, f_bullet, max_width=w - 180)
            for wbl in wrapped_b[:2]:
                d2.text((114, by_cur), wbl, fill=pal["text_primary"], font=f_bullet)
                by_cur += 28
            by_cur += 8

        # 2. Slayt Alt Swipe Çağrısı
        swipe2_y = req_panel_top + req_panel_h + 25
        d2.rounded_rectangle([(50, swipe2_y), (w - 50, swipe2_y + 85)], radius=22, fill=pal["pdf_banner_bg"], outline=pal["tag_color_4"], width=2)
        d2.text((80, swipe2_y + 18), "BAŞVURU TARİHLERİ & LİNK İÇİN KAYDIRIN", fill=(255, 255, 255), font=self._get_font(23, bold=True))
        d2.text((w - 140, swipe2_y + 16), "➡️", fill=pal["tag_color_4"], font=self._get_font(34, bold=True))
        d2.text((82, swipe2_y + 52), "Resmi başvuru ekranı ve DM otomasyonu bir sonraki slayttadır.", fill=pal["text_secondary"], font=self._get_font(15))

        draw_carousel_footer(d2, slide_num=2, total_slides=3)
        path2 = self.output_dir / f"carousel_{job_id}_slide_2_{timestamp}.png"
        img2.convert("RGB").save(str(path2), "PNG", quality=98)
        output_paths.append(path2)

        # =====================================================================
        # 3. SLAYT: BAŞVURU & VİRAL ETKİLEŞİM / CTA (CONVERSION SLIDE - 1080x1350)
        # =====================================================================
        img3 = Image.new("RGBA", (w, h), (0, 0, 0, 255))
        d3 = ImageDraw.Draw(img3)
        self._draw_lux_background(d3, img3, pal["bg_top"], pal["bg_bottom"], pal["accent_glow"], width=w, height=h)
        d3 = ImageDraw.Draw(img3)
        d3.rounded_rectangle([(20, 20), (w - 20, h - 20)], radius=24, outline=(pal["border"][0], pal["border"][1], pal["border"][2], 140), width=1)
        d3.rounded_rectangle([(28, 28), (w - 28, h - 28)], radius=20, outline=pal["hero_border"], width=2)
        apply_watermark(img3)
        draw_header_logo(img3, d3, y_offset=54)

        # Slayt Başlığı
        d3.text((54, 175), "BAŞVURU ADIMLARI VE RESMİ TAKVİM", fill=pal["hero_tag"], font=self._get_font(28, bold=True))
        d3.text((54, 215), clean_inst[:65], fill=pal["text_secondary"], font=self._get_font(20, bold=True))

        # Son Başvuru Tarihi Paneli (Vurgulu Kırmızı / Altın Lüks Panel)
        dead_top = 270
        dead_h = 135
        d3.rounded_rectangle([(50, dead_top), (w - 50, dead_top + dead_h)], radius=22, fill=pal["panel_hero"], outline=pal["hero_stripe"], width=2)
        d3.rounded_rectangle([(50, dead_top), (66, dead_top + dead_h)], radius=10, fill=pal["hero_stripe"])
        d3.text((86, dead_top + 20), "SON BAŞVURU TARİHİ (RESMİ SÜRE)", fill=pal["hero_tag"], font=self._get_font(18, bold=True))
        d3.text((86, dead_top + 52), d_str, fill=pal["hero_val"], font=self._get_font(42, bold=True))
        d3.text((86, dead_top + 100), "⚠️ Başvurular son gün mesai bitimi (23:59) itibarıyla kapanacaktır.", fill=pal["text_secondary"], font=self._get_font(16))

        # Başvuru Kanalı Paneli
        chan_top = dead_top + dead_h + 25
        chan_h = 100
        d3.rounded_rectangle([(50, chan_top), (w - 50, chan_top + chan_h)], radius=18, fill=pal["panel"], outline=pal["border"], width=2)
        d3.text((76, chan_top + 18), "BAŞVURU YAPILACAK RESMİ KANAL", fill=pal["tag_color_3"], font=self._get_font(16, bold=True))
        d3.text((76, chan_top + 46), "Kariyer Kapısı İşe Alım (isealimkariyerkapisi.cbiko.gov.tr) / e-Devlet", fill=(255, 255, 255), font=self._get_font(22, bold=True))

        # VİRAL ETKİLEŞİM KUTUSU (INSTAGRAM YORUM-DM BÜYÜME TETİKLEYİCİSİ)
        # Bu kutu kullanıcının yoruma 'KILAVUZ' veya 'LİNK' yazmasını sağlayarak algoritmayı patlatır!
        viral_top = chan_top + chan_h + 30
        viral_h = 290
        d3.rounded_rectangle([(50, viral_top), (w - 50, viral_top + viral_h)], radius=24, fill=(16, 44, 34), outline=(52, 211, 153), width=3)
        d3.rounded_rectangle([(50, viral_top), (66, viral_top + viral_h)], radius=10, fill=(52, 211, 153))

        d3.text((88, viral_top + 24), "💬 BAŞVURU EKRANI VE KILAVUZU DM İLE ALIN!", fill=(52, 211, 153), font=self._get_font(26, bold=True))
        
        viral_call = (
            "Bu gönderinin altına \"KILAVUZ\" veya \"LİNK\" yazın;\n"
            "Resmi başvuru ekranı bağlantısını, kadro kılavuzunu ve\n"
            "tüm şartnameyi ANINDA DM kutunuza gönderelim! 📩"
        )
        f_vcall = self._get_font(22, bold=True)
        vy_c = viral_top + 72
        for vl in viral_call.split("\n"):
            d3.text((88, vy_c), vl, fill=(255, 255, 255), font=f_vcall)
            vy_c += 36

        # Güven ve hız rozeti
        d3.rounded_rectangle([(88, viral_top + 215), (w - 88, viral_top + 265)], radius=12, fill=(24, 68, 52))
        d3.text((106, viral_top + 226), "⚡ Sıfır bekleme • Otomatik asistanımız tarafından hemen iletilir.", fill=(167, 243, 208), font=self._get_font(18, bold=True))

        # Sosyal Eylemler (Kaydet & Arkadaşına Gönder)
        soc_top = viral_top + viral_h + 30
        soc_w = (w - 100 - 30) // 2

        # Sol: Arkadaşına Gönder
        d3.rounded_rectangle([(50, soc_top), (50 + soc_w, soc_top + 90)], radius=18, fill=pal["panel"], outline=pal["border"], width=2)
        d3.text((70, soc_top + 18), "↗️ ARKADAŞINA GÖNDER", fill=pal["tag_color_2"], font=self._get_font(17, bold=True))
        d3.text((70, soc_top + 48), "İş arayan yakının haberdar olsun", fill=pal["text_secondary"], font=self._get_font(16))

        # Sağ: Kaydet Unutma
        d3.rounded_rectangle([(50 + soc_w + 30, soc_top), (w - 50, soc_top + 90)], radius=18, fill=pal["panel"], outline=pal["border"], width=2)
        d3.text((50 + soc_w + 50, soc_top + 18), "📌 KAYDET UNUTMA", fill=pal["hero_stripe"], font=self._get_font(17, bold=True))
        d3.text((50 + soc_w + 50, soc_top + 48), "Son başvuruya kadar elinin altında kalsın", fill=pal["text_secondary"], font=self._get_font(16))

        # Sağ altta Dinamik QR Kod
        qr_target = source_url or "https://kamuilan.sbb.gov.tr/"
        if "ilanDetay.aspx" in qr_target:
            qr_target = "https://kamuilan.sbb.gov.tr/"

        try:
            qr = qrcode.QRCode(version=1, box_size=3, border=2)
            qr.add_data(qr_target)
            qr.make(fit=True)
            qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
            qw, qh = qr_img.size
            qx = w - 50 - qw
            qy = soc_top + 105
            d3.rounded_rectangle([(qx - 4, qy - 4), (qx + qw + 4, qy + qh + 4)], radius=8, fill=(255, 255, 255), outline=pal["hero_stripe"], width=2)
            img3.paste(qr_img, (qx, qy, qx + qw, qy + qh))
            d3.text((54, qy + 10), "Resmi İlan Kılavuzunu İndirmek İçin", fill=pal["text_muted"], font=self._get_font(15, bold=True))
            d3.text((54, qy + 34), "Kameranızla QR Kodu Okutabilirsiniz", fill=pal["hero_tag"], font=self._get_font(18, bold=True))
        except Exception:
            pass

        draw_carousel_footer(d3, slide_num=3, total_slides=3)
        path3 = self.output_dir / f"carousel_{job_id}_slide_3_{timestamp}.png"
        img3.convert("RGB").save(str(path3), "PNG", quality=98)
        output_paths.append(path3)

        logger.info(f"Carousel (3 Slayt) başarıyla üretildi: {[p.name for p in output_paths]}")
        return output_paths

    def generate_story_card(
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
        Instagram Story & Reels Kapak formatında 9:16 Dikey (1080x1920) görsel üretir.
        Orta kısımda Instagram 'Link Çıkartması' (Link Sticker) konulacak alan bırakılmıştır.
        """
        w, h = 1080, 1920
        theme_key = theme or get_system_setting("DEFAULT_CARD_THEME", "OFFICIAL_NAVY")
        pal = CARD_THEMES.get(theme_key, CARD_THEMES["OFFICIAL_NAVY"])
        clean_inst, clean_pos = clean_inst_and_pos(institution, position, title)

        tot_num = total_positions if (total_positions and total_positions > 0) else 1
        pos_badge = f"{tot_num:,} PERSONEL ALIMI".replace(",", ".")
        kpss_str = kpss_requirement or "Resmi Kılavuzda"
        edu_str = education_level or "Resmi Kılavuzda"
        d_str = to_turkish_date_str(deadline)

        img = Image.new("RGBA", (w, h), (0, 0, 0, 255))
        draw = ImageDraw.Draw(img)
        self._draw_lux_background(draw, img, pal["bg_top"], pal["bg_bottom"], pal["accent_glow"], width=w, height=h)
        draw = ImageDraw.Draw(img)

        # Çerçeveler
        draw.rounded_rectangle([(24, 24), (w - 24, h - 24)], radius=32, outline=pal["hero_border"], width=2)

        # Filigran
        if self.logo_path.exists():
            try:
                logo_raw = Image.open(self.logo_path).convert("RGBA")
                wm = logo_raw.resize((700, 700), Image.Resampling.LANCZOS)
                r, g, b, alpha = wm.split()
                alpha = alpha.point(lambda p: int(p * 0.05))
                wm.putalpha(alpha)
                img.alpha_composite(wm, ((w - 700) // 2, (h - 700) // 2))
            except Exception:
                pass

        # Üst Header
        lh = 88
        if self.logo_path.exists():
            try:
                logo_crop = logo_raw.resize((lh, lh), Image.Resampling.LANCZOS)
                mask = Image.new("L", (lh, lh), 0)
                ImageDraw.Draw(mask).ellipse((0, 0, lh, lh), fill=255)
                logo_circ = ImageOps.fit(logo_crop, mask.size, centering=(0.5, 0.5))
                logo_circ.putalpha(mask)
                draw.ellipse([(60, 90), (60 + lh + 8, 90 + lh + 8)], outline=pal["hero_stripe"], width=2)
                img.alpha_composite(logo_circ, (64, 94))
            except Exception:
                pass

        draw.text((170, 96), "KAMU PERSONEL REHBERİ", fill=pal["text_primary"], font=self._get_font(30, bold=True))
        draw.text((172, 140), "T.C. DEVLET TEYİTLİ RESMİ İLAN", fill=pal["hero_tag"], font=self._get_font(16, bold=True))

        # Kurum
        draw.text((64, 230), "RESMİ İLAN DUYURUSU", fill=pal["hero_tag"], font=self._get_font(20, bold=True))
        f_inst = self._get_font(42, bold=True)
        inst_lines = self._wrap_text(clean_inst, f_inst, max_width=w - 130)
        y_cur = 270
        for il in inst_lines[:2]:
            draw.text((64, y_cur), il, fill=pal["text_primary"], font=f_inst)
            y_cur += 52

        # Kontenjan Hero Panel
        y_cur += 30
        draw.rounded_rectangle([(60, y_cur), (w - 60, y_cur + 240)], radius=24, fill=pal["panel_hero"], outline=pal["hero_border"], width=3)
        draw.rounded_rectangle([(60, y_cur), (78, y_cur + 240)], radius=12, fill=pal["hero_stripe"])
        draw.text((100, y_cur + 30), "TOPLAM ALIM KONTENJANI", fill=pal["hero_tag"], font=self._get_font(22, bold=True))
        draw.text((100, y_cur + 72), pos_badge, fill=pal["hero_val"], font=self._get_font(56, bold=True))
        draw.text((100, y_cur + 160), "Başvuru Şartları ve Kadro Dağılımı Yayınlandı", fill=pal["tag_color_2"], font=self._get_font(22, bold=True))

        # Pozisyon
        pos_y = y_cur + 280
        draw.rounded_rectangle([(60, pos_y), (w - 60, pos_y + 220)], radius=24, fill=pal["panel"], outline=pal["border"], width=2)
        draw.text((100, pos_y + 25), "KADRO / BRANŞLAR", fill=pal["tag_color_3"], font=self._get_font(20, bold=True))
        f_p = self._get_font(34, bold=True)
        for idx, pl in enumerate(self._wrap_text(clean_pos, f_p, max_width=w - 180)[:3]):
            draw.text((100, pos_y + 68 + idx * 46), pl, fill=(255, 255, 255), font=f_p)

        # Şartlar Grid
        info_y = pos_y + 260
        draw.rounded_rectangle([(60, info_y), (w - 60, info_y + 160)], radius=20, fill=pal["panel"], outline=pal["border"], width=2)
        draw.text((90, info_y + 24), f"🎯 KPSS Şartı: {kpss_str}", fill=pal["text_primary"], font=self._get_font(24, bold=True))
        draw.text((90, info_y + 68), f"🎓 Mezuniyet: {edu_str}", fill=pal["text_secondary"], font=self._get_font(22, bold=True))
        draw.text((90, info_y + 112), f"🗓 Son Başvuru: {d_str}", fill=pal["hero_tag"], font=self._get_font(22, bold=True))

        # VİRAL REELS & STORY ETKİLEŞİM VE DM KUTUSU (VİDEODAKİ GÖZ ALICI ÇAĞRI)
        link_box_y = info_y + 190
        box_h = 240
        draw.rounded_rectangle([(60, link_box_y), (w - 60, link_box_y + box_h)], radius=26, fill=(16, 44, 34), outline=(52, 211, 153), width=4)
        draw.rounded_rectangle([(60, link_box_y), (76, link_box_y + box_h)], radius=12, fill=(251, 191, 36))

        draw.text((96, link_box_y + 24), "💬 YORUMA \"KILAVUZ\" YAZIN! 👇", fill=(251, 191, 36), font=self._get_font(34, bold=True))
        draw.text((96, link_box_y + 78), "Resmi Başvuru Ekranı & Kadro Dağılımı", fill=(255, 255, 255), font=self._get_font(25, bold=True))
        draw.text((96, link_box_y + 118), "ANINDA DM KUTUNUZA GELSİN! 📩", fill=(52, 211, 153), font=self._get_font(25, bold=True))

        # Kilit & Takip Rozeti
        draw.rounded_rectangle([(96, link_box_y + 170), (w - 96, link_box_y + 218)], radius=12, fill=(24, 68, 52), outline=(52, 211, 153), width=1)
        draw.text((114, link_box_y + 180), "🔒 Bizi Takip Eden Adaylara Kılavuz Kilidi Otomatik Açılır!", fill=(167, 243, 208), font=self._get_font(19, bold=True))


        # Alt Footer
        draw.text((64, h - 140), "Instagram: @kamupersonelrehberi", fill=pal["text_primary"], font=self._get_font(24, bold=True))
        draw.text((64, h - 100), "Telegram: t.me/kamupersonelrehberi", fill=pal["text_secondary"], font=self._get_font(20))

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = self.output_dir / f"story_{job_id}_{theme_key.lower()}_{timestamp}.png"
        img.convert("RGB").save(str(filepath), "PNG", quality=98)
        logger.info(f"Story görseli üretildi: {filepath}")
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

