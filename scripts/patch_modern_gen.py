"""
modern_generator.py icindeki is ilani kart alt bolumunu gunceller:
- CTA butonunu tam ortalar
- Web URL pilini buyutur ve merkeze alir
- 'Ilan detaylari icin yoruma KILAVUZ veya LINK yazin' mesajini ekler
"""
from pathlib import Path

file_path = Path("graphics/modern_generator.py")
content = file_path.read_text(encoding="utf-8")

OLD = (
    "        # 10. CTA & Web Adresi Butonlar\u0131\r\n"
    "        cta_btn_color = (220, 38, 38) if is_cancellation else (37, 99, 235)\r\n"
    "        cta_text = \"\u0130PTAL DETAYLARINI \u0130NCELE \u2192\" if is_cancellation else \"\u015eARTLARI \u0130NCELE & RESM\u0130 KILAVUZU \u0130ND\u0130R \u2192\"\r\n"
    "        draw.rounded_rectangle([(56, 1160), (1024, 1240)], radius=16, fill=cta_btn_color)\r\n"
    "        draw.text((220, 1184), cta_text, fill=(255, 255, 255), font=self._get_font(23, bold=True))\r\n"
    "\r\n"
    "        draw.rounded_rectangle([(56, 1260), (1024, 1330)], radius=16, fill=(15, 23, 42), outline=(56, 189, 248), width=1)\r\n"
    "        draw.text((360, 1282), f\"\U0001f310 {website_url}\", fill=(56, 189, 248), font=self._get_font(21, bold=True))\r\n"
    "\r\n"
    "        # 11. Alt \u0130mza\r\n"
    "        draw.line([(56, 1540), (1024, 1540)], fill=(51, 65, 85), width=1)\r\n"
    "        draw.text((270, 1560), \"DO\u011eRU B\u0130LG\u0130  |  DO\u011eRU KAR\u0130YER  |  KAMU PERSONEL REHBER\u0130\", fill=(100, 116, 139), font=self._get_font(14, bold=True))\r\n"
    "\r\n"
    "        # 12. RGB \u00c7\u0131kt\u0131 Kaydet\r\n"
    "        final_img = canvas.convert(\"RGB\")\r\n"
    "        final_img.save(str(filepath), \"PNG\", quality=95)\r\n"
    "        logger.info(f\"Yeni Nesil Modern Afi\u015f \u00dcretildi [Pillow Engine/{sector}]: {filepath}\")\r\n"
    "        return filepath"
)

NEW = (
    "        # 10. CTA & Web Adresi Butonlari\r\n"
    "        cta_btn_color = (220, 38, 38) if is_cancellation else (37, 99, 235)\r\n"
    "        cta_text = \"IPTAL DETAYLARINI INCELE\" if is_cancellation else \"SARTLARI INCELE & RESMI KILAVUZU INDIR\"\r\n"
    "        draw.rounded_rectangle([(56, 1160), (1024, 1240)], radius=16, fill=cta_btn_color)\r\n"
    "        cta_font = self._get_font(22, bold=True)\r\n"
    "        bbox_cta = draw.textbbox((0, 0), cta_text, font=cta_font)\r\n"
    "        cta_tw = bbox_cta[2] - bbox_cta[0]\r\n"
    "        draw.text(((1080 - cta_tw) // 2, 1193), cta_text, fill=(255, 255, 255), font=cta_font)\r\n"
    "\r\n"
    "        # Buyutulmus & tam merkezli web URL pill\r\n"
    "        url_bar_w, url_bar_h = 660, 60\r\n"
    "        url_bar_x = (1080 - url_bar_w) // 2\r\n"
    "        url_bar_y = 1260\r\n"
    "        draw.rounded_rectangle([(url_bar_x - 3, url_bar_y - 3), (url_bar_x + url_bar_w + 3, url_bar_y + url_bar_h + 3)], radius=35, fill=(0, 0, 0, 80))\r\n"
    "        draw.rounded_rectangle([(url_bar_x, url_bar_y), (url_bar_x + url_bar_w, url_bar_y + url_bar_h)], radius=32, fill=(15, 23, 42), outline=(56, 189, 248), width=2)\r\n"
    "        url_disp = website_url.replace(\"https://\", \"\").replace(\"http://\", \"\")\r\n"
    "        url_font = self._get_font(22, bold=True)\r\n"
    "        bbox_url = draw.textbbox((0, 0), url_disp, font=url_font)\r\n"
    "        url_tw = bbox_url[2] - bbox_url[0]\r\n"
    "        draw.text(((1080 - url_tw) // 2, url_bar_y + 18), url_disp, fill=(56, 189, 248), font=url_font)\r\n"
    "\r\n"
    "        # Yorum CTA satiri - tamamen merkezli\r\n"
    "        ilan_cta = \"Ilan detaylari icin yoruma KILAVUZ veya LINK yazin\"\r\n"
    "        ilan_cta_font = self._get_font(14)\r\n"
    "        bbox_ilan = draw.textbbox((0, 0), ilan_cta, font=ilan_cta_font)\r\n"
    "        ilan_tw = bbox_ilan[2] - bbox_ilan[0]\r\n"
    "        draw.text(((1080 - ilan_tw) // 2, url_bar_y + url_bar_h + 14), ilan_cta, fill=(100, 116, 139), font=ilan_cta_font)\r\n"
    "\r\n"
    "        # 11. Alt Imza\r\n"
    "        draw.line([(56, 1540), (1024, 1540)], fill=(51, 65, 85), width=1)\r\n"
    "        draw.text((270, 1560), \"DOGRU BILGI  |  DOGRU KARIYER  |  KAMU PERSONEL REHBERI\", fill=(100, 116, 139), font=self._get_font(14, bold=True))\r\n"
    "\r\n"
    "        # 12. RGB Cikti Kaydet\r\n"
    "        final_img = canvas.convert(\"RGB\")\r\n"
    "        final_img.save(str(filepath), \"PNG\", quality=95)\r\n"
    "        logger.info(f\"Yeni Nesil Modern Afis Uretildi [Pillow Engine/{sector}]: {filepath}\")\r\n"
    "        return filepath"
)

if OLD in content:
    content = content.replace(OLD, NEW)
    file_path.write_text(content, encoding="utf-8")
    print("[OK] modern_generator.py guncellendi - CTA + URL pill + yorum satiri eklendi.")
else:
    # fallback: try without CR
    OLD_lf = OLD.replace("\r\n", "\n")
    NEW_lf = NEW.replace("\r\n", "\n")
    if OLD_lf in content:
        content = content.replace(OLD_lf, NEW_lf)
        file_path.write_text(content, encoding="utf-8")
        print("[OK] (LF fallback) modern_generator.py guncellendi.")
    else:
        print("[HATA] Hedef icerik bulunamadi. Manuel kontrol gerekiyor.")
        # Print context
        idx = content.find("# 10. CTA")
        print("Bulunan bolum:")
        print(repr(content[idx:idx+600]))
