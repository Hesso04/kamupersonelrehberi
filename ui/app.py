import sys
import time
import re
import json
from pathlib import Path
import io

# Proje kök dizinini Python arama yoluna ekle
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import streamlit as st
import pandas as pd
from datetime import datetime
from sqlalchemy.orm import Session

from config.settings import settings
from core.database import (
    init_db,
    get_db,
    get_all_system_settings,
    set_system_setting,
    get_system_setting,
)
from core.models import JobAnnouncement, JobStatus, Platform
from core.scheduler import scheduler, AUTOPILOT_PACE_PRESETS
from scrapers.manager import ScraperManager
from ai.processor import AIProcessor
from ai.groq_client import GroqClient
from ai.llm_client import LLMClient
from ai.search_assistant import AISearchAssistant
from graphics.generator import JobCardGenerator, CARD_THEMES
from publishers.manager import PublisherManager
from publishers.telegram import TelegramPublisher
from publishers.whatsapp import WhatsAppPublisher
from publishers.instagram import InstagramPublisher
from publishers.facebook import FacebookPublisher
from publishers.meta_helper import MetaHelper


def to_turkish_date_str(val) -> str:
    """Tarih girdilerini eksiksiz Türkçe ay isimlerine dönüştürür (Örn: 05 Ekim 2026)."""
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


