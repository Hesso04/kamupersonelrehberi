"""
Kamu Personel Rehberi — Çok Sayfalı Statik Site Üreticisi (SSG Builder)
=======================================================================
Mevcut Apple Glass / Fraunces tasarım dilini (%100 koruyarak) tüm site için
bağımsız, indekslenebilir, SEO & Google AdSense uyumlu statik HTML sayfaları
ve temiz sitemap.xml üretir.

Üretilen Sayfalar:
  - /hakkimizda/index.html
  - /iletisim/index.html
  - /gizlilik-politikasi/index.html
  - /kullanim-kosullari/index.html
  - /sss/index.html                  (FAQPage JSON-LD)
  - /araclar/kpss-puan-hesaplama/index.html
  - /rehber/index.html               + 12 bağımsız /rehber/<slug>/index.html (Article JSON-LD)
  - /haberler/index.html             + tüm onaylı /haber/<slug>/index.html  (NewsArticle JSON-LD)
  - /ilan/<slug>/index.html          + en güncel 60 aktif ilan sayfası       (JobPosting JSON-LD)
  - /sitemap.xml                     (Sadece gerçek, benzersiz statik URL'ler!)
"""

import html
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

from modules.editorial_pipeline import VisualCuratorAgent, slugify
from modules.guides_data import GUIDES

BASE_URL = "https://kamupersonelrehberiniz.me"
ADSENSE_CLIENT = "ca-pub-6698554585648483"


def esc(text: Any) -> str:
    return html.escape(str(text or ""), quote=True)


def render_page_shell(
    *,
    title: str,
    description: str,
    canonical_path: str,
    body_html: str,
    og_type: str = "website",
    og_image: str = "/assets/img/og-banner.png",
    json_ld: Optional[Dict[str, Any]] = None,
    active_nav: str = "",
    extra_script: str = "",
) -> str:
    canonical_url = f"{BASE_URL}{canonical_path}"
    full_og_image = og_image if og_image.startswith("http") else f"{BASE_URL}{og_image}"
    ld_script = ""
    if json_ld:
        ld_json = json.dumps(json_ld, ensure_ascii=False, indent=2)
        ld_script = f'<script type="application/ld+json">\n{ld_json}\n</script>'

    def nav_cls(key: str) -> str:
        return ' class="header-nav-link active"' if active_nav == key else ' class="header-nav-link"'

    return f"""<!DOCTYPE html>
<html lang="tr" prefix="og: https://ogp.me/ns#">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{esc(title)}</title>
  <link rel="canonical" href="{esc(canonical_url)}">
  <meta name="description" content="{esc(description)}">
  <meta name="robots" content="index, follow, max-image-preview:large, max-snippet:-1">
  <meta name="author" content="Kamu Personel Rehberi Editoryal Kurulu">
  <meta name="theme-color" content="#133B5C">

  <!-- Google AdSense -->
  <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={ADSENSE_CLIENT}" crossorigin="anonymous"></script>

  <!-- Open Graph & Twitter -->
  <meta property="og:type" content="{esc(og_type)}">
  <meta property="og:url" content="{esc(canonical_url)}">
  <meta property="og:site_name" content="Kamu Personel Rehberi">
  <meta property="og:locale" content="tr_TR">
  <meta property="og:title" content="{esc(title)}">
  <meta property="og:description" content="{esc(description)}">
  <meta property="og:image" content="{esc(full_og_image)}">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{esc(title)}">
  <meta name="twitter:description" content="{esc(description)}">
  <meta name="twitter:image" content="{esc(full_og_image)}">

  <link rel="icon" type="image/svg+xml" href="/assets/img/favicon.svg">
  <link rel="icon" type="image/x-icon" href="/favicon.ico">
  <link rel="apple-touch-icon" sizes="180x180" href="/assets/img/apple-touch-icon.png">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600;9..144,700&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="/assets/css/portal.css?v=8.0.0">
  <link rel="stylesheet" href="/assets/css/editorial.css?v=8.0.0">
  {ld_script}
  <script>
    (function(){{
      try {{
        if (localStorage.getItem('kpr_theme') === 'dark') {{
          document.documentElement.classList.add('dark');
        }}
      }} catch(e){{}}
    }})();
  </script>
</head>
<body>
  <div class="top-ticker-bar">
    <div class="portal-container top-ticker-inner">
      <span class="ticker-badge"><span class="ticker-dot"></span> GÜNCEL MEMUR ALIMLARI</span>
      <div class="ticker-viewport">
        <span class="ticker-item">T.C. Resmi Gazete, SBB Kamu İlan Portalı ve Kariyer Kapısı teyitli güncel alım duyuruları</span>
      </div>
      <span class="ticker-date">{datetime.now().strftime("%d.%m.%Y")}</span>
    </div>
  </div>

  <header class="site-header">
    <div class="portal-container">
      <div class="header-main-row">
        <a href="/" class="brand-lockup">
          <div class="brand-emblem" aria-hidden="true">KPR</div>
          <div class="brand-text-wrap">
            <span class="brand-name">Kamu Personel Rehberi</span>
            <span class="brand-tagline">Kamu İlanlarının Güncel Adresi | KPSS'siz Alım, Atama &amp; Rehber</span>
          </div>
        </a>
        <div class="header-right-tools">
          <a href="https://t.me/kamupersonelrehberi" target="_blank" rel="noopener noreferrer" class="header-tg-btn" title="Telegram İlan Kanalı">
            <span>Telegram</span>
          </a>
          <button class="icon-tool-btn" id="theme-toggle-btn" aria-label="Temayı Değiştir" title="Açık / Koyu Tema">
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/></svg>
          </button>
        </div>
      </div>
    </div>
    <nav class="header-nav-bar" aria-label="Ana Navigasyon">
      <div class="portal-container">
        <div class="header-nav-list">
          <a href="/"{nav_cls("home")}>Güncel İlanlar</a>
          <a href="/haberler/"{nav_cls("haberler")}>Kamu Haberleri</a>
          <a href="/rehber/"{nav_cls("rehber")}>İstihdam Rehberi</a>
          <a href="/araclar/kpss-puan-hesaplama/"{nav_cls("kpss")}>KPSS Hesapla</a>
          <a href="/sss/"{nav_cls("sss")}>S.S.S.</a>
          <a href="/hakkimizda/"{nav_cls("hakkimizda")}>Hakkımızda</a>
          <a href="/iletisim/"{nav_cls("iletisim")}>İletişim</a>
        </div>
      </div>
    </nav>
  </header>

  <main class="editorial-main">
    <div class="editorial-container">
      {body_html}
    </div>
  </main>

  <footer class="portal-footer">
    <div class="portal-container">
      <div class="portal-footer-grid">
        <div>
          <div class="footer-brand">Kamu Personel Rehberi</div>
          <p class="footer-desc">
            T.C. Resmi Gazete, SBB Kamu İlan Portalı, Kariyer Kapısı ve resmi bakanlık duyurularını tek merkezde sunan bağımsız kamu istihdam ve kariyer rehberlik portalı.
          </p>
        </div>
        <div>
          <div class="footer-col-h">İçerik &amp; Araçlar</div>
          <ul class="footer-col-list">
            <li><a href="/">Güncel Kamu İlanları</a></li>
            <li><a href="/haberler/">Resmi Kamu Haberleri</a></li>
            <li><a href="/rehber/">KPSS &amp; İstihdam Rehberi</a></li>
            <li><a href="/araclar/kpss-puan-hesaplama/">KPSS Puan Hesaplama</a></li>
            <li><a href="/sss/">Sıkça Sorulan Sorular</a></li>
          </ul>
        </div>
        <div>
          <div class="footer-col-h">Popüler Rehberler</div>
          <ul class="footer-col-list">
            <li><a href="/rehber/2026-kpss-4b-sozlesmeli-personel-alim-sartlari/">2026 KPSS 4/B Şartları</a></li>
            <li><a href="/rehber/kariyer-kapisi-basvuru-rehberi-adim-adim/">Kariyer Kapısı Rehberi</a></li>
            <li><a href="/rehber/kpss-sartsiz-kamu-personeli-ve-isci-alimi-nasil-yapilir/">KPSS Şartsız Alımlar</a></li>
            <li><a href="/rehber/guvenlik-sorusturmasi-ve-arsiv-arastirmasi-rehberi/">Güvenlik Soruşturması</a></li>
          </ul>
        </div>
        <div>
          <div class="footer-col-h">Kurumsal &amp; Yasal</div>
          <ul class="footer-col-list">
            <li><a href="/hakkimizda/">Hakkımızda &amp; Künye</a></li>
            <li><a href="/iletisim/">İletişim &amp; Düzeltme</a></li>
            <li><a href="/gizlilik-politikasi/">Gizlilik Politikası &amp; KVKK</a></li>
            <li><a href="/kullanim-kosullari/">Kullanım Koşulları</a></li>
            <li><a href="https://t.me/kamupersonelrehberi" target="_blank" rel="noopener noreferrer">Telegram Kanalımız</a></li>
          </ul>
        </div>
      </div>
      <div class="footer-bottom">
        <div>© 2026 Kamu Personel Rehberi (kamupersonelrehberiniz.me) — Tüm Hakları Saklıdır.</div>
        <div>Resmi Gazete &amp; SBB Kamu İlan Portalı teyitli bağımsız bilgilendirme platformu.</div>
      </div>
    </div>
  </footer>

  <script>
    (function(){{
      var btn = document.getElementById('theme-toggle-btn');
      if (btn) {{
        btn.addEventListener('click', function(){{
          var isDark = document.documentElement.classList.toggle('dark');
          try {{ localStorage.setItem('kpr_theme', isDark ? 'dark' : 'light'); }} catch(e){{}}
        }});
      }}
    }})();
  </script>
  {extra_script}
</body>
</html>
"""


