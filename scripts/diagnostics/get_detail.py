import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import re

with open(r'C:\Users\HP\Documents\Plant-Monitor\plant-monitor\monitoring\api_dashboard.py', 'r', encoding='utf-8') as f:
    text = f.read()

match = re.search(r'def get_machine_detail.*?return \{.*?\n\s*\}', text, re.DOTALL)
if match:
    print(match.group(0))
else:
    match = re.search(r'def get_machine_detail.*', text, re.DOTALL)
    print(match.group(0)[:1500])
