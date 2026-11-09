import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
django.setup()
from monitoring.models import MachineMinuteLog, Machine
from django.utils import timezone
from datetime import timedelta

now = timezone.now()
cutoff = now - timedelta(minutes=1)

shadowed = MachineMinuteLog.objects.filter(timestamp__gte=cutoff, data_quality='SHADOWED').values_list('machine__code', flat=True)
print('SHADOWED machines:', list(shadowed)[:20])
print()
normal = MachineMinuteLog.objects.filter(timestamp__gte=cutoff, data_quality='NORMAL').values_list('machine__code', flat=True)
print('NORMAL machines:', list(normal)[:20])
print()

# Cek temperature sekarang untuk beberapa mesin SHADOWED
shadowed_codes = list(shadowed[:5])
for m in Machine.objects.filter(code__in=shadowed_codes):
    print(f'  {m.code}: temp={m.temperature}, valid_min={m.valid_min}, valid_max={m.valid_max}')
