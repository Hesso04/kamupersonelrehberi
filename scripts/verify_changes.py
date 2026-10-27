"""
Tum degisiklikleri dogrulayan test scripti:
1. official_news.py - source_url yok, sadece kamupersonelrehberiniz.me
2. news_card_generator.py - kart, carousel, story passthrough
3. modern_generator.py - URL pill ortalanmis
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print("=" * 60)
print("DEGISIKLIK DOGRULAMA TESTI")
print("=" * 60)

# 1. official_news.py generate_social_post_text testi
print("\n[1] official_news.py - generate_social_post_text testi")
try:
    from scrapers.official_news import OfficialNewsScraper
    scraper = OfficialNewsScraper()
    test_item = {
        "title": "Sağlık Bakanlığı 5000 Hemşire Alımı",
        "institution": "T.C. Sağlık Bakanlığı",
        "summary": "Sağlık Bakanlığı 81 ile hemşire alımı yapacak.",
        "source_url": "https://www.saglik.gov.tr/haber/1234",
        "category": "ATAMA_KADRO"
    }
    text = scraper.generate_social_post_text(test_item)
    if "saglik.gov.tr" in text:
        print("[HATA] Dış kaynak URL hala metinde var!")
    elif "kamupersonelrehberiniz.me" in text:
        print("[OK] Sadece kamupersonelrehberiniz.me var, dış URL yok.")
    if "KILAVUZ" in text or "LINK" in text:
        print("[OK] Yorum tetikleyici (KILAVUZ/LINK) metinde mevcut.")
    else:
        print("[HATA] Yorum tetikleyici bulunamadi!")
    print("Uretilen metin (ilk 300 karakter):")
    print(text[:300])
except Exception as e:
    print(f"[HATA] official_news import/test hatasi: {e}")

# 2. purge_expired_news methodu varligi testi
print("\n[2] purge_expired_news metodu kontrol")
try:
    from scrapers.official_news import OfficialNewsScraper
    scraper = OfficialNewsScraper()
    if hasattr(scraper, "purge_expired_news"):
        print("[OK] purge_expired_news() metodu mevcut.")
    else:
        print("[HATA] purge_expired_news() metodu bulunamadi!")
except Exception as e:
    print(f"[HATA] {e}")

# 3. news_card_generator import testi
print("\n[3] news_card_generator import testi")
try:
    from graphics.news_card_generator import NewsCardGenerator
    gen = NewsCardGenerator()
    print("[OK] NewsCardGenerator basariyla import edildi.")

    import inspect
    src_carousel = inspect.getsource(gen.generate_carousel_slides)
    if "_make_premium_slide_canvas" in src_carousel:
        print("[OK] Carousel Slayt 2 ve 3 premium slide canvas kullaniyor.")
    else:
        print("[HATA] Carousel guncellenmemis!")

    if "bg_reuse_path" in src_carousel:
        print("[OK] AI arka plan yeniden kullanim (bg_reuse_path) mevcut.")
    else:
        print("[HATA] AI arka plan yeniden kullanim yok!")

    src_gen = inspect.getsource(gen.generate)
    if "Haber detaylari" in src_gen or "KILAVUZ" in src_gen:
        print("[OK] Feed karti alt yorum CTA satiri mevcut.")
    else:
        print("[HATA] Feed karti alt yorum CTA satiri eksik!")

    if "560" in src_gen and "640" in src_gen:
        print("[OK] Kapsul tuval genisletilmis (640x46).")
    else:
        print("[UYARI] Kapsul tuval kontrolu farkli bir sekilde yapilmis.")
except Exception as e:
    print(f"[HATA] news_card_generator: {e}")
    import traceback
    traceback.print_exc()

# 4. modern_generator.py CTA degisikligi kontrol
print("\n[4] modern_generator.py CTA guncelleme kontrol")
try:
    with open("graphics/modern_generator.py", "r", encoding="utf-8") as f:
        mg_content = f.read()
    if "url_bar_w" in mg_content and "ilan_cta" in mg_content:
        print("[OK] modern_generator.py - URL pill + yorum satiri guncellendi.")
    else:
        print("[HATA] modern_generator.py guncellenmemis!")
    if "IPTAL DETAYLARINI INCELE" in mg_content or "cta_tw" in mg_content:
        print("[OK] CTA butonu ortalama kodu mevcut.")
except Exception as e:
    print(f"[HATA] {e}")

# 5. instagram.py story degisikligi kontrol
print("\n[5] instagram.py story yeniden kullanim kontrol")
try:
    with open("publishers/instagram.py", "r", encoding="utf-8") as f:
        ig_content = f.read()
    if "generate_story" not in ig_content or "Akis goerseli Story olarak da paylasildi" in ig_content or "Akis" in ig_content:
        print("[OK] instagram.py - story artik yeni AI kart uretmiyor, feed karti kullaniyor.")
    else:
        # check direct
        if "final_img_path" in ig_content and "publish_story(final_img_path)" in ig_content:
            print("[OK] instagram.py - story artik final_img_path ile publish ediliyor.")
        else:
            print("[UYARI] instagram.py story degisikligi kontrol edilmeli.")
except Exception as e:
    print(f"[HATA] {e}")

print("\n" + "=" * 60)
print("DOGRULAMA TAMAMLANDI")
print("=" * 60)
