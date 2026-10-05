"""
SQLite veritabanındaki tüm ilan ve sistem ayarlarını
Supabase PostgreSQL veritabanına eksiksiz ve hızlı aktaran migrasyon scripti.
"""
import sys
from loguru import logger
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from core.models import Base, JobAnnouncement, SystemSetting
from config.settings import ROOT_DIR


def migrate(target_postgres_url: str):
    sqlite_url = f"sqlite:///{ROOT_DIR / 'data' / 'kamu.db'}"
    logger.info(f"Kaynak (SQLite): {sqlite_url}")
    logger.info("Hedef (PostgreSQL): Bağlanılıyor...")

    sqlite_engine = create_engine(sqlite_url, connect_args={"check_same_thread": False})
    connect_args = {"prepare_threshold": None} if ("pooler.supabase.com" in target_postgres_url or ":6543" in target_postgres_url or "supabase" in target_postgres_url) else {}
    pg_engine = create_engine(target_postgres_url, connect_args=connect_args, echo=False)

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

        # 2. JobAnnouncements Toplu Aktarımı
        jobs = sqlite_db.query(JobAnnouncement).order_by(JobAnnouncement.id.asc()).all()
        logger.info(f"{len(jobs)} adet kamu ilanı aktarılıyor...")

        # Hedefteki eski/eksik kayıtları temizle (tekrarı önlemek için)
        pg_db.execute(text("TRUNCATE TABLE job_announcements RESTART IDENTITY CASCADE;"))
        pg_db.commit()

        new_jobs = []
        for job in jobs:
            new_job = JobAnnouncement(
                id=job.id,
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
            new_jobs.append(new_job)

        pg_db.add_all(new_jobs)
        pg_db.commit()

        # PostgreSQL ID sequence'ini en son ID'ye güncelle
        pg_db.execute(text("SELECT setval(pg_get_serial_sequence('job_announcements', 'id'), coalesce(max(id), 1)) FROM job_announcements;"))
        pg_db.commit()

        total_pg_jobs = pg_db.query(JobAnnouncement).count()
        logger.info(f"🎉 MÜKEMMEL! Toplam {total_pg_jobs} kamu ilanı eksiksiz olarak Supabase'e aktarıldı!")

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
