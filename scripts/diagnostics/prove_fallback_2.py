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

print("=== PROVING FALLBACK TO INDEX #2 (UNIQUE) ===")
with connection.cursor() as cursor:
    cursor.execute("BEGIN;")
    cursor.execute("DROP INDEX idx_log_machine_ts_dq;")
    cursor.execute("DROP INDEX idx_log_machine_ts_desc;")
    
    print("\nEXPLAIN after dropping #5 and #4:")
    cursor.execute("EXPLAIN SELECT 1 FROM monitoring_machineminutelog WHERE machine_id = 1 AND timestamp >= NOW() - INTERVAL '1 day' LIMIT 1;")
    for r in cursor.fetchall(): print("  ", r[0])
        
    cursor.execute("ROLLBACK;")
