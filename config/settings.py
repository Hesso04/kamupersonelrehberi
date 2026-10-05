from pathlib import Path
from typing import Optional, Any
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Proje Kök Dizini (kamupersonelrehberi)
ROOT_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """
    Kamu Personel Rehberi - Merkezi Ayar ve Konfigürasyon Yöneticisi
    Statik dosya ve ortam değişkenlerini yönetir, veritabanındaki dinamik ayarlar için köprü kurar.
    """

    # Uygulama Temel Ayarları
    APP_NAME: str = Field(default="Kamu Personel Rehberi", description="Uygulama adı")
    APP_ENV: str = Field(default="development", description="Çalışma ortamı: development / production")
    DEBUG: bool = Field(default=True, description="Hata ayıklama modu")
    SECRET_KEY: str = Field(
        default="super-secret-key-change-me-in-production",
        description="Oturum güvenliği için anahtar"
    )

    # Veritabanı Ayarları
    DATABASE_URL: str = Field(
        default=f"sqlite:///{ROOT_DIR / 'data' / 'kamu.db'}",
        description="SQLAlchemy uyumlu veritabanı bağlantı URI'si"
    )

    # Statik / Çevresel Fallback Ayarları (.env dosyası veya sistem ortamı)
    GROQ_API_KEY: Optional[str] = Field(default=None, description="Groq API anahtarı (Varsayılan)")
    GROQ_MODEL: str = Field(
        default="llama-3.3-70b-versatile",
        description="Varsayılan Groq LLM modeli"
    )
    TELEGRAM_BOT_TOKEN: Optional[str] = Field(default=None, description="Telegram Bot Token (Varsayılan)")
    TELEGRAM_CHANNEL_ID: Optional[str] = Field(
        default=None,
        description="Paylaşım yapılacak Telegram kanalı (örn: @kamupersonelrehberi)"
    )

    # Admin Paneli Erişim Bilgileri
    ADMIN_USERNAME: str = Field(default="admin", description="Admin panel kullanıcı adı")
    ADMIN_PASSWORD: str = Field(default="kamu_secure_password_123", description="Admin panel parolası")

    # Dizin Yolları
    DATA_DIR: Path = Field(default_factory=lambda: ROOT_DIR / "data")
    IMAGE_OUTPUT_DIR: Path = Field(default_factory=lambda: ROOT_DIR / "graphics" / "output")
    ASSETS_DIR: Path = Field(default_factory=lambda: ROOT_DIR / "graphics" / "assets")
    FONTS_DIR: Path = Field(default_factory=lambda: ROOT_DIR / "graphics" / "assets" / "fonts")
    TEMPLATES_DIR: Path = Field(default_factory=lambda: ROOT_DIR / "graphics" / "assets" / "templates")

    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True
    )

    def init_directories(self) -> None:
        """Sistemin ihtiyaç duyduğu temel dizinlerin mevcut olduğundan emin olur."""
        for directory in [self.DATA_DIR, self.IMAGE_OUTPUT_DIR, self.FONTS_DIR, self.TEMPLATES_DIR]:
            directory.mkdir(parents=True, exist_ok=True)

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.lower() == "production"

    # =========================================================================
    # DİNAMİK VERİTABANI AYARLARI (Admin Panelinden Yönetilen Canlı Değerler)
    # =========================================================================

    def get_dynamic(self, key: str, fallback: Optional[Any] = None) -> Optional[Any]:
        """
        Veritabanından en güncel ayar değerini çeker.
        Eğer veritabanında henüz ayarlanmamışsa 'fallback' değerini döner.
        """
        try:
            from core.database import get_system_setting
            val = get_system_setting(key)
            if val is not None and val != "":
                return val
        except Exception:
            pass
        return fallback

    @property
    def active_groq_api_key(self) -> Optional[str]:
        """Admin panelinde güncellenen aktif Groq API anahtarını döner."""
        return self.get_dynamic("GROQ_API_KEY", self.GROQ_API_KEY)

    @property
    def active_groq_model(self) -> str:
        """Admin panelinde seçilen aktif Groq modelini döner."""
        return self.get_dynamic("GROQ_MODEL", self.GROQ_MODEL) or "llama-3.3-70b-versatile"

    @property
    def active_telegram_bot_token(self) -> Optional[str]:
        """Admin panelinde güncellenen aktif Telegram bot tokenını döner."""
        return self.get_dynamic("TELEGRAM_BOT_TOKEN", self.TELEGRAM_BOT_TOKEN)

    @property
    def active_telegram_channel_id(self) -> Optional[str]:
        """Admin panelinde güncellenen aktif Telegram kanalını döner."""
        return self.get_dynamic("TELEGRAM_CHANNEL_ID", self.TELEGRAM_CHANNEL_ID)

    @property
    def is_groq_configured(self) -> bool:
        key = self.active_groq_api_key
        return bool(key and key != "gsk_your_groq_api_key_here")

    @property
    def is_telegram_configured(self) -> bool:
        token = self.active_telegram_bot_token
        channel = self.active_telegram_channel_id
        return bool(token and channel)


# Global Tekil Ayar Nesnesi (Singleton)
settings = Settings()
settings.init_directories()
