"""
Kamu Personel Rehberi - Canlı Web Sitesi Eşzamanlama Aracı
Veritabanındaki güncel ilanları derler ve doğrudan GitHub Pages'e push eder.
İster tek seferlik, ister arka planda periyodik döngü olarak çalıştırılabilir.
"""

import sys
import time
import argparse
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

from scripts.export_website_data import sync_and_push


def main():
    parser = argparse.ArgumentParser(description="Kamu Personel Rehberi Web Sitesi Senkronizasyonu")
    parser.add_argument("--loop", action="store_true", help="Belirli saat aralıklarıyla arka planda sürekli çalıştır")
    parser.add_argument("--hours", type=float, default=2.0, help="Döngü çalışma aralığı (saat cinsinden, varsayılan: 2)")
    parser.add_argument("--no-push", action="store_true", help="Yalnızca JSON üret, git push yapma")
    args = parser.parse_args()

    auto_push = not args.no_push

    if not args.loop:
        print("⚡ Tek seferlik senkronizasyon başlatılıyor...")
        success = sync_and_push(auto_push=auto_push)
        if success:
            print("✅ Web sitesi başarıyla güncellendi!")
        else:
            print("❌ Senkronizasyon sırasında hata oluştu.")
        return

    interval_sec = int(args.hours * 3600)
    print(f"🔄 Web sitesi canlı senkronizasyon servisi aktif. Her {args.hours} saatte bir güncellenecek...")

    while True:
        try:
            print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Canlı güncelleme tetikleniyor...")
            sync_and_push(auto_push=auto_push)
        except Exception as e:
            print(f"⚠️ Hata: {e}")

        print(f"⏳ Sonraki güncelleme için {args.hours} saat bekleniyor...")
        time.sleep(interval_sec)


if __name__ == "__main__":
    main()
