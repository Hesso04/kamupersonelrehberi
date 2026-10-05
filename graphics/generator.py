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


def to_turkish_date_str(val: Any) -> str:
    """Tarih girdilerini eksiksiz Türkçe ay isimlerine dönüştürür (Örn: 05 Ekim 2026)."""
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

    # İngilizce Ay İsimlerini Türkçeye Kesin Çevir
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


def tr_title(text: str) -> str:
    """Türkçe karakterleri (İ, I, ş, ğ, ü, ö, ç) bozmadan ve birleşik nokta (\u0307) hatası üretmeden başlık yapar."""
    if not text:
        return ""
    words = text.split()
    res = []
    for w in words:
        if not w:
            continue
        w_clean = w.replace("İ", "i").replace("I", "ı")
        first = w_clean[0].upper()
        if w_clean[0] == "i":
            first = "İ"
        elif w_clean[0] == "ı":
            first = "I"
        rest = w_clean[1:].lower().replace("\u0307", "")
        res.append(first + rest)
    return " ".join(res)


# =============================================================================
# PROFESYONEL KURUMSAL AFİŞ RENK & TASARIM TEMALARI (LUXURY PALETTES)
# =============================================================================
CARD_THEMES: Dict[str, Dict[str, Any]] = {
    "ROYAL_CRIMSON": {
        "id": "ROYAL_CRIMSON",
        "name": "🔴 Kraliyet Bordo & Bronz (Resmi Prestij)",
        "desc": "Zengin kadife bordo degrade, asil altın ışıltısı ve yüksek kontrastlı vitrin tasarımı",
        "bg_top": (24, 6, 14),
        "bg_bottom": (42, 10, 24),
        "panel": (52, 14, 30),
        "panel_hero": (68, 18, 38),
        "border": (115, 34, 62),
        "hero_border": (251, 146, 60),
        "hero_stripe": (245, 158, 11),
        "hero_tag": (253, 186, 116),
        "hero_val": (255, 255, 255),
        "badge_bg": (48, 12, 28),
        "badge_border": (251, 191, 36),
        "badge_text": (255, 255, 255),
        "badge_dot": (251, 191, 36),
        "tag_color_1": (251, 146, 60),
        "tag_color_2": (251, 191, 36),
        "val_color_1": (255, 255, 255),
        "val_color_2": (251, 191, 36),
        "pdf_banner_bg": (46, 12, 26),
        "pdf_banner_border": (251, 146, 60),
        "accent_glow": (251, 146, 60),
        "text_primary": (255, 255, 255),
        "text_secondary": (254, 205, 211),
        "text_muted": (168, 110, 125),
    },
    "OFFICIAL_NAVY": {
        "id": "OFFICIAL_NAVY",
        "name": "🏛️ Kurumsal Lacivert & Altın (Official Prestige)",
        "desc": "Ağırbaşlı devlet kurumu prestiji, derin gece laciverti ve asil altın ışıltısı",
        "bg_top": (8, 16, 36),
        "bg_bottom": (14, 26, 52),
        "panel": (18, 34, 66),
        "panel_hero": (26, 46, 88),
        "border": (48, 76, 135),
        "hero_border": (245, 158, 11),
        "hero_stripe": (245, 158, 11),
        "hero_tag": (56, 189, 248),
        "hero_val": (251, 191, 36),
        "badge_bg": (16, 40, 76),
        "badge_border": (245, 158, 11),
        "badge_text": (255, 255, 255),
        "badge_dot": (245, 158, 11),
        "tag_color_1": (56, 189, 248),
        "tag_color_2": (251, 191, 36),
        "val_color_1": (56, 189, 248),
        "val_color_2": (251, 191, 36),
        "pdf_banner_bg": (16, 42, 80),
        "pdf_banner_border": (56, 189, 248),
        "accent_glow": (251, 191, 36),
        "text_primary": (255, 255, 255),
        "text_secondary": (148, 163, 184),
        "text_muted": (100, 116, 139),
    },
    "DARK_NOIR": {
        "id": "DARK_NOIR",
        "name": "⬛ Minimalist Noir (Siyah & Beyaz & Titanyum)",
        "desc": "Ultra modern, şık monokrom, yüksek kontrastlı editoryal prestij tasarım",
        "bg_top": (10, 10, 14),
        "bg_bottom": (18, 18, 24),
        "panel": (24, 24, 30),
        "panel_hero": (32, 32, 40),
        "border": (68, 74, 88),
        "hero_border": (255, 255, 255),
        "hero_stripe": (255, 255, 255),
        "hero_tag": (160, 165, 175),
        "hero_val": (255, 255, 255),
        "badge_bg": (26, 26, 34),
        "badge_border": (210, 215, 225),
        "badge_text": (255, 255, 255),
        "badge_dot": (255, 255, 255),
        "tag_color_1": (255, 255, 255),
        "tag_color_2": (210, 215, 225),
        "val_color_1": (255, 255, 255),
        "val_color_2": (230, 235, 245),
        "pdf_banner_bg": (26, 26, 32),
        "pdf_banner_border": (190, 195, 205),
        "accent_glow": (255, 255, 255),
        "text_primary": (255, 255, 255),
        "text_secondary": (175, 180, 190),
        "text_muted": (120, 125, 135),
    },
    "EMERALD_MINT": {
        "id": "EMERALD_MINT",
        "name": "🟢 Zümrüt Yeşili & Kamu (Executive Mint)",
        "desc": "Taze, resmi, %100 onaylı ve güven veren derin orman & zümrüt tasarımı",
        "bg_top": (6, 26, 18),
        "bg_bottom": (10, 44, 30),
        "panel": (14, 54, 38),
        "panel_hero": (20, 74, 52),
        "border": (30, 96, 68),
        "hero_border": (52, 211, 153),
        "hero_stripe": (52, 211, 153),
        "hero_tag": (110, 231, 183),
        "hero_val": (255, 255, 255),
        "badge_bg": (10, 48, 34),
        "badge_border": (52, 211, 153),
        "badge_text": (255, 255, 255),
        "badge_dot": (52, 211, 153),
        "tag_color_1": (110, 231, 183),
        "tag_color_2": (251, 191, 36),
        "val_color_1": (255, 255, 255),
        "val_color_2": (251, 191, 36),
        "pdf_banner_bg": (14, 56, 40),
        "pdf_banner_border": (52, 211, 153),
        "accent_glow": (52, 211, 153),
        "text_primary": (255, 255, 255),
        "text_secondary": (167, 243, 208),
        "text_muted": (110, 150, 130),
    },
    "CYBER_VIOLET": {
        "id": "CYBER_VIOLET",
        "name": "🟣 Gece Moru & Neon Siber (Kamu Personel Rehberi Orijinal)",
        "desc": "Marka logosuyla kusursuz eşleşen neon mor, elektrik mavisi ve altın vurgular",
        "bg_top": (12, 10, 26),
        "bg_bottom": (26, 16, 48),
        "panel": (28, 24, 58),
        "panel_hero": (38, 30, 78),
        "border": (78, 50, 125),
        "hero_border": (168, 85, 247),
        "hero_stripe": (251, 191, 36),
        "hero_tag": (56, 189, 248),
        "hero_val": (251, 191, 36),
        "badge_bg": (36, 22, 68),
        "badge_border": (168, 85, 247),
        "badge_text": (255, 255, 255),
        "badge_dot": (168, 85, 247),
        "tag_color_1": (56, 189, 248),
        "tag_color_2": (251, 191, 36),
        "val_color_1": (56, 189, 248),
        "val_color_2": (251, 191, 36),
        "pdf_banner_bg": (34, 22, 60),
        "pdf_banner_border": (168, 85, 247),
        "accent_glow": (168, 85, 247),
        "text_primary": (255, 255, 255),
        "text_secondary": (192, 132, 252),
        "text_muted": (125, 115, 145),
    }
}


