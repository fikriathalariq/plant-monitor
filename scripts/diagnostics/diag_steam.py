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

from monitoring.models import Machine
from monitoring.utils.steam_active import is_steam_active_from_machine

machines = list(Machine.objects.filter(is_active=True).select_related('group'))

# Metode port 8000 (views.py dashboard)
port8000_total = 0.0
port8000_active = []
for m in machines:
    is_active = is_steam_active_from_machine(m)
    if is_active:
        steam = m.average_steam_usage or 0.0
        port8000_total += steam
        port8000_active.append(f'  {m.name or m.code} [{m.last_thermal_status}] gradient={m.temperature_gradient} temp={m.temperature} steam={steam}')

# Metode port 8002 (api_dashboard.py get_steam_traffic) 
port8002_total = 0.0
port8002_active = []
machines2 = list(Machine.objects.filter(is_active=True))
for m in machines2:
    is_active = is_steam_active_from_machine(m)
    if is_active:
        steam = m.average_steam_usage or 0.0
        port8002_total += steam
        port8002_active.append(f'  {m.name or m.code} [{m.last_thermal_status}] gradient={m.temperature_gradient} temp={m.temperature} steam={steam}')

print('=== PORT 8000 (dashboard view) ===')
print(f'Total: {port8000_total}')
for x in port8000_active:
    print(x)

print()
print('=== PORT 8002 (api_dashboard.py steam-traffic) ===')
print(f'Total: {port8002_total}')
for x in port8002_active:
    print(x)

print()
if abs(port8000_total - port8002_total) < 0.01:
    print('>> SAMA - kode sudah identik')
else:
    print(f'>> BERBEDA: selisih = {abs(port8000_total - port8002_total)}')
    # Cari mesin yang ada di satu tapi tidak di lain
    names8000 = set(x.split('[')[0].strip() for x in port8000_active)
    names8002 = set(x.split('[')[0].strip() for x in port8002_active)
    only8000 = names8000 - names8002
    only8002 = names8002 - names8000
    if only8000: print(f'  Hanya di 8000: {only8000}')
    if only8002: print(f'  Hanya di 8002: {only8002}')
