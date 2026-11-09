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

# Cek semua tabel beserta ukurannya
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT 
            schemaname,
            tablename,
            pg_total_relation_size(quote_ident(schemaname)||'.'||quote_ident(tablename)) as size_bytes,
            pg_size_pretty(pg_total_relation_size(quote_ident(schemaname)||'.'||quote_ident(tablename))) as size_pretty,
            pg_size_pretty(pg_relation_size(quote_ident(schemaname)||'.'||quote_ident(tablename))) as table_size_pretty,
            pg_size_pretty(pg_total_relation_size(quote_ident(schemaname)||'.'||quote_ident(tablename)) - pg_relation_size(quote_ident(schemaname)||'.'||quote_ident(tablename))) as index_size_pretty,
            (SELECT count(*) FROM information_schema.columns WHERE table_name = tablename) as column_count
        FROM pg_tables
        WHERE schemaname = 'public'
        ORDER BY size_bytes DESC
        LIMIT 20;
    """)
    rows = cursor.fetchall()
    print(f"{'Table':<45} {'Total':>10} {'Data':>10} {'Indexes':>10} {'Cols':>6}")
    print("-" * 90)
    for row in rows:
        print(f"{row[1]:<45} {row[3]:>10} {row[4]:>10} {row[5]:>10} {row[6]:>6}")
