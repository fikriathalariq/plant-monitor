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

from django.db import connection

print("=" * 60)
print("VALIDASI PRE-DROP  MachineMinuteLog Indexes")
print("=" * 60)

with connection.cursor() as cursor:

    # -- 1. Umur statistik --------------------------------------
    print("\n[1] UMUR STATISTIK pg_stat_user_indexes")
    cursor.execute("""
        SELECT 
            datname,
            stats_reset,
            now() - stats_reset AS age
        FROM pg_stat_database 
        WHERE datname = current_database();
    """)
    r = cursor.fetchone()
    print(f"  Database : {r[0]}")
    print(f"  Reset at : {r[1]}")
    print(f"  Age      : {r[2]}")

    # -- 2. idx_tup_fetch vs idx_scan per index ------------------
    print("\n[2] idx_scan vs idx_tup_fetch (kunci untuk covering index #5)")
    cursor.execute("""
        SELECT 
            indexrelname,
            idx_scan,
            idx_tup_read,
            idx_tup_fetch,
            CASE WHEN idx_scan > 0 
                 THEN round(idx_tup_fetch::numeric / idx_scan, 2) 
                 ELSE 0 END AS fetch_per_scan,
            CASE WHEN idx_tup_read > 0 
                 THEN round(idx_tup_fetch::numeric / idx_tup_read * 100, 2) 
                 ELSE 0 END AS heap_fetch_ratio_pct,
            pg_size_pretty(pg_relation_size(indexrelid)) AS size
        FROM pg_stat_user_indexes
        WHERE relname = 'monitoring_machineminutelog'
        ORDER BY idx_scan DESC;
    """)
    rows = cursor.fetchall()
    print(f"\n  {'Index':<55} {'Scans':>8} {'TupRead':>12} {'TupFetch':>12} {'Fetch/Scan':>12} {'HeapFetch%':>12} {'Size':>10}")
    print("  " + "-" * 125)
    for r in rows:
        print(f"  {r[0]:<55} {r[1]:>8,} {r[2]:>12,} {r[3]:>12,} {r[4]:>12} {r[5]:>11}% {r[6]:>10}")

    # -- 3. Cek apakah ada query aktif yang lock tabel ini -------
    print("\n[3] TRANSAKSI AKTIF yang sedang akses tabel (untuk DROP timing)")
    cursor.execute("""
        SELECT pid, usename, application_name, state, 
               query_start, now() - query_start AS duration, left(query, 100) AS query_snippet
        FROM pg_stat_activity
        WHERE query ILIKE '%machineminutelog%'
          AND state != 'idle'
        ORDER BY query_start;
    """)
    rows = cursor.fetchall()
    if rows:
        for r in rows:
            print(f"  PID={r[0]}, user={r[1]}, state={r[2]}, duration={r[5]}")
            print(f"  Query: {r[6]}")
    else:
        print("  ? Tidak ada transaksi aktif yang menyentuh tabel ini saat ini.")

    # -- 4. Cek ada BRIN option? (versi PostgreSQL) --------------
    print("\n[4] VERSI POSTGRESQL (untuk cek BRIN & partitioning support)")
    cursor.execute("SELECT version();")
    print(f"  {cursor.fetchone()[0][:80]}")
