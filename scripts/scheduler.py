"""
KAMU PERSONEL REHBERİ — MERKEZİ OTOMATİK ZAMANLAYICI (Scheduler v2.0)
=======================================================================
Periyodik görevleri yönetir:
  [A] Her 3 saatte bir: Resmi kamu haberleri taraması (memurlar.net, ÖSYM, TOKİ, MEB, AA, SGK, DPB vb.)
  [B] Her 6 saatte bir: Kamu ilanı taraması (SBB, İŞKUR, Kariyer Kapısı, Resmi Gazete)
  [C] Her 4 saatte bir: Yayın kuyruğu işleme (Telegram + Instagram)
  [D] Her 12 saatte bir: İçerik kalite denetimi ve filtre istatistikleri

Patron panelinden tek tıkla başlatılıp durdurulabilir.
Yeni Nesil Editoryal Motor v2.0 ile entegre çalışır.
"""

import os
import sys
import time
import signal
import threading
from datetime import datetime, timedelta
from typing import Optional
from loguru import logger

# Proje kök dizini
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from core.database import get_system_setting, set_system_setting


# ============================================================
# ZAMANLAYICI AYARLARI (Patron Panelinden Değiştirilebilir)
# ============================================================
DEFAULT_NEWS_INTERVAL_HOURS = 3       # Haber tarama aralığı (saat)
DEFAULT_JOBS_INTERVAL_HOURS = 6       # İlan tarama aralığı (saat)
DEFAULT_PUBLISH_INTERVAL_HOURS = 4    # Yayın kuyruğu aralığı (saat)
DEFAULT_AUDIT_INTERVAL_HOURS = 12     # Kalite denetimi aralığı (saat)
DEFAULT_PUBLISH_LIMIT = 3             # Her döngüde yayınlanacak max haber


class SchedulerTask:
    """Periyodik bir görevi tanımlar."""

    def __init__(self, name: str, interval_hours: float, func, enabled_key: str, enabled_default: str = "true"):
        self.name = name
        self.interval_hours = interval_hours
        self.func = func
        self.enabled_key = enabled_key
        self.enabled_default = enabled_default
        self.last_run: Optional[datetime] = None
        self.run_count = 0
        self.error_count = 0

    @property
    def is_enabled(self) -> bool:
        val = get_system_setting(self.enabled_key, self.enabled_default)
        return str(val).strip().lower() in ["true", "1", "yes", "on", "aktif"]

    @property
    def is_due(self) -> bool:
        if not self.last_run:
            return True
        return datetime.utcnow() >= self.last_run + timedelta(hours=self.interval_hours)

    def run(self):
        if not self.is_enabled:
            logger.debug(f"[Zamanlayıcı] '{self.name}' devre dışı, atlanıyor.")
            return
        if not self.is_due:
            return
        try:
            logger.info(f"⏱️ [Zamanlayıcı] '{self.name}' görevi başlatılıyor...")
            self.func()
            self.last_run = datetime.utcnow()
            self.run_count += 1
            logger.info(f"✅ [Zamanlayıcı] '{self.name}' tamamlandı. (Toplam: {self.run_count}x çalıştı)")
        except Exception as e:
            self.error_count += 1
            logger.error(f"❌ [Zamanlayıcı] '{self.name}' hatası #{self.error_count}: {e}")


# ============================================================
# GÖREV FONKSİYONLARI
# ============================================================

def task_scrape_news():
    """
    [A] Kamu haberleri taraması.
    Tüm resmi kaynaklardan (memurlar.net, ÖSYM, TOKİ, MEB, SGK, DPB, AA vb.)
    filtrelenmiş haberleri toplar ve veritabanına kaydeder.
    """
    from scrapers.official_news import run_news_scraper
    count = run_news_scraper()
    logger.info(f"📰 Haber taraması: {count} yeni haber veritabanına eklendi.")


def task_scrape_jobs():
    """
    [B] Kamu ilanı taraması.
    SBB, İŞKUR, Kariyer Kapısı, Resmi Gazete, CSB ve diğer kaynaklardan
    yeni personel alım ilanlarını toplar.
    """
    try:
        from scrapers.manager import ScraperManager
        manager = ScraperManager()
        result = manager.run_all()
        logger.info(f"📋 İlan taraması: {result.get('total_saved', 0)} yeni ilan kaydedildi.")
    except Exception as e:
        logger.error(f"İlan taraması hatası: {e}")


