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

print("=== Kolom di MachineMinuteLog (AKTUAL dari DB) ===")
# ewma_temp, kalman_p, kalman_x, ewma_gradient, kalman_grad_x - apakah ini dipakai di code?
interesting = ['ewma_temp', 'kalman_p', 'kalman_x', 'ewma_gradient', 'kalman_grad_x']
print(f"Kolom 'tersembunyi' yang tidak ada di model Python:")
for col in interesting:
    print(f"  - {col}")

print("\n=== Index pada MachineMinuteLog ===")
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT indexrelname, pg_size_pretty(pg_relation_size(indexrelid)) as idx_size
        FROM pg_stat_user_indexes
        WHERE relname = 'monitoring_machineminutelog'
        ORDER BY pg_relation_size(indexrelid) DESC;
    """)
    for r in cursor.fetchall():
        print(f"  {r[0]}: {r[1]}")

print("\n=== Distribusi thermal_state (berapa OFFLINE vs NORMAL?) ===")
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT thermal_state, count(*) as cnt, 
               round(count(*) * 100.0 / sum(count(*)) over(), 2) as pct
        FROM monitoring_machineminutelog
        GROUP BY thermal_state
        ORDER BY cnt DESC;
    """)
    for r in cursor.fetchall():
        print(f"  {r[0] or 'NULL'}: {r[1]:,} ({r[2]}%)")

print("\n=== Distribusi data_quality ===")
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT data_quality, count(*) as cnt, 
               round(count(*) * 100.0 / sum(count(*)) over(), 2) as pct
        FROM monitoring_machineminutelog
        GROUP BY data_quality
        ORDER BY cnt DESC;
    """)
    for r in cursor.fetchall():
        print(f"  {r[0] or 'NULL'}: {r[1]:,} ({r[2]}%)")
