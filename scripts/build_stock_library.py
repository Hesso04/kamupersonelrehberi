"""
Kamu Personel Rehberi — Küratörlü Tematik Stok Görsel Kütüphanesi Üreticisi
=============================================================================
10 ana tema için yerel yüksek çözünürlüklü arka planlar ve doğrulanmış
telifsiz kaynaklardan 1200x675 (16:9) WebP stok fotoğrafları üretir ve
website/data/stock_library_manifest.json ile docs/data/stock_library_manifest.json oluşturur.
"""

import json
import shutil
import sys
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Any

import requests
from PIL import Image

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

STOCK_LIB_DIR = ROOT_DIR / "website" / "assets" / "img" / "stock_library"
DOCS_STOCK_DIR = ROOT_DIR / "docs" / "assets" / "img" / "stock_library"

THEME_META = {
    "egitim": "Eğitim & MEB",
    "sinav_kpss": "KPSS & Sınavlar",
    "konut_toki": "TOKİ & Konut",
    "iklim_cevre": "İklim & Çevre",
    "belediye_sehir": "Yerel Yönetim & Belediye",
    "saglik": "Sağlık & Kamu",
    "bilisim": "Bilişim & Teknoloji",
    "adalet_mevzuat": "Mevzuat & Özlük",
    "savunma_enerji": "Savunma & Enerji",
    "kamu_resmi": "Resmi Gündem",
}

# Her tema için (kaynak_türü, değer, etiket) listesi
# 'local': proje içi dosya, 'url': telifsiz Unsplash görseli
THEME_SOURCES: Dict[str, List[tuple]] = {
    "egitim": [
        ("local", "website/assets/img/categories/ogretmen.webp", "Sınıf ve Eğitim Ortamı"),
        ("local", "website/assets/img/categories/universite.webp", "Üniversite Kampüsü"),
        ("local", "graphics/assets/backgrounds/education.jpg", "Eğitim ve Akademik Çalışma"),
    ],
    "sinav_kpss": [
        ("local", "website/assets/img/categories/atama.webp", "Sınav ve Kariyer Planlama"),
        ("url", "https://images.unsplash.com/photo-1434030216411-0b793f4b4173?auto=format&fit=crop&w=1200&q=80", "Kütüphane ve Sınav Hazırlığı"),
        ("local", "graphics/assets/backgrounds/education.jpg", "KPSS Hazırlık ve Kaynaklar"),
    ],
    "konut_toki": [
        ("local", "graphics/assets/backgrounds/toki_realistic.jpg", "Modern Toplu Konut Projeleri"),
        ("local", "website/assets/img/categories/belediye.webp", "Kentsel Mimari Yapılar"),
        ("url", "https://images.unsplash.com/photo-1545324418-cc1a3fa10c00?auto=format&fit=crop&w=1200&q=80", "Yeni Konut ve Yaşam Alanları"),
    ],
    "iklim_cevre": [
        ("local", "graphics/assets/backgrounds/water_forest.jpg", "Doğa, Su ve Orman Ekosistemi"),
        ("local", "graphics/assets/backgrounds/ogm_realistic.jpg", "Yeşil Doğa ve Çevre"),
    ],
    "belediye_sehir": [
        ("local", "graphics/assets/backgrounds/municipality.jpg", "Belediye ve Şehir Yönetimi"),
        ("local", "website/assets/img/categories/belediye.webp", "Modern Şehir ve Yerel İdare"),
    ],
    "saglik": [
        ("local", "graphics/assets/backgrounds/health.jpg", "Sağlık Hizmetleri ve Hastane"),
        ("local", "website/assets/img/categories/saglik.webp", "Tıp ve Sağlık Personeli"),
    ],
    "bilisim": [
        ("local", "website/assets/img/categories/bilisim.webp", "Yazılım, Veri ve Teknoloji"),
        ("url", "https://images.unsplash.com/photo-1518770660439-4636190af475?auto=format&fit=crop&w=1200&q=80", "Dijital Altyapı ve Sistemler"),
    ],
    "adalet_mevzuat": [
        ("local", "graphics/assets/backgrounds/justice.jpg", "Hukuk, Mevzuat ve Adalet"),
        ("local", "website/assets/img/categories/sozlesmeli.webp", "Resmi Sözleşme ve Kanun"),
    ],
    "savunma_enerji": [
        ("local", "website/assets/img/categories/askeri.webp", "Savunma ve Güvenlik"),
        ("local", "website/assets/img/categories/guvenlik.webp", "Stratejik Güvenlik ve Enerji"),
    ],
    "kamu_resmi": [
        ("local", "graphics/assets/backgrounds/general.jpg", "Kamu Kurumu ve Resmi Bina"),
        ("local", "graphics/assets/backgrounds/finance.jpg", "Ekonomi, Bütçe ve Kamu İdaresi"),
        ("local", "website/assets/img/categories/kamu-personel.webp", "Resmi Çalışma Ofisi"),
    ],
}

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0.0.0"}


