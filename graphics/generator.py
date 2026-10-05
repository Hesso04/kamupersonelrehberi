import re
import os
from pathlib import Path
from typing import Optional, Tuple, List, Any, Dict
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont, ImageOps
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
# GELİŞMİŞ GÖRSEL VİTRİNİ RENK VE STİL TEMALARI
# =============================================================================
CARD_THEMES: Dict[str, Dict[str, Any]] = {
    "DARK_NOIR": {
        "id": "DARK_NOIR",
        "name": "⬛ Minimalist Noir (Siyah & Beyaz & Titanyum)",
        "desc": "Ultra modern, şık monokrom, yüksek kontrastlı prestij editoryal tasarım",
        "bg_top": (10, 10, 12),
        "bg_bottom": (18, 18, 22),
        "panel": (22, 22, 26),
        "panel_hero": (30, 30, 36),
        "border": (65, 70, 80),
        "hero_border": (255, 255, 255),
        "hero_stripe": (255, 255, 255),
        "hero_tag": (160, 165, 175),
        "hero_val": (255, 255, 255),
        "badge_bg": (26, 26, 32),
        "badge_border": (200, 205, 215),
        "badge_text": (255, 255, 255),
        "badge_dot": (255, 255, 255),
        "tag_color_1": (255, 255, 255),
        "tag_color_2": (210, 215, 225),
        "val_color_1": (255, 255, 255),
        "val_color_2": (230, 235, 245),
        "pdf_banner_bg": (24, 24, 28),
        "pdf_banner_border": (180, 185, 195),
        "accent_glow": (255, 255, 255),
        "text_primary": (255, 255, 255),
        "text_secondary": (170, 175, 185),
        "text_muted": (115, 120, 130),
    },
    "OFFICIAL_NAVY": {
        "id": "OFFICIAL_NAVY",
        "name": "🏛️ Kurumsal Lacivert & Altın (Official Prestige)",
        "desc": "Ağırbaşlı devlet kurumu prestiji, gece laciverti ve asil altın ışıltısı",
        "bg_top": (10, 18, 38),
        "bg_bottom": (15, 24, 48),
        "panel": (18, 32, 60),
        "panel_hero": (24, 42, 80),
        "border": (45, 70, 125),
        "hero_border": (245, 158, 11),
        "hero_stripe": (245, 158, 11),
        "hero_tag": (56, 189, 248),
        "hero_val": (251, 191, 36),
        "badge_bg": (15, 38, 70),
        "badge_border": (245, 158, 11),
        "badge_text": (255, 255, 255),
        "badge_dot": (245, 158, 11),
        "tag_color_1": (56, 189, 248),
        "tag_color_2": (251, 191, 36),
        "val_color_1": (56, 189, 248),
        "val_color_2": (251, 191, 36),
        "pdf_banner_bg": (16, 40, 75),
        "pdf_banner_border": (56, 189, 248),
        "accent_glow": (251, 191, 36),
        "text_primary": (255, 255, 255),
        "text_secondary": (148, 163, 184),
        "text_muted": (100, 116, 139),
    },
    "EMERALD_MINT": {
        "id": "EMERALD_MINT",
        "name": "🟢 Zümrüt Yeşili & Kamu (Executive Mint)",
        "desc": "Taze, resmi, %100 onaylı ve güven veren derin orman & zümrüt tasarımı",
        "bg_top": (6, 26, 20),
        "bg_bottom": (10, 44, 32),
        "panel": (13, 53, 40),
        "panel_hero": (18, 72, 54),
        "border": (28, 95, 70),
        "hero_border": (52, 211, 153),
        "hero_stripe": (52, 211, 153),
        "hero_tag": (110, 231, 183),
        "hero_val": (255, 255, 255),
        "badge_bg": (8, 48, 36),
        "badge_border": (52, 211, 153),
        "badge_text": (255, 255, 255),
        "badge_dot": (52, 211, 153),
        "tag_color_1": (110, 231, 183),
        "tag_color_2": (251, 191, 36),
        "val_color_1": (255, 255, 255),
        "val_color_2": (251, 191, 36),
        "pdf_banner_bg": (12, 55, 42),
        "pdf_banner_border": (52, 211, 153),
        "accent_glow": (52, 211, 153),
        "text_primary": (255, 255, 255),
        "text_secondary": (167, 243, 208),
        "text_muted": (107, 148, 130),
    },
    "CYBER_VIOLET": {
        "id": "CYBER_VIOLET",
        "name": "🟣 Gece Moru & Neon Siber (Kamu Personel Rehberi Orijinal)",
        "desc": "Marka logosuyla eşleşen neon mor, elektrik mavisi ve altın vurgular",
        "bg_top": (11, 14, 25),
        "bg_bottom": (26, 16, 48),
        "panel": (26, 24, 56),
        "panel_hero": (36, 30, 75),
        "border": (75, 48, 120),
        "hero_border": (168, 85, 247),
        "hero_stripe": (251, 191, 36),
        "hero_tag": (56, 189, 248),
        "hero_val": (251, 191, 36),
        "badge_bg": (35, 20, 65),
        "badge_border": (168, 85, 247),
        "badge_text": (255, 255, 255),
        "badge_dot": (168, 85, 247),
        "tag_color_1": (56, 189, 248),
        "tag_color_2": (251, 191, 36),
        "val_color_1": (56, 189, 248),
        "val_color_2": (251, 191, 36),
        "pdf_banner_bg": (32, 20, 58),
        "pdf_banner_border": (168, 85, 247),
        "accent_glow": (168, 85, 247),
        "text_primary": (255, 255, 255),
        "text_secondary": (192, 132, 252),
        "text_muted": (120, 110, 140),
    },
    "ROYAL_CRIMSON": {
        "id": "ROYAL_CRIMSON",
        "name": "🔴 Kraliyet Bordo & Bronz (Urgent / VIP İlan)",
        "desc": "Çarpıcı koyu bordo zemin, bronz altın ve yakut detaylarıyla acil/flaş alımlar",
        "bg_top": (30, 10, 18),
        "bg_bottom": (48, 14, 28),
        "panel": (58, 18, 33),
        "panel_hero": (75, 22, 42),
        "border": (120, 38, 65),
        "hero_border": (251, 146, 60),
        "hero_stripe": (251, 146, 60),
        "hero_tag": (251, 146, 60),
        "hero_val": (255, 255, 255),
        "badge_bg": (60, 15, 30),
        "badge_border": (251, 146, 60),
        "badge_text": (255, 255, 255),
        "badge_dot": (251, 146, 60),
        "tag_color_1": (251, 146, 60),
        "tag_color_2": (251, 191, 36),
        "val_color_1": (255, 255, 255),
        "val_color_2": (251, 191, 36),
        "pdf_banner_bg": (50, 15, 28),
        "pdf_banner_border": (251, 146, 60),
        "accent_glow": (251, 146, 60),
        "text_primary": (255, 255, 255),
        "text_secondary": (253, 164, 175),
        "text_muted": (150, 100, 115),
    }
}


