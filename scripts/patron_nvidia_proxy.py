"""
Kamu Personel Rehberi — Opsiyonel Yerel NVIDIA NIM Sohbet Köprüsü
=================================================================
Lokal bilgisayardaki .env içindeki NVIDIA_API_KEY kullanarak
http://127.0.0.1:8787/v1/chat/completions adresinde CORS destekli
OpenAI-uyumlu köprü açar. Patron Paneli'ndeki AI Asistanı "Özel / NVIDIA Köprüsü"
moduyla doğrudan bu adrese bağlanabilir.
"""

import http.server
import json
import os
from pathlib import Path
import requests

ROOT_DIR = Path(__file__).resolve().parent.parent


def load_nvidia_key() -> str:
    env_path = ROOT_DIR / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("NVIDIA_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return os.getenv("NVIDIA_API_KEY", "").strip()


class BridgeHandler(http.server.BaseHTTPRequestHandler):
    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        key = load_nvidia_key()
        if not key:
            self.send_response(400)
            self._cors_headers()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": ".env içinde NVIDIA_API_KEY bulunamadı"}).encode("utf-8"))
            return

        try:
            body = json.loads(raw.decode("utf-8"))
            if not body.get("model") or body["model"] == "default":
                body["model"] = "nvidia/nemotron-3-ultra-550b-a55b"
            body["chat_template_kwargs"] = {"enable_thinking": False}
            r = requests.post(
                "https://integrate.api.nvidia.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=body,
                timeout=45,
            )
            self.send_response(r.status_code)
            self._cors_headers()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(r.content)
        except Exception as e:
            self.send_response(500)
            self._cors_headers()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))


if __name__ == "__main__":
    print("🚀 NVIDIA NIM Yerel Köprüsü çalışıyor: http://127.0.0.1:8787/v1/chat/completions")
    http.server.HTTPServer(("127.0.0.1", 8787), BridgeHandler).serve_forever()
