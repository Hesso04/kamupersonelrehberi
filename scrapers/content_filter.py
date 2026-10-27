"""
KAMU VE ADAY KİTLESİ AKILLI İÇERİK FİLTRELEME MOTORU (Smart Content Filter v2.0)
================================================================================
Bu modül, resmi kaynaklardan ve portallardan toplanan içerik havuzunu tarayarak:
1. Memur ve aday kitlesinin ilgilenmediği rutin bürokratik, protokol ve tören haberlerini
   (başsağlığı, ziyaret, tebrik, büyükelçi kabulleri vb.) otomatik olarak eler (Kara Liste).
2. Kitlenin doğrudan cebine, atamasına, özlük haklarına ve barınma/sosyal haklarına dokunan
   içerikleri (maaş, KPSS şartsız, 35 yaş, sürekli işçi, TOKİ vb.) önceliklendirir (Beyaz Liste).
3. "Yeni Nesil Editoryal Motor v2.0" özelliği ile entegre çalışır.
"""

import re
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from loguru import logger

from core.database import get_system_setting


@dataclass
class FilterResult:
    is_allowed: bool
    score: int  # 0 - 100 arası ilgi puanı
    category: str
    is_high_priority: bool
    matched_positive: List[str]
    matched_negative: List[str]
    reject_reason: Optional[str] = None


# 1. KARA LİSTE (Kitlemizi ilgilendirmeyen protokol, rutin bürokratik ve törensel haberler)
BLACKLIST_KEYWORDS = [
    "başsağlığı",
    "taziye",
    "şehit",
    "kabul etti",
    "kabulü",
    "ziyaret etti",
    "ziyarette bulundu",
    "nezaket ziyareti",
    "makamında ağırladı",
    "makamında kabul",
    "görüştü",
    "tebrik etti",
    "kutladı",
    "kutlama mesajı",
    "resepsiyon",
    "büyükelçi",
    "büyükelçisi",
    "büyükelçisini",
    "kınama",
    "kınadı",
    "lanetledi",
    "vefat",
    "anma töreni",
    "anıldı",
    "açılış töreni",
    "teftiş etti",
    "incelemelerde bulundu",
    "iftar programı",
    "yemek programı",
    "veda ziyareti",
    "plaket takdim",
    "heyet kabulü",
    "heyeti kabul etti",
    "basın toplantısı düzenledi",
    "açıklamalarda bulundu",
    "buluştu",
    "bir araya geldi",
    "ziyaret",
    "katıldı",
    "ziyareti",
    "toplantısına katıldı",
    "incelemede bulundu",
    "açılışını yaptı",
    "konuğu oldu",
    "programının konuğu",
    "yayınına katıldı",
    "canlı yayın konuğu",
    "zirvesi düzenlendi",
    "çalıştayı düzenlendi",
    "festivali başladı",
    "fuarı açıldı",
    "sempozyum düzenlendi",
    "imza töreni gerçekleştirildi",
]

# 2. BEYAZ LİSTE / YÜKSEK İLGİ ANAHTARLARI (Kitlenin en çok etkileşim verdiği konular)
HIGH_INTEREST_PATTERNS: Dict[str, List[str]] = {
    "OZLUK_MAAS": [
        "maaş", "memur maaşı", "zam", "zam oranı", "enflasyon farkı",
        "ek gösterge", "3600 ek gösterge", "özlük hakları", "tazminat",
        "taban aylık", "seyyanen", "harcırah", "promosyon", "banka promosyonu",
        "ikramiye", "tediye", "bayram ikramiyesi", "maaş katsayısı"
    ],
    "ATAMA_KADRO": [
        "kpss", "kpss şartsız", "kpsssiz", "taban puan", "atama", "atamaları",
        "öğretmen atama", "sağlık personeli alımı", "polis alımı", "bekçi alımı",
        "jandarma", "subay alımı", "astsubay alımı", "uzman erbaş",
        "zabıt katibi", "infaz koruma", "mübaşir", "büro personeli",
        "kontenjan", "branş dağılımı", "mülakat", "mülakatsız", "yerleştirme",
        "35 yaş", "35 yaş sınırı", "yaş şartı", "ösym", "kılavuz yayımlandı"
    ],
    "ISCI_SOZLESMELI": [
        "sürekli işçi", "işçi alımı", "4/b", "4/d", "sözleşmeli personel",
        "kadro", "taşerona kadro", "belediye işçi", "işkur", "typ",
        "temizlik görevlisi", "güvenlik görevlisi", "destek personeli"
    ],
    "SOSYAL_HAK_TOKI": [
        "toki", "sosyal konut", "konut projesi", "konut kuraları", "kura çekimi",
        "ilk evim", "arsa satışı", "arsa kurası", "lojman", "memur konut"
    ],
    "DEZENFORMASYON": [
        "dezenformasyon", "dmm", "iddia doğru değil", "asparagas", "yalan haber",
        "iddialara ilişkin açıklama", "gerçeği yansıtmamaktadır"
    ],
    "MEVZUAT": [
        "resmi gazete", "yönetmelik değişikliği", "kanun teklifi", "cumhurbaşkanı kararı",
        "kararname", "genelge", "disiplin affı", "tayin hakkı", "mazeret tayini"
    ]
}


