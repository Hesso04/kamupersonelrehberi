import os
from pathlib import Path

news_card_path = Path("graphics/news_card_generator.py")
with open(news_card_path, "r", encoding="utf-8") as f:
    content = f.read()

# generate metodunu yeni temiz kodla değiştir
marker_start = "    def generate("
marker_end = "    def generate_story("

idx_start = content.find(marker_start)
idx_end = content.find(marker_end)

if idx_start == -1 or idx_end == -1:
    print("HATA: Belirteçler bulunamadı!")
    exit(1)

new_func = '''    def generate(
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

        # Dikey Saf Kurumsal Metin (İkonsuz)
        vert_txt = "KAMU PERSONEL REHBERİ  •  WWW.KAMUPERSONELREHBERINIZ.ME"
        txt_img = Image.new("RGBA", (560, 40), (255, 255, 255, 0))
        txt_draw = ImageDraw.Draw(txt_img)
        txt_draw.text((0, 8), vert_txt, fill=(51, 65, 85, 255), font=self._get_font(17, bold=True))
        rotated_txt = txt_img.rotate(270, expand=True)
        canvas.paste(rotated_txt, (cx + 24, cy + 110), mask=rotated_txt)

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
        sub_text = "Başvuru Kılavuzu ve Şartlar Yayımlandı." if ("alımı" in title.lower() or "ilan" in title.lower() or "alım" in title.lower()) else "Resmi Karar ve Ayrıntılar Duyuruldu."
        draw.text((bx, cur_ty + 20), sub_text, fill=(250, 204, 21), font=font_sub)

        # 7. KURAL 3: FİLİGRANI ÖRTEN OVAL WEB BUTONU VE BİLGİ ŞERİDİ (y=1225..1315)
        bar_w, bar_h = 440, 56
        bar_x = (self.WIDTH - bar_w) // 2
        bar_y = 1225
        draw.rounded_rectangle([(bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h)], radius=28, fill=(15, 23, 42, 240), outline=(255, 255, 255, 90), width=1)
        draw.text((bar_x + 44, bar_y + 16), "www.kamupersonelrehberiniz.me", fill=(241, 245, 249), font=self._get_font(18, bold=True))

        # Dip Bilgi Satırı - Filigranın tam üstünü ezer
        draw.text((self.WIDTH // 2 - 180, 1305), "Türkiye Resmi Kamu İlan ve Bilgi Portalı", fill=(100, 116, 139), font=self._get_font(14))

        # RGB Moduna Dönüştür ve Kaydet
        final_img = canvas.convert("RGB")
        final_img.save(str(out_path), "JPEG", quality=96)
        logger.info(f"Ultra HD haber kartı başarıyla üretildi: {out_path}")
        return str(out_path)

'''

updated_content = content[:idx_start] + new_func + content[idx_end:]
with open(news_card_path, "w", encoding="utf-8") as f:
    f.write(updated_content)

print("Kusursuz sekilde guncellendi!")
