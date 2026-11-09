import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import os
import django
import sys
import re
import statistics
from datetime import date, timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
django.setup()

from monitoring.models import ProductionPlanBatch, ProductionPlanBlock, DyeingProcess, Machine

TARGET_STEAM = 6000
START_DATE = date(2026, 8, 11)

machines = Machine.objects.all()
steam_usage = {m.code: m.average_steam_usage or 0 for m in machines}
operation_mode = {m.code: m.operation_mode for m in machines}

baseline_data = {
    'JD_01': (187.8, 57.5, 72.8), 'JD_03': (125.7, 33.6, 63.3), 'JD_04': (116.0, 38.7, 57.0),
    'JD_08': (150.5, 52.8, 76.4), 'JD_09': (120.9, 45.2, 47.0), 'JD_10': (119.1, 49.8, 69.4),
    'JD_11': (133.7, 58.0, 38.0), 'JD_12': (105.0, 46.6, 46.1), 'JD_13': (115.1, 44.8, 46.5),
    'JD_14': (114.9, 52.1, 40.1), 'JD_15': (154.5, 52.3, 53.0), 'JD_16': (126.7, 55.1, 52.8),
    'JD_18': (141.8, 45.7, 56.0), 'JD_19': (185.2, 53.9, 39.1), 'JD_JetMini': (142.9, 45.5, 74.8),
    'JR_02': (165.1, 41.4, 56.8), 'JR_03': (146.1, 43.3, 48.7), 'JR_04': (164.3, 55.4, 62.6),
    'JR_05': (141.5, 55.0, 52.6), 'JR_06': (101.0, 55.7, 94.7), 'JR_07': (138.6, 45.1, 42.9),
    'JR_08': (124.3, 48.8, 51.2), 'JR_09': (129.7, 46.6, 57.4), 'JR_11': (175.6, 60.8, 79.1),
    'JR_12': (119.8, 62.0, 33.5), 'JR_13': (108.1, 53.4, 32.6), 'ZET_06': (140.5, 35.7, 32.5),
    'ZET_07': (141.3, 44.7, 26.5), 'ZET_08': (153.4, 55.8, 19.0), 'ZET_10': (144.9, 24.2, 35.2),
    'ZET_11': (135.6, 35.1, 43.0),
}

batches = ProductionPlanBatch.objects.filter(
    plan__shift_date__gte='2026-08-11',
    plan__shift_date__lte='2026-08-21'
).select_related('plan', 'machine').prefetch_related('blocks')

records = []
unmatched_labels = 0
missing_procs = 0

for b in batches:
    day_idx = (b.plan.shift_date - START_DATE).days
    start_abs = day_idx * 1440 + b.start_offset_minutes
    blocks = list(b.blocks.all().order_by('sequence'))
    orig_total_dur = sum(block.duration_minutes for block in blocks)
    
    max_temp = 0
    m = re.search(r'Batch #(\d+)', b.label)
    if m:
        proc = DyeingProcess.objects.filter(machine=b.machine, batch_number=m.group(1)).first()
        if proc and proc.max_temp:
            max_temp = proc.max_temp
        elif not proc:
            missing_procs += 1
    else:
        unmatched_labels += 1

    records.append({
        'batch': b,
        'machine_code': b.machine.code,
        'original_start_abs': start_abs,
        'original_end_abs': start_abs + orig_total_dur,
        'orig_total_dur': orig_total_dur,
        'max_temp': max_temp,
        'blocks': blocks,
        'mode': operation_mode.get(b.machine.code, 'AUTO')
    })

records.sort(key=lambda x: x['original_start_abs'])

TOTAL_MINUTES = 30 * 1440
global_steam = [0.0] * TOTAL_MINUTES
original_steam = [0.0] * TOTAL_MINUTES

machine_state = {}
changes_log = []
escape_valve_triggers = 0
actual_max_steam = 0.0

# Counters for why batches were NOT optimized
skip_temp_low = 0
skip_manual = 0
skip_no_baseline = 0
optimized_count = 0

