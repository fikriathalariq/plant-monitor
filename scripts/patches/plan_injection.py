import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

﻿import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
django.setup()

from monitoring.models import Machine

auto_machines = Machine.objects.filter(is_active=True, operation_mode='AUTO').order_by('code')

print("=== PLAN INJEKSI 51 MESIN AUTO ===")
print("Semua mesin di bawah ini akan di-set menjadi sensor untuk dirinya sendiri (1:1 mapping).")
print("Karena mengikuti logika sistem yang ada saat ini, semuanya akan di-set ke THERMAL_STATE_BASED.\n")

for m in auto_machines:
    print(f"[{m.code}] {m.name}")
    print(f"  |- TRIGGER_OP     -> Sensor: {m.code} | Metode: THERMAL_STATE_BASED")
    print(f"  +- TRIGGER_ENERGY -> Sensor: {m.code} | Metode: THERMAL_STATE_BASED")

print("\n(Note: Untuk mesin Continuous seperti CDR, metode ini nanti bisa diedit menjadi STATIC_HYSTERESIS dari Django Admin setelah di-seed).")
