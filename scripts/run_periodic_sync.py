"""
Yerel veya VDS/Sunucu ortamında kesintisiz 2 saatte bir çalışan senkronizasyon servisi.
Kaynak siteleri tarar (İlanlar + Resmi Haberler), website ve docs verilerini günceller.
"""
import time
import subprocess
import sys
import os
from datetime import datetime

INTERVAL_SECONDS = 2 * 60 * 60  # 2 saat = 7200 saniye

def log(msg: str):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)

def run_step(cmd_args: list, desc: str):
    log(f"-> Başlatılıyor: {desc}...")
    try:
        res = subprocess.run(cmd_args, capture_output=True, text=True, check=False)
        if res.returncode == 0:
            log(f"OK: {desc} başarıyla tamamlandı.")
        else:
            log(f"UYARI: {desc} kod {res.returncode} ile bitti:\n{res.stderr[-300:] if res.stderr else ''}")
    except Exception as e:
        log(f"HATA: {desc} çalışırken hata: {e}")

def sync_cycle():
    py = sys.executable
    log("==================================================")
    log("2 SAATLİK OTOMATİK TARAMA DÖNGÜSÜ BAŞLADI")
    log("==================================================")

    # 1. Resmi Haberler
    run_step([py, "scrapers/official_news.py"], "Resmi Haber Tarayıcısı (İletişim, ÇSGB, Resmi Gazete)")

    # 2. İlanlar
    run_step([py, "scrapers/manager.py"], "Kamu İlanları Tarayıcısı (SBB, Kariyer Kapısı, İŞKUR, BİK)")

    # 3. Export
    run_step([py, "scripts/export_website_data.py"], "Website Veri ve Sitemap Export")

    # 4. Docs Sync
    run_step([py, "-c", "import shutil; shutil.copytree('website/data', 'docs/data', dirs_exist_ok=True); shutil.copy('website/sitemap.xml', 'docs/sitemap.xml')"], "Docs Senkronizasyonu")

    log("Döngü tamamlandı. Bir sonraki tarama 2 saat sonra gerçekleşecek.")

def main():
    log("Kamu Personel Rehberi - 2 Saatlik Otomasyon Servisi Başlatıldı.")
    # İlk döngüyü hemen çalıştır
    sync_cycle()

    while True:
        try:
            log(f"Beklemeye geçiliyor ({INTERVAL_SECONDS // 3600} saat)...")
            time.sleep(INTERVAL_SECONDS)
            sync_cycle()
        except KeyboardInterrupt:
            log("Otomasyon servisi kullanıcı tarafından durduruldu.")
            break
        except Exception as e:
            log(f"Beklenmeyen hata: {e}. 60 saniye sonra tekrar denenecek...")
            time.sleep(60)

if __name__ == "__main__":
    main()
