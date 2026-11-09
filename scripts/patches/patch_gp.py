import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import re
with open('monitoring/utils/gradient_processor.py', 'r', encoding='utf-8') as f:
    text = f.read()

replacement1 = '''    last_classified_thermal: str = "OFF"
    
    # Shadow / Data Quality Tracking (field formal)
    consecutive_shadow_minutes: int = 0'''

text = re.sub(r'    last_classified_thermal: str = "OFF"', replacement1, text, count=1, flags=re.DOTALL)

replacement2 = '''class ProcessingConfig:
    """Konfigurasi parameter processing."""
    # Physical bounds (relax to extremely wide ranges, real limits are in Machine model)
    T_MIN: float = -9999.0
    T_MAX: float = 9999.0'''

text = re.sub(r'class ProcessingConfig:\s*"""Konfigurasi parameter processing\."""\s*# Physical bounds\s*T_MIN: float = -20\.0.*?T_MAX: float = 150\.0.*?\n', replacement2 + '\n', text, count=1, flags=re.DOTALL)

with open('monitoring/utils/gradient_processor.py', 'w', encoding='utf-8') as f:
    f.write(text)
