import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import os
import django
import sys
from datetime import datetime

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
django.setup()

from monitoring.models import DyeingIdentity

today = datetime(2026, 9, 1).date()

qs = DyeingIdentity.objects.filter(created_at__date=today).order_by('-created_at')

print(f"Total DyeingIdentity hari ini (2026-09-01): {qs.count()}")
print("-" * 50)
for item in qs:
    print(f"ID: {item.id} | No Order: {item.nomor_order} | Artikel: {item.artikel_kain} | Batch: {item.batch} | Warna: {item.nomor_warna} | Jenis: {item.jenis_proses} | Operator: {item.operator} | Waktu: {item.created_at.strftime('%H:%M:%S') if item.created_at else 'None'} | Mesin: {item.machine.code if item.machine else 'None'} | Process: {item.dyeing_process.id if item.dyeing_process else 'None'}")
