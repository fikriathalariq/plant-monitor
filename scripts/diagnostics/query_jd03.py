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

machine = Machine.objects.filter(code__iexact='JD_03').first()

if not machine:
    print("Machine JD_03 not found!")
    exit(1)

processes = DyeingProcess.objects.filter(
    machine=machine,
    max_temp__gte=125.0,
    max_temp__lte=150.0,
    is_valid_process=True,
    duration_effective__gte=30.0,
    real_heating_duration__isnull=False
).select_related('identity', 'identity__program')

sebelum = []
mulai = []
cutoff_date = datetime.strptime('2026-06-27 00:00:00', '%Y-%m-%d %H:%M:%S').replace(tzinfo=pytz.timezone('Asia/Jakarta'))

for p in processes:
    if not p.start_time: continue
    
    h = p.real_heating_duration or 0
    s = p.steady_duration or 0
    c = p.cooling_duration or 0
    total_phase = h + s + c
    eff_dur = p.duration_effective or 0
    
    # Classify period
    if p.start_time < cutoff_date:
        sebelum.append((p, h, s, c, total_phase, eff_dur, "Sebelum 27 Jun 2026"))
    else:
        mulai.append((p, h, s, c, total_phase, eff_dur, "Mulai 27 Jun 2026"))

# Sort by Total Fase (x[4]) then Heat (x[1])
sebelum.sort(key=lambda x: (x[4], x[1]))
mulai.sort(key=lambda x: (x[4], x[1]))

valid_processes = sebelum[:30] + mulai[:30]

print("| Periode | Batch | Waktu Mulai | Peak Temp (°C) | Heat Act/Idl | Hold Act/Idl | Cool Act/Idl | Total Fase | Eff. Durasi | Program | Max Prg (°C) |")
print("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")

for p, h, s, c, total_phase, eff_dur, period in valid_processes:
    st_time_str = p.start_time.strftime('%Y-%m-%d %H:%M') if p.start_time else "N/A"
    
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
        
    print(f"| {period} | **{p.batch_number}** | {st_time_str} | {p.max_temp:.1f} | {h:.1f} / {h_ideal} | {s:.1f} / {s_ideal} | {c:.1f} / {c_ideal} | {total_phase:.1f} | {eff_dur:.1f} | {prog_name} | {prog_max_temp} |")
