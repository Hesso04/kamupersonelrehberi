"""
Telegram Kanal/Grup Büyütme ve Aktif Üye Çekme Modülü (Telethon MTProto)
======================================================================
Bu modül, Streamlit tabanlı yönetim panellerine entegre edilmek üzere tasarlanmıştır.

Özellikler:
1. Hesap Bağlantısı: Telethon MTProto Client ile SMS ve 2FA (Bulut Şifresi) destekli oturum.
2. Hedef Kitle Kazıma (Scrape): Rakip/hedef gruptan sadece son 24 saatte çevrimiçi olmuş
   (UserStatusOnline, UserStatusRecently) ve kullanıcı adı (@username) olan aktif üyeleri filtreleme.
3. Anti-Ban Korumalı Üye Ekleme (Add): Rastgele gecikmeler (random sleep), FloodWait otomatik bekleme,
   PeerFlood acil durdurma koruması ve tüm gizlilik engellerini atlayan hata yönetimi.
"""

import asyncio
import os
import random
import time
from datetime import datetime
from pathlib import Path
import threading
import queue
import concurrent.futures
from typing import List, Dict, Any, Optional

import pandas as pd
import streamlit as st
from telethon import TelegramClient
from telethon.errors import (
    ChatAdminRequiredError,
    ChannelPrivateError,
    FloodWaitError,
    PasswordHashInvalidError,
    PeerFloodError,
    PhoneCodeEmptyError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    PhoneNumberInvalidError,
    SessionPasswordNeededError,
    UserAlreadyParticipantError,
    UserChannelsTooMuchError,
    UserNotMutualContactError,
    UserPrivacyRestrictedError,
)
from telethon.tl.functions.channels import (
    InviteToChannelRequest,
    JoinChannelRequest,
    GetFullChannelRequest,
)
from telethon.tl.functions.messages import (
    AddChatUserRequest,
    ImportChatInviteRequest,
    CheckChatInviteRequest,
)
from telethon.tl.types import (
    Channel,
    Chat,
    User,
    InputPeerUser,
    UserStatusOnline,
    UserStatusRecently,
    UserStatusLastWeek,
    UserStatusLastMonth,
    UserStatusOffline,
)

# =============================================================================
# ASYNCIO / STREAMLIT DÖNGÜ YÖNETİMİ (UVICORN / ANYIO UYUMLU İZOLE THREAD)
# =============================================================================
SESSION_DIR = Path("data/sessions")
SESSION_DIR.mkdir(parents=True, exist_ok=True)
SESSION_FILE_PREFIX = str(SESSION_DIR / "telethon_growth_session")


class AsyncLoopThread:
    """Telethon için izole tek bir event loop thread'i çalıştırır. Uvicorn/AnyIO ile asla çakışmaz."""
    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run, daemon=True, name="TelethonLoopThread")
        self.thread.start()

    def _run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    @classmethod
    def get_loop(cls):
        with cls._lock:
            if cls._instance is None or not cls._instance.thread.is_alive():
                cls._instance = cls()
            return cls._instance.loop


def run_async(coro):
    """Asenkron coroutine'leri Streamlit ve AnyIO ortamında thread-safe çalıştırır."""
    loop = AsyncLoopThread.get_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=120)


# =============================================================================
# YARDIMCI TELETHON FONKSİYONLARI
# =============================================================================

# Global client cache — Streamlit rerun'larında yeni TelegramClient oluşturmak yerine
# mevcut olanı (hâlâ bağlı ve yetkili ise) yeniden kullanır.
_CLIENT_CACHE_LOCK = threading.Lock()
_CACHED_CLIENT: Optional[TelegramClient] = None


async def _get_or_create_client(api_id: int, api_hash: str) -> TelegramClient:
    """
    Thread-safe global client cache.
    Eğer daha önce oluşturulmuş ve hâlâ bağlı/yetkili bir client varsa onu döndürür.
    Yoksa veya bağlantı koptuysa yeni client oluşturur ve bağlar.
    """
    global _CACHED_CLIENT
    with _CLIENT_CACHE_LOCK:
        client = _CACHED_CLIENT

    if client is not None:
        try:
            if client.is_connected():
                return client
            else:
                await client.connect()
                return client
        except Exception:
            # Mevcut client kullanılamıyorsa yenisini oluştur
            pass

    loop = AsyncLoopThread.get_loop()
    new_client = TelegramClient(SESSION_FILE_PREFIX, api_id, api_hash.strip(), loop=loop)
    await new_client.connect()

    with _CLIENT_CACHE_LOCK:
        _CACHED_CLIENT = new_client
    return new_client


async def _check_active_authorization(api_id: int, api_hash: str):
    """Mevcut bir oturumun aktif ve yetkilendirilmiş olup olmadığını kontrol eder."""
    client = await _get_or_create_client(api_id, api_hash)
    is_auth = await client.is_user_authorized()
    user_info = None
    if is_auth:
        me = await client.get_me()
        user_info = {
            "id": me.id,
            "first_name": me.first_name or "",
            "last_name": me.last_name or "",
            "username": f"@{me.username}" if me.username else "Yok",
            "phone": me.phone or "Bilinmiyor",
        }
    return client, is_auth, user_info


def _clean_telegram_target(target_str: str) -> str:
    """Telegram link veya kullanıcı adı girdisini temizler."""
    t = target_str.strip()
    if "?" in t:
        t = t.split("?")[0]
    if "#" in t:
        t = t.split("#")[0]
    t = t.rstrip("/")
    for prefix in ["https://t.me/", "http://t.me/", "t.me/", "tg://resolve?domain="]:
        if t.startswith(prefix):
            t = t[len(prefix):]
    t = t.replace("joinchat/", "+")
    if t.startswith("@"):
        t = t[1:]
    return t.strip()


