import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import os
import sys
from datetime import datetime, timedelta
import pytz
import numpy as np

# Setup Django Environment
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
import django
django.setup()

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from monitoring.models import Machine, DyeingProcess, MachineMinuteLog, ProgramMaster, DyeingIdentity

OUTPUT_DIR = r"C:\Users\HP\.gemini\antigravity\brain\708cb8e3-3e9d-4c3b-b278-31dfe6433d38"
os.makedirs(OUTPUT_DIR, exist_ok=True)

tz = pytz.timezone('Asia/Jakarta')
m_jr03 = Machine.objects.get(code='JR_03')
m_steam = Machine.objects.get(code='Steam_Pr')

print("Starting JR 3 Heating Report Generation...")

# ==============================================================================
# 1. CHART 1: RECREATING THE USER SCREENSHOT WITH STEAM PRESSURE OVERLAY
# ==============================================================================
print("Generating Chart 1: Batch 71 & 72 vs Steam Pressure...")

start_t = datetime(2026, 9, 7, 21, 0, tzinfo=tz)
end_t = datetime(2026, 9, 8, 9, 0, tzinfo=tz)

logs_jr03 = MachineMinuteLog.objects.filter(
    machine=m_jr03, 
    timestamp__gte=start_t, 
    timestamp__lte=end_t
).order_by('timestamp')

logs_steam = MachineMinuteLog.objects.filter(
    machine=m_steam, 
    timestamp__gte=start_t, 
    timestamp__lte=end_t
).order_by('timestamp')

times_jr = [l.timestamp.astimezone(tz).replace(tzinfo=None) for l in logs_jr03]
raw_temps = [l.raw_temperature for l in logs_jr03]
cal_temps = [l.temperature for l in logs_jr03]

times_st = [l.timestamp.astimezone(tz).replace(tzinfo=None) for l in logs_steam]
steam_prs = [l.temperature for l in logs_steam]

fig, ax1 = plt.subplots(figsize=(14, 7), dpi=150)

# Temperature curves
color_temp = '#1f77b4'
line1 = ax1.plot(times_jr, raw_temps, color=color_temp, linewidth=2.5, label='JR 3 Suhu Aktual (°C)')
ax1.set_xlabel('Waktu Lokal (WIB / Asia/Jakarta)', fontsize=12, fontweight='bold')
ax1.set_ylabel('Suhu Mesin JR 3 (°C)', color=color_temp, fontsize=12, fontweight='bold')
ax1.tick_params(axis='y', labelcolor=color_temp)
ax1.set_ylim(20, 140)

# Highlight Plateaus at 80-100C
t_b71_start = datetime(2026, 9, 7, 23, 20)
t_b71_end = datetime(2026, 9, 8, 0, 46)
ax1.axvspan(t_b71_start, t_b71_end, color='orange', alpha=0.25, label='Plateau 80–100°C (87 min)')

t_b72_start = datetime(2026, 9, 8, 5, 5)
t_b72_end = datetime(2026, 9, 8, 6, 15)
ax1.axvspan(t_b72_start, t_b72_end, color='orange', alpha=0.25)

# Steam Pressure on secondary axis
ax2 = ax1.twinx()
color_steam = '#2ca02c'
line2 = ax2.plot(times_st, steam_prs, color=color_steam, linewidth=1.5, linestyle='--', alpha=0.85, label='Steam Header Pressure (Bar)')
ax2.set_ylabel('Tekanan Uap / Steam_Pr (Bar)', color=color_steam, fontsize=12, fontweight='bold')
ax2.tick_params(axis='y', labelcolor=color_steam)
ax2.set_ylim(0, 8)
ax2.axhline(3.8, color='red', linestyle=':', alpha=0.6, label='Batas Minimum Steam Standar (3.8 Bar)')

# Annotations
ax1.annotate('Batch #71 (P. 136)\nHold/Slow 86–92°C: 87 min\nAvg Steam: 5.12 Bar',
             xy=(datetime(2026, 9, 8, 0, 0), 88),
             xytext=(datetime(2026, 9, 7, 22, 30), 115),
             arrowprops=dict(facecolor='black', shrink=0.05, width=1.5, headwidth=8),
             bbox=dict(boxstyle="round,pad=0.5", fc="white", ec="orange", lw=2),
             fontsize=10, fontweight='bold')

ax1.annotate('Batch #72 (P. 136)\nHold/Slow 88–90°C: 60 min\nAvg Steam: 5.32 Bar',
             xy=(datetime(2026, 9, 8, 5, 40), 89),
             xytext=(datetime(2026, 9, 8, 3, 30), 115),
             arrowprops=dict(facecolor='black', shrink=0.05, width=1.5, headwidth=8),
             bbox=dict(boxstyle="round,pad=0.5", fc="white", ec="orange", lw=2),
             fontsize=10, fontweight='bold')

