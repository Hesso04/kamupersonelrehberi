import os
import sys
import time
import re
import subprocess
from pathlib import Path
from typing import Tuple, Optional
from loguru import logger
from playwright.sync_api import sync_playwright

from config.settings import settings
from core.models import JobAnnouncement


def ensure_browser_installed():
    """Linux / Streamlit Cloud ortamında eksik Playwright Chromium tarayıcısını otomatik kurar."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            exe = p.chromium.executable_path
            if not Path(exe).exists():
                raise FileNotFoundError()
    except Exception as e:
        logger.info(f"Playwright Chromium bulunamadı, otomatik kuruluyor: {e}")
        try:
            subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
            logger.info("Playwright Chromium başarıyla kuruldu.")
        except Exception as install_err:
            logger.error(f"Playwright kurulum hatası: {install_err}")


def make_clean_qr_image(raw_data: str, target_path: Path):
    """Raw data-ref kodundan telefon kameralarının anında okuyacağı yüksek kontrastlı, beyaz kenarlıklı QR üretir."""
    import qrcode
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(raw_data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(target_path))


def pad_canvas_screenshot(img_path: Path):
    """Ekran görüntüsünün etrafına 50px genişliğinde beyaz sessiz alan (quiet zone) ekler."""
    from PIL import Image
    try:
        im = Image.open(img_path).convert("RGBA")
        padded = Image.new("RGB", (im.width + 100, im.height + 100), (255, 255, 255))
        padded.paste(im, (50, 50), im if im.mode == "RGBA" else None)
        padded.save(str(img_path), "PNG")
    except Exception as e:
        logger.warning(f"QR padding hatası: {e}")


class WhatsAppWebPublisher:
    """
    Yerel WhatsApp Web ve WhatsApp Kanalları (Channels) Otomasyonu.
    Playwright ve kalıcı profil dizini (data/whatsapp_session) kullanarak
    ekstra API ücreti veya sağlayıcıya gerek kalmadan WhatsApp kanalına
    doğrudan görsel kart, ilan metni ve resmi PDF şartname yayınlar.
    """

    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )

    def __init__(self):
        self.session_dir = Path("data/whatsapp_session").resolve()
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.flag_file = self.session_dir / "logged_in.flag"
        self.qr_path = Path("graphics/assets/whatsapp_qr.png").resolve()

    def get_channel_url(self) -> str:
        """Kayıtlı veya varsayılan WhatsApp kanal linkini döner."""
        raw = (
            settings.get_dynamic("WHATSAPP_CHANNEL_URL") or 
            settings.get_dynamic("WHATSAPP_PHONE_NUMBER_ID") or 
            "0029Vb8mg1DFsn0nmDsQxF1K"
        ).strip()
        
        if "whatsapp.com/channel/" in raw:
            key = raw.split("channel/")[-1].strip("/")
            return f"https://web.whatsapp.com/channel/{key}"
        if raw.startswith("0029"):
            return f"https://web.whatsapp.com/channel/{raw}"
        return raw if raw.startswith("http") else f"https://web.whatsapp.com/channel/{raw}"

    def is_logged_in(self) -> bool:
        """Kayıtlı bir WhatsApp Web oturumunun olup olmadığını kontrol eder."""
        if self.flag_file.exists():
            return True
        # IndexedDB içinde whatsapp verisi var mı
        leveldb = self.session_dir / "Default" / "IndexedDB" / "https_web.whatsapp.com_0.indexeddb.leveldb"
        if leveldb.exists() and len(list(leveldb.glob("*.ldb"))) > 0:
            return True
        return False

    def logout(self) -> Tuple[bool, str]:
        """WhatsApp oturumunu sonlandırır ve flag dosyasını siler."""
        try:
            if self.flag_file.exists():
                self.flag_file.unlink()
            if self.qr_path.exists():
                self.qr_path.unlink()
            return True, "WhatsApp Web oturumu yerel olarak sıfırlandı."
        except Exception as e:
            return False, f"Çıkış hatası: {str(e)}"

    def start_login_window(self, max_wait: int = 90, on_qr_ready: Optional[callable] = None) -> Tuple[bool, str]:
        """
        Kullanıcının telefonundan QR kod okutabilmesi için WhatsApp Web oturumu başlatır.
        Bulut ortamında (Linux) arkaplanda headless çalışıp QR kod görselini arayüze aktarır.
        """
        ensure_browser_installed()
        is_cloud = (sys.platform != "win32") or not os.environ.get("DISPLAY")
        headless_mode = bool(is_cloud)
        logger.info(f"WhatsApp Web QR süreci başlatılıyor (Headless={headless_mode})...")
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch_persistent_context(
                    user_data_dir=str(self.session_dir),
                    headless=headless_mode,
                    user_agent=self.USER_AGENT,
                    viewport={"width": 1050, "height": 780},
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
                )
                page = browser.pages[0] if browser.pages else browser.new_page()
                page.goto("https://web.whatsapp.com", wait_until="domcontentloaded", timeout=60000)

                start_time = time.time()
                logged_in = False
                qr_captured = False

                last_ref = None
                while time.time() - start_time < max_wait:
                    time.sleep(1.5)

                    # A. Süre dolup "Yenile" butonu belirdiyse otomatik tıkla
                    reload_btn = (
                        page.query_selector('button:has-text("Yenile")') or 
                        page.query_selector('span[data-icon="refresh"]') or 
                        page.query_selector('div[role="button"]:has(span[data-icon="refresh"])')
                    )
                    if reload_btn:
                        try:
                            reload_btn.click()
                            time.sleep(1.5)
                        except Exception:
                            pass

                    # B. data-ref niteliği varsa doğrudan %100 net, beyaz kenarlıklı QR üret
                    ref_elem = page.query_selector('div[data-ref]')
                    data_ref = ref_elem.get_attribute("data-ref") if ref_elem else None

                    if data_ref and data_ref != last_ref:
                        last_ref = data_ref
                        try:
                            make_clean_qr_image(data_ref, self.qr_path)
                            logger.info(f"WhatsApp data-ref yakalandı ve net QR üretildi: {self.qr_path}")
                            if on_qr_ready:
                                on_qr_ready(str(self.qr_path))
                        except Exception as e:
                            logger.warning(f"QR oluşturma hatası: {e}")

                    # C. data-ref henüz yoksa canvas ekran görüntüsünü al ve beyaz margin ekle
                    elif not last_ref:
                        qr_canvas = page.query_selector('canvas[aria-label*="QR"]') or page.query_selector('canvas')
                        if qr_canvas:
                            try:
                                self.qr_path.parent.mkdir(parents=True, exist_ok=True)
                                qr_canvas.screenshot(path=str(self.qr_path))
                                pad_canvas_screenshot(self.qr_path)
                                last_ref = "canvas"
                                logger.info(f"WhatsApp canvas yakalandı ve beyaz çerçeve ile kaydedildi: {self.qr_path}")
                                if on_qr_ready:
                                    on_qr_ready(str(self.qr_path))
                            except Exception:
                                pass

                    # 2. Giriş başarılı mı kontrol et
                    chat_pane = (
                        page.query_selector("#pane-side") or 
                        page.query_selector('div[aria-label="Chat list"]') or 
                        page.query_selector('div[aria-label="Sohbet listesi"]') or
                        page.query_selector('div[data-tab="3"]')
                    )
                    if chat_pane:
                        logged_in = True
                        break

                browser.close()

                if logged_in:
                    self.flag_file.write_text(f"logged_in_at={time.time()}")
                    if self.qr_path.exists():
                        try:
                            self.qr_path.unlink()
                        except Exception:
                            pass
                    logger.info("WhatsApp Web oturumu başarıyla bağlandı!")
                    return True, "WhatsApp Web oturumu başarıyla bağlandı! Artık kanalınıza otomatik gönderi yapılabilir."
                else:
                    return False, "Süre doldu veya QR kod okutulmadı. Lütfen tekrar deneyin."

        except Exception as e:
            logger.error(f"WhatsApp Web giriş hatası: {e}")
            return False, f"WhatsApp Web Hatası: {str(e)}"

    def send_test_message(self) -> Tuple[bool, str]:
        """Kanal bağlantısını test etmek için kısa bir test mesajı gönderir."""
        if not self.is_logged_in():
            return False, "WhatsApp Web oturumu açılmamış. Lütfen önce QR kod ile bağlanın."

        channel_url = self.get_channel_url()
        test_text = (
            "✅ *Kamu Personel Rehberi - WhatsApp Kanal Entegrasyonu Testi*\n\n"
            "Bu mesaj, yerel yapay zeka otomasyon sistemimiz tarafından başarıyla iletilmiştir.\n"
            "Resmi kamu personel alımları anlık olarak bu kanaldan paylaşılacaktır. 🏛️📢"
        )

        ensure_browser_installed()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch_persistent_context(
                    user_data_dir=str(self.session_dir),
                    headless=True,
                    user_agent=self.USER_AGENT,
                    viewport={"width": 1280, "height": 800},
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
                )
                page = browser.pages[0] if browser.pages else browser.new_page()
                page.goto(channel_url, wait_until="networkidle", timeout=45000)
                time.sleep(4)

                # Kanala katıl / görüntüle
                join_btn = page.query_selector('div[role="button"]:has-text("Kanalı görüntüle"), div[role="button"]:has-text("View channel")')
                if join_btn:
                    join_btn.click()
                    time.sleep(2)

                # Mesaj kutusu
                input_box = (
                    page.query_selector('footer div[contenteditable="true"]') or
                    page.query_selector('div[contenteditable="true"][data-tab="10"]') or
                    page.query_selector('div[contenteditable="true"]')
                )

                if not input_box:
                    browser.close()
                    return False, "Kanala mesaj yazma kutusu bulunamadı. Kanalda yönetici yetkiniz olduğundan emin olun."

                input_box.fill(test_text)
                time.sleep(1)
                page.keyboard.press("Enter")
                time.sleep(3)
                browser.close()
                return True, "Test mesajı WhatsApp kanalına başarıyla gönderildi!"
        except Exception as e:
            return False, f"Test gönderim hatası: {str(e)}"

    def publish_to_channel(self, job: JobAnnouncement) -> Tuple[bool, str]:
        """
        Kamu Personel Rehberi WhatsApp kanalına görsel ilan kartı ve açıklama yayınlar.
        """
        if not self.is_logged_in():
            return False, "WhatsApp Web oturumu henüz açılmamış. Lütfen Ayarlar sekmesinden QR kodu taratın."

        channel_url = self.get_channel_url()
        clean_url = job.source_url or "https://kamuilan.sbb.gov.tr/"
        if "ilanDetay.aspx" in clean_url:
            clean_url = "https://kamuilan.sbb.gov.tr/"

        # Pozisyon başlığı
        pos_title = job.position if (job.position and job.position != "None") else job.title
        
        from graphics.generator import to_turkish_date_str
        deadline_str = to_turkish_date_str(job.application_end_date)

        caption_text = (
            f"📢 *{job.institution or 'Kamu Alımı'}*\n"
            f"*{pos_title}*\n\n"
            f"👥 *Kontenjan:* {job.total_positions or 1} Kişi\n"
            f"🗓 *Son Başvuru:* {deadline_str}\n"
            f"🎯 *KPSS Şartı:* {job.kpss_requirement or 'Resmi ilanda'}\n"
            f"🎓 *Mezuniyet:* {job.education_level or 'İlgili bölüm'}\n\n"
            f"🔗 *Resmi Başvuru / Kılavuz:* {clean_url}\n\n"
            f"⚠️ _%100 Doğrulanmış Resmi Kaynaklıdır._\n"
            f"#KamuPersoneli #İlan #KamuAlımı"
        )

        image_path = Path(job.image_path) if job.image_path else None

        logger.info(f"WhatsApp kanalına ilan yayınlanıyor: {channel_url}")

        ensure_browser_installed()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch_persistent_context(
                    user_data_dir=str(self.session_dir),
                    headless=True,
                    user_agent=self.USER_AGENT,
                    viewport={"width": 1280, "height": 800},
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
                )
                page = browser.pages[0] if browser.pages else browser.new_page()

                # 1. Kanala git
                page.goto(channel_url, wait_until="networkidle", timeout=50000)
                time.sleep(4)

                # Kanala katıl / Kanalı görüntüle butonu çıkarsa tıkla
                join_btn = page.query_selector('div[role="button"]:has-text("Kanalı görüntüle"), div[role="button"]:has-text("View channel")')
                if join_btn:
                    join_btn.click()
                    time.sleep(2)

                # Oturum düşmüş mü kontrolü (QR canvas belirdiyse)
                if page.query_selector('canvas[aria-label*="QR"]'):
                    if self.flag_file.exists():
                        self.flag_file.unlink()
                    browser.close()
                    return False, "WhatsApp Web oturumu sonlanmış. Lütfen Ayarlar sekmesinden tekrar QR kod okutun."

                # 2. Görsel varsa görsel + açıklama olarak gönder
                sent = False
                if image_path and image_path.exists():
                    try:
                        # Ekle (+) veya ataç butonuna tıkla
                        attach_btn = page.query_selector(
                            'span[data-icon="plus"], span[data-icon="attach-menu-plus"], '
                            'div[aria-label="Ekle"], div[aria-label="Attach"], '
                            'button[aria-label="Ekle"], button[aria-label="Attach"]'
                        )
                        if attach_btn:
                            attach_btn.click()
                            time.sleep(1)

                        file_input = page.query_selector('input[type="file"]')
                        if file_input:
                            file_input.set_input_files(str(image_path))
                            time.sleep(3)

                            # Görsel açıklama kutusunu bul ve doldur
                            caption_box = (
                                page.query_selector('div[contenteditable="true"][data-tab="10"]') or
                                page.query_selector('div[aria-placeholder*="Açıklama"]') or
                                page.query_selector('div[aria-placeholder*="caption"]') or
                                page.query_selector('div[contenteditable="true"]')
                            )
                            if caption_box:
                                caption_box.fill(caption_text)
                                time.sleep(1)

                            # Gönder butonuna bas
                            send_btn = page.query_selector(
                                'span[data-icon="send"], div[aria-label="Gönder"], '
                                'div[aria-label="Send"], button[aria-label="Send"]'
                            )
                            if send_btn:
                                send_btn.click()
                            else:
                                page.keyboard.press("Enter")
                            
                            time.sleep(5)
                            sent = True
                    except Exception as img_err:
                        logger.warning(f"WhatsApp görsel ekleme aşamasında hata, metin olarak deneniyor: {img_err}")

                # 3. Görsel yoksa veya ekleme başarısız olduysa metin olarak gönder
                if not sent:
                    input_box = (
                        page.query_selector('footer div[contenteditable="true"]') or
                        page.query_selector('div[contenteditable="true"][data-tab="10"]') or
                        page.query_selector('div[aria-placeholder*="güncelleme"]') or
                        page.query_selector('div[aria-placeholder*="update"]') or
                        page.query_selector('div[contenteditable="true"]')
                    )
                    if input_box:
                        input_box.fill(caption_text)
                        time.sleep(1)
                        page.keyboard.press("Enter")
                        time.sleep(3)
                        sent = True

                browser.close()

                if sent:
                    logger.info(f"WhatsApp kanalında ilan başarıyla paylaşıldı: ID {job.id}")
                    return True, "WhatsApp kanalında başarıyla yayınlandı!"
                else:
                    return False, "WhatsApp kanalında mesaj giriş alanı bulunamadı. Kanal yöneticisi olduğunuzdan emin olun."

        except Exception as e:
            logger.error(f"WhatsApp kanal paylaşım hatası: {e}")
            return False, f"WhatsApp Kanal Paylaşım Hatası: {str(e)}"
