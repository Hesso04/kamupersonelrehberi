"""
Gercek gorsel uretim testi: Feed karti + 3 slaytlik Carousel
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from graphics.news_card_generator import NewsCardGenerator
gen = NewsCardGenerator()

# Feed karti uret
print("1. Feed karti uretiliyor...")
feed_path = gen.generate(
    news_id=1001,
    title="Devlet Memurlarına Yüzde 30 Maaş Zammı Açıklandı",
    institution="T.C. Hazine ve Maliye Bakanlığı",
    category="OZLUK_MAAS",
    summary="Cumhurbaşkanlığı kararnamesiyle tüm devlet memurlarına yüzde 30 maaş artışı yapılacak. Zam Ocak ayı itibariyle geçerli olacak.",
    source_url="https://kamupersonelrehberiniz.me"
)
print(f"[OK] Feed karti: {feed_path}")

# 3 slaytlik carousel uret
print("\n2. 3-slaytlik Carousel uretiliyor...")
slides = gen.generate_carousel_slides(
    news_id=1001,
    title="Devlet Memurlarına Yüzde 30 Maaş Zammı Açıklandı",
    institution="T.C. Hazine ve Maliye Bakanlığı",
    category="OZLUK_MAAS",
    summary="Cumhurbaşkanlığı kararnamesiyle tüm devlet memurlarına yüzde 30 maaş artışı yapılacak. Zam Ocak ayı itibariyle geçerli olacak.",
    content="Maaş artışı tüm kamu görevlilerini kapsayacak. 657 sayılı Devlet Memurları Kanunu kapsamındaki memurlar, sözleşmeli personel ve işçiler bu artıştan yararlanacak. Artış tutarı brüt maaşlar üzerinden hesaplanacak ve Ocak 2026 maaşlarına yansıtılacak.",
    source_url="https://kamupersonelrehberiniz.me"
)
print(f"[OK] Carousel slaytlari ({len(slides)} adet):")
for i, s in enumerate(slides):
    size_kb = os.path.getsize(s) // 1024 if os.path.exists(s) else 0
    print(f"  Slayt {i+1}: {s} ({size_kb} KB)")

print("\n[TAMAMLANDI] Gorsel uretim testi basarili.")
