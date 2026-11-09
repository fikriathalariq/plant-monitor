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

# Simulate actual API calls to catch runtime errors
from django.test import RequestFactory
from django.contrib.auth import get_user_model

User = get_user_model()
user = User.objects.filter(is_superuser=True).first()

if not user:
    print('No superuser found, skipping auth tests')
else:
    print(f'Testing as: {user.username}')

# Test views.py steam_usage_history_api runtime
try:
    rf = RequestFactory()
    req = rf.get('/api/steam-usage-history/', {'hours': '24'})
    req.user = user
    from monitoring.views import steam_usage_history_api
    response = steam_usage_history_api(req)
    print(f'steam_usage_history_api (24h): OK - status {response.status_code}')
except Exception as e:
    import traceback
    print(f'steam_usage_history_api ERROR:')
    traceback.print_exc()

# Test api_dashboard get_steam_traffic
try:
    from monitoring.api_dashboard import get_steam_traffic
    rf = RequestFactory()
    req = rf.get('/api/v1/dashboard/steam-traffic/')
    req.user = user
    result = get_steam_traffic(req)
    print(f'get_steam_traffic: OK - current_usage={result[\"current_usage\"]}')
except Exception as e:
    import traceback
    print('get_steam_traffic ERROR:')
    traceback.print_exc()
