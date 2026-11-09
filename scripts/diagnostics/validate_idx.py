# -*- coding: utf-8 -*-
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
print("VALIDASI PRE-DROP -- MachineMinuteLog Indexes")
print("=" * 60)

with connection.cursor() as cursor:

    # 1. Umur statistik
    print("\n[1] UMUR STATISTIK pg_stat_user_indexes")
    cursor.execute("""
        SELECT datname, stats_reset, now() - stats_reset AS age
        FROM pg_stat_database WHERE datname = current_database();
    """)
    r = cursor.fetchone()
    print("  Database :", r[0])
    print("  Reset at :", r[1])
    print("  Age      :", r[2])

    # 2. idx_tup_fetch vs idx_scan
    print("\n[2] idx_scan vs idx_tup_fetch (covering index check index #5)")
    cursor.execute("""
        SELECT indexrelname, idx_scan, idx_tup_read, idx_tup_fetch,
            CASE WHEN idx_scan > 0 THEN round(idx_tup_fetch::numeric/idx_scan,2) ELSE 0 END AS fetch_per_scan,
            CASE WHEN idx_tup_read > 0 THEN round(idx_tup_fetch::numeric/idx_tup_read*100,2) ELSE 0 END AS heap_ratio_pct,
            pg_size_pretty(pg_relation_size(indexrelid)) AS size
        FROM pg_stat_user_indexes
        WHERE relname = 'monitoring_machineminutelog'
        ORDER BY idx_scan DESC;
    """)
    rows = cursor.fetchall()
    print("  {:<55} {:>8} {:>12} {:>12} {:>12} {:>12} {:>10}".format(
        'Index','Scans','TupRead','TupFetch','Fetch/Scan','HeapFetch%','Size'))
    print("  " + "-" * 130)
    for r in rows:
        print("  {:<55} {:>8,} {:>12,} {:>12,} {:>12} {:>11}% {:>10}".format(
            r[0], r[1], r[2], r[3], r[4], r[5], r[6]))

    # 3. Transaksi aktif
    print("\n[3] TRANSAKSI AKTIF saat ini di tabel")
    cursor.execute("""
        SELECT pid, usename, state, now()-query_start AS duration, left(query,100)
        FROM pg_stat_activity
        WHERE query ILIKE '%machineminutelog%' AND state != 'idle'
        ORDER BY query_start;
    """)
    rows = cursor.fetchall()
    if rows:
        for r in rows:
            print("  PID={} user={} state={} dur={}".format(r[0],r[1],r[2],r[3]))
            print("    Q:", r[4])
    else:
        print("  -> Tidak ada transaksi aktif.")

    # 4. Versi PostgreSQL
    print("\n[4] VERSI POSTGRESQL")
    cursor.execute("SELECT version();")
    print(" ", cursor.fetchone()[0][:100])

    # 5. Korelasi fisik timestamp (syarat BRIN)
    print("\n[5] KORELASI FISIK timestamp (syarat BRIN efektif)")
    cursor.execute("""
        SELECT corr FROM pg_stats
        WHERE tablename='monitoring_machineminutelog' AND attname='timestamp';
    """)
    r = cursor.fetchone()
    if r:
        corr = r[0]
        print("  Physical correlation:", corr)
        if corr and abs(corr) > 0.8:
            print("  -> Tinggi => BRIN SANGAT EFEKTIF untuk kolom timestamp")
        else:
            print("  -> Rendah => BTree lebih aman, BRIN berisiko")
    else:
        print("  -> Tidak ada data (jalankan ANALYZE dulu)")

    # 6. Backup DDL
    print("\n[6] BACKUP DDL SEMUA INDEX")
    cursor.execute("""
        SELECT indexrelname, indexdef
        FROM pg_stat_user_indexes ui
        JOIN pg_indexes pi ON ui.indexrelname = pi.indexname
        WHERE ui.relname = 'monitoring_machineminutelog'
        ORDER BY pg_relation_size(indexrelid) DESC;
    """)
    for r in cursor.fetchall():
        print("\n  --", r[0])
        print(" ", r[1] + ";")
