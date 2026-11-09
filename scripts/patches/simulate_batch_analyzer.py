import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import os, django
from datetime import datetime, timezone
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
django.setup()

from monitoring.models import DyeingProcess, MachineMinuteLog
from monitoring.utils.batch_analyzer import BatchGradientProcessor, BatchProcessingConfig, FilterState, analyze_batch_details

# Ambil data batch JD_08 #355
batch = DyeingProcess.objects.get(machine__code='JD_08', batch_number=355)
logs = MachineMinuteLog.objects.filter(
    machine=batch.machine,
    timestamp__range=(batch.start_time, batch.end_time)
).order_by('timestamp')

# 1. Jalankan ulang filter (rekonstruksi batch_logs)
config = BatchProcessingConfig()
processor = BatchGradientProcessor(config)
state = FilterState()

batch_logs = []
for i, log in enumerate(logs):
    # Hitung dt_minutes
    if i == 0:
        dt_minutes = 1.0
    else:
        dt_minutes = (log.timestamp - logs[i-1].timestamp).total_seconds() / 60.0
        
    f_temp, grad, therm, state = processor.process_single(log.temperature, state, dt_minutes)
    
    batch_logs.append({
        'timestamp': log.timestamp,
        'raw_temp': log.temperature,
        'filtered_temp': f_temp,
        'gradient': grad,
        'state': therm
    })

# Cetak kondisi puncak saat ini
peak_idx_raw = max(range(len(batch_logs)), key=lambda i: batch_logs[i]['raw_temp'])
print(f"============================================================")
print(f" KONDISI SAAT INI (Menggunakan raw_temp)")
print(f"============================================================")
res_raw = analyze_batch_details(batch_logs, batch_logs[peak_idx_raw]['raw_temp'], config)

print(f"Peak Mentah       : {batch_logs[peak_idx_raw]['raw_temp']:.2f}°C (di {batch_logs[peak_idx_raw]['timestamp']})")
print(f"Heating Start     : {res_raw.get('heating_start_time')}")
print(f"Steady Start      : {res_raw.get('steady_start_time')}")
print(f"Cooling Start     : {res_raw.get('cooling_start_time')}")
print(f"Steady Duration   : {res_raw.get('steady_duration')} m")

