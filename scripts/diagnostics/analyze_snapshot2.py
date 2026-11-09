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
import json

# Analisis Snapshot lebih dalam - berapa besar snapshot_data rata-rata?
with connection.cursor() as cursor:
    # Sample snapshot size
    cursor.execute("""
        SELECT 
            avg(pg_column_size(snapshot_data)) as avg_bytes,
            min(pg_column_size(snapshot_data)) as min_bytes,
            max(pg_column_size(snapshot_data)) as max_bytes,
            count(*) as total_rows
        FROM monitoring_machinestatussnapshot;
    """)
    r = cursor.fetchone()
    print(f"Snapshot JSONB per row:")
    print(f"  Avg size: {r[0]:.0f} bytes")
    print(f"  Min size: {r[1]} bytes")
    print(f"  Max size: {r[2]} bytes")
    print(f"  Total rows: {r[3]:,}")
    
    # Show what the snapshot contains - sample 1 row
    cursor.execute("""
        SELECT snapshot_data FROM monitoring_machinestatussnapshot 
        ORDER BY timestamp DESC LIMIT 1;
    """)
    sample = cursor.fetchone()
    if sample:
        data = sample[0]
        if isinstance(data, list):
            print(f"\n  Sample (list of {len(data)} machines):")
            if len(data) > 0:
                print(f"  First machine keys: {list(data[0].keys())}")
                print(f"  Sample entry:")
                for k, v in list(data[0].items())[:10]:
                    print(f"    {k}: {v}")
        elif isinstance(data, dict):
            print(f"\n  Sample keys: {list(data.keys())}")

    # Cek interval snapshot - berapa menit sekali?
    cursor.execute("""
        SELECT 
            extract(epoch from (lead(timestamp) OVER (ORDER BY timestamp) - timestamp)) / 60 as interval_min
        FROM monitoring_machinestatussnapshot
        ORDER BY timestamp DESC
        LIMIT 20;
    """)
    intervals = [r[0] for r in cursor.fetchall() if r[0] is not None]
    if intervals:
        print(f"\n  Capture interval (last 20 entries):")
        print(f"  Avg: {sum(intervals)/len(intervals):.2f} minutes")
        print(f"  Min: {min(intervals):.2f} minutes")
        print(f"  Max: {max(intervals):.2f} minutes")
