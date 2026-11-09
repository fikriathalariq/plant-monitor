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

replacement = '    def __str__(self):'
text = re.sub(r'    sensor_shadow_max_minutes = models\.IntegerField.*?def __str__\(self\):', replacement, text, count=1, flags=re.DOTALL)

with open('monitoring/models.py', 'w', encoding='utf-8') as f:
    f.write(text)
