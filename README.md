# 🏛 Kamu Personel Rehberi (Anti-Clickbait Kamu Alımları Otomasyonu)

> **Misyon:** İnternetteki bilgi kirliliğini ve asılsız "müjde/şok" tık tuzağı (clickbait) ilanları bitirmek; adaylara **%100 doğrulanmış, resmi kaynaklı** (Resmi Gazete, SBB Kamu İlan Portalı vb.) kamu alımlarını şeffaf, hızlı ve kurumsal görsel/metinlerle ulaştırmak.

---

## 🚀 Hızlı Başlangıç

### 1. Bağımlılıkları Yükleme
```bash
# Sanal ortamı aktive ediniz (veya doğrudan uv/pip kullanınız)
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Uygulamayı Başlatma
Tek komutla hem veritabanını senkronize edebilir hem de Streamlit Admin & Onay Panelini açabilirsiniz:

```bash
python run.py
```
*Tarayıcınızda otomatik olarak açılır:* `http://localhost:8501`

---

## 🛠 Mimari ve Modüller

```
kamupersonelrehberi/
├── run.py                      # Tek tıkla sistemi başlatan kök script
├── requirements.txt            # Streamlit, Pydantic, Pillow, Groq, SQLAlchemy vb.
├── .env.example                # Ortam değişkenleri şablonu
│
├── config/
│   └── settings.py             # Pydantic tabanlı statik + dinamik DB ayar köprüsü
│
├── core/
│   ├── models.py               # JobAnnouncement, SystemSetting, JobStatus enumları
│   └── database.py             # SQLite oturum yönetimi, CRUD ve tohumlama
│
├── scrapers/
│   ├── base.py                 # Doğrulama filtreleri içeren BaseScraper
│   ├── kamu_ilan_sbb.py        # SBB Kamu İlan Portalı resmi kazıyıcısı (.gov.tr)
│   ├── resmi_gazete.py         # Resmi Gazete Çeşitli İlanlar kazıyıcısı
│   └── manager.py              # Mükerrer kayıtları önleyen merkezi orkestratör
│
├── ai/
│   ├── groq_client.py          # Groq Cloud LLM istemcisi ve akıllı fallback motoru
│   ├── prompts.py              # Anti-clickbait kurumsal sistem promptları
│   └── processor.py            # Yapısal veri çıkarımı ve Telegram metni üretimi
│
├── graphics/
│   ├── generator.py            # Pillow ile 1080x1080 modern kurumsal kart üretici
│   ├── assets/fonts/           # Full Türkçe destekli TTF yazı tipleri
│   └── output/                 # Üretilen ilan kartları (.png)
│
├── publishers/
│   ├── base.py                 # BasePublisher arayüzü
│   ├── telegram.py             # Telegram Bot API (Fotoğraflı + Butonlu paylaşım)
│   └── manager.py              # Çok kanallı dağıtım koordinatörü
│
└── ui/
    └── app.py                  # Streamlit Admin & Human-in-the-Loop Onay Paneli
```

---

## 🔑 Dinamik Ayarlar ve Güvenlik (Zero-Hardcoding)

Hiçbir API anahtarı veya model koda gömülü değildir:
1. Panel açıldığında **"⚙️ Sistem & API Ayarları"** sekmesine gidilir.
2. `GROQ_API_KEY`, model seçimi (`llama-3.3-70b-versatile` vb.), `TELEGRAM_BOT_TOKEN` ve `TELEGRAM_CHANNEL_ID` girilip **Kaydet** butonuna basılır.
3. Ayarlar SQLite `system_settings` tablosunda kalıcı olarak saklanır ve sistem yeniden başlasa bile korunur.
4. "🧪 Bağlantıyı Test Et" butonları ile canlı entegrasyonlar doğrulanabilir.

---

## 📋 İnsan Onaylı Yaşam Döngüsü (State Machine)

1. **DRAFT:** Resmi kaynaklardan (`kamuilan.sbb.gov.tr`) kazınır ve `.gov.tr` doğrulaması yapılır.
2. **AI_PROCESSED:** Groq LLM ilanı analiz eder; kadro, mezuniyet, KPSS şartı ve Telegram paylaşım metnini üretir.
3. **PENDING_APPROVAL:** Admin panelinde onay kuyruğuna düşer. Admin bilgileri düzenleyebilir ve kart görselini önizleyebilir.
4. **APPROVED & PUBLISHED:** Admin "Onayla ve Paylaş" butonuna bastığı an görsel ve metin Telegram kanalına iletilir.
