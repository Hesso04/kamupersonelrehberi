"""
KAMU HABERLERİ & RESMİ DUYURULAR GÖRSEL KART MOTORU (NewsCardGenerator)
=======================================================================
İlan kartlarından tamamen farklı; editoryal, son dakika ve resmi devlet bülteni
formatında 1080x1350 (4:5 Dikey Instagram/Telegram) görsel kart üreticisi.
"""

import os
from pathlib import Path
from typing import Optional, List
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from loguru import logger
import qrcode

from graphics.generator import tr_upper, to_turkish_date_str


class NewsCardGenerator:
    """
    Kamu haberleri ve Dezenformasyonla Mücadele bültenleri için
    yüksek prestijli, resmi editoryal haber kartları üreten motor.
    """

    def __init__(self):
        self.width = 1080
        self.height = 1350
        self.output_dir = Path("graphics/output/news")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.assets_dir = Path("graphics/assets")

    def _get_font(self, size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
        candidates = [
            self.assets_dir / "fonts" / ("PlusJakartaSans-Bold.ttf" if bold else "PlusJakartaSans-Regular.ttf"),
            self.assets_dir / "fonts" / ("font_bold.ttf" if bold else "font.ttf"),
            Path("C:/Windows/Fonts/arialbd.ttf") if bold else Path("C:/Windows/Fonts/arial.ttf"),
            Path("C:/Windows/Fonts/segoeuib.ttf") if bold else Path("C:/Windows/Fonts/segoeui.ttf"),
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
        1080x1350 çözünürlüğünde resmi haber kartını üretip dosya yolunu döner.
        """
        out_path = self.output_dir / f"news_{news_id}.png"

        # Tema Renkleri (Kategoriye Göre)
        # DEZENFORMASYON: Bordo/Koyu Kırmızı (DMM tonu)
        # OZLUK_MAAS: Zümrüt Yeşili / Hazine Yeşili
        # MEVZUAT: Kraliyet Mavisi / Mühür Laciverti
        # RESMI_HABER: Gece Mavisi / Çelik Lacivert
        if category == "DEZENFORMASYON":
            bg_top = (75, 10, 18)
            bg_bottom = (20, 4, 8)
            badge_bg = (195, 30, 45)
            badge_text = "🛡️ DMM DOĞRULAMA BÜLTENİ"
            accent_color = (255, 90, 95)
        elif category == "OZLUK_MAAS":
            bg_top = (10, 48, 40)
            bg_bottom = (4, 18, 15)
            badge_bg = (16, 120, 85)
            badge_text = "📊 ÖZLÜK & MALİ HAKLAR BÜLTENİ"
            accent_color = (60, 215, 145)
        elif category == "MEVZUAT":
            bg_top = (25, 30, 60)
            bg_bottom = (8, 10, 24)
            badge_bg = (50, 75, 160)
            badge_text = "📜 RESMİ MEVZUAT DEĞİŞİKLİĞİ"
            accent_color = (120, 160, 255)
        else:
            bg_top = (15, 23, 42)
            bg_bottom = (6, 9, 20)
            badge_bg = (30, 58, 138)
            badge_text = "🏛️ RESMİ DEVLET AÇIKLAMASI"
            accent_color = (96, 165, 250)

        img = Image.new("RGBA", (self.width, self.height), bg_bottom)
        draw = ImageDraw.Draw(img)

        # 1. Degrade Arka Plan Çizimi
        for y in range(self.height):
            ratio = y / self.height
            r = int(bg_top[0] * (1 - ratio) + bg_bottom[0] * ratio)
            g = int(bg_top[1] * (1 - ratio) + bg_bottom[1] * ratio)
            b = int(bg_top[2] * (1 - ratio) + bg_bottom[2] * ratio)
            draw.line([(0, y), (self.width, y)], fill=(r, g, b, 255))

        # 2. Üst Header Bandı
        header_h = 130
        draw.rectangle([(0, 0), (self.width, header_h)], fill=(0, 0, 0, 70))
        draw.line([(0, header_h), (self.width, header_h)], fill=(255, 255, 255, 35), width=2)

        font_header_title = self._get_font(28, bold=True)
        font_header_sub = self._get_font(18, bold=False)

        draw.text((60, 36), "T.C. KAMU HABERLERİ & RESMİ DUYURU AKIŞI", fill=(255, 255, 255, 240), font=font_header_title)
        draw.text((60, 76), "REKLAMSIZ • ARACISIZ • BİRİNCİL ELDEN TEYİTLİ DEVLET KAYNAĞI", fill=accent_color, font=font_header_sub)

        # 3. Kategori Rozeti (Badge)
        badge_font = self._get_font(24, bold=True)
        badge_y = 175
        bbox = badge_font.getbbox(badge_text)
        bw = (bbox[2] - bbox[0]) + 40
        bh = 52
        draw.rounded_rectangle([(60, badge_y), (60 + bw, badge_y + bh)], radius=12, fill=badge_bg)
        draw.text((80, badge_y + 11), badge_text, fill=(255, 255, 255), font=badge_font)

        # 4. Kurum Adı
        font_inst = self._get_font(32, bold=True)
        inst_text = tr_upper(institution or "T.C. KAMU KURUMU")
        draw.text((60, 255), inst_text, fill=(230, 235, 245), font=font_inst)

        # Dekoratif İnce Çizgi
        draw.line([(60, 305), (240, 305)], fill=accent_color, width=4)

        # 5. Büyük Haber Başlığı (Headline)
        font_headline = self._get_font(52, bold=True)
        headline_lines = self._wrap_text(title, font_headline, max_width=960)
        # Maksimum 4 satır göster
        headline_lines = headline_lines[:4]

        cur_y = 335
        for line in headline_lines:
            draw.text((60, cur_y), line, fill=(255, 255, 255), font=font_headline)
            cur_y += 66

        # 6. Editoryal Spot Kutusu (Glass Box)
        spot_box_y = max(cur_y + 35, 620)
        spot_box_h = 360
        draw.rounded_rectangle(
            [(60, spot_box_y), (self.width - 60, spot_box_y + spot_box_h)],
            radius=20,
            fill=(255, 255, 255, 18),
            outline=(255, 255, 255, 45),
            width=2
        )

        font_spot_label = self._get_font(20, bold=True)
        draw.text((95, spot_box_y + 28), "RESMİ AÇIKLAMA / SPOT ÖZET", fill=accent_color, font=font_spot_label)

        font_spot_text = self._get_font(26, bold=False)
        clean_summary = summary or "İlgili resmi açıklamanın tam metni ve yasal dayanakları kamu portalında yayımlanmıştır."
        summary_lines = self._wrap_text(clean_summary, font_spot_text, max_width=890)
        summary_lines = summary_lines[:7]

        sum_y = spot_box_y + 70
        for sline in summary_lines:
            draw.text((95, sum_y), sline, fill=(225, 230, 240), font=font_spot_text)
            sum_y += 38

        # 7. Alt Bilgi & Doğrulama Çubuğu (Footer)
        footer_y = 1040
        # Güvenilirlik Mührü
        draw.rounded_rectangle([(60, footer_y), (self.width - 60, footer_y + 110)], radius=16, fill=(0, 0, 0, 90), outline=(255, 255, 255, 30), width=1)
        
        font_footer_bold = self._get_font(22, bold=True)
        font_footer_sub = self._get_font(18, bold=False)

        date_str = to_turkish_date_str(publish_date or datetime.utcnow())
        draw.text((95, footer_y + 24), "✅ RESMİ DEVLET KAYNAĞI TEYİTLİDİR", fill=(74, 222, 128), font=font_footer_bold)
        draw.text((95, footer_y + 60), f"Yayın Tarihi: {date_str} • Doğrudan Resmi Metin", fill=(180, 190, 205), font=font_footer_sub)

        # 8. Web Sitesi Marka İmzası
        brand_y = 1200
        font_brand = self._get_font(30, bold=True)
        font_domain = self._get_font(22, bold=False)

        draw.text((60, brand_y), "KAMU PERSONEL REHBERİ", fill=(255, 255, 255), font=font_brand)
        draw.text((60, brand_y + 42), "kamupersonelrehberiniz.me/haberler", fill=accent_color, font=font_domain)

        # Sağ Alt QR Kod
        try:
            qr = qrcode.QRCode(box_size=3, border=2)
            qr.add_data(source_url or "https://kamupersonelrehberiniz.me")
            qr.make(fit=True)
            qr_img = qr.make_image(fill_color="white", back_color=bg_bottom).convert("RGBA")
            img.paste(qr_img, (self.width - 170, brand_y - 20))
        except Exception:
            pass

        # RGB Moduna Dönüştür ve Kaydet
        final_img = img.convert("RGB")
        final_img.save(str(out_path), quality=95)
        logger.info(f"Haber kartı başarıyla üretildi: {out_path}")
        return str(out_path)
