import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import re
with open('monitoring/models.py', 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Remove from FavoriteMachine
bad_fields = '''    sensor_shadow_max_minutes = models.IntegerField(
        default=15,
        verbose_name="Maks. Durasi Shadow Berturut-turut (menit)",
        help_text="Berapa menit berturut-turut sensor boleh di-shadow sebelum sistem memaksa OFFLINE. Default: 15. Nilai ini juga menentukan depth query rehydration saat restart."
    )
    
    sensor_rehydrate_buffer_minutes = models.IntegerField(
        default=5,
        verbose_name="Toleransi Jeda Restart (menit)",
        help_text="Jika jeda antara log terakhir dan waktu restart > nilai ini, shadow counter dianggap tidak relevan (fresh start). Default: 5 menit. Set lebih tinggi jika daemon sering lambat startup."
    )

'''
text = text.replace(bad_fields, '')

# 2. Add to GlobalSettings (use coal_calorific_value as anchor because it's unique)
good_fields = '''    coal_calorific_value = models.FloatField(
        default=5500.0,
        verbose_name="Nilai Kalor Batu Bara (kcal/kg)",
        help_text="Dipakai untuk hitung efisiensi termal (energi output / energi input)."
    )
    
    sensor_shadow_max_minutes = models.IntegerField(
        default=15,
        verbose_name="Maks. Durasi Shadow Berturut-turut (menit)",
        help_text="Berapa menit berturut-turut sensor boleh di-shadow sebelum sistem memaksa OFFLINE. Default: 15. Nilai ini juga menentukan depth query rehydration saat restart."
    )
    
    sensor_rehydrate_buffer_minutes = models.IntegerField(
        default=5,
        verbose_name="Toleransi Jeda Restart (menit)",
        help_text="Jika jeda antara log terakhir dan waktu restart > nilai ini, shadow counter dianggap tidak relevan (fresh start). Default: 5 menit. Set lebih tinggi jika daemon sering lambat startup."
    )'''
text = re.sub(r'    coal_calorific_value = models\.FloatField\(.*?help_text="Dipakai untuk hitung efisiensi termal \(energi output / energi input\)\."\s*\)', good_fields, text, flags=re.DOTALL)

with open('monitoring/models.py', 'w', encoding='utf-8') as f:
    f.write(text)