# Formatting x-axis
ax1.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M\n%d/%m/%Y'))
ax1.xaxis.set_major_locator(mdates.HourLocator(interval=2))
ax1.grid(True, linestyle=':', alpha=0.6)

# Combine legends
lines = line1 + line2
labels = [l.get_label() for l in lines]
ax1.legend(lines, labels, loc='upper left', framealpha=0.9)

plt.title('Analisis Riwayat Suhu JR 3 vs Tekanan Steam Header\n(Konfirmasi Batch 71 & 72: Program P. 136 - Plateau Bukan Akibat Tekanan Uap)', 
          fontsize=14, fontweight='bold', pad=15)
plt.tight_layout()
chart1_path = os.path.join(OUTPUT_DIR, 'jr03_batch_71_72_vs_steam.png')
plt.savefig(chart1_path)
plt.close()
print(f"Chart 1 saved to {chart1_path}")


# ==============================================================================
# 2. CHART 2: OVERLAY COMPARISON - P. 136 (Bermasalah) vs P. 133 & P. 132 (Normal)
# ==============================================================================
print("Generating Chart 2: Normalized Heating Curves Overlay...")

def get_normalized_heating(dp_id):
    dp = DyeingProcess.objects.get(id=dp_id)
    logs = list(MachineMinuteLog.objects.filter(
        machine=dp.machine,
        timestamp__gte=dp.start_time,
        timestamp__lte=dp.end_time or (dp.start_time + timedelta(hours=5))
    ).order_by('timestamp'))
    
    valid = [l for l in logs if l.raw_temperature is not None]
    temps = [l.raw_temperature for l in valid]
    
    # find where temp crosses 40C
    start_idx = None
    for i, t in enumerate(temps):
        if t >= 40.0:
            start_idx = i
            break
    if start_idx is None:
        start_idx = 0
        
    max_idx = int(np.argmax(temps))
    heating_temps = temps[start_idx:max_idx+1]
    elapsed_minutes = list(range(len(heating_temps)))
    return elapsed_minutes, heating_temps

fig, ax = plt.subplots(figsize=(13, 7), dpi=150)

# Problem batches (P. 136)
dp_71 = DyeingIdentity.objects.filter(batch='71', machine=m_jr03).first().dyeing_process
m_71, t_71 = get_normalized_heating(dp_71.id)
ax.plot(m_71, t_71, color='#d62728', linewidth=2.8, label='Batch #71 (P. 136) - Plateau 87m, Total Heat 166m')

dp_72 = DyeingIdentity.objects.filter(batch='72', machine=m_jr03).first().dyeing_process
m_72, t_72 = get_normalized_heating(dp_72.id)
ax.plot(m_72, t_72, color='#e377c2', linewidth=2.8, linestyle='--', label='Batch #72 (P. 136) - Plateau 60m, Total Heat 145m')

# Severe historical batch: DP 3209802 (Batch 822, P. 136)
try:
    dp_822 = DyeingProcess.objects.filter(identity__batch='822', machine=m_jr03).first()
    if dp_822:
        m_822, t_822 = get_normalized_heating(dp_822.id)
        ax.plot(m_822, t_822, color='#8c564b', linewidth=2, linestyle=':', alpha=0.8, label='Batch #822 (P. 136) - Plateau 156m')
except Exception as e:
    pass

# Normal batches (P. 133 on JR 3)
try:
    dp_319 = DyeingProcess.objects.filter(identity__batch='319', machine=m_jr03).first()
    if dp_319:
        m_319, t_319 = get_normalized_heating(dp_319.id)
        ax.plot(m_319, t_319, color='#2ca02c', linewidth=2.5, label='Batch #319 (P. 133) - Normal Kontinu (Tanpa Plateau)')
except Exception as e:
    pass

try:
    dp_320 = DyeingProcess.objects.filter(identity__batch='320', machine=m_jr03).first()
    if dp_320:
        m_320, t_320 = get_normalized_heating(dp_320.id)
        ax.plot(m_320, t_320, color='#17becf', linewidth=2.5, linestyle='-.', label='Batch #320 (P. 133) - Normal Kontinu')
except Exception as e:
    pass

# Normal batch P. 132 on JR 3
try:
    dp_132 = DyeingProcess.objects.filter(identity__program__nama='P. 132', machine=m_jr03).first()
    if dp_132:
        m_132, t_132 = get_normalized_heating(dp_132.id)
        ax.plot(m_132, t_132, color='#ff7f0e', linewidth=2, label=f'Batch #{dp_132.identity.batch} (P. 132) - Normal Kontinu')
except Exception as e:
    pass

ax.axhspan(80, 100, color='gray', alpha=0.15, label='Zona Investigasi (80–100°C)')
ax.axhline(130, color='blue', linestyle=':', label='Target Suhu Maksimal (130°C)')

