import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import subprocess
import os

chrome = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
artifact_dir = r'C:\Users\HP\.gemini\antigravity\brain\b04a2a90-03d6-4297-ba59-6cf1c0ec979f'
out_png = os.path.join(artifact_dir, 'dashboard_1_preview.png')

cmd = [
    chrome,
    '--headless=new',
    '--disable-gpu',
    '--hide-scrollbars',
    '--window-size=1680,1200',
    f'--screenshot={out_png}',
    'http://127.0.0.1:8000/dashboard-1'
]

print('Capturing screenshot of dashboard-1...')
res = subprocess.run(cmd, timeout=30)
print('Exit code:', res.returncode)
print('Screenshot exists:', os.path.exists(out_png))
if os.path.exists(out_png):
    print('Size:', os.path.getsize(out_png))
