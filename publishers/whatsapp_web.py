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

    def get_channel_code(self) -> str:
        """Kayıtlı WhatsApp kanal davet kodunu (0029...) temiz olarak ayıklar."""
        raw = (
            settings.get_dynamic("WHATSAPP_CHANNEL_URL") or 
            settings.get_dynamic("WHATSAPP_PHONE_NUMBER_ID") or 
            "0029Vb8mg1DFsn3nmDsQxF1K"
        ).strip()
        m = re.search(r"0029[A-Za-z0-9]+", raw)
        if m:
            return m.group(0)
        if "channel/" in raw:
            return raw.split("channel/")[-1].split("?")[0].strip("/")
        if "channel_invite_code=" in raw:
            return raw.split("channel_invite_code=")[-1].split("&")[0].strip()
        return raw.strip("/")

    def get_channel_url(self) -> str:
        """Kayıtlı WhatsApp kanalının doğrudan WhatsApp Web açılış linkini döner."""
        code = self.get_channel_code()
        return f"https://web.whatsapp.com/accept?channel_invite_code={code}"

    def is_logged_in(self) -> bool:
        """Kayıtlı bir WhatsApp Web oturumunun olup olmadığını kontrol eder."""
        return self.flag_file.exists()

    def logout(self) -> Tuple[bool, str]:
        """WhatsApp oturumunu sonlandırır, profil ve önbellek dosyalarını tamamen sıfırlar."""
        try:
            import shutil
            if self.flag_file.exists():
                try:
                    self.flag_file.unlink()
                except Exception:
                    pass
            if self.qr_path.exists():
                try:
                    self.qr_path.unlink()
                except Exception:
                    pass
            if self.session_dir.exists():
                shutil.rmtree(self.session_dir, ignore_errors=True)
                self.session_dir.mkdir(parents=True, exist_ok=True)
            return True, "WhatsApp Web oturumu ve profil önbelleği tamamen sıfırlandı."
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

    def _open_channel_and_get_input(self, page, channel_url: str):
        """
        Kanalı açıp mesaj yazma kutusunu güvenle bulur.
        1. Doğrudan WhatsApp Web kanal davet / açılış linkine gider.
        2. Progress / yükleme ekranının bitmesini bekler.
        3. 'Kanalı görüntüle', 'Takip et', 'Aç' vb. butonları tıklar.
        4. Mesaj yazma kutusunu (footer div, güncelleme yaz vb.) tarar.
        5. Gerekirse sol menüdeki Kanallar sekmesi veya Arama üzerinden kanala tıklar.
        6. Başarısızlık halinde teşhis için graphics/assets/wa_debug.png ekran görüntüsünü kaydeder.
        """
        code = self.get_channel_code()
        open_url = f"https://web.whatsapp.com/accept?channel_invite_code={code}"
        logger.info(f"WhatsApp kanalı açılıyor: {open_url} (Kod: {code})")
        try:
            page.goto(open_url, wait_until="domcontentloaded", timeout=45000)
        except Exception as ge:
            logger.warning(f"Navigasyon uyarısı: {ge}")

        # 1. WhatsApp Web ana arayüzünün yüklenmesini bekle (progress bar kaybolana kadar)
        for _ in range(25):
            progress = page.query_selector('progress, div[data-testid="startup-progress"]')
            if not progress:
                if page.query_selector('div#side, div#main, header, span[data-icon="newsletter-outline"], div[role="textbox"]'):
                    break
            time.sleep(1)

        # 2. Olası açılış butonlarına tıkla (Kanalı görüntüle, Aç, Takip et vb.)
        for sel in [
            'button:has-text("Kanalı görüntüle")',
            'div[role="button"]:has-text("Kanalı görüntüle")',
            'a:has-text("Kanalı görüntüle")',
            'button:has-text("View channel")',
            'div[role="button"]:has-text("View channel")',
            'button:has-text("Kanalı aç")',
            'div[role="button"]:has-text("Kanalı aç")',
            'button:has-text("Görüntüle")',
            'div[role="button"]:has-text("Görüntüle")',
            'button:has-text("Takip et")',
            'div[role="button"]:has-text("Takip et")',
            'button:has-text("Follow")',
            'div[role="button"]:has-text("Follow")',
            'button:has-text("Katıl")',
            'div[role="button"]:has-text("Katıl")',
            'button:has-text("Devam")',
            'div[role="button"]:has-text("Devam")',
        ]:
            try:
                b = page.query_selector(sel)
                if b and b.is_visible():
                    logger.info(f"Kanal açılış butonuna tıklandı: {sel}")
                    b.click()
                    time.sleep(3)
                    break
            except Exception:
                pass

        input_selectors = [
            '#main footer div[contenteditable="true"]',
            'footer div[contenteditable="true"]',
            'div[contenteditable="true"][data-tab="10"]',
            'div[contenteditable="true"][data-tab="6"]',
            'div[contenteditable="true"][role="textbox"]',
            'div[aria-placeholder*="güncelleme"]',
            'div[aria-placeholder*="update"]',
            'div[aria-placeholder*="mesaj"]',
            'div[aria-placeholder*="message"]',
            'div[aria-label*="güncelleme"]',
            'div[aria-label*="update"]',
            'div[aria-label*="Mesaj"]',
            'div[aria-label*="message"]',
            'div[title*="güncelleme"]',
            'div[title*="update"]',
            'p.selectable-text.copyable-text',
            '#main div[contenteditable="true"]',
        ]

        # 3. Giriş kutusunu tara
        for _ in range(12):
            for sel in input_selectors:
                try:
                    el = page.query_selector(sel)
                    if el and el.is_visible():
                        logger.info(f"Kanal mesaj kutusu bulundu ({sel})")
                        return el
                except Exception:
                    pass
            time.sleep(1)

        # 4. Alternatif A: Sol menüden Kanallar sekmesini tıkla
        logger.info("Doğrudan mesaj kutusu bulunamadı, Kanallar sekmesi taranıyor...")
        try:
            for ch_nav in [
                'button[aria-label*="Kanal"]',
                'button[aria-label*="Channel"]',
                'button[aria-label*="Güncelleme"]',
                'span[data-icon="newsletter-outline"]',
                'span[data-icon="channel-outline"]',
                'span[data-icon="status-outline"]',
            ]:
                cn = page.query_selector(ch_nav)
                if cn and cn.is_visible():
                    cn.click()
                    time.sleep(2)
                    break

            for ch_item in [
                'span[title*="Kamu Personel"]',
                'div[role="listitem"]:has-text("Kamu Personel")',
                'div[role="gridcell"]:has-text("Kamu Personel")',
                'div[data-testid="cell-frame-container"]:has-text("Kamu Personel")',
            ]:
                ci = page.query_selector(ch_item)
                if ci and ci.is_visible():
                    logger.info(f"Kanal listesinden kanala tıklandı: {ch_item}")
                    ci.click()
                    time.sleep(3)
                    for sel in input_selectors:
                        el = page.query_selector(sel)
                        if el and el.is_visible():
                            return el
                    break
        except Exception as e_nav:
            logger.warning(f"Kanallar sekmesi hatası: {e_nav}")

        # 5. Alternatif B: Arama kutusuna kanal adını yaz
        logger.info("Sol menüden arama kutusu ile aranıyor...")
        try:
            search_box = (
                page.query_selector('div[contenteditable="true"][data-tab="3"]') or
                page.query_selector('button[aria-label*="Ara"]') or
                page.query_selector('div[role="textbox"][data-tab="3"]')
            )
            if search_box:
                search_box.click()
                time.sleep(0.5)
                search_box.fill("Kamu Personel")
                time.sleep(2)
                item = (
                    page.query_selector('span[title*="Kamu Personel"]') or
                    page.query_selector('div[role="listitem"]:has-text("Kamu Personel")') or
                    page.query_selector('div[data-testid="cell-frame-container"]:has-text("Kamu Personel")')
                )
                if item:
                    item.click()
                    time.sleep(3)
                    for sel in input_selectors:
                        el = page.query_selector(sel)
                        if el and el.is_visible():
                            return el
        except Exception as se:
            logger.warning(f"Arama fallback hatası: {se}")

        # 6. Başarısızlık halinde ekran görüntüsünü kaydet
        try:
            debug_img = Path("graphics/assets/wa_debug.png")
            debug_img.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(debug_img))
            logger.warning(f"Kanal mesaj kutusu bulunamadı. URL: {page.url}. Ekran görüntüsü kaydedildi: {debug_img}")
        except Exception:
            pass

        return None

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
                input_box = self._open_channel_and_get_input(page, channel_url)

                if not input_box:
                    browser.close()
                    return False, "Kanala mesaj yazma kutusu bulunamadı. Kanalda yönetici yetkiniz olduğundan ve kanal linkinin doğruluğundan emin olun."

                # Metin alanına odaklan
                input_box.click()
                time.sleep(0.5)

                # React / ContentEditable editörüne execCommand ile metin yaz
                try:
                    page.evaluate("""([el, text]) => {
                        el.focus();
                        document.execCommand('insertText', false, text);
                    }""", [input_box, test_text])
                except Exception:
                    pass

                time.sleep(1)
                # Yedek: Eğer execCommand doldurmadıysa fill veya keyboard.type kullan
                if not (input_box.text_content() or "").strip():
                    try:
                        input_box.fill(test_text)
                    except Exception:
                        page.keyboard.type(test_text, delay=10)

                time.sleep(1)

                # Gönder butonu veya Enter
                send_btn = page.query_selector(
                    'span[data-icon="send"], button[aria-label*="Gönder"], '
                    'button[aria-label*="Send"], div[aria-label*="Gönder"], div[aria-label*="Send"]'
                )
                if send_btn and send_btn.is_visible():
                    send_btn.click()
                else:
                    page.keyboard.press("Enter")

                time.sleep(4)
                browser.close()
                return True, "WhatsApp kanalına test mesajı başarıyla gönderildi!"
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

                # 1. Kanala git ve giriş kutusunu hazırla
                input_box = self._open_channel_and_get_input(page, channel_url)
                if not input_box:
                    browser.close()
                    return False, "WhatsApp kanalında mesaj giriş alanı bulunamadı. Kanal yöneticisi olduğunuzdan emin olun."

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
                            time.sleep(1.5)

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
                                caption_box.click()
                                time.sleep(0.5)
                                try:
                                    page.evaluate("""([el, text]) => {
                                        el.focus();
                                        document.execCommand('insertText', false, text);
                                    }""", [caption_box, caption_text])
                                except Exception:
                                    pass

                                if not (caption_box.text_content() or "").strip():
                                    caption_box.fill(caption_text)
                                time.sleep(1)

                            # Gönder butonuna bas
                            send_btn = page.query_selector(
                                'span[data-icon="send"], div[aria-label="Gönder"], '
                                'div[aria-label="Send"], button[aria-label="Send"], button[aria-label="Gönder"]'
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
                    input_box.click()
                    time.sleep(0.5)
                    try:
                        page.evaluate("""([el, text]) => {
                            el.focus();
                            document.execCommand('insertText', false, text);
                        }""", [input_box, caption_text])
                    except Exception:
                        pass

                    if not (input_box.text_content() or "").strip():
                        input_box.fill(caption_text)
                    time.sleep(1)

                    send_btn = page.query_selector(
                        'span[data-icon="send"], button[aria-label*="Gönder"], button[aria-label*="Send"]'
                    )
                    if send_btn and send_btn.is_visible():
                        send_btn.click()
                    else:
                        page.keyboard.press("Enter")
                    time.sleep(4)
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
