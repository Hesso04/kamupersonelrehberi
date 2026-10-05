FROM python:3.11-slim

# Sistem bağımlılıkları ve yazı tipi paketleri
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    fontconfig \
    libfreetype6-dev \
    libpng-dev \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Çalışma dizini
WORKDIR /app

# Bağımlılıkları yükle
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Uygulama dosyalarını kopyala
COPY . .

# Gerekli dizinlerin oluşturulması
RUN mkdir -p data graphics/output graphics/assets/fonts graphics/assets/templates

# Hugging Face Spaces / Render standart portu (7860 veya 8501)
EXPOSE 7860

# Streamlit konfigürasyonu
ENV STREAMLIT_SERVER_PORT=7860
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0
ENV STREAMLIT_SERVER_HEADLESS=true
ENV STREAMLIT_SERVER_ENABLE_CORS=false
ENV STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION=false

# Uygulamayı başlat
CMD ["streamlit", "run", "ui/app.py"]
