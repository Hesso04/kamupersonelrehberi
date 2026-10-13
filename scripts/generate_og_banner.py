import os
from PIL import Image, ImageDraw, ImageFont

# Ensure directories exist
os.makedirs("website/assets/img", exist_ok=True)
os.makedirs("docs/assets/img", exist_ok=True)

width, height = 1200, 630
img = Image.new("RGB", (width, height), color=(15, 23, 42))  # slate-900
draw = ImageDraw.Draw(img)

# 1. Subtle gradient background
for y in range(height):
    r = int(11 + (y / height) * 15)
    g = int(17 + (y / height) * 22)
    b = int(32 + (y / height) * 35)
    draw.line([(0, y), (width, y)], fill=(r, g, b))

# 2. Glowing ambient circles
glow_overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
glow_draw = ImageDraw.Draw(glow_overlay)

# Blue / Cyan glow top right and bottom left
for radius in range(250, 0, -5):
    alpha = int(25 * (1 - radius / 250))
    glow_draw.ellipse([900 - radius, 120 - radius, 900 + radius, 120 + radius], fill=(37, 99, 235, alpha))
    glow_draw.ellipse([150 - radius, 520 - radius, 150 + radius, 520 + radius], fill=(14, 165, 233, alpha))

img = Image.alpha_composite(img.convert("RGBA"), glow_overlay).convert("RGB")
draw = ImageDraw.Draw(img)

# 3. Decorative top border (Turkish red & turquoise gradient line)
for x in range(width):
    ratio = x / width
    r_val = int(239 * (1 - ratio) + 14 * ratio)
    g_val = int(68 * (1 - ratio) + 165 * ratio)
    b_val = int(68 * (1 - ratio) + 233 * ratio)
    draw.line([(x, 0), (x, 6)], fill=(r_val, g_val, b_val))

# Font selection
try:
    font_badge = ImageFont.truetype("arialbd.ttf", 20)
    font_title = ImageFont.truetype("arialbd.ttf", 64)
    font_sub = ImageFont.truetype("arial.ttf", 26)
    font_tags = ImageFont.truetype("arialbd.ttf", 22)
    font_url = ImageFont.truetype("arialbd.ttf", 24)
except Exception:
    font_badge = ImageFont.load_default()
    font_title = ImageFont.load_default()
    font_sub = ImageFont.load_default()
    font_tags = ImageFont.load_default()
    font_url = ImageFont.load_default()

# 4. Badge: "T.C. KAMU İLANLARI & MEMUR ALIMLARI"
badge_text = "🇹🇷 T.C. RESMİ KAMU İLANLARI & MEMUR ALIM REHBERİ"
# Draw rounded pill box
badge_bbox = draw.textbbox((0, 0), badge_text, font=font_badge)
badge_w = badge_bbox[2] - badge_bbox[0]
badge_x = (width - badge_w) // 2
badge_y = 100
padding_x, padding_y = 24, 10
draw.rounded_rectangle(
    [badge_x - padding_x, badge_y - padding_y, badge_x + badge_w + padding_x, badge_y + 24 + padding_y],
    radius=18,
    fill=(30, 41, 59),
    outline=(59, 130, 246),
    width=2
)
draw.text((badge_x, badge_y), badge_text, font=font_badge, fill=(147, 197, 253))

# 5. Main Title
title_text = "KAMU PERSONEL REHBERİ"
title_bbox = draw.textbbox((0, 0), title_text, font=font_title)
title_w = title_bbox[2] - title_bbox[0]
title_x = (width - title_w) // 2
draw.text((title_x, 185), title_text, font=font_title, fill=(255, 255, 255))

# 6. Subtitle
sub_text = "Güncel Memur, Sözleşmeli Personel, İşçi ve Akademik Kadro Alımları"
sub_bbox = draw.textbbox((0, 0), sub_text, font=font_sub)
sub_w = sub_bbox[2] - sub_bbox[0]
sub_x = (width - sub_w) // 2
draw.text((sub_x, 280), sub_text, font=font_sub, fill=(203, 213, 225))

sub_text_2 = "Resmi Gazete ve Kamu İlan Portalları Teyitli Başvuru Kılavuzları & Şartnameler"
sub2_bbox = draw.textbbox((0, 0), sub_text_2, font=font_sub)
sub2_w = sub2_bbox[2] - sub2_bbox[0]
draw.text(((width - sub2_w) // 2, 325), sub_text_2, font=font_sub, fill=(148, 163, 184))

# 7. Trust Badges (Cards in a row)
badges = [
    ("✓ %100 Resmi Teyitli", (16, 185, 129)),
    ("✓ PDF Kılavuz İndirme", (59, 130, 246)),
    ("✓ Doğrudan Başvuru Ekranı", (168, 85, 247)),
    ("✓ Anlık Sonuç Duyuruları", (245, 158, 11))
]
card_w = 230
total_cards_w = len(badges) * card_w + (len(badges) - 1) * 20
start_card_x = (width - total_cards_w) // 2
card_y = 405

for i, (b_txt, b_color) in enumerate(badges):
    bx = start_card_x + i * (card_w + 20)
    draw.rounded_rectangle(
        [bx, card_y, bx + card_w, card_y + 55],
        radius=12,
        fill=(30, 41, 59, 200),
        outline=b_color,
        width=1
    )
    b_t_bbox = draw.textbbox((0, 0), b_txt, font=font_tags)
    b_tw = b_t_bbox[2] - b_t_bbox[0]
    draw.text((bx + (card_w - b_tw) // 2, card_y + 14), b_txt, font=font_tags, fill=(241, 245, 249))

# 8. Bottom URL Bar
url_text = "🌐 https://kamupersonelrehberiniz.me"
url_bbox = draw.textbbox((0, 0), url_text, font=font_url)
url_w = url_bbox[2] - url_bbox[0]
draw.text(((width - url_w) // 2, 530), url_text, font=font_url, fill=(96, 165, 250))

# Save image
out_paths = [
    "website/assets/img/og-banner.png",
    "docs/assets/img/og-banner.png"
]
for p in out_paths:
    img.save(p, "PNG", optimize=True)
    print(f"Saved: {p} ({os.path.getsize(p)} bytes)")