# 2. Modifikasi Fungsi (Simulasi dengan filtered_temp untuk Peak)
def analyze_batch_details_simulated(batch_logs, peak_temp, config):
    # SALIN KODE ASLI, UBAH HANYA BAGIAN PEAK
    metrics = {
        'heating_span': 0.0, 'steady_duration': 0, 'cooling_70_duration': 0.0,
        'cooling_start_time': None, 'heating_start_time': None, 'reached_70c_time': None,
        'steady_start_time': None, 'real_heating_duration': 0, 'avg_heating_efficiency': 0.0,
        'ideal_heating_time': 0.0, 'heating_lag': 0.0, 'avg_steam_temp': 0.0, 'avg_steam_pressure': 0.0
    }
    
    # PERUBAHAN: Gunakan filtered_temp untuk mencari index puncak, dan jadikan nilai puncaknya dari filtered_temp
    peak_idx = max(range(len(batch_logs)), key=lambda i: batch_logs[i]['filtered_temp'])
    peak_time = batch_logs[peak_idx]['timestamp']
    peak_val_filtered = batch_logs[peak_idx]['filtered_temp']
    logs_before_peak = batch_logs[:peak_idx+1]
    
    # 2. HEATING START (Sama)
    candidate_log = None
    real_start_locked = False
    from datetime import timedelta
    for log in logs_before_peak:
        grad, temp = log['gradient'], log['filtered_temp']
        if real_start_locked: break
        if candidate_log is None:
            if grad >= config.ANALYSIS_HEAT_THRESH: candidate_log = log
        else:
            if (temp - candidate_log['filtered_temp']) >= config.LOCK_RISE_DELTA:
                metrics['heating_start_time'] = candidate_log['timestamp'] - timedelta(minutes=1)
                real_start_locked = True
                break
            if grad <= config.RESET_GRAD_THRESH: candidate_log = None
    if not metrics['heating_start_time'] and candidate_log: metrics['heating_start_time'] = candidate_log['timestamp'] - timedelta(minutes=1)
    if not metrics['heating_start_time']: metrics['heating_start_time'] = batch_logs[0]['timestamp']

    # 3. COOLING START
    start_search_idx = peak_idx
    cooling_start_found = None
    w_cool = config.STEADY_SCAN_WINDOW
    for k in range(start_search_idx, len(batch_logs)):
        if k >= start_search_idx + w_cool - 1:
            window_start_idx = k - (w_cool - 1)
            window_logs = batch_logs[window_start_idx:k+1]
            total_dt = 0; total_dtemp = 0
            for idx in range(1, len(window_logs)):
                dt = (window_logs[idx]['timestamp'] - window_logs[idx-1]['timestamp']).total_seconds() / 60.0
                if dt > 0:
                    total_dt += dt
                    total_dtemp += (window_logs[idx]['raw_temp'] - window_logs[idx-1]['raw_temp'])
            if total_dt > 0:
                avg_grad = total_dtemp / total_dt
                if avg_grad <= -1.0:
                    cooling_start_found = window_logs[0]['timestamp']
                    break
    if not cooling_start_found: cooling_start_found = peak_time
    metrics['cooling_start_time'] = cooling_start_found

    # 4. STEADY START
    # PERUBAHAN: Thresh berdasarkan peak_val_filtered, bukan raw
    steady_thresh = peak_val_filtered - 5.0
    
    steady_window = [l for l in batch_logs if metrics['heating_start_time'] <= l['timestamp'] <= metrics['cooling_start_time']]
    found_steady = False
    
    w = config.STEADY_SCAN_WINDOW
    for k in range(len(steady_window)):
        log = steady_window[k]
        if log['filtered_temp'] < steady_thresh: # PERUBAHAN: Pengecekan threshold pakai filtered_temp
            continue
        if k >= w - 1:
            window_start_idx = k - (w - 1)
            window_logs = steady_window[window_start_idx:k+1]
            total_dt = 0; total_dtemp = 0
            for idx in range(1, len(window_logs)):
                dt = (window_logs[idx]['timestamp'] - window_logs[idx-1]['timestamp']).total_seconds() / 60.0
                if dt > 0:
                    total_dt += dt
                    total_dtemp += (window_logs[idx]['filtered_temp'] - window_logs[idx-1]['filtered_temp']) # Pakai filtered_temp
            if total_dt > 0:
                avg_grad = total_dtemp / total_dt
                if abs(avg_grad) <= config.STEADY_GRAD_THRESH:
                    metrics['steady_start_time'] = steady_window[window_start_idx]['timestamp']
                    found_steady = True
                    break
    
    if not found_steady:
        # PERUBAHAN: Pengecekan fallback pakai filtered_temp
        fallback_candidates = [l for l in steady_window if l['filtered_temp'] >= steady_thresh and l['state'] != 'HEAT']
        if fallback_candidates:
            metrics['steady_start_time'] = fallback_candidates[0]['timestamp']
        else:
            metrics['steady_start_time'] = metrics['cooling_start_time']
    
    if metrics['steady_start_time']:
        if metrics['steady_start_time'] >= metrics['cooling_start_time']: metrics['steady_duration'] = 0
        else:
            diff = (metrics['cooling_start_time'] - metrics['steady_start_time']).total_seconds() / 60.0
            metrics['steady_duration'] = max(0, int(diff))

    return metrics, peak_val_filtered

print(f"\n============================================================")
print(f" SIMULASI (Menggunakan filtered_temp untuk peak & steady)")
print(f"============================================================")
res_sim, peak_sim = analyze_batch_details_simulated(batch_logs, 0, config)

peak_idx_sim = max(range(len(batch_logs)), key=lambda i: batch_logs[i]['filtered_temp'])

print(f"Peak Filtered     : {peak_sim:.2f}°C (di {batch_logs[peak_idx_sim]['timestamp']})")
print(f"Heating Start     : {res_sim.get('heating_start_time')}")
print(f"Steady Start      : {res_sim.get('steady_start_time')}")
print(f"Cooling Start     : {res_sim.get('cooling_start_time')}")
print(f"Steady Duration   : {res_sim.get('steady_duration')} m")

print(f"\nKesimpulan:")
print(f"Suhu Ambang Steady (Mentah)   : {(batch_logs[peak_idx_raw]['raw_temp'] - 5):.2f}°C")
print(f"Suhu Ambang Steady (Simulasi) : {(peak_sim - 5):.2f}°C")