class JobCardGenerator:
    """
    Yeni Nesil Yüksek Çözünürlüklü Kurumsal İlan Vitrini Motoru (v2.0).
    - 1080x1080 kare (Instagram Akış & Profil Izgarası, Facebook, Telegram için kusursuz)
    - Pürüzsüz degrade ve atmosferik lüks derinlik ışıltısı
    - Glassmorphism yarı şeffaf bilgi kartları
    - Akıllı dinamik metin boyutlandırma (asla taşmayan unvanlar)
    - Çoklu kanal (Telegram, Instagram, Facebook) marka koruma altlığı
    - Dinamik doğrulanmış QR kod entegrasyonu
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

        # Font Tanımları (Segoe UI veya Arial)
        self.font_regular_path = Path("C:/Windows/Fonts/segoeui.ttf")
        self.font_bold_path = Path("C:/Windows/Fonts/segoeuib.ttf")

        if not self.font_regular_path.exists():
            self.font_regular_path = Path("C:/Windows/Fonts/arial.ttf")
            self.font_bold_path = Path("C:/Windows/Fonts/arialbd.ttf")

    def _get_font(self, size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
        path = self.font_bold_path if bold else self.font_regular_path
        try:
            return ImageFont.truetype(str(path), size=size)
        except Exception:
            return ImageFont.load_default()

    def _draw_lux_background(
        self,
        draw: ImageDraw.ImageDraw,
        img: Image.Image,
        c_top: Tuple[int, int, int],
        c_bottom: Tuple[int, int, int],
        accent: Tuple[int, int, int]
    ) -> None:
        """Pürüzsüz lüks dikey degrade ve yumuşak atmosferik ışıltı çizer."""
        # 1. Dikey Degrade
        for y in range(self.HEIGHT):
            ratio = y / self.HEIGHT
            r = int(c_top[0] * (1 - ratio) + c_bottom[0] * ratio)
            g = int(c_top[1] * (1 - ratio) + c_bottom[1] * ratio)
            b = int(c_top[2] * (1 - ratio) + c_bottom[2] * ratio)
            draw.line([(0, y), (self.WIDTH, y)], fill=(r, g, b, 255))

        # 2. Üst Vurgu Ambient Işıltısı (Yumuşak Parlaklık Katmanı)
        glow_layer = Image.new("RGBA", (self.WIDTH, self.HEIGHT), (0, 0, 0, 0))
        d_glow = ImageDraw.Draw(glow_layer)
        # Sağ üst köşeye ve merkez üste yumuşak renk halkası
        d_glow.ellipse(
            [(self.WIDTH - 380, -120), (self.WIDTH + 180, 420)],
            fill=(accent[0], accent[1], accent[2], 26)
        )
        d_glow.ellipse(
            [(-150, 240), (320, 720)],
            fill=(accent[0], accent[1], accent[2], 14)
        )
        glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(50))
        img.alpha_composite(glow_layer)

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
        theme: Optional[str] = None
    ) -> Path:
        """
        1080x1080 boyutunda seçilen tema paletiyle üst düzey kurumsal ilan vitrini afişi üretir.
        """
        theme_key = theme or get_system_setting("DEFAULT_CARD_THEME", "ROYAL_CRIMSON")
        pal = CARD_THEMES.get(theme_key, CARD_THEMES["ROYAL_CRIMSON"])

        img = Image.new("RGBA", (self.WIDTH, self.HEIGHT), (0, 0, 0, 255))
        draw = ImageDraw.Draw(img)

        # 1. Atmosferik Lüks Degrade ve Derinlik Işıltısı
        self._draw_lux_background(draw, img, pal["bg_top"], pal["bg_bottom"], pal["accent_glow"])
        draw = ImageDraw.Draw(img)  # Composite sonrası çizim nesnesini tazele

        # 2. Üst Lüks Neon Işıltı Çizgisi
        for i in range(4):
            alpha = int(255 * (1 - i / 4))
            draw.line([(0, i), (self.WIDTH, i)], fill=(pal["accent_glow"][0], pal["accent_glow"][1], pal["accent_glow"][2], alpha))

        # Dış Zarif Çift Çerçeve
        draw.rounded_rectangle([(24, 24), (self.WIDTH - 24, self.HEIGHT - 24)], radius=24, outline=(pal["border"][0], pal["border"][1], pal["border"][2], 120), width=1)
        draw.rounded_rectangle([(32, 32), (self.WIDTH - 32, self.HEIGHT - 32)], radius=20, outline=pal["border"], width=2)

        # 3. ÇALINMAYA KARŞI MERKEZİ ŞEFFAF FİLİGRAN (WATERMARK)
        if self.logo_path.exists():
            try:
                logo_raw = Image.open(self.logo_path).convert("RGBA")
                wm_size = (540, 540)
                wm = logo_raw.resize(wm_size, Image.Resampling.LANCZOS)
                r, g, b, alpha = wm.split()
                alpha = alpha.point(lambda p: int(p * 0.055))
                wm.putalpha(alpha)
                wx = (self.WIDTH - wm_size[0]) // 2
                wy = (self.HEIGHT - wm_size[1]) // 2 + 15
                img.alpha_composite(wm, (wx, wy))
            except Exception as e:
                logger.debug(f"Filigran yerleştirme uyarısı: {e}")

        # 4. ÜST HEADER ALANI
        # Sol Rozet: Orijinal Marka Logosu
        if self.logo_path.exists():
            try:
                lh = 76
                logo_crop = logo_raw.resize((lh, lh), Image.Resampling.LANCZOS)
                mask = Image.new("L", (lh, lh), 0)
                d_mask = ImageDraw.Draw(mask)
                d_mask.ellipse((0, 0, lh, lh), fill=255)
                logo_circ = ImageOps.fit(logo_crop, mask.size, centering=(0.5, 0.5))
                logo_circ.putalpha(mask)

                # Logo halkası ve gölge
                draw.ellipse([(52, 46), (52 + lh + 12, 46 + lh + 12)], outline=pal["hero_stripe"], width=2)
                img.alpha_composite(logo_circ, (58, 52))
            except Exception as le:
                logger.debug(f"Logo render uyarısı: {le}")

        f_brand = self._get_font(25, bold=True)
        draw.text((154, 52), "KAMU PERSONEL REHBERİ", fill=pal["text_primary"], font=f_brand)
        f_slogan = self._get_font(13, bold=True)
        draw.text((156, 86), "GÜNCEL • DOĞRU • RESMİ DEVLET TEYİTLİ", fill=pal["text_secondary"], font=f_slogan)

        # Sağ Üst Doğrulanmış Rozeti (Pill)
        badge_text = "RESMİ DEVLET İLANI"
        f_badge = self._get_font(15, bold=True)
        bbox = f_badge.getbbox(badge_text)
        bw = bbox[2] - bbox[0] + 52
        bx = self.WIDTH - 55 - bw
        draw.rounded_rectangle([(bx, 60), (bx + bw, 102)], radius=14, fill=pal["badge_bg"], outline=pal["badge_border"], width=2)
        # Rozet içi yeşil/altın canlı durum noktası
        draw.ellipse([(bx + 16, 75), (bx + 26, 85)], fill=pal["badge_dot"])
        draw.text((bx + 34, 70), badge_text, fill=pal["badge_text"], font=f_badge)

        # Ayırıcı Çizgi
        draw.line([(55, 142), (self.WIDTH - 55, 142)], fill=pal["border"], width=1)

        # 5. KAMU KURUMU BAŞLIĞI
        draw.ellipse([(60, 166), (72, 178)], fill=pal["hero_stripe"])
        draw.text((80, 163), "KAMU KURUMU / BAKANLIK", fill=pal["hero_tag"], font=self._get_font(14, bold=True))

        clean_inst = (institution or "T.C. KAMU KURUMU").upper().strip()
        f_inst = self._get_font(32, bold=True)
        inst_lines = self._wrap_text(clean_inst, f_inst, max_width=940)
        curr_y = 192
        for line in inst_lines[:2]:
            draw.text((60, curr_y), line, fill=pal["text_primary"], font=f_inst)
            curr_y += 42

        # 6. POZİSYON HERO KARTI (BÜYÜK VURGU PANOSU)
        hero_y = curr_y + 10
        hero_h = 112
        # Yarı saydam lüks kart
        draw.rounded_rectangle([(55, hero_y), (self.WIDTH - 55, hero_y + hero_h)], radius=18, fill=pal["panel_hero"], outline=pal["hero_border"], width=2)
        # Sol amber / vurgu dikey şerit
        draw.rounded_rectangle([(55, hero_y), (67, hero_y + hero_h)], radius=6, fill=pal["hero_stripe"])

        pos_raw = (position or "Personel Alımı").strip()
        clean_pos = re.sub(r"^\s*(\d+\s*)+", "", pos_raw)
        clean_pos = re.sub(r"\s*(?:alacak|alımı|temin edilecek|alınacaktır|alınacak|alım ilanı).*$", "", clean_pos, flags=re.IGNORECASE)
        clean_pos = clean_pos.strip(" -:,")
        clean_pos = re.sub(r"\bpersoneli\b", "Personel", clean_pos, flags=re.IGNORECASE)
        clean_pos = tr_title(clean_pos) or "Kamu Personeli"

        draw.text((85, hero_y + 16), "ALIM YAPILACAK KADRO / POZİSYON", fill=pal["hero_tag"], font=self._get_font(13, bold=True))
        
        # Dinamik font boyutu (Uzun başlıklarda küçülterek kusursuz sığdırma)
        pos_font_size = 34 if len(clean_pos) < 45 else 28
        f_pos = self._get_font(pos_font_size, bold=True)
        pos_lines = self._wrap_text(clean_pos, f_pos, max_width=890)
        p_y = hero_y + 44 if len(pos_lines) == 1 else hero_y + 36
        for pline in pos_lines[:2]:
            draw.text((85, p_y), pline, fill=pal["hero_val"], font=f_pos)
            p_y += (pos_font_size + 6)

        # 7. BİLGİ KARTLARI (2x2 GRID - KESİNTİSİZ ÇİFT SATIR DESTEKLİ)
        grid_top = hero_y + hero_h + 22
        col_w = 465
        row_h = 146
        gap_x = 40
        gap_y = 18
        left1 = 55
        left2 = left1 + col_w + gap_x

        pos_count_str = f"{total_positions} Kişi" if total_positions else "İlanda Belirtilmiştir"
        kpss_str = kpss_requirement or "Resmi İlanda Belirtilmiştir"
        edu_str = education_level or "İlgili Bölüm Mezuniyeti"
        deadline_str = to_turkish_date_str(deadline)

        tiles = [
            {
                "rect": [(left1, grid_top), (left1 + col_w, grid_top + row_h)],
                "tag": "KONTENJAN",
                "val": pos_count_str,
                "color": pal["val_color_1"],
                "tag_color": pal["tag_color_1"]
            },
            {
                "rect": [(left2, grid_top), (left2 + col_w, grid_top + row_h)],
                "tag": "KPSS ŞARTI",
                "val": kpss_str,
                "color": pal["val_color_2"],
                "tag_color": pal["tag_color_2"]
            },
            {
                "rect": [(left1, grid_top + row_h + gap_y), (left1 + col_w, grid_top + 2 * row_h + gap_y)],
                "tag": "ÖĞRENİM DÜZEYİ",
                "val": edu_str,
                "color": pal["text_primary"],
                "tag_color": pal["tag_color_1"]
            },
            {
                "rect": [(left2, grid_top + row_h + gap_y), (left2 + col_w, grid_top + 2 * row_h + gap_y)],
                "tag": "SON BAŞVURU TARİHİ",
                "val": deadline_str,
                "color": pal["val_color_2"],
                "tag_color": pal["tag_color_2"]
            }
        ]

        f_tag = self._get_font(15, bold=True)
        f_val = self._get_font(23, bold=True)

        for t in tiles:
            r = t["rect"]
            draw.rounded_rectangle(r, radius=16, fill=pal["panel"], outline=pal["border"], width=2)
            
            # Canlı etiket noktası ve başlığı
            draw.ellipse([(r[0][0] + 24, r[0][1] + 25), (r[0][0] + 34, r[0][1] + 35)], fill=t["tag_color"])
            draw.text((r[0][0] + 44, r[0][1] + 20), t["tag"], fill=t["tag_color"], font=f_tag)

            # Değer metni (2 satıra kadar düzgün sarım)
            val_lines = self._wrap_text(t["val"], f_val, max_width=col_w - 45)
            vy = r[0][1] + 62 if len(val_lines) == 1 else r[0][1] + 52
            for vline in val_lines[:2]:
                draw.text((r[0][0] + 25, vy), vline, fill=t["color"], font=f_val)
                vy += 32

        # 8. RESMİ KILAVUZ BANT ŞERİDİ
        banner_y = grid_top + 2 * row_h + gap_y + 20
        banner_fill = pal["pdf_banner_bg"]
        banner_outline = pal["pdf_banner_border"]
        banner_text = "RESMİ BAŞVURU KILAVUZU & ŞARTNAME (PDF) EKLENMİŞTİR" if has_pdf else "RESMİ BAŞVURU VE DUYURU SİSTEMDE MEVCUTTUR"

        draw.rounded_rectangle([(55, banner_y), (self.WIDTH - 55, banner_y + 54)], radius=14, fill=banner_fill, outline=banner_outline, width=2)
        draw.ellipse([(76, banner_y + 21), (88, banner_y + 33)], fill=banner_outline)
        f_banner = self._get_font(16, bold=True)
        draw.text((100, banner_y + 17), banner_text, fill=pal["text_primary"], font=f_banner)

        # 9. ALT BİLGİ & ÇALINMAYA KARŞI GÜVENLİK ALANI (FOOTER)
        footer_y = banner_y + 70
        draw.line([(55, footer_y), (self.WIDTH - 55, footer_y)], fill=pal["border"], width=1)

        # Çok Kanallı Sosyal Medya İmzası
        draw.text((60, footer_y + 16), "Telegram: @kamupersonelrehberi", fill=pal["text_primary"], font=self._get_font(21, bold=True))
        draw.text((60, footer_y + 46), "Instagram: @kamupersonelrehberi   •   Facebook: /kamupersonelrehberi", fill=pal["text_secondary"], font=self._get_font(15, bold=True))
        draw.text((60, footer_y + 72), "Telif Hakları Saklıdır • %100 Doğrulanmış Resmi Kamu İlanı • İzinsiz Alınamaz", fill=pal["text_muted"], font=self._get_font(12))

        # Sağ Dinamik QR Kod
        qr_target = source_url or "https://t.me/kamupersonelrehberi"
        if "ilanDetay.aspx" in qr_target:
            qr_target = "https://kamuilan.sbb.gov.tr/"

        try:
            qr = qrcode.QRCode(version=1, box_size=3, border=2)
            qr.add_data(qr_target)
            qr.make(fit=True)
            qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
            qr_w, qr_h = qr_img.size

            qx = self.WIDTH - 60 - qr_w
            qy = footer_y + 10

            draw.rounded_rectangle([(qx - 8, qy - 8), (qx + qr_w + 8, qy + qr_h + 8)], radius=10, fill=(255, 255, 255), outline=pal["border"], width=2)
            img.paste(qr_img, (qx, qy, qx + qr_w, qy + qr_h))

            draw.text((qx - 190, footer_y + 26), "RESMİ KILAVUZ", fill=pal["text_muted"], font=self._get_font(13, bold=True))
            draw.text((qx - 190, footer_y + 48), "QR KODU OKUTUN", fill=pal["val_color_2"], font=self._get_font(15, bold=True))
        except Exception as qe:
            logger.warning(f"QR kod oluşturulamadı: {qe}")

        # 10. RGB'ye Dönüştür ve Kaydet
        final_img = img.convert("RGB")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"ilan_kart_{job_id}_{theme_key.lower()}_{timestamp}.png"
        filepath = self.output_dir / filename
        final_img.save(str(filepath), "PNG", quality=95)

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
                institution="T.C. Cumhurbaşkanlığı SBB",
                position="Kamu ve Bilişim Uzmanı Alımı",
                total_positions=50,
                kpss_requirement="KPSS P3 En Az 70",
                education_level="Lisans / Ön Lisans",
                deadline="15 Ekim 2026",
                source_url="https://kamuilan.sbb.gov.tr/",
                has_pdf=True,
                theme=theme_key
            )
            shutil.copyfile(gen_path, sample_path)
        return sample_path