def write_html(base_dir: Path, rel_path: str, content: str) -> None:
    target = base_dir / rel_path.lstrip("/")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


# =============================================================================
# 1. KURUMSAL SAYFALAR & SSS & KPSS HESAPLAMA ARACI
# =============================================================================
def build_static_core_pages(website_dir: Path) -> List[Tuple[str, str, str]]:
    """(url_path, lastmod, priority) listesi döner."""
    today = datetime.now().strftime("%Y-%m-%d")
    urls: List[Tuple[str, str, str]] = []

    # 1. HAKKIMIZDA
    about_body = """
    <nav class="breadcrumb-nav" aria-label="Konum"><a href="/">Ana Sayfa</a><span class="breadcrumb-sep">/</span><span>Hakkımızda</span></nav>
    <section class="page-hero-card apple-glass">
      <span class="page-kicker">KURUMSAL & EDİTORYAL İLKELER</span>
      <h1 class="page-h1">Hakkımızda — Kamu Personel Rehberi</h1>
      <p class="page-lead">Türkiye Cumhuriyeti kamu kurumlarının resmi personel alım duyurularını, mevzuat rehberlerini ve kariyer haberlerini doğru, şeffaf ve erişilebilir biçimde tek platformda sunuyoruz.</p>
    </section>
    <article class="article-body-card apple-glass prose">
      <h2>Misyonumuz</h2>
      <p><strong>Kamu Personel Rehberi (kamupersonelrehberiniz.me)</strong>, memur, 4/B sözleşmeli personel, kamu işçisi ve akademik kadro adaylarının resmi duyurulara dağınık kaynaklarda kaybolmadan, bilgi kirliliğine maruz kalmadan ulaşabilmesi amacıyla kurulmuş bağımsız bir dijital bilgilendirme ve rehberlik platformudur.</p>
      <h2>Veri Doğrulama ve Editoryal Metodolojimiz</h2>
      <p>Sitemizde yayımlanan her ilan ve haber metni, yalnızca resmi devlet kurumlarının kamuya açık kaynakları esas alınarak derlenir:</p>
      <ul>
        <li><strong>T.C. Resmi Gazete</strong> (resmigazete.gov.tr)</li>
        <li><strong>Cumhurbaşkanlığı Strateji ve Bütçe Başkanlığı Kamu İlan Portalı</strong> (kamuilan.sbb.gov.tr)</li>
        <li><strong>Cumhurbaşkanlığı Kariyer Kapısı</strong> (isealimkariyerkapisi.cbiko.gov.tr)</li>
        <li><strong>ÖSYM, MEB, İŞKUR, Basın İlan Kurumu ve T.C. Bakanlık Resmi Portalları</strong></li>
      </ul>
      <p>Otomatik tarama ve editoryal denetim katmanlarımız sayesinde mükerrer kayıtlar ayıklanır, son başvuru tarihi geçmiş ilanlar arşivlenir ve her duyurunun doğrudan resmi başvuru/PDF bağlantısı adaylara şeffaf biçimde sunulur.</p>
      <h2>Bağımsızlık İlkesi</h2>
      <p>Kamu Personel Rehberi herhangi bir resmi devlet kurumu, bakanlık veya siyasi kuruluşun resmi temsilcisi değildir; adaylardan başvuru ücreti, komisyon veya danışmanlık bedeli talep etmez. Tüm başvurular yalnızca ilgili resmi kurumların belirttiği e-Devlet, Kariyer Kapısı veya resmi başvuru kanalları üzerinden gerçekleştirilir.</p>
      <h2>Yayın Künyesi</h2>
      <ul>
        <li><strong>Platform Adı:</strong> Kamu Personel Rehberi</li>
        <li><strong>Alan Adı:</strong> https://kamupersonelrehberiniz.me</li>
        <li><strong>İçerik Kategorisi:</strong> Kamu Personeli Alım İlanları, KPSS ve Mevzuat Rehberliği</li>
        <li><strong>İletişim:</strong> <a href="/iletisim/">İletişim Sayfası</a> | Telegram: @kamupersonelrehberi</li>
      </ul>
    </article>
    """
    write_html(
        website_dir,
        "hakkimizda/index.html",
        render_page_shell(
            title="Hakkımızda & Yayın İlkeleri — Kamu Personel Rehberi",
            description="Kamu Personel Rehberi misyonu, resmi veri doğrulama metodolojisi, editoryal ilkeleri ve yayın künyesi.",
            canonical_path="/hakkimizda/",
            body_html=about_body,
            active_nav="hakkimizda",
        ),
    )
    urls.append(("/hakkimizda/", today, "0.7"))

    # 2. İLETİŞİM
    contact_body = """
    <nav class="breadcrumb-nav" aria-label="Konum"><a href="/">Ana Sayfa</a><span class="breadcrumb-sep">/</span><span>İletişim</span></nav>
    <section class="page-hero-card apple-glass">
      <span class="page-kicker">DESTEK & EDİTORYAL BİLDİRİM</span>
      <h1 class="page-h1">İletişim ve Düzeltme Talepleri</h1>
      <p class="page-lead">İlan düzeltme bildirimleri, resmi kurum duyuru paylaşımları, telif/tekzip talepleri ve önerileriniz için bize doğrudan ulaşabilirsiniz.</p>
    </section>
    <article class="article-body-card apple-glass prose">
      <h2>Resmi İletişim Kanallarımız</h2>
      <ul>
        <li><strong>E-posta:</strong> iletisim@kamupersonelrehberiniz.me</li>
        <li><strong>Resmi Telegram Kanalı:</strong> <a href="https://t.me/kamupersonelrehberi" target="_blank" rel="noopener noreferrer">t.me/kamupersonelrehberi</a></li>
        <li><strong>Instagram:</strong> <a href="https://instagram.com/kamupersonelrehberi" target="_blank" rel="noopener noreferrer">@kamupersonelrehberi</a></li>
      </ul>
      <h2>İlan Düzeltme ve Tekzip Prosedürü</h2>
      <p>Yayımlanan herhangi bir kamu ilanında kontenjan, son başvuru tarihi, PDF bağlantısı veya kurum bilgisinde eksiklik/güncelleme fark ederseniz ilgili sayfa adresini ve resmi kaynak bağlantısını e-posta ile iletmeniz yeterlidir. Editoryal ekibimiz gelen bildirimleri en geç <strong>24 saat içinde</strong> inceleyerek günceller.</p>
      <h2>Önemli Bilgilendirme</h2>
      <p>Platformumuz üzerinden <strong>iş başvurusu veya özgeçmiş (CV) kabul edilmemektedir</strong>. Başvurularınızı her ilanın detay sayfasında yer alan resmi kurum bağlantısı veya Kariyer Kapısı üzerinden gerçekleştiriniz.</p>
    </article>
    """
    write_html(
        website_dir,
        "iletisim/index.html",
        render_page_shell(
            title="İletişim — Kamu Personel Rehberi",
            description="Kamu Personel Rehberi iletişim bilgileri, ilan düzeltme talepleri, resmi kanallar ve editoryal destek.",
            canonical_path="/iletisim/",
            body_html=contact_body,
            active_nav="iletisim",
        ),
    )
    urls.append(("/iletisim/", today, "0.6"))

    # 3. GİZLİLİK POLİTİKASI & KVKK
    privacy_body = """
    <nav class="breadcrumb-nav" aria-label="Konum"><a href="/">Ana Sayfa</a><span class="breadcrumb-sep">/</span><span>Gizlilik Politikası</span></nav>
    <section class="page-hero-card apple-glass">
      <span class="page-kicker">KVKK & ÇEREZ POLİTİKASI</span>
      <h1 class="page-h1">Gizlilik Politikası ve Kişisel Verilerin Korunması</h1>
      <p class="page-lead">Son Güncelleme: 20 Kasım 2026. Ziyaretçilerimizin gizliliğine saygı duyuyor, 6698 sayılı KVKK ve Google yayıncı politikalarına tam uyum sağlıyoruz.</p>
    </section>
    <article class="article-body-card apple-glass prose">
      <h2>1. Toplanan Veriler ve Kullanım Amacı</h2>
      <p><strong>kamupersonelrehberiniz.me</strong> ziyaretçilerinden üyelik, T.C. kimlik numarası, telefon veya ödeme bilgisi talep etmez. Sitemizi ziyaret ettiğinizde yalnızca hizmet kalitesini artırmak ve site güvenliğini sağlamak amacıyla anonim teknik veriler (tarayıcı türü, cihaz ekran boyutu, ziyaret edilen sayfa, tema tercihi) işlenebilir.</p>
      <h2>2. Çerezler (Cookies) ve Yerel Depolama</h2>
      <p>Sitemizde açık/koyu tema tercihinizi ve çerez onay durumunuzu hatırlamak için tarayıcı yerel depolaması (localStorage) kullanılmaktadır. Tarayıcı ayarlarınızdan çerezleri dilediğiniz zaman silebilir veya engelleyebilirsiniz.</p>
      <h2>3. Üçüncü Taraf Reklamları ve Google AdSense</h2>
      <p>Sitemizde reklam hizmetleri sunmak amacıyla <strong>Google AdSense</strong> kullanılabilir. Google dahil üçüncü taraf satıcılar, kullanıcının bu web sitesine veya diğer web sitelerine yaptığı önceki ziyaretlere dayalı olarak reklam yayınlamak için çerezler (DART çerezi dahil) kullanır.</p>
      <p>Kullanıcılar, <a href="https://adssettings.google.com/" target="_blank" rel="noopener noreferrer">Google Reklam Ayarları</a> sayfasını ziyaret ederek kişiselleştirilmiş reklamcılığı devre dışı bırakabilirler.</p>
      <h2>4. Dış Bağlantılar</h2>
      <p>İlan ve haber sayfalarımızda T.C. Resmi Gazete, Kariyer Kapısı, İŞKUR ve ilgili bakanlıkların resmi internet sitelerine yönlendiren dış bağlantılar yer almaktadır. Bu dış sitelerin gizlilik uygulamalarından ilgili kurumlar sorumludur.</p>
      <h2>5. KVKK Kapsamındaki Haklarınız</h2>
      <p>6698 sayılı Kişisel Verilerin Korunması Kanunu’nun 11. maddesi kapsamındaki tüm bilgi ve silme talepleriniz için <a href="/iletisim/">İletişim</a> sayfamız üzerinden bize ulaşabilirsiniz.</p>
    </article>
    """
    write_html(
        website_dir,
        "gizlilik-politikasi/index.html",
        render_page_shell(
            title="Gizlilik Politikası, Çerezler ve KVKK — Kamu Personel Rehberi",
            description="Kamu Personel Rehberi gizlilik politikası, 6698 sayılı KVKK aydınlatma metni, çerez kullanımı ve Google AdSense reklam bilgilendirmesi.",
            canonical_path="/gizlilik-politikasi/",
            body_html=privacy_body,
        ),
    )
    urls.append(("/gizlilik-politikasi/", today, "0.5"))

    # 4. KULLANIM KOŞULLARI & YASAL UYARI
    terms_body = """
    <nav class="breadcrumb-nav" aria-label="Konum"><a href="/">Ana Sayfa</a><span class="breadcrumb-sep">/</span><span>Kullanım Koşulları</span></nav>
    <section class="page-hero-card apple-glass">
      <span class="page-kicker">YASAL UYARI & SORUMLULUK REDDİ</span>
      <h1 class="page-h1">Kullanım Koşulları ve Yasal Uyarı</h1>
      <p class="page-lead">Kamu Personel Rehberi platformunun kullanım şartları, resmi kaynak teyit sorumluluğu ve fikri mülkiyet hakları.</p>
    </section>
    <article class="article-body-card apple-glass prose">
      <h2>1. Bilgilendirme Amaçlı Yayın</h2>
      <p><strong>kamupersonelrehberiniz.me</strong> üzerinde yayımlanan tüm kamu alım ilanları, haberler, rehber makaleleri ve KPSS hesaplama araçları yalnızca genel bilgilendirme amacıyla hazırlanmıştır. İlgili kamu kurumları tarafından yapılabilecek ilan iptali, tarih uzatımı veya nitelik değişikliklerinde <strong>T.C. Resmi Gazete</strong> ve ilgili kurumun resmi duyuru metni esastır.</p>
      <h2>2. Sorumluluk Reddi</h2>
      <p>Editoryal ekibimiz verilerin doğruluğu ve güncelliği için azami özen göstermekle birlikte, teknik aksaklıklar veya kurum kaynaklı son dakika değişikliklerinden doğabilecek doğrudan ya da dolaylı hak kayıplarından platform sorumlu tutulamaz. Başvuru öncesi resmi PDF kılavuzunun incelenmesi adayın sorumluluğundadır.</p>
      <h2>3. Fikri Mülkiyet ve Telif Hakları</h2>
      <p>Sitemizde yayımlanan özgün rehber makaleleri, editoryal değerlendirmeler, tasarım bileşenleri ve hesaplama araçları Kamu Personel Rehberi’ne aittir. Aktif kaynak linki (dofollow/nofollow belirtilerek) verilmeden izinsiz kopyalanması yasaktır.</p>
    </article>
    """
    write_html(
        website_dir,
        "kullanim-kosullari/index.html",
        render_page_shell(
            title="Kullanım Koşulları ve Yasal Uyarı — Kamu Personel Rehberi",
            description="Kamu Personel Rehberi kullanım şartları, resmi kaynak sorumluluk reddi ve telif hakları bilgilendirmesi.",
            canonical_path="/kullanim-kosullari/",
            body_html=terms_body,
        ),
    )
    urls.append(("/kullanim-kosullari/", today, "0.5"))

    # 5. SIKÇA SORULAN SORULAR (FAQPage JSON-LD)
    faq_items = [
        ("Kamu Personel Rehberi resmi bir devlet kurumu mudur?", "Hayır. Kamu Personel Rehberi, T.C. Resmi Gazete, SBB Kamu İlan Portalı, Kariyer Kapısı ve resmi bakanlık portallarında yayımlanan duyuruları tek çatı altında toplayan bağımsız bir bilgilendirme ve kariyer rehberliği platformudur."),
        ("İlanlara bu site üzerinden mi başvuru yapılıyor?", "Hayır. Sitemiz üzerinden başvuru veya kişisel evrak alınmaz. Her ilanın sayfasında yer alan 'Resmi Başvuru / Kılavuz' bağlantısı üzerinden doğrudan ilgili kamu kurumunun veya Kariyer Kapısı'nın resmi ekranına yönlendirilirsiniz."),
        ("4/B sözleşmeli personel kaç yıl sonra kadroya geçer?", "7433 sayılı Kanun ile kalıcı hale getirilen 3+1 modeli uyarınca, 4/B sözleşmeli personel aynı kurumda 3 yıl fiilen görev yaptıktan sonra talebi halinde 657 4/A memur kadrosuna atanır; ardından 1 yıl daha aynı görev yerinde çalışır."),
        ("4/B sözleşmeli personelin 1 yıl bekleme cezası nedir?", "Kendi isteğiyle 4/B sözleşmesini fesheden personel, unvan değişikliği veya mevzuattaki özel mazeret istisnaları hariç olmak üzere fesih tarihinden itibaren 1 yıl geçmeden başka bir 4/B pozisyonuna atanamaz."),
        ("KPSS şartsız devlet memuru veya kamu işçisi olunabilir mi?", "Devlet memurluğu (657 4/A) alımlarında kural olarak KPSS zorunludur. Ancak İŞKUR üzerinden yapılan 4857 sayılı İş Kanunu kapsamındaki daimi/sürekli kamu işçisi alımlarında, belediye iştirak şirketlerinde ve bazı akademik/bilişim kadrolarında KPSS şartı aranmaz."),
        ("KPSS puanı kaç yıl geçerlidir?", "KPSS B Grubu (P3, P93, P94) puanları sonuçların açıklandığı tarihten itibaren 2 yıl geçerlidir. Öğretmenlik (KPSS P10/P121) puanları 1 yıl geçerlidir."),
        ("Kariyer Kapısı başvurusu nasıl doğrulanır?", "isealimkariyerkapisi.cbiko.gov.tr adresine e-Devlet ile giriş yaptıktan sonra 'Başvurularım' sekmesinde ilgili ilan için 'Başvuru Alındı' ibaresini görmeniz ve alındı belgesini indirmeniz yeterlidir."),
        ("Güvenlik soruşturması ve arşiv araştırması ne kadar sürer?", "7315 sayılı Kanun gereğince arşiv araştırması en geç 30 iş günü, güvenlik soruşturması ise en geç 60 iş günü içinde sonuçlandırılır. Toplu alımlarda komisyon süreciyle birlikte 1,5-3 ay sürebilir."),
        ("Aynı anda birden fazla kamu kurumunun ilanına başvurabilir miyim?", "Evet, farklı kamu kurumlarının ilanlarına aynı dönemde başvuru yapabilirsiniz. Ancak tek bir kurumun aynı ilan metnindeki birden fazla pozisyonuna (kılavuzda aksi yazmadıkça) sadece tek tercih yapılabilir."),
        ("Zabıta ve itfaiye eri alımlarında yaş ve boy şartı nedir?", "Sınav tarihinde 30 yaşını doldurmamış olmak; erkeklerde en az 1.67 m, kadınlarda en az 1.60 m boyunda olmak ve boy-kilo farkının (+,-) 10 kg aralığında bulunması şarttır."),
    ]
    faq_html_items = "\n".join(
        f'<details class="faq-item"><summary>{esc(q)}</summary><div class="faq-answer">{esc(a)}</div></details>'
        for q, a in faq_items
    )
    faq_body = f"""
    <nav class="breadcrumb-nav" aria-label="Konum"><a href="/">Ana Sayfa</a><span class="breadcrumb-sep">/</span><span>Sıkça Sorulan Sorular</span></nav>
    <section class="page-hero-card apple-glass">
      <span class="page-kicker">MEVZUAT & BAŞVURU KILAVUZU</span>
      <h1 class="page-h1">Sıkça Sorulan Sorular (KPSS & Kamu Alımları)</h1>
      <p class="page-lead">Kamu personeli alım süreçleri, 4/B sözleşmeli statüsü, Kariyer Kapısı, İŞKUR işçi kuraları ve güvenlik soruşturması hakkında en çok merak edilen soruların teyitli yanıtları.</p>
    </section>
    <section class="article-body-card apple-glass">
      {faq_html_items}
      <div class="editorial-actions">
        <a href="/rehber/" class="btn-editorial-primary">Tüm İstihdam Rehberlerini Oku</a>
        <a href="/araclar/kpss-puan-hesaplama/" class="btn-editorial-secondary">KPSS Puan Hesaplama Aracı</a>
      </div>
    </section>
    """
    faq_ld = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": q,
                "acceptedAnswer": {"@type": "Answer", "text": a},
            }
            for q, a in faq_items
        ],
    }
    write_html(
        website_dir,
        "sss/index.html",
        render_page_shell(
            title="Sıkça Sorulan Sorular — KPSS ve Kamu Alımları | Kamu Personel Rehberi",
            description="KPSS geçerlilik süresi, 4/B kadroya geçiş, 1 yıl bekleme kuralı, Kariyer Kapısı ve güvenlik soruşturması hakkında sıkça sorulan sorular.",
            canonical_path="/sss/",
            body_html=faq_body,
            json_ld=faq_ld,
            active_nav="sss",
        ),
    )
    urls.append(("/sss/", today, "0.8"))

    # 6. İNTERAKTİF ARAÇ: KPSS PUAN & NET HESAPLAMA ARACI
    kpss_body = """
    <nav class="breadcrumb-nav" aria-label="Konum"><a href="/">Ana Sayfa</a><span class="breadcrumb-sep">/</span><a href="/rehber/">Rehber</a><span class="breadcrumb-sep">/</span><span>KPSS Puan Hesaplama</span></nav>
    <section class="page-hero-card apple-glass">
      <span class="page-kicker">ÜCRETSİZ İNTERAKTİF ARAÇ</span>
      <h1 class="page-h1">2026 KPSS Puan ve Net Hesaplama Robotu (P3, P93, P94)</h1>
      <p class="page-lead">Genel Yetenek (60 soru) ve Genel Kültür (60 soru) doğru-yanlış sayılarınızı girerek 4 yanlışın 1 doğruyu götürdüğü sistemde tahmini KPSS Lisans (P3), Ön Lisans (P93) ve Ortaöğretim (P94) puanınızı anında hesaplayın.</p>
    </section>

    <section class="article-body-card apple-glass" style="margin-bottom:28px;">
      <div class="calc-grid">
        <div>
          <h2 style="font-family:var(--font-editorial);font-size:1.3rem;margin-bottom:16px;">Sınav Bilgilerinizi Girin</h2>
          <div style="margin-bottom:16px;">
            <label for="kpss-level" style="display:block;font-size:0.85rem;font-weight:600;margin-bottom:6px;">Sınav Düzeyi</label>
            <select id="kpss-level" class="calc-input">
              <option value="p3">KPSS Lisans (B Grubu — P3)</option>
              <option value="p93">KPSS Ön Lisans (P93)</option>
              <option value="p94">KPSS Ortaöğretim / Lise (P94)</option>
            </select>
          </div>
          <div class="calc-field-row">
            <label style="font-weight:600;font-size:0.92rem;">Genel Yetenek (60 Soru)</label>
            <input type="number" id="gy-d" class="calc-input" min="0" max="60" value="42" placeholder="Doğru">
            <input type="number" id="gy-y" class="calc-input" min="0" max="60" value="8" placeholder="Yanlış">
          </div>
          <div class="calc-field-row">
            <label style="font-weight:600;font-size:0.92rem;">Genel Kültür (60 Soru)</label>
            <input type="number" id="gk-d" class="calc-input" min="0" max="60" value="38" placeholder="Doğru">
            <input type="number" id="gk-y" class="calc-input" min="0" max="60" value="10" placeholder="Yanlış">
          </div>
          <p id="kpss-warn" style="color:var(--warning-text);font-size:0.84rem;min-height:20px;margin-top:6px;"></p>
        </div>
        <div class="calc-result-box">
          <div style="font-size:0.78rem;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:var(--text-secondary);" id="kpss-type-label">TAHMİNİ KPSS P3 PUANI</div>
          <div class="calc-score-big" id="kpss-score-out">81.45</div>
          <div style="font-size:0.88rem;color:var(--text-secondary);margin-bottom:14px;">
            GY Net: <strong id="gy-net-out">40.00</strong> &nbsp;|&nbsp; GK Net: <strong id="gk-net-out">35.50</strong><br>
            Toplam Net: <strong id="tot-net-out">75.50 / 120</strong>
          </div>
          <div style="font-size:0.78rem;color:var(--text-tertiary);">Son 3 sınav döneminin ÖSYM standart sapma ortalamalarına göre hesaplanan tahmini puandır.</div>
        </div>
      </div>
    </section>

    <article class="article-body-card apple-glass prose">
      <h2>KPSS Puanı Nasıl Hesaplanır?</h2>
      <p>ÖSYM tarafından uygulanan KPSS Genel Yetenek ve Genel Kültür oturumlarında her testte <strong>60’ar soru</strong> (toplam 120 soru) yer alır. Her iki test için ayrı ayrı <strong>4 yanlış cevap 1 doğru cevabı</strong> götürerek ham net sayısı bulunur.</p>
      <p>Ardından sınava giren tüm adayların ortalaması ve standart sapması kullanılarak <strong>Standart Puan (SP)</strong> elde edilir. KPSS P3 (Lisans), P93 (Ön Lisans) ve P94 (Ortaöğretim) puan türlerinde Genel Yetenek testinin ağırlığı <strong>%50</strong>, Genel Kültür testinin ağırlığı ise <strong>%50</strong> olarak uygulanır.</p>
      <h2>Hangi Puanla Hangi İlanlara Başvurabilirsiniz?</h2>
      <ul>
        <li><strong>60 – 70 Puan Aralığı:</strong> Belediye zabıta/itfaiye alımları, bazı destek personeli ve mülakatlı kurum sınavları.</li>
        <li><strong>70 – 80 Puan Aralığı:</strong> Adalet Bakanlığı zabıt katipliği / İKM, üniversite 4/B sağlık ve teknik kadrolar, bakanlık sözleşmeli alımları.</li>
        <li><strong>80 – 90+ Puan Aralığı:</strong> Merkezi atama (ÖSYM KPSS tercihleri), VHKİ, mühendislik ve yüksek rekabetli bakanlık büro kadroları.</li>
      </ul>
      <p>Puanınızla başvurabileceğiniz güncel ilanları görmek için <a href="/">Güncel Kamu İlanları Listesi</a>’ni ziyaret edebilir veya <a href="/rehber/kpss-puan-turleri-p3-p93-p94-hangi-kadrolar/">KPSS Puan Türleri Rehberi</a>’ni inceleyebilirsiniz.</p>
    </article>
    """
    kpss_script = """
    <script>
      (function(){
        var coeffs = {
          p3:  { label: 'TAHMİNİ KPSS P3 (LİSANS) PUANI',      base: 48.2, gy: 0.455, gk: 0.415 },
          p93: { label: 'TAHMİNİ KPSS P93 (ÖN LİSANS) PUANI',  base: 50.1, gy: 0.435, gk: 0.405 },
          p94: { label: 'TAHMİNİ KPSS P94 (ORTAÖĞRETİM) PUANI',base: 51.4, gy: 0.425, gk: 0.395 }
        };
        function calc(){
          var lvl = document.getElementById('kpss-level').value;
          var gyd = Math.max(0, Math.min(60, parseFloat(document.getElementById('gy-d').value)||0));
          var gyy = Math.max(0, Math.min(60, parseFloat(document.getElementById('gy-y').value)||0));
          var gkd = Math.max(0, Math.min(60, parseFloat(document.getElementById('gk-d').value)||0));
          var gky = Math.max(0, Math.min(60, parseFloat(document.getElementById('gk-y').value)||0));
          var warn = '';
          if (gyd + gyy > 60) { warn = 'Genel Yetenek doğru + yanlış toplamı 60’ı geçemez.'; gyy = Math.max(0, 60 - gyd); }
          if (gkd + gky > 60) { warn = 'Genel Kültür doğru + yanlış toplamı 60’ı geçemez.'; gky = Math.max(0, 60 - gkd); }
          document.getElementById('kpss-warn').textContent = warn;
          var gyNet = gyd - (gyy * 0.25);
          var gkNet = gkd - (gky * 0.25);
          var c = coeffs[lvl] || coeffs.p3;
          var score = Math.max(40, Math.min(100, c.base + (gyNet * c.gy) + (gkNet * c.gk)));
          document.getElementById('kpss-type-label').textContent = c.label;
          document.getElementById('kpss-score-out').textContent = score.toFixed(2);
          document.getElementById('gy-net-out').textContent = gyNet.toFixed(2);
          document.getElementById('gk-net-out').textContent = gkNet.toFixed(2);
          document.getElementById('tot-net-out').textContent = (gyNet + gkNet).toFixed(2) + ' / 120';
        }
        ['kpss-level','gy-d','gy-y','gk-d','gk-y'].forEach(function(id){
          var el = document.getElementById(id);
          if (el) el.addEventListener('input', calc);
        });
        calc();
      })();
    </script>
    """
    write_html(
        website_dir,
        "araclar/kpss-puan-hesaplama/index.html",
        render_page_shell(
            title="2026 KPSS Puan ve Net Hesaplama Robotu (P3, P93, P94) — Kamu Personel Rehberi",
            description="Genel Yetenek ve Genel Kültür doğru-yanlış sayılarınızı girerek 2026 KPSS Lisans P3, Ön Lisans P93 ve Ortaöğretim P94 puanınızı ücretsiz hesaplayın.",
            canonical_path="/araclar/kpss-puan-hesaplama/",
            body_html=kpss_body,
            active_nav="kpss",
            extra_script=kpss_script,
        ),
    )
    urls.append(("/araclar/kpss-puan-hesaplama/", today, "0.9"))

    return urls


