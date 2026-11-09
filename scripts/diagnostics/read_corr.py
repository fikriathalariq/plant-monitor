import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

with open(r'frontend\src\pages\MachineDailyReport.jsx', encoding='utf-8') as f:
    lines = f.readlines()
for j in range(2820, min(len(lines), 2950)):
    text = lines[j].encode('ascii', 'backslashreplace').decode('ascii')
    print(f'{j+1}: {text}', end='')
