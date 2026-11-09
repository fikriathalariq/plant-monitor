import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
django.setup()

from django.db import connection

# Analisis mendalam snapshot - apa saja isinya?
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT snapshot_data FROM monitoring_machinestatussnapshot 
        ORDER BY timestamp DESC LIMIT 1;
    """)
    sample = cursor.fetchone()
    if sample:
        data = sample[0]
        if isinstance(data, list) and len(data) > 0:
            print(f"Snapshot berisi list dari {len(data)} entries")
            print(f"\nContoh 1 entry (semua keys & values):")
            for k, v in data[0].items():
                print(f"  {k}: {repr(v)[:80]}")
