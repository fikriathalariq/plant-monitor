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

print("=== EXPLAIN WHY PLANNER CHOSE INDEX #5 ===")
with connection.cursor() as cursor:
    queries = [
        ("EXISTS check", "EXPLAIN SELECT 1 FROM monitoring_machineminutelog WHERE machine_id = 1 AND timestamp >= NOW() - INTERVAL '1 day' LIMIT 1;"),
        ("TIMESTAMP only", "EXPLAIN SELECT timestamp FROM monitoring_machineminutelog WHERE machine_id = 1 ORDER BY timestamp DESC LIMIT 1;"),
        ("ALL COLS (last_log)", "EXPLAIN SELECT * FROM monitoring_machineminutelog WHERE machine_id = 1 ORDER BY timestamp DESC LIMIT 1;"),
    ]
    
    for name, q in queries:
        print(f"\n--- {name} ---")
        cursor.execute(q)
        for r in cursor.fetchall():
            print("  ", r[0])