def task_publish_queue():
    """
    [C] Yayın kuyruğu işleme.
    Paylaşılmayı bekleyen haberleri ve ilanları Telegram + Instagram'a gönderir.
    Yalnızca AUTO_PUBLISH_NEWS_ENABLED aktifse çalışır.
    """
    from publishers.news_publisher import NewsPublisherManager
    manager = NewsPublisherManager()
    result = manager.publish_pending_news(
        limit=int(get_system_setting("SCHEDULER_PUBLISH_LIMIT", str(DEFAULT_PUBLISH_LIMIT)))
    )
    published = result.get("published", 0)
    if published > 0:
        logger.info(f"📤 Yayın kuyruğu: {published} haber yayınlandı.")
    else:
        logger.debug(f"📤 Yayın kuyruğu: Yayınlanacak yeni haber yok veya otomasyon kapalı.")


def task_quality_audit():
    """
    [D] Filtre istatistikleri ve kalite denetimi.
    Son 12 saatte kaç haber elendi, kaç tanesinin yüksek relevance skoru var gibi
    temel metrikleri loglar ve sistem ayarına yazar.
    """
    try:
        from core.database import get_db
        from core.models import OfficialNews
        from sqlalchemy import func

        with get_db() as db:
            total = db.query(func.count(OfficialNews.id)).scalar() or 0
            unpublished = db.query(func.count(OfficialNews.id)).filter(
                OfficialNews.is_social_published == False
            ).scalar() or 0
            published = total - unpublished

        audit_msg = (
            f"📊 [Kalite Denetimi] Toplam haber DB: {total} | "
            f"Yayınlandı: {published} | Bekliyor: {unpublished}"
        )
        logger.info(audit_msg)
        set_system_setting("LAST_AUDIT_RESULT", audit_msg)
        set_system_setting("LAST_AUDIT_TIME", datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"))
    except Exception as e:
        logger.warning(f"Kalite denetimi hatası: {e}")


# ============================================================
# ANA ZAMANLAYICI SINIFI
# ============================================================

class KamuScheduler:
    """
    Kamu Personel Rehberi merkezi görev zamanlayıcısı.
    Thread tabanlı, ana süreci bloke etmeden arka planda çalışır.
    """

    _instance: Optional["KamuScheduler"] = None
    _lock = threading.Lock()

    def __init__(self):
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._tasks = [
            SchedulerTask(
                name="Kamu Haberleri Taraması",
                interval_hours=float(get_system_setting("SCHEDULER_NEWS_INTERVAL", str(DEFAULT_NEWS_INTERVAL_HOURS))),
                func=task_scrape_news,
                enabled_key="SCHEDULER_NEWS_ENABLED",
                enabled_default="true"
            ),
            SchedulerTask(
                name="Kamu İlanları Taraması",
                interval_hours=float(get_system_setting("SCHEDULER_JOBS_INTERVAL", str(DEFAULT_JOBS_INTERVAL_HOURS))),
                func=task_scrape_jobs,
                enabled_key="SCHEDULER_JOBS_ENABLED",
                enabled_default="true"
            ),
            SchedulerTask(
                name="Yayın Kuyruğu İşleme",
                interval_hours=float(get_system_setting("SCHEDULER_PUBLISH_INTERVAL", str(DEFAULT_PUBLISH_INTERVAL_HOURS))),
                func=task_publish_queue,
                enabled_key="SCHEDULER_PUBLISH_ENABLED",
                enabled_default="false"   # Varsayılan kapalı — Patron panelinden açılır
            ),
            SchedulerTask(
                name="Kalite Denetimi",
                interval_hours=float(get_system_setting("SCHEDULER_AUDIT_INTERVAL", str(DEFAULT_AUDIT_INTERVAL_HOURS))),
                func=task_quality_audit,
                enabled_key="SCHEDULER_AUDIT_ENABLED",
                enabled_default="true"
            ),
        ]

    @classmethod
    def get_instance(cls) -> "KamuScheduler":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
        return cls._instance

    def start(self):
        """Zamanlayıcıyı arka plan thread'inde başlatır."""
        if self._running:
            logger.warning("Zamanlayıcı zaten çalışıyor.")
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="KamuScheduler")
        self._thread.start()
        logger.info("🚀 KamuScheduler arka plan thread'i başlatıldı.")
        set_system_setting("SCHEDULER_STATUS", "running")
        set_system_setting("SCHEDULER_STARTED_AT", datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"))

    def stop(self):
        """Zamanlayıcıyı durdurur."""
        self._running = False
        logger.info("⏹️ KamuScheduler durduruldu.")
        set_system_setting("SCHEDULER_STATUS", "stopped")

    def is_running(self) -> bool:
        return self._running and (self._thread is not None) and self._thread.is_alive()

    def _loop(self):
        """Ana döngü: 60 saniyede bir tüm görevleri kontrol eder."""
        logger.info("⏱️ KamuScheduler döngüsü başladı (60s kontrol aralığı).")
        while self._running:
            for task in self._tasks:
                try:
                    task.run()
                except Exception as e:
                    logger.error(f"Zamanlayıcı döngü hatası [{task.name}]: {e}")
            time.sleep(60)  # 60 saniye bekle

    def get_status(self) -> dict:
        """Tüm görevlerin anlık durumunu döner."""
        return {
            "running": self.is_running(),
            "tasks": [
                {
                    "name": t.name,
                    "enabled": t.is_enabled,
                    "interval_hours": t.interval_hours,
                    "last_run": t.last_run.strftime("%Y-%m-%d %H:%M UTC") if t.last_run else "Henüz çalışmadı",
                    "is_due": t.is_due,
                    "run_count": t.run_count,
                    "error_count": t.error_count,
                }
                for t in self._tasks
            ]
        }

    def trigger_task(self, task_name: str) -> bool:
        """Belirli bir görevi manuel olarak tetikler (Patron paneli için)."""
        for task in self._tasks:
            if task.name == task_name:
                task.last_run = None  # Zorunlu çalıştırma için sıfırla
                task.run()
                return True
        return False


# ============================================================
# SINGLETON ERİŞİM FONKSİYONLARI (Diğer modüllerden kullanım için)
# ============================================================

def start_scheduler():
    """Singleton zamanlayıcıyı başlatır."""
    KamuScheduler.get_instance().start()


def stop_scheduler():
    """Singleton zamanlayıcıyı durdurur."""
    KamuScheduler.get_instance().stop()


def get_scheduler_status() -> dict:
    """Zamanlayıcı durumunu döner."""
    return KamuScheduler.get_instance().get_status()


def trigger_manual_task(task_name: str) -> bool:
    """Patron paneli için manuel görev tetikleme."""
    return KamuScheduler.get_instance().trigger_task(task_name)


# ============================================================
# DOĞRUDAN ÇALIŞTIRMA (Test / Daemon modu)
# ============================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Kamu Personel Rehberi Görev Zamanlayıcısı")
    parser.add_argument("--daemon", action="store_true", help="Daemon modunda sürekli çalıştır")
    parser.add_argument("--once", choices=["news", "jobs", "publish", "audit"], help="Tek seferlik görev çalıştır")
    args = parser.parse_args()

    if args.once == "news":
        logger.info("Tek seferlik: Haber taraması başlatılıyor...")
        task_scrape_news()
    elif args.once == "jobs":
        logger.info("Tek seferlik: İlan taraması başlatılıyor...")
        task_scrape_jobs()
    elif args.once == "publish":
        logger.info("Tek seferlik: Yayın kuyruğu işleniyor...")
        task_publish_queue()
    elif args.once == "audit":
        logger.info("Tek seferlik: Kalite denetimi çalışıyor...")
        task_quality_audit()
    elif args.daemon:
        logger.info("Daemon modu: Sürekli çalışıyor (Ctrl+C ile durdurun)...")

        def handle_signal(sig, frame):
            logger.info("Sinyal alındı, zamanlayıcı durduruluyor...")
            stop_scheduler()
            sys.exit(0)

        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

        start_scheduler()
        # Ana thread'i canlı tut
        while True:
            time.sleep(30)
            status = get_scheduler_status()
            logger.debug(f"Zamanlayıcı canlı - {len(status['tasks'])} görev kayıtlı.")
    else:
        parser.print_help()
