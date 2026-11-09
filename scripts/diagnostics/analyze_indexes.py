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

print("=== DEFINISI LENGKAP SEMUA INDEX ===")
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT 
            indexrelname as index_name,
            pg_size_pretty(pg_relation_size(indexrelid)) as size,
            indexdef
        FROM pg_stat_user_indexes ui
        JOIN pg_indexes pi ON ui.indexrelname = pi.indexname
        WHERE ui.relname = 'monitoring_machineminutelog'
        ORDER BY pg_relation_size(indexrelid) DESC;
    """)
    rows = cursor.fetchall()
    for r in rows:
        print(f"\nIndex: {r[0]}")
        print(f"  Size: {r[1]}")
        print(f"  DDL:  {r[2]}")
