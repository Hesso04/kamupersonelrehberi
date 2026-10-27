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
        font_inst = self._get_font(50, bold=True)
        font_sub = self._get_font(38, bold=True)

        inst_clean = institution.upper() if institution else "T.C. RESMİ KAMU KURUMU"
        draw.text((bx, 860), inst_clean, fill=(255, 255, 255), font=font_inst)

        # Başlık satır bölme
        headline_lines = self._wrap_text(title, font_inst, max_width=self.WIDTH - bx - 50)
        cur_ty = 925
        for tl in headline_lines[:2]:
            draw.text((bx, cur_ty), tl, fill=(255, 255, 255), font=font_inst)
            cur_ty += 62

        # Sarı Vurgu Alt Başlığı
        sub_text = "Basvuru Kilavuzu ve Sartlar Yayimlandi." if ("alımı" in title.lower() or "ilan" in title.lower() or "alım" in title.lower()) else "Resmi Karar ve Ayrintilar Duyuruldu."
        draw.text((bx, cur_ty + 20), sub_text, fill=(250, 204, 21), font=font_sub)

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

        # Renk ve Tema Paleti
        if category in ["OZLUK_MAAS", "OZLUK"]:
            theme_badge = "📊 ÖZLÜK & MAAŞ DÜZENLEMESİ"
            accent_col = (59, 130, 246)  # Mavi
            accent_bg = (30, 58, 138)
            accent_light = (147, 197, 253)
        elif category in ["ATAMA_KADRO", "ATAMA"]:
            theme_badge = "🎯 ÖSYM & ATAMA DUYURUSU"
            accent_col = (16, 185, 129)  # Zümrüt Yeşil
            accent_bg = (6, 78, 59)
            accent_light = (167, 243, 208)
        elif category == "SOSYAL_HAK_TOKI":
            theme_badge = "🏠 TOKİ SOSYAL KONUT & KURA"
            accent_col = (245, 158, 11)  # Altın Amber
            accent_bg = (120, 53, 15)
            accent_light = (253, 230, 138)
        elif category == "DEZENFORMASYON":
            theme_badge = "🛡️ DMM DOĞRULAMA BÜLTENİ"
            accent_col = (239, 68, 68)  # Kırmızı
            accent_bg = (153, 27, 27)
            accent_light = (254, 202, 202)
        else:
            theme_badge = "📢 RESMİ KAMU DUYURUSU"
            accent_col = (139, 92, 246)  # Mor
            accent_bg = (76, 29, 149)
            accent_light = (221, 214, 254)

        # 1. 1080x1920 Dikey Zemin (AI Mimari Arka Plan + Lüks Karanlık Degrade)
        canvas = Image.new("RGBA", (sw, sh), (8, 12, 22, 255))

        # AI Arka Plan Yükleme
        try:
            from graphics.ai_background_generator import AIGeneratorService
            ai_service = AIGeneratorService()
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

        # Sinematik Karanlık Cam Katmanı
        s_overlay = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
        d_over = ImageDraw.Draw(s_overlay)
        for i in range(sh):
            ratio = i / sh
            alpha = int(170 + 85 * ratio)
            d_over.line([(0, i), (sw, i)], fill=(8, 12, 22, alpha))
        canvas = Image.alpha_composite(canvas, s_overlay)
        draw = ImageDraw.Draw(canvas)

        # Üst Vurgu Rozeti ve Branding Barı (Y: 120-260)
        draw.text((60, 130), "kamupersonelrehberiniz.me", fill=(148, 163, 184), font=self._get_font(22, bold=True))
        date_str = to_turkish_date_str(publish_date or datetime.utcnow())
        draw.text((sw - 60 - 240, 130), f"🗓️ {date_str}", fill=(100, 116, 139), font=self._get_font(18))

        # #SonDakika Kırmızı Neon Rozet
        draw.rounded_rectangle([(60, 185), (290, 245)], radius=30, fill=(220, 38, 38, 255), outline=(248, 113, 113, 200), width=2)
        draw.text((88, 200), "🔥 #SON DAKİKA", fill=(255, 255, 255), font=self._get_font(22, bold=True))

        # Kategori Rozeti
        draw.rounded_rectangle([(310, 185), (sw - 60, 245)], radius=30, fill=(*accent_bg, 220), outline=(*accent_col, 200), width=2)
        draw.text((335, 202), theme_badge, fill=accent_light, font=self._get_font(19, bold=True))

        # 2. Kurum Başlığı Paneli (Y: 280-360)
        inst_clean = institution.upper() if institution else "T.C. RESMİ KURUM"
        draw.text((60, 290), f"🏛️ {inst_clean}", fill=(203, 213, 225), font=self._get_font(24, bold=True))

        # 3. Ana Manşet Akrilik Cam Paneli (Y: 350-980)
        self._create_frosted_glass_panel(
            canvas,
            (50, 350, sw - 50, 980),
            radius=28,
            tint_color=(15, 23, 42, 230),
            border_color=(255, 255, 255, 45),
            accent_strip_color=accent_col
        )
        draw = ImageDraw.Draw(canvas)

        font_story_title = self._get_font(46, bold=True)
        title_lines = self._wrap_text(title, font_story_title, max_width=900)
        title_lines = title_lines[:8]

        cur_ty = 400
        for tline in title_lines:
            # Hafif gölge efekti
            draw.text((86, cur_ty + 2), tline, fill=(0, 0, 0, 180), font=font_story_title)
            draw.text((84, cur_ty), tline, fill=(255, 255, 255), font=font_story_title)
            cur_ty += 66

        # 4. Resmi Spot / Özet Paneli (Y: 1020-1460)
        self._create_frosted_glass_panel(
            canvas,
            (50, 1020, sw - 50, 1460),
            radius=24,
            tint_color=(2, 6, 23, 240),
            border_color=(51, 65, 85, 220),
            accent_strip_color=accent_col
        )
        draw = ImageDraw.Draw(canvas)

        draw.text((84, 1055), "📌 RESMİ AÇIKLAMA VE AYRINTILAR", fill=accent_light, font=self._get_font(22, bold=True))

        font_summary = self._get_font(30, bold=False)
        clean_summary = summary or "İlgili kamu kararı ve resmi takvim kamuoyuna duyurulmuştur."
        summary_lines = self._wrap_text(clean_summary, font_summary, max_width=900)
        summary_lines = summary_lines[:7]

        cur_sy = 1115
        for sline in summary_lines:
            draw.text((84, cur_sy), sline, fill=(226, 232, 240), font=font_summary)
            cur_sy += 46

        # 5. SİMÜLE EDİLMİŞ INSTAGRAM HİKAYE BAĞLANTI KATMANI (Y: 1520-1720)
        # Tıpkı Instagram hikayelerindeki lüks beyaz oval bağlantı çıkartması gibi
        btn_y1 = 1530
        btn_y2 = 1660
        btn_x1 = 90
        btn_x2 = sw - 90

        # Dış ışıma & gölge
        draw.rounded_rectangle([(btn_x1 - 4, btn_y1 - 4), (btn_x2 + 4, btn_y2 + 4)], radius=65, fill=(0, 0, 0, 80))
        # Beyaz parlak oval buton
        draw.rounded_rectangle([(btn_x1, btn_y1), (btn_x2, btn_y2)], radius=65, fill=(255, 255, 255, 255), outline=(226, 232, 240, 255), width=3)

        # Buton İç Metni
        font_btn = self._get_font(34, bold=True)
        draw.text((btn_x1 + 65, btn_y1 + 40), "🔗 DETAYLAR İÇİN TIKLAYINIZ", fill=(15, 23, 42), font=font_btn)

        # Buton Altı Web Adresi Yönlendirmesi
        font_sub_link = self._get_font(22, bold=True)
        draw.text((sw // 2 - 165, 1690), "👉 kamupersonelrehberiniz.me", fill=accent_light, font=font_sub_link)

        # 6. Alt Güven ve Telif Şeridi (Y: 1770-1860)
        draw.line([(60, 1760), (sw - 60, 1760)], fill=(51, 65, 85, 120), width=1)
        draw.text((sw // 2 - 275, 1795), "Türkiye'nin Güvenilir Resmi Kamu Bilgi & Kariyer Platformu", fill=(148, 163, 184), font=self._get_font(18))
        draw.text((sw // 2 - 210, 1830), "T.C. Resmi Kaynaklarından Anlık Teyit Edilmiştir", fill=(100, 116, 139), font=self._get_font(16))

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

        # Slayt 1 arka planini yukle - Slayt 2 ve 3 icin tekrar kullanilacak
        # Once AI cache dosyasini bul, yoksa static bg kullan
        bg_reuse_path = None
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

        def _make_premium_slide_canvas(slide_bg_path) -> Image.Image:
            """Shared: AI arka plani yukle, sinematik karartma ekle, RGBA tuval dondur."""
            canvas = Image.new("RGBA", (self.WIDTH, self.HEIGHT), (8, 12, 22, 255))
            if slide_bg_path and Path(slide_bg_path).exists():
                try:
                    bg = Image.open(str(slide_bg_path)).convert("RGBA")
                    scale = max(self.WIDTH / bg.width, self.HEIGHT / bg.height)
                    bg = bg.resize((int(bg.width * scale), int(bg.height * scale)), Image.Resampling.LANCZOS)
                    canvas.paste(bg, (0, 0))
                except Exception:
                    pass
            # Sinematik karartma katmani
            overlay = Image.new("RGBA", (self.WIDTH, self.HEIGHT), (0, 0, 0, 0))
            ov_draw = ImageDraw.Draw(overlay)
            for y in range(self.HEIGHT):
                if y < 300:
                    alpha = int(140 + (y / 300.0) * 60)
                elif y < 900:
                    ratio = (y - 300) / 600.0
                    alpha = int(200 + ratio * 50)
                else:
                    alpha = 255
                ov_draw.line([(0, y), (self.WIDTH, y)], fill=(8, 12, 22, alpha))
            return Image.alpha_composite(canvas, overlay)

        # =========================================================
        # SLAYT 2: DETAYLAR - Slayt 1 AI arka plani yeniden kullan
        # =========================================================
        slide2_path = self.output_dir / f"{base_name}_slide2.png"
        s2_canvas = _make_premium_slide_canvas(bg_reuse_path)

        # Frosted glass ust panel
        self._create_frosted_glass_panel(
            s2_canvas,
            (48, 60, self.WIDTH - 48, 160),
            radius=20,
            tint_color=(15, 23, 42, 200),
            border_color=(255, 255, 255, 40)
        )
        s2_draw = ImageDraw.Draw(s2_canvas)
        s2_draw.text((70, 90), "KAMU PERSONEL REHBERI", fill=(203, 213, 225), font=self._get_font(22, bold=True))
        s2_draw.text((self.WIDTH - 170, 90), "2 / 3", fill=(96, 165, 250), font=self._get_font(22, bold=True))

        # Frosted glass ana icerik paneli
        self._create_frosted_glass_panel(
            s2_canvas,
            (48, 180, self.WIDTH - 48, self.HEIGHT - 100),
            radius=24,
            tint_color=(6, 10, 28, 220),
            border_color=(96, 165, 250, 80)
        )
        s2_draw = ImageDraw.Draw(s2_canvas)

        s2_draw.text((78, 210), "RESMI METIN & AYRINTILAR", fill=(96, 165, 250), font=self._get_font(26, bold=True))
        # Ust vurgu cizgi
        s2_draw.line([(78, 248), (self.WIDTH - 78, 248)], fill=(96, 165, 250, 180), width=2)

        full_body = content or summary or title
        body_lines = self._wrap_text(full_body, self._get_font(25), max_width=self.WIDTH - 160)[:20]
        cur_y = 268
        for bline in body_lines:
            s2_draw.text((78, cur_y), bline, fill=(226, 232, 240), font=self._get_font(25))
            cur_y += 48

        # Alt CTA
        self._create_frosted_glass_panel(
            s2_canvas,
            (48, self.HEIGHT - 95, self.WIDTH - 48, self.HEIGHT - 20),
            radius=16,
            tint_color=(15, 23, 42, 230),
            border_color=(255, 255, 255, 40)
        )
        s2_draw = ImageDraw.Draw(s2_canvas)
        s2_draw.text((78, self.HEIGHT - 72), "www.kamupersonelrehberiniz.me", fill=(96, 165, 250), font=self._get_font(20, bold=True))
        s2_draw.text((self.WIDTH - 260, self.HEIGHT - 72), "Sola Kaydirin >>>", fill=(250, 204, 21), font=self._get_font(19, bold=True))

        s2_canvas.convert("RGB").save(str(slide2_path), "PNG", quality=98)
        slides.append(str(slide2_path))

        # =========================================================
        # SLAYT 3: YONLENDIRME - Slayt 1 AI arka plani yeniden kullan
        # =========================================================
        slide3_path = self.output_dir / f"{base_name}_slide3.png"
        s3_canvas = _make_premium_slide_canvas(bg_reuse_path)

        # Ust bar
        self._create_frosted_glass_panel(
            s3_canvas,
            (48, 60, self.WIDTH - 48, 160),
            radius=20,
            tint_color=(15, 23, 42, 200),
            border_color=(255, 255, 255, 40)
        )
        s3_draw = ImageDraw.Draw(s3_canvas)
        s3_draw.text((70, 90), "KAMU PERSONEL REHBERI", fill=(203, 213, 225), font=self._get_font(22, bold=True))
        s3_draw.text((self.WIDTH - 170, 90), "3 / 3", fill=(74, 222, 128), font=self._get_font(22, bold=True))

        # Web linki vurgu paneli
        self._create_frosted_glass_panel(
            s3_canvas,
            (48, 185, self.WIDTH - 48, 320),
            radius=20,
            tint_color=(2, 6, 23, 240),
            border_color=(59, 130, 246, 200)
        )
        s3_draw = ImageDraw.Draw(s3_canvas)
        s3_draw.text((80, 220), "DETAYLAR ICIN ZIYARET EDIN:", fill=(148, 163, 184), font=self._get_font(20))
        s3_draw.text((80, 258), "kamupersonelrehberiniz.me", fill=(147, 197, 253), font=self._get_font(36, bold=True))

        # Yorum CTA paneli
        self._create_frosted_glass_panel(
            s3_canvas,
            (48, 350, self.WIDTH - 48, 560),
            radius=20,
            tint_color=(20, 30, 55, 230),
            border_color=(250, 204, 21, 100)
        )
        s3_draw = ImageDraw.Draw(s3_canvas)
        s3_draw.text((80, 380), "YORUMA 'LINK' YAZIN!", fill=(250, 204, 21), font=self._get_font(32, bold=True))
        yorum_lines = [
            "Gonderi altina 'LINK' veya 'KILAVUZ' yazan",
            "takipcilerimize resmi duyuru baglantisi",
            "otomatik olarak DM ile iletilecektir."
        ]
        yc = 435
        for yl in yorum_lines:
            s3_draw.text((80, yc), yl, fill=(203, 213, 225), font=self._get_font(22))
            yc += 38

        # QR Kod Alani
        try:
            qr = qrcode.QRCode(box_size=7, border=2)
            qr.add_data("https://kamupersonelrehberiniz.me")
            qr.make(fit=True)
            qr_img = qr.make_image(fill_color="white", back_color=(8, 12, 22)).convert("RGBA")
            qr_w = qr_img.size[0]
            qr_x = (self.WIDTH - qr_w) // 2
            s3_canvas.paste(qr_img, (qr_x, 600))
            s3_draw = ImageDraw.Draw(s3_canvas)
            s3_draw.text((qr_x, 600 + qr_img.size[1] + 14), "Kameranizla Tara", fill=(148, 163, 184), font=self._get_font(20))
        except Exception:
            pass

        # Alt URL bar
        self._create_frosted_glass_panel(
            s3_canvas,
            (48, self.HEIGHT - 95, self.WIDTH - 48, self.HEIGHT - 20),
            radius=16,
            tint_color=(15, 23, 42, 230),
            border_color=(255, 255, 255, 40)
        )
        s3_draw = ImageDraw.Draw(s3_canvas)
        s3_draw.text((78, self.HEIGHT - 72), "www.kamupersonelrehberiniz.me", fill=(74, 222, 128), font=self._get_font(20, bold=True))

        s3_canvas.convert("RGB").save(str(slide3_path), "PNG", quality=98)
        slides.append(str(slide3_path))

        logger.info(f"Haber #{news_id} icin 3 slaytlik premium Karusel uretildi (sifir ekstra AI maliyeti): {slides}")
        return slides