# =============================================================================
# 2. REHBER MAKALELERİ (/rehber/ + /rehber/<slug>/)
# =============================================================================
def build_guides_pages(website_dir: Path, curator: VisualCuratorAgent) -> List[Tuple[str, str, str]]:
    urls: List[Tuple[str, str, str]] = []
    today = datetime.now().strftime("%Y-%m-%d")

    cards_html = []
    for g in GUIDES:
        cover_url, alt_text, credit = curator.ensure_cover(
            slug=f"rehber-{g['slug']}",
            title=g["title"],
            institution="Kamu Personel Rehberi Editoryal Kurulu",
            category=g.get("category", "REHBER"),
        )
        g["cover_image"] = cover_url
        g["cover_alt"] = alt_text
        g["cover_credit"] = credit

        cards_html.append(f"""
        <article class="editorial-card apple-glass">
          <a href="/rehber/{esc(g['slug'])}/">
            <img src="{esc(cover_url)}" alt="{esc(alt_text)}" class="editorial-card-thumb" loading="lazy" width="1200" height="675">
          </a>
          <div class="editorial-card-body">
            <span class="editorial-card-cat">{esc(g['category_label'])}</span>
            <h2 class="editorial-card-title"><a href="/rehber/{esc(g['slug'])}/">{esc(g['title'])}</a></h2>
            <p class="editorial-card-excerpt">{esc(g['excerpt'])}</p>
            <div class="editorial-card-footer">
              <span>{esc(g['date_formatted'])}</span>
              <a href="/rehber/{esc(g['slug'])}/" class="editorial-card-cta">Rehberi Oku →</a>
            </div>
          </div>
        </article>
        """)

        # İlişkili diğer rehberler
        related = [x for x in GUIDES if x["slug"] != g["slug"]][:5]
        rel_list = "".join(
            f'<li><a href="/rehber/{esc(r["slug"])}/">{esc(r["title"])}<small>{esc(r["category_label"])}</small></a></li>'
            for r in related
        )

        detail_body = f"""
        <nav class="breadcrumb-nav" aria-label="Konum">
          <a href="/">Ana Sayfa</a><span class="breadcrumb-sep">/</span>
          <a href="/rehber/">İstihdam Rehberi</a><span class="breadcrumb-sep">/</span>
          <span>{esc(g['category_label'])}</span>
        </nav>

        <div class="editorial-article-layout">
          <div>
            <section class="page-hero-card apple-glass">
              <span class="page-kicker">{esc(g['category_label'])}</span>
              <h1 class="page-h1">{esc(g['title'])}</h1>
              <p class="page-lead">{esc(g['excerpt'])}</p>
              <div class="article-meta-bar">
                <span class="article-meta-pill">Editör: <strong>Kamu Personel Rehberi Kurulu</strong></span>
                <span class="article-meta-pill">Güncelleme: <strong>{esc(g['date_formatted'])}</strong></span>
                <span class="article-meta-pill">Mevzuat Teyitli</span>
              </div>
            </section>

            <figure class="article-cover-wrap">
              <img src="{esc(cover_url)}" alt="{esc(alt_text)}" class="article-cover-img" width="1200" height="675">
              <figcaption class="article-cover-caption">{esc(credit)}</figcaption>
            </figure>

            <article class="article-body-card apple-glass prose">
              {g['body_html']}
              <div class="editorial-actions">
                <a href="/" class="btn-editorial-primary">Güncel Kamu İlanlarını İncele</a>
                <a href="/araclar/kpss-puan-hesaplama/" class="btn-editorial-secondary">KPSS Puanını Hesapla</a>
              </div>
            </article>
          </div>

          <aside class="editorial-sidebar">
            <div class="sidebar-card apple-glass">
              <h3 class="sidebar-card-title">Diğer Kamu Rehberleri</h3>
              <ul class="sidebar-list">{rel_list}</ul>
            </div>
            <div class="sidebar-card apple-glass">
              <h3 class="sidebar-card-title">Hızlı Araçlar</h3>
              <ul class="sidebar-list">
                <li><a href="/araclar/kpss-puan-hesaplama/">2026 KPSS Puan & Net Hesaplama<small>P3, P93, P94 canlı hesaplayıcı</small></a></li>
                <li><a href="/haberler/">Son Resmi Kamu Haberleri<small>Teyitli bakanlık & ÖSYM duyuruları</small></a></li>
                <li><a href="/sss/">Sıkça Sorulan Sorular<small>Mevzuat ve başvuru yanıtları</small></a></li>
              </ul>
            </div>
          </aside>
        </div>
        """

        article_ld = {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": g["title"],
            "description": g["meta_description"],
            "image": f"{BASE_URL}{cover_url}",
            "datePublished": g["date"],
            "dateModified": today,
            "author": {"@type": "Organization", "name": "Kamu Personel Rehberi"},
            "publisher": {
                "@type": "Organization",
                "name": "Kamu Personel Rehberi",
                "logo": {"@type": "ImageObject", "url": f"{BASE_URL}/assets/img/logo.png"},
            },
            "mainEntityOfPage": f"{BASE_URL}/rehber/{g['slug']}/",
        }
        write_html(
            website_dir,
            f"rehber/{g['slug']}/index.html",
            render_page_shell(
                title=f"{g['title']} — Kamu Personel Rehberi",
                description=g["meta_description"],
                canonical_path=f"/rehber/{g['slug']}/",
                body_html=detail_body,
                og_type="article",
                og_image=cover_url,
                json_ld=article_ld,
                active_nav="rehber",
            ),
        )
        urls.append((f"/rehber/{g['slug']}/", g["date"], "0.85"))

    # Rehber Dizin Sayfası
    index_body = f"""
    <nav class="breadcrumb-nav" aria-label="Konum"><a href="/">Ana Sayfa</a><span class="breadcrumb-sep">/</span><span>İstihdam Rehberi</span></nav>
    <section class="page-hero-card apple-glass">
      <span class="page-kicker">MEVZUAT & KARİYER KÜTÜPHANESİ</span>
      <h1 class="page-h1">Kamu Personeli ve KPSS İstihdam Rehberi</h1>
      <p class="page-lead">657 sayılı Kanun, 4/B sözleşmeli personel şartları, Kariyer Kapısı, İŞKUR işçi alımları, mülakat hazırlığı ve güvenlik soruşturması üzerine uzman rehber makaleleri.</p>
    </section>
    <section class="editorial-grid">
      {"".join(cards_html)}
    </section>
    """
    write_html(
        website_dir,
        "rehber/index.html",
        render_page_shell(
            title="Kamu İstihdam ve KPSS Rehberi — Kamu Personel Rehberi",
            description="2026 KPSS şartları, 4/B sözleşmeli personel, Kariyer Kapısı başvurusu, güvenlik soruşturması ve devlet memurluğu rehber makaleleri.",
            canonical_path="/rehber/",
            body_html=index_body,
            active_nav="rehber",
        ),
    )
    urls.append(("/rehber/", today, "0.9"))
    return urls


