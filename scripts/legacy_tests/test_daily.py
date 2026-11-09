import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "plant_monitor.settings")
django.setup()

from monitoring.api_dashboard import daily_processes_api

try:
    res = daily_processes_api(None)
    print("SUCCESS")
    print(res)
except Exception as e:
    import traceback
    traceback.print_exc()
