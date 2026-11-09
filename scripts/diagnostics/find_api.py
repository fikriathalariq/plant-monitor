import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import re

with open(r'C:\Users\HP\Documents\Plant-Monitor\plant-monitor\frontend\src\pages\Dashboard.jsx', 'r', encoding='utf-8') as f:
    text = f.read()

# Find the function that fetches machine details
match = re.search(r'const\s+(?:fetch|load)[\w]*Machine[\w]*\s*=\s*(?:async)?\s*\([^)]*\)\s*=>\s*\{[^}]*\}', text)
if match:
    print(match.group(0))
else:
    # Just find any assignment to machineDetail
    matches = re.finditer(r'api\.get\([^)]*\)', text)
    for m in matches:
        print(m.group(0))
