import enum
from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Boolean,
    DateTime,
    Enum as SQLEnum,
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class JobStatus(str, enum.Enum):
    """İlanın yaşam döngüsü durumları (State Machine)"""
    DRAFT = "DRAFT"                          # Kazıyıcıdan ham geldi
    AI_PROCESSED = "AI_PROCESSED"            # Groq ile temizlendi ve ayrıştırıldı
    PENDING_APPROVAL = "PENDING_APPROVAL"    # Admin panelinde onay bekliyor
    APPROVED = "APPROVED"                    # Admin onayladı, yayına hazır
    REJECTED = "REJECTED"                    # Admin tarafından reddedildi / tık tuzağı
    PUBLISHED = "PUBLISHED"                  # Sosyal kanallara başarıyla gönderildi
    FAILED = "FAILED"                        # Yayınlanırken hata oluştu


class Platform(str, enum.Enum):
    """Dağıtım yapılacak sosyal medya platformları"""
    TELEGRAM = "TELEGRAM"
    WHATSAPP = "WHATSAPP"
    INSTAGRAM = "INSTAGRAM"


class SystemSetting(Base):
    """
    Sistem Ayarları Tablosu:
    Admin panelinden dinamik olarak yönetilen API anahtarları, model isimleri
    ve sosyal medya konfigürasyonlarını kalıcı olarak saklar.
    """
    __tablename__ = "system_settings"

    key = Column(String(100), primary_key=True, index=True, doc="Ayar anahtarı (örn: GROQ_API_KEY)")
    value = Column(Text, nullable=True, doc="Ayar değeri")
    description = Column(String(255), nullable=True, doc="Ayarın kullanıcı dostu açıklaması")
    is_secret = Column(Boolean, default=False, doc="Arayüzde maskelenip maskelenmeyeceği")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        masked_val = "***" if self.is_secret and self.value else self.value
        return f"<SystemSetting(key='{self.key}', value='{masked_val}')>"


class JobAnnouncement(Base):
    """
    Kamu Personel Alım İlanları Tablosu:
    Resmi kaynaklardan doğrulanan, AI ile zenginleştirilen ve insan onayından geçen
    tüm ilan havuzunun ana veri modeli.
    """
    __tablename__ = "job_announcements"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Temel İlan Bilgileri
    title = Column(String(350), nullable=False, index=True, doc="İlan başlığı")
    institution = Column(String(250), nullable=True, index=True, doc="İlanı açan kamu kurumu")
    position = Column(String(300), nullable=True, doc="Alım yapılacak kadro / ünvan")
    city = Column(String(150), nullable=True, doc="Görev yeri / şehir")
    total_positions = Column(Integer, nullable=True, default=1, doc="Alınacak toplam personel sayısı")
    kpss_requirement = Column(String(150), nullable=True, doc="KPSS şartı (Örn: KPSS P3 En az 65, KPSS Şartsız)")
    education_level = Column(String(200), nullable=True, doc="Mezuniyet şartı (Lisans, Ön Lisans, Lise vb.)")

    # Tarihler
    application_start_date = Column(DateTime, nullable=True, doc="Başvuru başlangıç tarihi")
    application_end_date = Column(DateTime, nullable=True, doc="Son başvuru tarihi")

    # Resmi Kaynak & Güvenilirlik Denetimi
    source_name = Column(String(100), nullable=False, doc="Kaynak (Resmi Gazete, SBB Kamu İlan, İŞKUR)")
    source_url = Column(Text, nullable=False, doc="İlanın internet adresi")
    official_doc_url = Column(Text, nullable=True, doc="Resmi Gazete sayısı / Orijinal PDF bağlantısı")
    is_verified = Column(Boolean, default=True, doc="Resmi kurum alan adı (.gov.tr vb.) doğrulandı mı?")

    # Yapay Zeka Çıktıları
    raw_content = Column(Text, nullable=True, doc="Kazınan ham duyuru metni")
    ai_summary = Column(Text, nullable=True, doc="AI tarafından çıkartılan maddeli özet")
    social_post_text = Column(Text, nullable=True, doc="Telegram ve sosyal medya için üretilen hazır metin")
    image_path = Column(Text, nullable=True, doc="Pillow ile üretilen ilan kartı görseli")
    pdf_path = Column(Text, nullable=True, doc="İndirilen resmi PDF kılavuzunun yerel dosya yolu")

    # Durum ve Onay Yönetimi (Human-in-the-Loop)
    status = Column(
        SQLEnum(JobStatus),
        default=JobStatus.PENDING_APPROVAL,
        nullable=False,
        index=True,
        doc="İlanın güncel onay ve yayın durumu"
    )
    admin_notes = Column(Text, nullable=True, doc="Adminin bıraktığı not veya red gerekçesi")
    published_channels = Column(Text, nullable=True, doc="Yayınlanan kanalların listesi (virgülle ayrılmış)")

    # Sistem Zaman Damgaları
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    published_at = Column(DateTime, nullable=True, doc="Yayına girdiği an")

    def __repr__(self) -> str:
        return f"<JobAnnouncement(id={self.id}, institution='{self.institution}', status='{self.status}')>"