for r in records:
    mc = r['machine_code']
    usage = steam_usage.get(mc, 0)
    mode = r['mode']
    
    orig_steam_dur = sum(blk.duration_minutes for blk in r['blocks'] if blk.phase in ['HEAT', 'STEADY', 'RUNNING'])
    for i in range(r['original_start_abs'], min(r['original_start_abs'] + orig_steam_dur, TOTAL_MINUTES)):
        original_steam[i] += usage
        
    baseline_dur = 0
    if mode == 'AUTO':
        if r['max_temp'] > 110:
            if mc in baseline_data:
                heat, hold, cool = baseline_data[mc]
                baseline_dur = heat + hold + cool
                new_blocks = [
                    {'phase': 'HEAT', 'duration': int(round(heat))},
                    {'phase': 'STEADY', 'duration': int(round(hold))},
                    {'phase': 'COOL', 'duration': int(round(cool))}
                ]
                is_opt = True
                optimized_count += 1
            else:
                skip_no_baseline += 1
                is_opt = False
        else:
            skip_temp_low += 1
            is_opt = False
    else:
        skip_manual += 1
        is_opt = False

    if not is_opt:
        new_blocks = [{'phase': blk.phase, 'duration': blk.duration_minutes} for blk in r['blocks']]
        
    new_total_dur = sum(blk['duration'] for blk in new_blocks)
    new_steam_dur = sum(blk['duration'] for blk in new_blocks if blk['phase'] in ['HEAT', 'STEADY', 'RUNNING'])
    
    # E_start calculation with constraints
    if mc in machine_state:
        prev = machine_state[mc]
        real_gap = r['original_start_abs'] - prev['orig_end_abs']
        
        if real_gap > 120:
            # Finding 6 fix: No forced 1-hour gap for arrivals
            E_start = max(r['original_start_abs'], prev['new_end_abs'])
        else:
            allowed_min_gap = min(60, max(0, real_gap))
            E_start = prev['new_end_abs'] + allowed_min_gap
            
            # Finding 1 fix: Cap the early shift
            if is_opt:
                max_early_shift = baseline_dur * 0.5
            else:
                max_early_shift = r['orig_total_dur'] * 0.5
                
            absolute_earliest = r['original_start_abs'] - max_early_shift
            if E_start < absolute_earliest:
                E_start = int(absolute_earliest)
    else:
        E_start = r['original_start_abs']
        
    O_start = E_start
    forced = False
    while O_start + new_steam_dur < TOTAL_MINUTES:
        window = global_steam[O_start : O_start + new_steam_dur]
        if not window:
            break
        
        if max(window) + usage <= TARGET_STEAM:
            break 
            
        O_start += 1
        
        # Finding 3 fix: Escape valve logging
        if O_start - E_start > 720:
            forced = True
            escape_valve_triggers += 1
            break

    for i in range(O_start, min(O_start + new_steam_dur, TOTAL_MINUTES)):
        global_steam[i] += usage
        actual_max_steam = max(actual_max_steam, global_steam[i])
        
    machine_state[mc] = {
        'orig_end_abs': r['original_end_abs'],
        'new_end_abs': O_start + new_total_dur
    }
    
    diff = O_start - r['original_start_abs']
    dur_diff = new_total_dur - r['orig_total_dur']
    
    changes_log.append({
        'batch': r['batch'].label,
        'machine': mc,
        'shift_date': r['batch'].plan.shift_date,
        'diff': diff,
        'dur_diff': dur_diff,
        'is_opt': is_opt,
        'forced': forced
    })

print("=== DATA QUALITY REPORT ===")
print(f"Total Batches: {len(records)}")
print(f"Unmatched Labels: {unmatched_labels}")
print(f"Missing DyeingProcess: {missing_procs}")
print(f"Optimized (>110C, AUTO, has baseline): {optimized_count}")
print(f"Skipped (Temp <= 110C): {skip_temp_low}")
print(f"Skipped (MANUAL mode): {skip_manual}")
print(f"Skipped (No Baseline): {skip_no_baseline}")

moved_earlier = [c['diff'] for c in changes_log if c['diff'] < -5]
moved_later = [c['diff'] for c in changes_log if c['diff'] > 5]

print("\n=== SHIFTING REPORT ===")
print(f"Batches Moved Earlier: {len(moved_earlier)}")
if moved_earlier:
    print(f"  Average Early Shift: {sum(moved_earlier)/len(moved_earlier)/60:.2f} hrs")
    print(f"  Median Early Shift: {statistics.median(moved_earlier)/60:.2f} hrs")
    print(f"  Max Early Shift: {min(moved_earlier)/60:.2f} hrs")

print(f"Batches Moved Later: {len(moved_later)}")
if moved_later:
    print(f"  Average Late Shift: {sum(moved_later)/len(moved_later)/60:.2f} hrs")
    print(f"  Median Late Shift: {statistics.median(moved_later)/60:.2f} hrs")
    print(f"  Max Late Shift: {max(moved_later)/60:.2f} hrs")

print("\n=== STEAM LEVELLING REPORT ===")
print(f"Max Original Steam: {max(original_steam):.1f} kg/h")
print(f"Max New Steam: {actual_max_steam:.1f} kg/h")
print(f"Escape Valve Triggers (Forced Placements >12h delay): {escape_valve_triggers}")

total_orig_time = sum(c['dur_diff'] for c in changes_log if c['dur_diff'] < 0)
print(f"\nTotal time saved from durations: {abs(total_orig_time)/60:.1f} hours")