# =============================================================================
# 3. OTONOM HABER MERKEZİ SAYFALARI (/haberler/ + /haber/<slug>/)
# =============================================================================
def build_news_pages(website_dir: Path) -> List[Tuple[str, str, str]]:
    editorial_path = website_dir / "data" / "editorial_news.json"
    today = datetime.now().strftime("%Y-%m-%d")
    urls: List[Tuple[str, str, str]] = []

    articles: List[Dict[str, Any]] = []
    if editorial_path.exists():
        data = json.loads(editorial_path.read_text(encoding="utf-8"))
        articles = data.get("articles", [])

    cards_html = []
    for a in articles:
        slug = a["slug"]
        cover = a.get("cover_image") or "/assets/img/og-banner.png"
        alt = a.get("cover_alt") or a["headline"]
        pub_iso = (a.get("publish_date") or today)[:10]

        cards_html.append(f"""
        <article class="editorial-card apple-glass">
          <a href="/haber/{esc(slug)}/">
            <img src="{esc(cover)}" alt="{esc(alt)}" class="editorial-card-thumb" loading="lazy" width="1200" height="675">
          </a>
          <div class="editorial-card-body">
            <span class="editorial-card-cat">{esc(a.get('category_label', 'Resmi Duyuru'))} • {esc(a.get('institution', ''))}</span>
            <h2 class="editorial-card-title"><a href="/haber/{esc(slug)}/">{esc(a['headline'])}</a></h2>
            <p class="editorial-card-excerpt">{esc(a.get('excerpt', ''))}</p>
            <div class="editorial-card-footer">
              <span>{esc(a.get('publish_date_formatted', pub_iso))}</span>
              <a href="/haber/{esc(slug)}/" class="editorial-card-cta">Haberi Oku →</a>
            </div>
          </div>
        </article>
        """)

        related_news = [x for x in articles if x["slug"] != slug][:5]
        rel_list = "".join(
            f'<li><a href="/haber/{esc(r["slug"])}/">{esc(r["headline"])}<small>{esc(r.get("institution",""))} • {esc(r.get("publish_date_formatted",""))}</small></a></li>'
            for r in related_news
        )

        src_btn = ""
        if a.get("source_url"):
            src_btn = f'<a href="{esc(a["source_url"])}" target="_blank" rel="noopener noreferrer nofollow" class="btn-editorial-primary">Resmi Kaynağa Git ({esc(a.get("source_name","Kurum"))}) ↗</a>'

        detail_body = f"""
        <nav class="breadcrumb-nav" aria-label="Konum">
          <a href="/">Ana Sayfa</a><span class="breadcrumb-sep">/</span>
          <a href="/haberler/">Kamu Haberleri</a><span class="breadcrumb-sep">/</span>
          <span>{esc(a.get('category_label','Resmi Duyuru'))}</span>
        </nav>

        <div class="editorial-article-layout">
          <div>
            <section class="page-hero-card apple-glass">
              <span class="page-kicker">{esc(a.get('category_label','Resmi Duyuru'))}</span>
              <h1 class="page-h1">{esc(a['headline'])}</h1>
              <div class="article-meta-bar">
                <span class="article-meta-pill">Kurum: <strong>{esc(a.get('institution',''))}</strong></span>
                <span class="article-meta-pill">Tarih: <strong>{esc(a.get('publish_date_formatted', pub_iso))}</strong></span>
                <span class="article-meta-pill">Okuma: <strong>~{a.get('reading_time_min', 2)} dk</strong></span>
              </div>
            </section>

            <figure class="article-cover-wrap">
              <img src="{esc(cover)}" alt="{esc(alt)}" class="article-cover-img" width="1200" height="675">
              <figcaption class="article-cover-caption">{esc(a.get('cover_credit','Kamu Personel Rehberi'))}</figcaption>
            </figure>

            <article class="article-body-card apple-glass prose">
              {a['body_html']}
              <div class="editorial-actions">
                {src_btn}
                <a href="/haberler/" class="btn-editorial-secondary">Tüm Kamu Haberleri</a>
              </div>
            </article>
          </div>

          <aside class="editorial-sidebar">
            <div class="sidebar-card apple-glass">
              <h3 class="sidebar-card-title">Son Resmi Duyurular</h3>
              <ul class="sidebar-list">{rel_list}</ul>
            </div>
            <div class="sidebar-card apple-glass">
              <h3 class="sidebar-card-title">Öne Çıkan Rehberler</h3>
              <ul class="sidebar-list">
                <li><a href="/rehber/2026-kpss-4b-sozlesmeli-personel-alim-sartlari/">2026 KPSS 4/B Şartları<small>Sözleşmeli İstihdam</small></a></li>
                <li><a href="/rehber/kariyer-kapisi-basvuru-rehberi-adim-adim/">Kariyer Kapısı Başvuru Rehberi<small>Adım Adım Kılavuz</small></a></li>
                <li><a href="/araclar/kpss-puan-hesaplama/">KPSS Puan Hesaplama<small>Ücretsiz Robot</small></a></li>
              </ul>
            </div>
          </aside>
        </div>
        """

        news_ld = {
            "@context": "https://schema.org",
            "@type": "NewsArticle",
            "headline": a["headline"],
            "description": a.get("meta_description") or a.get("excerpt") or a["headline"],
            "image": [f"{BASE_URL}{cover}"],
            "datePublished": a.get("publish_date") or today,
            "dateModified": a.get("publish_date") or today,
            "author": {"@type": "Organization", "name": "Kamu Personel Rehberi"},
            "publisher": {
                "@type": "Organization",
                "name": "Kamu Personel Rehberi",
                "logo": {"@type": "ImageObject", "url": f"{BASE_URL}/assets/img/logo.png"},
            },
            "mainEntityOfPage": f"{BASE_URL}/haber/{slug}/",
        }
        write_html(
            website_dir,
            f"haber/{slug}/index.html",
            render_page_shell(
                title=f"{a['headline']} — Kamu Personel Rehberi",
                description=a.get("meta_description") or a.get("excerpt") or a["headline"],
                canonical_path=f"/haber/{slug}/",
                body_html=detail_body,
                og_type="article",
                og_image=cover,
                json_ld=news_ld,
                active_nav="haberler",
            ),
        )
        urls.append((f"/haber/{slug}/", pub_iso, "0.8"))

    # Haberler Dizin Sayfası
    news_index_body = f"""
    <nav class="breadcrumb-nav" aria-label="Konum"><a href="/">Ana Sayfa</a><span class="breadcrumb-sep">/</span><span>Kamu Haberleri</span></nav>
    <section class="page-hero-card apple-glass">
      <span class="page-kicker">TEYİTLİ RESMİ BÜLTENLER</span>
      <h1 class="page-h1">Güncel Kamu Haberleri ve Resmi Duyurular</h1>
      <p class="page-lead">ÖSYM, Millî Eğitim Bakanlığı, İletişim Başkanlığı, TOKİ ve resmi kurumların kamu personeli ile adayları ilgilendiren doğrulanmış haber arşivi.</p>
    </section>
    <section class="editorial-grid">
      {"".join(cards_html) if cards_html else '<p>Güncel resmi haberler hazırlanıyor...</p>'}
    </section>
    """
    write_html(
        website_dir,
        "haberler/index.html",
        render_page_shell(
            title="Güncel Kamu Haberleri ve Resmi Duyurular — Kamu Personel Rehberi",
            description="ÖSYM, MEB, bakanlıklar ve kamu kurumlarının teyitli atama, sınav ve personel haberleri.",
            canonical_path="/haberler/",
            body_html=news_index_body,
            active_nav="haberler",
        ),
    )
    urls.append(("/haberler/", today, "0.9"))
    return urls


