import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

﻿import psycopg
conn = psycopg.connect('dbname=plantmonitor user=postgres password=suritex01 host=127.0.0.1')
cur = conn.cursor()
cur.execute('''
    SELECT pid, state, wait_event_type, wait_event, query 
    FROM pg_stat_activity 
    WHERE state != 'idle' AND pid != pg_backend_pid();
''')
for row in cur.fetchall():
    print(row)
conn.close()
