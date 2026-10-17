"""
KAMU HABERLERİ & RESMİ DUYURULAR GÖRSEL KART MOTORU (NewsCardGenerator v2.0 Ultra HD)
=====================================================================================
İlan kartlarından tamamen farklı; lüks, editoryal, son dakika ve resmi devlet bülteni
formatında 1080x1350 (4:5 Dikey Instagram/Telegram) görsel kart üreticisi.
Mimari arka planlar, akrilik cam (frosted glass) paneller, neon ışımalı rozetler
ve yüksek kontrastlı tipografi içerir.
"""

import os
from pathlib import Path
from typing import Optional, List, Tuple
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps
from loguru import logger
import qrcode

from graphics.generator import tr_upper, to_turkish_date_str


class NewsCardGenerator:
    """
    Kamu haberleri ve Dezenformasyonla Mücadele bültenleri için
    yüksek prestijli, editoryal haber kartları üreten profesyonel grafik motoru.
    """

    WIDTH = 1080
    HEIGHT = 1350

    SECTOR_BG_MAP = {
        "DEZENFORMASYON": "cancellation.jpg",
        "OZLUK_MAAS": "finance.jpg",
        "MEVZUAT": "justice.jpg",
        "RESMI_HABER": "general.jpg"
    }

    def __init__(self):
        self.output_dir = Path("graphics/output/news")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.assets_dir = Path("graphics/assets")
        self.bg_dir = self.assets_dir / "backgrounds"
        self.logo_path = self.assets_dir / "logo.png"
        self.logo_circ_path = self.assets_dir / "logo_circular.png"

    def _get_font(self, size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
        candidates = [
            self.assets_dir / "fonts" / ("font_bold.ttf" if bold else "font.ttf"),
            self.assets_dir / "fonts" / ("PlusJakartaSans-Bold.ttf" if bold else "PlusJakartaSans-Regular.ttf"),
            Path("C:/Windows/Fonts/segoeuib.ttf") if bold else Path("C:/Windows/Fonts/segoeui.ttf"),
            Path("C:/Windows/Fonts/arialbd.ttf") if bold else Path("C:/Windows/Fonts/arial.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf") if bold else Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        ]
        for c in candidates:
            if c.exists():
                try:
                    return ImageFont.truetype(str(c), size=size)
                except Exception:
                    pass
        return ImageFont.load_default()

    def _wrap_text(self, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> List[str]:
        words = text.split()
        lines = []
        current = []
        for w in words:
            current.append(w)
            bbox = font.getbbox(" ".join(current))
            if (bbox[2] - bbox[0]) > max_width:
                if len(current) > 1:
                    current.pop()
                    lines.append(" ".join(current))
                    current = [w]
                else:
                    lines.append(" ".join(current))
                    current = []
        if current:
            lines.append(" ".join(current))
        return lines

    def _create_frosted_glass_panel(
        self,
        base_img: Image.Image,
        bbox: Tuple[int, int, int, int],
        radius: int = 24,
        tint_color: Tuple[int, int, int, int] = (15, 23, 42, 215),
        border_color: Tuple[int, int, int, int] = (255, 255, 255, 60),
        accent_strip_color: Optional[Tuple[int, int, int]] = None
    ) -> Image.Image:
        """
        Lüks buzlu cam (frosted glass) paneli oluşturur.
        """
        x1, y1, x2, y2 = bbox
        w, h = x2 - x1, y2 - y1

        # Arka plandan paneli kes ve bulanıklaştır
        cropped = base_img.crop((x1, y1, x2, y2))
        blurred = cropped.filter(ImageFilter.GaussianBlur(14))

        # Yarı saydam renk filtresi uygula
        tint = Image.new("RGBA", (w, h), tint_color)
        blurred.paste(tint, (0, 0), mask=tint)

        # Yuvarlatılmış maske oluştur
        mask = Image.new("L", (w, h), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.rounded_rectangle([(0, 0), (w, h)], radius=radius, fill=255)

        # Panel çerçevesi çiz
        border = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        border_draw = ImageDraw.Draw(border)
        border_draw.rounded_rectangle([(0, 0), (w, h)], radius=radius, outline=border_color, width=2)

        # Sol kenar akrilik vurgu çizgisi (isteğe bağlı)
        if accent_strip_color:
            border_draw.rounded_rectangle([(2, 2), (8, h - 2)], radius=3, fill=(*accent_strip_color, 255))

        # Base görsel üzerine yapıştır
        base_img.paste(blurred, (x1, y1), mask=mask)
        base_img.paste(border, (x1, y1), mask=mask)
        return base_img

    def generate(
        self,
        news_id: int,
        title: str,
        institution: str,
        category: str = "RESMI_HABER",
        summary: str = "",
        source_url: str = "https://kamupersonelrehberiniz.me",
        publish_date: Optional[datetime] = None
    ) -> str:
        """
        1080x1350 Ultra HD editoryal haber bülteni kartı üretir.
        """
        out_path = self.output_dir / f"news_{news_id}.png"

        # Tema Renk Paletleri
        if category == "DEZENFORMASYON":
            theme_name = "DMM DOĞRULAMA"
            badge_icon = "🛡️"
            badge_title = "DMM DEZENFORMASYON BÜLTENİ"
            badge_bg = (185, 28, 28)
            badge_border = (248, 113, 113)
            accent_rgb = (239, 68, 68)
            accent_light = (254, 202, 202)
            bg_ambient = (69, 10, 10)
        elif category == "OZLUK_MAAS":
            theme_name = "ÖZLÜK & MAAŞ"
            badge_icon = "📊"
            badge_title = "ÖZLÜK HAKLARI & MALİ GELİŞME"
            badge_bg = (4, 120, 87)
            badge_border = (52, 211, 153)
            accent_rgb = (16, 185, 129)
            accent_light = (167, 243, 208)
            bg_ambient = (6, 78, 59)
        elif category == "MEVZUAT":
            theme_name = "MEVZUAT"
            badge_icon = "📜"
            badge_title = "YASAL MEVZUAT DEĞİŞİKLİĞİ"
            badge_bg = (67, 56, 202)
            badge_border = (129, 140, 248)
            accent_rgb = (99, 102, 241)
            accent_light = (199, 210, 254)
            bg_ambient = (30, 27, 75)
        else:
            theme_name = "RESMİ HABER"
            badge_icon = "🏛️"
            badge_title = "T.C. RESMİ DEVLET AÇIKLAMASI"
            badge_bg = (29, 78, 216)
            badge_border = (96, 165, 250)
            accent_rgb = (37, 99, 235)
            accent_light = (191, 219, 254)
            bg_ambient = (15, 23, 42)

        # 1. Ana Tuval (Derin Gece Tonu)
        canvas = Image.new("RGBA", (self.WIDTH, self.HEIGHT), (8, 12, 22, 255))

        # 2. Mimari Arka Plan Fotoğrafı
        bg_file = self.SECTOR_BG_MAP.get(category, "general.jpg")
        bg_path = self.bg_dir / bg_file
        if not bg_path.exists():
            bg_path = self.bg_dir / "general.jpg"

        if bg_path.exists():
            try:
                bg = Image.open(bg_path).convert("RGBA")
                # Fotoğrafı 1080x1350'ye orantılı kırp
                scale = max(self.WIDTH / bg.width, 900 / bg.height)
                new_w = int(bg.width * scale)
                new_h = int(bg.height * scale)
                bg = bg.resize((new_w, new_h), Image.Resampling.LANCZOS)
                # Üst kısmı yerleştir
                canvas.paste(bg, (0, 0))
            except Exception as e:
                logger.warning(f"Arka plan görseli yükleme uyarısı: {e}")

        # 3. Sinematik Karanlık Degrade Katmanı
        gradient = Image.new("RGBA", (self.WIDTH, self.HEIGHT), (0, 0, 0, 0))
        d_grad = ImageDraw.Draw(gradient)

        for y in range(self.HEIGHT):
            if y < 220:
                alpha = int(140 + (y / 220.0) * 50)
                r = int(bg_ambient[0] * 0.4)
                g = int(bg_ambient[1] * 0.4)
                b = int(bg_ambient[2] * 0.4)
            elif y < 650:
                ratio = (y - 220) / 430.0
                alpha = int(190 + ratio * 55)
                r = int(bg_ambient[0] * 0.5 * (1 - ratio) + 8 * ratio)
                g = int(bg_ambient[1] * 0.5 * (1 - ratio) + 12 * ratio)
                b = int(bg_ambient[2] * 0.5 * (1 - ratio) + 22 * ratio)
            else:
                alpha = 255
                r, g, b = 8, 12, 22
            d_grad.line([(0, y), (self.WIDTH, y)], fill=(r, g, b, alpha))

        canvas = Image.alpha_composite(canvas, gradient)
        draw = ImageDraw.Draw(canvas)

        # 4. Üst Navigasyon & Marka Bandı
        header_h = 110
        # Üst şerit için lüks cam panel
        self._create_frosted_glass_panel(
            canvas,
            (48, 36, self.WIDTH - 48, 126),
            radius=18,
            tint_color=(15, 23, 42, 180),
            border_color=(255, 255, 255, 40)
        )
        draw = ImageDraw.Draw(canvas)

        # Logo Yerleştir
        active_logo = self.logo_circ_path if self.logo_circ_path.exists() else self.logo_path
        if active_logo.exists():
            try:
                logo_img = Image.open(active_logo).convert("RGBA")
                logo_img.thumbnail((62, 62), Image.Resampling.LANCZOS)
                canvas.paste(logo_img, (66, 50), mask=logo_img)
            except Exception:
                pass

        font_brand = self._get_font(23, bold=True)
        font_sub = self._get_font(13, bold=False)

        draw.text((142, 53), "KAMU PERSONEL REHBERİ", fill=(255, 255, 255), font=font_brand)
        draw.text((142, 83), "T.C. RESMİ HABER & DOĞRULAMA AKIŞI", fill=accent_light, font=font_sub)

        # Sağ Üst Canlı Teyit Rozeti
        badge_right_w = 210
        rx1 = self.WIDTH - 48 - badge_right_w - 18
        ry1 = 54
        draw.rounded_rectangle([(rx1, ry1), (rx1 + badge_right_w, ry1 + 36)], radius=18, fill=(16, 185, 129, 45), outline=(52, 211, 153), width=1)
        draw.ellipse([(rx1 + 14, ry1 + 13), (rx1 + 24, ry1 + 23)], fill=(52, 211, 153))
        font_right_pill = self._get_font(13, bold=True)
        draw.text((rx1 + 32, ry1 + 9), "RESMİ DEVLET TEYİTLİ", fill=(255, 255, 255), font=font_right_pill)

        # 5. Kategori Rozeti (Glowing Banner)
        cat_y = 158
        font_badge = self._get_font(21, bold=True)
        badge_full_text = f"{badge_icon}  {badge_title}"
        b_box = font_badge.getbbox(badge_full_text)
        bw = (b_box[2] - b_box[0]) + 44
        bh = 48

        # Rozet Dış Işıması
        draw.rounded_rectangle([(48, cat_y), (48 + bw, cat_y + bh)], radius=12, fill=badge_bg, outline=badge_border, width=2)
        draw.text((70, cat_y + 11), badge_full_text, fill=(255, 255, 255), font=font_badge)

        # 6. Kurum Adı
        font_inst = self._get_font(30, bold=True)
        clean_inst = tr_upper(institution or "T.C. RESMİ DEVLET KURUMU")
        inst_y = 228
        draw.text((48, inst_y), clean_inst, fill=(226, 232, 240), font=font_inst)

        # Dekoratif Altın / Neon Çizgi
        draw.line([(48, inst_y + 44), (280, inst_y + 44)], fill=accent_rgb, width=4)

        # 7. Büyük Editoryal Manşet (Headline)
        font_headline = self._get_font(48, bold=True)
        headline_lines = self._wrap_text(title, font_headline, max_width=984)
        headline_lines = headline_lines[:3]  # En fazla 3 satır

        head_y = 296
        for hline in headline_lines:
            # Hafif drop-shadow efekti ile maksimum okunurluk
            draw.text((49, head_y + 2), hline, fill=(0, 0, 0, 180), font=font_headline)
            draw.text((48, head_y), hline, fill=(255, 255, 255), font=font_headline)
            head_y += 62

        # 8. Lüks Akrilik Cam Spot Kutusu (Frosted Glass Panel)
        spot_top = max(head_y + 26, 520)
        spot_h = 390
        spot_bbox = (48, spot_top, self.WIDTH - 48, spot_top + spot_h)

        self._create_frosted_glass_panel(
            canvas,
            spot_bbox,
            radius=20,
            tint_color=(15, 23, 42, 210),
            border_color=(255, 255, 255, 50),
            accent_strip_color=accent_rgb
        )
        draw = ImageDraw.Draw(canvas)

        # Spot İçi Etiketi
        font_spot_tag = self._get_font(18, bold=True)
        draw.text((78, spot_top + 26), "📌 RESMİ AÇIKLAMA / SPOT ÖZET", fill=accent_light, font=font_spot_tag)

        # Spot Metni
        font_spot_text = self._get_font(25, bold=False)
        clean_summary = summary or "İlgili resmi kamu duyurusunun yasal gerekçeleri, uygulama takvimi ve resmi metni yayımlanmıştır."
        summary_lines = self._wrap_text(clean_summary, font_spot_text, max_width=920)
        summary_lines = summary_lines[:7]

        sum_cur_y = spot_top + 68
        for sline in summary_lines:
            draw.text((78, sum_cur_y), sline, fill=(226, 232, 240), font=font_spot_text)
            sum_cur_y += 38

        # 9. Güvenilirlik & Teyit Mührü Barı (Trust Seal)
        seal_y = 940
        seal_h = 130
        self._create_frosted_glass_panel(
            canvas,
            (48, seal_y, self.WIDTH - 48, seal_y + seal_h),
            radius=18,
            tint_color=(2, 6, 23, 235),
            border_color=(51, 65, 85, 200)
        )
        draw = ImageDraw.Draw(canvas)

        font_seal_title = self._get_font(22, bold=True)
        font_seal_desc = self._get_font(16, bold=False)
        date_str = to_turkish_date_str(publish_date or datetime.utcnow())

        draw.text((80, seal_y + 24), "✅ BİRİNCİL ELDEN DEVLET KAYNAĞI TEYİTLİDİR", fill=(74, 222, 128), font=font_seal_title)
        draw.text((80, seal_y + 58), f"Yayın Tarihi: {date_str} • Doğrudan Kurum Portalı (.gov.tr)", fill=(203, 213, 225), font=font_seal_desc)
        draw.text((80, seal_y + 88), "Reklamsız • Tıklama Tuzaksız • Doğrulanmış Resmi Haber", fill=(148, 163, 184), font=self._get_font(14))

        # 10. Alt Marka İmzası & QR Kod Alanı (Footer)
        footer_y = 1110
        font_foot_brand = self._get_font(30, bold=True)
        font_foot_url = self._get_font(20, bold=False)

        draw.text((48, footer_y), "KAMU PERSONEL REHBERİ", fill=(255, 255, 255), font=font_foot_brand)
        draw.text((48, footer_y + 42), "kamupersonelrehberiniz.me/haberler", fill=accent_light, font=font_foot_url)
        draw.text((48, footer_y + 78), "Türkiye'nin Güvenilir Resmi Kamu Kariyer & Bilgi Portalı", fill=(100, 116, 139), font=self._get_font(15))

        # Sağ Alt Lüks QR Kod Kutusu
        qr_box_x = self.WIDTH - 48 - 140
        qr_box_y = footer_y - 12
        try:
            qr = qrcode.QRCode(box_size=3, border=2)
            qr.add_data(source_url or "https://kamupersonelrehberiniz.me")
            qr.make(fit=True)
            qr_img = qr.make_image(fill_color="white", back_color=(8, 12, 22)).convert("RGBA")
            # QR kodu yuvarlak köşeli cam arkalıkla süsle
            draw.rounded_rectangle([(qr_box_x - 10, qr_box_y - 10), (qr_box_x + 130, qr_box_y + 130)], radius=16, fill=(15, 23, 42, 240), outline=(255, 255, 255, 40), width=1)
            canvas.paste(qr_img, (qr_box_x, qr_box_y))
            draw.text((qr_box_x - 4, qr_box_y + 140), "Resmi Haberi Oku", fill=(148, 163, 184), font=self._get_font(13))
        except Exception as qre:
            logger.warning(f"QR kod üretim hatası: {qre}")

        # RGB Moduna Dönüştür ve Ultra HD Olarak Kaydet
        final_img = canvas.convert("RGB")
        final_img.save(str(out_path), "PNG", quality=98)
        logger.info(f"Ultra HD haber kartı başarıyla üretildi: {out_path}")
        return str(out_path)