class ContentFilterEngine:
    """
    Kamu Personel Rehberi Akıllı Editoryal Filtreleme ve Kitle Skorlama Motoru.
    """

    @classmethod
    def is_engine_v2_active(cls) -> bool:
        """
        Yeni Nesil Editoryal Motor v2.0'ın aktif olup olmadığını döndürür.
        Patron panelinden açılıp kapatılabilir.
        Varsayılan: 'true' (aktif).
        """
        val = get_system_setting("EDITORIAL_ENGINE_V2_ENABLED", "true")
        return str(val).strip().lower() in ["true", "1", "yes", "on", "aktif"]

    @classmethod
    def filter_item(
        cls,
        title: str,
        content: str = "",
        summary: str = "",
        institution: str = "",
        strict_mode: bool = False
    ) -> FilterResult:
        """
        Verilen başlık ve içeriği analiz ederek kitlenin ilgisine uygunluğunu denetler.

        Dönüş:
            FilterResult: İzin durumu, uygunluk skoru (0-100), tespit edilen pozitif/negatif anahtarlar.
        """
        full_text = f"{title} {summary} {content}".lower()
        title_lower = title.lower()

        matched_negative = []
        matched_positive = []
        best_category = "RESMI_HABER"
        highest_cat_score = 0

        # Eğer Editoryal Motor v2.0 kapalıysa ve zorunlu mod değilse filtreyi pasif tut
        if not cls.is_engine_v2_active() and not strict_mode:
            return FilterResult(
                is_allowed=True,
                score=50,
                category="RESMI_HABER",
                is_high_priority=False,
                matched_positive=[],
                matched_negative=[],
                reject_reason=None
            )

        # 1. KARA LİSTE KONTROLÜ
        for bad_kw in BLACKLIST_KEYWORDS:
            # Başlıkta geçmesi doğrudan ret sebebidir; metin içinde geçmesi ağırlıklı ceza verir
            if re.search(r"\b" + re.escape(bad_kw) + r"\b", title_lower):
                matched_negative.append(f"başlık:{bad_kw}")
            elif re.search(r"\b" + re.escape(bad_kw) + r"\b", full_text):
                matched_negative.append(f"metin:{bad_kw}")

        # Başlıkta doğrudan bürokratik/protokol anahtar kelimesi varsa REDDET
        title_negatives = [n for n in matched_negative if n.startswith("başlık:")]
        if title_negatives:
            reason = f"Protokol/bürokratik içerik kara listesine takıldı: {', '.join(title_negatives)}"
            logger.debug(f"[FİLTRE RED] '{title[:50]}' -> {reason}")
            return FilterResult(
                is_allowed=False,
                score=10,
                category="PROTOKOL_ELENDI",
                is_high_priority=False,
                matched_positive=[],
                matched_negative=matched_negative,
                reject_reason=reason
            )

        # 2. BEYAZ LİSTE / POZİTİF KATEGORİ PUANLAMASI
        for cat, keywords in HIGH_INTEREST_PATTERNS.items():
            cat_score = 0
            for kw in keywords:
                if re.search(r"\b" + re.escape(kw) + r"\b", title_lower):
                    cat_score += 30
                    matched_positive.append(f"{cat}:{kw}(başlık)")
                elif re.search(r"\b" + re.escape(kw) + r"\b", full_text):
                    cat_score += 10
                    matched_positive.append(f"{cat}:{kw}")

            if cat_score > highest_cat_score:
                highest_cat_score = cat_score
                best_category = cat

        # Taban Puan Hesaplaması
        # Başlık pozitif kelime içeriyorsa 70-100 puan, içermiyorsa genel resmi haber olarak 50 puan
        base_score = 50
        if highest_cat_score > 0:
            base_score = min(100, 50 + highest_cat_score)

        # Metin içi negatif kelimelerin puan kırması
        body_negatives = [n for n in matched_negative if n.startswith("metin:")]
        if body_negatives:
            base_score -= len(body_negatives) * 15

        final_score = max(0, min(100, base_score))

        # Eğer kitle ilgisi yoksa ve metinde negatif kelimeler baskınsa ele
        if final_score < 40:
            reason = f"Kitle ilgi skoru yetersiz ({final_score}/100). Memur/aday odaklı bulunmadı."
            return FilterResult(
                is_allowed=False,
                score=final_score,
                category=best_category,
                is_high_priority=False,
                matched_positive=matched_positive,
                matched_negative=matched_negative,
                reject_reason=reason
            )

        is_high_priority = final_score >= 75 or best_category in ["OZLUK_MAAS", "ATAMA_KADRO", "SOSYAL_HAK_TOKI"]

        return FilterResult(
            is_allowed=True,
            score=final_score,
            category=best_category,
            is_high_priority=is_high_priority,
            matched_positive=matched_positive,
            matched_negative=matched_negative,
            reject_reason=None
        )


def check_audience_relevance(title: str, content: str = "", summary: str = "") -> Tuple[bool, str, int]:
    """
    Hızlı kontrol fonksiyonu: (Geçti mi, Kategori, Skor)
    """
    res = ContentFilterEngine.filter_item(title=title, content=content, summary=summary)
    return res.is_allowed, res.category, res.score
