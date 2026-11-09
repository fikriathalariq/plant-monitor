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

print("=== COVERING INDEX ANALYSIS: idx_log_machine_ts_dq ===")
print()
with connection.cursor() as cursor:
    
    # Cari query mana yang BENAR-BENAR memakai index #5 sebagai covering scan
    # Hint: idx_tup_fetch jauh lebih rendah dari idx_tup_read = index-only scan
    cursor.execute("""
        SELECT indexrelname, idx_scan, idx_tup_read, idx_tup_fetch,
            CASE WHEN idx_tup_read > 0 
                THEN round((1.0 - idx_tup_fetch::numeric/idx_tup_read)*100, 2) 
                ELSE 0 END AS index_only_scan_pct
        FROM pg_stat_user_indexes
        WHERE relname = 'monitoring_machineminutelog'
          AND indexrelname IN ('idx_log_machine_ts_dq', 
                               'monitoring_machineminutelog_machine_id_timestamp_d76393d5_uniq',
                               'idx_log_machine_ts_desc')
        ORDER BY idx_scan DESC;
    """)
    rows = cursor.fetchall()
    print("Index-Only Scan Analysis:")
    print("{:<60} {:>8} {:>12} {:>12} {:>18}".format(
        "Index", "Scans", "TupRead", "TupFetch", "IndexOnlyScan%"))
    print("-" * 120)
    for r in rows:
        print("{:<60} {:>8,} {:>12,} {:>12,} {:>17}%".format(
            r[0], r[1], r[2], r[3], r[4]))
    
    print()
    print("Interpretasi:")
    print("  IndexOnlyScan% = persen scan yang TIDAK perlu baca heap (disk page)")
    print("  Semakin tinggi = index ini benar-benar dipakai sebagai covering index")
    print("  Semakin rendah = PostgreSQL pakai index untuk lokasi, lalu fetch heap")
    print()

    # EXPLAIN ANALYZE simulasi query yang mungkin pakai #5 sebagai covering
    print("=== EXPLAIN plan: query yang kemungkinan pakai index #5 ===")
    
    # Query 1: yang paling sering di log_minute_history (machine + timestamp filter)
    cursor.execute("""
        EXPLAIN (FORMAT TEXT, COSTS ON, BUFFERS OFF)
        SELECT machine_id, timestamp, data_quality 
        FROM monitoring_machineminutelog
        WHERE machine_id = 1 AND timestamp >= NOW() - INTERVAL '2 hours'
        ORDER BY timestamp;
    """)
    rows = cursor.fetchall()
    print("\nQuery A: SELECT machine_id, timestamp, data_quality WHERE machine+ts")
    for r in rows:
        print(" ", r[0])

    # Query 2: Full scan timestamp-only 
    cursor.execute("""
        EXPLAIN (FORMAT TEXT, COSTS ON, BUFFERS OFF)
        SELECT machine_id, timestamp, data_quality
        FROM monitoring_machineminutelog
        WHERE timestamp >= NOW() - INTERVAL '2 hours'
        ORDER BY timestamp;
    """)
    rows = cursor.fetchall()
    print("\nQuery B: SELECT machine_id, timestamp, data_quality WHERE only timestamp")
    for r in rows:
        print(" ", r[0])
        
    # What does #5 extra column buy us?
    print()
    print("=== STATS_RESET CHECK ===")
    cursor.execute("""
        SELECT stats_reset, 
               CASE WHEN stats_reset IS NULL THEN 'NEVER RESET (stats since server init)'
               ELSE 'Reset at: ' || stats_reset::text 
               END as interpretation
        FROM pg_stat_database WHERE datname = current_database();
    """)
    r = cursor.fetchone()
    print(" ", r[1])
    if r[0] is None:
        print("  -> stats_reset = NULL artinya statistik ini terkumpul SEJAK")
        print("     PostgreSQL pertama kali diinisialisasi/diinstall.")
        print("     Data angka scan ini sangat representatif dan bisa dipercaya.")
