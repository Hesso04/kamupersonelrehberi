"""
Kamu Personel Rehberi - Başlatıcı Script
Kullanım: python run.py
"""
import sys
import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent

if __name__ == "__main__":
    app_path = ROOT_DIR / "ui" / "app.py"
    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app_path),
        "--server.port=8501",
        "--server.address=localhost",
        "--browser.serverAddress=localhost",
    ]
    print("=" * 60)
    print("🏛  KAMU PERSONEL REHBERİ - ADMİN & OTOMASYON PORTALI")
    print("=" * 60)
    print(f"Tarayıcıda açılıyor: http://localhost:8501")
    print("Çıkmak için CTRL+C tuşlarına basabilirsiniz.\n")
    
    subprocess.run(cmd)
