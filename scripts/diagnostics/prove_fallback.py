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

print("=== PROVING FALLBACK TO INDEX #2 ===")
with connection.cursor() as cursor:
    cursor.execute("BEGIN;")
    
    print("\n1. EXPLAIN before drop:")
    cursor.execute("EXPLAIN SELECT 1 FROM monitoring_machineminutelog WHERE machine_id = 1 AND timestamp >= NOW() - INTERVAL '1 day' LIMIT 1;")
    for r in cursor.fetchall(): print("  ", r[0])
        
    print("\n2. Dropping index #5...")
    cursor.execute("DROP INDEX idx_log_machine_ts_dq;")
    
    print("\n3. EXPLAIN after drop:")
    cursor.execute("EXPLAIN SELECT 1 FROM monitoring_machineminutelog WHERE machine_id = 1 AND timestamp >= NOW() - INTERVAL '1 day' LIMIT 1;")
    for r in cursor.fetchall(): print("  ", r[0])
        
    cursor.execute("ROLLBACK;")
    print("\n-> Rollback complete.")
