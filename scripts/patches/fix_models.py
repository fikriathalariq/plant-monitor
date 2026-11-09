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

bad_block = '''unique_together = [['machine', 'timestamp']]
        indexes = [
            models.Index(fields=['machine', 'timestamp']),
            models.Index(fields=['thermal_state']),
        ]'''

text = text.replace(bad_block, '')

with open('monitoring/models.py', 'w', encoding='utf-8') as f:
    f.write(text)
