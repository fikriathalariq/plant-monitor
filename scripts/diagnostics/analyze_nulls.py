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

# Cek kolom-kolom di MachineMinuteLog dan analisis null/non-null rate
with connection.cursor() as cursor:
    # Analisis per kolom: berapa persen nilainya NULL, total storage estimasi per kolom
    cursor.execute("""
        SELECT count(*) as total FROM monitoring_machineminutelog;
    """)
    total = cursor.fetchone()[0]
    
    # Check null percentage per column that matters
    columns = ['raw_temperature', 'temperature', 'filtered_temp', 'gradient', 
               'thermal_state', 'last_status', 'data_quality']
    
    print(f"Total rows: {total:,}")
    print()
    print(f"{'Column':<25} {'Non-NULL':>12} {'NULL':>12} {'% NULL':>8}")
    print("-" * 65)
    
    for col in columns:
        cursor.execute(f"""
            SELECT 
                COUNT(*) FILTER (WHERE {col} IS NOT NULL) as non_null,
                COUNT(*) FILTER (WHERE {col} IS NULL) as null_count
            FROM monitoring_machineminutelog;
        """)
        non_null, null_count = cursor.fetchone()
        pct_null = (null_count / total * 100) if total > 0 else 0
        print(f"{col:<25} {non_null:>12,} {null_count:>12,} {pct_null:>7.1f}%")
