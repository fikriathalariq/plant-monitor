import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "plant_monitor.settings")
django.setup()
from monitoring.models import MachineMinuteLog
from django.utils import timezone
from datetime import timedelta

now = timezone.now()
cutoff = now - timedelta(minutes=2)
# Ambil 5 menit terakhir untuk lihat pola NORMAL vs SHADOWED
from django.db.models import Count
result = MachineMinuteLog.objects.filter(timestamp__gte=cutoff).values('timestamp', 'data_quality').annotate(cnt=Count('id')).order_by('-timestamp')[:10]
for r in result:
    print(r['timestamp'].strftime('%H:%M'), r['data_quality'], ':', r['cnt'], 'mesin')