# =============================================================================
# 4. EN GÜNCEL AKTİF İLAN DETAY SAYFALARI (/ilan/<slug>/)
# =============================================================================
def build_top_job_pages(website_dir: Path, limit: int = 60) -> List[Tuple[str, str, str]]:
    jobs_path = website_dir / "data" / "jobs.json"
    today = datetime.now().strftime("%Y-%m-%d")
    urls: List[Tuple[str, str, str]] = []
    if not jobs_path.exists():
        return urls

    jobs_data = json.loads(jobs_path.read_text(encoding="utf-8"))
    jobs = [j for j in jobs_data.get("jobs", []) if not j.get("is_cancellation")]
    # En güncel ve yüksek kontenjanlı ilanlara öncelik ver
    jobs.sort(key=lambda x: (int(x.get("sort_key") or 0), int(x.get("total_positions") or 0)), reverse=True)
    selected = jobs[:limit]

    seen_slugs = set()
    for job in selected:
        inst = job.get("institution") or "Kamu Kurumu"
        pos = job.get("position") or "Kamu Personeli"
        j_id = job.get("id")
        base_slug = slugify(f"{inst}-{pos}-{j_id}", max_len=78)
        if base_slug in seen_slugs:
            continue
        seen_slugs.add(base_slug)

        title = job.get("title") or f"{inst} {pos} Alım İlanı"
        quota_disp = job.get("quota_display") or f"{job.get('total_positions') or 1} Kadro"
        city = job.get("city") or "Türkiye Geneli"
        edu = job.get("education_level") or "Resmi Kılavuzda Belirtilmiştir"
        kpss = job.get("kpss_requirement") or "Kılavuza Bakınız"
        dates = job.get("date_interval") or job.get("end_date_str") or "Resmi Kılavuzda"
        source_name = job.get("source_name") or "Resmi Kamu Portalı"
        pdf_url = job.get("pdf_url") or ""
        source_url = job.get("source_url") or ""
        cat = job.get("category") or "Kamu Personeli"

        # Başvuru rehberi ile zenginleştirilmiş (350+ kelime) benzersiz ilan sayfası
        action_btns = []
        if pdf_url:
            href = pdf_url if pdf_url.startswith("http") else f"/{pdf_url.lstrip('/')}"
            action_btns.append(f'<a href="{esc(href)}" target="_blank" rel="noopener noreferrer" class="btn-editorial-primary">Resmi PDF Kılavuzunu Aç ↗</a>')
        if source_url:
            action_btns.append(f'<a href="{esc(source_url)}" target="_blank" rel="noopener noreferrer nofollow" class="btn-editorial-secondary">Resmi İlan Kaynağı ({esc(source_name)}) ↗</a>')

        job_body = f"""
        <nav class="breadcrumb-nav" aria-label="Konum">
          <a href="/">Ana Sayfa</a><span class="breadcrumb-sep">/</span>
          <a href="/">Güncel İlanlar</a><span class="breadcrumb-sep">/</span>
          <span>{esc(inst)}</span>
        </nav>

        <div class="editorial-article-layout">
          <div>
            <section class="page-hero-card apple-glass">
              <span class="page-kicker">{esc(cat)} • TEYİTLİ RESMİ İLAN</span>
              <h1 class="page-h1">{esc(title)}</h1>
              <p class="page-lead"><strong>{esc(inst)}</strong> bünyesinde istihdam edilmek üzere yayımlanan <strong>{esc(pos)}</strong> alımına ilişkin kontenjan, öğrenim, KPSS şartı ve resmi başvuru adımları.</p>
            </section>

            <section class="article-body-card apple-glass prose">
              <div class="job-meta-grid">
                <div class="job-meta-box"><div class="job-meta-label">Kontenjan</div><div class="job-meta-val">{esc(quota_disp)}</div></div>
                <div class="job-meta-box"><div class="job-meta-label">Başvuru Tarihleri</div><div class="job-meta-val">{esc(dates)}</div></div>
                <div class="job-meta-box"><div class="job-meta-label">KPSS Şartı</div><div class="job-meta-val">{esc(kpss)}</div></div>
                <div class="job-meta-box"><div class="job-meta-label">Şehir / Bölge</div><div class="job-meta-val">{esc(city)}</div></div>
              </div>

              <h2>İlan Özeti ve Kadro Detayları</h2>
              <p><strong>{esc(inst)}</strong> tarafından <strong>{esc(source_name)}</strong> üzerinden yayımlanan resmi duyuruya göre <strong>{esc(pos)}</strong> pozisyonu için toplam <strong>{esc(quota_disp)}</strong> alım gerçekleştirilecektir. İlanın öğrenim şartı <strong>{esc(edu)}</strong>, KPSS değerlendirme durumu ise <strong>{esc(kpss)}</strong> olarak bildirilmiştir.</p>

              <h2>Genel Başvuru Şartları (657 DMK & Kurum Kılavuzu)</h2>
              <ul>
                <li>Türkiye Cumhuriyeti vatandaşı olmak ve kamu haklarından mahrum bulunmamak.</li>
                <li>657 sayılı Devlet Memurları Kanunu’nun 48. maddesinde belirtilen genel şartları ve adli sicil koşullarını taşımak.</li>
                <li>Erkek adaylar için askerlikle ilişiği bulunmamak (yapmış, muaf veya tecilli olmak).</li>
                <li>Görevini devamlı yapmasına engel olabilecek sağlık sorunu bulunmamak ve güvenlik/arşiv araştırmasından olumlu sonuç almak.</li>
                <li>İlanda belirtilen <strong>{esc(edu)}</strong> mezuniyet şartını ve özel nitelikleri son başvuru tarihi itibarıyla sağlamak.</li>
              </ul>

              <h2>Nasıl Başvuru Yapılır?</h2>
              <p>Adayların başvuru işlemlerini ilan metninde belirtilen <strong>{esc(dates)}</strong> tarihleri arasında tamamlamaları gerekmektedir. Başvuru kanalı (e-Devlet / Kariyer Kapısı, kurum online başvuru sistemi veya şahsen/posta yoluyla teslim) ve istenen belgelerin tam listesi resmi başvuru kılavuzunda yer almaktadır. Eksik veya barkodsuz belgelerle yapılan başvurular komisyon tarafından değerlendirmeye alınmamaktadır.</p>

              <div class="callout-box">
                <div class="callout-box-title">Adaylar İçin Önemli Hatırlatma</div>
                <p>Başvurunuzu tamamlamadan önce kılavuzdaki <strong>özel nitelik kodlarını</strong>, yaş sınırını ve varsa belge/sertifika şartlarını mutlaka teyit edin. Kariyer Kapısı başvurularında sürecin eksiksiz tamamlanması için <a href="/rehber/kariyer-kapisi-basvuru-rehberi-adim-adim/">Kariyer Kapısı Başvuru Rehberi</a>’mizi inceleyebilirsiniz.</p>
              </div>

              <div class="editorial-actions">
                {"".join(action_btns)}
                <a href="/" class="btn-editorial-secondary">← Tüm İlanlara Dön</a>
              </div>
            </section>
          </div>

          <aside class="editorial-sidebar">
            <div class="sidebar-card apple-glass">
              <h3 class="sidebar-card-title">Faydalı Rehberler</h3>
              <ul class="sidebar-list">
                <li><a href="/rehber/2026-kpss-4b-sozlesmeli-personel-alim-sartlari/">2026 KPSS 4/B Başvuru Şartları<small>Sözleşmeli İstihdam</small></a></li>
                <li><a href="/rehber/e-devlet-kamu-ilan-basvuru-belgeleri-kontrol-listesi/">e-Devlet Başvuru Belgeleri Listesi<small>Barkodlu Evrak Rehberi</small></a></li>
                <li><a href="/rehber/guvenlik-sorusturmasi-ve-arsiv-arastirmasi-rehberi/">Güvenlik Soruşturması Rehberi<small>7315 Sayılı Kanun</small></a></li>
                <li><a href="/araclar/kpss-puan-hesaplama/">KPSS Puan Hesaplama Robotu<small>P3, P93, P94</small></a></li>
              </ul>
            </div>
          </aside>
        </div>
        """

        job_ld = {
            "@context": "https://schema.org",
            "@type": "JobPosting",
            "title": title,
            "description": f"{inst} tarafından yayımlanan {pos} alım ilanı. Kontenjan: {quota_disp}. KPSS: {kpss}. Başvuru tarihleri: {dates}.",
            "datePosted": today,
            "hiringOrganization": {"@type": "Organization", "name": inst},
            "jobLocation": {
                "@type": "Place",
                "address": {"@type": "PostalAddress", "addressLocality": city, "addressCountry": "TR"},
            },
            "employmentType": "FULL_TIME",
        }
        write_html(
            website_dir,
            f"ilan/{base_slug}/index.html",
            render_page_shell(
                title=f"{title} — Kamu Personel Rehberi",
                description=f"{inst} {pos} alımı ({quota_disp}). Başvuru tarihleri: {dates}. KPSS: {kpss}. Resmi PDF kılavuzu ve başvuru şartları.",
                canonical_path=f"/ilan/{base_slug}/",
                body_html=job_body,
                json_ld=job_ld,
                active_nav="home",
            ),
        )
        urls.append((f"/ilan/{base_slug}/", today, "0.75"))

    return urls


