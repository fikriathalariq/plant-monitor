import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import os

content = """
@report_router.get("/process/{process_id}/analytics")
def get_process_analytics(request, process_id: int):
    process = get_object_or_404(DyeingProcess.objects.select_related('machine', 'identity', 'identity__program'), id=process_id)
    identity = getattr(process, 'identity', None)
    program = identity.program if identity else None

    # Calculate metrics
    loss_time = None
    efficiency = None
    grade = "-"
    
    if program and program.durasi_ideal and process.duration_effective:
        loss_time = round(process.duration_effective - program.durasi_ideal, 1)
        efficiency = round((program.durasi_ideal / process.duration_effective) * 100, 1)
        if efficiency >= 80: grade = 'A'
        elif efficiency >= 60: grade = 'B'
        else: grade = 'C'

    heat_dur  = process.real_heating_duration or 0
    hold_dur  = process.steady_duration or 0
    cool_dur  = process.cooling_duration or 0
    total_dur = heat_dur + hold_dur + cool_dur

    phase_pct = {}
    if total_dur > 0:
        phase_pct['heat'] = round(heat_dur / total_dur * 100, 1)
        phase_pct['cooling'] = round(cool_dur / total_dur * 100, 1)
        if hold_dur > 0:
            phase_pct['hold'] = round(hold_dur / total_dur * 100, 1)

    # Chart data
    start_dt = process.start_time
    end_dt = process.end_time or timezone.now()
    
    logs = MachineMinuteLog.objects.filter(
        machine=process.machine, timestamp__range=(start_dt, end_dt)
    ).order_by('timestamp').values_list('timestamp', 'temperature')

    logs_list = list(logs)
    target_points = 80
    if len(logs_list) > target_points:
        step = len(logs_list) // target_points
        downsampled = logs_list[::step]
    else:
        downsampled = logs_list

    # Also get steam pressure for these timestamps
    steam_logs = MachineMinuteLog.objects.filter(
        machine__code='Steam_Pr', timestamp__range=(start_dt, end_dt)
    ).order_by('timestamp')
    
    steam_dict = {}
    for log in steam_logs:
        # round timestamp to nearest minute for matching
        t = log.timestamp.replace(second=0, microsecond=0)
        steam_dict[t] = log.temperature

    chart_data = []
    for ts, temp in downsampled:
        t_key = ts.replace(second=0, microsecond=0)
        steam_val = steam_dict.get(t_key, 0)
        
        chart_data.append({
            "time": timezone.localtime(ts).strftime('%H:%M'),
            "temp": temp,
            "pressure": steam_val
        })

    avg_steam = process.avg_steam_pressure

    return {
        "machine_name": process.machine.name,
        "batch_number": process.batch_number,
        "identity": {
            "nomor_order": identity.nomor_order if identity and identity.nomor_order else "-",
            "artikel_kain": identity.artikel_kain if identity and identity.artikel_kain else "-",
            "batch": identity.batch if identity and identity.batch else "-",
            "kode_buyer": identity.kode_buyer if identity and identity.kode_buyer else "-",
            "operator": identity.operator if identity and identity.operator else "-",
            "program": program.nama if program else "-",
            "jenis_proses": identity.get_jenis_proses_display() if identity else "-",
            "nomor_warna": identity.nomor_warna if identity and identity.nomor_warna else "-",
            "nomor_desain": identity.nomor_desain if identity and identity.nomor_desain else "-",
            "isi_per_tube": identity.isi_per_tube if identity and identity.isi_per_tube else "-",
            "heat_start_time": timezone.localtime(process.heating_start_time).strftime('%d %b %Y, %H:%M') if process.heating_start_time else "-",
            "end_time": timezone.localtime(process.end_time).strftime('%d %b %Y, %H:%M') if process.end_time else "In Progress",
            "masalah": identity.masalah if identity and identity.masalah else "",
            "keterangan": identity.keterangan if identity and identity.keterangan else "",
        },
        "kpi": {
            "duration_effective": round(process.duration_effective, 1) if process.duration_effective else None,
            "loss_time": loss_time,
            "efficiency": efficiency,
            "grade": grade,
        },
        "timing": {
            "heat_ideal": round(program.durasi_heating_ideal, 1) if program and program.durasi_heating_ideal else None,
            "keep_ideal": round(program.durasi_keeping_ideal, 1) if program and program.durasi_keeping_ideal else None,
            "cool_ideal": round(program.durasi_cooling_ideal, 1) if program and program.durasi_cooling_ideal else None,
            "total_ideal": round(program.durasi_ideal, 1) if program and program.durasi_ideal else None,
            "heat_actual": round(heat_dur, 0) if heat_dur else None,
            "hold_actual": round(hold_dur, 0) if hold_dur else None,
            "cool_actual": round(cool_dur, 0) if cool_dur else None,
            "total_actual": round(total_dur, 0) if total_dur else None,
            "peak_temp": round(process.max_temp, 1) if process.max_temp else None,
            "start_temp": round(process.start_temp, 1) if process.start_temp else None,
            "heat_gradient": round(process.heating_avg_gradient, 2) if process.heating_avg_gradient else None,
            "cool_gradient": round(process.cooling_avg_gradient, 2) if process.cooling_avg_gradient else None,
            "max_temp_prg": program.suhu_max if program else None,
            "ideal_heat": round(process.ideal_heating_time, 1) if process.ideal_heating_time else None,
            "avg_steam": round(avg_steam, 2) if avg_steam else None,
        },
        "phase_breakdown": phase_pct,
        "chart_data": chart_data,
        "avg_steam": avg_steam
    }
"""

with open("c:/Users/HP/Documents/Plant-Monitor/plant-monitor/monitoring/api_report.py", "a") as f:
    f.write(content)
print("Added get_process_analytics endpoint successfully.")
