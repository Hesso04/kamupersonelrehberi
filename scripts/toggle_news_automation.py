"""
Kamu Haberleri Otomatik Pilot Yönetim Aracı
Kullanım:
  python scripts/toggle_news_automation.py --status
  python scripts/toggle_news_automation.py --enable
  python scripts/toggle_news_automation.py --disable
  python scripts/toggle_news_automation.py --fetch
  python scripts/toggle_news_automation.py --publish-now
"""

import sys
import argparse
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Proje ana dizinini path'e ekle
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.database import get_db, get_system_setting
from core.models import OfficialNews
from publishers.news_publisher import NewsPublisherManager, toggle_news_autopilot
from scrapers.official_news import run_news_scraper


def print_status():
    is_active = NewsPublisherManager.is_automation_enabled()
    channels = get_system_setting("AUTO_PUBLISH_NEWS_CHANNELS", "TELEGRAM,INSTAGRAM")

    with get_db() as db:
        total = db.query(OfficialNews).count()
        published = db.query(OfficialNews).filter(OfficialNews.is_social_published == True).count()
        pending = db.query(OfficialNews).filter(OfficialNews.is_social_published == False).count()

    print("\n" + "=" * 60)
    print("📢 KAMU HABERLERİ OTOMATİK PİLOT DURUMU")
    print("=" * 60)
    status_text = "🟢 AKTİF (Yeni gelen haberler otomatik paylaşılır)" if is_active else "🔴 PASİF / STANDBY (Otomasyon beklemede, paylaşım yapılmaz)"
    print(f"Durum          : {status_text}")
    print(f"Hedef Kanallar : {channels}")
    print(f"Toplam Haber   : {total}")
    print(f"Yayınlanan     : {published}")
    print(f"Bekleyen (Yeni): {pending}")
    print("=" * 60)
    if not is_active:
        print("💡 Aktifleştirmek için: python scripts/toggle_news_automation.py --enable")
    else:
        print("💡 Pasife almak için   : python scripts/toggle_news_automation.py --disable")
    print("\n")


def main():
    parser = argparse.ArgumentParser(description="Kamu Haberleri Otomasyon Yönetim Aracı")
    parser.add_argument("--status", action="store_true", help="Otomasyon durumunu göster")
    parser.add_argument("--enable", action="store_true", help="Haber otomatik pilotunu aktif et")
    parser.add_argument("--disable", action="store_true", help="Haber otomatik pilotunu pasife al (standby)")
    parser.add_argument("--fetch", action="store_true", help="Resmi kaynaklardan yeni haberleri çek")
    parser.add_argument("--publish-now", action="store_true", help="Bekleyen haberleri sosyal medyaya gönder")
    parser.add_argument("--force", action="store_true", help="Otomasyon kapalı olsa bile zorla gönder")

    args = parser.parse_args()

    if args.enable:
        msg = toggle_news_autopilot(True)
        print(f"\n{msg}\n")
        print_status()
    elif args.disable:
        msg = toggle_news_autopilot(False)
        print(f"\n{msg}\n")
        print_status()
    elif args.fetch:
        print("\n🔄 Resmi kaynaklar taranıyor...")
        count = run_news_scraper()
        print(f"✅ {count} adet yeni resmi kamu haberi veritabanına eklendi.\n")
        print_status()
    elif args.publish_now:
        print("\n🚀 Haber yayınlama süreci başlatılıyor...")
        pub = NewsPublisherManager()
        res = pub.publish_pending_news(limit=5, force=args.force)
        print(f"Sonuç: {res}\n")
        print_status()
    else:
        print_status()


if __name__ == "__main__":
    main()
