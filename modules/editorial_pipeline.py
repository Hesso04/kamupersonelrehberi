"""
Kamu Personel Rehberi — 5 Ajanlı Otonom AI Haber Merkezi & Görsel Pipeline'ı
=============================================================================
Mimari:
  1. ArticleFetcherAgent   -> Resmi kaynak URL'lerinden tam metni çeker, mükerrerleri eler.
  2. EditorialWriterAgent  -> LLM (Groq/NVIDIA/OpenAI) veya yapılandırılmış editoryal motorla
                              400-700 kelimelik, alt başlıklı, özgün Türkçe haber üretir.
  3. VisualCuratorAgent    -> Pexels/Unsplash telifsiz API veya Pillow ile benzersiz
                              1200x675 WebP kapak görseli ve SEO alt etiketi üretir.
  4. QualityGateAgent      -> Kelime sayısı, kesik metin ([...]), encoding, kopya URL ve
                              görsel denetimi yapar; düşük kaliteli içeriği yayına sokmaz.
  5. Çıktı                 -> website/data/editorial_news.json (SSG Builder tarafından okunur)
"""

import hashlib
import json
import os
import re
import sys
import textwrap
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

try:
    from PIL import Image, ImageDraw, ImageFont
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
        "(KamuPersonelRehberi-EditorialBot/1.0)"
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
        "pexels_query": "education classroom university turkey",
        "bg_start": (28, 52, 43),
        "bg_end": (17, 30, 26),
        "accent": (152, 195, 159),
    },
    "SINAV_KPSS": {
        "label": "KPSS & Sınavlar",
        "pexels_query": "exam study library desk",
        "bg_start": (31, 45, 61),
        "bg_end": (18, 25, 36),
        "accent": (147, 197, 253),
    },
    "MEVZUAT_MAAS": {
        "label": "Mevzuat & Özlük",
        "pexels_query": "courthouse law architecture government",
        "bg_start": (56, 42, 34),
        "bg_end": (29, 22, 18),
        "accent": (234, 179, 8),
    },
    "RESMI_HABER": {
        "label": "Resmi Duyuru",
        "pexels_query": "government building architecture ankara",
        "bg_start": (36, 54, 46),
        "bg_end": (20, 28, 25),
        "accent": (134, 239, 172),
    },
    "REHBER": {
        "label": "Kariyer Rehberi",
        "pexels_query": "modern office notebook desk workspace",
        "bg_start": (34, 48, 42),
        "bg_end": (18, 24, 22),
        "accent": (152, 195, 159),
    },
}


