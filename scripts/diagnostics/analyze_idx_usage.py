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

print("=== INDEX USAGE STATS (berapa kali setiap index dipakai PostgreSQL) ===")
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT 
            indexrelname as index_name,
            idx_scan as times_scanned,
            idx_tup_read as tuples_read,
            idx_tup_fetch as tuples_fetched,
            pg_size_pretty(pg_relation_size(indexrelid)) as size
        FROM pg_stat_user_indexes
        WHERE relname = 'monitoring_machineminutelog'
        ORDER BY idx_scan DESC;
    """)
    rows = cursor.fetchall()
    print(f"\n{'Index':<55} {'Scans':>10} {'Tuples Read':>15} {'Size':>10}")
    print("-" * 100)
    for r in rows:
        print(f"{r[0]:<55} {r[1]:>10,} {r[2]:>15,} {r[4]:>10}")
