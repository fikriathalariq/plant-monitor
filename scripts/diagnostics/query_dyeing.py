import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
django.setup()

from monitoring.models import DyeingProcess, Machine

machine = Machine.objects.filter(code='JR_03').first()

processes = DyeingProcess.objects.filter(
    machine=machine,
    max_temp__gte=125.0,
    max_temp__lte=150.0,
    is_valid_process=True,
    duration_effective__gte=30.0,
    real_heating_duration__isnull=False,
    identity__program__nama='P. 133'
).select_related('identity', 'identity__program')

valid_processes = []
for p in processes:
    h = p.real_heating_duration or 0
    s = p.steady_duration or 0
    c = p.cooling_duration or 0
    total_phase = h + s + c
    eff_dur = p.duration_effective or 0
    
    # Classify period
    period = "Sebelum Maret 2026" if p.start_time.strftime('%Y-%m') < '2026-03' else "Mulai Maret 2026"
    
    valid_processes.append((p, h, s, c, total_phase, eff_dur, period))

valid_processes.sort(key=lambda x: (x[6], x[1])) # Sort by period (Mulai will be before Sebelum alphabetically, wait. M comes before S. So 'Mulai Maret' then 'Sebelum Maret') then heat duration
# Let's fix the sort order so it is chronological period wise
# "Sebelum" should be first.
valid_processes.sort(key=lambda x: (0 if x[6] == "Sebelum Maret 2026" else 1, x[1]))

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