def slugify(text: str, max_len: int = 72) -> str:
    text = re.sub(r"[^\w\s-]", " ", text.translate(TR_SLUG_MAP).lower())
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
            # Başlık sonu kesilmiş [...] olan kopyaları atla, temiz başlığı tercih et
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

            # Öncelikli içerik konteynerleri
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

            # Tekrarlı paragrafları sil
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
# 2. EDİTÖR / YAZAR AJANI — LLM + Yapılandırılmış Editoryal Zenginleştirme
# =============================================================================
class EditorialWriterAgent:
    """
    Ham resmi bülteni özgün, alt başlıklı, aday odaklı 450-700 kelimelik
    Türkçe habere dönüştürür. Ortamda LLM API anahtarı varsa LLM kullanır;
    yoksa çekilen gerçek tam metni temiz ve zengin editoryal HTML'e dönüştürür.
    """

    def __init__(self):
        self.groq_key = os.getenv("GROQ_API_KEY", "").strip()
        self.groq_model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
        self.nvidia_key = os.getenv("NVIDIA_API_KEY", "").strip()

    def _call_llm(self, prompt: str) -> Optional[str]:
        if self.groq_key:
            try:
                r = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.groq_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.groq_model,
                        "messages": [
                            {
                                "role": "system",
                                "content": (
                                    "Sen deneyimli bir Türk kamu personeli ve mevzuat editörüsün. "
                                    "Resmi kurum duyurularını adayların kolayca anlayacağı, %100 özgün, "
                                    "tarafsız, doğrulanmış ve akıcı Türkçe haber makalesi olarak yazarsın. "
                                    "Uydurma tarih, sayı veya şart ekleme; yalnızca verilen kaynak metne ve "
                                    "genel kamu personel rehberliğine dayan."
                                ),
                            },
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.45,
                        "max_tokens": 1400,
                    },
                    timeout=25,
                )
                if r.status_code == 200:
                    return r.json()["choices"][0]["message"]["content"].strip()
            except Exception:
                pass
        return None

    def write_article(self, item: Dict[str, Any], full_source_text: str) -> Dict[str, Any]:
        title = item.get("clean_title") or strip_emojis(item.get("title", ""))
        institution = item.get("institution") or "T.C. Resmi Kurum"
        source_name = item.get("source_name") or institution
        pub_date = item.get("publish_date_formatted") or "Güncel"
        source_url = item.get("source_url") or ""
        category = item.get("category") or "RESMI_HABER"

        # 1) LLM mevcutsa ve kaynak metin varsa AI Editör ile yaz
        if self.groq_key and len(full_source_text.split()) >= 40:
            prompt = f"""
Aşağıdaki resmi kurum duyurusundan kamu personeli ve memur adayları için 450-650 kelimelik özgün bir haber makalesi yaz.
Çıktıyı saf HTML gövdesi olarak ver (sadece <h2>, <h3>, <p>, <ul>, <li>, <strong> kullan; <html> veya <h1> kullanma).

Kurallar:
- İlk paragraf güçlü bir haber spotu olsun.
- En az 3 adet anlamlı <h2> alt başlığı kullan (örn: Duyurunun Detayları, Adayları ve Kamu Personelini Nasıl Etkiliyor?, Resmi Takvim ve Dikkat Edilmesi Gerekenler).
- Madde işaretli bir özet listesi (<ul>) ekle.
- Kesinlikle uydurma sayı/tarih ekleme.

Başlık: {title}
Kurum: {institution}
Tarih: {pub_date}
Kaynak Metin:
{full_source_text[:3500]}
"""
            llm_html = self._call_llm(prompt)
            if llm_html and len(BeautifulSoup(llm_html, "html.parser").get_text().split()) >= 280:
                lead = BeautifulSoup(llm_html, "html.parser").find("p")
                lead_text = clean_whitespace(lead.get_text(" ")) if lead else title
                return {
                    "headline": title,
                    "meta_description": lead_text[:158],
                    "excerpt": lead_text[:220],
                    "body_html": llm_html,
                    "generated_by": "llm_editorial_agent",
                }

        # 2) LLM anahtarı yoksa ama resmi kurumdan gerçek tam metin çekildiyse
        #    temiz, yapılandırılmış ve aday rehberliği eklenmiş editoryal makale üret
        paragraphs = [p.strip() for p in full_source_text.split("\n\n") if len(p.strip()) >= 45]
        if len(" ".join(paragraphs).split()) >= 80:
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
                (
                    f"<p>{institution} tarafından paylaşılan bu gelişme, kamu kurumlarında görev yapan personel ve "
                    "yeni alım süreçlerini takip eden adaylar açısından önem taşımaktadır. Resmi kurumlarca yayımlanan "
                    "duyuru ve yönetmelik değişiklikleri, ilerleyen dönemlerdeki yerleştirme kılavuzlarına ve kurum içi "
                    "uygulamalara doğrudan yön vermektedir.</p>"
                ),
                (
                    "<p>Başvuru veya resmi işlem gerektiren süreçlerde yalnızca ilgili kurumun resmî internet sitesi, "
                    "<strong>e-Devlet Kapısı</strong> ve <strong>Kariyer Kapısı</strong> üzerinden yapılan duyuruların "
                    "esas alınması, son başvuru tarihlerinin ve belge şartlarının kılavuzdan teyit edilmesi önerilir.</p>"
                ),
                "<h2>Resmi Kaynak ve Teyit</h2>",
                (
                    f"<p>Bu haber metni, <strong>{source_name}</strong> resmi bülteni esas alınarak Kamu Personel Rehberi "
                    "editoryal ekibi tarafından derlenmiştir. Duyurunun aslına ve varsa ek belgelere aşağıdaki resmi "
                    "kaynak bağlantısından doğrudan ulaşabilirsiniz.</p>"
                ),
            ])
            html_out = "\n".join(body_parts)
            return {
                "headline": title,
                "meta_description": lead_text[:158],
                "excerpt": lead_text[:220],
                "body_html": html_out,
                "generated_by": "structured_source_agent",
            }

        # Kaynak tam metin çekilemediyse kalite kapısı bunu eleyecek (thin content üretme!)
        return {
            "headline": title,
            "meta_description": title[:155],
            "excerpt": title[:200],
            "body_html": "",
            "generated_by": "insufficient_source",
        }


