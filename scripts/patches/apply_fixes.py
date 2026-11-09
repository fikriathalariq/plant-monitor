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

from monitoring.models import DyeingIdentity, DyeingProcess
from monitoring.utils.batch_analyzer import BatchGradientProcessor, BatchProcessingConfig, analyze_batch_details
from monitoring.models import MachineMinuteLog

print("=" * 70)
print("  REKALKULASI & PENANDAAN BATCH KRITIS")
print("=" * 70)

# 1. Tandai Batch yang Gagal (Prematur / Salah Program) sbg tidak valid
invalid_ids = [2327, 1852, 191]
for rid in invalid_ids:
    try:
        ident = DyeingIdentity.objects.get(id=rid)
        if ident.dyeing_process:
            batch = ident.dyeing_process
            batch.is_valid_process = False
            batch.save(update_fields=['is_valid_process'])
            print(f"ID={rid} -> Batch #{batch.batch_number} ditandai is_valid_process=False")
        else:
            print(f"ID={rid} -> Saat ini Orphan, tidak ada batch yang ditandai.")
    except DyeingIdentity.DoesNotExist:
        pass

# 2. Rekalkulasi Batch #355 (JD_08) ID=1715
try:
    ident = DyeingIdentity.objects.get(id=1715)
    batch = ident.dyeing_process
    if batch:
        print(f"\nID=1715 -> Merekalkulasi Batch #{batch.batch_number} (Mesin: {batch.machine.code})...")
        
        # Ambil logs
        logs = MachineMinuteLog.objects.filter(
            machine=batch.machine,
            timestamp__range=(batch.start_time, batch.end_time)
        ).order_by('timestamp')
        
        # Proses ulang
        config = BatchProcessingConfig()
        processor = BatchGradientProcessor(config)
        from monitoring.utils.batch_analyzer import FilterState
        state = FilterState()
        
        batch_logs = []
        for i, log in enumerate(logs):
            dt_minutes = 1.0 if i == 0 else (log.timestamp - logs[i-1].timestamp).total_seconds() / 60.0
            f_temp, grad, therm, state = processor.process_single(log.temperature, state, dt_minutes)
            batch_logs.append({
                'timestamp': log.timestamp,
                'raw_temp': log.temperature,
                'filtered_temp': f_temp,
                'gradient': grad,
                'state': therm
            })
            
        peak_idx = max(range(len(batch_logs)), key=lambda i: batch_logs[i]['filtered_temp'])
        peak_temp = batch_logs[peak_idx]['filtered_temp']
        
        metrics = analyze_batch_details(batch_logs, peak_temp, config)
        
        # Update metrics ke database
        batch.max_temp = peak_temp
        batch.heating_start_time = metrics.get('heating_start_time')
        batch.steady_start_time = metrics.get('steady_start_time')
        batch.cooling_start_time = metrics.get('cooling_start_time')
        batch.reached_70c_time = metrics.get('reached_70c_time')
        
        batch.steady_duration = metrics.get('steady_duration', 0)
        batch.real_heating_duration = metrics.get('real_heating_duration', 0)
        
        # Simpan perubahan
        batch.save(update_fields=[
            'max_temp', 'heating_start_time', 'steady_start_time',
            'cooling_start_time', 'reached_70c_time', 'steady_duration',
            'real_heating_duration'
        ])
        
        print(f"BERHASIL! Update metrics Batch #{batch.batch_number}:")
        print(f"  Steady Duration yang baru: {batch.steady_duration} menit (sebelumnya 0 menit)")
        print(f"  Steady Start             : {batch.steady_start_time.strftime('%H:%M')} UTC")
    else:
        print(f"ID=1715 -> Saat ini Orphan, rekalkulasi dibatalkan.")
except DyeingIdentity.DoesNotExist:
    pass

print(f"\n============================================================")
print(f" SELESAI")
print(f"============================================================")
