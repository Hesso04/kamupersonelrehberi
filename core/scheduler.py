import time
import threading
from datetime import datetime
from typing import Dict, Any, Optional, List
from loguru import logger

from scrapers.manager import ScraperManager
from ai.processor import AIProcessor
from publishers.manager import PublisherManager
from core.database import get_db, get_system_setting, set_system_setting
from core.models import JobAnnouncement, JobStatus


AUTOPILOT_PACE_PRESETS = {
    "1_PER_HOUR": {
        "name": "Saatte 1 Paylaşım (Anti-Spam / En Güvenli)",
        "short_name": "Saatte 1 İlan",
        "desc": "Her 60 dakikada 1 ilan yayınlar. Sosyal medya algoritmaları için ideal ve risksizdir.",
        "interval_seconds": 3600,
    },
    "3_PER_2HOURS": {
        "name": "2 Saatte 3 Paylaşım (Dengeli Akış)",
        "short_name": "2 Saatte 3 İlan",
        "desc": "Her 40 dakikada 1 ilan yayınlar (2 saatte 3 ilan). Yüksek etkileşim sağlar.",
        "interval_seconds": 2400,
    },
    "5_PER_2HOURS": {
        "name": "2 Saatte 5 Paylaşım (Hızlı İlan Akışı)",
        "short_name": "2 Saatte 5 İlan",
        "desc": "Her 24 dakikada 1 ilan yayınlar (2 saatte 5 ilan). Yoğun ilan dönemleri için uygundur.",
        "interval_seconds": 1440,
    },
    "2_PER_HOUR": {
        "name": "Saatte 2 Paylaşım (30 dk ara)",
        "short_name": "Saatte 2 İlan",
        "desc": "Her 30 dakikada 1 ilan yayınlar.",
        "interval_seconds": 1800,
    },
    "1_PER_2HOURS": {
        "name": "2 Saatte 1 Paylaşım (Sakin Akış - 120 dk ara)",
        "short_name": "2 Saatte 1 İlan",
        "desc": "Her 2 saatte 1 ilan yayınlar.",
        "interval_seconds": 7200,
    },
    "TEST_FAST": {
        "name": "Hızlı Test Modu (3 dk ara)",
        "short_name": "Test (3 dk)",
        "desc": "Sistemi ve kanalları hızlıca test etmek için her 3 dakikada bir paylaşır.",
        "interval_seconds": 180,
    },
}


