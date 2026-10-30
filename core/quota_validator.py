"""
Kamu Personel Rehberi - Merkezi Teyitli Kontenjan Çözücü ve Doğrulayıcı (Quota Validator)
Bu modül, kamu ilanlarındaki yıl sayılarını (2024, 2025, 2026, 2027 vb.),
kanun maddelerini (657, 4857 vb.), dönem/aşama numaralarını (1., 2., 3. vb.)
ve rastgele sayıları ayıklar; yalnızca gerçek ve teyitli kontenjanları yakalar.
"""

import re
from typing import Optional, Dict, Any

# Yıllar ve bilinen mevzuat/kanun numaraları (Asla kontenjan olamaz)
FORBIDDEN_NUMBERS = {
    # Yıllar
    2020, 2021, 2022, 2023, 2024, 2025, 2026, 2027, 2028, 2029, 2030, 2031, 2032,
    # Kanun ve KHK Maddeleri
    657, 4857, 375, 2547, 5018, 2802, 399, 5510, 6191, 3269, 7075,
    # Sıkça rastlanan telefon / santral kodları veya form kodları
    112, 155, 156, 170, 182
}

# Sayıdan hemen sonra geldiğinde kontenjan olduğunu %100 teyit eden meslek ve terim tamlamaları
STRONG_SUFFIX_PATTERN = re.compile(
    r"\b(\d{1,4}(?:[.,]\d{3})?)\s*"
    r"(?:adet|kişi|kişilik|personel|memur|uzman\s*yardımcısı|uzman|asistan|öğretim\s*görevlisi|"
    r"araştırma\s*görevlisi|öğretim\s*üyesi|öğr\.\s*gör\.|arş\.\s*gör\.|doçent|profesör|"
    r"işçi|sürekli\s*işçi|sağlık\s*personeli|güvenlik\s*görevlisi|güvenlik|zabıta\s*memuru|zabıta|"
    r"sözleşmeli\s*personel|sözleşmeli|polis|astsubay|subay|mühendis|avukat|mimar|tekniker|"
    r"teknisyen|programcı|denetçi\s*yardımcısı|denetçi|müfettiş\s*yardımcısı|müfettiş|"
    r"hemşire|ebe|sağlık\s*memuru|psikolog|sosyal\s*çalışmacı|büro\s*personeli|şoför|"
    r"hizmetli|temizlik\s*görevlisi|koruma\s*ve\s*güvenlik|kütüphaneci|bilişim\s*personeli)\b",
    re.IGNORECASE
)

# Kesinlikle kontenjan OLMAYAN sayı kalıpları (Bu ifadeler temizlenmeden sayı aranmaz)
NON_QUOTA_CLEANUP_PATTERNS = [
    # Yıllar ve yıl uzantıları: "2026 Yılı", "2026-2", "2026/1", "2026 Yılında", "2026"
    r"\b202\d(?:-\d+|/\d+|\s*(?:yılı|yili|senesi|tarihli|tarihinde))?\b",
    # Dönem ve aşama: "3. Dönem", "3. Donem", "1. Etap", "2. Aşama", "3'üncü dönem"
    r"\b\d{1,2}(?:\.|\'?[uüıioöeaniIİÜÖÇŞĞüöçşğ]+\b)?\s*(?:dönem|donem|aşama|asama|etap|grup|derece|madde)\b",
    # Mevzuat / Kanun: "657 Sayılı", "4857 sayılı kanun"
    r"\b\d{3,4}\s*(?:sayılı|sayili|nolu|no'lu|madde|maddesi|kanun|khk)\b",
    # Tarih günleri: "26.10.2026", "26/10/2026"
    r"\b\d{1,2}[./]\d{1,2}[./]\d{2,4}\b"
]


