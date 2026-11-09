import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import re

file_path = r'monitoring/templates/monitoring/machine_monthly_full_report.html'
with open(file_path, 'r', encoding='utf-8') as f:
    text = f.read()

# Let's inspect sections 3, 4, 5 and footer positions
sec3_pos = text.find('3. MATRIKS KEPATUHAN')
sec4_pos = text.find('4. DIAGNOSTIK VISUAL')
sec5_pos = text.find('5. REKOMENDASI FINANSIAL')
footer_pos = text.find('<footer class=')

print(f"Sec 3: {sec3_pos}, Sec 4: {sec4_pos}, Sec 5: {sec5_pos}, Footer: {footer_pos}")
