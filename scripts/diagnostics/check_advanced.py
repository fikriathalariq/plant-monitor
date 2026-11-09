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

print("=== 1. CHECK REINDEX HISTORY (OID vs Relfilenode) & LAST VACUUM ===")
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT 
            i.relname AS index_name,
            i.oid,
            i.relfilenode,
            CASE WHEN i.oid = i.relfilenode THEN 'Original' ELSE 'Reindexed/Rebuilt' END AS status,
            psui.idx_scan
        FROM pg_class i
        JOIN pg_index ix ON i.oid = ix.indexrelid
        JOIN pg_stat_user_indexes psui ON i.oid = psui.indexrelid
        WHERE i.relname IN (
            'monitoring__machine_f2f068_idx', 
            'monitoring_machineminutelog_machine_id_d7c640fa',
            'monitoring__thermal_484794_idx',
            'idx_log_machine_ts_dq'
        );
    """)
    rows = cursor.fetchall()
    print("{:<50} {:<10} {:<15} {:<20} {:<10}".format("Index", "OID", "Relfilenode", "Status", "Scans"))
    print("-" * 110)
    for r in rows:
        print("{:<50} {:<10} {:<15} {:<20} {:<10}".format(r[0], r[1], r[2], r[3], r[4]))

print("\n=== 2. CHECK REPLICA IDENTITY (indisreplident) ===")
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT indexrelid::regclass, indisreplident 
        FROM pg_index 
        WHERE indrelid = 'monitoring_machineminutelog'::regclass
          AND indisreplident = true;
    """)
    rows = cursor.fetchall()
    if rows:
        for r in rows:
            print(f"Replica Identity Index: {r[0]}")
    else:
        print("-> Tidak ada index yang diset sebagai REPLICA IDENTITY (Aman).")
