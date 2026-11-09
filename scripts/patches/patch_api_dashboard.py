import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

﻿import re
import os

filepath = r"c:\Users\HP\Documents\Plant-Monitor\plant-monitor\monitoring\api_dashboard.py"
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update get_steam_traffic
old_traffic = '''    for m in machines:
        status = get_machine_status_logic(m)
        is_active = False
        if m.operation_mode == "MANUAL":
            is_active = (status == "Running")
        else:
            has_valid_gradient = m.temperature_gradient is not None and m.temperature_gradient > -0.1
            is_active = (status in ["HEAT", "STEADY", "Running"]) and has_valid_gradient
            
        if is_active:'''
new_traffic = '''    from monitoring.utils.steam_active import is_steam_active_from_machine
    for m in machines:
        status = get_machine_status_logic(m)
        is_active = is_steam_active_from_machine(m)
            
        if is_active:'''
content = content.replace(old_traffic, new_traffic)

# 2. Update get_active_machines (Card A)
old_active = '''        # Kartu A: Steam & HTO Aktif (HEAT / STEADY / Running)
        if status in ["HEAT", "STEADY", "Running"]:
            if has_steam:'''
new_active = '''        # Kartu A: Steam & HTO Aktif (HEAT / STEADY / Running)
        from monitoring.utils.steam_active import is_steam_active_from_machine
        if is_steam_active_from_machine(m):
            if has_steam:'''
content = content.replace(old_active, new_active)

# 3. Update get_active_machines (Cooling Off)
old_cooling = '''    for m in machines:
        status = get_machine_status_logic(m)
        steam = m.average_steam_usage or 0.0
        if status in ["COOL", "Stop", "OFF", "Offline"] and steam > 0:
            cooling_off_steam += steam'''
new_cooling = '''    for m in machines:
        status = get_machine_status_logic(m)
        steam = m.average_steam_usage or 0.0
        from monitoring.utils.steam_active import is_steam_active_from_machine
        # Mesin masuk kategori pendinginan uap jika tidak aktif uap tapi punya steam
        if not is_steam_active_from_machine(m) and steam > 0 and status != "RUNNING":
            cooling_off_steam += steam'''
content = content.replace(old_cooling, new_cooling)

# 4. Update get_machine_detail active_counts query
old_query = '''    ).filter(
        Q(thermal_state__in=["HEAT", "STEADY"]) | Q(last_status="Running")
    ).values('timestamp')'''
new_query = '''    ).filter(
        Q(thermal_state="HEAT") | Q(thermal_state="STEADY", temperature__gte=90.0) | Q(last_status="Running")
    ).values('timestamp')'''
content = content.replace(old_query, new_query)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)
print("Done patching api_dashboard.py")
