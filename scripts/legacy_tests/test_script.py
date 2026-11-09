import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import os, django, re
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
from plant_monitor import settings
settings.ALLOWED_HOSTS = ['*']
django.setup()

from django.test import Client
from django.contrib.auth.models import User

user = User.objects.get(username='admin')
client = Client()
client.force_login(user)

response = client.get('/admin/monitoring/dyeingprocess/')
if response.status_code != 200:
    print('Failed to get page:', response.status_code)
    exit(1)

html = response.content.decode('utf-8')
total = re.search(r'name="form-TOTAL_FORMS"\s+value="(\d+)"', html).group(1)
initial = re.search(r'name="form-INITIAL_FORMS"\s+value="(\d+)"', html).group(1)

post_data = {
    'form-TOTAL_FORMS': total,
    'form-INITIAL_FORMS': initial,
    'form-MIN_NUM_FORMS': '0',
    'form-MAX_NUM_FORMS': '1000',
    '_save': 'Save',
}

ids = re.findall(r'name="form-(\d+)-id"\s+value="([0-9]+)"', html)
for i, str_id in ids:
    post_data[f'form-{i}-id'] = str_id
    if i == '0':
        continue # leave unchecked
    post_data[f'form-{i}-is_valid_process'] = 'on'

print('Parsed total forms:', total)
res_post = client.post('/admin/monitoring/dyeingprocess/', post_data, follow=True)
res_html = res_post.content.decode('utf-8')

import sys
if 'errornote' in res_html or 'errorlist' in res_html:
    print('ERROR DETECTED!')
    err_block = re.search(r'<p class="errornote">(.*?)</p>', res_html, re.DOTALL)
    if err_block: print('Global Error:', err_block.group(1).strip())
    
    nonform = re.search(r'<ul class="errorlist nonform">(.*?)</ul>', res_html, re.DOTALL)
    if nonform: print('NonForm Error:', nonform.group(1).strip())
    
    # Try finding specific row errors
    for idx in range(int(total)):
        field_err = re.search(fr'<input[^>]*name="form-{idx}-is_valid_process"[^>]*>.*?<ul class="errorlist">(.*?)</ul>', res_html, re.DOTALL)
        if field_err:
            print(f'Row {idx} Form Error:', field_err.group(1).strip())
else:
    print('SUCCESS! No errors.')
