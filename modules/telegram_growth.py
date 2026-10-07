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
import re
import time
from datetime import datetime
from pathlib import Path
import threading
import queue
import concurrent.futures
import json
from typing import List, Dict, Any, Optional

import pandas as pd
import streamlit as st
from config.settings import settings
from modules.kpss_quiz_engine import KPSSQuizEngine
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


def normalize_phone_number(raw_phone: str) -> str:
    """Telefon numarasını Telegram uyumlu E.164 uluslararası formatına (+90...) dönüştürür."""
    import re
    cleaned = re.sub(r"[^\d+]", "", (raw_phone or "").strip())
    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]
    elif cleaned.startswith("0") and len(cleaned) == 11 and cleaned[1] == "5":
        cleaned = "+90" + cleaned[1:]
    elif cleaned.startswith("5") and len(cleaned) == 10:
        cleaned = "+90" + cleaned
    elif not cleaned.startswith("+") and cleaned.isdigit():
        cleaned = "+" + cleaned
    return cleaned


def _auto_restore_session():
    """
    Her Streamlit rerun'ında çağrılır.
    Eğer session_state'te oturum bilgisi yoksa ama diskte .session dosyası varsa
    ve API bilgileri mevcutsa, otomatik olarak oturumu yeniden bağlar.
    Bu sayede sayfa yenilendiğinde kullanıcı oturumunu kaybetmez.
    """
    # Kod doğrulama veya 2FA parolası beklenirken oturum kurtarmayı ÇALIŞTIRMA (Handshake aktif!)
    if st.session_state.get("tg_awaiting_code", False) or st.session_state.get("tg_awaiting_2fa", False):
        return

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

    # 5 Aşamalı Genişletilmiş Büyüme & Otomasyon Arayüzü
    tab_auth, tab_scrape, tab_add, tab_quiz, tab_seo = st.tabs([
        "🔑 1. Hesap Bağlantısı",
        "🕵️ 2. Üye Kazıma (Scrape)",
        "➕ 3. Üye Ekleme (Add)",
        "🎯 4. Günlük KPSS Quiz / Soru Motoru",
        "🚀 5. Kanal SEO & İletilme (Forward) Stüdyosu"
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
                help="Telegram hesabınıza bağlı telefon numarası (Örn: +905321234567 veya 05321234567)."
            )

            if not st.session_state.tg_awaiting_code and not st.session_state.tg_awaiting_2fa:
                if st.button("📩 Doğrulama Kodu Gönder", type="primary"):
                    if not api_id_input or not api_hash_input or not phone_input:
                        st.error("Lütfen API ID, API Hash ve Telefon Numarası alanlarını eksiksiz doldurun.")
                    else:
                        norm_phone = normalize_phone_number(phone_input)
                        if len(norm_phone) < 10 or not norm_phone.startswith("+"):
                            st.error(f"Geçersiz telefon formatı: '{phone_input}'. Lütfen ülke koduyla girin (Örn: +905321234567)")
                        else:
                            try:
                                with st.spinner("Telegram ile bağlantı kuruluyor ve Kod isteniyor..."):
                                    # API bilgilerini DB'ye kaydet
                                    set_system_setting("TELEGRAM_API_ID", str(api_id_input).strip())
                                    set_system_setting("TELEGRAM_API_HASH", str(api_hash_input).strip())

                                    client = run_async(_get_or_create_client(int(api_id_input), api_hash_input))
                                    code_req = run_async(client.send_code_request(norm_phone))

                                    del_type = type(code_req.type).__name__ if hasattr(code_req, 'type') else "Bilinmiyor"

                                    st.session_state.tg_client = client
                                    st.session_state.tg_saved_api_id = str(api_id_input).strip()
                                    st.session_state.tg_saved_api_hash = str(api_hash_input).strip()
                                    st.session_state.tg_temp_phone = norm_phone
                                    st.session_state.tg_phone_code_hash = code_req.phone_code_hash
                                    st.session_state.tg_delivery_type = del_type
                                    st.session_state.tg_awaiting_code = True
                                    st.success("Doğrulama kodu oluşturuldu!")
                                    st.rerun()
                            except PhoneNumberInvalidError:
                                st.error("Girdiğiniz telefon numarası Telegram tarafından tanınmadı!")
                            except Exception as ex:
                                st.error(f"Kod gönderme hatası: {str(ex)}")

            # Kod Giriş Aşaması
            if st.session_state.tg_awaiting_code and not st.session_state.tg_awaiting_2fa:
                del_type = st.session_state.get("tg_delivery_type", "")
                if "App" in del_type:
                    st.info(f"💬 **DİKKAT:** Telegram doğrulama kodunu **TELEGRAM UYGULAMANIZA** gönderdi! Lütfen telefonunuzdaki Telegram uygulamasında 'Telegram' servis mesajını kontrol edin. (SMS gelmeyebilir)")
                else:
                    st.info(f"📱 **{st.session_state.tg_temp_phone}** numarasına SMS / Telegram ile gelen kodu girin:")

                sms_code_input = st.text_input("Telegram Doğrulama Kodu", placeholder="12345")

                col_btn1, col_btn2 = st.columns([1, 4])
                with col_btn1:
                    if st.button("✅ Girişi Tamamla", type="primary"):
                        clean_code = re.sub(r"[^\d]", "", (sms_code_input or "").strip())
                        if not clean_code:
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
                                            code=clean_code,
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

    # =========================================================================
    # 4. AŞAMA: GÜNLÜK KPSS QUIZ & SORU MOTORU (QUIZ POLLS)
    # =========================================================================
    with tab_quiz:
        st.subheader("🎯 Günlük KPSS Quiz & Soru Anketi Motoru")
        st.caption("Adayların bildirimleri sürekli açık tutmasını ve kanala her gün girmesini sağlayan Telegram resmi Quiz Anketleri.")

        st.markdown("""
        <div style="background: rgba(56, 189, 248, 0.08); border-left: 4px solid #38bdf8; padding: 14px 18px; border-radius: 8px; margin-bottom: 20px;">
            <b style="color: #38bdf8; font-size: 15px;">💡 Neden İşe Yarar ve Kanalı Nasıl Büyütür?</b>
            <p style="color: #cbd5e1; margin: 6px 0 0 0; font-size: 0.92rem;">
                Sadece ilan paylaşılan kanallar, ilan olmayan günlerde sessiz kalır ve üyeler bildirimleri kapatır (mute). 
                Günde 1 veya 2 kez (sabah 10:00 ve akşam 20:30) yayınlanan açıklamalı KPSS Quiz soruları:
                <br>• Üyelerin bildirimleri <b>açık tutmasını</b> sağlar.
                <br>• Adaylar soruyu diğer KPSS çalışma gruplarına ileterek kanala <b>yeni organik üyeler</b> çeker.
                <br>• Doğru cevap tıklandığında beliren detaylı <b>açıklama & çözüm metni</b> kanalınızı güvenilir bir etüt merkezine dönüştürür.
            </p>
        </div>
        """, unsafe_allow_html=True)

        # KPSS Quiz & Soru Motoru Entegrasyonu
        quiz_engine = KPSSQuizEngine()
        stats = quiz_engine.get_autopilot_stats()

        # =====================================================================
        # 1. BÖLÜM: TAM OTOMATİK KPSS QUIZ OTOPİLOTU (TAM OTOMATİK)
        # =====================================================================
        st.markdown("### 🤖 Tam Otomatik KPSS Soru Otopilotu")
        is_auto_on = stats["enabled"]

        if is_auto_on:
            st.success("🟢 **OTOPİLOT DEVREDE (TAM OTOMATİK):** Yapay zeka her gün belirlenen saat aralıklarında (08:30 - 23:30) günde 10 adet özgün KPSS sorusu üretir; **eşzamanlı olarak hem Telegram'a canlı anket/quiz olarak atar, hem de Instagram'da doğru cevabı gizli tutup çözümü Telegram'a yönlendiren post olarak paylaşır.** Sizin hiçbir butona basmanıza gerek yoktur.")
        else:
            st.warning("🔴 **OTOPİLOT DURDURULDU (MANUEL MOD):** Otomasyon duraklatılmıştır. Bir hata gördüğünüzde sistemi manuele alıp inceleyebilir, düzelttikten sonra tekrar başlatabilirsiniz.")

        col_st1, col_st2, col_st3, col_st4 = st.columns(4)
        with col_st1:
            st.metric("🎯 Günlük Hedef", f"{stats['target_daily']} Soru")
        with col_st2:
            st.metric("✈️ Telegram / 📸 Instagram", f"TG: {stats.get('sent_tg_today', stats['sent_today'])} | IG: {stats.get('sent_ig_today', 0)}")
        with col_st3:
            st.metric("⏱️ Gönderim Aralığı", "Her ~90 Dakikada 1")
        with col_st4:
            st.metric("🕒 Son Otomatik Gönderim", stats['last_sent_time'])

        col_ctrl1, col_ctrl2, col_ctrl3 = st.columns([2, 2, 3])
        with col_ctrl1:
            if is_auto_on:
                if st.button("🔴 Otopilotu Durdur / Manuele Al", type="secondary", use_container_width=True, help="Bir hata görürseniz otomasyonu durdurup manuele alabilirsiniz."):
                    set_system_setting("AUTO_KPSS_QUIZ_ENABLED", "false")
                    st.warning("Otopilot durduruldu. Sistem manuel moda alındı.")
                    st.rerun()
            else:
                if st.button("🟢 Otopilotu Başlat (Tam Otomatik)", type="primary", use_container_width=True):
                    set_system_setting("AUTO_KPSS_QUIZ_ENABLED", "true")
                    st.success("Otopilot başlatıldı! Sistem arka planda tam otomatik çalışıyor.")
                    st.rerun()

        with col_ctrl2:
            if st.button("⚡ Şimdi 1 Otomatik Soru Paylaş (Telegram + Insta Test)", use_container_width=True, help="Zamanlayıcıyı beklemeden sıradaki soruyu anında hem Telegram'a hem de Instagram'a atar."):
                with st.spinner("Otopilot canlı soruyu hazırlayıp Telegram ve Instagram'a eşzamanlı aktarıyor..."):
                    succ, msg, q_sent, c_path = quiz_engine.publish_automated_quiz(
                        channel_id=settings.active_telegram_channel_id,
                        post_to_instagram=True
                    )
                    if succ:
                        st.success(f"🎉 Harika! Soru eşzamanlı olarak yayınlandı!\n{msg}")
                        if c_path:
                            st.session_state["last_ig_quiz_card"] = c_path
                        st.rerun()
                    else:
                        st.error(f"❌ Gönderim başarısız: {msg}")

        with col_ctrl3:
            daily_target_val = st.selectbox(
                "Günlük Otomatik Soru Sayısı:",
                [10, 15, 20],
                index=0 if stats["target_daily"] == 10 else (1 if stats["target_daily"] == 15 else 2),
                key="sel_quiz_daily_target"
            )
            if daily_target_val != stats["target_daily"]:
                set_system_setting("AUTO_KPSS_QUIZ_DAILY_TARGET", str(daily_target_val))
                new_interval = round(15.0 / daily_target_val, 2)
                set_system_setting("AUTO_KPSS_QUIZ_INTERVAL_HOURS", str(new_interval))
                st.rerun()

        st.markdown("---")
        st.markdown("#### 🛠️ Manuel İnceleme ve Acil Müdahale Havuzu")
        st.caption("Otopilot zaten otomatik çalışmaktadır. Burası sadece soruları tek tek incelemek veya test etmek istediğinizde kullanılır.")

        if "kpss_active_questions" not in st.session_state or not st.session_state["kpss_active_questions"]:
            st.session_state["kpss_active_questions"] = quiz_engine.generate_ai_questions(count=10)

        c_gen1, c_gen2, c_gen3 = st.columns([2, 2, 3])
        with c_gen1:
            if st.button("🤖 AI ile Havuzu Yenile (10 Soru)", type="primary", use_container_width=True):
                with st.spinner("ÖSYM standartlarında 10 özgün KPSS sorusu üretiliyor..."):
                    st.session_state["kpss_active_questions"] = quiz_engine.generate_ai_questions(count=10)
                    st.success("✅ 10 yeni KPSS sorusu üretildi!")
                    st.rerun()

        with c_gen2:
            if st.button("⚡ AI ile Havuzu Yenile (20 Soru)", use_container_width=True):
                with st.spinner("ÖSYM standartlarında 20 özgün KPSS sorusu üretiliyor..."):
                    st.session_state["kpss_active_questions"] = quiz_engine.generate_ai_questions(count=20)
                    st.success("✅ 20 yeni KPSS sorusu üretildi!")
                    st.rerun()

        with c_gen3:
            target_tg_ch = st.text_input(
                "Hedef Telegram Kanalı:",
                value=settings.active_telegram_channel_id or "@kamupersonelrehberi",
                key="tg_quiz_target_ch"
            )

        q_list = st.session_state["kpss_active_questions"]
        q_titles = [f"#{i+1} [{q.get('subject', 'KPSS')}] {q.get('question', '')[:65]}..." for i, q in enumerate(q_list)]

        col_qsel, col_stat = st.columns([3, 1])
        with col_qsel:
            selected_q_idx = st.selectbox("İncelemek ve Yayınlamak İçin Soru Seçin:", list(range(len(q_titles))), format_func=lambda i: q_titles[i])
        with col_stat:
            st.metric("Havuzdaki Soru Sayısı", len(q_list))

        cur_q = q_list[selected_q_idx]
        q_text = cur_q.get("question", "")
        q_opts = cur_q.get("options", [])
        q_corr = int(cur_q.get("correct_option_id", 0))
        q_expl = cur_q.get("explanation", "")
        q_subj = cur_q.get("subject", "KPSS")

        # Canlı Önizleme Kartı (Admin Paneli)
        st.markdown(f"""
        <div style="background: rgba(18, 22, 26, 0.95); border: 1px solid #334155; border-radius: 12px; padding: 18px; margin-bottom: 16px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                <span style="background: #1e293b; color: #94a3b8; font-weight: 700; padding: 3px 10px; border-radius: 6px; font-size: 13px; border: 1px solid #475569;">
                    📚 {q_subj}
                </span>
                <span style="color: #64748b; font-size: 12px;">Telegram Native Quiz & Instagram Uyumlu</span>
            </div>
            <h4 style="color: #ffffff; margin: 10px 0 16px 0; font-weight: 600; line-height: 1.4;">{q_text}</h4>
            <div style="display: flex; flex-direction: column; gap: 8px;">
        """, unsafe_allow_html=True)
        for i, opt in enumerate(q_opts):
            is_correct = (i == q_corr)
            badge = " (✅ Doğru Cevap - Telegram'da tıklandığında açılır)" if is_correct else ""
            bg = "rgba(16, 185, 129, 0.12); border: 1px solid #10b981;" if is_correct else "rgba(30, 41, 59, 0.5); border: 1px solid #334155;"
            opt_letter = ["A", "B", "C", "D", "E"][i] if i < 5 else f"{i+1}"
            st.markdown(f"""
            <div style="background: {bg} border-radius: 8px; padding: 10px 14px; color: #e2e8f0; font-size: 14px;">
                <b>{opt_letter}]</b> {opt} <b style="color: #34d399;">{badge}</b>
            </div>
            """, unsafe_allow_html=True)
        st.markdown(f"""
            </div>
            <div style="margin-top: 14px; padding-top: 10px; border-top: 1px solid #334155; color: #94a3b8; font-size: 13px;">
                💡 <b>ÖSYM Çözüm Açıklaması:</b> {q_expl}
            </div>
        </div>
        """, unsafe_allow_html=True)

        col_act1, col_act2, col_act3 = st.columns(3)
        bot_token = settings.active_telegram_bot_token

        with col_act1:
            if st.button("🚀 Bu Soruyu Telegram'da Yayınla", type="primary", use_container_width=True):
                with st.spinner("Quiz Telegram kanalına aktarılıyor..."):
                    succ, msg = quiz_engine.send_quiz_to_telegram(cur_q, target_tg_ch, bot_token)
                    if succ:
                        st.success(f"🎉 Soru #{selected_q_idx+1} Telegram'da anket olarak yayınlandı!")
                    else:
                        st.error(f"❌ {msg}")

        with col_act2:
            if st.button(f"⚡ Tüm {len(q_list)} Soruyu Sırayla Kanala Gönder", use_container_width=True):
                with st.spinner(f"{len(q_list)} adet soru sırayla Telegram kanalına aktarılıyor..."):
                    success_count = 0
                    prog = st.progress(0)
                    for idx, q_item in enumerate(q_list):
                        succ, _ = quiz_engine.send_quiz_to_telegram(q_item, target_tg_ch, bot_token)
                        if succ:
                            success_count += 1
                        prog.progress((idx + 1) / len(q_list))
                        time.sleep(2)  # Anti-flood koruması
                    st.success(f"🎉 Toplam {success_count}/{len(q_list)} soru Telegram kanalına gönderildi!")

        with col_act3:
            if st.button("📸 Instagram İçin Minimalist Kart Üret", use_container_width=True):
                with st.spinner("Minimalist, filigranlı soru kartı hazırlanıyor..."):
                    card_path = quiz_engine.generate_instagram_quiz_card(cur_q)
                    st.session_state["last_ig_quiz_card"] = card_path
                    st.success("✅ Instagram soru kartı üretildi!")

        if "last_ig_quiz_card" in st.session_state and st.session_state["last_ig_quiz_card"]:
            c_card = Path(st.session_state["last_ig_quiz_card"])
            if c_card.exists():
                st.markdown("---")
                st.subheader("🖼️ Instagram Soru Kartı (Doğru Cevapsız & Filigran Korumalı)")
                st.caption("Renk cümbüşünden uzak, mat antrasit zeminli ve arka planda hırsızlığa karşı şeffaf filigran içeren resmi soru postu.")
                col_img, col_info = st.columns([1, 1])
                with col_img:
                    st.image(str(c_card), caption=f"Instagram Kartı: {c_card.name}", use_container_width=True)
                with col_info:
                    st.markdown("""
                    **🎯 Bu Tasarım Neden Daha Fazla Etkileşim Getirir?**
                    - **Doğru Cevap Gizlidir:** Adaylar çözümü merak edip doğru şıkkı yorumlara yazarlar.
                    - **Yorumlar Algoritmayı Uçurur:** Her yorum Instagram Keşfet (Explore) algoritmasında postu öne çıkarır.
                    - **Hırsızlığa Karşı Korumalıdır:** Arka planda şeffaf `@kamupersonelrehberi` damgası bulunur.
                    """)
                    col_dl1, col_dl2 = st.columns(2)
                    with col_dl1:
                        with open(c_card, "rb") as f_img:
                            st.download_button(
                                label="📥 Görseli İndir (Manuel)",
                                data=f_img.read(),
                                file_name=c_card.name,
                                mime="image/png",
                                use_container_width=True
                            )
                    with col_dl2:
                        if st.button("🚀 Instagram'da Yayınla", type="primary", use_container_width=True, help="Bu soru kartını Telegram yönlendirmeli açıklamayla Instagram akışında paylaşır."):
                            with st.spinner("Instagram akışına aktarılıyor..."):
                                ig_ok, ig_res = quiz_engine.publish_quiz_to_instagram(str(c_card), cur_q)
                                if ig_ok:
                                    st.success(f"🎉 {ig_res}")
                                else:
                                    st.error(f"❌ {ig_res}")

                    with st.expander("📝 Instagram Gönderi Açıklaması (Telegram Yönlendirmesi)", expanded=False):
                        st.text_area("Post Metni:", value=quiz_engine.build_instagram_quiz_caption(cur_q), height=180)

    # =========================================================================
    # 5. AŞAMA: KANAL SEO & İLETİLME (FORWARD) STÜDYOSU
    # =========================================================================
    with tab_seo:
        st.subheader("🚀 Telegram Kanal SEO & İletilme (Forward) Stüdyosu")
        st.caption("Telegram Global Search (Arama Motoru) sıralamasını zirveye taşıyan başlık, açıklama ve viral iletim kuralları.")

        c_seo1, c_seo2 = st.columns(2)
        with c_seo1:
            st.markdown("""
            <div style="background: rgba(30, 41, 59, 0.7); border: 1px solid #334155; padding: 18px; border-radius: 12px; margin-bottom: 16px;">
                <h4 style="color: #38bdf8; margin: 0 0 10px 0;">🔍 1. Arama Motoru Kanal Başlığı (Title SEO)</h4>
                <p style="color: #94a3b8; font-size: 13px;">Telegram arama motoru kanal adının ilk 2 kelimesine en yüksek ağırlığı verir.</p>
                <div style="background: #0f172a; padding: 10px; border-radius: 8px; border-left: 3px solid #10b981;">
                    <b style="color: #34d399;">Önerilen Başlık:</b><br>
                    <code style="color: #ffffff; font-size: 14px;">Kamu Personel Rehberi | KPSS & Memur Alımları 2026</code>
                </div>
            </div>
            """, unsafe_allow_html=True)

            st.markdown("""
            <div style="background: rgba(30, 41, 59, 0.7); border: 1px solid #334155; padding: 18px; border-radius: 12px;">
                <h4 style="color: #f59e0b; margin: 0 0 10px 0;">💎 2. Telegram Premium Üye Ağırlığı</h4>
                <p style="color: #cbd5e1; font-size: 13px;">
                    Telegram algoritmasında kanalınızdaki <b>Premium abonelerin</b> arama sıralamasındaki ağırlığı standart üyelerden <b>3-4 kat daha fazladır</b>. 
                    Kaliteli ve aktif kitle aramalarda kanalı en tepeye fırlatır. Sahte bot üye basmak ise tersine aramalardan silinmeye neden olur.
                </p>
            </div>
            """, unsafe_allow_html=True)

        with c_seo2:
            st.markdown("""
            <div style="background: rgba(30, 41, 59, 0.7); border: 1px solid #334155; padding: 18px; border-radius: 12px; margin-bottom: 16px;">
                <h4 style="color: #38bdf8; margin: 0 0 10px 0;">📝 3. Açıklama (İlk 160 Karakter SEO)</h4>
                <p style="color: #94a3b8; font-size: 13px;">Arama motoru ve yeni gelen üyeler için hazır, optimize edilmiş kanal açıklaması:</p>
                <div style="background: #0f172a; padding: 12px; border-radius: 8px; border-left: 3px solid #38bdf8; font-size: 13px; color: #e2e8f0;">
                    🇹🇷 T.C. Resmi Gazete ve SBB onaylı kamu personel alımları, KPSS tercih kılavuzları, anlık memur, işçi, sağlık ve MEB atama duyuruları resmi kanalıdır. Sıfır bilgi kirliliği.<br><br>
                    🌐 Web: kamupersonelrehberi.com<br>
                    📸 Instagram: @kamupersonelrehberi
                </div>
            </div>
            """, unsafe_allow_html=True)

            st.markdown("""
            <div style="background: rgba(30, 41, 59, 0.7); border: 1px solid #334155; padding: 18px; border-radius: 12px;">
                <h4 style="color: #ec4899; margin: 0 0 10px 0;">📲 4. Viral İletilme (Forwarding) Butonu</h4>
                <p style="color: #cbd5e1; font-size: 13px;">
                    Sistemimizin Telegram yayıncısına entegre edilen <b>'📲 Arkadaşına İlet'</b> butonu sayesinde, 
                    adaylar tek tıkla ilanı WhatsApp veya Telegram gruplarına atar. İletilen her mesajın başlığındaki 
                    <code>@kamupersonelrehberi</code> bağlantısı kanala her gün onlarca bedava abone kazandırır.
                </p>
            </div>
            """, unsafe_allow_html=True)


# Modül tek başına test edilmek istendiğinde:
if __name__ == "__main__":
    st.set_page_config(page_title="Telegram Büyütme Modülü", layout="wide")
    telegram_buyutme_modulu()
