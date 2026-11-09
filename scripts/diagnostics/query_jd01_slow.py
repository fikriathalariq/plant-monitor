import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import os
import django
from datetime import datetime
import pytz

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
django.setup()

from monitoring.models import DyeingProcess, Machine

machine = Machine.objects.filter(code__iexact='JD_01').first()

if not machine:
    print("Machine JD_01 not found!")
    exit(1)

processes = DyeingProcess.objects.filter(
    machine=machine,
    max_temp__gte=125.0,
    max_temp__lte=150.0,
    is_valid_process=True,
    duration_effective__gte=30.0,
    real_heating_duration__isnull=False,
    start_time__gte=datetime(2026, 6, 29, 0, 0, 0, tzinfo=pytz.timezone('Asia/Jakarta')),
    avg_steam_pressure__gt=3.5
).select_related('identity', 'identity__program')

data = []

for p in processes:
    if not p.start_time: continue
    
    h = p.real_heating_duration or 0
    s = p.steady_duration or 0
    c = p.cooling_duration or 0
    total_phase = h + s + c
    eff_dur = p.duration_effective or 0
    
    data.append((p, h, s, c, total_phase, eff_dur))

# Sort by Total Fase (x[4]) then Heat (x[1]) DESCENDING
data.sort(key=lambda x: (x[4], x[1]), reverse=True)

# Take top 50 slowest
valid_processes = data[:50]

print("| Rank | Batch | Waktu Mulai (WIB) | Start Temp (°C) | Peak Temp (°C) | Avg Steam Pr (Bar) | Heat Act/Idl | Hold Act/Idl | Cool Act/Idl | Total Fase | Eff. Durasi | Program | Max Prg (°C) |")
print("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")

for idx, (p, h, s, c, total_phase, eff_dur) in enumerate(valid_processes, 1):
    if p.start_time:
        local_time = p.start_time.astimezone(pytz.timezone('Asia/Jakarta'))
        st_time_str = local_time.strftime('%Y-%m-%d %H:%M')
    else:
        st_time_str = "N/A"
    
    prog_name = "-"
    prog_max_temp = "-"
    h_ideal = "-"
    s_ideal = "-"
    c_ideal = "-"
    try:
        if hasattr(p, 'identity') and p.identity and p.identity.program:
            prog = p.identity.program
            prog_name = prog.nama or "-"
            prog_max_temp = f"{prog.suhu_max}" if prog.suhu_max else "-"
            h_ideal = f"{prog.durasi_heating_ideal}" if prog.durasi_heating_ideal else "-"
            s_ideal = f"{prog.durasi_keeping_ideal}" if prog.durasi_keeping_ideal else "-"
            c_ideal = f"{prog.durasi_cooling_ideal}" if prog.durasi_cooling_ideal else "-"
    except Exception as e:
        pass
        
    start_t = f"{p.start_temp:.1f}" if p.start_temp is not None else "-"
    steam_pr = f"{p.avg_steam_pressure:.2f}" if p.avg_steam_pressure is not None else "-"
        
    print(f"| {idx} | **{p.batch_number}** | {st_time_str} | {start_t} | {p.max_temp:.1f} | {steam_pr} | {h:.1f} / {h_ideal} | {s:.1f} / {s_ideal} | {c:.1f} / {c_ideal} | {total_phase:.1f} | {eff_dur:.1f} | {prog_name} | {prog_max_temp} |")
