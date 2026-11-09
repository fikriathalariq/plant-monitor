import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import os
import django
import pytz
from datetime import datetime

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
django.setup()

from monitoring.models import DyeingProcess, Machine, MachineGroup
from django.db.models import Avg

start_date = datetime(2026, 3, 25, 0, 0, 0, tzinfo=pytz.timezone('Asia/Jakarta'))

target_groups = [
    'Jet Dyeing Gedung Processing', 
    'Jet Relax Gedung Processing', 
    'Mesin Jet Gedung Printing'
]

machines = Machine.objects.filter(group__name__in=target_groups).order_by('group__name', 'code')

with open(r"C:\Users\HP\.gemini\antigravity\brain\3cd1910f-c004-4696-aeaa-1b5108d5599b\fleet_efficiency_report.md", "w", encoding='utf-8') as f:
    f.write("# Laporan Efisiensi Armada Mesin (JD_PRC, JR_PRC, JD_PRT)\n\n")
    f.write("*Filter: Suhu Max Program >= 120°C | Avg Steam > 3.8 bar | Durasi Aktual >= 40 mnt | Deviasi Suhu <= 15°C*\n\n")
    
    f.write("| Grup | Mesin | Total Proses | Ada Program | Tanpa Program | Valid & Sehat | > 60% | > 70% | > 80% | Efisiensi Rata-Rata |\n")
    f.write("| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |\n")
    
    for mc in machines:
        group_name = ""
        if "Dyeing" in mc.group.name and "Processing" in mc.group.name:
            group_name = "JD_PRC"
        elif "Relax" in mc.group.name and "Processing" in mc.group.name:
            group_name = "JR_PRC"
        elif "Printing" in mc.group.name:
            group_name = "JD_PRT"
        else:
            group_name = mc.group.name

        mc_start_date = datetime(2026, 6, 28, 0, 0, 0, tzinfo=pytz.timezone('Asia/Jakarta')) if mc.code == 'JD_03' else start_date
        
        processes = DyeingProcess.objects.filter(
            machine=mc,
            start_time__gte=mc_start_date
        ).select_related('identity', 'identity__program')
        
        total_proses = 0
        ada_program = 0
        tanpa_program = 0
        
        valid_sehat_count = 0
        count_60 = 0
        count_70 = 0
        count_80 = 0
        total_efficiency = 0.0
        
        for p in processes:
            total_proses += 1
            has_program = False
            
            # Check program
            if hasattr(p, 'identity') and p.identity and p.identity.program:
                has_program = True
                ada_program += 1
            else:
                tanpa_program += 1
                
            if not has_program:
                continue
                
            prog = p.identity.program
            
            # 1. Suhu Target >= 120
            if not prog.suhu_max or prog.suhu_max < 120:
                continue
                
            # 2. Durasi Efektif >= 40 menit
            h = p.real_heating_duration or 0
            s = p.steady_duration or 0
            c = p.cooling_duration or 0
            total_actual = h + s + c
            if total_actual < 40:
                continue
                
            # 3. Deviasi Suhu Aktual vs Program <= 15
            actual_max = p.max_temp or 0
            if abs(actual_max - prog.suhu_max) > 15:
                continue
                
            # 4. Kondisi Steam Sehat > 3.8
            if not p.avg_steam_pressure or p.avg_steam_pressure <= 3.8:
                continue
                
            # If all passed, it's valid & sehat!
            valid_sehat_count += 1
            
            ideal_h = prog.durasi_heating_ideal or 0
            ideal_s = prog.durasi_keeping_ideal or 0
            ideal_c = prog.durasi_cooling_ideal or 0
            ideal_total = ideal_h + ideal_s + ideal_c
            
            efficiency = (ideal_total / total_actual) * 100
            total_efficiency += efficiency
            
            if efficiency > 60:
                count_60 += 1
            if efficiency > 70:
                count_70 += 1
            if efficiency > 80:
                count_80 += 1
                
        avg_eff = (total_efficiency / valid_sehat_count) if valid_sehat_count > 0 else 0
        
        if total_proses > 0:
            f.write(f"| {group_name} | **{mc.code}** | {total_proses} | {ada_program} | {tanpa_program} | {valid_sehat_count} | {count_60} | {count_70} | {count_80} | **{avg_eff:.1f}%** |\n")

print("Report generated successfully.")
