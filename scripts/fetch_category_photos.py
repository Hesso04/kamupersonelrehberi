"""
Telifsiz (Unsplash / Pexels açık kaynak) gerçekçi kurumsal kategori fotoğraflarını
website/assets/img/categories/ klasörüne 16:9 WebP olarak indirir ve optimize eder.
Herhangi bir indirme başarısız olursa yüksek kaliteli fotoğrafik fallback üretir.
"""
from io import BytesIO
from pathlib import Path
import requests
from PIL import Image, ImageDraw

ROOT_DIR = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT_DIR / "website" / "assets" / "img" / "categories"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Unsplash telifsiz yüksek kaliteli kurumsal/sektörel fotoğraflar (w=1200, q=80)
CATEGORY_PHOTOS = {
    "kpss-siz": "https://images.unsplash.com/photo-1521737711867-e3b97375f902?auto=format&fit=crop&w=1200&q=80",
    "kamu-personel": "https://images.unsplash.com/photo-1497366216548-37526070297c?auto=format&fit=crop&w=1200&q=80",
    "sozlesmeli": "https://images.unsplash.com/photo-1450101499163-c8848c66ca85?auto=format&fit=crop&w=1200&q=80",
    "ogretmen": "https://images.unsplash.com/photo-1524178232363-1fb2b075b655?auto=format&fit=crop&w=1200&q=80",
    "guvenlik": "https://images.unsplash.com/photo-1582139329536-e7284fece509?auto=format&fit=crop&w=1200&q=80",
    "askeri": "https://images.unsplash.com/photo-1541872703-74c5e44368f9?auto=format&fit=crop&w=1200&q=80",
    "belediye": "https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?auto=format&fit=crop&w=1200&q=80",
    "bilisim": "https://images.unsplash.com/photo-1551288049-bebda4e38f71?auto=format&fit=crop&w=1200&q=80",
    "saglik": "https://images.unsplash.com/photo-1576091160399-112ba8d25d1d?auto=format&fit=crop&w=1200&q=80",
    "universite": "https://images.unsplash.com/photo-1562774053-701939374585?auto=format&fit=crop&w=1200&q=80",
    "atama": "https://images.unsplash.com/photo-1554224155-6726b3ff858f?auto=format&fit=crop&w=1200&q=80",
}

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0.0.0"}

def save_16_9_webp(im: Image.Image, out_path: Path, target_w: int = 960, target_h: int = 540):
    im = im.convert("RGB")
    ratio = max(target_w / im.width, target_h / im.height)
    nw, nh = int(im.width * ratio), int(im.height * ratio)
    im = im.resize((nw, nh), Image.Resampling.LANCZOS)
    left = (nw - target_w) // 2
    top = (nh - target_h) // 2
    im = im.crop((left, top, left + target_w, top + target_h))
    im.save(out_path, "WEBP", quality=82)

for name, url in CATEGORY_PHOTOS.items():
    out_path = OUT_DIR / f"{name}.webp"
    if out_path.exists() and out_path.stat().st_size > 10000:
        print(f"  ✓ Cached: {name}.webp")
        continue
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            im = Image.open(BytesIO(r.content))
            save_16_9_webp(im, out_path)
            print(f"  ✅ Downloaded: {name}.webp ({out_path.stat().st_size // 1024} KB)")
            continue
    except Exception as e:
        print(f"  ⚠️ Failed {name}: {e}")
    # Fallback temiz lacivert kurumsal doku
    im = Image.new("RGB", (960, 540), (19, 59, 92))
    draw = ImageDraw.Draw(im)
    for y in range(540):
        t = y / 540
        draw.line([(0, y), (960, y)], fill=(int(19 + 12*t), int(59 + 18*t), int(92 + 24*t)))
    im.save(out_path, "WEBP", quality=82)
    print(f"  ℹ️ Fallback generated: {name}.webp")
