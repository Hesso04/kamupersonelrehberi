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
    "SMART_PEAK": {
        "name": "🔥 Türkiye Pik Saatleri Modu (09:00, 13:00, 19:00, 21:30 - Maksimum Keşfet & Kaydetme)",
        "short_name": "Pik Saatler (Günde 4 İlan)",
        "desc": "Yalnızca Türkiye'de KPSS ve memur adaylarının en aktif olduğu 4 altın pik penceresinde paylaşır. Spam riski sıfırdır, algoritma puanını zirveye çıkarır.",
        "interval_seconds": 3600,
    },
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
        self.last_kpss_quiz_time: Optional[datetime] = None
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

                default_theme = get_system_setting("DEFAULT_CARD_THEME", "OFFICIAL_NAVY")
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

    def sync_missing_channels(self, limit: int = 5) -> Dict[str, Any]:
        """
        Daha önce Telegram'a gitmiş ancak Instagram veya Facebook'a ulaştırılamamış
        son yayınlanan ilanları tespit eder ve eksik kanalları tamamlar.
        """
        raw_ap = get_system_setting("AUTOPILOT_CHANNELS", "TELEGRAM,INSTAGRAM,FACEBOOK")
        configured_channels = [c.strip().upper() for c in raw_ap.split(",") if c.strip()]
        publisher = PublisherManager()
        default_theme = get_system_setting("DEFAULT_CARD_THEME", "OFFICIAL_NAVY")

        synced_count = 0
        details = []

        with get_db() as db:
            recent_published = db.query(JobAnnouncement).filter(
                JobAnnouncement.status == JobStatus.PUBLISHED
            ).order_by(JobAnnouncement.id.desc()).limit(20).all()

            target_jobs = []
            for j in recent_published:
                cur_pub = [c.strip().upper() for c in (j.published_channels or "").split(",") if c.strip()]
                missing = [c for c in configured_channels if c not in cur_pub]
                if missing:
                    target_jobs.append((j.id, missing))
                if len(target_jobs) >= limit:
                    break

        for j_id, missing in target_jobs:
            res = publisher.publish_missing_channels(j_id, target_channels=missing, theme=default_theme)
            any_succ = any(s for s, _ in res.values())
            if any_succ:
                synced_count += 1
            details.append({"job_id": j_id, "missing": missing, "results": res})

        return {"synced_count": synced_count, "details": details}

    def _worker(self):
        logger.info(f"Arka plan zamanlayıcı ve otopilot motoru başlatıldı. Tarama aralığı: {self.interval_minutes} dk.")
        last_scan_time = datetime.min
        last_ig_comment_check = datetime.min

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

                    if pace_key == "SMART_PEAK":
                        # Türkiye yerel saati pik pencereleri:
                        # Sabah (08:30-10:00), Öğle (12:30-14:00), Akşam (18:30-20:00), Gece (21:00-23:00)
                        h_m = now.hour + now.minute / 60.0
                        in_peak = (8.5 <= h_m <= 10.0) or (12.5 <= h_m <= 14.0) or (18.5 <= h_m <= 20.0) or (21.0 <= h_m <= 23.0)
                        if self.last_autopilot_publish_time is None:
                            should_publish = in_peak
                        else:
                            elapsed = (now - self.last_autopilot_publish_time).total_seconds()
                            should_publish = in_peak and (elapsed >= 3600)
                    else:
                        if self.last_autopilot_publish_time is None:
                            should_publish = True
                        else:
                            elapsed = (now - self.last_autopilot_publish_time).total_seconds()
                            should_publish = elapsed >= interval_sec

                    if should_publish:
                        pub_count = self.run_autopilot_publish(limit=1)
                        if pub_count > 0:
                            self.last_autopilot_publish_time = now
                            logger.info(f"[OTOPİLOT] 1 ilan başarıyla paylaşıldı. Belirlenen tempo ({pace_cfg['name']}) devrede.")

                # 3. Instagram Canlı Yorum ve DM Yanıtlayıcı (Her 60 saniyede bir yeni yorumları tara)
                if (now - last_ig_comment_check).total_seconds() >= 60:
                    last_ig_comment_check = now
                    try:
                        from modules.instagram_growth import InstagramGrowthManager
                        ig_mgr = InstagramGrowthManager()
                        ig_mgr.process_live_comments(limit_media=10)
                    except Exception as ige:
                        logger.debug(f"Otomatik Instagram yorum işleme hatası: {ige}")

                # 4. Otomatik KPSS Quiz Otopilotu (Günde 10-20 soru, kanala periyodik anket olarak)
                if get_system_setting("AUTO_KPSS_QUIZ_ENABLED", "true") == "true":
                    interval_hours = float(get_system_setting("AUTO_KPSS_QUIZ_INTERVAL_HOURS", "1.5"))
                    if self.last_kpss_quiz_time is None or (now - self.last_kpss_quiz_time).total_seconds() >= interval_hours * 3600:
                        # Türkiye saatiyle 08:30 - 23:30 saatleri arasında gönder
                        if 8 <= now.hour <= 23:
                            self.last_kpss_quiz_time = now
                            try:
                                from modules.kpss_quiz_engine import KPSSQuizEngine
                                q_eng = KPSSQuizEngine()
                                fresh_q = q_eng.generate_ai_questions(count=1)
                                if fresh_q:
                                    succ, q_msg = q_eng.send_quiz_to_telegram(fresh_q[0])
                                    if succ:
                                        logger.info(f"[OTOPİLOT QUIZ] Otomatik KPSS sorusu Telegram kanalına aktarıldı: {fresh_q[0].get('subject')}")
                                    else:
                                        logger.warning(f"[OTOPİLOT QUIZ] Soru gönderilemedi: {q_msg}")
                            except Exception as q_err:
                                logger.error(f"[OTOPİLOT QUIZ] Otopilot soru hatası: {q_err}")

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
