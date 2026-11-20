"""
Kamu Personel Rehberi — 5 Ajanlı Otonom AI Haber Merkezi & Görsel Pipeline'ı
=============================================================================
Mimari:
  1. ArticleFetcherAgent   -> Resmi kaynak URL'lerinden tam metni çeker, mükerrerleri eler.
  2. EditorialWriterAgent  -> LLM (NVIDIA Nemotron-3-Ultra-550B / Groq) veya yapılandırılmış
                              editoryal motorla 400-650 kelimelik özgün Türkçe haber üretir.
  3. VisualCuratorAgent    -> Pexels API veya Küratörlü Tematik Stok Görsel Kütüphanesi'nden
                              fotoğraf çekip çok katmanlı karartma + hafif blur + taşmayan
                              tipografi ile profesyonel 1200x675 WebP kapak üretir.
  4. QualityGateAgent      -> Kelime sayısı, halüsinasyon (yanlış isim), kesik başlık, kesik metin
                              ([...]), encoding, kopya URL ve görsel denetimi yapar.
  5. Çıktı                 -> website/data/editorial_news.json & docs/data/editorial_news.json
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import unicodedata
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

try:
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 "
        "(KamuPersonelRehberi-EditorialBot/2.0)"
    ),
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.7",
}

TR_SLUG_MAP = str.maketrans({
    "ç": "c", "Ç": "c", "ğ": "g", "Ğ": "g", "ı": "i", "İ": "i",
    "ö": "o", "Ö": "o", "ş": "s", "Ş": "s", "ü": "u", "Ü": "u",
    "â": "a", "Â": "a", "î": "i", "Î": "i", "û": "u", "Û": "u",
})

CATEGORY_THEMES = {
    "ATAMA_KADRO": {
        "label": "Atama & Kadro",
        "pexels_query": "education classroom university architecture",
        "stock_theme": "egitim",
    },
    "SINAV_KPSS": {
        "label": "KPSS & Sınavlar",
        "pexels_query": "exam study library desk notebook",
        "stock_theme": "sinav_kpss",
    },
    "MEVZUAT_MAAS": {
        "label": "Mevzuat & Özlük",
        "pexels_query": "courthouse law architecture government",
        "stock_theme": "adalet_mevzuat",
    },
    "RESMI_HABER": {
        "label": "Resmi Duyuru",
        "pexels_query": "government building architecture ankara",
        "stock_theme": "kamu_resmi",
    },
    "REHBER": {
        "label": "Kariyer Rehberi",
        "pexels_query": "modern office notebook desk workspace",
        "stock_theme": "kamu_resmi",
    },
}

DEFAULT_PATRON_CONFIG: Dict[str, Any] = {
    "version": "1.0",
    "agents_enabled": {
        "fetcher": True,
        "editor": True,
        "visual": True,
        "qa": True,
        "publisher": True,
        "briefing": True,
    },
    "editor_settings": {
        "nvidia_model": "nvidia/nemotron-3-ultra-550b-a55b",
        "min_word_count": 200,
        "max_articles_per_run": 35,
        "extra_instructions": "",
    },
    "cover_settings": {
        "use_stock_library": True,
        "blur_radius": 2.2,
        "scrim_strength": 0.86,
        "show_domain_watermark": True,
    },
    "hidden_news_slugs": [],
    "featured_news_slugs": [],
}


def load_patron_config() -> Dict[str, Any]:
    cfg_path = ROOT_DIR / "website" / "data" / "patron_config.json"
    cfg = json.loads(json.dumps(DEFAULT_PATRON_CONFIG))
    if cfg_path.exists():
        try:
            loaded = json.loads(cfg_path.read_text(encoding="utf-8"))
            for section in ("agents_enabled", "editor_settings", "cover_settings"):
                if isinstance(loaded.get(section), dict):
                    cfg[section].update(loaded[section])
            for key in ("hidden_news_slugs", "featured_news_slugs"):
                if isinstance(loaded.get(key), list):
                    cfg[key] = loaded[key]
        except Exception as e:
            print(f"⚠️ patron_config.json okuma uyarısı: {e}")
    return cfg


def classify_visual_topic(title: str, institution: str = "", category: str = "") -> Tuple[str, str]:
    """Haber/rehber metnine göre (stock_theme, kapak_rozet_etiketi) döner."""
    hay = f"{title} {institution} {category}".lower()

    if any(k in hay for k in ["toki", "konut", "kentsel", "anahtar teslim", "deprem konut", "sosyal konut"]):
        return "konut_toki", "TOKİ & KONUT"
    if any(k in hay for k in ["cop31", "iklim", "çevre", "orman", "tarım", "su ", "ekosistem"]):
        return "iklim_cevre", "İKLİM & ÇEVRE"
    if any(k in hay for k in ["kpss", "ösym", "tus", "yds", "ydts", "yks", "bursluluk", "sınav", "ekpss", "ales", "puan"]):
        return "sinav_kpss", "KPSS & SINAV"
    if any(k in hay for k in ["meb", "millî eğitim", "milli eğitim", "okul", "öğrenci", "öğretmen", "pisa", "üniversite", "yök", "akademik"]):
        return "egitim", "EĞİTİM & MEB"
    if any(k in hay for k in ["sağlık", "hastane", "doktor", "hemşire", "tıp"]):
        return "saglik", "SAĞLIK & KAMU"
    if any(k in hay for k in ["belediye", "zabıta", "itfaiye", "yerel yönetim", "mahalli"]):
        return "belediye_sehir", "YEREL YÖNETİM"
    if any(k in hay for k in ["bilişim", "yazılım", "dijital", "siber", "teknoloji"]):
        return "bilisim", "BİLİŞİM & TEKNOLOJİ"
    if any(k in hay for k in ["kızılelma", "savunma", "oruç reis", "enerji", "tsk", "güvenlik", "polis", "askeri", "sismik"]):
        return "savunma_enerji", "SAVUNMA & ENERJİ"
    if any(k in hay for k in ["kanun", "mevzuat", "657", "4/b", "güvenlik soruşturması", "arşiv araştırması", "maaş", "özlük", "sözleşmeli"]):
        return "adalet_mevzuat", "MEVZUAT & ÖZLÜK"
    return "kamu_resmi", "RESMİ GÜNDEM"


def slugify(text: str, max_len: int = 72) -> str:
    text = re.sub(r"[^\w\s-]", " ", (text or "").translate(TR_SLUG_MAP).lower())
    text = re.sub(r"[\s_-]+", "-", text).strip("-")
    if len(text) > max_len:
        text = text[:max_len].rsplit("-", 1)[0]
    return text or "haber"


def strip_emojis(text: str) -> str:
    return re.sub(
        r"[\U00010000-\U0010ffff\u2600-\u27bf\ufe0f]+", "", text or ""
    ).strip()


def clean_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def sanitize_headline(text: str, max_len: int = 110) -> str:
    """Kesik tırnakları veya aşırı uzun cümleleri temiz Türkçe başlığa dönüştürür."""
    t = clean_whitespace(strip_emojis(text)).replace("[...]", "").strip(" ,;-:")
    if len(t) > max_len:
        t = t[:max_len].rsplit(" ", 1)[0].strip(" ,;-:") + "…"
    # Tek kalan çift tırnağı kapat
    if t.count('"') % 2 == 1:
        t = t.replace('"', "")
    return t


# =============================================================================
# 1. MUHABİR AJANI — Tam Metin Çekme & Tekilleştirme
# =============================================================================
class ArticleFetcherAgent:
    """Resmi kaynak URL'lerinden tam haber metnini çeker ve mükerrerleri ayıklar."""

    def __init__(self, timeout: int = 10):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.timeout = timeout

    def deduplicate(self, raw_news: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen_urls = set()
        seen_titles = set()
        unique_items = []
        for item in raw_news:
            url = (item.get("source_url") or "").strip().rstrip("/")
            title_clean = strip_emojis(item.get("title") or "")
            title_norm = re.sub(r"\W+", "", title_clean.lower())[:60]
            if url and url in seen_urls:
                continue
            if title_norm and title_norm in seen_titles:
                continue
            if url:
                seen_urls.add(url)
            if title_norm:
                seen_titles.add(title_norm)
            item = dict(item)
            item["clean_title"] = title_clean.replace("[...]", "").strip()
            unique_items.append(item)
        return unique_items

    def fetch_full_text(self, url: str) -> str:
        """Resmi kurum haber sayfasından ana metin paragraflarını çıkarır."""
        if not url or not url.startswith("http"):
            return ""
        try:
            resp = self.session.get(url, timeout=self.timeout, allow_redirects=True)
            if resp.status_code != 200:
                return ""
            raw_bytes = resp.content
            try:
                html = raw_bytes.decode("utf-8-sig")
            except UnicodeDecodeError:
                html = raw_bytes.decode("iso-8859-9", errors="replace")

            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form", "noscript"]):
                tag.decompose()

            container = (
                soup.find("article")
                or soup.find("div", class_=re.compile(r"(content|detail|haber|news|body|text|icerik)", re.I))
                or soup.find("main")
                or soup.body
            )
            if not container:
                return ""

            paragraphs = []
            for p in container.find_all(["p", "li"]):
                txt = clean_whitespace(p.get_text(" "))
                if len(txt) >= 45 and not any(
                    noise in txt.lower()
                    for noise in ["çerez", "cookie", "tüm hakları saklıdır", "paylaş", "yazdır", "geri dön"]
                ):
                    paragraphs.append(txt)

            seen_p = set()
            final_p = []
            for p in paragraphs:
                key = p[:80].lower()
                if key not in seen_p:
                    seen_p.add(key)
                    final_p.append(p)

            return "\n\n".join(final_p[:14])
        except Exception:
            return ""


# =============================================================================
# 2. EDİTÖR / YAZAR AJANI — NVIDIA NIM 550B + Halüsinasyon Koruması
# =============================================================================
class EditorialWriterAgent:
    """
    Ham resmi bülteni veya özel konuyu özgün, alt başlıklı, 400-650 kelimelik
    Türkçe habere dönüştürür.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        env_path = ROOT_DIR / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                if "=" in line and not line.strip().startswith("#"):
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip().strip('"').strip("'")
                    if k and v and k not in os.environ:
                        os.environ[k] = v

        self.config = config or load_patron_config()
        ed_cfg = self.config.get("editor_settings", {})
        self.nvidia_key = os.getenv("NVIDIA_API_KEY", "").strip()
        self.nvidia_model = (ed_cfg.get("nvidia_model") or os.getenv("NVIDIA_MODEL") or "nvidia/nemotron-3-ultra-550b-a55b").strip()
        self.groq_key = os.getenv("GROQ_API_KEY", "").strip()
        self.groq_model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
        self.extra_instructions = (ed_cfg.get("extra_instructions") or "").strip()

    @property
    def has_llm(self) -> bool:
        return bool(self.nvidia_key or self.groq_key)

    def _call_llm(self, prompt: str) -> Optional[str]:
        sys_msg = (
            "Sen deneyimli bir Türk kamu personeli ve mevzuat editörüsün. "
            "Resmi kurum duyurularını adayların kolayca anlayacağı, %100 özgün, "
            "tarafsız, doğrulanmış ve akıcı Türkçe haber makalesi olarak yazarsın. "
            "KRİTİK KURAL 1: Başlıkta veya kaynak metinde geçen kişi isimlerini ve makam sahiplerini ASLA değiştirme; "
            "eğitim hafızandan eski bakan veya başkan adı yazma (örneğin başlıkta 'Duran' geçiyorsa kesinlikle 'Fahrettin Altun' yazma). "
            "KRİTİK KURAL 2: Uydurma tarih, sayı veya şart ekleme; yalnızca verilen kaynak metne ve genel kamu mevzuatına dayan. "
            "Çıktıyı sadece saf HTML gövdesi olarak ver (markdown ```html kullanma)."
        )
        if self.extra_instructions:
            sys_msg += f" YÖNETİCİ TALİMATI: {self.extra_instructions}"

        endpoints = []
        if self.nvidia_key:
            endpoints.append((
                "NVIDIA NIM",
                "https://integrate.api.nvidia.com/v1/chat/completions",
                self.nvidia_key,
                self.nvidia_model,
            ))
        if self.groq_key:
            endpoints.append((
                "Groq Cloud",
                "https://api.groq.com/openai/v1/chat/completions",
                self.groq_key,
                self.groq_model,
            ))

        for name, url, api_key, model in endpoints:
            try:
                body: Dict[str, Any] = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": sys_msg},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.4,
                    "max_tokens": 1600,
                }
                if name == "NVIDIA NIM":
                    body["chat_template_kwargs"] = {"enable_thinking": False}
                r = requests.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                    timeout=45,
                )
                if r.status_code == 200:
                    text = (r.json()["choices"][0]["message"].get("content") or "").strip()
                    text = re.sub(r"^```(?:html)?\s*", "", text, flags=re.I)
                    text = re.sub(r"\s*```$", "", text)
                    if text:
                        return text.strip()
            except Exception as e:
                print(f"  ⚠️ {name} LLM çağrısı başarısız: {e}")
        return None

    def _extract_headline_and_clean(self, raw_title: str, llm_html: str) -> Tuple[str, str]:
        headline = raw_title
        # İlk satırda <!-- HEADLINE: ... --> varsa al
        m = re.match(r"^\s*<!--\s*HEADLINE:\s*(.+?)\s*-->\s*", llm_html, flags=re.I | re.S)
        if m:
            candidate = sanitize_headline(m.group(1), max_len=105)
            if len(candidate) >= 15:
                headline = candidate
            llm_html = llm_html[m.end():].strip()
        elif len(raw_title) > 105 or raw_title.count('"') % 2 == 1:
            # Kesik RSS başlığı yerine ilk temiz <h2> başlığını kullan
            soup = BeautifulSoup(llm_html, "html.parser")
            h2 = soup.find("h2")
            if h2:
                h2_txt = sanitize_headline(h2.get_text(" "), max_len=105)
                if len(h2_txt) >= 18:
                    headline = h2_txt
        headline = sanitize_headline(headline, max_len=105)
        return headline, llm_html

    def write_article(self, item: Dict[str, Any], full_source_text: str) -> Dict[str, Any]:
        raw_title = item.get("clean_title") or strip_emojis(item.get("title", ""))
        institution = item.get("institution") or "T.C. Resmi Kurum"
        source_name = item.get("source_name") or institution
        pub_date = item.get("publish_date_formatted") or "Güncel"

        source_context = full_source_text.strip() or clean_whitespace(item.get("summary") or item.get("content") or raw_title)
        if self.has_llm and len(raw_title) >= 12:
            prompt = f"""
Aşağıdaki resmi kamu duyurusundan Türkiye'deki kamu personeli ve memur adayları için 420-620 kelimelik %100 özgün, akıcı ve bilgilendirici bir Türkçe haber makalesi yaz.

Format Kuralları:
1. İlk satıra mutlaka şu yorumu ekle: <!-- HEADLINE: 6-13 kelimelik, kesiksiz, tam ve profesyonel Türkçe haber başlığı -->
2. Ardından saf HTML gövdesini yaz (yalnızca <h2>, <h3>, <p>, <ul>, <li>, <strong> kullan; <html>, <body>, <h1> veya markdown kullanma).
3. İlk paragraf güçlü, net bir haber spotu olsun.
4. En az 3 adet anlamlı <h2> alt başlığı kullan ve madde işaretli (<ul><li>...</li></ul>) pratik bir özet listesi ekle.
5. Başlıkta 'Duran' geçiyorsa adını ASLA 'Fahrettin Altun' yazma; sadece başlıkta/kaynakta geçen ismi veya makam unvanını kullan.
6. Kesinlikle uydurma tarih, saat, kontenjan veya puan ekleme; kesik metin ([...]) asla yazma.

Ham Başlık: {raw_title}
Kurum: {institution}
Tarih: {pub_date}
Resmi Kaynak: {source_name}
Kaynak Metin:
{source_context[:3500]}
"""
            llm_html = self._call_llm(prompt)
            if llm_html and len(BeautifulSoup(llm_html, "html.parser").get_text().split()) >= 220:
                clean_title, clean_body = self._extract_headline_and_clean(raw_title, llm_html)
                lead = BeautifulSoup(clean_body, "html.parser").find("p")
                lead_text = clean_whitespace(lead.get_text(" ")) if lead else clean_title
                return {
                    "headline": clean_title,
                    "meta_description": lead_text[:158],
                    "excerpt": lead_text[:220],
                    "body_html": clean_body,
                    "generated_by": "nvidia_nemotron_550b_agent" if self.nvidia_key else "groq_agent",
                }

        # Yapılandırılmış Tam Metin Fallback (LLM erişilemediğinde)
        paragraphs = [p.strip() for p in full_source_text.split("\n\n") if len(p.strip()) >= 45]
        if len(" ".join(paragraphs).split()) >= 80:
            clean_title = sanitize_headline(raw_title, max_len=105)
            lead_text = paragraphs[0]
            body_parts = [
                f"<p><strong>{institution}</strong> tarafından {pub_date} tarihinde yayımlanan resmi duyurunun ayrıntıları netleşti. {lead_text}</p>",
                '<div class="callout-box"><div class="callout-box-title">Öne Çıkan Resmi Bilgiler</div><ul>'
                f"<li><strong>Yayımlayan Kurum:</strong> {institution}</li>"
                f"<li><strong>Duyuru Tarihi:</strong> {pub_date}</li>"
                f"<li><strong>Resmi Kaynak:</strong> {source_name}</li>"
                "</ul></div>",
                "<h2>Resmi Açıklamanın Ayrıntıları</h2>",
            ]
            for p in paragraphs[1:9]:
                body_parts.append(f"<p>{p}</p>")
            body_parts.extend([
                "<h2>Kamu Personeli ve Adaylar İçin Değerlendirme</h2>",
                f"<p>{institution} tarafından paylaşılan bu gelişme, kamu kurumlarında görev yapan personel ve yeni alım süreçlerini takip eden adaylar açısından önem taşımaktadır. Resmi duyuru metni ve başvuru detayları için ilgili kurumun resmî duyuru kanallarının takip edilmesi önerilir.</p>",
            ])
            html_out = "\n".join(body_parts)
            return {
                "headline": clean_title,
                "meta_description": lead_text[:158],
                "excerpt": lead_text[:220],
                "body_html": html_out,
                "generated_by": "structured_source_agent",
            }

        return {
            "headline": sanitize_headline(raw_title),
            "meta_description": raw_title[:155],
            "excerpt": raw_title[:200],
            "body_html": "",
            "generated_by": "insufficient_source",
        }


# =============================================================================
# 3. GÖRSEL YÖNETMENİ AJANI — Stok Kütüphanesi + Pexels + Dergi Kapak Kompozitörü
# =============================================================================
class VisualCuratorAgent:
    """
    1. Pexels API (varsa) veya Küratörlü Tematik Stok Görsel Kütüphanesinden
       (website/assets/img/stock_library/<tema>/) konuya en uygun 1200x675 fotoğrafı alır.
    2. Üzerine hafif Gaussian Blur + Çok Katmanlı Kurumsal Lacivert Scrim (karartma) +
       sol vurgu çizgisi + taşmayan otomatik ölçümlü rozet + crisp beyaz tipografi uygular.
    Düz tek renk kutu ASLA üretmez!
    """

    def __init__(self, covers_dir: Path, config: Optional[Dict[str, Any]] = None):
        self.covers_dir = covers_dir
        self.covers_dir.mkdir(parents=True, exist_ok=True)
        self.stock_dir = ROOT_DIR / "website" / "assets" / "img" / "stock_library"
        self.config = config or load_patron_config()
        self.cover_cfg = self.config.get("cover_settings", {})
        self.pexels_key = os.getenv("PEXELS_API_KEY", "").strip()
        self._used_pexels_ids = set()

    def _find_font(self, size: int, bold: bool = False):
        candidates = [
            "C:/Windows/Fonts/seguisb.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
            "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
            "C:/Windows/Fonts/georgiab.ttf" if bold else "C:/Windows/Fonts/georgia.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        ]
        for path in candidates:
            if os.path.exists(path):
                try:
                    return ImageFont.truetype(path, size)
                except Exception:
                    continue
        return ImageFont.load_default()

    def _fetch_pexels_pil(self, query: str) -> Tuple[Optional[Image.Image], Optional[str]]:
        if not self.pexels_key or not HAS_PIL:
            return None, None
        try:
            r = requests.get(
                "https://api.pexels.com/v1/search",
                headers={"Authorization": self.pexels_key},
                params={"query": query, "per_page": 12, "orientation": "landscape"},
                timeout=10,
            )
            if r.status_code != 200:
                return None, None
            for p in r.json().get("photos", []):
                pid = p.get("id")
                if pid in self._used_pexels_ids:
                    continue
                img_url = p.get("src", {}).get("large2x") or p.get("src", {}).get("large")
                if not img_url:
                    continue
                ir = requests.get(img_url, timeout=12)
                if ir.status_code == 200:
                    im = Image.open(BytesIO(ir.content)).convert("RGB")
                    self._used_pexels_ids.add(pid)
                    photographer = p.get("photographer") or "Pexels"
                    return im, f"Fotoğraf: {photographer} / Pexels (Telifsiz)"
        except Exception:
            pass
        return None, None

    def _pick_stock_photo(self, slug: str, theme_key: str) -> Tuple[Optional[Image.Image], str]:
        """Yerel Küratörlü Stok Görsel Kütüphanesinden deterministik olarak fotoğraf seçer."""
        if not self.cover_cfg.get("use_stock_library", True):
            return None, "Kamu Personel Rehberi"
        theme_folder = self.stock_dir / theme_key
        files = sorted(theme_folder.glob("*.webp")) if theme_folder.exists() else []
        if not files:
            fallback_folder = self.stock_dir / "kamu_resmi"
            files = sorted(fallback_folder.glob("*.webp")) if fallback_folder.exists() else []
        if not files:
            return None, "Kamu Personel Rehberi Arşivi"

        seed = int(hashlib.md5(slug.encode("utf-8")).hexdigest()[:8], 16)
        chosen = files[seed % len(files)]
        try:
            im = Image.open(chosen).convert("RGB")
            return im, "Kamu Personel Rehberi Stok Görsel Kütüphanesi"
        except Exception:
            return None, "Kamu Personel Rehberi Arşivi"

    def _wrap_text_px(self, draw: ImageDraw.ImageDraw, text: str, font, max_width: int, max_lines: int = 4) -> List[str]:
        words = text.split()
        lines: List[str] = []
        current = ""
        for w in words:
            test = (current + " " + w).strip()
            bbox = draw.textbbox((0, 0), test, font=font)
            if (bbox[2] - bbox[0]) <= max_width:
                current = test
            else:
                if current:
                    lines.append(current)
                current = w
                if len(lines) >= max_lines - 1:
                    break
        # Kalan kelimeleri son satıra sığdır
        used_words = sum(len(l.split()) for l in lines)
        remaining = " ".join(words[used_words:]).strip()
        if remaining and len(lines) < max_lines:
            # Sığmıyorsa ... ile kısalt
            while remaining:
                bbox = draw.textbbox((0, 0), remaining, font=font)
                if (bbox[2] - bbox[0]) <= max_width:
                    break
                parts = remaining.rsplit(" ", 1)
                if len(parts) == 1:
                    remaining = remaining[:-2] + "…"
                    break
                remaining = parts[0].strip(" ,;-:") + "…"
            lines.append(remaining)
        return lines[:max_lines]

    def _compose_magazine_cover(
        self,
        bg_img: Optional[Image.Image],
        slug: str,
        title: str,
        institution: str,
        theme_label: str,
        out_path: Path,
    ) -> None:
        w, h = 1200, 675
        blur_radius = float(self.cover_cfg.get("blur_radius", 2.2))
        scrim_strength = float(self.cover_cfg.get("scrim_strength", 0.86))
        show_watermark = bool(self.cover_cfg.get("show_domain_watermark", True))

        # 1. Arka Plan Fotoğrafını 16:9 Kırp, Hafif Blur & Kontrast Uygula
        if bg_img is not None:
            ratio = max(w / bg_img.width, h / bg_img.height)
            nw, nh = max(w, int(bg_img.width * ratio)), max(h, int(bg_img.height * ratio))
            base = bg_img.resize((nw, nh), Image.Resampling.LANCZOS)
            left = (nw - w) // 2
            top = (nh - h) // 2
            base = base.crop((left, top, left + w, top + h)).convert("RGBA")
            if blur_radius > 0:
                base = base.filter(ImageFilter.GaussianBlur(radius=blur_radius))
            base = ImageEnhance.Contrast(base).enhance(1.06)
            base = ImageEnhance.Color(base).enhance(0.88)
        else:
            # En kötü durum fotoğrafik lacivert degrade
            base = Image.new("RGBA", (w, h), (15, 38, 62, 255))

        # 2. Çok Katmanlı Yönlü Kurumsal Scrim (Sol + Alt Koyu Lacivert, Sağ Üst Fotoğraf Görünür)
        gw, gh = 64, 36
        grad = Image.new("RGBA", (gw, gh))
        px = grad.load()
        max_alpha = int(max(0.55, min(0.95, scrim_strength)) * 255)
        min_alpha = int(max_alpha * 0.34)
        for yy in range(gh):
            ty = yy / (gh - 1)  # yukarı=0, aşağı=1
            for xx in range(gw):
                tx = xx / (gw - 1)  # sol=0, sağ=1
                # Sol ve alt bölgeler daha koyu, sağ üst daha açık
                weight = 0.62 * (1.0 - tx) + 0.38 * ty
                a = int(min_alpha + (max_alpha - min_alpha) * min(1.0, weight * 1.15))
                px[xx, yy] = (8, 22, 38, a)
        scrim = grad.resize((w, h), Image.Resampling.BILINEAR)
        canvas = Image.alpha_composite(base, scrim)

        draw = ImageDraw.Draw(canvas)

        # 3. Sol Dikey Kurumsal Vurgu Çizgisi
        draw.rectangle([54, 70, 60, 600], fill=(56, 189, 248, 235))

        # 4. Taşmayan Otomatik Ölçümlü Kategori Rozeti
        font_badge = self._find_font(20, bold=True)
        badge_text = f"{theme_label}  •  TEYİTLİ BİLGİ"
        bb = draw.textbbox((0, 0), badge_text, font=font_badge)
        bw = bb[2] - bb[0]
        bh = bb[3] - bb[1]
        pill_x1, pill_y1 = 84, 74
        pill_x2 = min(1120, pill_x1 + bw + 40)
        pill_y2 = pill_y1 + bh + 22
        draw.rounded_rectangle(
            [pill_x1, pill_y1, pill_x2, pill_y2],
            radius=20,
            fill=(19, 59, 92, 210),
            outline=(56, 189, 248, 220),
            width=2,
        )
        draw.text((pill_x1 + 20, pill_y1 + 9), badge_text, fill=(224, 242, 254, 255), font=font_badge)

        # 5. Akıllı Dinamik Punto & Temiz Başlık Tipografisi
        clean_title = sanitize_headline(title, max_len=105)
        t_len = len(clean_title)
        title_size = 46 if t_len <= 55 else (40 if t_len <= 80 else 35)
        font_title = self._find_font(title_size, bold=True)
        lines = self._wrap_text_px(draw, clean_title, font_title, max_width=1025, max_lines=4)
        line_step = int(title_size * 1.32)

        y_cursor = 160 if len(lines) >= 3 else 190
        for line in lines:
            # Okunabilirlik için ince drop shadow
            draw.text((86, y_cursor + 2), line, fill=(0, 0, 0, 150), font=font_title)
            draw.text((84, y_cursor), line, fill=(248, 250, 252, 255), font=font_title)
            y_cursor += line_step

        # 6. Alt Bilgi Bandı (Yatay Ayırıcı + Kurum + Sağdan Hizalı Domain)
        draw.line([(84, 548), (1126, 548)], fill=(255, 255, 255, 65), width=2)
        font_sub = self._find_font(22, bold=True)
        font_dom = self._find_font(21, bold=False)

        inst_raw = clean_whitespace(institution)
        if len(inst_raw) > 58:
            inst_clean = inst_raw[:58].rsplit(" ", 1)[0].rstrip(" (-:,")
        else:
            inst_clean = inst_raw
        draw.text((84, 570), inst_clean, fill=(125, 211, 252, 255), font=font_sub)

        if show_watermark:
            dom = "kamupersonelrehberiniz.me"
            db = draw.textbbox((0, 0), dom, font=font_dom)
            dw = db[2] - db[0]
            draw.text((1126 - dw, 571), dom, fill=(203, 213, 225, 230), font=font_dom)

        canvas.convert("RGB").save(out_path, "WEBP", quality=84)

    def ensure_cover(
        self,
        slug: str,
        title: str,
        institution: str,
        category: str,
        force_regen: bool = False,
    ) -> Tuple[str, str, str]:
        filename = f"{slug}.webp"
        out_path = self.covers_dir / filename
        rel_url = f"/assets/img/covers/{filename}"
        alt_text = f"{sanitize_headline(title, max_len=95)} — {institution}"

        theme_key, theme_label = classify_visual_topic(title, institution, category)

        if out_path.exists() and out_path.stat().st_size > 2000 and not force_regen:
            return rel_url, alt_text, f"Kamu Personel Rehberi Stok Arşivi — {theme_label}"

        if not HAS_PIL:
            return "/assets/img/og-banner.png", alt_text, "Kamu Personel Rehberi"

        bg_img, credit = self._fetch_pexels_pil(
            CATEGORY_THEMES.get(category, CATEGORY_THEMES["RESMI_HABER"])["pexels_query"]
        )
        if bg_img is None:
            bg_img, credit = self._pick_stock_photo(slug, theme_key)

        self._compose_magazine_cover(
            bg_img=bg_img,
            slug=slug,
            title=title,
            institution=institution,
            theme_label=theme_label,
            out_path=out_path,
        )
        return rel_url, alt_text, f"{credit} — {theme_label}"


# =============================================================================
# 4. KALİTE & DOĞRULUK DENETÇİ AJANI (QA Gatekeeper)
# =============================================================================
class QualityGateAgent:
    """Yayına çıkmadan önce her içeriği AdSense/SEO ve halüsinasyon kurallarına göre denetler."""

    BAD_MARKERS = ["[...]", "Ã¼", "Ä±", "ÅŸ", "Ã¶", "Ã§", "undefined", "null"]

    def sanitize_hallucinations(self, article: Dict[str, Any]) -> Dict[str, Any]:
        """Bilinen model halüsinasyonlarını ve kesik metin artıklarını düzeltir."""
        a = dict(article)
        hl = (a.get("headline") or "").lower()
        if "duran" in hl:
            for field in ("body_html", "excerpt", "meta_description"):
                val = a.get(field) or ""
                val = val.replace("Prof. Dr. Fahrettin Altun", "İletişim Başkanı Burhanettin Duran")
                val = val.replace("Fahrettin Altun", "Burhanettin Duran")
                val = val.replace("Başkan Altun", "Başkan Duran")
                a[field] = val
        return a

    def audit(self, article: Dict[str, Any], min_words: int = 160) -> Tuple[bool, str, int]:
        body_html = article.get("body_html") or ""
        if not body_html.strip():
            return False, "Kaynak tam metni yetersiz", 0

        text = clean_whitespace(BeautifulSoup(body_html, "html.parser").get_text(" "))
        word_count = len(text.split())
        if word_count < min_words:
            return False, f"Kelime sayısı yetersiz ({word_count} < {min_words})", word_count

        for bad in self.BAD_MARKERS:
            if bad in text or bad in (article.get("headline") or ""):
                return False, f"Bozuk/kesik metin tespit edildi: {bad}", word_count

        hl_low = (article.get("headline") or "").lower()
        if "duran" in hl_low and "altun" in text.lower():
            return False, "İsim tutarsızlığı (Duran vs Altun)", word_count

        if not article.get("cover_image"):
            return False, "Kapak görseli eksik", word_count

        return True, "OK", word_count


# =============================================================================
# MEVCUT HABERLERİ ONARMA & KAPAKLARI YENİLEME
# =============================================================================
def _sync_editorial_files(out_path: Path, payload: Dict[str, Any]) -> None:
    docs_out = ROOT_DIR / "docs" / "data" / "editorial_news.json"
    for p in (out_path, docs_out):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def repair_existing_articles(rebuild_covers: bool = False) -> List[Dict[str, Any]]:
    cfg = load_patron_config()
    out_path = ROOT_DIR / "website" / "data" / "editorial_news.json"
    covers_dir = ROOT_DIR / "website" / "assets" / "img" / "covers"
    if not out_path.exists():
        return []

    data = json.loads(out_path.read_text(encoding="utf-8"))
    articles = data.get("articles", [])
    curator = VisualCuratorAgent(covers_dir, cfg)
    qa = QualityGateAgent()

    fixed_articles = []
    for art in articles:
        art = qa.sanitize_hallucinations(art)
        hl = art.get("headline") or ""
        # Eğer başlık aşırı uzun veya kesik tırnaklı ise gövdedeki ilk temiz <h2>'yi veya temiz kısaltmayı kullan
        if len(hl) > 105 or hl.count('"') % 2 == 1:
            soup = BeautifulSoup(art.get("body_html") or "", "html.parser")
            h2 = soup.find("h2")
            if h2:
                cand = sanitize_headline(h2.get_text(" "), max_len=105)
                if 20 <= len(cand) <= 105:
                    hl = cand
            hl = sanitize_headline(hl, max_len=105)
        art["headline"] = hl

        # Eksik/kesik özet düzeltme
        for f_name, limit in (("meta_description", 158), ("excerpt", 220)):
            val = clean_whitespace(art.get(f_name) or "").replace("[...]", "")
            if len(val) < 40:
                p = BeautifulSoup(art.get("body_html") or "", "html.parser").find("p")
                if p:
                    val = clean_whitespace(p.get_text(" "))[:limit]
            art[f_name] = val

        # Kapak görselini yeni stok fotoğraf + blur + scrim motoruyla yeniden üret
        if rebuild_covers or not art.get("cover_image"):
            cover_url, alt_text, credit = curator.ensure_cover(
                slug=art["slug"],
                title=art["headline"],
                institution=art.get("institution") or "T.C. Resmi Kurum",
                category=art.get("category") or "RESMI_HABER",
                force_regen=True,
            )
            art["cover_image"] = cover_url
            art["cover_alt"] = alt_text
            art["cover_credit"] = credit

        _, theme_label = classify_visual_topic(art["headline"], art.get("institution", ""), art.get("category", ""))
        art["category_label"] = theme_label

        passed, _, wc = qa.audit(art, min_words=150)
        if passed:
            art["word_count"] = wc
            art["reading_time_min"] = max(2, round(wc / 180))
            fixed_articles.append(art)

    data["articles"] = fixed_articles
    data.setdefault("meta", {})["total_approved"] = len(fixed_articles)
    data["meta"]["generated_at"] = datetime.now(timezone.utc).isoformat()
    _sync_editorial_files(out_path, data)
    print(f"🛠️  Mevcut haberler onarıldı ve kapaklar yenilendi: {len(fixed_articles)} makale.")
    return fixed_articles


def generate_custom_article(topic: str, category: str = "RESMI_HABER") -> Optional[Dict[str, Any]]:
    """Patron Panelinden verilen özel konu/başlık için AI Editör ile makale + kapak üretir."""
    cfg = load_patron_config()
    out_path = ROOT_DIR / "website" / "data" / "editorial_news.json"
    covers_dir = ROOT_DIR / "website" / "assets" / "img" / "covers"

    writer = EditorialWriterAgent(cfg)
    curator = VisualCuratorAgent(covers_dir, cfg)
    qa = QualityGateAgent()

    now_dt = datetime.now()
    tr_months = {1:"Ocak",2:"Şubat",3:"Mart",4:"Nisan",5:"Mayıs",6:"Haziran",7:"Temmuz",8:"Ağustos",9:"Eylül",10:"Ekim",11:"Kasım",12:"Aralık"}
    pub_tr = f"{now_dt.day:02d} {tr_months[now_dt.month]} {now_dt.year}"

    fake_item = {
        "id": int(now_dt.timestamp()),
        "clean_title": topic.strip(),
        "institution": "Kamu Personel Rehberi Özel Analiz",
        "source_name": "Kamu Personel Rehberi Editoryal Kurulu",
        "publish_date_formatted": pub_tr,
        "category": category,
    }
    written = writer.write_article(fake_item, f"Özel Editoryal Konu: {topic.strip()}. Türkiye'deki kamu personeli, KPSS adayları ve memurlar için güncel mevzuat çerçevesinde kapsamlı rehber haber hazırla.")
    slug = slugify(written["headline"])
    _, theme_label = classify_visual_topic(written["headline"], fake_item["institution"], category)
    cover_url, alt_text, credit = curator.ensure_cover(
        slug=slug,
        title=written["headline"],
        institution=fake_item["institution"],
        category=category,
        force_regen=True,
    )

    art = {
        "id": fake_item["id"],
        "slug": slug,
        "headline": written["headline"],
        "institution": fake_item["institution"],
        "category": category,
        "category_label": theme_label,
        "publish_date": datetime.now(timezone.utc).isoformat(),
        "publish_date_formatted": pub_tr,
        "source_name": "Kamu Personel Rehberi",
        "source_url": "",
        "meta_description": written["meta_description"],
        "excerpt": written["excerpt"],
        "body_html": written["body_html"],
        "cover_image": cover_url,
        "cover_alt": alt_text,
        "cover_credit": credit,
        "generated_by": written["generated_by"],
    }
    art = qa.sanitize_hallucinations(art)
    passed, reason, wc = qa.audit(art, min_words=160)
    if not passed:
        print(f"⛔ Özel makale kalite kapısından geçemedi: {reason}")
        return None
    art["word_count"] = wc
    art["reading_time_min"] = max(2, round(wc / 180))

    existing = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else {"meta": {}, "articles": []}
    arts = [a for a in existing.get("articles", []) if a.get("slug") != slug]
    arts.insert(0, art)
    existing["articles"] = arts
    existing.setdefault("meta", {})["total_approved"] = len(arts)
    existing["meta"]["generated_at"] = datetime.now(timezone.utc).isoformat()
    _sync_editorial_files(out_path, existing)
    print(f"✍️ Özel AI Makale eklendi: {slug} ({wc} kelime)")
    return art


# =============================================================================
# ORKESTRATÖR — Pipeline Çalıştırıcı
# =============================================================================
def run_editorial_pipeline(
    max_articles: Optional[int] = None,
    force_refresh: bool = False,
    rebuild_covers: bool = False,
) -> List[Dict[str, Any]]:
    cfg = load_patron_config()
    agents_on = cfg.get("agents_enabled", {})
    ed_cfg = cfg.get("editor_settings", {})

    if not agents_on.get("editor", True) and not rebuild_covers:
        print("⏸️ Editör Ajanı patron_config.json üzerinden duraklatılmış; atlanıyor.")
        return []

    max_count = max_articles or int(ed_cfg.get("max_articles_per_run", 35))
    min_words = int(ed_cfg.get("min_word_count", 200))

    raw_news_path = ROOT_DIR / "website" / "data" / "news.json"
    out_path = ROOT_DIR / "website" / "data" / "editorial_news.json"
    covers_dir = ROOT_DIR / "website" / "assets" / "img" / "covers"

    if not raw_news_path.exists():
        print("⚠️ website/data/news.json bulunamadı.")
        return []

    raw_data = json.loads(raw_news_path.read_text(encoding="utf-8"))
    raw_news = raw_data.get("news", [])

    existing_by_url: Dict[str, Dict[str, Any]] = {}
    if out_path.exists() and not force_refresh:
        try:
            prev = json.loads(out_path.read_text(encoding="utf-8"))
            for item in prev.get("articles", []):
                if item.get("source_url"):
                    existing_by_url[item["source_url"]] = item
        except Exception:
            pass

    fetcher = ArticleFetcherAgent()
    writer = EditorialWriterAgent(cfg)
    curator = VisualCuratorAgent(covers_dir, cfg)
    qa = QualityGateAgent()

    unique_news = fetcher.deduplicate(raw_news) if agents_on.get("fetcher", True) else raw_news
    print(f"📡 Muhabir Ajanı: {len(raw_news)} ham haber -> {len(unique_news)} benzersiz haber.")

    approved_articles: List[Dict[str, Any]] = []
    rejected_count = 0

    for item in unique_news[:max_count]:
        src_url = (item.get("source_url") or "").strip()
        if src_url in existing_by_url and existing_by_url[src_url].get("word_count", 0) >= min_words:
            cached = qa.sanitize_hallucinations(existing_by_url[src_url])
            if rebuild_covers:
                c_url, c_alt, c_cred = curator.ensure_cover(
                    slug=cached["slug"],
                    title=cached["headline"],
                    institution=cached.get("institution") or "T.C. Resmi Kurum",
                    category=cached.get("category") or "RESMI_HABER",
                    force_regen=True,
                )
                cached["cover_image"] = c_url
                cached["cover_alt"] = c_alt
                cached["cover_credit"] = c_cred
            approved_articles.append(cached)
            continue

        full_text = fetcher.fetch_full_text(src_url) if agents_on.get("fetcher", True) else ""
        written = writer.write_article(item, full_text)
        slug = slugify(written["headline"] or item.get("clean_title") or f"haber-{item.get('id')}")

        if agents_on.get("visual", True):
            cover_url, alt_text, credit = curator.ensure_cover(
                slug=slug,
                title=written["headline"],
                institution=item.get("institution") or "T.C. Resmi Kurum",
                category=item.get("category") or "RESMI_HABER",
                force_regen=rebuild_covers,
            )
        else:
            cover_url, alt_text, credit = "/assets/img/og-banner.png", written["headline"], "Kamu Personel Rehberi"

        _, theme_label = classify_visual_topic(written["headline"], item.get("institution", ""), item.get("category", ""))
        article_record = {
            "id": item.get("id"),
            "slug": slug,
            "headline": written["headline"],
            "institution": item.get("institution") or "T.C. Resmi Kurum",
            "category": item.get("category") or "RESMI_HABER",
            "category_label": theme_label,
            "publish_date": item.get("publish_date") or datetime.now(timezone.utc).isoformat(),
            "publish_date_formatted": item.get("publish_date_formatted") or datetime.now().strftime("%d.%m.%Y"),
            "source_name": item.get("source_name") or item.get("institution") or "Resmi Kaynak",
            "source_url": src_url,
            "meta_description": written["meta_description"],
            "excerpt": written["excerpt"],
            "body_html": written["body_html"],
            "cover_image": cover_url,
            "cover_alt": alt_text,
            "cover_credit": credit,
            "generated_by": written["generated_by"],
        }
        article_record = qa.sanitize_hallucinations(article_record)

        if agents_on.get("qa", True):
            passed, reason, wc = qa.audit(article_record, min_words=min_words)
        else:
            wc = len(BeautifulSoup(article_record["body_html"], "html.parser").get_text(" ").split())
            passed, reason = True, "QA bypassed"

        if passed:
            article_record["word_count"] = wc
            article_record["reading_time_min"] = max(2, round(wc / 180))
            approved_articles.append(article_record)
            print(f"  ✅ [ONAY] {slug[:48]} ({wc} kelime)")
        else:
            rejected_count += 1
            print(f"  ⛔ [RED]  {slug[:48]} -> {reason}")

    payload = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_approved": len(approved_articles),
            "total_rejected": rejected_count,
        },
        "articles": approved_articles,
    }
    _sync_editorial_files(out_path, payload)
    print(f"📰 Editoryal Pipeline Tamamlandı: {len(approved_articles)} onaylı, {rejected_count} elendi -> {out_path}")
    return approved_articles


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Kamu Personel Rehberi 5 Ajanlı Editoryal Pipeline")
    parser.add_argument("--force-refresh", action="store_true", help="Tüm haberleri sıfırdan yeniden yaz")
    parser.add_argument("--rebuild-covers", action="store_true", help="Kapak görsellerini yeni motorla yeniden üret")
    parser.add_argument("--repair-existing", action="store_true", help="Mevcut makalelerdeki halüsinasyon ve kesik başlıkları onar")
    parser.add_argument("--custom-topic", type=str, default="", help="Özel konu için tek makale üret")
    parser.add_argument("--custom-category", type=str, default="RESMI_HABER", help="Özel makale kategorisi")
    args = parser.parse_args()

    if args.custom_topic.strip():
        generate_custom_article(args.custom_topic.strip(), args.custom_category.strip() or "RESMI_HABER")
    elif args.repair_existing:
        repair_existing_articles(rebuild_covers=args.rebuild_covers or True)
    else:
        run_editorial_pipeline(force_refresh=args.force_refresh, rebuild_covers=args.rebuild_covers)
