import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
django.setup()

from django.db import connection

try:
    with connection.cursor() as cursor:
        cols = ['error_count', 'file_size', 'processed_at', 'processing_time_seconds', 'rows_processed', 'machines_updated', 'original_filename']
        for c in cols:
            print(f'Dropping {c}...')
            cursor.execute(f'ALTER TABLE monitoring_rawdatafile DROP COLUMN IF EXISTS {c} CASCADE;')
        
        # Also drop others from 0036 if needed:
        # CompanyProfile:
        for c in ['address', 'email', 'phone', 'website']:
            cursor.execute(f'ALTER TABLE monitoring_companyprofile DROP COLUMN IF EXISTS {c} CASCADE;')
            
        # DyeingProcess
        cursor.execute(f'ALTER TABLE monitoring_dyeingprocess DROP COLUMN IF EXISTS heading_gradient_duration CASCADE;')
        
        # IPAccessControl
        cursor.execute(f'ALTER TABLE monitoring_ipaccesscontrol DROP COLUMN IF EXISTS auto_block_count CASCADE;')
        cursor.execute(f'ALTER TABLE monitoring_ipaccesscontrol DROP COLUMN IF EXISTS last_block_reason CASCADE;')
        
        # Machine
        cursor.execute(f'ALTER TABLE monitoring_machine DROP COLUMN IF EXISTS manual_target_temp CASCADE;')
        
    print('SUCCESS')
except Exception as e:
    print('ERROR:', e)