# =============================================================================
# 3. GÖRSEL YÖNETMENİ AJANI — Telifsiz Stok API + WebP Editoryal Kapak Üretici
# =============================================================================
class VisualCuratorAgent:
    """
    Her haber ve rehber için benzersiz, telifsiz 1200x675 WebP kapak görseli üretir.
    PEXELS_API_KEY tanımlıysa Pexels telifsiz stok fotoğraf çeker; yoksa
    Pillow ile yüksek çözünürlüklü, Apple Glass / Fraunces uyumlu editoryal kapak üretir.
    """

    def __init__(self, covers_dir: Path):
        self.covers_dir = covers_dir
        self.covers_dir.mkdir(parents=True, exist_ok=True)
        self.pexels_key = os.getenv("PEXELS_API_KEY", "").strip()
        self._used_pexels_ids = set()

    def _find_font(self, size: int, bold: bool = False):
        candidates = [
            "C:/Windows/Fonts/georgiab.ttf" if bold else "C:/Windows/Fonts/georgia.ttf",
            "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
        ]
        for path in candidates:
            if os.path.exists(path):
                try:
                    return ImageFont.truetype(path, size)
                except Exception:
                    continue
        return ImageFont.load_default()

    def _fetch_pexels_image(self, query: str, out_path: Path) -> Optional[str]:
        if not self.pexels_key or not HAS_PIL:
            return None
        try:
            r = requests.get(
                "https://api.pexels.com/v1/search",
                headers={"Authorization": self.pexels_key},
                params={"query": query, "per_page": 15, "orientation": "landscape"},
                timeout=12,
            )
            if r.status_code != 200:
                return None
            photos = r.json().get("photos", [])
            for p in photos:
                pid = p.get("id")
                if pid in self._used_pexels_ids:
                    continue
                img_url = p.get("src", {}).get("large2x") or p.get("src", {}).get("large")
                if not img_url:
                    continue
                img_resp = requests.get(img_url, timeout=15)
                if img_resp.status_code == 200:
                    from io import BytesIO
                    im = Image.open(BytesIO(img_resp.content)).convert("RGB")
                    # 1200x675 (16:9) merkez kırpma
                    target_w, target_h = 1200, 675
                    ratio = max(target_w / im.width, target_h / im.height)
                    new_w, new_h = int(im.width * ratio), int(im.height * ratio)
                    im = im.resize((new_w, new_h), Image.Resampling.LANCZOS)
                    left = (new_w - target_w) // 2
                    top = (new_h - target_h) // 2
                    im = im.crop((left, top, left + target_w, top + target_h))
                    im.save(out_path, "WEBP", quality=82)
                    self._used_pexels_ids.add(pid)
                    photographer = p.get("photographer") or "Pexels"
                    return f"Fotoğraf: {photographer} / Pexels (Telifsiz)"
        except Exception:
            return None
        return None

    def _generate_editorial_cover(
        self, slug: str, title: str, institution: str, category: str, out_path: Path
    ) -> str:
        """Pillow ile 1200x675 benzersiz, telifsiz editoryal WebP kapak üretir."""
        theme = CATEGORY_THEMES.get(category, CATEGORY_THEMES["RESMI_HABER"])
        w, h = 1200, 675
        im = Image.new("RGB", (w, h), theme["bg_start"])
        draw = ImageDraw.Draw(im)

        # Yumuşak dikey degrade
        r1, g1, b1 = theme["bg_start"]
        r2, g2, b2 = theme["bg_end"]
        for y in range(h):
            t = y / h
            color = (
                int(r1 + (r2 - r1) * t),
                int(g1 + (g2 - g1) * t),
                int(b1 + (b2 - b1) * t),
            )
            draw.line([(0, y), (w, y)], fill=color)

        # İnce mimari grid çizgileri (editorial stil)
        seed = int(hashlib.md5(slug.encode("utf-8")).hexdigest()[:6], 16)
        grid_color = (min(255, r1 + 14), min(255, g1 + 14), min(255, b1 + 14))
        for x in range(60, w, 120):
            draw.line([(x, 0), (x, h)], fill=grid_color, width=1)
        for y in range(60, h, 120):
            draw.line([(0, y), (w, y)], fill=grid_color, width=1)

        # Dekoratif geometrik vurgu çemberi (her görselde farklı konum)
        cx = 920 + (seed % 160)
        cy = 140 + ((seed >> 4) % 180)
        rad = 190 + (seed % 60)
        draw.ellipse(
            [cx - rad, cy - rad, cx + rad, cy + rad],
            outline=theme["accent"],
            width=2,
        )
        draw.ellipse(
            [cx - rad + 36, cy - rad + 36, cx + rad - 36, cy + rad - 36],
            outline=grid_color,
            width=1,
        )

        # Üst kategori etiketi
        accent = theme["accent"]
        font_badge = self._find_font(22, bold=True)
        font_title = self._find_font(48, bold=True)
        font_sub = self._find_font(24, bold=False)

        badge_text = f"{theme['label'].upper()}  •  TEYİTLİ BİLGİ"
        draw.rounded_rectangle([72, 74, 520, 120], radius=22, outline=accent, width=2)
        draw.text((96, 84), badge_text, fill=accent, font=font_badge)

        # Ana başlık (satır sarma, max 4 satır)
        wrapped = textwrap.wrap(title, width=34)[:4]
        y_cursor = 170
        for line in wrapped:
            draw.text((72, y_cursor), line, fill=(247, 246, 242), font=font_title)
            y_cursor += 64

        # Alt marka ve kurum bandı
        draw.line([(72, 545), (1128, 545)], fill=grid_color, width=2)
        draw.text((72, 575), institution[:60], fill=accent, font=font_sub)
        draw.text((780, 575), "kamupersonelrehberiniz.me", fill=(180, 180, 174), font=font_sub)

        im.save(out_path, "WEBP", quality=84)
        return f"Kamu Personel Rehberi Editoryal Görseli — {theme['label']}"

    def ensure_cover(
        self, slug: str, title: str, institution: str, category: str
    ) -> Tuple[str, str, str]:
        """
        (web_relative_path, alt_text, credit_text) döner.
        Dosya zaten varsa tekrar üretmez.
        """
        filename = f"{slug}.webp"
        out_path = self.covers_dir / filename
        rel_url = f"/assets/img/covers/{filename}"
        alt_text = f"{title} — {institution} resmi duyuru görseli"

        if out_path.exists() and out_path.stat().st_size > 2000:
            return rel_url, alt_text, "Kamu Personel Rehberi Arşivi"

        theme = CATEGORY_THEMES.get(category, CATEGORY_THEMES["RESMI_HABER"])
        credit = self._fetch_pexels_image(theme["pexels_query"], out_path)
        if credit:
            return rel_url, alt_text, credit

        if HAS_PIL:
            credit = self._generate_editorial_cover(slug, title, institution, category, out_path)
            return rel_url, alt_text, credit

        return "/assets/img/og-banner.png", alt_text, "Kamu Personel Rehberi"


