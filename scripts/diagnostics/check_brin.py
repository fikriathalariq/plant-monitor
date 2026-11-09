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
from django.db import connection

with connection.cursor() as cursor:
    # Fix: pg_stats column name in PG17
    cursor.execute("""
        SELECT column_name FROM information_schema.columns 
        WHERE table_name = 'pg_stats' ORDER BY ordinal_position;
    """)
    cols = [r[0] for r in cursor.fetchall()]
    print("pg_stats columns:", cols)

    # Then check correlation column
    corr_col = 'correlation' if 'correlation' in cols else ('corr' if 'corr' in cols else None)
    print("Correlation column:", corr_col)

    if corr_col:
        cursor.execute(f"""
            SELECT {corr_col}, n_distinct, null_frac 
            FROM pg_stats
            WHERE tablename='monitoring_machineminutelog' AND attname='timestamp';
        """)
        r = cursor.fetchone()
        if r:
            print("Correlation:", r[0])
            print("n_distinct:", r[1])
            print("null_frac:", r[2])
        else:
            print("No stats found - run ANALYZE first")