def extract_verified_quota(
    title: str = "",
    raw_content: str = "",
    default_val: Optional[int] = None
) -> Dict[str, Any]:
    """
    İlan başlığı ve içeriğinden teyitli kontenjan çıkarır.
    
    Dönüş:
    {
        "quota": int,                # Sayısal değer (Teyitli değilse 1)
        "is_exact": bool,            # Sayı kesin ve teyitli mi?
        "display_text": str,         # Afiş ve sosyal medya için güvenli gösterim metni (Örn: '8.000 Kişi' veya 'Resmi Kılavuzda')
        "is_high_quota": bool,       # Yüksek kontenjan banner'ı hak ediyor mu? (>= 50 kişi)
    }
    """
    t_clean = (title or "").strip()
    c_clean = (raw_content or "").strip()

    # 1. Aşama: Sayı + Meslek/Kişi tamlaması var mı? (En yüksek güvenilirlik)
    strong_matches = STRONG_SUFFIX_PATTERN.findall(t_clean)
    if not strong_matches:
        # Başlıkta yoksa içerikte ara
        strong_matches = STRONG_SUFFIX_PATTERN.findall(c_clean[:1000])

    if strong_matches:
        raw_m = strong_matches[0].strip()
        val_str = raw_m.replace(".", "").replace(",", "")
        try:
            val = int(val_str)
            if val not in FORBIDDEN_NUMBERS and 1 <= val < 50000:
                return {
                    "quota": val,
                    "is_exact": True,
                    "display_text": f"{val:,} Kişi".replace(",", "."),
                    "is_high_quota": val >= 50
                }
        except Exception:
            pass

    # 2. Aşama: Başlıktaki tüm yanıltıcı kalıpları (yıllar, dönemler, kanunlar) kazıyalım
    scrubbed_title = t_clean
    for pat in NON_QUOTA_CLEANUP_PATTERNS:
        scrubbed_title = re.sub(pat, " ", scrubbed_title, flags=re.IGNORECASE)

    # 3. Aşama: Kalan metinden geçerli sayıları al
    candidate_tokens = re.findall(r"\b(\d{1,4}(?:[.,]\d{3})?)\b", scrubbed_title)
    valid_candidates = []
    for token in candidate_tokens:
        clean_tok = token.replace(".", "").replace(",", "")
        try:
            num = int(clean_tok)
            if num not in FORBIDDEN_NUMBERS and 1 <= num < 10000:
                valid_candidates.append(num)
        except Exception:
            continue

    if valid_candidates:
        if len(valid_candidates) > 1 and ("," in scrubbed_title or " ve " in scrubbed_title or "+" in scrubbed_title):
            sum_val = sum(valid_candidates)
            if sum_val not in FORBIDDEN_NUMBERS and sum_val < 50000:
                return {
                    "quota": sum_val,
                    "is_exact": True,
                    "display_text": f"{sum_val:,} Kişi".replace(",", "."),
                    "is_high_quota": sum_val >= 50
                }
        else:
            first_val = valid_candidates[0]
            # Tek başına kalan sayı 1'den büyükse geçerlidir
            if first_val > 1:
                return {
                    "quota": first_val,
                    "is_exact": True,
                    "display_text": f"{first_val:,} Kişi".replace(",", "."),
                    "is_high_quota": first_val >= 50
                }

    # 4. Aşama: Varsayılan değer (default_val) verilmişse ve yasaklı değilse kontrol et
    if default_val and default_val not in FORBIDDEN_NUMBERS and default_val > 1:
        return {
            "quota": default_val,
            "is_exact": True,
            "display_text": f"{default_val:,} Kişi".replace(",", "."),
            "is_high_quota": default_val >= 50
        }

    # 5. Aşama: Kontenjan sayısı açıkça teyit edilemedi!
    # Teyitsiz durumlarda ASLA 2026 veya varsayımsal 1 Kişi yazılmaz!
    return {
        "quota": 1,
        "is_exact": False,
        "display_text": "Resmi Kılavuzda",
        "is_high_quota": False
    }