def save_cropped_webp(im: Image.Image, out_path: Path, target_w: int = 1200, target_h: int = 675) -> None:
    im = im.convert("RGB")
    ratio = max(target_w / im.width, target_h / im.height)
    nw, nh = max(target_w, int(im.width * ratio)), max(target_h, int(im.height * ratio))
    im = im.resize((nw, nh), Image.Resampling.LANCZOS)
    left = (nw - target_w) // 2
    top = (nh - target_h) // 2
    im = im.crop((left, top, left + target_w, top + target_h))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    im.save(out_path, "WEBP", quality=84)


def build_stock_library(force: bool = False) -> Dict[str, Any]:
    STOCK_LIB_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_STOCK_DIR.mkdir(parents=True, exist_ok=True)

    manifest_themes: Dict[str, Any] = {}
    total_images = 0

    for theme_key, sources in THEME_SOURCES.items():
        theme_dir = STOCK_LIB_DIR / theme_key
        theme_dir.mkdir(parents=True, exist_ok=True)
        theme_items = []

        idx = 1
        for src_type, src_val, label in sources:
            out_name = f"{theme_key}_{idx:02d}.webp"
            out_path = theme_dir / out_name
            rel_url = f"/assets/img/stock_library/{theme_key}/{out_name}"

            if out_path.exists() and out_path.stat().st_size > 4000 and not force:
                size_kb = round(out_path.stat().st_size / 1024, 1)
                theme_items.append({
                    "file": out_name,
                    "url": rel_url,
                    "label": label,
                    "source": src_type,
                    "size_kb": size_kb,
                })
                total_images += 1
                idx += 1
                continue

            loaded_img = None
            if src_type == "local":
                local_file = ROOT_DIR / src_val
                if local_file.exists():
                    try:
                        loaded_img = Image.open(local_file)
                    except Exception as e:
                        print(f"  ⚠️ Yerel dosya okunamadı ({src_val}): {e}")
                else:
                    print(f"  ⚠️ Yerel dosya yok: {src_val}")
            elif src_type == "url":
                try:
                    resp = requests.get(src_val, headers=HEADERS, timeout=15)
                    if resp.status_code == 200:
                        loaded_img = Image.open(BytesIO(resp.content))
                except Exception as e:
                    print(f"  ⚠️ URL indirilemedi ({theme_key}): {e}")

            if loaded_img is not None:
                save_cropped_webp(loaded_img, out_path)
                size_kb = round(out_path.stat().st_size / 1024, 1)
                theme_items.append({
                    "file": out_name,
                    "url": rel_url,
                    "label": label,
                    "source": src_type,
                    "size_kb": size_kb,
                })
                total_images += 1
                print(f"  ✅ [{theme_key}] {out_name} ({size_kb} KB) - {label}")
                idx += 1

        manifest_themes[theme_key] = {
            "label": THEME_META.get(theme_key, theme_key),
            "count": len(theme_items),
            "images": theme_items,
        }

    # docs/ altına senkronize et
    for item in STOCK_LIB_DIR.rglob("*"):
        rel = item.relative_to(STOCK_LIB_DIR)
        target = DOCS_STOCK_DIR / rel
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)

    manifest = {
        "total_themes": len(manifest_themes),
        "total_images": total_images,
        "resolution": "1200x675",
        "format": "WEBP",
        "themes": manifest_themes,
    }

    for mp in [
        ROOT_DIR / "website" / "data" / "stock_library_manifest.json",
        ROOT_DIR / "docs" / "data" / "stock_library_manifest.json",
    ]:
        mp.parent.mkdir(parents=True, exist_ok=True)
        mp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"🖼️  Stok Görsel Kütüphanesi hazır: {len(manifest_themes)} tema, {total_images} WebP fotoğraf.")
    return manifest


if __name__ == "__main__":
    build_stock_library()
