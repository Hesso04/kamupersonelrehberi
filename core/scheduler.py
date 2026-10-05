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

                # 2. Seçili aktif kanallarda (Telegram vb.) yayınla
                results = publisher.publish_job(j_id, channels=["TELEGRAM"])
                t_success, t_msg = results.get("TELEGRAM", (False, ""))
                if t_success:
                    published_count += 1
                    logger.info(f"[OTOPİLOT] İlan #{j_id} başarıyla otomatik yayınlandı: {t_msg}")
                else:
                    logger.warning(f"[OTOPİLOT] İlan #{j_id} yayınlanamadı: {t_msg}")
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

                # 2. Otopilot Motoru (Manuel Onay Kapalıysa Bekleyen Doğrulanmış İlanları Otomatik Yayınla)
                if not manual_mode:
                    # Sıradaki ilanı güvenle Telegram'a aktar
                    pub_count = self.run_autopilot_publish(limit=1)
                    if pub_count > 0:
                        logger.info("[OTOPİLOT] 1 ilan başarıyla paylaşıldı. Telegram hız limiti için 5 sn bekleniyor...")
                        if self._stop_event.wait(timeout=5):
                            break
                        continue

            except Exception as e:
                logger.error(f"Zamanlayıcı / Otopilot döngü hatası: {e}")

            # 5 saniyelik hafif bekleme (kullanıcı ayar değiştirdiğinde anında tepki verir)
            if self._stop_event.wait(timeout=5):
                break

        logger.info("Arka plan zamanlayıcı durduruldu.")

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