# Sayfa Genel Yapılandırması
st.set_page_config(
    page_title="Kamu Personel Rehberi - Kurumsal Otomasyon Portalı",
    page_icon="🏛",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Veritabanını başlat
init_db()

# =============================================================================
# ULTRA-MODERN DARK GLASSMORPHISM TASARIM SİSTEMİ
# =============================================================================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');

    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', system-ui, -apple-system, sans-serif;
    }

    /* Ana Başlık ve Alt Başlık */
    .main-header {
        font-size: 2.1rem;
        font-weight: 800;
        background: linear-gradient(90deg, #ffffff 0%, #cbd5e1 50%, #94a3b8 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        letter-spacing: -0.02em;
        margin-bottom: 0.3rem;
    }
    .sub-header {
        font-size: 0.95rem;
        color: #94a3b8;
        line-height: 1.5;
        margin-bottom: 1.6rem;
    }

    /* Durum Rozetleri */
    .status-badge {
        padding: 5px 12px;
        border-radius: 8px;
        font-size: 0.8rem;
        font-weight: 700;
        display: inline-flex;
        align-items: center;
        gap: 6px;
        letter-spacing: 0.02em;
    }
    .badge-pending { 
        background: rgba(245, 158, 11, 0.15); 
        color: #fbbf24; 
        border: 1px solid rgba(245, 158, 11, 0.35); 
    }
    .badge-ai { 
        background: rgba(99, 102, 241, 0.15); 
        color: #a5b4fc; 
        border: 1px solid rgba(99, 102, 241, 0.35); 
    }
    .badge-approved { 
        background: rgba(16, 185, 129, 0.15); 
        color: #34d399; 
        border: 1px solid rgba(16, 185, 129, 0.35); 
    }
    .badge-published { 
        background: rgba(16, 185, 129, 0.2); 
        color: #10b981; 
        border: 1px solid #10b981;
        box-shadow: 0 0 10px rgba(16, 185, 129, 0.25);
    }
    .badge-rejected { 
        background: rgba(239, 68, 68, 0.15); 
        color: #f87171; 
        border: 1px solid rgba(239, 68, 68, 0.35); 
    }
    
    /* Buton Zarafeti */
    .stButton>button {
        border-radius: 10px;
        font-weight: 600;
        letter-spacing: 0.01em;
        transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
        border: 1px solid rgba(255, 255, 255, 0.1);
    }
    .stButton>button:hover {
        transform: translateY(-1px);
        box-shadow: 0 8px 25px rgba(0, 0, 0, 0.35);
    }

    /* Genişletilebilir Kartlar */
    div[data-testid="stExpander"] {
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 14px !important;
        background: rgba(15, 23, 42, 0.45) !important;
        margin-bottom: 12px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
    }
</style>
""", unsafe_allow_html=True)


# =============================================================================
# YAN MENÜ (SIDEBAR) & NAVİGASYON
# =============================================================================
logo_img_path = ROOT_DIR / "graphics" / "assets" / "logo.png"
if logo_img_path.exists():
    st.sidebar.image(str(logo_img_path), width=72)
else:
    st.sidebar.markdown("🏛")

st.sidebar.title("Kamu Personel Rehberi")
st.sidebar.caption("Anti-Clickbait & Doğrulanmış Resmi Kamu İlanları")

menu = st.sidebar.radio(
    "Modüller",
    [
        "📋 Onay Havuzu (Human-in-the-Loop)",
        "🤖 AI Doğrulanmış İlan Danışmanı & Arama",
        "📊 Gösterge Paneli (Dashboard)",
        "🌐 İlan Tarayıcı & Manuel Ekle",
        "🚀 Telegram Kanal Büyütme & Üye Çekme",
        "📸 Instagram Büyüme & Otomasyon Merkezi",
        "⚙️ Sistem & API Ayarları",
    ],
    index=0,
)

st.sidebar.markdown("---")
# Arka Plan Zamanlayıcı Kontrolü
if not scheduler.is_running:
    scheduler.start(interval_minutes=30)

sched_status = scheduler.get_status()
st.sidebar.subheader("⏰ Otomatik Tarayıcı & Otopilot")
if sched_status["is_running"]:
    st.sidebar.success("🟢 Otomatik Tarama & Otopilot Açık")
    if st.sidebar.button("⏹️ Otomasyonu Durdur", use_container_width=True):
        scheduler.stop()
        st.rerun()
else:
    st.sidebar.info("⚪ Otomasyon Beklemede")
    if st.sidebar.button("▶️ Otomasyonu Başlat", use_container_width=True):
        scheduler.start(interval_minutes=30)
        st.rerun()

# Otopilot Dağıtım Kanalları
cur_ap_raw = get_system_setting("AUTOPILOT_CHANNELS", "TELEGRAM,INSTAGRAM,FACEBOOK")
cur_ap_list = [c.strip().upper() for c in cur_ap_raw.split(",") if c.strip()]
selected_ap_channels = st.sidebar.multiselect(
    "📢 Otopilot Dağıtım Kanalları",
    options=["TELEGRAM", "INSTAGRAM", "FACEBOOK", "WHATSAPP"],
    default=[c for c in cur_ap_list if c in ["TELEGRAM", "INSTAGRAM", "FACEBOOK", "WHATSAPP"]],
    format_func=lambda x: {
        "TELEGRAM": "✈️ Telegram Kanalı",
        "INSTAGRAM": "📸 Instagram",
        "FACEBOOK": "📘 Facebook Sayfası",
        "WHATSAPP": "💬 WhatsApp (Otomatik Bot)"
    }.get(x, x),
    help="Otopilot aktifken yeni ilanların otomatik yayınlanacağı kanallar."
)
new_ap_str = ",".join(selected_ap_channels)
if new_ap_str != cur_ap_raw:
    set_system_setting("AUTOPILOT_CHANNELS", new_ap_str)

# Otopilot Paylaşım Temposu (Anti-Spam Koruması)
cur_pace = get_system_setting("AUTOPILOT_PACE_PRESET", "1_PER_HOUR")
pace_keys = list(AUTOPILOT_PACE_PRESETS.keys())
p_idx = pace_keys.index(cur_pace) if cur_pace in pace_keys else 0
selected_pace = st.sidebar.selectbox(
    "⏱️ Otopilot Temposu (Spam Koruması)",
    options=pace_keys,
    index=p_idx,
    format_func=lambda k: AUTOPILOT_PACE_PRESETS[k]["short_name"],
    help="Sosyal medya platformlarının spam filtrelerine takılmamak için ilanlar arası bekleme aralığı."
)
if selected_pace != cur_pace:
    set_system_setting("AUTOPILOT_PACE_PRESET", selected_pace)

st.sidebar.markdown("---")
# Entegrasyon Durum Özeti & Canlı Token Kontrolü
groq_status = "🟢" if settings.active_groq_api_key else "🔴"
telegram_status = "🟢" if (settings.active_telegram_bot_token and settings.active_telegram_channel_id) else "🔴"

try:
    wp_check = WhatsAppPublisher()
    if wp_check.is_logged_in():
        wa_status = f"🟢 ({wp_check.mode.upper()})"
    else:
        wa_status = "⚪ (Bağlantı Yok)"
except Exception:
    wa_status = "⚪"

@st.cache_data(ttl=60)
def get_cached_meta_diagnosis(token: Optional[str]) -> dict:
    if not token or not token.strip():
        return {"is_valid": False, "is_configured": False, "status_code": "EMPTY", "message": "Belirteç tanımlı değil."}
    return MetaHelper.diagnose_token(token)

cur_meta_tok = get_system_setting("INSTAGRAM_ACCESS_TOKEN") or get_system_setting("FACEBOOK_ACCESS_TOKEN")
meta_diag = get_cached_meta_diagnosis(cur_meta_tok)

if not meta_diag.get("is_configured"):
    ig_status = "⚪ (Ayar Yok)"
    fb_status = "⚪ (Ayar Yok)"
elif meta_diag.get("status_code") == "EXPIRED":
    ig_status = "🔴 (Süresi Doldu)"
    fb_status = "🔴 (Süresi Doldu)"
elif not meta_diag.get("is_valid"):
    ig_status = "🔴 (Hata)"
    fb_status = "🔴 (Hata)"
else:
    ig_status = "🟢 (Aktif)"
    fb_status = "🟢 (Aktif)"

st.sidebar.markdown(f"**Groq AI:** {groq_status} | **Telegram:** {telegram_status}")
st.sidebar.markdown(f"**Instagram:** {ig_status}")
st.sidebar.markdown(f"**Facebook:** {fb_status}")
st.sidebar.markdown(f"**WhatsApp:** {wa_status}")

st.sidebar.markdown("---")
if st.sidebar.button("🔄 Önbelleği Sıfırla & Yenile", use_container_width=True, help="Streamlit önbelleğini temizler ve sistemi en son verilerle yeniler."):
    st.cache_data.clear()
    st.cache_resource.clear()
    st.rerun()

st.sidebar.caption("v1.4.0 - Çok Temalı, Çok Kanallı & Anti-Spam Otopilot")



# =============================================================================
# MODÜL 1: ONAY HAVUZU (HUMAN-IN-THE-LOOP)
# =============================================================================
if menu == "📋 Onay Havuzu (Human-in-the-Loop)":
    st.markdown('<div class="main-header">📋 İlan İnceleme ve Onay Havuzu</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-header">Doğrulanan resmi ilanlar sosyal medyaya gitmeden önce buradan insan onayından geçer. '
        'Metni düzenleyebilir, dinamik QR kodlu görseli kontrol edebilir ve seçtiğiniz kanallara (Telegram, WhatsApp, Instagram) dağıtabilirsiniz.</div>',
        unsafe_allow_html=True,
    )

    # =========================================================================
    # META TOKEN ACİL DURUM UYARI BARI (INSTAGRAM & FACEBOOK KESİNTİ BİLDİRİMİ)
    # =========================================================================
    if meta_diag.get("status_code") == "EXPIRED":
        st.error(
            "🚨 **DİKKAT: Meta (Instagram & Facebook) Erişim Belirtecinin (Access Token) Süresi Doldu!**\n\n"
            "• **Durum:** Telegram otopilotu sorunsuz çalışıyor ancak Meta oturum süresi bittiği için Instagram ve Facebook akış paylaşımları durduruldu.\n"
            "• **Hızlı Çözüm:** Meta for Developers panelinden yeni aldığınız belirteci aşağıdaki kutuya yapıştırıp 'Güncelle & Başlat'a tıklayın. Sistem anında tüm kanalları yeniden devreye sokacaktır."
        )
        c_q_tok, c_q_btn = st.columns([3.5, 1.2])
        with c_q_tok:
            new_quick_token = st.text_input(
                "Yeni Meta Access Token",
                placeholder="EAAXZAhM1NsdQ...",
                type="password",
                key="quick_meta_token_box",
                label_visibility="collapsed"
            )
        with c_q_btn:
            if st.button("⚡ Belirteci Güncelle & Başlat", type="primary", use_container_width=True, key="quick_save_meta_btn"):
                if new_quick_token.strip():
                    set_system_setting("INSTAGRAM_ACCESS_TOKEN", new_quick_token.strip(), is_secret=True)
                    set_system_setting("FACEBOOK_ACCESS_TOKEN", new_quick_token.strip(), is_secret=True)
                    st.cache_data.clear()
                    st.success("✅ Yeni Meta Belirteci kaydedildi! Instagram ve Facebook akışı yeniden aktifleştirildi.")
                    st.rerun()
                else:
                    st.warning("Lütfen yeni belirteci kutuya yapıştırın.")

        with st.expander("📋 30 Saniyede Yeni Token Nasıl Alınır? (Rehber)"):
            st.markdown("""
            1. **[Meta for Developers - Graph API Explorer](https://developers.facebook.com/tools/explorer/)** sayfasına gidin.
            2. Sağ üstten **Meta Uygulamanızı** seçin.
            3. **User Token** seçiliyken şu izinlerin ekli olduğundan emin olun:
               - `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`
               - `instagram_basic`, `instagram_content_publish`
            4. **Generate Access Token** butonuna tıklayıp onay verin.
            5. Çıkan `EAA...` kodunu kopyalayıp yukarıdaki kutucuğa yapıştırın ve **⚡ Belirteci Güncelle & Başlat**'a basın!
            """)
        st.markdown("---")

    # =========================================================================
    # OTOPİLOT & MANUEL ONAY KONTROL BARI
    # =========================================================================
    manual_mode_setting = get_system_setting("MANUAL_APPROVAL_REQUIRED", "true") == "true"
    
    col_mode_tgl, col_mode_action = st.columns([3, 2])
    with col_mode_tgl:
        is_manual_active = st.toggle(
            "🛡️ Manuel Onay Modu (İlanlar yayınlanmadan önce yönetici onayı beklesin)",
            value=manual_mode_setting,
            help="Açıkken: İlanlar bu havuza düşer ve onaylamanızı bekler. Kapalıyken: Güvenilir .gov.tr kaynaklı yeni ilanlar AI tarafından işlenir, afişiyle birlikte Telegram, Instagram ve WhatsApp kanallarına eşzamanlı otomatik yayınlanır."
        )
        if is_manual_active != manual_mode_setting:
            set_system_setting("MANUAL_APPROVAL_REQUIRED", "true" if is_manual_active else "false")
            if not is_manual_active:
                scheduler.trigger_autopilot_now(limit=2)
            st.rerun()

    with col_mode_action:
        if not is_manual_active:
            if st.button("🚀 Otopilotu Şimdi Çalıştır (Bekleyenleri Kanallara Dağıt)", use_container_width=True, type="primary"):
                with st.spinner("Otopilot devrede: Doğrulanmış ilanlar Telegram, WhatsApp ve Instagram'a aktarılıyor..."):
                    pub_count = scheduler.trigger_autopilot_now(limit=5)
                    if pub_count > 0:
                        st.success(f"{pub_count} adet yeni ilan başarıyla seçili kanallara otomatik yayınlandı!")
                    else:
                        st.info("Yayınlanacak bekleyen doğrulanmış ilan bulunamadı.")
                    st.rerun()

    if not is_manual_active:
        active_ch_names = []
        if "TELEGRAM" in selected_ap_channels: active_ch_names.append("✈️ Telegram")
        if "INSTAGRAM" in selected_ap_channels: active_ch_names.append("📸 Instagram")
        if "FACEBOOK" in selected_ap_channels: active_ch_names.append("📘 Facebook")
        if "WHATSAPP" in selected_ap_channels: active_ch_names.append("💬 WhatsApp")
        ch_text = ", ".join(active_ch_names) if active_ch_names else "Seçili kanal yok"
        
        ap_stat = scheduler.get_autopilot_status()
        st.success(
            f"🟢 **OTOPİLOT AKTİF:** Doğrulanmış (.gov.tr) kaynaklı ilanlar **{ch_text}** kanallarına otomatik yayınlanmaktadır. "
            f"| ⏱️ **Tempo:** `{ap_stat['pace_name']}` | ⏳ **Sonraki İlan Kalan Süre:** `{ap_stat['countdown_str']}`"
        )
    else:
        st.info("🛡️ **MANUEL ONAY AKTİF:** Yeni gelen ilanlar sosyal kanallara dağıtılmadan önce bu onay havuzunda insan denetiminden geçer.")

    st.markdown("---")

    # Filtreleme ve Arama Barı
    col_filter, col_search, col_actions = st.columns([2, 2, 2.4])
    with col_filter:
        status_filter = st.selectbox(
            "Durum Filtresi",
            ["Onay Bekleyenler (Aktif Kuyruk)", "AI Tarafından İşlenenler", "Yayınlananlar", "Reddedilenler", "Tümü"],
            index=0,
        )

    with col_search:
        search_query = st.text_input("🔍 Kurum veya Başlık Ara", placeholder="Örn: Üniversite, Sağlık, Mühendis...")

    with col_actions:
        st.write("")
        st.write("")
        c_act1, c_act2, c_act3 = st.columns(3)
        with c_act1:
            if st.button("⚡ AI Formatla", use_container_width=True, help="İlk 5 ilanı AI ile zenginleştirir"):
                with st.spinner("Yapay zeka analiz ediyor..."):
                    processor = AIProcessor()
                    processed = processor.batch_process_pending(limit=5)
                    st.success(f"{len(processed)} ilan AI tarafından işlendi!")
                    st.rerun()
        with c_act2:
            if st.button("🎨 Görsel Üret", use_container_width=True, help="İlk 5 ilan için yeni kart üretir"):
                with st.spinner("Görsel kartlar üretiliyor..."):
                    generator = JobCardGenerator()
                    with get_db() as db:
                        target_jobs = db.query(JobAnnouncement).filter(
                            JobAnnouncement.image_path == None,
                            JobAnnouncement.status.in_([JobStatus.PENDING_APPROVAL, JobStatus.AI_PROCESSED])
                        ).limit(5).all()
                        for tj in target_jobs:
                            d_txt = to_turkish_date_str(tj.application_end_date)
                            tj_pdf = getattr(tj, "pdf_path", None)
                            has_pdf = bool(tj_pdf and Path(tj_pdf).exists())
                            c_path = generator.generate_card(
                                job_id=tj.id,
                                institution=tj.institution or "Kamu Kurumu",
                                position=tj.position or tj.title,
                                total_positions=tj.total_positions,
                                kpss_requirement=tj.kpss_requirement,
                                education_level=tj.education_level,
                                deadline=d_txt,
                                source_url=tj.source_url,
                                has_pdf=has_pdf,
                                title=tj.title or ""
                            )
                            tj.image_path = str(c_path)
                        db.commit()
                    st.success("5 adet yüksek çözünürlüklü kurumsal kart üretildi!")
                    st.rerun()
        with c_act3:
            if st.button("🔄 Eksikleri Eşitle", use_container_width=True, help="Daha önce sadece Telegram'a gitmiş son 5 ilanın eksik Instagram & Facebook paylaşımlarını tamamlar"):
                with st.spinner("Eksik kanallar eşitleniyor..."):
                    sync_info = scheduler.sync_missing_channels(limit=5)
                    if sync_info["synced_count"] > 0:
                        st.success(f"🎉 {sync_info['synced_count']} adet ilanın eksik Instagram & Facebook paylaşımları tamamlandı!")
                    else:
                        st.info("Eşitlenecek eksik kanal bulunamadı veya belirteç yenilenmesi gerekiyor.")
                    st.rerun()


    # Kurum Türü Hızlı Filtresi
    inst_type = st.radio("Kurum Türü:", ["Tümü", "🏛 Üniversiteler", "🏢 Belediyeler", "🇹🇷 Bakanlıklar ve Genel Müdürlükler"], horizontal=True)

    # Hızlı Toplu Dağıtım Aksiyon Barı
    st.markdown("---")
    c_b_info, c_b_chan, c_b_btn = st.columns([3, 2, 2])
    with c_b_info:
        st.markdown("⚡ **Hızlı Toplu Yayınlama:** Bekleyen sıradaki 5 doğrulanmış ilanı seçtiğiniz kanallara tek tıkla yayınlayın.")
    with c_b_chan:
        b_chans = st.multiselect(
            "Yayın Kanalları:",
            options=["TELEGRAM", "INSTAGRAM", "FACEBOOK", "WHATSAPP"],
            default=["TELEGRAM", "INSTAGRAM", "FACEBOOK"],
            key="batch_publish_channels",
            format_func=lambda x: {"TELEGRAM": "✈️ Telegram", "INSTAGRAM": "📸 Instagram", "FACEBOOK": "📘 Facebook", "WHATSAPP": "💬 WhatsApp (Bot)"}.get(x, x)
        )
    with c_b_btn:
        st.write("")
        if st.button("🚀 İlk 5 İlanı Toplu Yayınla", type="primary", use_container_width=True):
            if not b_chans:
                st.warning("Lütfen en az bir yayın kanalı seçin.")
            else:
                with st.spinner("Seçili ilanlar kanallara dağıtılıyor..."):
                    with get_db() as db:
                        target_batch = db.query(JobAnnouncement).filter(
                            JobAnnouncement.status.in_([JobStatus.PENDING_APPROVAL, JobStatus.AI_PROCESSED])
                        ).order_by(JobAnnouncement.id.asc()).limit(5).all()
                        batch_ids = [b.id for b in target_batch]

                    if not batch_ids:
                        st.info("Kuyrukta bekleyen ilan bulunamadı.")
                    else:
                        pub_mgr = PublisherManager()
                        sys_def_theme = get_system_setting("DEFAULT_CARD_THEME", "DARK_NOIR")
                        succ_count = 0
                        for b_id in batch_ids:
                            res = pub_mgr.publish_job(b_id, channels=b_chans, theme=sys_def_theme)
                            if any(ok for ok, _ in res.values()):
                                succ_count += 1
                        st.success(f"🎉 {succ_count} adet ilan seçili kanallara ({', '.join(b_chans)}) başarıyla dağıtıldı!")
                        st.rerun()
    st.markdown("---")

    # Filtreye göre sorgula
    with get_db() as db:
        query = db.query(JobAnnouncement)
        if status_filter == "Onay Bekleyenler (Aktif Kuyruk)":
            query = query.filter(JobAnnouncement.status.in_([JobStatus.PENDING_APPROVAL, JobStatus.AI_PROCESSED]))
        elif status_filter == "AI Tarafından İşlenenler":
            query = query.filter(JobAnnouncement.status == JobStatus.AI_PROCESSED)
        elif status_filter == "Yayınlananlar":
            query = query.filter(JobAnnouncement.status == JobStatus.PUBLISHED)
        elif status_filter == "Reddedilenler":
            query = query.filter(JobAnnouncement.status == JobStatus.REJECTED)

        # Kurum Türü Filtresi
        if inst_type == "🏛 Üniversiteler":
            query = query.filter(JobAnnouncement.institution.ilike("%ÜNİVERSİTE%"))
        elif inst_type == "🏢 Belediyeler":
            query = query.filter(JobAnnouncement.institution.ilike("%BELEDİYE%"))
        elif inst_type == "🇹🇷 Bakanlıklar ve Genel Müdürlükler":
            query = query.filter(~JobAnnouncement.institution.ilike("%ÜNİVERSİTE%") & ~JobAnnouncement.institution.ilike("%BELEDİYE%"))

        if search_query.strip():
            sq = f"%{search_query.strip()}%"
            query = query.filter(
                (JobAnnouncement.title.ilike(sq)) |
                (JobAnnouncement.institution.ilike(sq)) |
                (JobAnnouncement.position.ilike(sq))
            )

        jobs = query.order_by(JobAnnouncement.id.desc()).limit(30).all()

    if not jobs:
        st.info("Bu kriterlere uygun ilan bulunamadı.")
    else:
        st.write(f"Toplam **{len(jobs)}** ilan listeleniyor:")

        for job in jobs:
            badge_class = {
                JobStatus.PENDING_APPROVAL: "badge-pending",
                JobStatus.AI_PROCESSED: "badge-ai",
                JobStatus.APPROVED: "badge-approved",
                JobStatus.PUBLISHED: "badge-published",
                JobStatus.REJECTED: "badge-rejected",
            }.get(job.status, "badge-pending")

            with st.expander(f"#{job.id} | {job.institution or 'Kurum Belirtilmedi'} - {job.title[:80]}...", expanded=(job.id == jobs[0].id)):
                cur_pub = (job.published_channels or "").upper()
                is_tg = "TELEGRAM" in cur_pub
                is_ig = "INSTAGRAM" in cur_pub
                is_fb = "FACEBOOK" in cur_pub
                is_wa = "WHATSAPP" in cur_pub

                tag_tg = "🟢 ✈️ Telegram" if is_tg else "⚪ ✈️ Telegram"
                tag_ig = "🟢 📸 Instagram" if is_ig else ("🔴 📸 Instagram" if is_tg else "⚪ 📸 Instagram")
                tag_fb = "🟢 📘 Facebook" if is_fb else ("🔴 📘 Facebook" if is_tg else "⚪ 📘 Facebook")
                tag_wa = "🟢 💬 WhatsApp" if is_wa else "⚪ 💬 WhatsApp"

                st.markdown(
                    f'<span class="status-badge {badge_class}">{job.status.value}</span> '
                    f'<b>Kaynak:</b> {job.source_name} | <b>Doğrulandı:</b> {"✅ Evet (.gov.tr)" if job.is_verified else "⚠️ Şüpheli"}<br>'
                    f'<b>Kanal Dağıtımı:</b> <code>{tag_tg}</code> | <code>{tag_ig}</code> | <code>{tag_fb}</code> | <code>{tag_wa}</code>',
                    unsafe_allow_html=True,
                )
                if job.admin_notes and ("Hata" in job.admin_notes or "Kanal Hatası" in job.admin_notes):
                    st.caption(f"⚠️ {job.admin_notes}")

                if job.status == JobStatus.PUBLISHED and (not is_ig or not is_fb):
                    if st.button(f"🔁 Sadece Eksik Kanallara Gönder (#{job.id} ➔ Instagram & Facebook)", key=f"btn_resync_{job.id}"):
                        with st.spinner("Eksik kanallara dağıtılıyor..."):
                            pm_res = PublisherManager().publish_missing_channels(job.id)
                            st.success(f"Gönderim tamamlandı: {pm_res}")
                            st.rerun()

                st.write("")

                c_left, c_right = st.columns([3, 2])

                with c_left:
                    st.subheader("📝 İlan Detayları & Dağıtım Metni")
                    # Akıllı veri temizliği (Çelişkili veya eksik verileri otomatik düzelt)
                    clean_title = job.title or ""
                    parts = [p.strip() for p in clean_title.split(" - ") if p.strip()]
                    if len(parts) >= 2 and parts[0].upper() == parts[1].upper():
                        auto_inst = parts[0]
                        rem = " - ".join(parts[2:]) if len(parts) > 2 else parts[1]
                    elif len(parts) >= 2:
                        auto_inst = parts[0]
                        rem = " - ".join(parts[1:])
                    else:
                        auto_inst = job.institution or "Kamu Kurumu"
                        rem = clean_title

                    if rem.upper().startswith(auto_inst.upper()):
                        rem = rem[len(auto_inst):].strip(" -:")

                    # Kontenjan hesabı (Başlıktaki gerçek sayı ile senkronize et)
                    all_nums = [int(n) for n in re.findall(r"\b(\d+)\b", rem)]
                    if job.total_positions and job.total_positions > 1:
                        auto_count = job.total_positions
                    elif all_nums and all_nums[0] > 1:
                        auto_count = all_nums[0]
                    else:
                        auto_count = job.total_positions or 1

                    # Pozisyon hesabı (Kadro adından sayıları ve 'Alımı/Alacak' eklerini temizle)
                    pos_src = job.position if (job.position and job.position != "None") else rem
                    clean_p = re.sub(r"^\s*(\d+\s*)+", "", pos_src)
                    clean_p = re.sub(r"\s*(?:alacak|alımı|temin edilecek|alınacaktır|alınacak|alım ilanı).*$", "", clean_p, flags=re.IGNORECASE)
                    clean_p = re.sub(r"\s+personel$", " Personeli", clean_p, flags=re.IGNORECASE).strip(" -:,")
                    auto_pos = clean_p if (clean_p and len(clean_p) >= 3) else "Kamu Personeli"

                    job_pdf_path = getattr(job, "pdf_path", None)
                    has_pdf_file = bool(job_pdf_path and Path(job_pdf_path).exists())

                    deadline_str = to_turkish_date_str(job.application_end_date)

                    proper_title = f"{auto_inst} - {auto_count} {auto_pos} Alımı" if auto_count > 1 else f"{auto_inst} - {auto_pos} Alımı"

                    with st.form(key=f"edit_form_{job.id}"):
                        f_title = st.text_input("İlan Başlığı", value=proper_title)
                        f_inst = st.text_input("Kamu Kurumu", value=auto_inst)
                        
                        f_col1, f_col2 = st.columns(2)
                        with f_col1:
                            f_pos = st.text_input("Kadro / Pozisyon", value=auto_pos)
                            f_kpss = st.text_input("KPSS Şartı", value=job.kpss_requirement or "Resmi Kılavuzda")
                        with f_col2:
                            f_count = st.number_input("Kontenjan", value=int(auto_count), min_value=1)
                            f_edu = st.text_input("Mezuniyet", value=job.education_level or "İlgili Bölüm Mezunu")

                        # Ön tanımlı paylaşım metninde çelişki ve 'None' olmayacak şekilde oluştur
                        if has_pdf_file:
                            pdf_row = "📄 <b>Resmi Kılavuz & Başvuru:</b> Resmi alım şartnamesi ve kadro tablosu (PDF) ekte sunulmuştur."
                        else:
                            clean_src = job.source_url or "https://kamuilan.sbb.gov.tr/"
                            if "ilanDetay.aspx" in clean_src:
                                clean_src = "https://kamuilan.sbb.gov.tr/"
                            pdf_row = f"🔗 <b>Detaylar:</b> {clean_src}"

                        dynamic_default_post = (
                            f"📢 <b>{auto_inst} Personel Alım İlanı</b>\n\n"
                            f"🏛 <b>Kurum:</b> {auto_inst}\n"
                            f"📋 <b>Kadro / Pozisyon:</b> {auto_pos}\n"
                            f"👥 <b>Kontenjan:</b> {auto_count} Kişi\n"
                            f"🗓 <b>Son Başvuru Tarihi:</b> {deadline_str}\n\n"
                            f"{pdf_row}\n"
                            f"#KamuPersoneli #İlan #KamuAlımı"
                        )

                        cur_post = job.social_post_text
                        if (
                            not cur_post
                            or "None" in cur_post
                            or f"<b>Kontenjan:</b> 1 Kişi" in cur_post and auto_count > 1
                            or f"{auto_count} {auto_pos} Alımı" in cur_post
                        ):
                            cur_post = dynamic_default_post

                        f_post = st.text_area(
                            "Telegram / Sosyal Medya Paylaşım Metni (HTML destekli)",
                            value=cur_post,
                            height=200,
                        )

                        clean_src_url = job.source_url or "https://kamuilan.sbb.gov.tr/"
                        if "ilanDetay.aspx" in clean_src_url:
                            clean_src_url = "https://kamuilan.sbb.gov.tr/"
                        f_link = st.text_input("Resmi Kaynak Linki", value=clean_src_url)

                        save_btn = st.form_submit_button("💾 Değişiklikleri Kaydet")
                        if save_btn:
                            with get_db() as db:
                                target = db.query(JobAnnouncement).filter(JobAnnouncement.id == job.id).first()
                                if target:
                                    target.title = f_title
                                    target.institution = f_inst
                                    target.position = f_pos
                                    target.kpss_requirement = f_kpss
                                    target.total_positions = f_count
                                    target.education_level = f_edu
                                    target.social_post_text = f_post
                                    target.source_url = f_link
                                    db.commit()
                            st.success("İlan bilgileri kaydedildi!")
                            st.rerun()

                with c_right:
                    st.subheader("🖼️ Sosyal Medya Kartı & QR Kod")
                    img_path = Path(job.image_path) if job.image_path else None
                    if img_path and img_path.exists():
                        st.image(str(img_path), caption=f"Kart: {img_path.name}", use_container_width=True)
                    else:
                        st.info("Bu ilan için henüz görsel kart üretilmedi.")

                    # Çoklu Renk ve Görsel Tema Seçici
                    theme_keys = list(CARD_THEMES.keys())
                    default_theme_sys = get_system_setting("DEFAULT_CARD_THEME", "DARK_NOIR")
                    cur_idx = theme_keys.index(default_theme_sys) if default_theme_sys in theme_keys else 0
                    selected_job_theme = st.selectbox(
                        "🎨 Afiş Tasarım Teması",
                        options=theme_keys,
                        index=cur_idx,
                        format_func=lambda k: CARD_THEMES[k]["name"],
                        key=f"theme_{job.id}",
                        help="İlan afişinin renk paletini ve görsel temasını belirleyin."
                    )

                    c_gen, c_ai = st.columns(2)
                    with c_gen:
                        if st.button("🎨 Seçili Temayla Üret", key=f"btn_img_{job.id}", use_container_width=True):
                            generator = JobCardGenerator()
                            deadline_txt = to_turkish_date_str(job.application_end_date)
                            new_path = generator.generate_card(
                                job_id=job.id,
                                institution=auto_inst,
                                position=auto_pos,
                                total_positions=auto_count,
                                kpss_requirement=job.kpss_requirement,
                                education_level=job.education_level,
                                deadline=deadline_txt,
                                source_url=job.source_url,
                                has_pdf=has_pdf_file,
                                theme=selected_job_theme,
                                title=job.title or ""
                            )
                            with get_db() as db:
                                target = db.query(JobAnnouncement).filter(JobAnnouncement.id == job.id).first()
                                target.image_path = str(new_path)
                                if not target.position: target.position = auto_pos
                                if not target.total_positions or target.total_positions == 1: target.total_positions = auto_count
                                db.commit()
                            st.success(f"Yeni görsel kart oluşturuldu! ({CARD_THEMES[selected_job_theme]['name']})")
                            st.rerun()

                    with c_ai:
                        if st.button("🤖 AI ile Yeniden İşle", key=f"btn_ai_{job.id}", use_container_width=True):
                            processor = AIProcessor()
                            processor.process_job(job.id)
                            st.success("Yapay zeka bilgileri güncelledi!")
                            st.rerun()

                st.markdown("---")
                # Çok Kanallı Dağıtım Seçimi ve Aksiyonlar
                st.markdown("##### 🚀 Yayınlama Kanallarını Seçin")
                ch_col1, ch_col2, ch_col3, ch_col4 = st.columns(4)
                with ch_col1:
                    use_tg = st.checkbox("✈️ Telegram", value=True, key=f"ch_tg_{job.id}")
                with ch_col2:
                    use_ig = st.checkbox("📸 Instagram", value=True, key=f"ch_ig_{job.id}")
                with ch_col3:
                    use_fb = st.checkbox("📘 Facebook", value=True, key=f"ch_fb_{job.id}")
                with ch_col4:
                    use_wa = st.checkbox("💬 WhatsApp (Bot)", value=False, key=f"ch_wa_{job.id}", help="WhatsApp Web veya Whapi bot ile otomatik göndermeyi dener. Manuel paylaşacaksanız kapalı bırakınız.")

                selected_channels = []
                if use_tg: selected_channels.append("TELEGRAM")
                if use_ig: selected_channels.append("INSTAGRAM")
                if use_fb: selected_channels.append("FACEBOOK")
                if use_wa: selected_channels.append("WHATSAPP")

                act_col1, act_col2, act_col3 = st.columns([3, 1, 2])

                with act_col1:
                    channels_label = ", ".join(selected_channels) if selected_channels else "Hiçbiri"
                    pub_btn = st.button(
                        f"🚀 ONAYLA VE SEÇİLEN KANALLARDA PAYLAŞ ({channels_label})",
                        key=f"pub_{job.id}",
                        type="primary",
                        use_container_width=True,
                    )
                    if pub_btn:
                        if not selected_channels:
                            st.warning("Lütfen en az bir paylaşım kanalı seçiniz.")
                        else:
                            publisher = PublisherManager()
                            results = publisher.publish_job(job.id, channels=selected_channels, theme=selected_job_theme)
                            success_msgs = []
                            error_msgs = []
                            for ch, (succ, msg) in results.items():
                                if succ:
                                    success_msgs.append(f"✅ {ch}: {msg}")
                                else:
                                    error_msgs.append(f"❌ {ch}: {msg}")

                            if success_msgs:
                                st.balloons()
                                for sm in success_msgs: st.success(sm)
                                st.rerun()
                            if error_msgs:
                                for em in error_msgs: st.error(em)

                with act_col2:
                    if st.button("❌ Reddet (Tık Tuzağı/Eski)", key=f"rej_{job.id}", use_container_width=True):
                        with get_db() as db:
                            target = db.query(JobAnnouncement).filter(JobAnnouncement.id == job.id).first()
                            target.status = JobStatus.REJECTED
                            db.commit()
                        st.warning(f"İlan #{job.id} reddedildi.")
                        st.rerun()

                with act_col3:
                    # Kural: Varsa direkt alım PDF'i, yoksa sadece haber linki
                    job_pdf = getattr(job, "pdf_path", None)
                    pdf_file = Path(job_pdf) if job_pdf else None
                    if pdf_file and pdf_file.exists():
                        with open(pdf_file, "rb") as f_pdf:
                            st.download_button(
                                label="📄 Resmi Kılavuzu İndir (PDF)",
                                data=f_pdf.read(),
                                file_name=f"{job.id}_{job.institution}_Kilavuz.pdf",
                                mime="application/pdf",
                                key=f"dl_pdf_{job.id}",
                                use_container_width=True
                            )
                    else:
                        clean_url = job.source_url or "https://kamuilan.sbb.gov.tr/"
                        if "ilanDetay.aspx" in clean_url:
                            clean_url = "https://kamuilan.sbb.gov.tr/"
                        st.link_button("🌐 Resmi Haber / Duyuru Sayfası", clean_url, use_container_width=True)

                # =============================================================
                # WHATSAPP İÇİN HIZLI MANUEL PAYLAŞIM PANELİ
                # =============================================================
                with st.expander("💬 WhatsApp İçin Manuel Paylaşım Araçları (Tek Tıkla Kopyala & İndir)", expanded=False):
                    wa_col_text, wa_col_actions = st.columns([3, 2])

                    wa_formatted_text = (
                        f"📢 *{auto_inst} Personel Alım İlanı*\n\n"
                        f"🏛 *Kurum:* {auto_inst}\n"
                        f"📋 *Kadro / Pozisyon:* {auto_pos}\n"
                        f"👥 *Kontenjan:* {auto_count} Kişi\n"
                        f"🗓 *Son Başvuru Tarihi:* {deadline_str}\n"
                        f"🎓 *Öğrenim:* {job.education_level or 'Kılavuzda belirtilen'}\n"
                        f"🎯 *KPSS:* {job.kpss_requirement or 'Resmi ilanda belirtilen'}\n\n"
                        f"🔗 *Resmi Kaynak Linki:*\n{clean_src_url}\n\n"
                        f"⚠️ *Kamu Personel Rehberi teyitli resmi kamu ilanıdır.*\n"
                        f"#KamuPersoneli #İlan #MemurAlımı"
                    )

                    with wa_col_text:
                        st.text_area(
                            "WhatsApp Formatlı Metin (*Kalın* fontlarla hazır):",
                            value=wa_formatted_text,
                            height=140,
                            key=f"wa_copy_text_{job.id}",
                            help="Metni kopyalayıp doğrudan WhatsApp kanalınıza veya grubunuza yapıştırabilirsiniz."
                        )

                    with wa_col_actions:
                        st.write("")
                        import urllib.parse
                        wa_web_share_url = f"https://web.whatsapp.com/send?text={urllib.parse.quote(wa_formatted_text)}"
                        st.link_button("📲 WhatsApp Web'de Aç (Metin Yazılı)", wa_web_share_url, use_container_width=True)

                        if img_path and img_path.exists():
                            with open(img_path, "rb") as f_img_wa:
                                st.download_button(
                                    label="🖼️ Afiş Görselini İndir",
                                    data=f_img_wa.read(),
                                    file_name=f"{job.id}_{auto_inst}_Afis.png",
                                    mime="image/png",
                                    key=f"dl_wa_img_{job.id}",
                                    use_container_width=True
                                )



# =============================================================================
# MODÜL: AI DOĞRULANMIŞ İLAN DANIŞMANI & AKILLI ARAMA
# =============================================================================
elif menu == "🤖 AI Doğrulanmış İlan Danışmanı & Arama":
    st.markdown('<div class="main-header">🤖 AI Doğrulanmış İlan Danışmanı & Akıllı Arama</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-header">T.C. Strateji ve Bütçe Başkanlığı (kamuilan.sbb.gov.tr) üzerindeki <b>179+ güncel resmi kamu ilanı</b> '
        'yapay zeka tarafından taranır. Doğal dilde soru sorarak en doğru resmi ilanlara anında ulaşabilirsiniz.</div>',
        unsafe_allow_html=True,
    )

    # Hızlı Arama Butonları (Örnek Sorular)
    st.markdown("##### 💡 Hızlı Kategori Aramaları")
    q_col1, q_col2, q_col3, q_col4, q_col5 = st.columns(5)

    selected_prompt = None
    with q_col1:
        if st.button("👷 Mühendis Alımları", use_container_width=True):
            selected_prompt = "Mühendis alımı yapan tüm kamu kurumları ve belediyeler hangileridir?"
    with q_col2:
        if st.button("🏥 Sağlık & Hemşire", use_container_width=True):
            selected_prompt = "Sağlık personeli veya hemşire alımı yapan üniversite ve kurumlar hangileri?"
    with q_col3:
        if st.button("🏛 50+ Büyük Alımlar", use_container_width=True):
            selected_prompt = "50 kişiden fazla personel alan en büyük kamu alımları hangileridir?"
    with q_col4:
        if st.button("🏢 Belediye İlanları", use_container_width=True):
            selected_prompt = "Memur veya personel alımı yapan belediye ilanları hangileridir?"
    with q_col5:
        if st.button("🎯 KPSS Şartsız", use_container_width=True):
            selected_prompt = "KPSS şartsız veya düşük KPSS puanı ile alım yapan kamu duyuruları hangileridir?"

    # Doğal Dil Arama Girişi
    user_query = st.text_input(
        "Aramak İstediğiniz Pozisyon, Şehir veya Şartı Sorun:",
        value=selected_prompt or "",
        placeholder="Örn: Ankara'da veya Erzurum'da sözleşmeli personel alımı var mı?",
    )

    search_btn = st.button("🔍 Doğrulanmış Resmi Havuzda Ara ve Danış", type="primary", use_container_width=True)

    if search_btn and user_query.strip():
        with st.spinner("Yapay zeka 179+ resmi SBB ilanını tarıyor ve doğrulanmış yanıt hazırlıyor..."):
            assistant = AISearchAssistant()
            res = assistant.search_and_answer(user_query)

            st.markdown("---")
            st.markdown("### 💬 Yapay Zeka İlan Danışmanı Yanıtı")
            st.info(res["answer"])

            matched_jobs = res.get("matched_jobs", [])
            if matched_jobs:
                st.markdown(f"#### 📌 Eşleşen Resmi İlanlar ({len(matched_jobs)} İlan)")
                for mj in matched_jobs[:8]:
                    with st.container():
                        st.markdown(
                            f"**#{mj.id} | {mj.institution or 'Kamu Kurumu'}** — *{mj.title}*\n\n"
                            f"• **Kontenjan:** {mj.total_positions or 1} Kişi | **KPSS:** {mj.kpss_requirement or 'Resmi ilanda'}\n"
                            f"• **Kaynak:** {mj.source_name} (`.gov.tr` Doğrulandı)"
                        )
                        btn_col1, btn_col2 = st.columns([2, 3])
                        with btn_col1:
                            mj_pdf_str = getattr(mj, "pdf_path", None)
                            mj_pdf = Path(mj_pdf_str) if mj_pdf_str else None
                            if mj_pdf and mj_pdf.exists():
                                with open(mj_pdf, "rb") as f_pdf:
                                    st.download_button(
                                        label="📄 Resmi Kılavuzu İndir (PDF)",
                                        data=f_pdf.read(),
                                        file_name=f"{mj.id}_{mj.institution}_Kilavuz.pdf",
                                        mime="application/pdf",
                                        key=f"search_dl_{mj.id}",
                                        use_container_width=True
                                    )
                            else:
                                safe_src = mj.source_url or "https://kamuilan.sbb.gov.tr/"
                                if "ilanDetay.aspx" in safe_src:
                                    safe_src = "https://kamuilan.sbb.gov.tr/"
                                st.link_button("🌐 Resmi Haber / Duyuru Sayfası", safe_src, use_container_width=True)
                        st.markdown("---")


# =============================================================================
# MODÜL 2: GÖSTERGE PANELİ (DASHBOARD)
# =============================================================================
elif menu == "📊 Gösterge Paneli (Dashboard)":
    st.markdown('<div class="main-header">📊 Sistem Gösterge Paneli ve İstatistikler</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Kamu Personel Rehberi genel havuz verileri ve doğrulama metrikleri.</div>', unsafe_allow_html=True)

    with get_db() as db:
        total_jobs = db.query(JobAnnouncement).count()
        pending_jobs = db.query(JobAnnouncement).filter(JobAnnouncement.status.in_([JobStatus.PENDING_APPROVAL, JobStatus.AI_PROCESSED])).count()
        published_jobs = db.query(JobAnnouncement).filter(JobAnnouncement.status == JobStatus.PUBLISHED).count()
        rejected_jobs = db.query(JobAnnouncement).filter(JobAnnouncement.status == JobStatus.REJECTED).count()
        verified_jobs = db.query(JobAnnouncement).filter(JobAnnouncement.is_verified == True).count()

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Toplam Havuz", f"{total_jobs} İlan")
    m2.metric("Onay Bekleyen", f"{pending_jobs} İlan", delta=f"{pending_jobs} İşlemde", delta_color="inverse")
    m3.metric("Yayınlanan", f"{published_jobs} İlan", delta="Sosyal Medya", delta_color="normal")
    m4.metric("Reddedilen", f"{rejected_jobs} İlan")
    m5.metric("Doğrulanmış Kaynak", f"%{int((verified_jobs / total_jobs * 100)) if total_jobs > 0 else 100}")

    st.markdown("---")
    st.subheader("📋 Havuz Verilerini Dışa Aktarma (Export)")
    
    with get_db() as db:
        all_jobs = db.query(JobAnnouncement).order_by(JobAnnouncement.id.desc()).all()
        export_data = [
            {
                "ID": j.id,
                "Kurum": j.institution or "",
                "Başlık": j.title,
                "Pozisyon": j.position or "",
                "Kontenjan": j.total_positions or 1,
                "KPSS": j.kpss_requirement or "",
                "Kaynak": j.source_name,
                "Durum": j.status.value,
                "Kaynak URL": j.source_url,
                "Tarih": j.created_at.strftime("%Y-%m-%d %H:%M") if j.created_at else "",
            }
            for j in all_jobs
        ]

    if export_data:
        df = pd.DataFrame(export_data)
        csv_buffer = io.StringIO()
        df.to_csv(csv_buffer, index=False, encoding="utf-8-sig")
        
        c_exp1, c_exp2 = st.columns([1, 4])
        with c_exp1:
            st.download_button(
                label="📥 CSV Olarak İndir (Excel Uyumlu)",
                data=csv_buffer.getvalue(),
                file_name=f"kamu_ilan_havuzu_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                use_container_width=True
            )

    st.markdown("---")
    st.subheader("🕒 Son Eklenen Resmi İlanlar")
    if export_data:
        st.dataframe(df.head(15), use_container_width=True)


# =============================================================================
# MODÜL 3: İLAN TARAYICI & MANUEL EKLE
# =============================================================================
elif menu == "🌐 İlan Tarayıcı & Manuel Ekle":
    st.markdown('<div class="main-header">🌐 Resmi Kaynak Tarayıcı & Manuel İlan Girişi</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Resmi kurum web sitelerini tarayabilir veya harici resmi bir ilanı manuel olarak onay havuzuna ekleyebilirsiniz.</div>', unsafe_allow_html=True)

    tab_scan, tab_manual = st.tabs(["🔄 Otomatik Resmi Kaynak Taraması", "✍️ Manuel Resmi İlan Ekle"])

    with tab_scan:
        st.write("Sistem şu anda aşağıdaki doğrulanmış resmi kaynakları taramaktadır:")
        st.markdown("""
        *   **SBB Kamu İlan Portalı** (`kamuilan.sbb.gov.tr`) - *T.C. Cumhurbaşkanlığı Strateji ve Bütçe Başkanlığı*
        *   **T.C. Resmi Gazete** (`resmigazete.gov.tr`) - *Çeşitli İlanlar (Kamu Alımları)*
        """)

        if st.button("🚀 Resmi Siteleri Şimdi Tara ve Yeni İlanları Çek", type="primary", use_container_width=True):
            with st.spinner("Resmi kurumlar taranıyor, mükerrer kayıtlar eleniyor..."):
                sm = ScraperManager()
                result = sm.run_all()
                st.success(
                    f"Tarama Tamamlandı!\n\n"
                    f"• **Toplam Bulunan:** {result['total_found']}\n"
                    f"• **Yeni Eklenen:** {result['new_added']}\n"
                    f"• **Mükerrer Atlanan:** {result['duplicates']}"
                )
                if result["errors"]:
                    st.warning("Bazı kaynaklarda uyarılar oluştu:")
                    for err in result["errors"]:
                        st.caption(err)

    with tab_manual:
        st.subheader("Manuel İlan Ekleme Formu")
        with st.form("manual_job_form"):
            m_inst = st.text_input("Kurum Adı", placeholder="Örn: Sağlık Bakanlığı")
            m_title = st.text_input("İlan Başlığı", placeholder="Örn: Sağlık Bakanlığı 8.000 Sürekli İşçi Alım İlanı")
            m_url = st.text_input("Resmi Kaynak Linki (.gov.tr)", placeholder="https://...")
            m_content = st.text_area("İlan Metni / Duyuru Detayı", placeholder="İlandaki başvuru şartları ve detaylar...")

            m_submit = st.form_submit_button("Havuzuna Ekle ve AI ile İşle")
            if m_submit:
                if not m_title or not m_url:
                    st.error("Lütfen başlık ve resmi kaynak linkini doldurunuz.")
                else:
                    with get_db() as db:
                        new_job = JobAnnouncement(
                            title=m_title,
                            institution=m_inst or "Kamu Kurumu",
                            source_name="Manuel Giriş",
                            source_url=m_url,
                            official_doc_url=m_url,
                            raw_content=m_content,
                            is_verified=m_url.lower().endswith(".gov.tr") or ".gov.tr" in m_url.lower(),
                            status=JobStatus.PENDING_APPROVAL,
                            created_at=datetime.utcnow()
                        )
                        db.add(new_job)
                        db.commit()
                        new_id = new_job.id

                    # AI ile işle
                    processor = AIProcessor()
                    processor.process_job(new_id)

                    st.success(f"İlan #{new_id} başarıyla eklendi ve AI tarafından işlendi! 'Onay Havuzu' sekmesinden kontrol edebilirsiniz.")


# =============================================================================
# MODÜL: TELEGRAM KANAL BÜYÜTME & AKTİF ÜYE ÇEKME
# =============================================================================
elif menu == "🚀 Telegram Kanal Büyütme & Üye Çekme":
    try:
        from modules.telegram_growth import telegram_buyutme_modulu
        telegram_buyutme_modulu()
    except Exception as ex:
        st.error(f"Telegram Büyütme Modülü yüklenirken bir hata oluştu: {ex}")
        st.info("Kütüphanelerin güncellenmesi için sağ alttaki 'Manage app' -> 'Reboot app' butonuna tıklayabilirsiniz.")

# =============================================================================
# MODÜL: INSTAGRAM BÜYÜME & VİRAL OTOMASYON MERKEZİ
# =============================================================================
elif menu == "📸 Instagram Büyüme & Otomasyon Merkezi":
    try:
        import importlib
        import modules.instagram_growth as ig_mod
        importlib.reload(ig_mod)
        ig_mod.render_instagram_growth_tab()
    except Exception as ex:
        st.error(f"Instagram Büyüme Modülü yüklenirken bir hata oluştu: {ex}")
        st.exception(ex)


# =============================================================================
# MODÜL 4: SİSTEM & APİ AYARLARI (SETTINGS & TEST PLAYGROUND)
# =============================================================================
elif menu == "⚙️ Sistem & API Ayarları":
    st.markdown('<div class="main-header">⚙️ Sistem ve API Ayarları & Test Laboratuvarı</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-header">API anahtarlarınızı girip test edebilir, model yanıtlarını anlık olarak ölçebilir '
        've sistemin kullanacağı aktif yapay zeka motorunu seçebilirsiniz.</div>',
        unsafe_allow_html=True,
    )

    current_settings = get_all_system_settings()

    cur_active_ai = current_settings.get("ACTIVE_AI_PROVIDER", {}).get("value", "NVIDIA NIM")
    cur_nvidia_key = current_settings.get("NVIDIA_API_KEY", {}).get("value", "")
    cur_nvidia_model = current_settings.get("NVIDIA_MODEL", {}).get("value", "meta/llama-3.2-11b-vision-instruct")
    
    cur_groq_key = current_settings.get("GROQ_API_KEY", {}).get("value", "")
    cur_groq_model = current_settings.get("GROQ_MODEL", {}).get("value", "llama-3.3-70b-versatile")
    
    cur_custom_url = current_settings.get("CUSTOM_LLM_BASE_URL", {}).get("value", "https://api.deepseek.com/v1")
    cur_custom_key = current_settings.get("CUSTOM_LLM_API_KEY", {}).get("value", "")
    cur_custom_model = current_settings.get("CUSTOM_LLM_MODEL", {}).get("value", "deepseek-chat")

    cur_tele_token = current_settings.get("TELEGRAM_BOT_TOKEN", {}).get("value", "")
    cur_tele_channel = current_settings.get("TELEGRAM_CHANNEL_ID", {}).get("value", "@kamupersonelrehberi")
    cur_wa_token = current_settings.get("WHATSAPP_ACCESS_TOKEN", {}).get("value", "")
    cur_wa_phone_id = current_settings.get("WHATSAPP_PHONE_NUMBER_ID", {}).get("value", "")
    cur_wa_whapi = current_settings.get("WHATSAPP_WHAPI_TOKEN", {}).get("value", "")
    cur_green_id = current_settings.get("GREEN_API_ID", {}).get("value", "")
    cur_green_tok = current_settings.get("GREEN_API_TOKEN", {}).get("value", "")
    cur_ig_token = current_settings.get("INSTAGRAM_ACCESS_TOKEN", {}).get("value", "")
    cur_ig_acc_id = current_settings.get("INSTAGRAM_ACCOUNT_ID", {}).get("value", "")
    cur_fb_page_id = current_settings.get("FACEBOOK_PAGE_ID", {}).get("value", "1386232411235219")
    cur_fb_token = current_settings.get("FACEBOOK_ACCESS_TOKEN", {}).get("value", "")
    cur_default_theme = current_settings.get("DEFAULT_CARD_THEME", {}).get("value", "ROYAL_CRIMSON")

    # Sekmeli Yapı: 1. Ayarlar Formu, 2. Meta Token Asistanı, 3. İnteraktif Model Test Alanı
    tab_settings, tab_meta, tab_test = st.tabs([
        "⚙️ Genel Yapılandırma ve Anahtarlar",
        "🔑 Meta (Instagram & Facebook) Token Asistanı",
        "🧪 İnteraktif Model Yanıt Test Alanı (Playground)"
    ])

    with tab_settings:
        with st.form("settings_form"):
            # 1. Aktif AI Sağlayıcı Tercihi
            st.subheader("🎯 Aktif Yapay Zeka Motoru Tercihi")
            ai_providers = ["NVIDIA NIM", "Groq Cloud", "Özel / OpenAI Uyumlu"]
            p_idx = ai_providers.index(cur_active_ai) if cur_active_ai in ai_providers else 0
            in_active_provider = st.selectbox(
                "İlan Analizinde Kullanılacak Aktif Sağlayıcı",
                ai_providers,
                index=p_idx,
                help="Sistem ilanları zenginleştirirken öncelikli olarak bu servisi kullanır."
            )

            st.markdown("---")
            # 2. NVIDIA NIM Ayarları
            st.subheader("🟢 NVIDIA NIM Cloud (nvapi-...)")
            st.caption("NVIDIA AI Foundation modelleri (Llama 3.2, Nemotron vb.) için yüksek hızlı çıkarım motoru.")
            
            in_nvidia_key = st.text_input(
                "NVIDIA API Key",
                value=cur_nvidia_key,
                type="password",
                help="nvapi- ile başlayan NVIDIA NIM API anahtarınız."
            )
            
            nvidia_models = [
                "meta/llama-3.2-11b-vision-instruct",
                "meta/llama-3.2-90b-vision-instruct",
                "deepseek-ai/deepseek-v4.1-flash",
                "mistralai/mixtral-8x22b-v0.1",
            ]
            nv_idx = nvidia_models.index(cur_nvidia_model) if cur_nvidia_model in nvidia_models else 0
            in_nvidia_model = st.selectbox(
                "NVIDIA Modeli",
                nvidia_models,
                index=nv_idx,
                help="Önerilen: meta/llama-3.2-11b-vision-instruct (Ultra hızlı ve stabil Türkçe yanıt)"
            )

            st.markdown("---")
            # 3. Groq Cloud Ayarları
            st.subheader("⚡ Groq Cloud (gsk_...)")
            in_groq_key = st.text_input(
                "Groq API Key",
                value=cur_groq_key,
                type="password",
                help="gsk_ ile başlayan Groq Cloud API anahtarınız."
            )
            groq_models = [
                "llama-3.3-70b-versatile",
                "llama-3.1-70b-versatile",
                "llama3-70b-8192",
                "llama3-8b-8192",
                "mixtral-8x7b-32768",
            ]
            g_idx = groq_models.index(cur_groq_model) if cur_groq_model in groq_models else 0
            in_groq_model = st.selectbox("Groq Modeli", groq_models, index=g_idx)

            st.markdown("---")
            # 4. Özel / OpenAI Uyumlu Sağlayıcı
            st.subheader("🌐 Özel / OpenAI Uyumlu Sağlayıcı (DeepSeek, OpenRouter, Ollama vb.)")
            c_col1, c_col2 = st.columns(2)
            with c_col1:
                in_custom_url = st.text_input("Base URL", value=cur_custom_url, placeholder="https://api.deepseek.com/v1")
                in_custom_key = st.text_input("API Key", value=cur_custom_key, type="password")
            with c_col2:
                in_custom_model = st.text_input("Model Adı", value=cur_custom_model, placeholder="deepseek-chat")

            st.markdown("---")
            # 5. Görsel Kart Tasarım & Renk Teması Tercihi
            st.subheader("🎨 Sosyal Medya Afiş Tasarım & Renk Teması")
            st.caption("Otomatik otopilot paylaşımlarında ve yeni üretilen kartlarda kullanılacak varsayılan görsel stil.")
            theme_keys = list(CARD_THEMES.keys())
            th_idx = theme_keys.index(cur_default_theme) if cur_default_theme in theme_keys else 0
            in_default_theme = st.selectbox(
                "Varsayılan Afiş Tasarım Teması",
                theme_keys,
                index=th_idx,
                format_func=lambda k: f"{CARD_THEMES[k]['name']} — {CARD_THEMES[k]['desc']}",
                help="Kartın arkaplan degradesi, ışıltı rengi, etiket tonları ve çerçeve tipini belirler."
            )

            st.markdown("---")
            # 6. Sosyal Medya Ayarları
            st.subheader("📢 Sosyal Medya Dağıtım Kanalları")
            s_col1, s_col2 = st.columns(2)
            with s_col1:
                st.markdown("**Telegram**")
                in_tele_token = st.text_input("Bot API Token", value=cur_tele_token, type="password")
                in_tele_channel = st.text_input("Kanal ID (@kanal)", value=cur_tele_channel)

                st.markdown("**Instagram**")
                in_ig_token = st.text_input("Instagram User Access Token", value=cur_ig_token, type="password")
                in_ig_acc_id = st.text_input("Instagram Account ID", value=cur_ig_acc_id)

                st.markdown("**Facebook Sayfası**")
                in_fb_page_id = st.text_input("Facebook Page ID", value=cur_fb_page_id or "1386232411235219")
                in_fb_token = st.text_input("Facebook Page Access Token (Boşsa Instagram ile ortak token kullanılır)", value=cur_fb_token, type="password")

            with s_col2:
                st.markdown("**WhatsApp Kanal Dağıtım Ayarları**")
                in_wa_channel_url = st.text_input(
                    "WhatsApp Kanal Linki",
                    value=cur_wa_phone_id or "https://whatsapp.com/channel/0029Vb8mg1DFsn0nmDsQxF1K",
                    help="Resmi kamu alımlarının yayınlanacağı WhatsApp Kanalınızın davet linki."
                )
                in_wa_whapi_token = st.text_input(
                    "Whapi.cloud Token (Önerilen Bulut REST API)",
                    value=cur_wa_whapi,
                    type="password",
                    help="Whapi.cloud panelinden alabileceğiniz API anahtarı. Bulut ortamında (Streamlit Cloud) tarayıcı açmadan direkt kanala ve gruplara mesaj göndermenizi sağlar."
                )
                c_gw1, c_gw2 = st.columns(2)
                with c_gw1:
                    in_green_id = st.text_input("Green-API Instance ID", value=cur_green_id)
                with c_gw2:
                    in_green_tok = st.text_input("Green-API Token", value=cur_green_tok, type="password")

                in_wa_token = st.text_input(
                    "WhatsApp Cloud Token (İsteğe Bağlı Meta API)",
                    value=cur_wa_token,
                    type="password"
                )

            st.markdown("---")
            save_btn = st.form_submit_button("💾 TÜM AYARLARI VERİTABANINA KAYDET", type="primary", use_container_width=True)

            if save_btn:
                set_system_setting("ACTIVE_AI_PROVIDER", in_active_provider, is_secret=False)
                set_system_setting("NVIDIA_API_KEY", in_nvidia_key, is_secret=True)
                set_system_setting("NVIDIA_MODEL", in_nvidia_model, is_secret=False)
                set_system_setting("GROQ_API_KEY", in_groq_key, is_secret=True)
                set_system_setting("GROQ_MODEL", in_groq_model, is_secret=False)
                set_system_setting("CUSTOM_LLM_BASE_URL", in_custom_url, is_secret=False)
                set_system_setting("CUSTOM_LLM_API_KEY", in_custom_key, is_secret=True)
                set_system_setting("CUSTOM_LLM_MODEL", in_custom_model, is_secret=False)
                set_system_setting("DEFAULT_CARD_THEME", in_default_theme, is_secret=False)
                set_system_setting("TELEGRAM_BOT_TOKEN", in_tele_token, is_secret=True)
                set_system_setting("TELEGRAM_CHANNEL_ID", in_tele_channel, is_secret=False)
                set_system_setting("WHATSAPP_WHAPI_TOKEN", in_wa_whapi_token, is_secret=True)
                set_system_setting("GREEN_API_ID", in_green_id, is_secret=False)
                set_system_setting("GREEN_API_TOKEN", in_green_tok, is_secret=True)
                set_system_setting("WHATSAPP_ACCESS_TOKEN", in_wa_token, is_secret=True)
                set_system_setting("WHATSAPP_PHONE_NUMBER_ID", in_wa_channel_url, is_secret=False)
                set_system_setting("WHATSAPP_CHANNEL_URL", in_wa_channel_url, is_secret=False)
                set_system_setting("INSTAGRAM_ACCESS_TOKEN", in_ig_token, is_secret=True)
                set_system_setting("INSTAGRAM_ACCOUNT_ID", in_ig_acc_id, is_secret=False)
                set_system_setting("FACEBOOK_PAGE_ID", in_fb_page_id, is_secret=False)
                final_fb_tok = in_fb_token.strip() if in_fb_token.strip() else in_ig_token
                set_system_setting("FACEBOOK_ACCESS_TOKEN", final_fb_tok, is_secret=True)
                st.success("✅ Tüm ayarlar veritabanına başarıyla kaydedildi!")
                st.rerun()

        # =========================================================================
        # GÖRSEL TEMA VİTRİNİ & CANLI ÖNİZLEME GALERİSİ
        # =========================================================================
        st.markdown("---")
        st.subheader("🎨 Görsel Tema Vitrini & Canlı Önizleme Galerisi")
        st.markdown(
            "Kamu Personel Rehberi görsel motoru, tek düze ve basit afişler yerine 5 farklı yüksek kontrastlı, "
            "şık ve modern tema ile kart üretir. Beğendiğiniz temayı tek tıkla varsayılan yapabilirsiniz."
        )

        cols_theme = st.columns(len(CARD_THEMES))
        gen_preview = JobCardGenerator()
        for idx, (t_key, t_info) in enumerate(CARD_THEMES.items()):
            with cols_theme[idx]:
                st.markdown(f"**{t_info['name']}**")
                st.caption(t_info['desc'])
                sample_p = gen_preview.get_theme_sample(t_key)
                if sample_p.exists():
                    st.image(str(sample_p), use_container_width=True)
                
                is_current = (cur_default_theme == t_key)
                if is_current:
                    st.success("Aktif Varsayılan")
                else:
                    if st.button("Varsayılan Yap", key=f"set_def_theme_{t_key}", use_container_width=True):
                        set_system_setting("DEFAULT_CARD_THEME", t_key, is_secret=False)
                        st.success(f"Varsayılan tema {t_info['name']} olarak ayarlandı!")
                        st.rerun()

        # =========================================================================
        # SOSYAL MEDYA CANLI BAĞLANTI & TEST PANELİ (FORM DIŞINDA)
        # =========================================================================
        st.markdown("---")
        st.subheader("🌐 Sosyal Medya & Kanal Canlı Bağlantı Kontrol Merkezi")
        st.caption("Bağlantılarınızı canlı olarak doğrulayabilir, WhatsApp Web QR oturumunu başlatabilir veya test gönderileri yapabilirsiniz.")

        c_tg, c_ig, c_fb, c_wa = st.columns(4)

        # 1. TELEGRAM
        with c_tg:
            st.markdown("##### ✈️ Telegram Kanalı")
            if cur_tele_token and cur_tele_channel:
                st.success(f"🟢 Yapılandırılmış: `{cur_tele_channel}`")
            else:
                st.warning("🟠 Token veya Kanal Eksik")
            
            if st.button("🧪 Telegram Bağlantısını Test Et", key="btn_test_tg", use_container_width=True):
                with st.spinner("Telegram doğrulanıyor..."):
                    tp = TelegramPublisher()
                    ok, msg = tp.test_connection()
                    if ok:
                        st.success(f"✅ {msg}")
                    else:
                        st.error(f"❌ {msg}")

        # 2. INSTAGRAM
        with c_ig:
            st.markdown("##### 📸 Instagram Hesabı")
            if cur_ig_token and cur_ig_acc_id:
                st.success(f"🟢 Hesap ID: `{cur_ig_acc_id}`")
            else:
                st.warning("🟠 Token veya Hesap ID Eksik")

            if st.button("🧪 Instagram Bağlantısını Test Et", key="btn_test_ig", use_container_width=True):
                with st.spinner("Instagram Graph API doğrulanıyor..."):
                    ip = InstagramPublisher()
                    ok, msg = ip.test_connection()
                    if ok:
                        st.success(f"✅ {msg}")
                    else:
                        st.error(f"❌ {msg}")

        # 3. FACEBOOK SAYFASI
        with c_fb:
            st.markdown("##### 📘 Facebook Sayfası")
            cur_fb_page_id = current_settings.get("FACEBOOK_PAGE_ID", {}).get("value", "1386232411235219")
            if cur_fb_page_id and (cur_ig_token or current_settings.get("FACEBOOK_ACCESS_TOKEN", {}).get("value")):
                st.success(f"🟢 Sayfa ID: `{cur_fb_page_id}`")
            else:
                st.warning("🟠 Sayfa ID veya Token Eksik")

            if st.button("🧪 Facebook Bağlantısını Test Et", key="btn_test_fb", use_container_width=True):
                with st.spinner("Facebook Graph API doğrulanıyor..."):
                    fp = FacebookPublisher()
                    ok, msg = fp.test_connection()
                    if ok:
                        st.success(f"✅ {msg}")
                    else:
                        st.error(f"❌ {msg}")

        # 4. WHATSAPP AĞ GEÇİDİ & KANAL
        with c_wa:
            st.markdown("##### 💬 WhatsApp Kanalı")
            wp = WhatsAppPublisher()
            is_wa_online = wp.is_logged_in()
            active_mode = wp.mode

            if active_mode == "whapi":
                st.success("🟢 Whapi.cloud API Gateway Aktif")
                st.caption(f"Hedef Kanal: `{wp.channel_url}`")
                if st.button("🧪 Kanala Test Gönder (Whapi)", key="btn_test_wa_whapi", use_container_width=True):
                    with st.spinner("Whapi üzerinden test mesajı iletiliyor..."):
                        ok, msg = wp.send_test_message()
                        if ok: st.success(f"✅ {msg}")
                        else: st.error(f"❌ {msg}")

            elif active_mode == "green_api":
                st.success("🟢 Green-API Gateway Aktif")
                st.caption(f"Instance: `{wp.green_instance_id}` | Kanal: `{wp.channel_url}`")
                if st.button("🧪 Kanala Test Gönder (Green-API)", key="btn_test_wa_green", use_container_width=True):
                    with st.spinner("Green-API üzerinden test mesajı iletiliyor..."):
                        ok, msg = wp.send_test_message()
                        if ok: st.success(f"✅ {msg}")
                        else: st.error(f"❌ {msg}")

            elif active_mode == "cloud":
                st.success("🟢 Meta Cloud API Aktif")
                if st.button("🧪 Test Mesajı Gönder (Cloud API)", key="btn_test_wa_cloud", use_container_width=True):
                    ok, msg = wp.send_test_message()
                    if ok: st.success(f"✅ {msg}")
                    else: st.error(f"❌ {msg}")

            elif is_wa_online:
                st.success("🟢 WhatsApp Web Oturumu Aktif")
                st.caption(f"Kanal: `{wp.web.get_channel_url()}`")
                
                col_w1, col_w2 = st.columns(2)
                with col_w1:
                    if st.button("🧪 Kanala Test Gönder", key="btn_test_wa", use_container_width=True):
                        with st.spinner("WhatsApp kanalına test mesajı iletiliyor..."):
                            ok, msg = wp.send_test_message()
                            if ok:
                                st.success(f"✅ {msg}")
                            else:
                                st.error(f"❌ {msg}")
                with col_w2:
                    if st.button("🚪 Oturumu Kapat", key="btn_logout_wa", use_container_width=True):
                        wp.logout()
                        st.info("WhatsApp oturumu kapatıldı.")
                        st.rerun()

                debug_img_path = Path("graphics/assets/wa_debug.png")
                if debug_img_path.exists():
                    with st.expander("🔍 WhatsApp Web Ekran Görüntüsü / Canlı Durum Teşhisi"):
                        st.image(str(debug_img_path), caption="Son WhatsApp Web Ekran Görüntüsü", use_container_width=True)
            else:
                st.warning("🟠 Oturum Kapalı / QR Bekleniyor")
                st.caption(f"Hedef Kanal: `{cur_wa_phone_id or '0029Vb8mg1DFsn0nmDsQxF1K'}`")

                if st.button("📲 WhatsApp Web Girişi Yap (QR Aç)", key="btn_login_wa", type="primary", use_container_width=True):
                    qr_box = st.empty()
                    status_box = st.empty()
                    status_box.info("⏳ WhatsApp Web başlatılıyor ve QR kod üretiliyor, lütfen birkaç saniye bekleyin...")

                    def render_qr(qr_path_str):
                        import base64
                        try:
                            with open(qr_path_str, "rb") as f_img:
                                b64_str = base64.b64encode(f_img.read()).decode("utf-8")
                            qr_box.markdown(
                                f"""
                                <div style="background: #ffffff; padding: 20px; border-radius: 16px; width: 330px; margin: 10px auto; box-shadow: 0 8px 30px rgba(0,0,0,0.5); text-align: center;">
                                    <img src="data:image/png;base64,{b64_str}" style="width: 290px; height: 290px; display: block; margin: 0 auto; border-radius: 8px;" />
                                    <div style="color: #0f172a; font-size: 13px; font-weight: 700; margin-top: 12px; font-family: system-ui, -apple-system, sans-serif;">
                                        📱 WhatsApp &gt; Bağlı Cihazlar &gt; Cihaz Bağla
                                    </div>
                                </div>
                                """,
                                unsafe_allow_html=True
                            )
                        except Exception:
                            qr_box.image(qr_path_str, width=300)
                        status_box.warning("⚡ Yüksek Çözünürlüklü QR Kod hazır! Telefonunuzdan (WhatsApp > Bağlı Cihazlar) okutun.")

                    ok, msg = wp.start_login_window(max_wait=90, on_qr_ready=render_qr)
                    if ok:
                        qr_box.empty()
                        status_box.success(f"🎉 {msg}")
                        time.sleep(1)
                        st.rerun()
                    else:
                        status_box.error(f"❌ {msg}")

                qr_file = Path("graphics/assets/whatsapp_qr.png")
                if qr_file.exists():
                    import base64
                    try:
                        with open(qr_file, "rb") as f_img:
                            b64_str = base64.b64encode(f_img.read()).decode("utf-8")
                        st.markdown(
                            f"""
                            <div style="background: #ffffff; padding: 15px; border-radius: 14px; width: 280px; margin: 10px auto; box-shadow: 0 4px 20px rgba(0,0,0,0.3); text-align: center;">
                                <img src="data:image/png;base64,{b64_str}" style="width: 250px; height: 250px; display: block; margin: 0 auto; border-radius: 6px;" />
                                <div style="color: #334155; font-size: 12px; font-weight: 600; margin-top: 8px; font-family: system-ui, sans-serif;">
                                    Son üretilen QR Kod
                                </div>
                            </div>
                            """,
                            unsafe_allow_html=True
                        )
                    except Exception:
                        st.image(str(qr_file), width=260)

            # Kanal Linki Doğrulama ve Sıfırlama Butonu
            st.markdown("---")
            if st.button("🔗 Doğrulanmış Kanal Linkini Onar (0029Vb8mg1DFsn0nmDsQxF1K)", key="btn_fix_channel_url", use_container_width=True):
                fixed_url = "https://whatsapp.com/channel/0029Vb8mg1DFsn0nmDsQxF1K"
                set_system_setting("WHATSAPP_CHANNEL_URL", fixed_url)
                set_system_setting("WHATSAPP_PHONE_NUMBER_ID", fixed_url)
                st.success("✅ Kanal linki başarıyla '0029Vb8mg1DFsn0nmDsQxF1K' olarak ayarlandı!")
                st.rerun()

    # =========================================================================
    # TAB 2: META (INSTAGRAM & FACEBOOK) TOKEN ASİSTANI
    # =========================================================================
    with tab_meta:
        st.subheader("🔑 Meta (Instagram Business & Facebook Sayfası) Token Asistanı")
        st.markdown(
            "Meta Graph API belirteçlerinin süresini denetleyin, kısa ömürlü belirteçleri **60 günlük veya kalıcı** "
            "belirteçlere dönüştürün ve sayfanıza bağlı Instagram hesaplarını tek tıkla otomatik bağlayın."
        )

        col_m_diag, col_m_help = st.columns([3, 2])
        with col_m_diag:
            st.markdown("##### 1. Canlı Belirteç Teşhis ve Sağlık Kontrolü")
            inspect_tok = st.text_input(
                "İncelenecek Meta Access Token (Boş bırakılırsa kayıtlı belirteç test edilir)",
                type="password",
                key="input_inspect_meta_token"
            )
            target_t = inspect_tok.strip() if inspect_tok.strip() else cur_ig_token

            if st.button("🔍 Belirteci Derinlemesine İncele & Doğrula", key="btn_inspect_token", use_container_width=True):
                with st.spinner("Meta Graph API ile doğrulanıyor..."):
                    diag_res = MetaHelper.diagnose_token(target_t)
                    if diag_res["is_valid"]:
                        st.success(f"✅ {diag_res['message']} | Tür: {diag_res.get('type')}")
                    elif diag_res.get("status_code") == "EXPIRED":
                        st.error(f"❌ {diag_res['message']}")
                        st.caption(f"Meta Ham Yanıtı: `{diag_res.get('raw_error')}`")
                    else:
                        st.warning(f"⚠️ {diag_res['message']}")

            st.markdown("---")
            st.markdown("##### 2. Otomatik Varlık Keşfi (Sayfa & Instagram ID Bulucu)")
            st.caption("Belirtecinize bağlı tüm Facebook Sayfalarını ve Instagram İşletme Hesaplarını otomatik tespit eder.")
            if st.button("🚀 Bağlı Sayfa ve Instagram Hesaplarını Keşfet", key="btn_discover_assets", use_container_width=True):
                with st.spinner("Hesaplar taranıyor..."):
                    disc = MetaHelper.discover_connected_assets(target_t)
                    if disc.get("error"):
                        st.error(f"Hata: {disc['error']}")
                    else:
                        pages = disc.get("pages", [])
                        igs = disc.get("instagram_accounts", [])
                        st.success(f"Bulunan Facebook Sayfası: {len(pages)} adet | Instagram Hesabı: {len(igs)} adet")
                        
                        if igs:
                            for ig in igs:
                                st.info(f"📸 **@{ig['username']}** ({ig.get('name')}) — Instagram ID: `{ig['id']}` (Sayfa: {ig['page_name']})")
                                if st.button(f"✅ @{ig['username']} Hesabını Sisteme Tanımla", key=f"apply_ig_{ig['id']}"):
                                    set_system_setting("INSTAGRAM_ACCOUNT_ID", str(ig['id']))
                                    set_system_setting("FACEBOOK_PAGE_ID", str(ig['page_id']))
                                    st.success(f"Instagram ID `{ig['id']}` ve Facebook Page ID `{ig['page_id']}` kaydedildi!")
                                    st.rerun()
                        elif pages:
                            for p in pages:
                                st.info(f"📘 **{p['name']}** — Sayfa ID: `{p['id']}`")
                                if st.button(f"✅ {p['name']} Sayfasını Tanımla", key=f"apply_pg_{p['id']}"):
                                    set_system_setting("FACEBOOK_PAGE_ID", str(p['id']))
                                    if p.get("page_token"):
                                        set_system_setting("FACEBOOK_ACCESS_TOKEN", p["page_token"], is_secret=True)
                                    st.success(f"Facebook Sayfası `{p['name']}` kaydedildi!")
                                    st.rerun()
                        else:
                            st.warning("Bu belirtece bağlı yönetici olduğunuz bir Facebook Sayfası bulunamadı.")

        with col_m_help:
            st.markdown("##### 3. 60 Günlük / Kalıcı Belirteç Dönüştürücü")
            st.caption("Meta Graph API Explorer'dan aldığınız 1-2 saatlik belirteci 60 güne uzatın.")
            
            with st.form("long_lived_token_form"):
                in_app_id = st.text_input("Meta App ID", placeholder="Örn: 123456789012345")
                in_app_sec = st.text_input("Meta App Secret", placeholder="Örn: a1b2c3d4e5f6...", type="password")
                in_short_tok = st.text_input("Kısa Ömürlü Token", value=target_t, type="password")
                
                btn_convert = st.form_submit_button("🚀 60 Günlük Belirtece Dönüştür & Kaydet", type="primary", use_container_width=True)
                if btn_convert:
                    with st.spinner("Meta OAuth ile dönüştürülüyor..."):
                        ok_ex, msg_ex, new_tok = MetaHelper.exchange_to_long_lived_token(in_short_tok, in_app_id, in_app_sec)
                        if ok_ex and new_tok:
                            set_system_setting("INSTAGRAM_ACCESS_TOKEN", new_tok, is_secret=True)
                            set_system_setting("FACEBOOK_ACCESS_TOKEN", new_tok, is_secret=True)
                            st.success(f"🎉 {msg_ex}")
                            st.cache_data.clear()
                            st.rerun()
                        else:
                            st.error(f"❌ {msg_ex}")

            st.markdown("""
            > **İpucu:** Uzun ömürlü belirteç aldığınızda, sistem Facebook Sayfa belirtecinizi **hiç süresi dolmayan (kalıcı)** modda kullanabilir.
            """)

    # =========================================================================
    # TAB 3: İNTERAKTİF MODEL TEST ALANI (PLAYGROUND)
    # =========================================================================
    with tab_test:
        st.subheader("🧪 Canlı Yapay Zeka Model Test Laboratuvarı")
        st.markdown(
            "API anahtarınızı girdiğinizde modelin gerçekten yanıt verip vermediğini, hızını ve Türkçe kalitesini "
            "buradan anlık olarak test edebilirsiniz."
        )

        test_provider = st.selectbox(
            "Test Edilecek Servis",
            ["NVIDIA NIM", "Groq Cloud", "Özel / OpenAI Uyumlu"],
            index=0,
            key="test_provider_select"
        )

        # Seçilen servise göre anlık ayarları göster
        if test_provider == "NVIDIA NIM":
            t_key = get_system_setting("NVIDIA_API_KEY", cur_nvidia_key)
            t_model = get_system_setting("NVIDIA_MODEL", cur_nvidia_model)
            t_url = "https://integrate.api.nvidia.com/v1"
        elif test_provider == "Groq Cloud":
            t_key = get_system_setting("GROQ_API_KEY", cur_groq_key)
            t_model = get_system_setting("GROQ_MODEL", cur_groq_model)
            t_url = "https://api.groq.com/openai/v1"
        else:
            t_key = get_system_setting("CUSTOM_LLM_API_KEY", cur_custom_key)
            t_model = get_system_setting("CUSTOM_LLM_MODEL", cur_custom_model)
            t_url = get_system_setting("CUSTOM_LLM_BASE_URL", cur_custom_url)

        col_cfg1, col_cfg2 = st.columns([1, 1])
        with col_cfg1:
            st.info(f"**Test Edilen Model:** `{t_model}`\n\n**API Uç Noktası:** `{t_url}`")
        with col_cfg2:
            st.info(f"**API Anahtarı Durumu:** {'✅ Girilmiş' if t_key else '❌ Boş / Eksik'}")

        test_prompt = st.text_area(
            "Modele Gönderilecek Test Sorusu / Prompt",
            value="Merhaba! Ben Kamu Personel Rehberi yöneticisiyim. Sistemi başarıyla bağladık mı? Kendini ve modelini kısaca tanıt.",
            height=100
        )

        if st.button("🚀 MODELİ ŞİMDİ TEST ET VE YANIT AL", type="primary", use_container_width=True):
            if not t_key:
                st.error("Lütfen önce bu servis için geçerli bir API anahtarı giriniz.")
            else:
                with st.spinner(f"{test_provider} ({t_model}) modeline istek gönderiliyor..."):
                    llm = LLMClient()
                    success, reply, elapsed = llm.test_model_connection(
                        provider=test_provider,
                        api_key=t_key,
                        model=t_model,
                        base_url=t_url,
                        custom_prompt=test_prompt
                    )

                    if success:
                        st.success(f"🎉 BAŞARILI! Modelden yanıt alındı! (⚡ Hız: {elapsed} saniye)")
                        st.markdown("##### 💬 Modelin Yanıtı:")
                        st.info(reply)
                    else:
                        st.error(f"❌ BAĞLANTI HATASI (Süre: {elapsed} s)")
                        st.warning(reply)
