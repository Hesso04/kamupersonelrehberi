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
        Kural 1: Sektörel AI arka plan mimarisi.
        Kural 2: İkon ve emojilerden tamamen arındırılmış kurumsal saf tipografi.
        Kural 3: Filigranı yok eden y=1050..1350 siyah degrade ve dip kapatma bandı.
        """
        out_path = self.output_dir / f"news_{news_id}.png"

        # 1. Ana Tuval (Derin Gece Tonu)
        canvas = Image.new("RGBA", (self.WIDTH, self.HEIGHT), (8, 12, 22, 255))

        # 2. Mimari Arka Plan Fotoğrafı (Sektörel AI Arka Plan Motoru)
        bg_path = None
        try:
            from graphics.ai_background_generator import AIGeneratorService
            ai_service = AIGeneratorService()
            bg_path = ai_service.generate_background(
                news_id=news_id,
                title=title,
                institution=institution,
                category=category,
                width=self.WIDTH,
                height=self.HEIGHT
            )
        except Exception as ai_e:
            logger.debug(f"AI arka plan üretici pas geçildi: {ai_e}")

        if not bg_path or not Path(bg_path).exists():
            bg_file = self.SECTOR_BG_MAP.get(category, "general.jpg")
            bg_path = self.bg_dir / bg_file
            if not bg_path.exists():
                bg_path = self.bg_dir / "general.jpg"

        if bg_path and Path(bg_path).exists():
            try:
                bg = Image.open(str(bg_path)).convert("RGBA")
                scale = max(self.WIDTH / bg.width, self.HEIGHT / bg.height)
                new_w = int(bg.width * scale)
                new_h = int(bg.height * scale)
                bg = bg.resize((new_w, new_h), Image.Resampling.LANCZOS)
                canvas.paste(bg, (0, 0))
            except Exception as e:
                logger.warning(f"Arka plan görseli yükleme uyarısı: {e}")

        # 3. KURAL 3: FİLİGRAN YOK EDİCİ SİNEMATİK KARARTMA DEGRADE KATMANI (Y: 500 - 1350)
        overlay = Image.new("RGBA", (self.WIDTH, self.HEIGHT), (0, 0, 0, 0))
        draw_ov = ImageDraw.Draw(overlay)

        # 500 - 1050 arası sinematik okuma karartması
        for y in range(500, 1050):
            ratio = (y - 500) / 550.0
            alpha = int(200 * (ratio ** 1.3))
            draw_ov.line([(0, y), (self.WIDTH, y)], fill=(8, 12, 22, alpha))

        # 1050 - 1260 arası yumuşak geçiş
        for y in range(1050, 1260):
            ratio = (y - 1050) / 210.0
            alpha = int(200 + 55 * ratio)
            draw_ov.line([(0, y), (self.WIDTH, y)], fill=(6, 9, 18, alpha))

        # Y=1260 - 1350 ARASI TAM OPAK DERİN SİYAH (POLLINATIONS FİLİGRANINI SIFIRLAR)
        for y in range(1260, self.HEIGHT):
            draw_ov.line([(0, y), (self.WIDTH, y)], fill=(6, 9, 18, 255))

        canvas = Image.alpha_composite(canvas, overlay)
        draw = ImageDraw.Draw(canvas)

        # 4. KURAL 2: İKON VE EMOJİLERDEN ARINDIRILMIŞ SOL BEYAZ KAPSÜL
        cw, ch = 88, 720
        cx, cy = 60, 100
        draw.rounded_rectangle([(cx, cy), (cx + cw, cy + ch)], radius=44, fill=(255, 255, 255, 255))

        # Kapsül Üst Dairesel Logo
        draw.ellipse([(cx + 8, cy + 8), (cx + cw - 8, cy + cw - 8)], fill=(15, 23, 42, 255))
        draw.text((cx + 25, cy + 22), "K", fill=(255, 255, 255), font=self._get_font(34, bold=True))

        # Dikey Saf Kurumsal Metin - genişletilmiş tuval, son harf kesilmemesi için
        vert_txt = "KAMU PERSONEL REHBERI  -  WWW.KAMUPERSONELREHBERINIZ.ME"
        txt_img = Image.new("RGBA", (640, 46), (255, 255, 255, 0))
        txt_draw = ImageDraw.Draw(txt_img)
        txt_draw.text((0, 10), vert_txt, fill=(51, 65, 85, 255), font=self._get_font(16, bold=True))
        rotated_txt = txt_img.rotate(270, expand=True)
        paste_x = cx + 21
        paste_y = cy + 100
        canvas.paste(rotated_txt, (paste_x, paste_y), mask=rotated_txt)

        # 5. KURAL 2: İKONSUZ KURUMSAL 'SON DAKİKA' ROZETİ
        bx = cx + cw + 40
        by = 780
        badge_w, badge_h = 200, 52
        draw.rounded_rectangle([(bx, by), (bx + badge_w, by + badge_h)], radius=12, fill=(220, 38, 38, 255))
        draw.text((bx + 20, by + 13), "SON DAKİKA", fill=(255, 255, 255), font=self._get_font(21, bold=True))

        # 6. KURUM ADI VE MANŞET BAŞLIKLARI
        inst_clean = institution.upper() if institution else "T.C. RESMİ KAMU KURUMU"
        font_inst = self._get_font(42, bold=True)
        draw.text((bx, 840), inst_clean, fill=(203, 213, 225), font=font_inst)

        # Başlık boyutu ve satır yönetimi: Başlık uzunsa daha dengeli font seç
        title_len = len(title)
        title_font_size = 48 if title_len < 55 else (42 if title_len < 90 else 36)
        font_headline = self._get_font(title_font_size, bold=True)
        line_spacing = title_font_size + 12

        headline_lines = self._wrap_text(title, font_headline, max_width=self.WIDTH - bx - 50)
        cur_ty = 895
        # En fazla 3 satır başlık vererek cümlenin ortada kesilmesini önle
        for tl in headline_lines[:3]:
            draw.text((bx, cur_ty), tl, fill=(255, 255, 255), font=font_headline)
            cur_ty += line_spacing

        # Sarı Vurgu Alt Başlığı
        font_sub = self._get_font(32, bold=True)
        sub_text = "Basvuru Kilavuzu ve Sartlar Yayimlandi." if ("alımı" in title.lower() or "ilan" in title.lower() or "alım" in title.lower()) else "Resmi Karar ve Ayrintilar Duyuruldu."
        draw.text((bx, cur_ty + 14), sub_text, fill=(250, 204, 21), font=font_sub)

        # 7. KURAL 3: FİLİGRANI ÖRTEN GENIŞLETILMIŞ & TAM MERKEZLİ WEB BUTONU (y=1188..1258)
        bar_w, bar_h = 560, 62
        bar_x = (self.WIDTH - bar_w) // 2
        bar_y = 1190
        # Dış gölge
        draw.rounded_rectangle([(bar_x - 3, bar_y - 3), (bar_x + bar_w + 3, bar_y + bar_h + 3)], radius=32, fill=(0, 0, 0, 100))
        # Ana buton
        draw.rounded_rectangle([(bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h)], radius=31, fill=(15, 23, 42, 250), outline=(255, 255, 255, 120), width=2)
        url_text = "www.kamupersonelrehberiniz.me"
        url_font = self._get_font(20, bold=True)
        bbox = draw.textbbox((0, 0), url_text, font=url_font)
        url_text_w = bbox[2] - bbox[0]
        url_text_x = bar_x + (bar_w - url_text_w) // 2
        draw.text((url_text_x, bar_y + 20), url_text, fill=(241, 245, 249), font=url_font)

        # 8. YORUM CTA SATIRI - Filigranı tamamen örter
        cta_font = self._get_font(14, bold=False)
        cta_text = "Haber detayları icin yoruma KILAVUZ veya LINK yazin"
        bbox2 = draw.textbbox((0, 0), cta_text, font=cta_font)
        cta_w = bbox2[2] - bbox2[0]
        cta_x = (self.WIDTH - cta_w) // 2
        draw.text((cta_x, bar_y + bar_h + 14), cta_text, fill=(148, 163, 184), font=cta_font)

        # RGB Moduna Dönüştür ve Kaydet
        final_img = canvas.convert("RGB")
        final_img.save(str(out_path), "JPEG", quality=96)
        logger.info(f"Ultra HD haber kartı başarıyla üretildi: {out_path}")
        return str(out_path)

    def generate_story(
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
        1080x1920 Dikey Instagram / Facebook Hikaye (Story) formatında
        lüks akrilik cam, son dakika rozeti ve simüle edilmiş '🔗 DETAYLAR İÇİN TIKLAYINIZ'
        bağlantı katmanı içeren ultra prestijli hikaye kartı üretir.
        """
        out_path = self.output_dir / f"story_news_{news_id}.png"
        sw, sh = 1080, 1920

        # Kurumsal Renk Paleti (Carousel slide 3 ile birebir aynı kurumsal tonlar)
        COL_RED    = (220, 38, 38)     # Son Dakika / Rozet kırmızısı
        COL_GOLD   = (250, 204, 21)    # Kurumsal gold
        COL_WHITE  = (255, 255, 255)   # Saf beyaz
        COL_GRAY   = (203, 213, 225)   # Cool-gray gövde metni
        COL_LGRAY  = (148, 163, 184)   # Açık kurumsal gri
        COL_NAVY   = (15, 23, 42)      # Koyu lacivert zemin/panel

        # 1. 1080x1920 Dikey Zemin (AI Mimari Arka Plan + Lüks Karanlık Degrade)
        canvas = Image.new("RGBA", (sw, sh), (8, 12, 22, 255))

        # AI Arka Plan Yükleme (Slayt 1 ile aynı AI cache kontrolü)
        s_bg_path = None
        try:
            from graphics.ai_background_generator import AIGeneratorService
            ai_service = AIGeneratorService()
            import re as _re
            clean_cat = _re.sub(r"[^\w]", "_", category)
            candidate = ai_service.cache_dir / f"ai_{clean_cat}_{news_id}_1080x1350.jpg"
            if candidate.exists() and candidate.stat().st_size > 10000:
                s_bg_path = candidate
            else:
                s_bg_path = ai_service.generate_background(
                    news_id=news_id,
                    title=title,
                    institution=institution,
                    category=category,
                    width=sw,
                    height=sh
                )
            if s_bg_path and Path(s_bg_path).exists():
                s_bg = Image.open(str(s_bg_path)).convert("RGBA")
                scale = max(sw / s_bg.width, sh / s_bg.height)
                new_w, new_h = int(s_bg.width * scale), int(s_bg.height * scale)
                s_bg = s_bg.resize((new_w, new_h), Image.Resampling.LANCZOS)
                canvas.paste(s_bg, (0, 0))
        except Exception as s_bg_err:
            logger.debug(f"Story AI arka plan yüklenemedi: {s_bg_err}")

        # Sinematik Karanlık Cam Katmanı (Kademeli kurumsal karartma)
        s_overlay = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
        d_over = ImageDraw.Draw(s_overlay)
        for i in range(sh):
            if i < 250:
                alpha = int(70 + (i / 250.0) * 80)
            elif i < 900:
                ratio = (i - 250) / 650.0
                alpha = int(150 + ratio * 60)
            elif i < 1500:
                ratio = (i - 900) / 600.0
                alpha = int(210 + ratio * 35)
            else:
                alpha = 250
            d_over.line([(0, i), (sw, i)], fill=(8, 12, 22, alpha))
        canvas = Image.alpha_composite(canvas, s_overlay)

        def _story_glass(c, box, radius=18, opacity=165):
            x1, y1, x2, y2 = box
            w, h = x2 - x1, y2 - y1
            panel = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            pd = ImageDraw.Draw(panel)
            pd.rounded_rectangle([(0, 0), (w, h)], radius=radius, fill=(*COL_NAVY, opacity))
            c.paste(panel, (x1, y1), mask=panel)

        # 1. ÜST HEADER BAR (Y: 90 - 180) - Carousel Slayt 3 ile aynı
        _story_glass(canvas, (50, 90, sw - 50, 185), radius=16, opacity=170)
        draw = ImageDraw.Draw(canvas)
        draw.text((80, 122), "KAMU PERSONEL REHBERI", fill=COL_GRAY, font=self._get_font(24, bold=True))
        date_str = to_turkish_date_str(publish_date or datetime.utcnow())
        draw.text((sw - 330, 124), date_str, fill=COL_GOLD, font=self._get_font(20, bold=True))

        # 2. ROZETLER (Y: 215 - 280) - #SON DAKİKA + RESMİ KURUM BÜLTENİ
        draw.rounded_rectangle([(50, 215), (280, 275)], radius=12, fill=COL_RED)
        draw.text((76, 230), "SON DAKİKA", fill=COL_WHITE, font=self._get_font(22, bold=True))

        inst_clean = institution.upper() if institution else "T.C. RESMİ KAMU KURUMU"
        draw.text((310, 232), inst_clean, fill=COL_WHITE, font=self._get_font(24, bold=True))

        # 3. ANA MANŞET PANELİ (Y: 310 - 750) - Beyaz Başlık + Altın Sarı Vurgu
        _story_glass(canvas, (50, 310, sw - 50, 780), radius=22, opacity=165)
        draw = ImageDraw.Draw(canvas)

        font_story_title = self._get_font(44, bold=True)
        title_lines = self._wrap_text(title, font_story_title, max_width=sw - 160)
        cur_ty = 350
        for tline in title_lines[:5]:
            draw.text((85, cur_ty), tline, fill=COL_WHITE, font=font_story_title)
            cur_ty += 62

        # Sarı Vurgu Alt Başlığı
        sub_text = "Basvuru Kilavuzu ve Sartlar Yayimlandi." if ("alımı" in title.lower() or "ilan" in title.lower() or "alım" in title.lower()) else "Resmi Karar ve Ayrintilar Duyuruldu."
        draw.text((85, cur_ty + 20), sub_text, fill=COL_GOLD, font=self._get_font(30, bold=True))

        # 4. RESMİ AÇIKLAMA ÖZETİ PANELİ (Y: 820 - 1280)
        _story_glass(canvas, (50, 820, sw - 50, 1260), radius=22, opacity=160)
        draw = ImageDraw.Draw(canvas)
        draw.rounded_rectangle([(80, 855), (86, 895)], radius=3, fill=COL_GOLD)
        draw.text((102, 858), "RESMI ACIKLAMA VE AYRINTILAR", fill=COL_GOLD, font=self._get_font(22, bold=True))
        draw.line([(80, 910), (sw - 80, 910)], fill=(*COL_GOLD, 70), width=1)

        font_summary = self._get_font(28, bold=False)
        clean_summary = summary or "Ilgili kamu karari ve resmi takvim kamuoyuna duyurulmustur."
        summary_lines = self._wrap_text(clean_summary, font_summary, max_width=sw - 170)
        cur_sy = 935
        for sline in summary_lines[:6]:
            draw.text((85, cur_sy), sline, fill=COL_GRAY, font=font_summary)
            cur_sy += 44

        # 5. INSTAGRAM HİKAYE BAĞLANTI (LINK STICKER) YÖNLENDİRME KATMANI (Y: 1300 - 1600)
        # Kullanıcı buraya Instagram'ın 'Bağlantı' çıkartmasını (sticker) ekleyecek
        _story_glass(canvas, (50, 1300, sw - 50, 1620), radius=22, opacity=170)
        draw = ImageDraw.Draw(canvas)

        # Rozet bar: YORUMA LINK YAZIN veya TIKLAYIN
        draw.rounded_rectangle([(80, 1335), (86, 1378)], radius=3, fill=COL_RED)
        draw.text((102, 1340), "RESMI DUYURU & BASVURU LINKI", fill=COL_WHITE, font=self._get_font(24, bold=True))

        # Instagram Story Link Çıkartması Alanı (Görsel olarak tam link konumu simülasyonu)
        btn_y1 = 1410
        btn_y2 = 1530
        btn_x1 = 90
        btn_x2 = sw - 90

        # Beyaz parlak oval buton — Instagram Link Sticker ile tam örtüşür
        draw.rounded_rectangle([(btn_x1 - 3, btn_y1 - 3), (btn_x2 + 3, btn_y2 + 3)], radius=55, fill=(0, 0, 0, 70))
        draw.rounded_rectangle([(btn_x1, btn_y1), (btn_x2, btn_y2)], radius=55, fill=(255, 255, 255), outline=(226, 232, 240), width=2)

        # Buton İç Metni
        font_btn = self._get_font(32, bold=True)
        btn_lbl = "DETAYLAR ICIN TIKLAYINIZ"
        btn_bbox = draw.textbbox((0, 0), btn_lbl, font=font_btn)
        btn_lbl_w = btn_bbox[2] - btn_bbox[0]
        draw.text(((sw - btn_lbl_w) // 2, btn_y1 + 40), btn_lbl, fill=COL_NAVY, font=font_btn)

        # Buton Altı Web Adresi
        font_sub_link = self._get_font(22, bold=True)
        sub_link_txt = "kamupersonelrehberiniz.me"
        sub_bbox = draw.textbbox((0, 0), sub_link_txt, font=font_sub_link)
        sub_w = sub_bbox[2] - sub_bbox[0]
        draw.text(((sw - sub_w) // 2, 1555), sub_link_txt, fill=COL_GOLD, font=font_sub_link)

        # 6. ALT ŞERİT (Y: 1780 - 1860) - Carousel Slayt 3 alt şeridiyle aynı
        _story_glass(canvas, (50, 1780, sw - 50, 1860), radius=16, opacity=180)
        draw = ImageDraw.Draw(canvas)
        draw.text((85, 1805), "www.kamupersonelrehberiniz.me", fill=COL_WHITE, font=self._get_font(22, bold=True))
        draw.text((sw - 380, 1807), "%100 Resmi Teyitli Kamu Kaynagi", fill=COL_GRAY, font=self._get_font(18))

        # Kaydet
        final_story = canvas.convert("RGB")
        final_story.save(str(out_path), "PNG", quality=98)
        logger.info(f"Ultra HD 1080x1920 Story kartı başarıyla üretildi: {out_path}")
        return str(out_path)

    def generate_carousel_slides(
        self,
        news_id: int,
        title: str,
        institution: str,
        category: str = "RESMI_HABER",
        summary: str = "",
        content: str = "",
        source_url: str = "https://kamupersonelrehberiniz.me"
    ) -> List[str]:
        """
        Instagram akisi icin 3 slaytlik 1080x1350 Karusel seti uretir.
        - Slayt 1: Kapak Afisi (AI arka plan + premium tipografi)
        - Slayt 2: Detaylar (Slayt 1 AI arka plani TEKRAR KULLANILIR - sifir ekstra AI maliyeti)
        - Slayt 3: Yonlendirme Karti (Slayt 1 AI arka plani TEKRAR KULLANILIR + QR Kod)
        """
        slides = []
        base_name = f"carousel_news_{news_id}"

        # Slayt 1: Standart Ultra HD Kart
        slide1_path = self.generate(
            news_id=news_id,
            title=title,
            institution=institution,
            category=category,
            summary=summary,
            source_url=source_url
        )
        slides.append(slide1_path)

        bg_reuse_path = None
        # AI arka planini bul - Slayt 2 ve 3 icin yeniden kullanilacak
        try:
            from graphics.ai_background_generator import AIGeneratorService
            ai_service = AIGeneratorService()
            import re as _re
            clean_cat = _re.sub(r"[^\w]", "_", category)
            candidate = ai_service.cache_dir / f"ai_{clean_cat}_{news_id}_1080x1350.jpg"
            if candidate.exists() and candidate.stat().st_size > 10000:
                bg_reuse_path = candidate
        except Exception:
            pass

        if not bg_reuse_path:
            bg_file = self.SECTOR_BG_MAP.get(category, "general.jpg")
            bg_reuse_path = self.bg_dir / bg_file
            if not bg_reuse_path.exists():
                bg_reuse_path = self.bg_dir / "general.jpg"

        # ── RENK PALETİ: Slide 1 ile birebir aynı kurumsal dil ──
        # Slide 1'deki "SON DAKİKA" kırmızısı
        COL_RED    = (220, 38, 38)
        # Slide 1'deki kurumsal gold alt-başlık
        COL_GOLD   = (250, 204, 21)
        # Slide 1'deki beyaz başlık
        COL_WHITE  = (255, 255, 255)
        # Cool-gray ikincil metin
        COL_GRAY   = (203, 213, 225)
        COL_LGRAY  = (148, 163, 184)
        # Slide 1'deki derin navy panel
        COL_NAVY   = (15, 23, 42)

        def _make_premium_slide_canvas(slide_bg_path) -> Image.Image:
            """AI arka plani yukle, hafif sinematik karartma uygula — cok koy degil."""
            c = Image.new("RGBA", (self.WIDTH, self.HEIGHT), (8, 12, 22, 255))
            if slide_bg_path and Path(slide_bg_path).exists():
                try:
                    bg = Image.open(str(slide_bg_path)).convert("RGBA")
                    scale = max(self.WIDTH / bg.width, self.HEIGHT / bg.height)
                    bg = bg.resize((int(bg.width * scale), int(bg.height * scale)), Image.Resampling.LANCZOS)
                    c.paste(bg, (0, 0))
                except Exception:
                    pass
            # Slide 1 ile birebir aynı sinematik karartma gradyanı
            ov = Image.new("RGBA", (self.WIDTH, self.HEIGHT), (0, 0, 0, 0))
            ovd = ImageDraw.Draw(ov)
            for y in range(self.HEIGHT):
                if y < 200:
                    alpha = int(80 + (y / 200.0) * 80)          # üst kısım daha açık
                elif y < 700:
                    ratio = (y - 200) / 500.0
                    alpha = int(160 + ratio * 55)
                elif y < 1100:
                    ratio = (y - 700) / 400.0
                    alpha = int(215 + ratio * 35)
                else:
                    alpha = 250                                   # alt kısım tam koy
                ovd.line([(0, y), (self.WIDTH, y)], fill=(8, 12, 22, alpha))
            return Image.alpha_composite(c, ov)

        def _glass(canvas, box, radius=18, opacity=155):
            """Border yok, sadece semi-transparent navy blur panel."""
            x1, y1, x2, y2 = box
            w, h = x2 - x1, y2 - y1
            panel = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            pd = ImageDraw.Draw(panel)
            # Çok hafif dış gölge (1 piksel daha büyük, %20 opaklık)
            pd.rounded_rectangle([(2, 2), (w - 2, h - 2)], radius=radius, fill=(*COL_NAVY, opacity))
            canvas.paste(panel, (x1, y1), mask=panel)

        # ─────────────────────────────────────────────────────────────
        # SLAYT 2: DETAYLAR
        # ─────────────────────────────────────────────────────────────
        slide2_path = self.output_dir / f"{base_name}_slide2.png"
        s2c = _make_premium_slide_canvas(bg_reuse_path)

        # Üst header bar — aynı paleti kullan
        _glass(s2c, (48, 55, self.WIDTH - 48, 148), radius=14, opacity=170)
        s2d = ImageDraw.Draw(s2c)
        s2d.text((72, 82), "KAMU PERSONEL REHBERI", fill=COL_GRAY, font=self._get_font(22, bold=True))
        # Slide numarası: gold, cıvık mavi değil
        s2d.text((self.WIDTH - 155, 82), "2 / 3", fill=COL_GOLD, font=self._get_font(22, bold=True))

        # Ana içerik paneli — daha açık opaklık
        _glass(s2c, (48, 168, self.WIDTH - 48, self.HEIGHT - 90), radius=20, opacity=160)
        s2d = ImageDraw.Draw(s2c)

        # Bölüm başlığı: beyaz, bold — slide 1 kurum adı tonu
        s2d.text((78, 198), "RESMI METIN & AYRINTILAR", fill=COL_WHITE, font=self._get_font(26, bold=True))
        # İnce gold accent çizgisi (slide 1 subtitle gold tonuyla aynı)
        s2d.line([(78, 238), (self.WIDTH - 78, 238)], fill=(*COL_GOLD, 90), width=1)

        full_body = content or summary or title
        body_lines = self._wrap_text(full_body, self._get_font(25), max_width=self.WIDTH - 160)[:20]
        cur_y = 258
        for bline in body_lines:
            s2d.text((78, cur_y), bline, fill=COL_GRAY, font=self._get_font(25))
            cur_y += 48

        # Alt şerit
        _glass(s2c, (48, self.HEIGHT - 85, self.WIDTH - 48, self.HEIGHT - 18), radius=14, opacity=180)
        s2d = ImageDraw.Draw(s2c)
        s2d.text((78, self.HEIGHT - 60), "www.kamupersonelrehberiniz.me", fill=COL_WHITE, font=self._get_font(20, bold=True))
        # "Sola Kaydirin" → navy zeminde gold — slide 1 subtitle gold tonu
        s2d.text((self.WIDTH - 250, self.HEIGHT - 60), "Sola Kaydirin >>>", fill=COL_GOLD, font=self._get_font(19, bold=True))

        s2c.convert("RGB").save(str(slide2_path), "PNG", quality=98)
        slides.append(str(slide2_path))

        # ─────────────────────────────────────────────────────────────
        # SLAYT 3: YÖNLENDIRME & QR
        # ─────────────────────────────────────────────────────────────
        slide3_path = self.output_dir / f"{base_name}_slide3.png"
        s3c = _make_premium_slide_canvas(bg_reuse_path)

        # Üst header bar
        _glass(s3c, (48, 55, self.WIDTH - 48, 148), radius=14, opacity=170)
        s3d = ImageDraw.Draw(s3c)
        s3d.text((72, 82), "KAMU PERSONEL REHBERI", fill=COL_GRAY, font=self._get_font(22, bold=True))
        s3d.text((self.WIDTH - 155, 82), "3 / 3", fill=COL_GOLD, font=self._get_font(22, bold=True))

        # Web adresi panel
        _glass(s3c, (48, 175, self.WIDTH - 48, 310), radius=18, opacity=160)
        s3d = ImageDraw.Draw(s3c)
        s3d.text((80, 207), "DETAYLAR ICIN ZIYARET EDIN:", fill=COL_LGRAY, font=self._get_font(19))
        # URL: beyaz büyük bold — slide 1 başlık tonu
        s3d.text((80, 246), "kamupersonelrehberiniz.me", fill=COL_WHITE, font=self._get_font(34, bold=True))

        # CTA panel: "SON DAKİKA" kırmızısıyla aynı aksiyon tonu
        _glass(s3c, (48, 335, self.WIDTH - 48, 555), radius=18, opacity=158)
        s3d = ImageDraw.Draw(s3c)
        # "YORUMA 'LINK' YAZIN!" → slide 1 "SON DAKİKA" kırmızısı ile aynı kurumsal güç
        # Küçük kırmızı rozet
        s3d.rounded_rectangle([(80, 362), (80 + 6, 410)], radius=3, fill=COL_RED)
        s3d.text((96, 362), "YORUMA 'LINK' YAZIN!", fill=COL_WHITE, font=self._get_font(30, bold=True))
        # gold ince çizgi
        s3d.line([(80, 406), (self.WIDTH - 80, 406)], fill=(*COL_GOLD, 70), width=1)
        yorum_lines = [
            "Gonderi altina 'LINK' veya 'KILAVUZ' yazan",
            "takipcilerimize resmi duyuru baglantisi",
            "otomatik olarak DM ile iletilecektir.",
        ]
        yc = 424
        for yl in yorum_lines:
            s3d.text((80, yc), yl, fill=COL_GRAY, font=self._get_font(22))
            yc += 38

        # QR Kod — sade navy zemin, temiz görünüm
        try:
            qr = qrcode.QRCode(box_size=7, border=2)
            qr.add_data("https://kamupersonelrehberiniz.me")
            qr.make(fit=True)
            qr_img = qr.make_image(fill_color="white", back_color=(15, 23, 42)).convert("RGBA")
            qr_w, qr_h = qr_img.size
            qr_x = (self.WIDTH - qr_w) // 2
            qr_y = 590
            # QR arkasına hafif panel
            _glass(s3c, (qr_x - 20, qr_y - 16, qr_x + qr_w + 20, qr_y + qr_h + 46), radius=14, opacity=150)
            s3c.paste(qr_img, (qr_x, qr_y), mask=qr_img)
            s3d = ImageDraw.Draw(s3c)
            label = "Kameranizla Tara & Ac"
            bbox_lbl = s3d.textbbox((0, 0), label, font=self._get_font(18))
            lbl_w = bbox_lbl[2] - bbox_lbl[0]
            s3d.text(((self.WIDTH - lbl_w) // 2, qr_y + qr_h + 14), label, fill=COL_LGRAY, font=self._get_font(18))
        except Exception:
            pass

        # Alt şerit
        _glass(s3c, (48, self.HEIGHT - 85, self.WIDTH - 48, self.HEIGHT - 18), radius=14, opacity=180)
        s3d = ImageDraw.Draw(s3c)
        s3d.text((78, self.HEIGHT - 60), "www.kamupersonelrehberiniz.me", fill=COL_WHITE, font=self._get_font(20, bold=True))

        s3c.convert("RGB").save(str(slide3_path), "PNG", quality=98)
        slides.append(str(slide3_path))

        logger.info(f"Haber #{news_id} icin 3 slaytlik premium Karusel uretildi (sifir ekstra AI maliyeti): {slides}")
        return slides

