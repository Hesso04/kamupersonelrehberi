from typing import Optional, Dict, Any, Generator
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from loguru import logger

from config.settings import settings
from .models import Base, SystemSetting

import os

# Veritabanı URL çözümleme (Streamlit secrets, Ortam değişkeni ve postgres:// uyumluluğu)
db_url = settings.DATABASE_URL
try:
    import streamlit as st
    if hasattr(st, "secrets") and "DATABASE_URL" in st.secrets:
        db_url = st.secrets["DATABASE_URL"]
except Exception:
    pass

db_url = os.getenv("DATABASE_URL", db_url)
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

# Veritabanı motoru oluşturuluyor
connect_args = {}
if db_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
elif "pooler.supabase.com" in db_url or ":6543" in db_url or "supabase" in db_url:
    connect_args = {"prepare_threshold": None}

engine = create_engine(
    db_url,
    connect_args=connect_args,
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False, bind=engine)


@contextmanager
def get_db() -> Generator[Session, None, None]:
    """
    Oturum yönetimini sağlayan bağlam yöneticisi (Context Manager).
    Kullanım bittiğinde oturumu otomatik olarak kapatır, hata anında rollback yapar.
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error(f"Veritabanı oturum hatası: {exc}")
        raise
    finally:
        db.close()


def init_db() -> None:
    """
    Veritabanı tablolarını oluşturur ve ilk varsayılan sistem ayarlarını tohumlar (seed).
    """
    # 1. Tabloları oluştur
    Base.metadata.create_all(bind=engine)
    logger.info("Veritabanı tabloları başarıyla senkronize edildi.")

    # 2. Varsayılan ayarları tohumla
    default_settings = [
        {
            "key": "ACTIVE_AI_PROVIDER",
            "value": "NVIDIA NIM",
            "description": "Aktif Yapay Zeka Sağlayıcısı (NVIDIA NIM, Groq, Custom/OpenAI)",
            "is_secret": False
        },
        {
            "key": "NVIDIA_API_KEY",
            "value": "",
            "description": "NVIDIA NIM Cloud API Anahtarı (nvapi-...)",
            "is_secret": True
        },
        {
            "key": "NVIDIA_MODEL",
            "value": "meta/llama-3.2-11b-vision-instruct",
            "description": "NVIDIA NIM Modeli (Örn: meta/llama-3.2-11b-vision-instruct)",
            "is_secret": False
        },
        {
            "key": "CUSTOM_LLM_BASE_URL",
            "value": "https://api.deepseek.com/v1",
            "description": "Özel / OpenAI Uyumlu API Base URL (DeepSeek, OpenRouter, Ollama)",
            "is_secret": False
        },
        {
            "key": "CUSTOM_LLM_API_KEY",
            "value": "",
            "description": "Özel LLM API Anahtarı",
            "is_secret": True
        },
        {
            "key": "CUSTOM_LLM_MODEL",
            "value": "deepseek-chat",
            "description": "Özel LLM Model İsmi",
            "is_secret": False
        },
        {
            "key": "GROQ_API_KEY",
            "value": settings.GROQ_API_KEY or "",
            "description": "Groq Cloud API Anahtarı (Metin analizi ve özetleme için)",
            "is_secret": True
        },
        {
            "key": "GROQ_MODEL",
            "value": settings.GROQ_MODEL or "llama-3.3-70b-versatile",
            "description": "Kullanılacak Groq LLM Modeli",
            "is_secret": False
        },
        {
            "key": "TELEGRAM_BOT_TOKEN",
            "value": settings.TELEGRAM_BOT_TOKEN or "",
            "description": "Telegram Bot API Token (BotFather tarafından verilen token)",
            "is_secret": True
        },
        {
            "key": "TELEGRAM_CHANNEL_ID",
            "value": settings.TELEGRAM_CHANNEL_ID or "@kamupersonelrehberi",
            "description": "İlanların paylaşılacağı Telegram Kanalı (örn: @kamupersonelrehberi)",
            "is_secret": False
        },
        {
            "key": "WHATSAPP_ACCESS_TOKEN",
            "value": "",
            "description": "WhatsApp Cloud API Bearer Access Token",
            "is_secret": True
        },
        {
            "key": "WHATSAPP_PHONE_NUMBER_ID",
            "value": "",
            "description": "WhatsApp Phone Number ID veya Kanal ID",
            "is_secret": False
        },
        {
            "key": "INSTAGRAM_ACCESS_TOKEN",
            "value": "",
            "description": "Instagram Graph API Access Token (Facebook Login)",
            "is_secret": True
        },
        {
            "key": "INSTAGRAM_ACCOUNT_ID",
            "value": "",
            "description": "Instagram Business Account ID",
            "is_secret": False
        },
    ]

    with get_db() as db:
        for item in default_settings:
            existing = db.query(SystemSetting).filter_by(key=item["key"]).first()
            if not existing:
                setting_obj = SystemSetting(
                    key=item["key"],
                    value=item["value"],
                    description=item["description"],
                    is_secret=item["is_secret"]
                )
                db.add(setting_obj)
        logger.info("Varsayılan sistem ayarları kontrol edildi ve güncellendi.")


def get_system_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    """
    Veritabanından belirli bir ayar değerini okur.
    Eğer veritabanında henüz yoksa veya boşsa 'default' değeri döner.
    """
    try:
        with get_db() as db:
            setting = db.query(SystemSetting).filter_by(key=key).first()
            if setting and setting.value is not None and setting.value.strip() != "":
                return setting.value.strip()
    except Exception as e:
        logger.warning(f"Ayar okunamadı ({key}), varsayılana dönülüyor: {e}")
    return default


def set_system_setting(
    key: str,
    value: str,
    description: Optional[str] = None,
    is_secret: bool = False
) -> None:
    """
    Bir sistem ayarını veritabanına kaydeder veya varsa günceller.
    """
    with get_db() as db:
        setting = db.query(SystemSetting).filter_by(key=key).first()
        if setting:
            setting.value = value.strip() if value else ""
            if description:
                setting.description = description
        else:
            setting = SystemSetting(
                key=key,
                value=value.strip() if value else "",
                description=description,
                is_secret=is_secret
            )
            db.add(setting)
        logger.info(f"Sistem ayarı güncellendi: {key}")


def get_all_system_settings() -> Dict[str, Dict[str, Any]]:
    """
    Admin paneli için tüm ayarları sözlük olarak döner.
    """
    result = {}
    with get_db() as db:
        settings_list = db.query(SystemSetting).all()
        for s in settings_list:
            result[s.key] = {
                "key": s.key,
                "value": s.value or "",
                "description": s.description or "",
                "is_secret": s.is_secret,
                "updated_at": s.updated_at
            }
    return result


def bulk_update_system_settings(updates: Dict[str, str]) -> None:
    """
    Admin panelinden gelen form verilerini toplu olarak günceller.
    """
    with get_db() as db:
        for key, value in updates.items():
            setting = db.query(SystemSetting).filter_by(key=key).first()
            if setting:
                setting.value = value.strip() if value else ""
            else:
                db.add(SystemSetting(key=key, value=value.strip() if value else ""))
        logger.info(f"{len(updates)} adet sistem ayarı topluca kaydedildi.")
