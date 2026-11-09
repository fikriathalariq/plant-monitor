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

print("=== HUNTING THE COVERING INDEX QUERY ===")
with connection.cursor() as cursor:
    try:
        cursor.execute("""
            SELECT query, calls, rows 
            FROM pg_stat_statements 
            WHERE query ILIKE '%monitoring_machineminutelog%'
              AND query ILIKE '%data_quality%'
            ORDER BY calls DESC LIMIT 5;
        """)
        rows = cursor.fetchall()
        if rows:
            for r in rows:
                print(f"Calls: {r[1]}, Rows: {r[2]}")
                print(f"Query: {r[0][:150]}...\n")
        else:
            print("No queries found in pg_stat_statements matching data_quality.")
            
        cursor.execute("""
            SELECT query, calls, rows 
            FROM pg_stat_statements 
            WHERE query ILIKE '%monitoring_machineminutelog%'
            ORDER BY calls DESC LIMIT 10;
        """)
        rows = cursor.fetchall()
        print("\nTop 10 most called queries on MachineMinuteLog:")
        for r in rows:
            print(f"Calls: {r[1]}")
            print(f"Query: {r[0][:150]}...\n")

    except Exception as e:
        print(f"pg_stat_statements error: {e}")
