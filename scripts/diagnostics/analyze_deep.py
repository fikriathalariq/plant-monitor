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

# Analisis: apakah snapshot sudah redundan dengan MachineMinuteLog?
# Cek apa yang di-query dari snapshot di aggregate_steam_history.py
print("=== Isi snapshot sebenarnya ===")
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT snapshot_data->0 FROM monitoring_machinestatussnapshot 
        ORDER BY timestamp DESC LIMIT 1;
    """)
    row = cursor.fetchone()
    if row:
        item = row[0]
        if isinstance(item, dict):
            for k, v in item.items():
                print(f"  {k}: {repr(v)[:80]}")

print("\n=== MachineMinuteLog - kolom apa saja yang ada? ===")
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'monitoring_machineminutelog'
        ORDER BY ordinal_position;
    """)
    cols = cursor.fetchall()
    for col in cols:
        print(f"  {col[0]}: {col[1]}")

print("\n=== Perbandingan ukuran index di MachineMinuteLog ===")
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT
            indexname,
            pg_size_pretty(pg_relation_size(indexrelid)) as index_size
        FROM pg_stat_user_indexes
        WHERE relname = 'monitoring_machineminutelog'
        ORDER BY pg_relation_size(indexrelid) DESC;
    """)
    rows = cursor.fetchall()
    for r in rows:
        print(f"  {r[0]}: {r[1]}")
