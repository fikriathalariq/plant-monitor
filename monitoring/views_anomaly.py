from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from datetime import timedelta
import json

from .models import AnomalyThresholdMaster, AnomalyThresholdProposal, DyeingIdentity

def calibration_chart_view(request, source_type, record_id):
    """
    Menampilkan grafik kurva distribusi normal dan plot titik data aktual.
    source_type: 'master' atau 'proposal'
    """
    if source_type == 'master':
        record = get_object_or_404(AnomalyThresholdMaster, id=record_id)
        machine = record.machine
        program = record.program
        title = f"Kalibrasi Master: {machine.code} - {program.nama}"
        
        # Load params
        suhu_mean = record.suhu_mean; suhu_std = record.suhu_stddev
        suhu_low = record.suhu_lower_bound; suhu_up = record.suhu_upper_bound
        
        heat_mean = record.heat_mean; heat_std = record.heat_stddev
        heat_low = record.heat_lower_bound; heat_up = record.heat_upper_bound
        
        keep_mean = record.keep_mean; keep_std = record.keep_stddev
        keep_low = record.keep_lower_bound; keep_up = record.keep_upper_bound
        
        cool_mean = record.cool_mean; cool_std = record.cool_stddev
        cool_low = record.cool_lower_bound; cool_up = record.cool_upper_bound

    else:
        record = get_object_or_404(AnomalyThresholdProposal, id=record_id)
        machine = record.master.machine
        program = record.master.program
        title = f"Dry-Run Usulan Kalibrasi: {machine.code} - {program.nama}"
        
        # Load proposed params
        suhu_mean = record.suhu_mean_new; suhu_std = record.suhu_stddev_new
        suhu_low = record.suhu_lower_bound_new; suhu_up = record.suhu_upper_bound_new
        
        heat_mean = record.heat_mean_new; heat_std = record.heat_stddev_new
        heat_low = record.heat_lower_bound_new; heat_up = record.heat_upper_bound_new
        
        keep_mean = record.keep_mean_new; keep_std = record.keep_stddev_new
        keep_low = record.keep_lower_bound_new; keep_up = record.keep_upper_bound_new
        
        cool_mean = record.cool_mean_new; cool_std = record.cool_stddev_new
        cool_low = record.cool_lower_bound_new; cool_up = record.cool_upper_bound_new

    # Tarik riwayat data titik aktual 180 hari terakhir
    now = timezone.now()
    start_time = now - timedelta(days=180)
    
    qs = DyeingIdentity.objects.filter(
        machine=machine,
        program=program,
        dyeing_process__isnull=False,
        dyeing_process__is_valid_process=True,
        dyeing_process__start_time__gte=start_time,
        dyeing_process__start_time__lte=now
    ).select_related('dyeing_process', 'program')

    actual_suhu = []
    actual_heat = []
    actual_keep = []
    actual_cool = []
    
    for r in qs:
        b = r.dyeing_process
        p = r.program
        
        # Filter healthy pressure
        if b.avg_steam_pressure is not None and b.avg_steam_pressure < 3.8:
            continue
            
        ds = (b.max_temp - p.suhu_max) if p.suhu_max and b.max_temp else None
        dh = (b.heating_duration - p.durasi_heating_ideal) if p.durasi_heating_ideal and b.heating_duration is not None else None
        dk = (b.steady_duration - p.durasi_keeping_ideal) if p.durasi_keeping_ideal and b.steady_duration is not None else None
        dc = (b.cooling_duration - p.durasi_cooling_ideal) if p.durasi_cooling_ideal and b.cooling_duration is not None else None
        
        if ds is not None: actual_suhu.append(round(ds, 2))
        if dh is not None: actual_heat.append(round(dh, 2))
        if dk is not None: actual_keep.append(round(dk, 2))
        if dc is not None: actual_cool.append(round(dc, 2))

    # Pass the data to the template
    context = {
        'title': title,
        'params': json.dumps({
            'suhu': {'mean': suhu_mean, 'std': suhu_std, 'low': suhu_low, 'up': suhu_up},
            'heat': {'mean': heat_mean, 'std': heat_std, 'low': heat_low, 'up': heat_up},
            'keep': {'mean': keep_mean, 'std': keep_std, 'low': keep_low, 'up': keep_up},
            'cool': {'mean': cool_mean, 'std': cool_std, 'low': cool_low, 'up': cool_up},
        }),
        'actuals': json.dumps({
            'suhu': actual_suhu,
            'heat': actual_heat,
            'keep': actual_keep,
            'cool': actual_cool
        })
    }
    
    return render(request, 'calibration_chart.html', context)
