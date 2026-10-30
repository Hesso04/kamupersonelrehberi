"""
Geçmiş hatalı yıl kontenjanlarını (2026, 2027 vb.) ve teyitsiz 1 değerlerini
merkezi quota_validator üzerinden düzelten onarım scripti.
"""
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from core.database import get_db
from core.models import JobAnnouncement
from core.quota_validator import extract_verified_quota

def run_fix():
    with get_db() as db:
        jobs = db.query(JobAnnouncement).all()
        fixed_count = 0
        for j in jobs:
            # 2026/2027 veya kanun numarası gibi bariz hatalar
            if j.total_positions in [2024, 2025, 2026, 2027, 2028, 657, 4857] or not j.total_positions:
                old_val = j.total_positions
                q_res = extract_verified_quota(j.title or "", j.raw_content or "", default_val=1)
                j.total_positions = q_res["quota"]
                disp = q_res["display_text"]
                print(f"Onarıldı #{j.id}: {old_val} -> {j.total_positions} ({disp}) | {j.title[:50]}")
                fixed_count += 1
        print(f"\n✅ Toplam {fixed_count} hatalı ilan başarıyla onarıldı.")

if __name__ == "__main__":
    run_fix()
