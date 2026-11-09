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

replacement = '''    sensor_shadow_max_minutes = models.IntegerField(
        default=15,
        verbose_name="Maks. Durasi Shadow Berturut-turut (menit)",
        help_text="Berapa menit berturut-turut sensor boleh di-shadow sebelum sistem memaksa OFFLINE. Default: 15. Nilai ini juga menentukan depth query rehydration saat restart."
    )
    
    sensor_rehydrate_buffer_minutes = models.IntegerField(
        default=5,
        verbose_name="Toleransi Jeda Restart (menit)",
        help_text="Jika jeda antara log terakhir dan waktu restart > nilai ini, shadow counter dianggap tidak relevan (fresh start). Default: 5 menit. Set lebih tinggi jika daemon sering lambat startup."
    )

    created_at = models.DateTimeField(auto_now_add=True)'''

text = re.sub(r'    created_at = models\.DateTimeField\(auto_now_add=True\)', replacement, text, count=1, flags=re.DOTALL)

with open('monitoring/models.py', 'w', encoding='utf-8') as f:
    f.write(text)