def _auto_restore_session():
    """
    Her Streamlit rerun'ında çağrılır.
    Eğer session_state'te oturum bilgisi yoksa ama diskte .session dosyası varsa
    ve API bilgileri mevcutsa, otomatik olarak oturumu yeniden bağlar.
    Bu sayede sayfa yenilendiğinde kullanıcı oturumunu kaybetmez.
    """
    # Zaten giriş yapılmışsa bir şey yapma
    if st.session_state.get("tg_is_auth", False) and st.session_state.get("tg_user_info"):
        # Client'ın hâlâ geçerli olup olmadığını kontrol et
        client = st.session_state.get("tg_client")
        if client is not None:
            try:
                if client.is_connected():
                    return  # Her şey yolunda
            except Exception:
                pass
        # Client kaybolmuş veya bağlantı kopmuş, yeniden bağlanmayı dene
        api_id = st.session_state.get("tg_saved_api_id")
        api_hash = st.session_state.get("tg_saved_api_hash")
        if api_id and api_hash:
            try:
                client, is_auth, user_info = run_async(
                    _check_active_authorization(int(api_id), api_hash)
                )
                if is_auth:
                    st.session_state.tg_client = client
                    st.session_state.tg_is_auth = True
                    st.session_state.tg_user_info = user_info
                    return
            except Exception:
                pass
        # Bağlanamazsa durumu sıfırla
        st.session_state.tg_is_auth = False
        st.session_state.tg_user_info = None
        st.session_state.tg_client = None
        return

    # Session state'te giriş yok — diskte .session var mı ve API bilgileri var mı?
    session_file = Path(SESSION_FILE_PREFIX + ".session")
    if not session_file.exists():
        return

    # Veritabanından veya session_state'ten API bilgilerini al
    api_id = st.session_state.get("tg_saved_api_id")
    api_hash = st.session_state.get("tg_saved_api_hash")

    if not api_id or not api_hash:
        try:
            from core.database import get_system_setting
            api_id = get_system_setting("TELEGRAM_API_ID", "")
            api_hash = get_system_setting("TELEGRAM_API_HASH", "")
        except Exception:
            return

    if not api_id or not api_hash:
        return

    try:
        client, is_auth, user_info = run_async(
            _check_active_authorization(int(api_id), api_hash)
        )
        if is_auth and user_info:
            st.session_state.tg_client = client
            st.session_state.tg_is_auth = True
            st.session_state.tg_user_info = user_info
            st.session_state.tg_saved_api_id = str(api_id)
            st.session_state.tg_saved_api_hash = str(api_hash)
    except Exception:
        # Sessiz hata — kullanıcı tekrar giriş yapabilir
        pass


