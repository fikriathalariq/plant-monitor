import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import os
import django
import json

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
django.setup()

from django.test import RequestFactory
from monitoring.views import apidog_dyeing_process_lookup_api

factory = RequestFactory()
request = factory.get('/api/external/dyeing-process-lookup/', {
    'machine_code': 'JD_12',
    'time': '2025-11-18T23:00:00Z'
})

response = apidog_dyeing_process_lookup_api(request)

print(f"Status Code: {response.status_code}")
if response.status_code == 200:
    envelope = json.loads(response.content)
    data = envelope.get('data', {})
    print("Batch Info:")
    for k, v in data.get('batch_info', {}).items():
        print(f"  {k}: {v}")
    
    ts = data.get('time_series', [])
    print(f"\nTime Series Length: {len(ts)}")
    if ts:
        print("First 3 Data Points:")
        for point in ts[:3]:
            print(f"  {point}")
else:
    print(f"Error Response: {response.content.decode()}")