# =============================================================================
# 5. TEMİZ SITEMAP.XML ÜRETİCİ (Query string kopyaları YOK!)
# =============================================================================
def write_clean_sitemap(website_dir: Path, all_urls: List[Tuple[str, str, str]]) -> None:
    today = datetime.now().strftime("%Y-%m-%d")
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        "  <url>",
        f"    <loc>{BASE_URL}/</loc>",
        f"    <lastmod>{today}</lastmod>",
        "    <changefreq>daily</changefreq>",
        "    <priority>1.0</priority>",
        "  </url>",
    ]
    seen = {"/"}
    for path, lastmod, prio in all_urls:
        if path in seen:
            continue
        seen.add(path)
        lines.extend([
            "  <url>",
            f"    <loc>{BASE_URL}{path}</loc>",
            f"    <lastmod>{lastmod}</lastmod>",
            "    <changefreq>weekly</changefreq>",
            f"    <priority>{prio}</priority>",
            "  </url>",
        ])
    lines.append("</urlset>")
    sitemap_xml = "\n".join(lines) + "\n"
    (website_dir / "sitemap.xml").write_text(sitemap_xml, encoding="utf-8")
    print(f"🗺️  Temiz Sitemap üretildi: {len(seen)} benzersiz statik HTML sayfası (0 query kopyası!)")


