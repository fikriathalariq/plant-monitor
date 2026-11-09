import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

﻿import django, os, sys
sys.path.insert(0, r'c:\Users\HP\Documents\Plant-Monitor\plant-monitor')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
django.setup()

# Test import semua modul yang kita ubah
try:
    from monitoring.utils.steam_active import is_steam_active_from_machine, is_steam_active_from_snapshot
    print('steam_active.py: OK')
except Exception as e:
    print(f'steam_active.py ERROR: {e}')

try:
    from monitoring import views
    print('views.py: OK')
except Exception as e:
    print(f'views.py ERROR: {e}')

try:
    from monitoring import api_report
    print('api_report.py: OK')
except Exception as e:
    print(f'api_report.py ERROR: {e}')

try:
    from monitoring import api_dashboard
    print('api_dashboard.py: OK')
except Exception as e:
    print(f'api_dashboard.py ERROR: {e}')
