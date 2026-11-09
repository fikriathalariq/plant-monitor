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

replacement = '''    operation_mode = models.CharField(
        max_length=10,
        choices=MODE_CHOICES,
        default="AUTO"
    )

    valid_min = models.FloatField(
        default=-50.0,
        verbose_name="Batas Bawah Sensor Valid",
        help_text="Nilai di bawah ini dianggap Noise/Sensor Putus. JD=10.0, CDR Speed=-20.0, Steam_Pr=0.0"
    )
    
    valid_max = models.FloatField(
        default=1000.0,
        verbose_name="Batas Atas Sensor Valid",
        help_text="Nilai di atas ini dianggap Short Circuit / Sensor Rusak."
    )'''

text = re.sub(r'    operation_mode = models\.CharField\(\s*max_length=10,\s*choices=MODE_CHOICES,\s*default="AUTO"\s*\)', replacement, text, flags=re.DOTALL)

with open('monitoring/models.py', 'w', encoding='utf-8') as f:
    f.write(text)