ax.set_xlabel('Durasi Pemanasan Sejak 40°C (Menit)', fontsize=12, fontweight='bold')
ax.set_ylabel('Suhu Aktual (°C)', fontsize=12, fontweight='bold')
ax.set_title('Perbandingan Karakteristik Kurva Pemanasan pada Mesin JR 3\n(P. 136 Menunjukkan Step Plateau Datar 88–90°C vs P. 133 & P. 132 yang Kontinu)', fontsize=13, fontweight='bold', pad=15)
ax.set_ylim(35, 135)
ax.set_xlim(0, 220)
ax.grid(True, linestyle=':', alpha=0.7)
ax.legend(loc='lower right', framealpha=0.9, fontsize=9.5)

plt.tight_layout()
chart2_path = os.path.join(OUTPUT_DIR, 'jr03_heating_comparison_overlay.png')
plt.savefig(chart2_path)
plt.close()
print(f"Chart 2 saved to {chart2_path}")


# ==============================================================================
# 3. CHART 3: ZONE DURATION DISTRIBUTION PER PROGRAM
# ==============================================================================
print("Generating Chart 3: Duration breakdown per program...")

programs_to_plot = ['P. 136', 'P. 019', 'P. 133', 'P. 132', 'P. 024', 'P. 025']
zone_data = {p: {'40-80': [], '80-100': [], '100-128': []} for p in programs_to_plot}

procs_all = DyeingProcess.objects.filter(
    machine=m_jr03,
    identity__program__nama__in=programs_to_plot
).select_related('identity', 'identity__program')

for p in procs_all:
    p_name = p.identity.program.nama
    logs = list(MachineMinuteLog.objects.filter(
        machine=m_jr03,
        timestamp__gte=p.start_time,
        timestamp__lte=p.end_time or (p.start_time + timedelta(hours=6))
    ).order_by('timestamp'))
    
    valid = [l for l in logs if l.raw_temperature is not None]
    if not valid:
        continue
    temps = [l.raw_temperature for l in valid]
    max_idx = int(np.argmax(temps))
    if temps[max_idx] < 120:
        continue
    h_temps = temps[:max_idx+1]
    
    t1 = sum(1 for t in h_temps if 40 <= t < 80)
    t2 = sum(1 for t in h_temps if 80 <= t < 100)
    t3 = sum(1 for t in h_temps if 100 <= t <= 130)
    
    zone_data[p_name]['40-80'].append(t1)
    zone_data[p_name]['80-100'].append(t2)
    zone_data[p_name]['100-128'].append(t3)

fig, ax = plt.subplots(figsize=(12, 6.5), dpi=150)

x = np.arange(len(programs_to_plot))
width = 0.25

means_z1 = [np.mean(zone_data[p]['40-80']) if zone_data[p]['40-80'] else 0 for p in programs_to_plot]
means_z2 = [np.mean(zone_data[p]['80-100']) if zone_data[p]['80-100'] else 0 for p in programs_to_plot]
means_z3 = [np.mean(zone_data[p]['100-128']) if zone_data[p]['100-128'] else 0 for p in programs_to_plot]

rects1 = ax.bar(x - width, means_z1, width, label='Zona 1: 40–80°C', color='#2ca02c')
rects2 = ax.bar(x, means_z2, width, label='Zona 2: 80–100°C (Area Masalah)', color='#d62728')
rects3 = ax.bar(x + width, means_z3, width, label='Zona 3: 100–128°C', color='#1f77b4')

ax.set_ylabel('Rata-rata Durasi (Menit)', fontsize=12, fontweight='bold')
ax.set_title('Distribusi Rata-rata Durasi Pemanasan per Zona Suhu pada Mesin JR 3\n(Zona 80–100°C Hanya Mengalami Lonjakan Durasi pada P. 136 & P. 019)', fontsize=13, fontweight='bold', pad=15)
ax.set_xticks(x)
ax.set_xticklabels([f"{p}\n(n={len(zone_data[p]['80-100'])})" for p in programs_to_plot], fontsize=11, fontweight='bold')
ax.legend(fontsize=11)
ax.grid(True, axis='y', linestyle=':', alpha=0.7)

def autolabel(rects):
    for rect in rects:
        height = rect.get_height()
        if height > 0:
            ax.annotate(f'{height:.1f}m',
                        xy=(rect.get_x() + rect.get_width() / 2, height),
                        xytext=(0, 3),
                        textcoords="offset points",
                        ha='center', va='bottom', fontsize=9)

autolabel(rects1)
autolabel(rects2)
autolabel(rects3)

plt.tight_layout()
chart3_path = os.path.join(OUTPUT_DIR, 'jr03_zone_duration_distribution.png')
plt.savefig(chart3_path)
plt.close()
print(f"Chart 3 saved to {chart3_path}")

print("All charts successfully generated!")
