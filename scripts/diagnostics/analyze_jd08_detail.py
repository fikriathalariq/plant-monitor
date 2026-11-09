import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import os, sys, django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
django.setup()

from monitoring.models import DyeingIdentity

qs = DyeingIdentity.objects.filter(
    machine__code="JD_08",
    program__nama__in=["P. 015", "P. 025"],
    dyeing_process__isnull=False,
    program__isnull=False,
    dyeing_process__is_valid_process=True
).select_related('dyeing_process', 'program').order_by('program__nama', 'dyeing_process__start_time')

artifact_path = r"C:\Users\HP\.gemini\antigravity\brain\3c9a3eae-d5be-44c9-b0b1-29e9f62c1f25\jd08_p015_p025_details.md"

with open(artifact_path, "w", encoding="utf-8") as f:
    f.write("# Detail Data Batch Mesin JD_08 (P. 015 & P. 025)\n\n")
    f.write("Berikut adalah daftar seluruh batch (siklus) pada Mesin JD_08 yang menjalankan program P. 015 dan P. 025. Data ini dapat membantu mengidentifikasi apakah ada program yang salah klasifikasi atau keliru di-assign ke batch yang salah.\n\n")
    
    f.write("| Program | Batch No | Waktu Mulai | Max Temp Aktual | Target Suhu | Selisih | Durasi Efektif (m) |\n")
    f.write("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n")
    
    for r in qs:
        batch = r.dyeing_process
        prog = r.program
        
        actual = batch.max_temp
        prog_suhu = prog.suhu_max
        
        if actual is None or prog_suhu is None:
            continue
            
        diff = actual - prog_suhu
        start_time = batch.start_time.strftime('%Y-%m-%d %H:%M') if batch.start_time else "N/A"
        dur = f"{batch.duration_effective:.0f}" if batch.duration_effective else "N/A"
        diff_str = f"+{diff:.1f}" if diff > 0 else f"{diff:.1f}"
        
        # Beri bold/highlight jika bedanya ekstrim (> 5 derajat)
        if abs(diff) > 5:
            actual_str = f"**{actual:.1f}°C**"
            diff_str = f"**{diff_str}°C**"
        else:
            actual_str = f"{actual:.1f}°C"
            diff_str = f"{diff_str}°C"
            
        f.write(f"| {prog.nama} | {batch.batch_number} | {start_time} | {actual_str} | {prog_suhu}°C | {diff_str} | {dur} |\n")
        
print(f"Artifact created at {artifact_path}")