def sync_website_to_docs(website_dir: Path, docs_dir: Path) -> None:
    """Yeni üretilen tüm SSG klasörlerini ve dosyalarını docs/ içine senkronize eder."""
    dirs_to_sync = [
        "hakkimizda", "iletisim", "gizlilik-politikasi", "kullanim-kosullari",
        "sss", "araclar", "rehber", "haberler", "haber", "ilan",
        "assets/css", "assets/js", "assets/img/covers", "assets/img/categories", "data",
    ]
    for rel in dirs_to_sync:
        src = website_dir / rel
        dst = docs_dir / rel
        if not src.exists():
            continue
        dst.mkdir(parents=True, exist_ok=True)
        for item in src.rglob("*"):
            rel_item = item.relative_to(src)
            target = dst / rel_item
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, target)

    for fname in ["sitemap.xml", "index.html", "robots.txt", "ads.txt"]:
        src_f = website_dir / fname
        if src_f.exists():
            shutil.copy2(src_f, docs_dir / fname)
    print("🔄 website/ -> docs/ senkronizasyonu tamamlandı.")


def build_all(sync_docs: bool = True) -> None:
    website_dir = ROOT_DIR / "website"
    docs_dir = ROOT_DIR / "docs"
    covers_dir = website_dir / "assets" / "img" / "covers"
    curator = VisualCuratorAgent(covers_dir)

    all_urls: List[Tuple[str, str, str]] = []
    all_urls.extend(build_static_core_pages(website_dir))
    all_urls.extend(build_guides_pages(website_dir, curator))
    all_urls.extend(build_news_pages(website_dir))
    all_urls.extend(build_top_job_pages(website_dir, limit=60))

    write_clean_sitemap(website_dir, all_urls)
    if sync_docs:
        sync_website_to_docs(website_dir, docs_dir)
    print(f"✅ SSG Build Tamamlandı! Toplam {len(all_urls) + 1} benzersiz statik sayfa yayına hazır.")


if __name__ == "__main__":
    build_all(sync_docs=True)