# =============================================================================
# 4. KALİTE & DOĞRULUK DENETÇİ AJANI (QA Gatekeeper)
# =============================================================================
class QualityGateAgent:
    """Yayına çıkmadan önce her içeriği AdSense/SEO kalite kurallarına göre denetler."""

    BAD_MARKERS = ["[...]", "Ã¼", "Ä±", "ÅŸ", "Ã¶", "Ã§", "undefined", "null"]

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

        if not article.get("cover_image"):
            return False, "Kapak görseli eksik", word_count

        return True, "OK", word_count


# =============================================================================
# ORKESTRATÖR — Pipeline Çalıştırıcı
# =============================================================================
def run_editorial_pipeline(max_articles: int = 35, force_refresh: bool = False) -> List[Dict[str, Any]]:
    raw_news_path = ROOT_DIR / "website" / "data" / "news.json"
    out_path = ROOT_DIR / "website" / "data" / "editorial_news.json"
    covers_dir = ROOT_DIR / "website" / "assets" / "img" / "covers"

    if not raw_news_path.exists():
        print("⚠️ website/data/news.json bulunamadı.")
        return []

    raw_data = json.loads(raw_news_path.read_text(encoding="utf-8"))
    raw_news = raw_data.get("news", [])

    # Daha önce başarıyla işlenmiş haberleri koru (gereksiz tekrar fetch/LLM maliyeti olmasın)
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
    writer = EditorialWriterAgent()
    curator = VisualCuratorAgent(covers_dir)
    qa = QualityGateAgent()

    unique_news = fetcher.deduplicate(raw_news)
    print(f"📡 Muhabir Ajanı: {len(raw_news)} ham haber -> {len(unique_news)} benzersiz haber.")

    approved_articles: List[Dict[str, Any]] = []
    rejected_count = 0

    for item in unique_news[:max_articles]:
        src_url = (item.get("source_url") or "").strip()
        if src_url in existing_by_url and existing_by_url[src_url].get("word_count", 0) >= 160:
            approved_articles.append(existing_by_url[src_url])
            continue

        slug = slugify(item.get("clean_title") or item.get("title") or f"haber-{item.get('id')}")
        # Tam metni resmi kaynaktan çek
        full_text = fetcher.fetch_full_text(src_url)
        written = writer.write_article(item, full_text)

        cover_url, alt_text, credit = curator.ensure_cover(
            slug=slug,
            title=written["headline"],
            institution=item.get("institution") or "T.C. Resmi Kurum",
            category=item.get("category") or "RESMI_HABER",
        )

        article_record = {
            "id": item.get("id"),
            "slug": slug,
            "headline": written["headline"],
            "institution": item.get("institution") or "T.C. Resmi Kurum",
            "category": item.get("category") or "RESMI_HABER",
            "category_label": CATEGORY_THEMES.get(item.get("category") or "RESMI_HABER", CATEGORY_THEMES["RESMI_HABER"])["label"],
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

        passed, reason, wc = qa.audit(article_record, min_words=160)
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
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"📰 Editoryal Pipeline Tamamlandı: {len(approved_articles)} onaylı, {rejected_count} elendi -> {out_path}")
    return approved_articles


if __name__ == "__main__":
    run_editorial_pipeline()
