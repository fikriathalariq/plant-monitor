import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
django.setup()
from monitoring.models import Machine
from django.db.models import Count

print("=== DISTRIBUSI OPERATION MODE ===")
for row in Machine.objects.filter(is_active=True).values('operation_mode').annotate(cnt=Count('id')):
    print(f"Mode: {row['operation_mode']} -> {row['cnt']} mesin")

print("\n=== CONTOH MESIN MANUAL ===")
for m in Machine.objects.filter(is_active=True, operation_mode='MANUAL')[:10]:
    print(f"{m.code}: name={m.name}, type={m.machine_type}, manual_status={m.manual_status}")

print("\n=== CONTOH MESIN AUTO ===")
for m in Machine.objects.filter(is_active=True, operation_mode='AUTO')[:10]:
    print(f"{m.code}: name={m.name}, type={m.machine_type}, temp={m.temperature}")
