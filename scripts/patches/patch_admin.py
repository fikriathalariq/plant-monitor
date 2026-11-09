import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import re
with open('monitoring/admin.py', 'r', encoding='utf-8') as f:
    text = f.read()

replacement = '''class GlobalSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "__str__", "water_specific_heat", "water_density", "fabric_specific_heat",
        "standard_ambient_temp", "fuel_factor_steam_boiler", "fuel_factor_hto_boiler",
        "coal_calorific_value", "sensor_shadow_max_minutes", "sensor_rehydrate_buffer_minutes", "updated_at",
    )
    fieldsets = (
        ("Data Quality Shield", {
            "fields": ("sensor_shadow_max_minutes", "sensor_rehydrate_buffer_minutes"),
            "description": "Konfigurasi sistem anti-drop dan shadow data untuk sensor.",
        }),
        ("Parameter Air", {'''

text = re.sub(r'class GlobalSettingsAdmin\(admin\.ModelAdmin\):\s*list_display = \(\s*"__str__", "water_specific_heat", "water_density", "fabric_specific_heat",\s*"standard_ambient_temp", "fuel_factor_steam_boiler", "fuel_factor_hto_boiler",\s*"coal_calorific_value", "updated_at",\s*\)\s*fieldsets = \(\s*\("Parameter Air", \{', replacement, text, count=1, flags=re.DOTALL)

with open('monitoring/admin.py', 'w', encoding='utf-8') as f:
    f.write(text)
