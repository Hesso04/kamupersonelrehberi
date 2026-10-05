import re
from pathlib import Path
from typing import Optional, Tuple, List, Any
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont, ImageOps
from loguru import logger
import qrcode

from config.settings import settings


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


class JobCardGenerator:
    """
    Pillow tabanlı Yüksek Çözünürlüklü Kurumsal İlan Vitrini Motoru.
    Marka logosuyla %100 uyumlu (Neon Mor, Gece Mavisi ve Altın),
    merkezi çalınma önleyici şeffaf filigranlı (watermark),
    yüksek okunabilirlikli ve dinamik QR kodlu 1080x1080 afişler üretir.
    """

    WIDTH = 1080
    HEIGHT = 1080

    # Marka Uyumlu Renk Paleti (Obsidian, Electric Purple, Cyan & Gold)
    COLOR_BG_TOP = (11, 14, 25)          # #0B0E19 (Derin Obsidyen)
    COLOR_BG_BOTTOM = (17, 13, 36)       # #110D24 (Gece Moru)
    COLOR_PANEL = (20, 22, 46)          # #14162E (Vurgu Kart Paneli)
    COLOR_PANEL_HERO = (26, 24, 56)     # #1A1838 (Hero Pozisyon Paneli)
    COLOR_BORDER = (58, 48, 92)         # #3A305C (Sınır Çizgisi)
    COLOR_VIOLET = (139, 92, 246)       # #8B5CF6 (Neon Mor Vurgu)
    COLOR_VIOLET_LIGHT = (192, 132, 252)# #C084FC (Açık Mor)
    COLOR_CYAN = (56, 189, 248)         # #38BDF8 (Gökyüzü Mavisi)
    COLOR_GOLD = (251, 191, 36)         # #FBBF24 (Amber/Altın Vurgu)
    COLOR_EMERALD = (16, 185, 129)      # #10B981 (Doğrulanmış Yeşil)
    COLOR_WHITE = (255, 255, 255)
    COLOR_MUTED = (156, 163, 175)       # #9CA3AF (Açık Gri)

    def __init__(self):
        self.fonts_dir = settings.FONTS_DIR
        self.output_dir = settings.IMAGE_OUTPUT_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.assets_dir = Path("graphics/assets")
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        self.logo_path = self.assets_dir / "logo.png"

        # Font Tanımları (Öncelik: Segoe UI, Alternatif: Arial)
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

    def _draw_gradient(self, draw: ImageDraw.ImageDraw) -> None:
        """Pürüzsüz gece moru dikey degrade çizer."""
        for y in range(self.HEIGHT):
            ratio = y / self.HEIGHT
            r = int(self.COLOR_BG_TOP[0] * (1 - ratio) + self.COLOR_BG_BOTTOM[0] * ratio)
            g = int(self.COLOR_BG_TOP[1] * (1 - ratio) + self.COLOR_BG_BOTTOM[1] * ratio)
            b = int(self.COLOR_BG_TOP[2] * (1 - ratio) + self.COLOR_BG_BOTTOM[2] * ratio)
            draw.line([(0, y), (self.WIDTH, y)], fill=(r, g, b, 255))

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
        has_pdf: bool = True
    ) -> Path:
        """
        1080x1080 boyutunda marka logolu, merkezi filigran korumalı ve
        üst düzey okunabilirlikli resmi ilan afişi üretir.
        """
        img = Image.new("RGBA", (self.WIDTH, self.HEIGHT), (0, 0, 0, 255))
        draw = ImageDraw.Draw(img)

        # 1. Degrade Arka Plan
        self._draw_gradient(draw)

        # 2. Üst Neon Vurgu Işıltı Çizgisi
        for i in range(5):
            draw.line([(0, i), (self.WIDTH, i)], fill=self.COLOR_VIOLET)

        # Dış Kurumsal Çerçeve
        draw.rounded_rectangle([(30, 30), (self.WIDTH - 30, self.HEIGHT - 30)], radius=24, outline=self.COLOR_BORDER, width=2)

        # 3. ÇALINMAYA KARŞI MERKEZİ ŞEFFAF FİLİGRAN (WATERMARK)
        if self.logo_path.exists():
            try:
                logo_raw = Image.open(self.logo_path).convert("RGBA")
                wm_size = (580, 580)
                wm = logo_raw.resize(wm_size, Image.Resampling.LANCZOS)
                r, g, b, alpha = wm.split()
                alpha = alpha.point(lambda p: int(p * 0.075))  # %7.5 zarafetinde şeffaflık
                wm.putalpha(alpha)
                wx = (self.WIDTH - wm_size[0]) // 2
                wy = (self.HEIGHT - wm_size[1]) // 2 + 25
                img.alpha_composite(wm, (wx, wy))
            except Exception as e:
                logger.debug(f"Filigran yerleştirme uyarısı: {e}")

        # 4. ÜST HEADER ALANI
        # Sol Rozet: Orijinal Marka Logosu (Dairesel Vurgu)
        if self.logo_path.exists():
            try:
                lh = 80
                logo_crop = logo_raw.resize((lh, lh), Image.Resampling.LANCZOS)
                mask = Image.new("L", (lh, lh), 0)
                d_mask = ImageDraw.Draw(mask)
                d_mask.ellipse((0, 0, lh, lh), fill=255)
                logo_circ = ImageOps.fit(logo_crop, mask.size, centering=(0.5, 0.5))
                logo_circ.putalpha(mask)

                # Neon mor halka ve gölge efekti
                draw.ellipse([(54, 44), (54 + lh + 12, 44 + lh + 12)], outline=self.COLOR_VIOLET, width=2)
                img.alpha_composite(logo_circ, (60, 50))
            except Exception as le:
                logger.debug(f"Logo render uyarısı: {le}")

        f_brand = self._get_font(25, bold=True)
        draw.text((156, 54), "KAMU PERSONEL REHBERİ", fill=self.COLOR_WHITE, font=f_brand)
        f_slogan = self._get_font(13, bold=True)
        draw.text((158, 88), "GÜNCEL • DOĞRU • HIZLI", fill=self.COLOR_VIOLET_LIGHT, font=f_slogan)

        # Sağ Üst Doğrulanmış Rozeti (Pill)
        badge_text = "RESMİ DEVLET İLANI"
        f_badge = self._get_font(16, bold=True)
        bbox = f_badge.getbbox(badge_text)
        bw = bbox[2] - bbox[0] + 50
        bx = self.WIDTH - 60 - bw
        draw.rounded_rectangle([(bx, 62), (bx + bw, 102)], radius=12, fill=(15, 75, 60), outline=self.COLOR_EMERALD, width=2)
        draw.ellipse([(bx + 14, 75), (bx + 26, 87)], fill=self.COLOR_EMERALD)
        draw.text((bx + 35, 70), badge_text, fill=self.COLOR_WHITE, font=f_badge)

        # Ayırıcı Çizgi
        draw.line([(55, 145), (self.WIDTH - 55, 145)], fill=self.COLOR_BORDER, width=1)

        # 5. KAMU KURUMU BAŞLIĞI
        # Başlık üstü etiket noktası
        draw.ellipse([(60, 170), (70, 180)], fill=self.COLOR_VIOLET_LIGHT)
        draw.text((78, 166), "KAMU KURUMU", fill=self.COLOR_VIOLET_LIGHT, font=self._get_font(14, bold=True))

        clean_inst = (institution or "T.C. KAMU KURUMU").upper().strip()
        f_inst = self._get_font(33, bold=True)
        inst_lines = self._wrap_text(clean_inst, f_inst, max_width=940)
        curr_y = 196
        for line in inst_lines[:2]:
            draw.text((60, curr_y), line, fill=self.COLOR_WHITE, font=f_inst)
            curr_y += 44

        # 6. POZİSYON HERO KARTI (BÜYÜK VURGU PANOSU)
        hero_y = curr_y + 12
        hero_h = 110
        draw.rounded_rectangle([(55, hero_y), (self.WIDTH - 55, hero_y + hero_h)], radius=18, fill=self.COLOR_PANEL_HERO, outline=self.COLOR_VIOLET, width=2)
        # Sol amber dikey şerit
        draw.rounded_rectangle([(55, hero_y), (67, hero_y + hero_h)], radius=6, fill=self.COLOR_GOLD)

        # Temiz unvan metni
        pos_raw = (position or "Personel Alımı").strip()
        clean_pos = re.sub(r"^\s*(\d+\s*)+", "", pos_raw)
        clean_pos = re.sub(r"\s*(?:alacak|alımı|temin edilecek|alınacaktır|alınacak|alım ilanı).*$", "", clean_pos, flags=re.IGNORECASE)
        clean_pos = clean_pos.strip(" -:,")
        clean_pos = re.sub(r"\bpersoneli\b", "Personel", clean_pos, flags=re.IGNORECASE)
        clean_pos = tr_title(clean_pos)
        clean_pos = clean_pos or "Kamu Personeli"

        draw.text((85, hero_y + 16), "ALIM YAPILACAK KADRO / POZİSYON", fill=self.COLOR_CYAN, font=self._get_font(13, bold=True))
        
        f_pos = self._get_font(34, bold=True)
        pos_lines = self._wrap_text(clean_pos, f_pos, max_width=890)
        p_y = hero_y + 44 if len(pos_lines) == 1 else hero_y + 36
        for pline in pos_lines[:2]:
            draw.text((85, p_y), pline, fill=self.COLOR_GOLD, font=f_pos)
            p_y += 38

        # 7. BİLGİ KARTLARI (2x2 GRID - KESİNTİSİZ ÇİFT SATIR DESTEKLİ)
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
                "color": self.COLOR_CYAN,
                "tag_color": self.COLOR_CYAN
            },
            {
                "rect": [(left2, grid_top), (left2 + col_w, grid_top + row_h)],
                "tag": "KPSS ŞARTI",
                "val": kpss_str,
                "color": self.COLOR_WHITE,
                "tag_color": self.COLOR_GOLD
            },
            {
                "rect": [(left1, grid_top + row_h + gap_y), (left1 + col_w, grid_top + 2 * row_h + gap_y)],
                "tag": "ÖĞRENİM DÜZEYİ",
                "val": edu_str,
                "color": self.COLOR_WHITE,
                "tag_color": self.COLOR_VIOLET_LIGHT
            },
            {
                "rect": [(left2, grid_top + row_h + gap_y), (left2 + col_w, grid_top + 2 * row_h + gap_y)],
                "tag": "SON BAŞVURU TARİHİ",
                "val": deadline_str,
                "color": self.COLOR_GOLD,
                "tag_color": self.COLOR_GOLD
            }
        ]

        f_tag = self._get_font(15, bold=True)
        f_val = self._get_font(24, bold=True)

        for t in tiles:
            r = t["rect"]
            draw.rounded_rectangle(r, radius=16, fill=self.COLOR_PANEL, outline=self.COLOR_BORDER, width=2)
            
            # Vektörel etiket noktası ve başlığı
            draw.ellipse([(r[0][0] + 25, r[0][1] + 24), (r[0][0] + 35, r[0][1] + 34)], fill=t["tag_color"])
            draw.text((r[0][0] + 45, r[0][1] + 20), t["tag"], fill=t["tag_color"], font=f_tag)

            # Değer metni (2 satıra kadar düzgün sarım)
            val_lines = self._wrap_text(t["val"], f_val, max_width=col_w - 45)
            vy = r[0][1] + 62 if len(val_lines) == 1 else r[0][1] + 52
            for vline in val_lines[:2]:
                draw.text((r[0][0] + 25, vy), vline, fill=t["color"], font=f_val)
                vy += 32

        # 8. RESMİ KILAVUZ BANT ŞERİDİ
        banner_y = grid_top + 2 * row_h + gap_y + 24
        banner_fill = (15, 65, 55) if has_pdf else (22, 34, 60)
        banner_outline = self.COLOR_EMERALD if has_pdf else self.COLOR_CYAN
        banner_text = "RESMİ BAŞVURU KILAVUZU & ŞARTNAME (PDF) EKLENMİŞTİR" if has_pdf else "RESMİ BAŞVURU VE DUYURU SİSTEMDE MEVCUTTUR"

        draw.rounded_rectangle([(55, banner_y), (self.WIDTH - 55, banner_y + 55)], radius=14, fill=banner_fill, outline=banner_outline, width=2)
        draw.ellipse([(80, banner_y + 20), (94, banner_y + 34)], fill=banner_outline)
        f_banner = self._get_font(18, bold=True)
        draw.text((106, banner_y + 16), banner_text, fill=self.COLOR_WHITE, font=f_banner)

        # 9. ALT BİLGİ & ÇALINMAYA KARŞI GÜVENLİK ALANI (FOOTER)
        footer_y = banner_y + 70
        draw.line([(55, footer_y), (self.WIDTH - 55, footer_y)], fill=self.COLOR_BORDER, width=1)

        # Sol Telegram & Marka Koruması
        draw.text((60, footer_y + 20), "Telegram: @kamupersonelrehberi", fill=self.COLOR_WHITE, font=self._get_font(24, bold=True))
        draw.text((60, footer_y + 58), "Telif Hakları Saklıdır • Kamu Personel Rehberi Özgün İlan Vitrini • İzinsiz Alınamaz", fill=self.COLOR_MUTED, font=self._get_font(13))
        draw.text((60, footer_y + 83), "Sıfır Bilgi Kirliliği • %100 Doğrulanmış Resmi Kamu İlanları", fill=self.COLOR_CYAN, font=self._get_font(14, bold=True))

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

            # Beyaz koruyucu kart ve neon mor çerçeve
            draw.rounded_rectangle([(qx - 8, qy - 8), (qx + qr_w + 8, qy + qr_h + 8)], radius=10, fill=(255, 255, 255), outline=self.COLOR_VIOLET, width=2)
            img.paste(qr_img, (qx, qy, qx + qr_w, qy + qr_h))

            # QR Yanı Metin
            draw.text((qx - 190, footer_y + 36), "RESMİ KILAVUZ", fill=self.COLOR_MUTED, font=self._get_font(13, bold=True))
            draw.text((qx - 190, footer_y + 58), "QR KODU OKUTUN", fill=self.COLOR_GOLD, font=self._get_font(15, bold=True))
        except Exception as qe:
            logger.warning(f"QR kod oluşturulamadı: {qe}")

        # 10. RGB'ye Dönüştür ve Kaydet
        final_img = img.convert("RGB")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"ilan_kart_{job_id}_{timestamp}.png"
        filepath = self.output_dir / filename
        final_img.save(str(filepath), "PNG", quality=95)

        logger.info(f"Yeni kurumsal marka ilan vitrini üretildi: {filepath}")
        return filepath
