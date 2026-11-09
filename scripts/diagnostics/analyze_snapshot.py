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

# Analisis MachineStatusSnapshot - berapa lama interval dan berapa duplikat?
with connection.cursor() as cursor:
    cursor.execute("SELECT count(*) FROM monitoring_machinestatussnapshot;")
    snap_count = cursor.fetchone()[0]
    
    cursor.execute("""
        SELECT 
            pg_size_pretty(pg_total_relation_size('monitoring_machinestatussnapshot')) as total_size,
            pg_size_pretty(pg_relation_size('monitoring_machinestatussnapshot')) as table_size,
            pg_size_pretty(pg_total_relation_size('monitoring_machinestatussnapshot') - pg_relation_size('monitoring_machinestatussnapshot')) as index_size
    """)
    sz = cursor.fetchone()
    
    print(f"MachineStatusSnapshot:")
    print(f"  Total rows: {snap_count:,}")
    print(f"  Table size: {sz[0]} (data: {sz[1]}, indexes: {sz[2]})")
    
    # Snapshot index ratio (indexes vs data)
    cursor.execute("""
        SELECT 
            pg_total_relation_size('monitoring_machinestatussnapshot') as total,
            pg_relation_size('monitoring_machinestatussnapshot') as data
    """)
    r = cursor.fetchone()
    idx_pct = (r[0] - r[1]) / r[0] * 100
    print(f"  Index overhead: {idx_pct:.1f}% of total!")
    
    # Distinct columns in snapshot
    cursor.execute("""
        SELECT column_name, data_type, character_maximum_length
        FROM information_schema.columns
        WHERE table_name = 'monitoring_machinestatussnapshot'
        ORDER BY ordinal_position;
    """)
    cols = cursor.fetchall()
    print(f"\n  Columns ({len(cols)}):")
    for col in cols:
        print(f"    - {col[0]}: {col[1]}")