class JobCardGenerator:
    """
    Yüksek Çözünürlüklü Çok Temalı Kurumsal İlan Vitrini Motoru.
    Kullanıcının tercihine göre Siyah-Beyaz Monokrom, Kurumsal Lacivert,
    Zümrüt Yeşili, Gece Moru ve Kraliyet Bordo temalarıyla 1080x1080 piksel
    profesyonel sosyal medya afişleri üretir.
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

        # Font Tanımları (Öncelik: Segoe UI, Alternatif: Arial / Sans-serif)
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

    def _draw_gradient(self, draw: ImageDraw.ImageDraw, c_top: Tuple[int, int, int], c_bottom: Tuple[int, int, int]) -> None:
        """Pürüzsüz dikey degrade çizer."""
        for y in range(self.HEIGHT):
            ratio = y / self.HEIGHT
            r = int(c_top[0] * (1 - ratio) + c_bottom[0] * ratio)
            g = int(c_top[1] * (1 - ratio) + c_bottom[1] * ratio)
            b = int(c_top[2] * (1 - ratio) + c_bottom[2] * ratio)
            draw.line([(0, y), (self.WIDTH, y)], fill=(r, g, b, 255))

    def _draw_tech_grid(self, draw: ImageDraw.ImageDraw, border_color: Tuple[int, int, int]) -> None:
        """Arka plana lüks ve modern hava katan şeffaf geometrik teknoloji çizgileri ekler."""
        grid_alpha = (border_color[0], border_color[1], border_color[2], 30)
        # Hafif yatay ve dikey çizgiler
        for y in range(160, self.HEIGHT - 120, 180):
            draw.line([(40, y), (self.WIDTH - 40, y)], fill=grid_alpha, width=1)
        for x in range(180, self.WIDTH, 240):
            draw.line([(x, 140), (x, self.HEIGHT - 120)], fill=grid_alpha, width=1)

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
        # Aktif temayı belirle
        theme_key = theme or get_system_setting("DEFAULT_CARD_THEME", "DARK_NOIR")
        pal = CARD_THEMES.get(theme_key, CARD_THEMES["DARK_NOIR"])

        img = Image.new("RGBA", (self.WIDTH, self.HEIGHT), (0, 0, 0, 255))
        draw = ImageDraw.Draw(img)

        # 1. Degrade Arka Plan
        self._draw_gradient(draw, pal["bg_top"], pal["bg_bottom"])

        # 2. Arka Plan Geometrik Teknoloji Çizgileri
        self._draw_tech_grid(draw, pal["border"])

        # 3. Üst Neon / Vurgu Işıltı Çizgisi
        for i in range(5):
            draw.line([(0, i), (self.WIDTH, i)], fill=pal["accent_glow"])

        # Dış Kurumsal Çerçeve
        draw.rounded_rectangle([(30, 30), (self.WIDTH - 30, self.HEIGHT - 30)], radius=24, outline=pal["border"], width=2)

        # 4. ÇALINMAYA KARŞI MERKEZİ ŞEFFAF FİLİGRAN (WATERMARK)
        if self.logo_path.exists():
            try:
                logo_raw = Image.open(self.logo_path).convert("RGBA")
                wm_size = (580, 580)
                wm = logo_raw.resize(wm_size, Image.Resampling.LANCZOS)
                r, g, b, alpha = wm.split()
                alpha = alpha.point(lambda p: int(p * 0.065))  # Zarafetinde şeffaflık
                wm.putalpha(alpha)
                wx = (self.WIDTH - wm_size[0]) // 2
                wy = (self.HEIGHT - wm_size[1]) // 2 + 25
                img.alpha_composite(wm, (wx, wy))
            except Exception as e:
                logger.debug(f"Filigran yerleştirme uyarısı: {e}")

        # 5. ÜST HEADER ALANI
        # Sol Rozet: Orijinal Marka Logosu
        if self.logo_path.exists():
            try:
                lh = 80
                logo_crop = logo_raw.resize((lh, lh), Image.Resampling.LANCZOS)
                mask = Image.new("L", (lh, lh), 0)
                d_mask = ImageDraw.Draw(mask)
                d_mask.ellipse((0, 0, lh, lh), fill=255)
                logo_circ = ImageOps.fit(logo_crop, mask.size, centering=(0.5, 0.5))
                logo_circ.putalpha(mask)

                draw.ellipse([(54, 44), (54 + lh + 12, 44 + lh + 12)], outline=pal["border"], width=2)
                img.alpha_composite(logo_circ, (60, 50))
            except Exception as le:
                logger.debug(f"Logo render uyarısı: {le}")

        f_brand = self._get_font(25, bold=True)
        draw.text((156, 54), "KAMU PERSONEL REHBERİ", fill=pal["text_primary"], font=f_brand)
        f_slogan = self._get_font(13, bold=True)
        draw.text((158, 88), "GÜNCEL • DOĞRU • RESMİ TEYİTLİ", fill=pal["text_secondary"], font=f_slogan)

        # Sağ Üst Doğrulanmış Rozeti (Pill)
        badge_text = "RESMİ DEVLET İLANI"
        f_badge = self._get_font(15, bold=True)
        bbox = f_badge.getbbox(badge_text)
        bw = bbox[2] - bbox[0] + 52
        bx = self.WIDTH - 60 - bw
        draw.rounded_rectangle([(bx, 62), (bx + bw, 102)], radius=12, fill=pal["badge_bg"], outline=pal["badge_border"], width=2)
        draw.ellipse([(bx + 14, 75), (bx + 26, 87)], fill=pal["badge_dot"])
        draw.text((bx + 36, 70), badge_text, fill=pal["badge_text"], font=f_badge)

        # Ayırıcı Çizgi
        draw.line([(55, 145), (self.WIDTH - 55, 145)], fill=pal["border"], width=1)

        # 6. KAMU KURUMU BAŞLIĞI
        draw.ellipse([(60, 170), (70, 180)], fill=pal["hero_stripe"])
        draw.text((78, 166), "KAMU KURUMU", fill=pal["hero_tag"], font=self._get_font(14, bold=True))

        clean_inst = (institution or "T.C. KAMU KURUMU").upper().strip()
        f_inst = self._get_font(33, bold=True)
        inst_lines = self._wrap_text(clean_inst, f_inst, max_width=940)
        curr_y = 196
        for line in inst_lines[:2]:
            draw.text((60, curr_y), line, fill=pal["text_primary"], font=f_inst)
            curr_y += 44

        # 7. POZİSYON HERO KARTI (BÜYÜK VURGU PANOSU)
        hero_y = curr_y + 12
        hero_h = 110
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
        
        f_pos = self._get_font(34, bold=True)
        pos_lines = self._wrap_text(clean_pos, f_pos, max_width=890)
        p_y = hero_y + 44 if len(pos_lines) == 1 else hero_y + 36
        for pline in pos_lines[:2]:
            draw.text((85, p_y), pline, fill=pal["hero_val"], font=f_pos)
            p_y += 38

        # 8. BİLGİ KARTLARI (2x2 GRID)
        grid_top = hero_y + hero_h + 24
        col_w = 465
        row_h = 150
        gap_x = 40
        gap_y = 20
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
        f_val = self._get_font(24, bold=True)

        for t in tiles:
            r = t["rect"]
            draw.rounded_rectangle(r, radius=16, fill=pal["panel"], outline=pal["border"], width=2)
            
            draw.ellipse([(r[0][0] + 25, r[0][1] + 24), (r[0][0] + 35, r[0][1] + 34)], fill=t["tag_color"])
            draw.text((r[0][0] + 45, r[0][1] + 20), t["tag"], fill=t["tag_color"], font=f_tag)

            val_lines = self._wrap_text(t["val"], f_val, max_width=col_w - 45)
            vy = r[0][1] + 62 if len(val_lines) == 1 else r[0][1] + 52
            for vline in val_lines[:2]:
                draw.text((r[0][0] + 25, vy), vline, fill=t["color"], font=f_val)
                vy += 32

        # 9. RESMİ KILAVUZ BANT ŞERİDİ
        banner_y = grid_top + 2 * row_h + gap_y + 24
        banner_fill = pal["pdf_banner_bg"]
        banner_outline = pal["pdf_banner_border"]
        banner_text = "RESMİ BAŞVURU KILAVUZU & ŞARTNAME (PDF) EKLENMİŞTİR" if has_pdf else "RESMİ BAŞVURU VE DUYURU SİSTEMDE MEVCUTTUR"

        draw.rounded_rectangle([(55, banner_y), (self.WIDTH - 55, banner_y + 55)], radius=14, fill=banner_fill, outline=banner_outline, width=2)
        draw.ellipse([(80, banner_y + 20), (94, banner_y + 34)], fill=banner_outline)
        f_banner = self._get_font(18, bold=True)
        draw.text((106, banner_y + 16), banner_text, fill=pal["text_primary"], font=f_banner)

        # 10. ALT BİLGİ & ÇALINMAYA KARŞI GÜVENLİK ALANI (FOOTER)
        footer_y = banner_y + 70
        draw.line([(55, footer_y), (self.WIDTH - 55, footer_y)], fill=pal["border"], width=1)

        draw.text((60, footer_y + 20), "Telegram: @kamupersonelrehberi", fill=pal["text_primary"], font=self._get_font(24, bold=True))
        draw.text((60, footer_y + 58), "Telif Hakları Saklıdır • Kamu Personel Rehberi Özgün İlan Vitrini • İzinsiz Alınamaz", fill=pal["text_muted"], font=self._get_font(13))
        draw.text((60, footer_y + 83), "Sıfır Bilgi Kirliliği • %100 Doğrulanmış Resmi Kamu İlanları", fill=pal["tag_color_1"], font=self._get_font(14, bold=True))

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
            qy = footer_y + 15

            draw.rounded_rectangle([(qx - 8, qy - 8), (qx + qr_w + 8, qy + qr_h + 8)], radius=10, fill=(255, 255, 255), outline=pal["border"], width=2)
            img.paste(qr_img, (qx, qy, qx + qr_w, qy + qr_h))

            draw.text((qx - 190, footer_y + 36), "RESMİ KILAVUZ", fill=pal["text_muted"], font=self._get_font(13, bold=True))
            draw.text((qx - 190, footer_y + 58), "QR KODU OKUTUN", fill=pal["val_color_2"], font=self._get_font(15, bold=True))
        except Exception as qe:
            logger.warning(f"QR kod oluşturulamadı: {qe}")

        # 11. RGB'ye Dönüştür ve Kaydet
        final_img = img.convert("RGB")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"ilan_kart_{job_id}_{theme_key.lower()}_{timestamp}.png"
        filepath = self.output_dir / filename
        final_img.save(str(filepath), "PNG", quality=95)

        logger.info(f"Yeni kurumsal marka ilan vitrini üretildi [{pal['name']}]: {filepath}")
        return filepath

    def get_theme_sample(self, theme_key: str) -> Path:
        """Belirtilen tema için kalıcı bir örnek vitrin kartı döner."""
        import shutil
        sample_dir = self.assets_dir / "theme_previews"
        sample_dir.mkdir(parents=True, exist_ok=True)
        sample_path = sample_dir / f"sample_{theme_key.lower()}.png"
        if not sample_path.exists():
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

