import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import os, re, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
django.setup()

# Migration 0075 - index apa yang ditambahkan?
with open('monitoring/migrations/0075_globalsettings_sensor_rehydrate_buffer_minutes_and_more.py', 'r', encoding='utf-8') as f:
    content = f.read()
    
idx_section = re.findall(r'AddIndex|RemoveIndex|Index\(.*?\)', content, re.DOTALL)
print("Migration 0075 index changes:")
for i in idx_section[:20]:
    print(f"  {i[:200]}")

print()
# Migration 0014 - apa yang dibuat?
with open('monitoring/migrations/0014_alter_machineminutelog_options_and_more.py', 'r', encoding='utf-8') as f:
    content = f.read()

idx_section = re.findall(r'Index\(.*?\)', content, re.DOTALL)
print("Migration 0014 index definitions:")
for i in idx_section[:10]:
    print(f"  {i[:300]}")
