import re
import os
from pathlib import Path
from typing import Optional, Tuple, List, Any, Dict
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter
import qrcode

def tr_upper(text: str) -> str:
    if not text:
        return ""
    return text.translate(str.maketrans({"i": "İ", "ı": "I"})).upper()

def tr_lower(text: str) -> str:
    if not text:
        return ""
    return text.translate(str.maketrans({"İ": "i", "I": "ı"})).lower()

def tr_title(text: str) -> str:
    if not text:
        return ""
    return " ".join(tr_upper(w[0]) + tr_lower(w[1:]) if len(w) > 0 else "" for w in text.split())

def to_turkish_date_str(val: Any) -> str:
    if not val:
        return "Resmi Kılavuzda"
    if isinstance(val, datetime):
        tr_months = ["", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
        return f"{val.day:02d} {tr_months[val.month]} {val.year}"
    
    val_str = str(val).strip()
    if not val_str or val_str.lower() in ["none", "null"]:
        return "Resmi Kılavuzda"

    m_iso = re.match(r"^(\d{4})-(\d{2})-(\d{2})", val_str)
    if m_iso:
        y, m, d = int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3))
        tr_months = ["", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
        if 1 <= m <= 12:
            return f"{d:02d} {tr_months[m]} {y}"

    m_dot = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})", val_str)
    if m_dot:
        d, m, y = int(m_dot.group(1)), int(m_dot.group(2)), int(m_dot.group(3))
        tr_months = ["", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
        if 1 <= m <= 12:
            return f"{d:02d} {tr_months[m]} {y}"

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
    inst = (institution or "").strip()
    pos = (position or "").strip()
    tit = (title or "").strip()

    # 1. Kurumun içindeki personel sayısını veya 'alacak' kelimesini ayıkla
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

    # 3. Pozisyon temizliği
    pos = re.sub(r"\s*(?:alacak|alımı|alınacaktır|alınacak|alım ilanı|ilanı).*$", "", pos, flags=re.IGNORECASE).strip(" -:,")
    if not pos or pos.lower() in ["kamu personel", "kamu personeli"]:
        pos = "Personel Alımı"

    return tr_upper(inst), tr_title(pos)

class UltraCardGenerator:
    WIDTH = 1080
    HEIGHT = 1080

    def __init__(self):
        self.font_bold = Path("C:/Windows/Fonts/segoeuib.ttf")
        self.font_regular = Path("C:/Windows/Fonts/segoeui.ttf")
        if not self.font_bold.exists():
            self.font_bold = Path("C:/Windows/Fonts/arialbd.ttf")
            self.font_regular = Path("C:/Windows/Fonts/arial.ttf")
        self.logo_path = Path("graphics/assets/logo.png")

    def _get_font(self, size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
        p = self.font_bold if bold else self.font_regular
        try:
            return ImageFont.truetype(str(p), size=size)
        except Exception:
            return ImageFont.load_default()

    def _wrap(self, text: str, font: ImageFont.FreeTypeFont, max_w: int) -> List[str]:
        words = text.split()
        lines = []
        cur = []
        for w in words:
            cur.append(w)
            w_w = font.getbbox(" ".join(cur))[2] - font.getbbox(" ".join(cur))[0]
            if w_w > max_w:
                cur.pop()
                if cur:
                    lines.append(" ".join(cur))
                cur = [w]
        if cur:
            lines.append(" ".join(cur))
        return lines

    def generate(
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
        title: str = ""
    ) -> Path:
        clean_inst, clean_pos = clean_inst_and_pos(institution, position, title)

        img = Image.new("RGBA", (self.WIDTH, self.HEIGHT), (0, 0, 0, 255))
        draw = ImageDraw.Draw(img)

        # 1. Ultra Lüks Gece Laciverti / Kurumsal Altın Degrade Zemin
        c_top = (10, 18, 38)
        c_bot = (16, 28, 60)
        for y in range(self.HEIGHT):
            ratio = y / self.HEIGHT
            r = int(c_top[0] * (1 - ratio) + c_bot[0] * ratio)
            g = int(c_top[1] * (1 - ratio) + c_bot[1] * ratio)
            b = int(c_top[2] * (1 - ratio) + c_bot[2] * ratio)
            draw.line([(0, y), (self.WIDTH, y)], fill=(r, g, b, 255))

        # Yumuşak Atmosferik Işıltı (Sağ üst ve sol alt)
        glow = Image.new("RGBA", (self.WIDTH, self.HEIGHT), (0, 0, 0, 0))
        d_glow = ImageDraw.Draw(glow)
        d_glow.ellipse([(self.WIDTH - 420, -100), (self.WIDTH + 150, 450)], fill=(56, 189, 248, 35))
        d_glow.ellipse([(-120, 200), (350, 680)], fill=(245, 158, 11, 20))
        glow = glow.filter(ImageFilter.GaussianBlur(60))
        img.alpha_composite(glow)
        draw = ImageDraw.Draw(img)

        # Üst neon altın çizgisi
        for i in range(4):
            alpha = int(255 * (1 - i / 4))
            draw.line([(0, i), (self.WIDTH, i)], fill=(245, 158, 11, alpha))

        # Dış Çift Zarif Çerçeve
        draw.rounded_rectangle([(20, 20), (self.WIDTH - 20, self.HEIGHT - 20)], radius=24, outline=(48, 76, 135, 140), width=1)
        draw.rounded_rectangle([(28, 28), (self.WIDTH - 28, self.HEIGHT - 28)], radius=20, outline=(56, 189, 248), width=2)

        # 2. Şeffaf Filigran Logo (Merkezde hafif silik)
        if self.logo_path.exists():
            try:
                logo_raw = Image.open(self.logo_path).convert("RGBA")
                wm_size = (560, 560)
                wm = logo_raw.resize(wm_size, Image.Resampling.LANCZOS)
                r, g, b, alpha = wm.split()
                alpha = alpha.point(lambda p: int(p * 0.05))
                wm.putalpha(alpha)
                img.alpha_composite(wm, ((self.WIDTH - wm_size[0]) // 2, (self.HEIGHT - wm_size[1]) // 2 + 30))
            except Exception:
                pass

        # 3. HEADER (ÜST MARKA ALANI)
        lh = 80
        if self.logo_path.exists():
            try:
                logo_crop = logo_raw.resize((lh, lh), Image.Resampling.LANCZOS)
                mask = Image.new("L", (lh, lh), 0)
                ImageDraw.Draw(mask).ellipse((0, 0, lh, lh), fill=255)
                logo_circ = ImageOps.fit(logo_crop, mask.size, centering=(0.5, 0.5))
                logo_circ.putalpha(mask)

                # Logo çerçevesi
                draw.ellipse([(50, 44), (50 + lh + 8, 44 + lh + 8)], outline=(245, 158, 11), width=2)
                img.alpha_composite(logo_circ, (54, 48))
            except Exception:
                pass

        draw.text((150, 48), "KAMU PERSONEL REHBERİ", fill=(255, 255, 255), font=self._get_font(28, bold=True))
        draw.text((152, 86), "GÜNCEL • DOĞRU • %100 DEVLET TEYİTLİ İLANLAR", fill=(251, 191, 36), font=self._get_font(14, bold=True))

        # Sağ Üst Doğrulanmış Rozeti
        badge_text = "RESMİ DEVLET İLANI"
        f_b = self._get_font(16, bold=True)
        bw = f_b.getbbox(badge_text)[2] - f_b.getbbox(badge_text)[0] + 56
        bx = self.WIDTH - 50 - bw
        draw.rounded_rectangle([(bx, 54), (bx + bw, 104)], radius=16, fill=(18, 38, 76), outline=(245, 158, 11), width=2)
        draw.ellipse([(bx + 16, 73), (bx + 28, 85)], fill=(34, 197, 94)) # Canlı yeşil nokta
        draw.text((bx + 36, 68), badge_text, fill=(255, 255, 255), font=f_b)

        # Ayırıcı İnce Çizgi
        draw.line([(50, 144), (self.WIDTH - 50, 144)], fill=(48, 76, 135), width=2)

        # 4. KAMU KURUMU BAŞLIĞI (BÜYÜK, NET, KRİSTAL BEYAZ)
        draw.ellipse([(55, 168), (67, 180)], fill=(245, 158, 11))
        draw.text((76, 165), "KAMU KURUMU / BAKANLIK", fill=(56, 189, 248), font=self._get_font(16, bold=True))

        f_inst = self._get_font(42 if len(clean_inst) < 40 else 35, bold=True)
        inst_lines = self._wrap(clean_inst, f_inst, max_w=970)
        curr_y = 196
        for iline in inst_lines[:2]:
            # İnce gölge
            draw.text((56, curr_y + 2), iline, fill=(0, 0, 0, 160), font=f_inst)
            draw.text((54, curr_y), iline, fill=(255, 255, 255), font=f_inst)
            curr_y += 48 if len(clean_inst) < 40 else 42

        # 5. POZİSYON / KADRO HERO KARTI (GÖZ ALICI BÜYÜK AFİŞ PANOSU)
        hero_y = curr_y + 12
        hero_h = 118
        # Zemin
        draw.rounded_rectangle([(50, hero_y), (self.WIDTH - 50, hero_y + hero_h)], radius=18, fill=(22, 42, 84), outline=(56, 189, 248), width=2)
        # Sol altın şerit
        draw.rounded_rectangle([(50, hero_y), (64, hero_y + hero_h)], radius=6, fill=(245, 158, 11))

        draw.text((82, hero_y + 16), "ALIM YAPILACAK KADRO / POZİSYON", fill=(251, 191, 36), font=self._get_font(15, bold=True))

        f_pos = self._get_font(38 if len(clean_pos) < 36 else 30, bold=True)
        pos_lines = self._wrap(clean_pos, f_pos, max_w=910)
        py = hero_y + 46 if len(pos_lines) == 1 else hero_y + 40
        for pline in pos_lines[:2]:
            draw.text((82, py), pline, fill=(255, 255, 255), font=f_pos)
            py += 40

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
                "accent": (245, 158, 11),  # Altın
                "val_size": 42 if len(pos_str) < 12 else 34,
                "val_color": (255, 255, 255)
            },
            {
                "box": [(c2, grid_top), (c2 + col_w, grid_top + row_h)],
                "tag": "SON BAŞVURU TARİHİ",
                "val": deadline_str,
                "accent": (244, 63, 94),   # Mercan Kırmızı
                "val_size": 34,
                "val_color": (255, 255, 255)
            },
            {
                "box": [(c1, grid_top + row_h + gap_y), (c1 + col_w, grid_top + 2 * row_h + gap_y)],
                "tag": "KPSS ŞARTI",
                "val": kpss_str,
                "accent": (56, 189, 248),  # Elektrik Mavi
                "val_size": 28,
                "val_color": (255, 255, 255)
            },
            {
                "box": [(c2, grid_top + row_h + gap_y), (c2 + col_w, grid_top + 2 * row_h + gap_y)],
                "tag": "ÖĞRENİM DÜZEYİ",
                "val": edu_str,
                "accent": (34, 197, 94),   # Zümrüt Yeşili
                "val_size": 28,
                "val_color": (255, 255, 255)
            }
        ]

        f_card_tag = self._get_font(16, bold=True)
        for card in cards:
            bx = card["box"]
            draw.rounded_rectangle(bx, radius=16, fill=(18, 34, 68), outline=(48, 76, 135), width=2)
            
            # Canlı etiket rozeti
            draw.ellipse([(bx[0][0] + 20, bx[0][1] + 20), (bx[0][0] + 32, bx[0][1] + 32)], fill=card["accent"])
            draw.text((bx[0][0] + 40, bx[0][1] + 16), card["tag"], fill=card["accent"], font=f_card_tag)

            # Büyük Değer Metni
            f_v = self._get_font(card["val_size"], bold=True)
            v_lines = self._wrap(card["val"], f_v, max_w=col_w - 40)
            vy = bx[0][1] + 58 if len(v_lines) == 1 else bx[0][1] + 48
            for vl in v_lines[:2]:
                draw.text((bx[0][0] + 22, vy), vl, fill=card["val_color"], font=f_v)
                vy += (card["val_size"] + 4)

        # 7. RESMİ KILAVUZ BANT ŞERİDİ (GÖZ ALICI BEYAZ/ALTIN ŞERİT)
        banner_y = grid_top + 2 * row_h + gap_y + 18
        banner_text = "RESMİ BAŞVURU KILAVUZU & ŞARTNAME (PDF) EKLENMİŞTİR" if has_pdf else "RESMİ BAŞVURU VE DUYURU SİSTEMDE MEVCUTTUR"

        draw.rounded_rectangle([(50, banner_y), (self.WIDTH - 50, banner_y + 54)], radius=14, fill=(24, 48, 96), outline=(245, 158, 11), width=2)
        draw.ellipse([(72, banner_y + 20), (86, banner_y + 34)], fill=(245, 158, 11))
        f_banner = self._get_font(18, bold=True)
        draw.text((98, banner_y + 16), banner_text, fill=(255, 255, 255), font=f_banner)

        # 8. ALT BİLGİ & ÇALINMAYA KARŞI MARKA İMZASI (FOOTER)
        footer_y = banner_y + 68
        draw.line([(50, footer_y), (self.WIDTH - 50, footer_y)], fill=(48, 76, 135), width=2)

        draw.text((54, footer_y + 14), "✈️ Telegram: @kamupersonelrehberi", fill=(255, 255, 255), font=self._get_font(23, bold=True))
        draw.text((54, footer_y + 46), "📸 Instagram: @kamupersonelrehberi", fill=(56, 189, 248), font=self._get_font(18, bold=True))
        draw.text((54, footer_y + 74), "Telif Hakları Saklıdır • Doğrulanmış Resmi Kamu İlanı • İzinsiz Alınamaz", fill=(148, 163, 184), font=self._get_font(13))

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

            draw.rounded_rectangle([(qx - 6, qy - 6), (qx + qw + 6, qy + qh + 6)], radius=10, fill=(255, 255, 255), outline=(245, 158, 11), width=2)
            img.paste(qr_img, (qx, qy, qx + qw, qy + qh))

            draw.text((qx - 195, footer_y + 24), "RESMİ KILAVUZ", fill=(148, 163, 184), font=self._get_font(14, bold=True))
            draw.text((qx - 195, footer_y + 46), "QR KODU OKUTUN", fill=(251, 191, 36), font=self._get_font(16, bold=True))
        except Exception:
            pass

        final_img = img.convert("RGB")
        out_path = Path("graphics/scratch") / f"sample_clean_{job_id}.png"
        final_img.save(str(out_path), "PNG", quality=98)
        print("Generated:", out_path)
        return out_path

if __name__ == "__main__":
    gen = UltraCardGenerator()
    # Test 1: Giresun Üniversitesi (User screenshot case)
    gen.generate(
        job_id=991,
        institution="GİRESUN ÜNİVERSİTESİ",
        position="Öğretim Üyesi",
        total_positions=11,
        kpss_requirement="Resmi İlanda Belirtilmiştir",
        education_level="Kılavuzda Belirtilen Şartlar",
        deadline="2026-10-09",
        source_url="https://kamuilan.sbb.gov.tr/",
        title="GİRESUN ÜNİVERSİTESİ Personel Alım İlanı"
    )

    # Test 2: Han Belediyesi (Job 680)
    gen.generate(
        job_id=680,
        institution="HAN BELEDİYE BAŞKANLIĞI 1 SÖZLEŞMELİ PERSONEL ALACAK",
        position="Kamu Personel",
        total_positions=1,
        kpss_requirement="Resmi İlanda Belirtilmiştir",
        education_level="İlgili Bölüm Mezuniyeti",
        deadline="2026-10-02",
        source_url="https://kamuilan.sbb.gov.tr/",
        title="HAN BELEDİYE BAŞKANLIĞI 1 SÖZLEŞMELİ PERSONEL ALACAK"
    )