# =============================================================================
# ANA STREAMLIT MODÜLÜ
# =============================================================================
def telegram_buyutme_modulu():
    """
    Telegram Kanal/Grup Büyütme ve Aktif Üye Çekme Ana Streamlit Bileşeni.
    Doğrudan ana Streamlit sayfasına veya menü sistemine import edilip çağrılabilir.
    """
    st.markdown("""
        <div style="background: linear-gradient(135deg, rgba(30, 41, 59, 0.7) 0%, rgba(15, 23, 42, 0.9) 100%);
                    border-radius: 14px; padding: 20px; margin-bottom: 24px; border: 1px solid rgba(56, 189, 248, 0.2);">
            <h2 style="color: #38bdf8; margin: 0; display: flex; align-items: center; gap: 10px;">
                🚀 Telegram Kanal & Grup Büyütme Motoru
            </h2>
            <p style="color: #94a3b8; margin: 6px 0 0 0; font-size: 0.95rem;">
                Telethon MTProto altyapısıyla hedef kitle kazıma (scraping) ve anti-ban korumalı güvenli üye ekleme otomasyonu.
            </p>
        </div>
    """, unsafe_allow_html=True)

    # Session State Başlatma — sadece eksik anahtarları ekle, var olanları ASLA sıfırlama
    _defaults = {
        "tg_client": None,
        "tg_is_auth": False,
        "tg_user_info": None,
        "tg_phone_code_hash": None,
        "tg_temp_phone": "",
        "tg_awaiting_code": False,
        "tg_awaiting_2fa": False,
        "scraped_users": [],
        "stop_adding_requested": False,
        "tg_saved_api_id": "",
        "tg_saved_api_hash": "",
    }
    for key, default_val in _defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default_val

    # Otomatik oturum yenileme — sayfa yenilendiğinde oturumu koru
    _auto_restore_session()

    # 3 Aşamalı Sekme Arayüzü
    tab_auth, tab_scrape, tab_add = st.tabs([
        "🔑 1. Hesap Bağlantısı",
        "🕵️ 2. Üye Kazıma (Scrape)",
        "➕ 3. Üye Ekleme (Add)"
    ])

    # =========================================================================
    # 1. AŞAMA: HESAP BAĞLANTISI (TELETHON MTPROTO GİRİŞİ)
    # =========================================================================
    with tab_auth:
        st.subheader("📱 Telegram MTProto Oturum Yönetimi")
        st.caption("Telegram hesabınızı API ID ve Hash ile güvenli şekilde bağlayın. Oturum yerel `data/sessions/` dizininde saklanır.")

        from core.database import get_system_setting, set_system_setting

        db_api_id = get_system_setting("TELEGRAM_API_ID", "37415817")
        db_api_hash = get_system_setting("TELEGRAM_API_HASH", "c383d82fa1164039d3735ce3285c368a")

        col_cred1, col_cred2 = st.columns(2)
        with col_cred1:
            api_id_input = st.text_input(
                "Telegram API ID",
                value=st.session_state.get("tg_saved_api_id", "") or db_api_id,
                placeholder="Örn: 37415817",
                help="my.telegram.org adresinden temin ettiğiniz sayısal API ID."
            )
        with col_cred2:
            api_hash_input = st.text_input(
                "Telegram API Hash",
                value=st.session_state.get("tg_saved_api_hash", "") or db_api_hash,
                type="password",
                placeholder="Örn: c383d82fa116...",
                help="my.telegram.org adresinden temin ettiğiniz 32 karakterlik API Hash."
            )

        # Bilgi Kılavuzu Accordion
        with st.expander("ℹ️ Telegram API ID ve Hash Nasıl Alınır? (Ücretsiz & Resmi)"):
            st.markdown("""
            1. [my.telegram.org](https://my.telegram.org) adresine gidin ve telefon numaranızla giriş yapın.
            2. **API development tools** seçeneğine tıklayın.
            3. Açılan formda uygulama ismi ve kısa başlık girip **Create application** butonuna basın.
            4. Karşınıza çıkan **App api_id** ve **App api_hash** değerlerini yukarıdaki alanlara kopyalayın.
            """)

        st.markdown("---")

        # Mevcut Oturum Kontrolü
        session_exists = Path(SESSION_FILE_PREFIX + ".session").exists()

        if st.session_state.tg_is_auth and st.session_state.tg_user_info:
            u = st.session_state.tg_user_info
            st.success(f"🟢 **Telegram Oturumu Aktif:** {u.get('first_name')} {u.get('last_name')} ({u.get('username')})")

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("👤 İsim", f"{u.get('first_name')} {u.get('last_name')}")
            c2.metric("🏷️ Kullanıcı Adı", u.get("username"))
            c3.metric("📞 Telefon", u.get("phone"))
            c4.metric("🆔 Telegram ID", u.get("id"))

            if st.button("🚪 Oturumu Kapat / Çıkış Yap", type="secondary"):
                try:
                    client = st.session_state.tg_client
                    if client:
                        try:
                            run_async(client.log_out())
                        except Exception:
                            try:
                                run_async(client.disconnect())
                            except Exception:
                                pass
                    session_file = Path(SESSION_FILE_PREFIX + ".session")
                    if session_file.exists():
                        session_file.unlink()
                    # Global cache'i temizle
                    global _CACHED_CLIENT
                    with _CLIENT_CACHE_LOCK:
                        _CACHED_CLIENT = None
                except Exception as ex:
                    st.warning(f"Oturum temizlenirken not: {ex}")
                st.session_state.tg_client = None
                st.session_state.tg_is_auth = False
                st.session_state.tg_user_info = None
                st.session_state.tg_awaiting_code = False
                st.session_state.tg_awaiting_2fa = False
                st.session_state.tg_saved_api_id = ""
                st.session_state.tg_saved_api_hash = ""
                st.success("Oturum başarıyla kapatıldı.")
                st.rerun()

        elif session_exists and api_id_input and api_hash_input and not st.session_state.tg_awaiting_code:
            st.info("💾 Cihazınızda kayıtlı bir Telegram oturumu bulundu. Otomatik bağlanma deneniyor...")
            # Otomatik bağlanma burada zaten _auto_restore_session() ile yapılmış durumda.
            # Eğer hâlâ bu noktadayız, demek ki oto-bağlanma başarısız olmuş.
            if st.button("🔄 Kayıtlı Oturumu Yeniden Bağla", type="primary"):
                try:
                    with st.spinner("Oturum doğrulanıyor..."):
                        client, is_auth, user_info = run_async(_check_active_authorization(int(api_id_input), api_hash_input))
                        if is_auth:
                            st.session_state.tg_client = client
                            st.session_state.tg_is_auth = True
                            st.session_state.tg_user_info = user_info
                            st.session_state.tg_saved_api_id = api_id_input
                            st.session_state.tg_saved_api_hash = api_hash_input
                            st.success("Giriş başarılı!")
                            st.rerun()
                        else:
                            st.warning("Kayıtlı oturumun süresi dolmuş veya geçersiz. Lütfen telefon numarasıyla tekrar giriş yapın.")
                except Exception as ex:
                    st.error(f"Bağlantı hatası: {str(ex)}")

        if not st.session_state.tg_is_auth:
            st.markdown("### 🔑 Telefon ile Giriş Yap")
            phone_input = st.text_input(
                "Telefon Numarası (Ülke kodu ile)",
                value=st.session_state.tg_temp_phone,
                placeholder="+905xxxxxxxxx",
                help="Telegram hesabınıza bağlı telefon numarası."
            )

            if not st.session_state.tg_awaiting_code and not st.session_state.tg_awaiting_2fa:
                if st.button("📩 Doğrulama Kodu Gönder", type="primary"):
                    if not api_id_input or not api_hash_input or not phone_input:
                        st.error("Lütfen API ID, API Hash ve Telefon Numarası alanlarını eksiksiz doldurun.")
                    else:
                        try:
                            with st.spinner("Telegram ile bağlantı kuruluyor ve SMS/Kod isteniyor..."):
                                client = run_async(_get_or_create_client(int(api_id_input), api_hash_input))
                                code_req = run_async(client.send_code_request(phone_input.strip()))

                                st.session_state.tg_client = client
                                st.session_state.tg_saved_api_id = api_id_input
                                st.session_state.tg_saved_api_hash = api_hash_input
                                st.session_state.tg_temp_phone = phone_input.strip()
                                st.session_state.tg_phone_code_hash = code_req.phone_code_hash
                                st.session_state.tg_awaiting_code = True
                                st.success("Doğrulama kodu Telegram uygulamanıza veya SMS ile gönderildi!")
                                st.rerun()
                        except PhoneNumberInvalidError:
                            st.error("Girdiğiniz telefon numarası geçersiz!")
                        except Exception as ex:
                            st.error(f"Kod gönderme hatası: {str(ex)}")

            # Kod Giriş Aşaması
            if st.session_state.tg_awaiting_code and not st.session_state.tg_awaiting_2fa:
                st.info(f"📱 **{st.session_state.tg_temp_phone}** numarasına gelen Telegram kodunu girin:")
                sms_code_input = st.text_input("Telegram Doğrulama Kodu", placeholder="12345")

                col_btn1, col_btn2 = st.columns([1, 4])
                with col_btn1:
                    if st.button("✅ Girişi Tamamla", type="primary"):
                        if not sms_code_input:
                            st.warning("Lütfen kodu girin.")
                        else:
                            try:
                                with st.spinner("Giriş yapılıyor..."):
                                    client = st.session_state.tg_client
                                    if not client:
                                        client = run_async(_get_or_create_client(
                                            int(st.session_state.tg_saved_api_id),
                                            st.session_state.tg_saved_api_hash
                                        ))
                                        st.session_state.tg_client = client

                                    if not client.is_connected():
                                        run_async(client.connect())

                                    try:
                                        run_async(client.sign_in(
                                            phone=st.session_state.tg_temp_phone,
                                            code=sms_code_input.strip(),
                                            phone_code_hash=st.session_state.tg_phone_code_hash
                                        ))
                                        # Başarılı giriş
                                        me = run_async(client.get_me())
                                        st.session_state.tg_is_auth = True
                                        st.session_state.tg_user_info = {
                                            "id": me.id,
                                            "first_name": me.first_name or "",
                                            "last_name": me.last_name or "",
                                            "username": f"@{me.username}" if me.username else "Yok",
                                            "phone": me.phone or "",
                                        }
                                        st.session_state.tg_awaiting_code = False
                                        st.success(f"Giriş Başarılı! Hoş geldiniz, {me.first_name}")
                                        st.rerun()

                                    except SessionPasswordNeededError:
                                        st.session_state.tg_awaiting_2fa = True
                                        st.warning("Bu hesapta İki Adımlı Doğrulama (2FA Bulut Şifresi) aktif!")
                                        st.rerun()

                            except (PhoneCodeInvalidError, PhoneCodeEmptyError):
                                st.error("Doğrulama kodu hatalı!")
                            except PhoneCodeExpiredError:
                                st.error("Kodun süresi dolmuş. Lütfen yeniden kod talep edin.")
                            except Exception as ex:
                                st.error(f"Giriş hatası: {str(ex)}")

                with col_btn2:
                    if st.button("❌ İptal Et & Yeniden Başla"):
                        st.session_state.tg_awaiting_code = False
                        st.session_state.tg_awaiting_2fa = False
                        st.rerun()

            # 2FA Şifre Giriş Aşaması
            if st.session_state.tg_awaiting_2fa:
                st.warning("🔐 Hesabınızda İki Adımlı Doğrulama (2FA) bulunmaktadır. Lütfen şifrenizi girin:")
                password_2fa = st.text_input("2FA Bulut Parolanız", type="password")

                if st.button("🔓 2FA ile Giriş Yap", type="primary"):
                    if not password_2fa:
                        st.warning("Lütfen 2FA parolanızı girin.")
                    else:
                        try:
                            with st.spinner("2FA doğrulanıyor..."):
                                client = st.session_state.tg_client
                                if not client:
                                    client = run_async(_get_or_create_client(
                                        int(st.session_state.tg_saved_api_id),
                                        st.session_state.tg_saved_api_hash
                                    ))
                                    st.session_state.tg_client = client

                                if not client.is_connected():
                                    run_async(client.connect())
                                run_async(client.sign_in(password=password_2fa))
                                me = run_async(client.get_me())
                                st.session_state.tg_is_auth = True
                                st.session_state.tg_user_info = {
                                    "id": me.id,
                                    "first_name": me.first_name or "",
                                    "last_name": me.last_name or "",
                                    "username": f"@{me.username}" if me.username else "Yok",
                                    "phone": me.phone or "",
                                }
                                st.session_state.tg_awaiting_code = False
                                st.session_state.tg_awaiting_2fa = False
                                st.success(f"2FA Başarılı! Hoş geldiniz, {me.first_name}")
                                st.rerun()
                        except PasswordHashInvalidError:
                            st.error("2FA şifreniz hatalı!")
                        except Exception as ex:
                            st.error(f"2FA Giriş hatası: {str(ex)}")

    # =========================================================================
    # 2. AŞAMA: ÜYE KAZIMA (SCRAPE - AKTİF & HEDEF KİTLE)
    # =========================================================================
    with tab_scrape:
        st.subheader("🕵️ Hedef / Rakip Gruptan Aktif Üye Kazıma")
        st.caption("Hedef gruptaki üyeleri filtreleyerek SADECE son 24 saatte çevrimiçi olmuş ve kullanıcı adı olanları çeker.")

        if not st.session_state.tg_is_auth:
            st.warning("⚠️ Lütfen önce **1. Hesap Bağlantısı** sekmesinden Telegram hesabınıza giriş yapın.")
        else:
            col_sc1, col_sc2 = st.columns([3, 1])
            with col_sc1:
                target_group_input = st.text_input(
                    "Hedef Grup Linki veya Kullanıcı Adı",
                    placeholder="https://t.me/hedef_kamu_grubu veya @hedef_kamu_grubu",
                    help="Üyelerini taramak istediğiniz herkese açık (public) grubun linki veya kullanıcı adı."
                )
            with col_sc2:
                scrape_limit = st.number_input(
                    "Maks. Taranacak Üye",
                    min_value=50,
                    max_value=5000,
                    value=500,
                    step=50,
                    help="Gruptan toplanacak maksimum hedef aktif üye sayısı."
                )

            col_opt1, col_opt2 = st.columns([2, 2])
            with col_opt1:
                activity_filter = st.selectbox(
                    "⏱️ Aktiflik Kapsamı (Zaman Filtresi)",
                    options=[
                        "⚡ Son 7 Gün (Önerilen - Yüksek Verim & Canlı Kitle)",
                        "🔥 Son 24 Saat & Çevrimiçi (Süper Aktif - En Dar)",
                        "👥 Son 30 Gün (Geniş Kitle)",
                        "🌐 Tümü (Tüm Kayıtlı Üyeler)"
                    ],
                    index=0,
                    help="Telegram kullanıcılarının çoğu son görülmesini gizler. 'Son 7 Gün' seçildiğinde hem yakın zamanda girenler hem de gizli son görülmesi olan aktif adaylar yakalanır."
                )
            with col_opt2:
                st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                username_only = st.checkbox(
                    "Sadece @kullaniciadi Olanları Çek",
                    value=False,
                    help="İşaret kaldırıldığında kullanıcı adı olmayan üyeler de 'ID & Access Hash' ile listeye eklenir. Telegram API bu kişileri grubunuza sorunsuz ekler ve bulunan üye sayısını 2-3 katına çıkarır!"
                )

            # Filtre Bilgisi Kartı
            st.markdown("""
            <div style="background: rgba(16, 185, 129, 0.08); border-left: 4px solid #10b981; padding: 12px; border-radius: 6px; margin: 12px 0;">
                <b style="color: #10b981;">🚀 Yüksek Verimli Çok Aşamalı Kazıma Motoru (Deep Scraping):</b>
                <ul style="color: #cbd5e1; margin: 6px 0 0 0; padding-left: 20px; font-size: 0.9rem;">
                    <li><b>1. Aşama (Doğrudan Katılımcı):</b> Telegram genel katılımcı listesi taranır.</li>
                    <li><b>2. Aşama (A-Z Alfabetik Derin Arama):</b> Telegram'ın tek sorguda koyduğu üye limitini aşmak için A'dan Z'ye harf taramasıyla binlerce üye taranır.</li>
                    <li><b>3. Aşama (Canlı Grup Sohbeti):</b> Grupta 'Üyeleri Gizle' açık olsa bile sohbet geçmişinden soru soran ve aktif mesaj atan adaylar toplanır.</li>
                </ul>
            </div>
            """, unsafe_allow_html=True)

            if st.button("🚀 Aktif Üyeleri Tara & Kazı", type="primary"):
                if not target_group_input:
                    st.error("Lütfen hedef grup linkini girin.")
                else:
                    # Client'ı garanti altına al
                    client = st.session_state.tg_client
                    if not client:
                        try:
                            client = run_async(_get_or_create_client(
                                int(st.session_state.tg_saved_api_id),
                                st.session_state.tg_saved_api_hash
                            ))
                            st.session_state.tg_client = client
                        except Exception as e:
                            st.error(f"Telegram bağlantısı kurulamadı: {e}")
                            return

                    clean_target = _clean_telegram_target(target_group_input)

                    progress_bar = st.progress(0.0)
                    status_text = st.empty()
                    status_text.info(f"🔍 `{clean_target}` hedefi inceleniyor...")

                    async def _scrape_active_members(ev_queue: queue.Queue):
                        if not client.is_connected():
                            await client.connect()

                        ev_queue.put(('status', f"🔍 `{clean_target}` Telegram üzerinde çözümleniyor..."))

                        # 1. Entity çözümleme
                        try:
                            if clean_target.startswith("+"):
                                try:
                                    updates = await client(ImportChatInviteRequest(clean_target[1:]))
                                    target_entity = updates.chats[0]
                                except Exception:
                                    invite = await client(CheckChatInviteRequest(clean_target[1:]))
                                    target_entity = invite.chat
                            else:
                                target_entity = await client.get_entity(clean_target)
                        except Exception as e:
                            raise ValueError(f"Hedef grup bulunamadı veya link geçersiz: '{clean_target}' ({type(e).__name__}: {e})")

                        # 2. Eğer Broadcast Kanalı ise ve Megagroup değilse bağlı tartışma grubunu tespit et
                        if getattr(target_entity, 'broadcast', False) and not getattr(target_entity, 'megagroup', False):
                            try:
                                full_ch = await client(GetFullChannelRequest(target_entity))
                                linked_id = getattr(full_ch.full_chat, 'linked_chat_id', None)
                                if linked_id:
                                    ev_queue.put(('status', "ℹ️ Kanalın bağlı sohbet/tartışma grubu bulundu, üyeler gruptan taranacak..."))
                                    target_entity = await client.get_entity(linked_id)
                            except Exception:
                                pass

                        # 3. Gruba katılmayı dene
                        try:
                            await client(JoinChannelRequest(target_entity))
                        except Exception:
                            pass

                        collected = []
                        seen_ids = set()
                        total_scanned = 0
                        source_used = []

                        def check_activity(u_status):
                            if "Tümü" in activity_filter:
                                if isinstance(u_status, UserStatusOnline):
                                    return True, "🟢 Çevrimiçi"
                                elif isinstance(u_status, UserStatusRecently):
                                    return True, "🟡 Son 24 Saat (Recently)"
                                elif isinstance(u_status, UserStatusLastWeek):
                                    return True, "🔵 Son 7 Gün"
                                elif isinstance(u_status, UserStatusLastMonth):
                                    return True, "⚪ Son 30 Gün"
                                else:
                                    return True, "⚪ Kayıtlı Üye"
                            elif "Son 30 Gün" in activity_filter:
                                if isinstance(u_status, (UserStatusOnline, UserStatusRecently, UserStatusLastWeek, UserStatusLastMonth)):
                                    if isinstance(u_status, UserStatusOnline):
                                        return True, "🟢 Çevrimiçi"
                                    elif isinstance(u_status, UserStatusRecently):
                                        return True, "🟡 Son 24 Saat (Recently)"
                                    elif isinstance(u_status, UserStatusLastWeek):
                                        return True, "🔵 Son 7 Gün"
                                    return True, "⚪ Son 30 Gün"
                                return False, ""
                            elif "Son 7 Gün" in activity_filter:
                                if isinstance(u_status, (UserStatusOnline, UserStatusRecently, UserStatusLastWeek)):
                                    if isinstance(u_status, UserStatusOnline):
                                        return True, "🟢 Çevrimiçi"
                                    elif isinstance(u_status, UserStatusRecently):
                                        return True, "🟡 Son 24 Saat (Recently)"
                                    return True, "🔵 Son 7 Gün"
                                return False, ""
                            else:
                                if isinstance(u_status, (UserStatusOnline, UserStatusRecently)):
                                    return True, "🟢 Çevrimiçi" if isinstance(u_status, UserStatusOnline) else "🟡 Son 24 Saat (Recently)"
                                return False, ""

                        def process_user(u, src_label):
                            nonlocal total_scanned
                            total_scanned += 1
                            if not u or getattr(u, 'bot', False) or getattr(u, 'deleted', False):
                                return False
                            if u.id in seen_ids:
                                return False
                            if username_only and not getattr(u, 'username', None):
                                return False

                            is_active, status_desc = check_activity(getattr(u, 'status', None))
                            if not is_active:
                                return False

                            seen_ids.add(u.id)
                            username_val = f"@{u.username}" if getattr(u, 'username', None) else "Yok (ID ile Eklenecek)"
                            collected.append({
                                "ID": u.id,
                                "Access Hash": getattr(u, 'access_hash', 0),
                                "Kullanıcı Adı": username_val,
                                "Ad": u.first_name or "",
                                "Soyad": u.last_name or "",
                                "Durum": status_desc,
                                "Kaynak": src_label,
                                "Kazınma Tarihi": datetime.now().strftime("%Y-%m-%d %H:%M")
                            })
                            if src_label not in source_used:
                                source_used.append(src_label)
                            return True

                        # 1. AŞAMA: Doğrudan Katılımcı Listesini Tara (iter_participants)
                        ev_queue.put(('status', f"📋 1. Aşama: `{clean_target}` genel katılımcı listesi taranıyor..."))
                        try:
                            async for user in client.iter_participants(target_entity, limit=scrape_limit):
                                process_user(user, "Genel Üye Listesi")
                                if total_scanned % 15 == 0:
                                    ev_queue.put(('status', f"⏳ 1. Aşama: {total_scanned} üye incelendi | Bulunan Uygun: {len(collected)}/{scrape_limit}"))
                                    ev_queue.put(('progress', min(0.9, len(collected) / max(1, scrape_limit))))
                                if len(collected) >= scrape_limit:
                                    break
                        except Exception:
                            pass

                        # 2. AŞAMA: A-Z ALFABETİK DERİN ARAMA (Telegram 200/9 limitini aşar)
                        if len(collected) < scrape_limit:
                            ev_queue.put(('status', f"🔎 2. Aşama: A-Z Derin Arama motoru başlatılıyor ({len(collected)}/{scrape_limit})..."))
                            search_alphabet = [
                                "a", "e", "i", "o", "u", "s", "k", "m", "t", "r", "n", "l",
                                "b", "c", "d", "f", "g", "h", "j", "p", "v", "y", "z",
                                "ç", "ğ", "ö", "ş", "ü", "1", "2"
                            ]
                            for char in search_alphabet:
                                if len(collected) >= scrape_limit:
                                    break
                                try:
                                    ev_queue.put(('status', f"🔎 2. Aşama (A-Z Arama '{char.upper()}'): {len(collected)}/{scrape_limit} üye toplandı..."))
                                    ev_queue.put(('progress', min(0.95, len(collected) / max(1, scrape_limit))))
                                    async for user in client.iter_participants(target_entity, search=char, limit=100):
                                        process_user(user, f"Alfabetik Tarama ({char.upper()})")
                                        if len(collected) >= scrape_limit:
                                            break
                                except Exception:
                                    continue

                        # 3. AŞAMA: CANLI SOHBET MESAJLARINI TARA (Gizli Üye Bypass)
                        if len(collected) < scrape_limit:
                            ev_queue.put(('status', f"💬 3. Aşama: Canlı sohbet mesajları taranıyor ({len(collected)}/{scrape_limit})..."))
                            msg_scan_limit = max(scrape_limit * 10, 2500)
                            msg_count = 0

                            async for msg in client.iter_messages(target_entity, limit=msg_scan_limit):
                                msg_count += 1
                                if msg_count % 35 == 0:
                                    ev_queue.put(('status', f"💬 3. Aşama: {msg_count} canlı mesaj incelendi | Toplanan: {len(collected)}/{scrape_limit}"))
                                    ev_queue.put(('progress', min(0.98, len(collected) / max(1, scrape_limit))))

                                if not msg:
                                    continue

                                sender = msg.sender
                                if not sender and msg.from_id:
                                    try:
                                        sender = await msg.get_sender()
                                    except Exception:
                                        continue

                                if not sender or not isinstance(sender, User):
                                    continue

                                process_user(sender, "Canlı Sohbet (Mesaj Gönderen)")
                                if len(collected) >= scrape_limit:
                                    break

                        source_summary = ", ".join(source_used[:3]) if source_used else "Genel Tarama"
                        return collected, total_scanned, source_summary

                    try:
                        loop = AsyncLoopThread.get_loop()
                        ev_q = queue.Queue()
                        future = asyncio.run_coroutine_threadsafe(_scrape_active_members(ev_q), loop)

                        while not future.done():
                            while not ev_q.empty():
                                ev_type, *ev_args = ev_q.get_nowait()
                                if ev_type == 'status':
                                    status_text.info(ev_args[0])
                                elif ev_type == 'progress':
                                    progress_bar.progress(ev_args[0])
                            time.sleep(0.1)

                        while not ev_q.empty():
                            ev_type, *ev_args = ev_q.get_nowait()
                            if ev_type == 'status':
                                status_text.info(ev_args[0])
                            elif ev_type == 'progress':
                                progress_bar.progress(ev_args[0])

                        scraped_list, total_scanned, source_used = future.result()
                        progress_bar.progress(1.0)
                        st.session_state.scraped_users = scraped_list
                        if scraped_list:
                            status_text.success(f"🎉 Tarama Başarılı! {total_scanned} kayıt/mesaj incelendi, **{len(scraped_list)}** adet süper aktif kamu ve KPSS adayı toplandı! (Yöntem: {source_used})")
                        else:
                            status_text.warning("⚠️ Tarama tamamlandı ancak grupta seçilen kriterlere uyan aktif üye tespit edilemedi. Lütfen aktiflik filtresini genişletin veya limiti artırın.")
                    except FloodWaitError as e:
                        st.error(f"⏳ Telegram Hız Sınırı (FloodWait): Telegram güvenlik kısıtı nedeniyle lütfen {e.seconds} saniye bekleyin.")
                    except Exception as ex:
                        err_type = type(ex).__name__
                        err_str = str(ex).strip() or repr(ex)
                        st.error(f"❌ Kazıma Hatası ({err_type}): {err_str}")
                        with st.expander("🔍 Hata Detayları ve Çözüm"):
                            import traceback
                            st.code(traceback.format_exc())
                            st.info("💡 İpucu: Hedef grubun linkinin doğru ve herkese açık olduğunu teyit edin.")

            # Kazınan Üyelerin Gösterimi
            if st.session_state.scraped_users:
                st.markdown(f"### 📋 Tespit Edilen Aktif Üyeler ({len(st.session_state.scraped_users)} Kişi)")
                df_users = pd.DataFrame(st.session_state.scraped_users)
                st.dataframe(df_users, use_container_width=True, height=320)

                col_d1, col_d2 = st.columns([2, 1])
                with col_d1:
                    csv_data = df_users.to_csv(index=False).encode("utf-8-sig")
                    st.download_button(
                        label="📥 Listeyi CSV Olarak İndir",
                        data=csv_data,
                        file_name=f"telegram_aktif_uyeler_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
                with col_d2:
                    if st.button("🗑️ Listeyi Temizle", use_container_width=True):
                        st.session_state.scraped_users = []
                        st.rerun()

    # =========================================================================
    # 3. AŞAMA: ÜYE EKLEME (ADD - ANTİ-BAN MOTORU)
    # =========================================================================
    with tab_add:
        st.subheader("➕ Kendi Grubunuza Güvenli Üye Ekleme")
        st.caption("Kazınan aktif üyeleri akıllı gecikme ve otomatik hata yönetimiyle hedef grubunuza ekler.")

        # Hayati Anti-Ban Kılavuzu
        st.markdown("""
        <div style="background: rgba(239, 68, 68, 0.08); border-left: 4px solid #ef4444; padding: 14px; border-radius: 6px; margin-bottom: 16px;">
            <b style="color: #f87171;">⚠️ Telegram Anti-Ban ve Hesap Koruma Kuralları:</b>
            <ul style="color: #cbd5e1; margin: 6px 0 0 0; padding-left: 20px; font-size: 0.9rem;">
                <li><b>Günlük Güvenli Ekleme Limiti:</b> Kişisel bir Telegram hesabıyla günde <b>20-35 üye</b> eklemek en güvenli sınırdır. Tek seferde yüzlerce üye eklemek hesabınızı SpamBot kısıtlamasına sokar.</li>
                <li><b>Rastgele Bekleme Süresi:</b> Her üye arasında <b>60 - 120 saniye</b> rastgele bekleme uygulanmalıdır. Sabit süreler bot algoritmalarına yakalanır.</li>
                <li><b>Hata Yönetimi:</b> <code>FloodWaitError</code> oluşursa sistem otomatik durup süre bitene kadar bekler. <code>PeerFloodError</code> durumunda ise hesap güvenliği için işlem derhal kesilir.</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)

        if not st.session_state.tg_is_auth:
            st.warning("⚠️ Lütfen önce **1. Hesap Bağlantısı** sekmesinden Telegram hesabınıza giriş yapın.")
        elif not st.session_state.scraped_users:
            st.info("ℹ️ Henüz kazınmış üye listeniz yok. Lütfen önce **2. Üye Kazıma** sekmesinden hedef gruptan aktif üyeleri çekin.")
        else:
            col_target, col_max = st.columns([3, 1])
            with col_target:
                my_group_input = st.text_input(
                    "Üyelerin Ekleneceği Kendi Grubunuz (@kullaniciadi veya link)",
                    placeholder="https://t.me/benim_kamu_grubum veya @benim_kamu_grubum",
                    help="Yönetici olduğunuz veya üye ekleme izninizin açık olduğu grubunuz."
                )
            with col_max:
                max_to_add = st.number_input(
                    "Bu Sefer Eklenecek Sayı",
                    min_value=1,
                    max_value=min(100, len(st.session_state.scraped_users)),
                    value=min(25, len(st.session_state.scraped_users)),
                    step=5,
                    help="Güvenlik için tek bir oturumda 20-30 üyeden fazlasını eklememeniz önerilir."
                )

            # Rastgele Gecikme Slider'ı
            delay_range = st.slider(
                "⏱️ İki Üye Arası Rastgele Bekleme Süresi (Saniye)",
                min_value=15,
                max_value=240,
                value=(45, 90),
                step=5,
                help="Her kullanıcı eklendikten sonra bu aralıkta tamamen rastgele (random.randint) bir süre beklenir."
            )
            min_delay, max_delay = delay_range

            st.markdown("---")

            col_btn_start, col_btn_stop = st.columns([2, 1])
            start_add = col_btn_start.button("🚀 Güvenli Ekleme Sürecini Başlat", type="primary", use_container_width=True)

            # Thread-safe stop mekanizması — threading.Event kullanarak async loop'un içinden okunabilir
            if "tg_stop_event" not in st.session_state:
                st.session_state.tg_stop_event = threading.Event()

            if col_btn_stop.button("⏹️ İşlemi Güvenle Durdur", use_container_width=True):
                st.session_state.tg_stop_event.set()
                st.warning("⏹️ Durdurma sinyali gönderildi. Mevcut adım tamamlandıktan sonra durulacak...")

            if start_add:
                if not my_group_input:
                    st.error("Lütfen hedef grubunuzun linkini veya kullanıcı adını girin.")
                else:
                    # Stop event'i sıfırla
                    st.session_state.tg_stop_event.clear()
                    stop_event: threading.Event = st.session_state.tg_stop_event

                    clean_my_group = _clean_telegram_target(my_group_input)

                    # Client'ı garanti altına al
                    client = st.session_state.tg_client
                    if not client:
                        try:
                            client = run_async(_get_or_create_client(
                                int(st.session_state.tg_saved_api_id),
                                st.session_state.tg_saved_api_hash
                            ))
                            st.session_state.tg_client = client
                        except Exception as e:
                            st.error(f"Telegram bağlantısı kurulamadı: {e}")
                            return

                    users_pool = st.session_state.scraped_users[:max_to_add]

                    # Canlı Arayüz Elemanları
                    progress_bar = st.progress(0.0)
                    status_placeholder = st.empty()
                    metrics_col1, metrics_col2, metrics_col3, metrics_col4 = st.columns(4)
                    metric_success = metrics_col1.empty()
                    metric_privacy = metrics_col2.empty()
                    metric_already = metrics_col3.empty()
                    metric_fail = metrics_col4.empty()

                    log_placeholder = st.empty()
                    runtime_logs = []

                    def append_log(msg: str):
                        timestamp = datetime.now().strftime("%H:%M:%S")
                        entry = f"[{timestamp}] {msg}"
                        runtime_logs.append(entry)
                        log_placeholder.code("\n".join(runtime_logs[-15:]), language="bash")

                    append_log("🚀 Telegram üye ekleme otomasyonu başlatıldı...")
                    append_log(f"🎯 Hedef Grup: {clean_my_group} | Hedeflenen Kişi Sayısı: {len(users_pool)}")
                    append_log(f"⏱️ Güvenlik Bekleme Aralığı: {min_delay} - {max_delay} saniye (Rastgele)")

                    async def _add_members_process(ev_q: queue.Queue):
                        if not client.is_connected():
                            await client.connect()

                        try:
                            my_group_entity = await client.get_entity(clean_my_group)
                        except Exception as e:
                            ev_q.put(('log', f"❌ Hedef grup bulunamadı veya erişilemedi: {str(e)}"))
                            ev_q.put(('error', f"Hedef grup bulunamadı: {str(e)}"))
                            return

                        success_cnt = 0
                        privacy_cnt = 0
                        already_cnt = 0
                        fail_cnt = 0

                        for idx, user_data in enumerate(users_pool, start=1):
                            # Thread-safe stop kontrolü
                            if stop_event.is_set():
                                ev_q.put(('log', "⏹️ Kullanıcı talebiyle işlem güvenle durduruldu."))
                                ev_q.put(('warning', "İşlem kullanıcı tarafından durduruldu."))
                                break

                            u_name = user_data["Kullanıcı Adı"]
                            progress = idx / len(users_pool)
                            ev_q.put(('progress', progress, f"👤 ({idx}/{len(users_pool)}) **{u_name}** gruba davet ediliyor..."))

                            try:
                                u_id = user_data.get("ID")
                                u_hash = user_data.get("Access Hash")
                                if u_id and u_hash:
                                    target_user_entity = InputPeerUser(user_id=int(u_id), access_hash=int(u_hash))
                                elif u_name and u_name.startswith("@"):
                                    target_user_entity = await client.get_input_entity(u_name)
                                else:
                                    target_user_entity = await client.get_input_entity(int(u_id))

                                # Grup tipine göre davet etme isteği
                                if isinstance(my_group_entity, Channel):
                                    await client(InviteToChannelRequest(
                                        channel=my_group_entity,
                                        users=[target_user_entity]
                                    ))
                                elif isinstance(my_group_entity, Chat):
                                    await client(AddChatUserRequest(
                                        chat_id=my_group_entity.id,
                                        user_id=target_user_entity,
                                        fwd_limit=10
                                    ))
                                else:
                                    await client(InviteToChannelRequest(
                                        channel=my_group_entity,
                                        users=[target_user_entity]
                                    ))

                                success_cnt += 1
                                ev_q.put(('log', f"✅ {u_name} başarıyla gruba eklendi! (+1)"))

                                # Anti-Ban Rastgele Bekleme Süresi
                                if idx < len(users_pool):
                                    sleep_secs = random.randint(min_delay, max_delay)
                                    ev_q.put(('log', f"⏳ Anti-ban koruması: {sleep_secs} saniye rastgele bekleniyor..."))
                                    for remaining in range(sleep_secs, 0, -1):
                                        if stop_event.is_set():
                                            break
                                        ev_q.put(('status_info', f"⏳ Anti-ban soğuma süresi: {remaining} sn kaldı... (Son eklenen: {u_name})"))
                                        await asyncio.sleep(1)

                            except FloodWaitError as e:
                                ev_q.put(('log', f"⚠️ Telegram FloodWait Limiti: Telegram {e.seconds} saniye beklemeyi zorunlu kıldı."))
                                for rem in range(e.seconds, 0, -1):
                                    if stop_event.is_set():
                                        break
                                    ev_q.put(('warning', f"⚠️ FloodWait Beklemesi: {rem} sn kaldı..."))
                                    await asyncio.sleep(1)
                                ev_q.put(('log', "🔄 FloodWait süresi tamamlandı, işleme devam ediliyor..."))

                            except PeerFloodError:
                                ev_q.put(('log', "⛔ KRİTİK HATA (PeerFloodError): Telegram hesabınızı aşırı davet nedeniyle spam kısıtlamasına aldı!"))
                                ev_q.put(('log', "🚨 HESAP GÜVENLİĞİ İÇİN DÖNGÜ DERHAL DURDURULDU."))
                                ev_q.put(('log', "💡 Lütfen @SpamBot üzerinden kısıtlamanızı sorgulayın ve 24-48 saat işlem yapmayın."))
                                ev_q.put(('error', "⛔ PeerFloodError tespit edildi! Hesap ban koruması devreye girdi ve işlem derhal kesildi."))
                                break

                            except UserPrivacyRestrictedError:
                                privacy_cnt += 1
                                ev_q.put(('log', f"🔒 {u_name}: Kullanıcının gizlilik ayarları yabancıların gruba eklemesine kapalı. (Atlandı)"))

                            except UserNotMutualContactError:
                                privacy_cnt += 1
                                ev_q.put(('log', f"📇 {u_name}: Kullanıcı sadece karşılıklı rehberinde kayıtlı olanların eklemesine izin veriyor. (Atlandı)"))

                            except UserAlreadyParticipantError:
                                already_cnt += 1
                                ev_q.put(('log', f"ℹ️ {u_name}: Kullanıcı zaten grubunuzda mevcut. (Atlandı)"))

                            except UserChannelsTooMuchError:
                                already_cnt += 1
                                ev_q.put(('log', f"⚠️ {u_name}: Kullanıcı 500 grup/kanal limitine ulaşmış. (Atlandı)"))

                            except ChatAdminRequiredError:
                                ev_q.put(('log', "❌ HATA: Hedef grupta kullanıcı ekleme yetkiniz yok! Lütfen admin yetkilerinizi kontrol edin."))
                                ev_q.put(('error', "Grupta kullanıcı ekleme yetkisi bulunamadı."))
                                break

                            except Exception as ex:
                                fail_cnt += 1
                                ev_q.put(('log', f"❌ {u_name}: Hata -> {str(ex)}"))

                            # Metrikleri güncelle
                            ev_q.put(('metrics', success_cnt, privacy_cnt, already_cnt, fail_cnt))

                        ev_q.put(('log', f"🏁 İşlem Tamamlandı. Toplam Başarılı: {success_cnt}, Gizlilik: {privacy_cnt}, Hata: {fail_cnt}"))
                        ev_q.put(('done', f"🏁 Ekleme süreci tamamlandı! Başarıyla eklenen: {success_cnt} üye."))

                    def _drain_queue(ev_add_q):
                        """Kuyruktaki tüm mesajları işle."""
                        while not ev_add_q.empty():
                            try:
                                ev_type, *ev_args = ev_add_q.get_nowait()
                            except queue.Empty:
                                break
                            if ev_type == 'log':
                                append_log(ev_args[0])
                            elif ev_type == 'progress':
                                progress_bar.progress(ev_args[0])
                                status_placeholder.info(ev_args[1])
                            elif ev_type == 'status_info':
                                status_placeholder.info(ev_args[0])
                            elif ev_type == 'warning':
                                status_placeholder.warning(ev_args[0])
                            elif ev_type == 'error':
                                status_placeholder.error(ev_args[0])
                            elif ev_type == 'done':
                                status_placeholder.success(ev_args[0])
                            elif ev_type == 'metrics':
                                s_cnt, p_cnt, a_cnt, f_cnt = ev_args
                                metric_success.metric("🟢 Başarılı", s_cnt)
                                metric_privacy.metric("🔒 Gizlilik Engeli", p_cnt)
                                metric_already.metric("ℹ️ Zaten Üye/Limit", a_cnt)
                                metric_fail.metric("❌ Hata", f_cnt)

                    try:
                        loop = AsyncLoopThread.get_loop()
                        ev_add_q = queue.Queue()
                        future = asyncio.run_coroutine_threadsafe(_add_members_process(ev_add_q), loop)

                        while not future.done():
                            _drain_queue(ev_add_q)
                            time.sleep(0.1)

                        _drain_queue(ev_add_q)
                        future.result()
                    except Exception as ex:
                        err_type = type(ex).__name__
                        err_str = str(ex).strip() or repr(ex)
                        st.error(f"Genel işlem hatası ({err_type}): {err_str}")


# Modül tek başına test edilmek istendiğinde:
if __name__ == "__main__":
    st.set_page_config(page_title="Telegram Büyütme Modülü", layout="wide")
    telegram_buyutme_modulu()