class BackgroundScheduler:
    """
    Kamu Personel Rehberi - Arka Plan Otomasyon ve Tarayıcı Servisi.
    Belirlenen aralıklarla resmi kaynakları otomatik tarar,
    yeni gelen ilanları AI ile zenginleştirir.
    
    OTOPİLOT ÖZELLİĞİ:
    Eğer 'MANUAL_APPROVAL_REQUIRED' ayarı kapalıysa (False),
    resmi (.gov.tr) kaynaklardan doğrulanmış ve daha önce paylaşılmamış
    tüm ilanlar otomatik olarak görselleri ve PDF kılavuzlarıyla kanallara dağıtılır.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(BackgroundScheduler, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.is_running = False
        self.interval_minutes = 30
        self.last_run_time: Optional[datetime] = None
        self.last_autopilot_publish_time: Optional[datetime] = None
        self.last_result: Dict[str, Any] = {}
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def run_autopilot_publish(self, limit: int = 10) -> int:
        """
        Manuel onay kapalıyken güvenilir kaynaklı ve
        daha önce paylaşılmamış ilanları otomatik olarak kanallara yayınlar.
        """
        published_count = 0
        with get_db() as db:
            # Güvenilir (.gov.tr), onaylanmamış/reddedilmemiş, henüz yayınlanmamış ilanlar
            target_jobs = db.query(JobAnnouncement).filter(
                JobAnnouncement.is_verified == True,
                JobAnnouncement.status != JobStatus.PUBLISHED,
                JobAnnouncement.status != JobStatus.REJECTED,
                JobAnnouncement.published_at == None
            ).order_by(JobAnnouncement.id.asc()).limit(limit).all()

            job_ids = [j.id for j in target_jobs]

        if not job_ids:
            return 0

        logger.info(f"[OTOPİLOT] {len(job_ids)} adet doğrulanmış ilan otomatik yayına hazırlanıyor...")

        ai_processor = AIProcessor()
        publisher = PublisherManager()

        for j_id in job_ids:
            try:
                # 1. AI ile zenginleştir (eğer henüz metin yoksa)
                with get_db() as db:
                    job = db.query(JobAnnouncement).filter(JobAnnouncement.id == j_id).first()
                    if job and not job.social_post_text:
                        ai_processor.process_job(job.id)

                # 2. Seçili aktif kanallarda (Telegram, Instagram, Facebook) yayınla
                raw_ap = get_system_setting("AUTOPILOT_CHANNELS", "TELEGRAM,INSTAGRAM,FACEBOOK")
                configured_channels = [c.strip().upper() for c in raw_ap.split(",") if c.strip()]

                target_channels = []
                if "TELEGRAM" in configured_channels:
                    target_channels.append("TELEGRAM")
                if "INSTAGRAM" in configured_channels and getattr(publisher.instagram, "is_configured", False):
                    target_channels.append("INSTAGRAM")
                if "FACEBOOK" in configured_channels and getattr(publisher.facebook, "is_configured", False):
                    target_channels.append("FACEBOOK")
                if "WHATSAPP" in configured_channels and publisher.whatsapp.is_logged_in():
                    target_channels.append("WHATSAPP")

                if not target_channels:
                    target_channels = ["TELEGRAM"]

                default_theme = get_system_setting("DEFAULT_CARD_THEME", "DARK_NOIR")
                logger.info(f"[OTOPİLOT] İlan #{j_id} şu kanallara dağıtılıyor: {target_channels} (Tema: {default_theme})")
                results = publisher.publish_job(j_id, channels=target_channels, theme=default_theme)
                
                # Herhangi bir kanalda başarı sağlandıysa başarılı say
                any_success = any(succ for succ, _ in results.values())
                if any_success:
                    published_count += 1
                    logger.info(f"[OTOPİLOT] İlan #{j_id} başarıyla otomatik yayınlandı: {results}")
                else:
                    logger.warning(f"[OTOPİLOT] İlan #{j_id} yayınlanamadı: {results}")
            except Exception as ex:
                logger.error(f"[OTOPİLOT] İlan #{j_id} işleme hatası: {ex}")

        return published_count

    def _worker(self):
        logger.info(f"Arka plan zamanlayıcı ve otopilot motoru başlatıldı. Tarama aralığı: {self.interval_minutes} dk.")
        last_scan_time = datetime.min

        while not self._stop_event.is_set():
            try:
                now = datetime.now()
                manual_mode = get_system_setting("MANUAL_APPROVAL_REQUIRED", "true") == "true"
                auto_scan = get_system_setting("AUTO_SCAN_ENABLED", "true") == "true"

                # 1. Periyodik Resmi Kaynak Taraması (Her interval_minutes dakikada bir)
                if auto_scan and (now - last_scan_time).total_seconds() >= self.interval_minutes * 60:
                    last_scan_time = now
                    self.last_run_time = now
                    logger.info("Resmi kaynak taraması çalışıyor...")
                    sm = ScraperManager()
                    scan_res = sm.run_all()
                    self.last_result = scan_res

                # 2. Otopilot Motoru (Manuel Onay Kapalıysa Güvenilir İlanları Belirlenen Tempoda Otomatik Yayınla)
                if not manual_mode:
                    pace_key = get_system_setting("AUTOPILOT_PACE_PRESET", "1_PER_HOUR")
                    pace_cfg = AUTOPILOT_PACE_PRESETS.get(pace_key, AUTOPILOT_PACE_PRESETS["1_PER_HOUR"])
                    interval_sec = pace_cfg["interval_seconds"]

                    if self.last_autopilot_publish_time is None:
                        should_publish = True
                    else:
                        elapsed = (now - self.last_autopilot_publish_time).total_seconds()
                        should_publish = elapsed >= interval_sec

                    if should_publish:
                        pub_count = self.run_autopilot_publish(limit=1)
                        if pub_count > 0:
                            self.last_autopilot_publish_time = now
                            logger.info(f"[OTOPİLOT] 1 ilan başarıyla paylaşıldı. Belirlenen tempo ({pace_cfg['name']}) gereği bir sonraki ilan için {interval_sec} saniye bekleniyor.")

            except Exception as e:
                logger.error(f"Zamanlayıcı / Otopilot döngü hatası: {e}")

            # 5 saniyelik hafif bekleme (kullanıcı ayar değiştirdiğinde anında tepki verir)
            if self._stop_event.wait(timeout=5):
                break

        logger.info("Arka plan zamanlayıcı durduruldu.")

    def get_autopilot_status(self) -> Dict[str, Any]:
        """Otopilotun güncel durumunu, seçili temposunu ve sonraki paylaşım geri sayımını döndürür."""
        pace_key = get_system_setting("AUTOPILOT_PACE_PRESET", "1_PER_HOUR")
        pace_cfg = AUTOPILOT_PACE_PRESETS.get(pace_key, AUTOPILOT_PACE_PRESETS["1_PER_HOUR"])
        interval_sec = pace_cfg["interval_seconds"]

        now = datetime.now()
        if self.last_autopilot_publish_time is not None:
            elapsed = (now - self.last_autopilot_publish_time).total_seconds()
            remaining = max(0, int(interval_sec - elapsed))
        else:
            remaining = 0

        rem_min = remaining // 60
        rem_sec = remaining % 60
        countdown_str = f"{rem_min} dk {rem_sec} sn" if rem_min > 0 else f"{rem_sec} sn"

        return {
            "pace_key": pace_key,
            "pace_name": pace_cfg["name"],
            "pace_short": pace_cfg["short_name"],
            "pace_desc": pace_cfg["desc"],
            "interval_seconds": interval_sec,
            "remaining_seconds": remaining,
            "countdown_str": countdown_str,
            "last_publish_time": self.last_autopilot_publish_time,
        }

    def trigger_autopilot_now(self, limit: int = 5) -> int:
        """Kullanıcı butona bastığında veya ayar değiştiğinde anında otopilot yayını yapar."""
        if not self.is_running:
            self.start()
        return self.run_autopilot_publish(limit=limit)

    def start(self, interval_minutes: int = 30) -> bool:
        """Zamanlayıcıyı başlatır."""
        if self.is_running and self._thread and self._thread.is_alive():
            return False

        self.interval_minutes = interval_minutes
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()
        self.is_running = True
        set_system_setting("AUTO_SCAN_ENABLED", "true")
        logger.info("Arka plan otopilot servisi başlatıldı.")
        return True

    def stop(self) -> bool:
        """Zamanlayıcıyı güvenle durdurur."""
        if not self.is_running:
            return False

        self._stop_event.set()
        self.is_running = False
        set_system_setting("AUTO_SCAN_ENABLED", "false")
        return True

    def get_status(self) -> Dict[str, Any]:
        """Panel için zamanlayıcı durum raporunu döner."""
        return {
            "is_running": self.is_running,
            "interval_minutes": self.interval_minutes,
            "last_run_time": self.last_run_time,
            "last_result": self.last_result
        }


# Global Tekil Zamanlayıcı Nesnesi
scheduler = BackgroundScheduler()
