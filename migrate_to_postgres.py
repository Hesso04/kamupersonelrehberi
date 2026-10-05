"""
SQLite veritabanındaki tüm ilan ve sistem ayarlarını
Supabase PostgreSQL veritabanına aktaran migrasyon scripti.
"""
import sys
from loguru import logger
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.models import Base, JobAnnouncement, SystemSetting
from config.settings import ROOT_DIR


def migrate(target_postgres_url: str):
    sqlite_url = f"sqlite:///{ROOT_DIR / 'data' / 'kamu.db'}"
    logger.info(f"Kaynak (SQLite): {sqlite_url}")
    logger.info("Hedef (PostgreSQL): Bağlanılıyor...")

    # Bağlantılar
    sqlite_engine = create_engine(sqlite_url, connect_args={"check_same_thread": False})
    pg_engine = create_engine(target_postgres_url, echo=False)

    # Hedefte tabloları oluştur
    Base.metadata.create_all(bind=pg_engine)
    logger.info("Hedef veritabanında tablolar hazırlandı.")

    SqliteSession = sessionmaker(bind=sqlite_engine)
    PgSession = sessionmaker(bind=pg_engine)

    sqlite_db = SqliteSession()
    pg_db = PgSession()

    try:
        # 1. SystemSettings Aktarımı
        settings = sqlite_db.query(SystemSetting).all()
        logger.info(f"{len(settings)} adet sistem ayarı aktarılıyor...")
        for s in settings:
            existing = pg_db.query(SystemSetting).filter_by(key=s.key).first()
            if not existing:
                new_s = SystemSetting(
                    key=s.key,
                    value=s.value,
                    description=s.description,
                    is_secret=s.is_secret,
                    updated_at=s.updated_at
                )
                pg_db.add(new_s)
            else:
                existing.value = s.value
                existing.is_secret = s.is_secret
        pg_db.commit()
        logger.info("Sistem ayarları başarıyla aktarıldı.")

        # 2. JobAnnouncements Aktarımı
        jobs = sqlite_db.query(JobAnnouncement).order_by(JobAnnouncement.id.asc()).all()
        logger.info(f"{len(jobs)} adet kamu ilanı aktarılıyor...")
        
        migrated_count = 0
        for job in jobs:
            existing_job = pg_db.query(JobAnnouncement).filter_by(source_url=job.source_url).first()
            if not existing_job:
                new_job = JobAnnouncement(
                    title=job.title,
                    institution=job.institution,
                    position=job.position,
                    city=job.city,
                    total_positions=job.total_positions,
                    kpss_requirement=job.kpss_requirement,
                    education_level=job.education_level,
                    application_start_date=job.application_start_date,
                    application_end_date=job.application_end_date,
                    source_name=job.source_name,
                    source_url=job.source_url,
                    official_doc_url=job.official_doc_url,
                    is_verified=job.is_verified,
                    raw_content=job.raw_content,
                    ai_summary=job.ai_summary,
                    social_post_text=job.social_post_text,
                    image_path=job.image_path,
                    pdf_path=job.pdf_path,
                    status=job.status,
                    admin_notes=job.admin_notes,
                    published_channels=job.published_channels,
                    created_at=job.created_at,
                    updated_at=job.updated_at,
                    published_at=job.published_at
                )
                pg_db.add(new_job)
                migrated_count += 1
                if migrated_count % 100 == 0:
                    pg_db.commit()
                    logger.info(f"İlerleme: {migrated_count}/{len(jobs)} ilan aktarıldı.")

        pg_db.commit()
        logger.info(f"BAŞARILI! Toplam {migrated_count} yeni ilan PostgreSQL'e aktarıldı.")

    except Exception as e:
        pg_db.rollback()
        logger.error(f"Aktarım hatası: {e}")
        raise
    finally:
        sqlite_db.close()
        pg_db.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Kullanım: python migrate_to_postgres.py <POSTGRES_DATABASE_URL>")
        sys.exit(1)
    migrate(sys.argv[1])
