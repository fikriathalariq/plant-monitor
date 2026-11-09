from django.shortcuts import render, redirect
from django.utils.timezone import now
from .models import Machine, MachineGroup, OperatorProfile, MachineMinuteLog
from django.utils.timezone import localtime
from datetime import datetime
from django.utils.timezone import make_aware
from django.http import JsonResponse, Http404
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.contrib.auth.views import LoginView
from django.views.decorators.http import require_GET
from django.contrib import messages
from django.db.models import Prefetch
from .models import CompanyProfile
from django.utils import timezone
from datetime import timedelta
import math
from django.shortcuts import get_object_or_404
from .models import Machine, MachineGroup, OperatorProfile, MachineMinuteLog, CompanyProfile, DyeingProcess, DyeingIdentity
from .decorators import position_required, get_user_allowed_pages
from monitoring.utils.signal_freshness import get_machine_display_status, STATUS_NO_SIGNAL
# Try to import ProcessingConfig, but don't fail if it doesn't exist
try:
    from monitoring.utils.gradient_processor import ProcessingConfig
except ImportError:
    ProcessingConfig = None

def get_recent_status_changes(hours=1, machine_lookup=None):
    """
    [OPTIMIZED] Tidak ada DB query sama sekali.
    Filter langsung dari list Machine yang sudah di-load di memori.
    
    Syarat: machine_lookup harus diisi (dict code -> Machine instance).
    Field yang dipakai: status_changed_at, previous_display_status,
    last_thermal_status, last_status, operation_mode.
    """
    if machine_lookup is None:
        return []

    cutoff = timezone.now() - timedelta(hours=hours)
    changes = []

    for machine in machine_lookup.values():
        # Skip mesin yang belum pernah ganti status
        if not machine.status_changed_at:
            continue
        # Skip yang perubahannya lebih lama dari window waktu
        if machine.status_changed_at < cutoff:
            continue

        # Tentukan display_status saat ini (sama dengan logika di dashboard)
        if machine.operation_mode == "MANUAL":
            new_display = machine.manual_status or "Stop"
        elif machine.code in ["Oil_Temp", "Steam_Pr"]:
            new_display = machine.last_status or "Offline"
        else:
            new_display = machine.last_thermal_status or "OFFLINE"

        old_display = machine.previous_display_status or "Unknown"

        # Tentukan change_type untuk styling
        if new_display == 'Running' and old_display != 'Running':
            change_type = 'good'
        elif new_display in ['Stop', 'Offline', 'Warning', 'OFFLINE'] and old_display in ['Running', 'HEAT', 'STEADY']:
            change_type = 'bad'
        elif new_display == 'Warning':
            change_type = 'warning'
        else:
            change_type = 'neutral'

        changes.append({
            'name':          machine.name or machine.code,
            'code':          machine.code,
            'status_before': old_display,
            'status_after':  new_display,
            'detail_before': '',
            'detail_after':  '',
            'changed_at':    machine.status_changed_at,
            'change_type':   change_type,
        })

    changes.sort(key=lambda x: x['changed_at'], reverse=True)
    return changes
@login_required
@position_required('dashboard')
def dashboard(request):

    # ─────────────────────────────────────────────────────────────────
    # 1. Ambil SEMUA mesin aktif dalam SATU query (menghindari N+1)
    #    select_related('group') supaya tidak ada query tambahan per mesin
    # ─────────────────────────────────────────────────────────────────
    all_machines = list(
        Machine.objects
        .filter(is_active=True)
        .select_related('group')
        .order_by('group__code', 'code')
    )

    # ─────────────────────────────────────────────────────────────────
    # 2. KPI Realtime — ambil dari list yang sudah ada (no extra query)
    # ─────────────────────────────────────────────────────────────────
    steam_machine = next((m for m in all_machines if m.code == 'Steam_Pr'), None)
    hto_machine   = next((m for m in all_machines if m.code == 'Oil_Temp'), None)

    steam_value = steam_machine.temperature if steam_machine and steam_machine.temperature is not None else None
    hto_value   = hto_machine.temperature   if hto_machine   and hto_machine.temperature   is not None else None

    kpi = {
        "steam":    {"value": steam_value, "unit": "bar"},
        "hto":      {"value": hto_value,   "unit": "°C"},
        "downtime": {"value": 62, "avg": 44, "trend": 18, "top_issue": "Motor overload Line 2"},
        "energy":   {"value": 1820, "specific": 0.151, "trend": -3.2},
    }

    # ─────────────────────────────────────────────────────────────────
    # 3. Total Steam & HTO (dari list yang sudah ada — no extra query)
    # ─────────────────────────────────────────────────────────────────
    total_steam = 0.0
    total_hto   = 0.0

    for machine in all_machines:
        from monitoring.utils.steam_active import is_steam_active_from_machine
        is_active = is_steam_active_from_machine(machine)

        if is_active:
            total_steam += (machine.average_steam_usage or 0.0)
            total_hto   += (machine.avg_hto_calories or 0.0)

    # ─────────────────────────────────────────────────────────────────
    # 4. Grup Panel — gunakan list yang sudah ada, grup dengan dict
    #    (SATU query MachineGroup, nol query tambahan untuk Machine)
    # ─────────────────────────────────────────────────────────────────
    from collections import defaultdict
    from .models import MachineCalibration

    # Ambil semua master kalibrasi yang aktif (hanya 1 query ringan)
    active_calibrations = {c.machine_id: c for c in MachineCalibration.objects.filter(is_active=True)}

    # Kelompokkan mesin berdasarkan group
    machines_by_group = defaultdict(list)
    for m in all_machines:
        if m.group_id is not None:
            machines_by_group[m.group_id].append(m)

    groups = list(MachineGroup.objects.all().order_by("code"))
    group_panels = []

    # Ambil snapshot 1 jam lalu untuk mengecek apakah mesin baru menyala (NEW)
    from .models import MachineStatusSnapshot
    one_hour_ago = now() - timedelta(hours=1)
    past_snapshot = MachineStatusSnapshot.objects.filter(timestamp__lte=one_hour_ago).order_by('-timestamp').first()
    past_snapshot_data = past_snapshot.snapshot_data if past_snapshot else {}

    for g in groups:
        group_machines = machines_by_group.get(g.id, [])
        if not group_machines:
            continue  # skip grup kosong

        machines_for_group = []
        status_counts = {"running": 0, "heat": 0, "cool": 0, "steady": 0, "off": 0}

        for m in group_machines:
            temp = m.temperature
            if isinstance(temp, float) and math.isnan(temp):
                temp = None
            elif temp is not None and m.id in active_calibrations:
                # Terapkan rumus kalibrasi: y = Ax^2 + Bx + C
                cal = active_calibrations[m.id]
                cal_val = (cal.a_coeff * temp ** 2) + (cal.b_coeff * temp) + cal.c_coeff
                temp = round(cal_val, 1)

            grad = m.temperature_gradient
            if isinstance(grad, float) and math.isnan(grad):
                grad = None

            if m.operation_mode == "MANUAL":
                display_status = m.manual_status or "Stop"
            else:
                display_status = get_machine_display_status(m)

            status = display_status
            
            is_new = False
            if past_snapshot_data:
                prior_snap = past_snapshot_data.get(m.code)
                if not prior_snap:
                    # if no data in past snapshot, we assume it was off (so if it's running now, it's new)
                    if status in ['Running', 'HEAT', 'STEADY']:
                        is_new = True
                else:
                    prior_active = False
                    if prior_snap.get('mode') == 'MANUAL':
                        prior_active = prior_snap.get('status') == 'Running'
                    else:
                        prior_active = prior_snap.get('detail') in ['HEAT', 'STEADY']
                    
                    if not prior_active and status in ['Running', 'HEAT', 'STEADY']:
                        is_new = True
            elif m.status_changed_at and (now() - m.status_changed_at).total_seconds() <= 3600:
                # Fallback to status_changed_at if no snapshot is available
                if m.previous_display_status in ['OFF', 'Stop', 'OFFLINE', 'Offline', STATUS_NO_SIGNAL] and status in ['Running', 'HEAT', 'STEADY']:
                    is_new = True
            
            if status == "Running":
                badge_class, tile_class = "status-running", "tile-running"; status_counts["running"] += 1
            elif status in ["Warning", "HEAT"]:
                badge_class, tile_class = "status-warning", "tile-warning"; status_counts["heat"] += 1
            elif status in ["Stop", "OFF"]:
                badge_class, tile_class = "status-stop", "tile-stop"; status_counts["off"] += 1
            elif status == "STEADY":
                badge_class, tile_class = "status-steady", "tile-steady"; status_counts["steady"] += 1
            elif status == "COOL":
                badge_class, tile_class = "status-cool", "tile-cool"; status_counts["cool"] += 1
            elif status in [STATUS_NO_SIGNAL, "OFFLINE", "Offline"]:
                badge_class, tile_class = "status-offline", "tile-offline"; status_counts["off"] += 1
            else:
                badge_class, tile_class = "status-offline", "tile-offline"; status_counts["off"] += 1

            machines_for_group.append({
                "code": m.code,
                "name": m.name or m.code,
                "status": status,
                "badge_class": badge_class,
                "tile_class": tile_class,
                "last_update": localtime(m.last_update) if m.last_update else localtime(now()),
                "temperature": temp,
                "temperature_gradient": grad,
                "operation_mode": m.operation_mode,
                "manual_last_update": localtime(m.last_update) if m.operation_mode == "MANUAL" and m.last_update else None,
                "unit": m.unit_symbol,
                "is_new": is_new,
            })

        total_in_group = len(group_machines)
        status_percentages = {
            k: (v / total_in_group * 100) if total_in_group > 0 else 0
            for k, v in status_counts.items()
        }

        group_panels.append({
            "code": g.code,
            "name": g.name,
            "description": g.description,
            "count": total_in_group,
            "machines": machines_for_group,
            "status_counts": status_counts,
            "status_percentages": status_percentages,
        })

    # ─────────────────────────────────────────────────────────────────
    # 5. Data alarm (dummy — tidak ada DB query)
    # ─────────────────────────────────────────────────────────────────
    alarms = [
        {"time": "07:14:22", "machine": "Line 2 – Mixer",     "code": "A-203", "desc": "Motor overload – arus > 35 A",            "level": "Critical", "level_badge": "critical", "status": "Open",         "status_badge": "open"},
        {"time": "07:02:01", "machine": "Boiler",             "code": "W-105", "desc": "Level feed water rendah",                "level": "Warning",  "level_badge": "warning",  "status": "Acknowledged", "status_badge": "ack"},
        {"time": "06:55:40", "machine": "Line 1 – Extruder",  "code": "I-031", "desc": "Temperatur barrel mendekati batas atas",  "level": "Warning",  "level_badge": "warning",  "status": "Closed",       "status_badge": "closed"},
        {"time": "06:40:11", "machine": "Cooling Tower",      "code": "I-010", "desc": "Flowrate make-up water rendah",           "level": "Info",     "level_badge": "info",     "status": "Closed",       "status_badge": "closed"},
    ]

    profile = OperatorProfile.objects.filter(user=request.user).first()

    context = {
        "now": now(),
        "kpi": kpi,
        "group_panels": group_panels,
        "alarms": alarms,
        "operator_profile": profile,
        "total_steam": total_steam,
        "total_hto": total_hto,
    }

    return render(request, "dashboard.html", context)

def build_home_korlap_payload(request):
    """
    Kalkulasi data telemetri komprehensif untuk Home Koordinator Lapangan.
    Digunakan bersama oleh:
      1. home_korlap (Django Template port 8000)
      2. home_korlap_api (JSON endpoint untuk React JSX port 8002)
    """
    import math
    from collections import defaultdict
    from monitoring.utils.manual_status import get_status_since_info
    from monitoring.api_dashboard import sort_machines_custom

    all_machines = list(
        Machine.objects
        .filter(is_active=True)
        .select_related('group')
    )

    # 1. Sensor utilitas penting (Uap & HTO)
    steam_machine = next((m for m in all_machines if m.code == 'Steam_Pr'), None)
    hto_machine   = next((m for m in all_machines if m.code == 'Oil_Temp'), None)
    steam_value   = round(steam_machine.temperature, 2) if steam_machine and steam_machine.temperature is not None else None
    hto_value     = round(hto_machine.temperature, 1) if hto_machine and hto_machine.temperature is not None else None

    # Pemakaian Uap (ton/jam) & HTO (jt kcal) saat ini
    # Serta hitung jumlah mesin (MC) aktif yang memakai Steam dan HTO
    from monitoring.utils.steam_active import is_steam_active_from_machine
    current_steam_kg = 0.0
    current_hto_cal = 0.0
    steam_mc_count = 0
    hto_mc_count = 0
    total_steam_mc = 0
    total_hto_mc = 0

    for m in all_machines:
        if m.group and m.group.code == 'MC_BOILER':
            continue
        is_running = is_steam_active_from_machine(m)
        has_steam = (m.average_steam_usage or 0) > 0
        has_hto = (m.avg_hto_calories or 0) > 0

        if has_steam:
            total_steam_mc += 1
            if is_running:
                current_steam_kg += (m.average_steam_usage or 0.0)
                steam_mc_count += 1

        if has_hto:
            total_hto_mc += 1
            if is_running:
                current_hto_cal += (m.avg_hto_calories or 0.0)
                hto_mc_count += 1

    steam_ton = round(current_steam_kg / 1000.0, 1)
    steam_usage_str = f"{steam_ton:.1f} ton/jam".replace(".", ",")

    hto_jt = round(current_hto_cal / 1_000_000.0, 1)
    hto_usage_str = f"{hto_jt:.1f} jt kcal".replace(".", ",")

    # 2. Batch Aktif & Batch Terakhir
    active_batches = {
        dp.machine_id: dp 
        for dp in DyeingProcess.objects.filter(is_complete=False).select_related('identity', 'identity__program')
    }
    last_batches = {
        dp.machine_id: dp 
        for dp in DyeingProcess.objects.filter(is_complete=True).order_by('machine_id', '-end_time').distinct('machine_id')
    }

    current_time = now()
    
    # Batas waktu log: mesin heating aktif butuh log sejak heating_start_time,
    # mesin standby/lainnya hanya butuh 30 menit terakhir (cukup untuk raw_machine_logs[-20:]).
    from django.db.models import Q
    recent_cutoff = current_time - timedelta(minutes=30)
    active_heating_machines = [
        dp for dp in active_batches.values()
        if dp.heating_start_time and (current_time - dp.heating_start_time).total_seconds() < 86400
    ]

    if active_heating_machines:
        earliest_heat = min(dp.heating_start_time for dp in active_heating_machines)
        heating_mc_ids = [dp.machine_id for dp in active_heating_machines]
        recent_logs = (
            MachineMinuteLog.objects
            .filter(
                Q(timestamp__gte=recent_cutoff) |
                Q(machine_id__in=heating_mc_ids, timestamp__gte=earliest_heat)
            )
            .values('machine_id', 'temperature', 'timestamp')
            .order_by('machine_id', 'timestamp')
        )
    else:
        recent_logs = (
            MachineMinuteLog.objects
            .filter(timestamp__gte=recent_cutoff)
            .values('machine_id', 'temperature', 'timestamp')
            .order_by('machine_id', 'timestamp')
        )
    logs_by_machine = defaultdict(list)
    for log in recent_logs:
        val = log['temperature']
        if val is not None and not (isinstance(val, float) and math.isnan(val)):
            logs_by_machine[log['machine_id']].append((log['timestamp'], round(val, 1)))

    def downsample_list(lst, max_points=14):
        if len(lst) <= max_points:
            return lst
        step = (len(lst) - 1) / (max_points - 1)
        return [lst[int(round(i * step))] for i in range(max_points)]

    def make_chart_svg(values, width=95, height=38):
        if not values or len(values) < 2:
            return {'points': '', 'area': '', 'last_x': 90, 'last_y': 19, 'has_data': False, 'sampled_temps': []}
        min_val = min(values)
        max_val = max(values)
        if max_val - min_val < 10:
            max_val = min_val + 10
        pts = []
        n = len(values)
        for i, v in enumerate(values):
            x = round((i / (n - 1)) * (width - 10) + 5, 1)
            norm = (v - min_val) / (max_val - min_val)
            norm = max(0.0, min(1.0, norm))
            y = round((height - 8) - (norm * (height - 14)) - 4, 1)
            pts.append((x, y))
        
        pts_str = ' '.join(f'{x},{y}' for x, y in pts)
        first_x, first_y = pts[0]
        last_x, last_y = pts[-1]
        area_d = f'M {first_x},{height-2} L ' + ' L '.join(f'{x},{y}' for x, y in pts) + f' L {last_x},{height-2} Z'
        return {
            'points': pts_str,
            'area': area_d,
            'last_x': last_x,
            'last_y': last_y,
            'has_data': True,
            'min_temp': round(min_val, 1),
            'max_temp': round(max_val, 1),
            'sampled_temps': values,
        }

    def safe_get_identity(dp):
        if not dp:
            return None
        try:
            return dp.identity
        except Exception:
            return None

    status_counts = {"running": 0, "heat": 0, "cool": 0, "steady": 0, "off": 0, "nosignal": 0}
    machines_by_group = defaultdict(list)

    for m in all_machines:
        if m.group and m.group.code == 'MC_BOILER':
            continue

        if m.operation_mode == "MANUAL":
            raw_status = m.manual_status or "Stop"
        else:
            raw_status = get_machine_display_status(m)

        norm_status = (raw_status or "OFF").upper()
        if norm_status in ("STOP", "OFFLINE"):
            norm_status = "OFF"
        elif norm_status in ("NO SIGNAL", "NOSIGNAL"):
            norm_status = "NOSIGNAL"
        elif norm_status == "RUNNING":
            norm_status = "RUNNING"

        if norm_status == "RUNNING":
            status_counts["running"] += 1
        elif norm_status == "HEAT" or raw_status == "Warning":
            status_counts["heat"] += 1
            norm_status = "HEAT"
        elif norm_status == "STEADY":
            status_counts["steady"] += 1
        elif norm_status == "COOL":
            status_counts["cool"] += 1
        elif norm_status == "NOSIGNAL":
            status_counts["nosignal"] += 1
        else:
            status_counts["off"] += 1
            norm_status = "OFF"

        is_active = norm_status in ("HEAT", "STEADY", "COOL", "RUNNING")

        temp = m.temperature
        if isinstance(temp, float) and math.isnan(temp):
            temp = None
        elif temp is not None:
            temp = round(temp, 1)

        grad = m.temperature_gradient
        if isinstance(grad, float) and math.isnan(grad):
            grad = None
        elif grad is not None:
            grad = round(grad, 2)

        grad_icon = "trending_flat"
        grad_direction = "flat"
        grad_display = "-"
        if grad is not None:
            if grad > 0.05:
                grad_icon = "north_east"
                grad_direction = "up"
            elif grad < -0.05:
                grad_icon = "south_east"
                grad_direction = "down"
            grad_display = f"{grad:+.2f} °C/m"

        if norm_status == "HEAT":
            status_subtext = "SEDANG NAIK"
            status_subtext_class = "subtext-heat"
            chart_stroke = "#ba1a1a"
            chart_fill = "rgba(186, 26, 26, 0.2)"
            status_phase_label = "HT Ramp"
        elif norm_status == "STEADY":
            status_subtext = "STABIL / KEEP"
            status_subtext_class = "subtext-steady"
            chart_stroke = "#006591"
            chart_fill = "rgba(57, 184, 253, 0.2)"
            status_phase_label = "Steady Hold"
        elif norm_status == "COOL":
            status_subtext = "PENDINGINAN"
            status_subtext_class = "subtext-cool"
            chart_stroke = "#006591"
            chart_fill = "rgba(0, 101, 145, 0.2)"
            status_phase_label = "Cool Down"
        elif norm_status == "RUNNING":
            status_subtext = "BERJALAN"
            status_subtext_class = "subtext-running"
            chart_stroke = "#009668"
            chart_fill = "rgba(0, 150, 104, 0.2)"
            status_phase_label = "Circulation"
        elif norm_status == "NOSIGNAL":
            status_subtext = "TIDAK ADA SINYAL"
            status_subtext_class = "subtext-off"
            chart_stroke = "#76777d"
            chart_fill = "rgba(118, 119, 125, 0.15)"
            status_phase_label = "Offline"
        else:
            status_subtext = "STANDBY"
            status_subtext_class = "subtext-off"
            chart_stroke = "#76777d"
            chart_fill = "rgba(118, 119, 125, 0.15)"
            status_phase_label = "Idle Drain"

        progress_pct = max(4, min(100, int((temp / 130.0) * 100))) if temp is not None else 0

        active_batch = active_batches.get(m.id)
        last_batch = last_batches.get(m.id)
        since_info = get_status_since_info(m, active_batch)
        
        time_badge = ""
        time_subtext = ""
        time_type = "default"
        batch_num = None
        program_name = None
        artikel_kain = None
        nomor_order = None

        raw_machine_logs = logs_by_machine.get(m.id, [])
        cycle_temps = []
        cycle_label = "Standby Off"

        if active_batch:
            batch_num = active_batch.batch_number
            ident = safe_get_identity(active_batch)
            if ident:
                batch_num = ident.batch or active_batch.batch_number
                artikel_kain = ident.artikel_kain
                nomor_order = ident.nomor_order
                if ident.program:
                    program_name = ident.program.nama

            # SEMUA DIHITUNG DARI REAL HEAT (heating_start_time), BUKAN START BATCH!
            if active_batch.heating_start_time:
                heat_start = localtime(active_batch.heating_start_time)
                dur_mins = max(0, int((current_time - active_batch.heating_start_time).total_seconds() // 60))
                hh = dur_mins // 60
                mm = dur_mins % 60
                heat_dur_str = f"{hh}j {mm}m" if hh > 0 else f"{mm}m"
                cycle_temps = [val for ts, val in raw_machine_logs if ts >= active_batch.heating_start_time]

                if norm_status == "HEAT":
                    cycle_label = f"Heat {heat_dur_str}"
                    time_badge = f"Heat: {dur_mins} mnt (Mulai {heat_start.strftime('%H:%M')})"
                    time_subtext = f"Mulai {heat_start.strftime('%H:%M')}"
                    time_type = "heat_active"
                elif active_batch.real_heating_duration and active_batch.real_heating_duration > 0:
                    cycle_label = f"Aktif {heat_dur_str}"
                    time_badge = f"Real Heat: {round(active_batch.real_heating_duration, 0):.0f} mnt (Mulai {heat_start.strftime('%H:%M')})"
                    time_subtext = f"Mulai {heat_start.strftime('%H:%M')}"
                    time_type = "heat_done"
                else:
                    cycle_label = f"Aktif {heat_dur_str}"
                    time_badge = f"Heat: {dur_mins} mnt (Mulai {heat_start.strftime('%H:%M')})"
                    time_subtext = f"Mulai {heat_start.strftime('%H:%M')}"
                    time_type = "heat_done"
            else:
                # Belum mulai pemanasan Real Heat
                cycle_temps = [val for ts, val in raw_machine_logs[-20:]]
                cycle_label = "Menunggu Heat"
                time_badge = "Menunggu Real Heat"
                time_subtext = "Belum mulai pemanasan"
                time_type = "start_waiting"

        elif m.operation_mode == "MANUAL" and is_active:
            # Mesin manual yang sedang berjalan (seperti Ehwa / Stenter)
            dur_mins = since_info.get("duration_minutes") or 0
            since_disp = since_info.get("active_since") or since_info.get("status_since_display") or "Hari ini"
            ch = dur_mins // 60
            cm = dur_mins % 60
            dur_str = f"{ch}j {cm}m" if ch > 0 else f"{cm}m"
            cycle_label = f"Aktif {dur_str}"
            time_badge = f"Nyala {since_disp} ({dur_mins} mnt)"
            time_subtext = f"{dur_mins} mnt lalu"
            time_type = "manual_running"
            cycle_temps = [val for ts, val in raw_machine_logs[-20:]]

        elif is_active:
            # Mesin auto yang aktif berjalan tanpa batch di database
            dur_mins = since_info.get("duration_minutes") or 0
            since_disp = since_info.get("active_since") or since_info.get("status_since_display")
            ch = dur_mins // 60
            cm = dur_mins % 60
            dur_str = f"{ch}j {cm}m" if ch > 0 else f"{cm}m"
            cycle_label = f"Aktif {dur_str}"
            time_badge = f"Aktif {since_disp} ({dur_mins} mnt)" if since_disp else "Mesin Berjalan"
            time_subtext = f"{dur_mins} mnt lalu" if dur_mins else "Aktif"
            time_type = "active_no_batch"
            cycle_temps = [val for ts, val in raw_machine_logs[-20:]]

        elif last_batch and last_batch.end_time and (current_time - last_batch.end_time).total_seconds() < 129600:
            cycle_temps = [val for ts, val in raw_machine_logs[-20:]]
            cycle_label = "Standby Off"
            time_badge = "Standby Off"
            time_subtext = ""
            time_type = "offline"

        else:
            cycle_temps = [val for ts, val in raw_machine_logs[-20:]]
            cycle_label = "Standby Off"
            time_badge = "Standby Off"
            time_subtext = ""
            time_type = "offline"

        sampled_temps = downsample_list(cycle_temps, 14)
        if temp is not None and (not sampled_temps or abs(sampled_temps[-1] - temp) > 0.1):
            sampled_temps.append(temp)
            sampled_temps = downsample_list(sampled_temps, 14)

        chart_svg = make_chart_svg(sampled_temps, width=95, height=38)

        grp_code = m.group.code if m.group else "MC"
        machine_name = m.name or m.code

        subtitle_parts = []
        if batch_num:
            subtitle_parts.append(f"#{batch_num}")
        if artikel_kain:
            subtitle_parts.append(artikel_kain)
        elif program_name:
            subtitle_parts.append(program_name)
        elif not batch_num:
            if m.operation_mode == "MANUAL" and is_active:
                since_disp = since_info.get("active_since") or "Aktif"
                subtitle_parts.append(f"Operasional Manual · Nyala {since_disp}")
            elif is_active:
                subtitle_parts.append("Proses Berjalan (Non-Batch)")
            else:
                subtitle_parts.append("Kosong (Menunggu Kain)")
        batch_subtitle = " · ".join(subtitle_parts)

        # Perkiraan pemakaian energi untuk mesin aktif (ton/jam atau jt kcal)
        energy_parts = []
        if is_active:
            if (m.average_steam_usage or 0) > 0:
                s_ton = round(m.average_steam_usage / 1000.0, 1)
                energy_parts.append(f"{s_ton:.1f} ton/jam".replace(".", ","))
            if (m.avg_hto_calories or 0) > 0:
                h_jt = round(m.avg_hto_calories / 1_000_000.0, 1)
                energy_parts.append(f"{h_jt:.1f} jt kcal".replace(".", ","))
        energy_usage_str = " · ".join(energy_parts) if energy_parts else None

        machines_by_group[m.group_id].append({
            "id": m.id,
            "code": m.code,
            "name": machine_name,
            "display_title": f"{machine_name} ({grp_code})",
            "group_code": grp_code,
            "status": norm_status,
            "is_active": is_active,
            "energy_usage": energy_usage_str,
            "has_active_batch": bool(active_batch),
            "temperature": temp,
            "gradient": grad,
            "grad_icon": grad_icon,
            "grad_direction": grad_direction,
            "grad_display": grad_display,
            "status_subtext": status_subtext,
            "status_subtext_class": status_subtext_class,
            "status_phase_label": status_phase_label,
            "operation_mode": m.operation_mode,
            "is_manual": m.operation_mode == "MANUAL",
            "active_since": since_info.get("active_since"),
            "status_since_display": since_info.get("status_since_display"),
            "duration_minutes": since_info.get("duration_minutes"),
            "can_toggle": m.operation_mode == "MANUAL",
            "time_badge": time_badge,
            "time_subtext": time_subtext,
            "time_type": time_type,
            "chart": chart_svg,
            "chart_stroke": chart_stroke,
            "chart_fill": chart_fill,
            "cycle_label": cycle_label,
            "batch_number": batch_num,
            "artikel_kain": artikel_kain,
            "nomor_order": nomor_order,
            "program_name": program_name,
            "batch_subtitle": batch_subtitle,
            "progress_pct": progress_pct,
        })

    groups = list(MachineGroup.objects.exclude(code='MC_BOILER').order_by("code"))
    preferred_order = ['JR PRC', 'JD PRC', 'JD PRT', 'PRC CNT', 'PRT CNT']
    
    def group_sort_key(g):
        for idx, pref in enumerate(preferred_order):
            if pref in (g.code or '') or pref in (g.name or ''):
                return idx
        return 99
        
    groups.sort(key=group_sort_key)

    group_panels = []
    total_active_all = 0
    total_machines_all = 0

    group_descriptions = {
        'JD PRC': 'Vessel Bertekanan Tinggi (High Temperature Jet 135°C Max)',
        'JR PRC': 'Atmospheric & Tension Roller Units (Kain Tenun Cotton & Rayon)',
        'JD PRT': 'High Speed Dyeing Polyester Continuous & Semi-Continuous',
        'PRC CNT': 'Continuous Processing Pre-treatment & Mercerizing Line',
        'PRT CNT': 'Printing Continuous Washer & Finishing Steamers',
    }

    for g in groups:
        g_machines = machines_by_group.get(g.id, [])
        if not g_machines:
            continue
        
        # Urutkan mesin ascending secara natural berdasarkan kode mesin (misal JD_01 s.d. JD_19)
        import re
        def natural_code_key(item):
            code = item.get('code', '')
            return [int(part) if part.isdigit() else part.lower() for part in re.split(r'(\d+)', code or '')]
        g_machines.sort(key=natural_code_key)
        
        active_in_group = sum(1 for m in g_machines if m["is_active"])
        synced_in_group = sum(1 for m in g_machines if m.get("status") != "NOSIGNAL")
        total_in_group = len(g_machines)
        total_active_all += active_in_group
        total_machines_all += total_in_group

        group_panels.append({
            "code": g.code,
            "name": g.name,
            "synced_count": synced_in_group,
            "active_count": active_in_group,
            "total_count": total_in_group,
            "machines": g_machines,
        })

    profile = OperatorProfile.objects.filter(user=request.user).first() if request.user.is_authenticated else None
    from monitoring.utils.shift_time import get_current_operational_shift
    shift_info = get_current_operational_shift(current_time)

    return {
        "now": localtime(current_time).strftime("%d %b %Y · %H:%M WIB"),
        "now_iso": current_time.isoformat(),
        "shift_name": shift_info["name"],
        "shift_num": shift_info["num"],
        "shift_tag": shift_info["tag"],
        "shift_window": shift_info["window"],
        "operator_shift": profile.shift.name if profile and profile.shift else None,
        "steam_pressure": steam_value,
        "steam_usage": steam_usage_str,
        "steam_mc_count": steam_mc_count,
        "total_steam_mc": total_steam_mc,
        "oil_temp": hto_value,
        "hto_usage": hto_usage_str,
        "hto_mc_count": hto_mc_count,
        "total_hto_mc": total_hto_mc,
        "total_active": total_active_all,
        "total_machines": total_machines_all,
        "status_counts": status_counts,
        "group_panels": group_panels,
        "operator_name": profile.user.get_full_name() or profile.user.username if profile and profile.user else "Operator Shift",
    }


@login_required
@position_required('dashboard')
def home_korlap(request):
    data = build_home_korlap_payload(request)
    profile = OperatorProfile.objects.filter(user=request.user).first()
    context = {
        "now": now(),
        "shift_name": data.get("shift_name"),
        "steam_pressure": data["steam_pressure"],
        "oil_temp": data["oil_temp"],
        "total_active": data["total_active"],
        "total_machines": data["total_machines"],
        "status_counts": data["status_counts"],
        "group_panels": data["group_panels"],
        "operator_profile": profile,
    }
    return render(request, "home_korlap.html", context)


def home_korlap_api(request):
    """
    JSON API endpoint untuk Port 8002 React /home
    """
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Unauthorized', 'detail': 'Sesi belum aktif atau telah kedaluwarsa.'}, status=401)
    data = build_home_korlap_payload(request)
    return JsonResponse(data)


@login_required
def machine_status_api(request):
    machines = Machine.objects.filter(is_active=True).order_by("code")

    from .models import MachineStatusSnapshot, MachineCalibration
    n = timezone.now()
    one_hour_ago = n - timedelta(hours=1)
    past_snapshot = MachineStatusSnapshot.objects.filter(timestamp__lte=one_hour_ago).order_by('-timestamp').first()
    past_snapshot_data = past_snapshot.snapshot_data if past_snapshot else {}

    # Ambil semua master kalibrasi aktif
    active_calibrations = {c.machine_id: c for c in MachineCalibration.objects.filter(is_active=True)}

    data = []
    for m in machines:
        temp = m.temperature
        if isinstance(temp, float) and math.isnan(temp):
            temp = None
        elif temp is not None and m.id in active_calibrations:
            # Terapkan rumus kalibrasi: y = Ax^2 + Bx + C
            cal = active_calibrations[m.id]
            cal_val = (cal.a_coeff * temp ** 2) + (cal.b_coeff * temp) + cal.c_coeff
            temp = round(cal_val, 1)

        grad = m.temperature_gradient
        if isinstance(grad, float) and math.isnan(grad):
            grad = None

        # Determine which status to return based on operation mode + signal freshness
        display_status = get_machine_display_status(m, now=n)
            
        is_new = False
        if past_snapshot_data:
            prior_snap = past_snapshot_data.get(m.code)
            if not prior_snap:
                if display_status in ['Running', 'HEAT', 'STEADY']:
                    is_new = True
            else:
                prior_active = False
                if prior_snap.get('mode') == 'MANUAL':
                    prior_active = prior_snap.get('status') == 'Running'
                else:
                    prior_active = prior_snap.get('detail') in ['HEAT', 'STEADY']
                
                if not prior_active and display_status in ['Running', 'HEAT', 'STEADY']:
                    is_new = True
        elif m.status_changed_at and (n - m.status_changed_at).total_seconds() <= 3600:
            if m.previous_display_status in ['OFF', 'Stop', 'OFFLINE', 'Offline', STATUS_NO_SIGNAL] and display_status in ['Running', 'HEAT', 'STEADY']:
                is_new = True
        
        data.append({
            "code": m.code,
            "name": m.name or m.code,
            "status": display_status,
            "last_status": m.last_status or "Unknown",
            "last_thermal_status": m.last_thermal_status or "OFFLINE",
            "last_update": localtime(m.last_update).strftime("%H:%M:%S") if m.last_update else "",
            "last_valid_reading_at": localtime(m.last_valid_reading_at).strftime("%H:%M:%S") if m.last_valid_reading_at else "",
            "temperature": temp,
            "temperature_gradient": grad,
            "operation_mode": m.operation_mode,
            "is_new": is_new,
            "is_signal_stale": display_status == STATUS_NO_SIGNAL,
        })

    return JsonResponse({"machines": data})


def login_view(request):
    logo = CompanyProfile.objects.first()
    return render(request, "login.html", {"logo": logo})

class CustomLoginView(LoginView):
    template_name = "login.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # pastikan logo perusahaan ikut dikirim ke template
        context["company_profile"] = CompanyProfile.objects.first()
        return context


def _is_safe_internal_next(next_url):
    """Path internal yang aman untuk redirect setelah auto-login (bukan open redirect)."""
    if not next_url:
        return False
    if not next_url.startswith("/"):
        return False
    if next_url.startswith("//") or "\\" in next_url:
        return False
    path_only = next_url.split("?", 1)[0]
    if path_only == "/login" or path_only.startswith("/login/"):
        return False
    return True


def _render_auto_login_error(request, message, username=""):
    import urllib.parse
    params = urllib.parse.urlencode({
        "error": message,
        "username": username or request.GET.get("username", "")
    })
    return redirect(f"/login?{params}")


@require_GET
def url_auto_login(request, username, password):
    """
    Auto-login via GET /login/{username}/{password}/ untuk integrasi aplikasi internal.
    Django path converter sudah percent-decode; jangan unquote lagi (double-encode harus gagal).
    """
    try:
        username = (username or "").strip()
        password = (password or "").rstrip("/")

        if not username or not password:
            return _render_auto_login_error(
                request, "Username dan password wajib diisi.", username=username
            )

        user = authenticate(request, username=username, password=password)
        if user is None:
            existing = User.objects.filter(username=username).first()
            if existing is None:
                return _render_auto_login_error(request, "Username tidak ditemukan.", username=username)
            if not existing.is_active:
                return _render_auto_login_error(
                    request, "Akun dinonaktifkan. Hubungi admin.", username=username
                )
            return _render_auto_login_error(request, "Password salah.", username=username)

        login(request, user)

        next_url = request.GET.get("next")
        if _is_safe_internal_next(next_url):
            return redirect(next_url)
        return redirect("/home")
    except Exception:
        return _render_auto_login_error(
            request, "Login otomatis gagal. Silakan login manual.", username=username
        )

@login_required
@position_required('manual_input')
def manual_machine_usage(request):
    # Semua mesin aktif (MANUAL dan AUTO untuk preview)
    all_active_machines = Machine.objects.filter(is_active=True)
    
    # Separate MANUAL untuk POST handling
    manual_machines = all_active_machines.filter(operation_mode="MANUAL")

    # Group yang punya mesin aktif (MANUAL atau AUTO)
    # EXCLUDE groups dengan process_type ENERGY_SOURCE
    groups = (
        MachineGroup.objects
        .filter(machine__in=all_active_machines)
        .exclude(process_type="ENERGY_SOURCE")  # Exclude energy source machines
        .distinct()
        .prefetch_related(
            Prefetch(
                "machine_set",
                # Include both MANUAL and AUTO, sorted: MANUAL first, then AUTO
                queryset=all_active_machines.order_by("operation_mode", "code"),
            )
        )
    )

    if request.method == "POST":
        # Import logging utility
        from monitoring.utils.activity_logger import log_activity
        from monitoring.utils.manual_status import (
            apply_manual_status_change,
            MANUAL_STATUS_RUNNING,
            MANUAL_STATUS_STOP,
            SOURCE_MESIN_AKTIF_VIEW,
        )
        
        ids_on = set(request.POST.getlist("machines_on"))
        changes = []

        for m in manual_machines:
            old_status = m.manual_status
            new_status = MANUAL_STATUS_RUNNING if str(m.id) in ids_on else MANUAL_STATUS_STOP
            if apply_manual_status_change(m, new_status, SOURCE_MESIN_AKTIF_VIEW, request.user):
                changes.append({
                    'code': m.code,
                    'name': m.name,
                    'old': old_status,
                    'new': new_status
                })
        
        # Log all changes in one entry
        if changes:
            change_summary = ", ".join([f"{c['code']} ({c['old']}→{c['new']})" for c in changes])
            log_activity(
                request=request,
                action='UPDATE',
                description=f"Changed machine status: {change_summary}",
                additional_data={
                    'changes': changes,
                    'total_changed': len(changes),
                    'operation': 'machine_status_update'
                }
            )

        messages.success(request, "Status mesin (mode manual) berhasil diperbarui.")
        return redirect("manual_machine_usage")
    
    # Calculate totals for ALL active machines (both AUTO and MANUAL)
    total_steam = 0.0
    total_hto = 0.0
    
    for machine in all_active_machines:
        if machine.group and machine.group.process_type == "ENERGY_SOURCE":
            continue
        from monitoring.utils.steam_active import is_steam_active_from_machine
        is_active = is_steam_active_from_machine(machine)
        
        if is_active:
            # Add to totals (values are per hour)
            total_steam += (machine.average_steam_usage or 0.0)
            total_hto += (machine.avg_hto_calories or 0.0)
    
    # Prepare machine data for JavaScript (preview calculations)
    # Include both MANUAL and AUTO for preview
    machines_data = []
    for m in all_active_machines:
        if m.group and m.group.process_type == "ENERGY_SOURCE":
            continue
        machines_data.append({
            'id': m.id,
            'code': m.code,
            'name': m.name,
            'steam': m.average_steam_usage or 0.0,
            'hto': m.avg_hto_calories or 0.0,
            'operation_mode': m.operation_mode,
            'is_running': is_steam_active_from_machine(m),
        })
    
    # [K7] Kode DEBUG dihapus — tidak diperlukan di production
    # Menghilangkan 5+ query .count() + print() yang dieksekusi setiap kali halaman ini dibuka
    
    context = {
        "groups": groups,
        "machines": manual_machines,
        "machines_data": machines_data,
        "total_steam": total_steam,
        "total_hto": total_hto,
    }

    return render(
        request,
        "manual_machine_usage.html",
        context,
    )

def some_view(request):
    now = timezone.now()
    cutoff = now - timedelta(hours=1)

    logs = (
        MachineMinuteLog.objects
        .filter(timestamp__gte=cutoff)
        .select_related("machine")
        .order_by("timestamp")
    )
    # tinggal olah ke JSON untuk Chart.js, dsb

@login_required
def machine_chart_api(request, code):
    try:
        machine = Machine.objects.get(code=code)
    except Machine.DoesNotExist:
        return JsonResponse({"error": "Machine not found"}, status=404)

    try:
        hours = max(1, min(72, int(request.GET.get('hours', 6))))
    except (ValueError, TypeError):
        hours = 6

    now_t = timezone.now()
    cutoff = now_t - timedelta(hours=hours)

    # Gunakan .only() untuk mengurangi data yang dibaca dari DB
    logs = (
        MachineMinuteLog.objects
        .filter(machine=machine, timestamp__gte=cutoff)
        .only('timestamp', 'temperature')
        .order_by("timestamp")
    )

    timestamps = [
        localtime(l.timestamp).strftime("%H:%M")
        for l in logs
    ]
    temperatures = [
        round(l.temperature, 1) if l.temperature is not None else None
        for l in logs
    ]

    # Current machine display status
    if machine.operation_mode == "MANUAL":
        m_status = machine.manual_status or "OFF"
    else:
        m_status = get_machine_display_status(machine)

    return JsonResponse({
        "machine": machine.code,
        "name": machine.name or machine.code,
        "unit": machine.unit_symbol or "°C",
        "operation_mode": machine.operation_mode,
        "timestamps": timestamps,
        "labels": timestamps,
        "temperatures": temperatures,
        "current_temperature": round(machine.temperature, 1) if machine.temperature is not None else None,
        "status": m_status,
        "hours": hours,
    })

@login_required
def kpi_realtime_api(request):
    steam = Machine.objects.filter(code="Steam_Pr", is_active=True).first()
    hto = Machine.objects.filter(code="Oil_Temp", is_active=True).first()

    steam_value = steam.temperature if steam and steam.temperature is not None else None
    hto_value = hto.temperature if hto and hto.temperature is not None else None

    return JsonResponse({
        "steam": steam_value,
        "hto": hto_value,
    })




@login_required
def steam_usage_history_api(request):
    """
    API endpoint to get steam usage and pressure history.
    Uses Data Aggregation (Rollups) for longer time ranges to prevent server crash.
    Interval adjusts based on hours to return exactly 25 data points.
    """
    from .models import MachineStatusSnapshot, PlantHourlySummary, PlantDailySummary
    from collections import defaultdict
    
    hours = int(request.GET.get('hours', 24))
    end_time = timezone.now()
    start_time = end_time - timedelta(hours=hours)

    # ─── PROPORTIONAL TARGET_POINTS ──────────────────────────────────────────
    # 1H  → 1 titik/menit = 60
    # 24H → 1 titik/10mnt = 144
    # 7D  → 1 titik/jam   = 168
    # 30D → 1 titik/6jam  = 120
    # YTD → 1 titik/3hari = ~120
    if hours <= 1:
        TARGET_POINTS = 60
    elif hours <= 24:
        TARGET_POINTS = 144       # every ~10 minutes
    elif hours <= 168:
        TARGET_POINTS = min(hours, 168)  # 1 per hour
    else:
        TARGET_POINTS = 120

    total_minutes = hours * 60
    interval_minutes = total_minutes / TARGET_POINTS

    timestamps = []
    raw_timestamps = []
    steam_totals = []
    steam_pressures = []
    machine_counts = []

    # ─── ROUTING SUMBER DATA BERDASARKAN RENTANG WAKTU ──────────────────────
    if hours > 168:
        # > 1 Minggu (contoh: 30 Hari, YTD) -> Gunakan PlantDailySummary
        summaries = PlantDailySummary.objects.filter(
            timestamp__gte=start_time.date(),
            timestamp__lte=end_time.date()
        ).order_by('timestamp')
        
        # Aggregate ke bucket
        bucket_data = defaultdict(lambda: {'steam': 0.0, 'press': 0.0, 'machines': 0, 'count': 0})
        for s in summaries:
            # Cari bucket index (berdasarkan jam 00:00)
            dt = timezone.make_aware(timezone.datetime.combine(s.timestamp, timezone.datetime.min.time()))
            time_diff = (dt - start_time).total_seconds() / 60
            bucket_idx = int(time_diff / interval_minutes)
            if bucket_idx < 0: bucket_idx = 0
            if bucket_idx >= TARGET_POINTS: bucket_idx = TARGET_POINTS - 1
            
            bucket_data[bucket_idx]['steam'] += s.total_steam_usage
            bucket_data[bucket_idx]['press'] += s.avg_steam_pressure
            bucket_data[bucket_idx]['machines'] += s.machine_count
            bucket_data[bucket_idx]['count'] += 1
            
        for i in range(TARGET_POINTS):
            interval_start = start_time + timedelta(minutes=i * interval_minutes)
            if interval_start > end_time: break
            timestamps.append(localtime(interval_start).strftime("%Y-%m-%d"))
            raw_timestamps.append(interval_start.isoformat())
            
            b = bucket_data.get(i)
            if b and b['count'] > 0:
                steam_totals.append(round(b['steam'] / b['count'], 2))
                steam_pressures.append(round(b['press'] / b['count'], 2))
                machine_counts.append(round(b['machines'] / b['count']))
            else:
                steam_totals.append(0.0)
                steam_pressures.append(None)
                machine_counts.append(0)

    elif hours > 24:
        # > 24 Jam s/d 7 Hari -> Gunakan PlantHourlySummary
        summaries = PlantHourlySummary.objects.filter(
            timestamp__gte=start_time,
            timestamp__lte=end_time
        ).order_by('timestamp')
        
        bucket_data = defaultdict(lambda: {'steam': 0.0, 'press': 0.0, 'machines': 0, 'count': 0})
        for s in summaries:
            time_diff = (s.timestamp - start_time).total_seconds() / 60
            bucket_idx = int(time_diff / interval_minutes)
            if bucket_idx < 0: bucket_idx = 0
            if bucket_idx >= TARGET_POINTS: bucket_idx = TARGET_POINTS - 1
            
            bucket_data[bucket_idx]['steam'] += s.total_steam_usage
            bucket_data[bucket_idx]['press'] += s.avg_steam_pressure
            bucket_data[bucket_idx]['machines'] += s.machine_count
            bucket_data[bucket_idx]['count'] += 1
            
        for i in range(TARGET_POINTS):
            interval_start = start_time + timedelta(minutes=i * interval_minutes)
            if interval_start > end_time: break
            timestamps.append(localtime(interval_start).strftime("%d %b %H:%M"))
            raw_timestamps.append(interval_start.isoformat())
            
            b = bucket_data.get(i)
            if b and b['count'] > 0:
                steam_totals.append(round(b['steam'] / b['count'], 2))
                steam_pressures.append(round(b['press'] / b['count'], 2))
                machine_counts.append(round(b['machines'] / b['count']))
            else:
                steam_totals.append(0.0)
                steam_pressures.append(None)
                machine_counts.append(0)
                
    else:
        # <= 24 Jam -> Gunakan data Realtime (MachineStatusSnapshot & MinuteLog)
        snapshots = MachineStatusSnapshot.objects.filter(
            timestamp__gte=start_time,
            timestamp__lte=end_time
        ).order_by('timestamp')
        
        all_machines = Machine.objects.filter(
            is_active=True, average_steam_usage__gt=0
        ).select_related('group')
        machines_dict = {m.code: m for m in all_machines}
        
        # Collect unique group names (ordered)
        group_names_ordered = []
        seen_groups = set()
        for m in all_machines:
            gname = m.group.name if m.group else "Lain-lain"
            if gname not in seen_groups:
                group_names_ordered.append(gname)
                seen_groups.add(gname)
        
        # interval_data: key=interval_key, val={'steam_total', 'count', 'groups': {gname: total_count}}
        interval_data = defaultdict(lambda: {
            'steam_total': 0.0, 'count': 0,
            'groups': defaultdict(int)
        })
        
        for snapshot in snapshots:
            time_diff = (snapshot.timestamp - start_time).total_seconds() / 60
            bucket_index = int(time_diff / interval_minutes)
            bucket_start = start_time + timedelta(minutes=bucket_index * interval_minutes)
            interval_key = bucket_start.replace(second=0, microsecond=0)
            
            steam_total = 0.0
            for machine_code, snap_data in snapshot.snapshot_data.items():
                machine = machines_dict.get(machine_code)
                if machine:  # already filtered to steam-using machines
                    is_active = False
                    from monitoring.utils.steam_active import is_steam_active_from_snapshot
                    is_active = is_steam_active_from_snapshot(snap_data)
                    
                    if is_active:
                        steam_total += (machine.average_steam_usage or 0.0)
                        gname = machine.group.name if machine.group else "Lain-lain"
                        interval_data[interval_key]['groups'][gname] += 1
            
            interval_data[interval_key]['steam_total'] += steam_total
            interval_data[interval_key]['count'] += 1
        
        steam_pr_logs = MachineMinuteLog.objects.filter(
            machine__code="Steam_Pr",
            timestamp__gte=start_time,
            timestamp__lte=end_time
        ).order_by('timestamp')
        
        pressure_by_interval = defaultdict(lambda: {'total': 0.0, 'count': 0})
        for log in steam_pr_logs:
            if log.temperature is not None:
                time_diff = (log.timestamp - start_time).total_seconds() / 60
                bucket_index = int(time_diff / interval_minutes)
                bucket_start = start_time + timedelta(minutes=bucket_index * interval_minutes)
                interval_key = bucket_start.replace(second=0, microsecond=0)
                
                pressure_by_interval[interval_key]['total'] += log.temperature
                pressure_by_interval[interval_key]['count'] += 1

        # Build per-group count arrays (parallel to timestamps)
        group_count_arrays = {g: [] for g in group_names_ordered}

        for i in range(TARGET_POINTS):
            interval_start = start_time + timedelta(minutes=i * interval_minutes)
            interval_key = interval_start.replace(second=0, microsecond=0)
            # Do not go beyond current time
            if interval_start > end_time: break
            
            idata = interval_data.get(interval_key, {'steam_total': 0, 'count': 0, 'groups': {}})
            n = idata['count'] or 1  # avoid div by zero
            avg_steam = idata['steam_total'] / n if idata['count'] > 0 else 0.0
            
            # Total active machines this bucket
            total_active = sum(idata['groups'].values())
            avg_machines = round(total_active / n) if idata['count'] > 0 else 0

            # Per-group averages
            for g in group_names_ordered:
                raw_count = idata['groups'].get(g, 0)
                group_count_arrays[g].append(round(raw_count / n) if idata['count'] > 0 else 0)
            
            pressure_data = pressure_by_interval.get(interval_key, {'total': 0, 'count': 0})
            avg_pressure = pressure_data['total'] / pressure_data['count'] if pressure_data['count'] > 0 else None
            
            fmt = "%H:%M" if hours <= 24 else "%d %b %H:%M"
            timestamps.append(localtime(interval_key).strftime(fmt))
            raw_timestamps.append(interval_key.isoformat())
            steam_totals.append(round(avg_steam, 2))
            steam_pressures.append(round(avg_pressure, 2) if avg_pressure is not None else None)
            machine_counts.append(avg_machines)

        # ── Trim trailing empty buckets (no data yet) from the tail ──────────
        while (len(timestamps) > 1
               and steam_totals[-1] == 0.0
               and steam_pressures[-1] is None):
            timestamps.pop()
            raw_timestamps.pop()
            steam_totals.pop()
            steam_pressures.pop()
            machine_counts.pop()
            for g in group_names_ordered:
                if group_count_arrays[g]:
                    group_count_arrays[g].pop()

    return JsonResponse({
        "timestamps": timestamps,
        "raw_timestamps": raw_timestamps,
        "steam_totals": steam_totals,
        "steam_pressures": steam_pressures,
        "machine_counts": machine_counts,
        "machine_groups": group_names_ordered if 'group_names_ordered' in dir() else [],
        "machine_group_counts": group_count_arrays if 'group_count_arrays' in dir() else {},
        "period": f"{hours}h",
        "interval_minutes": round(interval_minutes, 1),
        "count": len(timestamps)
    })


@login_required
def hto_usage_history_api(request):
    """
    API endpoint to get HTO usage and oil temperature history.
    Currently supports up to 24 hours (snapshot-based).
    """
    from .models import MachineStatusSnapshot, MachineMinuteLog, Machine
    from collections import defaultdict
    from django.utils.timezone import localtime
    from datetime import timedelta
    from django.utils import timezone
    from django.http import JsonResponse, Http404
    
    hours = int(request.GET.get('hours', 24))
    end_time = timezone.now()
    start_time = end_time - timedelta(hours=hours)

    TARGET_POINTS = 144
    if hours <= 1:
        TARGET_POINTS = 60
    elif hours <= 24:
        TARGET_POINTS = 144
    else:
        TARGET_POINTS = 144
        start_time = end_time - timedelta(hours=24)
        hours = 24

    total_minutes = hours * 60
    interval_minutes = total_minutes / TARGET_POINTS

    # 1. Query suhu oli HTO
    hto_oil_logs = MachineMinuteLog.objects.filter(
        machine__code="Oil_Temp",
        timestamp__gte=start_time, timestamp__lte=end_time
    ).order_by('timestamp')

    hto_oil_by_interval = defaultdict(lambda: {'total': 0.0, 'count': 0})
    for log in hto_oil_logs:
        if log.temperature is not None:
            time_diff = (log.timestamp - start_time).total_seconds() / 60
            bucket_idx = int(time_diff / interval_minutes)
            bucket_start = start_time + timedelta(minutes=bucket_idx * interval_minutes)
            key = bucket_start.replace(second=0, microsecond=0)
            hto_oil_by_interval[key]['total'] += log.temperature
            hto_oil_by_interval[key]['count'] += 1

    # 2. Semua mesin dengan HTO
    all_hto_machines = Machine.objects.filter(
        is_active=True, avg_hto_calories__gt=0
    ).select_related('group')
    hto_machines_dict = {m.code: m for m in all_hto_machines}

    hto_group_names = []
    seen_groups = set()
    for m in all_hto_machines:
        gname = m.group.name if m.group else "Lain-lain"
        if gname not in seen_groups:
            hto_group_names.append(gname)
            seen_groups.add(gname)

    # 3. Iterate snapshots
    snapshots = MachineStatusSnapshot.objects.filter(
        timestamp__gte=start_time, timestamp__lte=end_time
    ).order_by('timestamp')

    hto_interval_data = defaultdict(lambda: {
        'hto_total': 0.0, 'count': 0, 'groups': defaultdict(int)
    })

    for snapshot in snapshots:
        time_diff = (snapshot.timestamp - start_time).total_seconds() / 60
        bucket_idx = int(time_diff / interval_minutes)
        bucket_start = start_time + timedelta(minutes=bucket_idx * interval_minutes)
        interval_key = bucket_start.replace(second=0, microsecond=0)

        hto_total = 0.0
        for machine_code, snap_data in snapshot.snapshot_data.items():
            if machine_code == "_energy_sources":
                continue
            machine = hto_machines_dict.get(machine_code)
            if not machine:
                continue

            detail = snap_data.get('detail', '')
            gradient = snap_data.get('gradient')
            mode = snap_data.get('mode', '')
            has_valid_gradient = gradient is not None and gradient > -0.1

            if mode == 'MANUAL':
                is_active = snap_data.get('status') == 'Running'
            elif detail == 'HEAT':
                is_active = has_valid_gradient
            elif detail == 'STEADY':
                temp = snap_data.get('temperature')
                is_active = has_valid_gradient and temp is not None and temp >= 90.0
            else:
                is_active = False

            if is_active:
                hto_total += (machine.avg_hto_calories or 0.0)
                gname = machine.group.name if machine.group else "Lain-lain"
                hto_interval_data[interval_key]['groups'][gname] += 1

        hto_interval_data[interval_key]['hto_total'] += hto_total
        hto_interval_data[interval_key]['count'] += 1

    # 4. Build arrays
    timestamps = []
    hto_totals = []
    hto_oil_temps = []
    machine_counts = []
    group_count_arrays = {g: [] for g in hto_group_names}

    for i in range(TARGET_POINTS):
        interval_start = start_time + timedelta(minutes=i * interval_minutes)
        if interval_start > end_time:
            break
        interval_key = interval_start.replace(second=0, microsecond=0)

        idata = hto_interval_data.get(interval_key, {'hto_total': 0, 'count': 0, 'groups': {}})
        n = idata['count'] or 1

        avg_hto = idata['hto_total'] / n if idata['count'] > 0 else 0.0
        total_active = sum(idata['groups'].values())
        avg_machines = round(total_active / n) if idata['count'] > 0 else 0

        for g in hto_group_names:
            raw = idata['groups'].get(g, 0)
            group_count_arrays[g].append(round(raw / n) if idata['count'] > 0 else 0)

        oil_data = hto_oil_by_interval.get(interval_key, {'total': 0, 'count': 0})
        avg_oil = oil_data['total'] / oil_data['count'] if oil_data['count'] > 0 else None

        fmt = "%H:%M"
        timestamps.append(localtime(interval_key).strftime(fmt))
        hto_totals.append(round(avg_hto, 1))
        hto_oil_temps.append(round(avg_oil, 1) if avg_oil is not None else None)
        machine_counts.append(avg_machines)

    # Trim trailing empty buckets
    while (len(timestamps) > 1 and hto_totals[-1] == 0.0 and hto_oil_temps[-1] is None):
        timestamps.pop()
        hto_totals.pop()
        hto_oil_temps.pop()
        machine_counts.pop()
        for g in hto_group_names:
            if group_count_arrays[g]:
                group_count_arrays[g].pop()

    return JsonResponse({
        "timestamps": timestamps,
        "hto_totals": hto_totals,
        "hto_oil_temps": hto_oil_temps,
        "machine_counts": machine_counts,
        "machine_groups": hto_group_names,
        "machine_group_counts": group_count_arrays,
        "period": f"{hours}h",
        "interval_minutes": round(interval_minutes, 1),
        "count": len(timestamps),
    })


@login_required
def steam_usage_detail_api(request):
    """
    API endpoint to get detailed list of machines using steam at a specific timestamp.
    Compares with data 1 hour prior to determine "NEW" status.
    """
    from .models import MachineStatusSnapshot, Machine
    from django.utils.dateparse import parse_datetime
    from collections import defaultdict
    
    timestamp_str = request.GET.get('timestamp')
    if not timestamp_str:
        return JsonResponse({"error": "Missing timestamp"}, status=400)
        
    try:
        target_time = parse_datetime(timestamp_str)
        if not target_time:
            # Maybe it's a date string (from Daily view)
            target_time = timezone.make_aware(timezone.datetime.strptime(timestamp_str, "%Y-%m-%d"))
    except Exception:
        return JsonResponse({"error": "Invalid timestamp format"}, status=400)

    # Cari snapshot terdekat yang waktunya paling dekat dengan titik grafik yang diklik
    # Kita beri toleransi 5 menit ke depan jika tidak pas, lalu ambil yang paling baru sebelumnya
    current_snapshot = MachineStatusSnapshot.objects.filter(
        timestamp__lte=target_time + timedelta(minutes=5)
    ).order_by('-timestamp').first()
    
    if not current_snapshot:
        return JsonResponse({"data": [], "timestamp_display": target_time.strftime("%d %b %H:%M")})
        
    # Get snapshot 1 hour prior to current_snapshot
    prior_time = current_snapshot.timestamp - timedelta(hours=1)
    prior_snapshot = MachineStatusSnapshot.objects.filter(
        timestamp__lte=prior_time
    ).order_by('-timestamp').first()
    
    prior_data = prior_snapshot.snapshot_data if prior_snapshot else {}
    current_data = current_snapshot.snapshot_data
    
    # Get all steam-using machines
    steam_machines = Machine.objects.filter(is_active=True, average_steam_usage__gt=0).select_related('group')
    
    # Process and group data
    grouped_data = defaultdict(list)
    
    for machine in steam_machines:
        snap = current_data.get(machine.code)
        if not snap:
            continue
            
        is_active = False
        display_status = ""
        
        if snap.get('mode') == 'MANUAL':
            is_active = snap.get('status') == 'Running'
            display_status = snap.get('status')
        else:
            is_active = snap.get('detail') in ['HEAT', 'STEADY']
            display_status = snap.get('detail')
            
        if is_active:
            # Check prior status
            is_new = False
            prior_snap = prior_data.get(machine.code)
            if not prior_snap:
                is_new = True
            else:
                prior_active = False
                if prior_snap.get('mode') == 'MANUAL':
                    prior_active = prior_snap.get('status') == 'Running'
                else:
                    prior_active = prior_snap.get('detail') in ['HEAT', 'STEADY']
                if not prior_active:
                    is_new = True
            
            group_name = machine.group.name if machine.group else "Lain-lain"
            
            grouped_data[group_name].append({
                "code": machine.code,
                "name": machine.name,
                "usage": machine.average_steam_usage,
                "status": display_status,
                "is_new": is_new
            })
            
    # Format the final response
    result = []
    for group_name, machines in grouped_data.items():
        # Sort machines by code
        machines.sort(key=lambda x: x['code'])
        result.append({
            "group_name": group_name,
            "machines": machines
        })
        
    # Sort groups alphabetically
    result.sort(key=lambda x: x['group_name'])
    
    return JsonResponse({
        "timestamp_display": localtime(current_snapshot.timestamp).strftime("%d %b %Y, %H:%M"),
        "data": result
    })


@login_required
@position_required('analytics')
def graph_menu(request):
    from django.db.models import Case, When, IntegerField
    
    # Custom ordering: MC_BOILER group goes to the bottom
    # Non-MC_BOILER groups (order=0) appear first, MC_BOILER (order=1) appears last
    machines = Machine.objects.filter(is_active=True).annotate(
        boiler_sort=Case(
            When(group__code='MC_BOILER', then=1),
            default=0,
            output_field=IntegerField(),
        )
    ).order_by('boiler_sort', 'name')
    
    return render(request, "graph_menu.html", {"machines": machines})


@login_required
def graph_data_api(request):
    machine_code = request.GET.get("machine")
    start = request.GET.get("start")
    end = request.GET.get("end")

    # Cek parameter
    if not machine_code or not start or not end:
        return JsonResponse({"error": "Missing parameters"}, status=400)

    # Convert waktu (format: YYYY-MM-DD HH:MM)
    try:
        start_dt = make_aware(datetime.strptime(start, "%Y-%m-%d %H:%M"))
        end_dt = make_aware(datetime.strptime(end, "%Y-%m-%d %H:%M"))
    except:
        return JsonResponse({"error": "Invalid datetime format"}, status=400)

    # Ambil mesin
    machine = Machine.objects.filter(code=machine_code).first()
    if not machine:
        return JsonResponse({"error": "Machine not found"}, status=404)

    # Ambil log 1 menit
    # .values_list() → Django mengirim tuple langsung dari PostgreSQL, skip instansiasi Model
    # Hemat RAM ~80% dibanding .filter().order_by() biasa pada dataset besar
    logs = (
        MachineMinuteLog.objects
        .filter(machine=machine, timestamp__range=(start_dt, end_dt))
        .values_list('timestamp', 'temperature')
        .order_by("timestamp")
    )

    timestamps = []
    temps = []
    for ts, temp in logs:
        timestamps.append(localtime(ts).strftime("%Y-%m-%d %H:%M"))
        temps.append(temp)

    return JsonResponse({
        "machine": machine.code,
        "unit": machine.unit_symbol,
        "timestamps": timestamps,
        "temperatures": temps,
        "count": len(temps),
    })

@login_required
def graph_multi_api(request):
    machine_codes = request.GET.get("machines")
    start = request.GET.get("start")
    end = request.GET.get("end")

    if not machine_codes or not start or not end:
        return JsonResponse({"error": "Missing parameters"}, status=400)

    machine_codes = machine_codes.split(",")

    # Convert datetime
    try:
        start_dt = make_aware(datetime.strptime(start, "%Y-%m-%d %H:%M"))
        end_dt = make_aware(datetime.strptime(end, "%Y-%m-%d %H:%M"))
    except:
        return JsonResponse({"error": "Invalid datetime format"}, status=400)

    # Ambil semua mesin
    machines = {m.code: m for m in Machine.objects.filter(code__in=machine_codes)}

    # Ambil log semua mesin
    # .values() → PostgreSQL JOIN 1x untuk 'machine__code', skip instansiasi Model
    # Menghilangkan N+1 query (log.machine.code sebelumnya = query baru per baris log)
    logs = (
        MachineMinuteLog.objects
        .filter(machine__code__in=machine_codes, timestamp__range=(start_dt, end_dt))
        .values(
            'timestamp', 'machine__code', 'temperature', 'filtered_temp',
            'gradient', 'thermal_state', 'ewma_temp', 'kalman_x'
        )
        .order_by("timestamp")
    )

    # Struktur tabel - now includes all processed fields
    table = {}   # key = timestamp, value = {machine_code: {temp, filtered, gradient, state}}

    for log in logs:
        ts = localtime(log['timestamp']).strftime("%Y-%m-%d %H:%M")
        if ts not in table:
            table[ts] = {}

        # machine__code sudah tersedia dari dict, tidak ada extra query ke DB
        table[ts][log['machine__code']] = {
            "temp": log['temperature'],
            "filtered": log['filtered_temp'],
            "gradient": log['gradient'],
            "state": log['thermal_state'],
            "ewma": log['ewma_temp'],
            "kalman": log['kalman_x'],
        }

    # Format untuk frontend
    timestamps = sorted(table.keys())
    
    meta_map = {
        code: {
            "unit": machines[code].unit_symbol,
            "nominal_power": machines[code].nominal_power
        }
        for code in machine_codes
        if code in machines
    }

    return JsonResponse({
        "timestamps": timestamps,
        "machines": machine_codes,
        "table": table,  # dict timestamp → {machine_code: {temp, filtered, gradient, state}}
        "meta": meta_map,
    })


@login_required
def steam_hto_analytics_api(request):
    """
    API endpoint for Steam and HTO analytics time-series data.
    Returns total steam usage and total HTO calories over time from MachineStatusSnapshot.
    
    Query Parameters:
    - start: Start datetime (format: YYYY-MM-DD HH:MM)
    - end: End datetime (format: YYYY-MM-DD HH:MM)
    - interval: Sampling interval in minutes (default: 5, options: 1, 5, 15, 30, 60)
    
    Returns:
    {
        "timestamps": ["2026-01-30 08:00", "2026-01-30 08:05", ...],
        "steam_totals": [120.5, 125.3, ...],  // in kg/h
        "hto_totals": [850000, 860000, ...],  // in kCal/h
        "interval": 5,
        "data_points": 288
    }
    """
    from .models import MachineStatusSnapshot
    
    # Parse parameters
    start_str = request.GET.get('start')
    end_str = request.GET.get('end')
    interval = int(request.GET.get('interval', 5))
    
    if not start_str or not end_str:
        return JsonResponse({"error": "Missing start or end parameter"}, status=400)
    
    # Convert datetime strings to datetime objects
    try:
        start_dt = make_aware(datetime.strptime(start_str, "%Y-%m-%d %H:%M"))
        end_dt = make_aware(datetime.strptime(end_str, "%Y-%m-%d %H:%M"))
    except ValueError:
        return JsonResponse({"error": "Invalid datetime format. Use YYYY-MM-DD HH:MM"}, status=400)
    
    # Validate interval
    if interval not in [1, 5, 15, 30, 60]:
        interval = 5
    
    # Query snapshots in the time range
    snapshots = MachineStatusSnapshot.objects.filter(
        timestamp__range=(start_dt, end_dt)
    ).order_by('timestamp')
    
    # Get all active machines for lookup
    # select_related('group') → 1 JOIN query, menghindari N+1 ke tabel MachineGroup
    all_machines = Machine.objects.filter(is_active=True).select_related('group')
    machine_dict = {m.code: m for m in all_machines}
    
    # Process snapshots and calculate totals
    results = []
    
    for snapshot in snapshots:
        # Sample by interval - only process snapshots where minute % interval == 0
        if snapshot.timestamp.minute % interval != 0:
            continue
        
        total_steam = 0.0
        total_hto = 0.0
        steam_machine_count = 0
        hto_machine_count = 0
        steam_pressure = None  # Steam pressure from steam_pr machine
        steam_by_group = {}         # group_name -> steam value for this snapshot
        hto_by_group = {}           # group_name -> hto value for this snapshot
        steam_count_by_group = {}   # group_name -> machine count (steam)
        hto_count_by_group = {}     # group_name -> machine count (hto)
        
        # Calculate totals from all machines in this snapshot
        for machine_code, snap_data in snapshot.snapshot_data.items():
            # Check if this is the steam_pr machine (steam pressure sensor)
            if machine_code.lower() == 'steam_pr':
                # Get temperature value which represents pressure in barg
                steam_pressure = snap_data.get('temperature')
                continue
            
            machine = machine_dict.get(machine_code)
            
            if not machine:
                continue
            
            # Determine if machine is active based on mode and status
            is_active = False
            
            from monitoring.utils.steam_active import is_steam_active_from_snapshot
            is_active = is_steam_active_from_snapshot(snap_data)
            
            if is_active:
                group_name = machine.group.name if machine.group else 'Lainnya'
                
                # Add to steam total and count if machine uses steam
                if machine.average_steam_usage and machine.average_steam_usage > 0:
                    total_steam += machine.average_steam_usage
                    steam_machine_count += 1
                    steam_by_group[group_name] = steam_by_group.get(group_name, 0.0) + machine.average_steam_usage
                    steam_count_by_group[group_name] = steam_count_by_group.get(group_name, 0) + 1
                
                # Add to HTO total and count if machine uses HTO
                if machine.avg_hto_calories and machine.avg_hto_calories > 0:
                    total_hto += machine.avg_hto_calories
                    hto_machine_count += 1
                    hto_by_group[group_name] = hto_by_group.get(group_name, 0.0) + machine.avg_hto_calories
                    hto_count_by_group[group_name] = hto_count_by_group.get(group_name, 0) + 1
        
        # Format timestamp for frontend
        timestamp_str = localtime(snapshot.timestamp).strftime("%Y-%m-%d %H:%M")
        
        # Store results
        results.append({
            'timestamp': timestamp_str,
            'steam': total_steam,
            'hto': total_hto,
            'steam_machines': steam_machine_count,
            'hto_machines': hto_machine_count,
            'steam_pressure': round(steam_pressure, 2) if steam_pressure is not None else None,
            'steam_by_group': steam_by_group,
            'hto_by_group': hto_by_group,
            'steam_count_by_group': steam_count_by_group,
            'hto_count_by_group': hto_count_by_group,
        })
    
    # Collect all unique group names across all snapshots (sorted)
    all_steam_groups = sorted(set(
        group for r in results for group in r['steam_by_group']
    ))
    all_hto_groups = sorted(set(
        group for r in results for group in r['hto_by_group']
    ))

    # Build per-group arrays aligned to timestamps
    steam_by_group_series = {}
    for group in all_steam_groups:
        steam_by_group_series[group] = [
            round(r['steam_by_group'].get(group, 0.0), 2) for r in results
        ]

    hto_by_group_series = {}
    for group in all_hto_groups:
        hto_by_group_series[group] = [
            round(r['hto_by_group'].get(group, 0.0), 2) for r in results
        ]

    # Build per-group machine COUNT arrays aligned to timestamps
    steam_count_by_group_series = {}
    for group in all_steam_groups:
        steam_count_by_group_series[group] = [
            r['steam_count_by_group'].get(group, 0) for r in results
        ]

    hto_count_by_group_series = {}
    for group in all_hto_groups:
        hto_count_by_group_series[group] = [
            r['hto_count_by_group'].get(group, 0) for r in results
        ]

    # Format response
    return JsonResponse({
        'timestamps': [r['timestamp'] for r in results],
        'steam_totals': [r['steam'] for r in results],
        'hto_totals': [r['hto'] for r in results],
        'steam_machine_counts': [r['steam_machines'] for r in results],
        'hto_machine_counts': [r['hto_machines'] for r in results],
        'steam_pressures': [r['steam_pressure'] for r in results],
        'steam_by_group': steam_by_group_series,
        'hto_by_group': hto_by_group_series,
        'steam_count_by_group': steam_count_by_group_series,
        'hto_count_by_group': hto_count_by_group_series,
        'steam_groups': all_steam_groups,
        'hto_groups': all_hto_groups,
        'interval': interval,
        'data_points': len(results)
    })


@login_required
def snapshot_detail_api(request):
    """
    API endpoint to get detailed snapshot at a specific timestamp.
    Shows all active machines with their status, filtered by type (steam/hto).
    
    Query Parameters:
    - timestamp: Exact timestamp (format: YYYY-MM-DD HH:MM)
    - type: Filter type ('steam' or 'hto')
    
    Returns machine details at that specific moment.
    """
    from .models import MachineStatusSnapshot
    
    # Parse parameters
    timestamp_str = request.GET.get('timestamp')
    filter_type = request.GET.get('type', 'steam')  # 'steam' or 'hto'
    
    if not timestamp_str:
        return JsonResponse({"error": "Missing timestamp parameter"}, status=400)
    
    # Convert timestamp string to datetime object
    try:
        timestamp_dt = make_aware(datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M"))
    except ValueError:
        return JsonResponse({"error": "Invalid timestamp format. Use YYYY-MM-DD HH:MM"}, status=400)
    
    # Find the snapshot at this exact timestamp
    try:
        snapshot = MachineStatusSnapshot.objects.get(timestamp=timestamp_dt)
    except MachineStatusSnapshot.DoesNotExist:
        return JsonResponse({
            "error": "No snapshot found at this timestamp",
            "timestamp": timestamp_str,
            "machines": [],
            "total_machines": 0,
            "total_usage": 0
        })
    
    # Get all active machines for lookup
    # select_related('group') → 1 JOIN query, menghindari N+1 ke tabel MachineGroup
    all_machines = Machine.objects.filter(is_active=True).select_related('group')
    machine_dict = {m.code: m for m in all_machines}
    
    # Get previous snapshot (1 hour ago) for status change detection
    one_hour_ago = timestamp_dt - timedelta(hours=1)
    try:
        prev_snapshot = MachineStatusSnapshot.objects.filter(
            timestamp__lte=one_hour_ago
        ).order_by('-timestamp').first()
    except:
        prev_snapshot = None
    
    # Process machines based on filter type
    machines_data = []
    total_usage = 0.0
    
    for machine_code, snap_data in snapshot.snapshot_data.items():
        machine = machine_dict.get(machine_code)
        
        if not machine:
            continue
        
        # Get current state info
        current_state = snap_data.get('detail', 'Unknown')
        current_status = snap_data.get('status', 'Unknown')
        current_mode = snap_data.get('mode', 'Unknown')
        
        # Filter by type and check if machine uses steam/hto
        # Show ALL machines (including OFF and COOLING) that have steam/hto usage configured
        usage_value = 0.0
        unit = ""
        
        if filter_type == 'steam':
            if machine.average_steam_usage and machine.average_steam_usage > 0:
                usage_value = machine.average_steam_usage
                unit = "kg/h"
            else:
                continue  # Skip machines that don't use steam
        else:  # hto
            if machine.avg_hto_calories and machine.avg_hto_calories > 0:
                usage_value = machine.avg_hto_calories
                unit = "kCal/h"
            else:
                continue  # Skip machines that don't use HTO
        
        # Determine if currently active (for display purposes)
        is_currently_active = False
        from monitoring.utils.steam_active import is_steam_active_from_snapshot
        is_currently_active = is_steam_active_from_snapshot(snap_data)
        
        # Only count usage if machine is currently active
        if is_currently_active:
            total_usage += usage_value
        
        # Detect status changes from previous snapshot
        status_change = None
        if prev_snapshot and machine_code in prev_snapshot.snapshot_data:
            prev_data = prev_snapshot.snapshot_data[machine_code]
            prev_state = prev_data.get('detail', 'Unknown')
            prev_status = prev_data.get('status', 'Unknown')
            prev_mode = prev_data.get('mode', 'Unknown')
            
            # Calculate time difference
            time_diff = timestamp_dt - prev_snapshot.timestamp
            hours_ago = time_diff.total_seconds() / 3600
            
            # Check if state changed
            state_changed = False
            change_description = []
            
            if prev_mode != current_mode:
                state_changed = True
                change_description.append(f"Mode: {prev_mode} → {current_mode}")
            
            if prev_status != current_status:
                state_changed = True
                change_description.append(f"Status: {prev_status} → {current_status}")
            
            if prev_state != current_state:
                state_changed = True
                change_description.append(f"State: {prev_state} → {current_state}")
            
            if state_changed:
                status_change = {
                    'changed': True,
                    'from_state': prev_state,
                    'to_state': current_state,
                    'from_status': prev_status,
                    'to_status': current_status,
                    'from_mode': prev_mode,
                    'to_mode': current_mode,
                    'description': ' | '.join(change_description),
                    'hours_ago': round(hours_ago, 1)
                }
            else:
                status_change = {
                    'changed': False,
                    'description': f'Stable for {round(hours_ago, 1)}h'
                }
        else:
            # No previous data
            status_change = {
                'changed': False,
                'description': 'New in this period'
            }
        
        # Build machine data
        machines_data.append({
            'code': machine.code,
            'name': machine.name or machine.code,
            'status': snap_data.get('status', 'Unknown'),
            'mode': snap_data.get('mode', 'Unknown'),
            'thermal_state': snap_data.get('detail', 'Unknown'),
            'usage_value': round(usage_value, 1),
            'unit': unit,
            'group': machine.group.name if machine.group else 'No Group',
            'status_change': status_change,
            'is_currently_active': is_currently_active
        })
    
    # Sort by usage value (descending)
    machines_data.sort(key=lambda x: x['usage_value'], reverse=True)
    
    # Count active vs inactive machines with detailed breakdown
    total_active = sum(1 for m in machines_data if m['is_currently_active'])
    total_inactive = len(machines_data) - total_active
    
    # Detailed state counts
    state_counts = {
        'running': 0,
        'heat': 0,
        'steady': 0,
        'off': 0,
        'cool': 0,
        'stop': 0
    }
    
    for machine in machines_data:
        if machine['mode'] == 'MANUAL':
            if machine['status'] == 'Running':
                state_counts['running'] += 1
            else:
                state_counts['stop'] += 1
        else:  # AUTO
            state = machine['thermal_state'].upper()
            if state == 'HEAT':
                state_counts['heat'] += 1
            elif state == 'STEADY':
                state_counts['steady'] += 1
            elif state == 'COOL':
                state_counts['cool'] += 1
            elif state == 'OFF':
                state_counts['off'] += 1
            else:
                # Unknown state, count as off
                state_counts['off'] += 1
    
    return JsonResponse({
        'timestamp': timestamp_str,
        'type': filter_type,
        'machines': machines_data,
        'total_machines': len(machines_data),
        'total_active_machines': total_active,
        'total_inactive_machines': total_inactive,
        'state_counts': state_counts,
        'total_usage': round(total_usage, 1),
        'unit': "kg/h" if filter_type == 'steam' else "kCal/h"
    })


@login_required
@position_required('history')
def history_list(request):
    """
    List of dyeing process batches with filters and pagination.
    """
    from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
    from django.db.models import Q, Exists, OuterRef
    from django.utils import timezone as dt_timezone
    
    # Base queryset
    batches = DyeingProcess.objects.select_related("machine", "machine__group", "identity", "identity__program").order_by("-start_time")
    
    # Filter: Search (batch number, machine code, or machine name)
    search_query = request.GET.get("search", "").strip()
    if search_query:
        batches = batches.filter(
            Q(batch_number__icontains=search_query) |
            Q(machine__code__icontains=search_query) |
            Q(machine__name__icontains=search_query) |
            Q(machine__group__name__icontains=search_query)
        )
    
    # Filter: Machine Group
    groups = MachineGroup.objects.all()
    group_id = request.GET.get("group")
    if group_id:
        try:
            batches = batches.filter(machine__group_id=int(group_id))
        except (ValueError, TypeError):
            pass  # Ignore invalid group_id
        
    # Filter: Machine
    # [K6] Hanya ambil mesin aktif + kolom yang dibutuhkan untuk dropdown filter
    machines = Machine.objects.filter(is_active=True).only('id', 'code', 'name').order_by('code')
    machine_code = request.GET.get("machine")
    if machine_code:
        batches = batches.filter(machine__code=machine_code)
        
    # Filter: Date Range (Start Time)
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")
    
    if start_date:
        try:
            batches = batches.filter(start_time__date__gte=start_date)
        except:
            pass  # Ignore invalid date
            
    if end_date:
        try:
            batches = batches.filter(start_time__date__lte=end_date)
        except:
            pass  # Ignore invalid date

    # Optimize: Filter batches with logs using annotate (avoiding N+1 queries)
    # Create a subquery to check if logs exist for each batch
    # log_exists_subquery = MachineMinuteLog.objects.filter(
    #     machine=OuterRef('machine'),
    #     timestamp__gte=OuterRef('start_time'),
    #     timestamp__lte=dt_timezone.now()  # Use current time if end_time is None
    # )
    # 
    # # Annotate batches with has_logs field
    # batches = batches.annotate(
    #     has_logs=Exists(log_exists_subquery)
    # ).filter(has_logs=True)
    
    # Pagination: Get page size from request (default 10, valid options: 10, 20, 50)
    page_size = request.GET.get('page_size', '10')
    try:
        page_size = int(page_size)
        if page_size not in [10, 20, 50]:
            page_size = 10
    except (ValueError, TypeError):
        page_size = 10
    
    paginator = Paginator(batches, page_size)
    page_number = request.GET.get('page', 1)
    
    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        # If page is not an integer, deliver first page
        page_obj = paginator.page(1)
    except EmptyPage:
        # If page is out of range, deliver last page
        page_obj = paginator.page(paginator.num_pages)
    
    # Context
    context = {
        "batches": page_obj.object_list,
        "page_obj": page_obj,
        "is_paginated": paginator.num_pages > 1,
        "page_size": page_size,  # Pass current page size to template
        "groups": groups,
        "machines": machines,
        "search_query": search_query,
        "current_group": int(group_id) if group_id and group_id.isdigit() else "",
        "current_machine": machine_code or "",
        "start_date": start_date or "",
        "end_date": end_date or "",
    }
    return render(request, "history_list.html", context)


@login_required
@position_required('history_report')
def history_report(request, machine_code, batch_number):
    """
    Kanonikal redirect ke modern SCADA React Process Report.
    Mengalihkan /history/<machine_code>/<batch_number>/ ke /history/report/<id>?machine=...&batch=...
    """
    if request.GET.get('raw_ssr') != '1':
        from django.shortcuts import redirect
        process = DyeingProcess.objects.filter(
            machine__code=machine_code,
            batch_number=batch_number
        ).order_by('-start_time').first()
        
        if process:
            return redirect(f"/history/report/{process.id}?machine={process.machine.code}&batch={process.batch_number}")
        return redirect(f"/history/report/0?machine={machine_code}&batch={batch_number}")

    process = get_object_or_404(
        DyeingProcess.objects.select_related("machine", "machine__group"), 
        machine__code=machine_code,
        batch_number=batch_number
    )
    
    # Time range
    start_dt = process.start_time
    end_dt = process.end_time or timezone.now()
    
    # === 1. Fetch Main Machine Logs ===
    main_logs = MachineMinuteLog.objects.filter(
        machine=process.machine,
        timestamp__range=(start_dt, end_dt)
    ).order_by("timestamp")
    
    # Check if we have any logs
    if not main_logs.exists():
        context = {
            "process": process,
            "table_data": [],
            "timestamps_json": "[]",
            "main_temps_json": "[]",
            "steam_vals_json": "[]",
            "hto_vals_json": "[]",
            "analysis": {},
            "factory_name": "PT. SURITEX",
            "error_message": "Tidak ada data log untuk batch ini."
        }
        return render(request, "history_report.html", context)
    
    # === 2. Fetch Auxiliary Logs (Steam & HTO) ===
    steam_logs = MachineMinuteLog.objects.filter(
        machine__code="Steam_Pr",
        timestamp__range=(start_dt, end_dt)
    ).order_by("timestamp")
    
    hto_logs = MachineMinuteLog.objects.filter(
        machine__code="Oil_Temp",
        timestamp__range=(start_dt, end_dt)
    ).order_by("timestamp")
    
    # Map for O(1) lookup - Filter None values
    steam_map = {
        log.timestamp.replace(second=0, microsecond=0): log.temperature 
        for log in steam_logs if log.temperature is not None
    }
    hto_map = {
        log.timestamp.replace(second=0, microsecond=0): log.temperature 
        for log in hto_logs if log.temperature is not None
    }
    
    table_data = []
    timestamps = []
    main_temps = []
    steam_vals = []
    hto_vals = []
    
    start_temp_heat = None
    end_temp_heat = None
    
    for log in main_logs:
        ts = log.timestamp.replace(second=0, microsecond=0)
        steam = steam_map.get(ts)
        hto = hto_map.get(ts)
        
        # Use filtered temp if available, otherwise raw temp
        main_temp = log.temperature
        
        # Calculate efficiency per row (like in analyze_batch_details)
        efficiency = None
        if log.thermal_state == "HEAT" and log.gradient and log.gradient > 0.1:
            # Use default steam temp (150°C as per config)
            steam_temp = 150.0
            filtered_temp = log.filtered_temp or main_temp or 0
            
            # Calculate driving force
            driving_force = steam_temp - filtered_temp
            
            # Avoid division by zero
            if driving_force > 1.0:  # MIN_DRIVING_FORCE = 1.0
                efficiency = log.gradient / driving_force
        
        table_data.append({
            "timestamp": ts,
            "main_temp": main_temp,
            "filtered": log.filtered_temp,
            "gradient": log.gradient,
            "state": log.thermal_state,
            "steam": steam,
            "hto": hto,
            "efficiency": efficiency  # Add efficiency to table data
        })
        
        # For Chart.js - convert to localtime and format
        timestamps.append(localtime(ts).strftime("%Y-%m-%d %H:%M"))
        main_temps.append(main_temp)
        steam_vals.append(steam)
        hto_vals.append(hto)
        
        # Capture start/end temps for physics calculation
        if process.heating_duration and log.thermal_state == "HEAT":
            if start_temp_heat is None and main_temp is not None: 
                start_temp_heat = main_temp
            if main_temp is not None:
                end_temp_heat = main_temp

    # === 3. Physics Analysis ===
    # Use pre-calculated values from process_batch_history
    analysis = {}
    
    # 1. Ideal Heating Time - from model field
    if process.ideal_heating_time:
        analysis["ideal_heating_time"] = round(process.ideal_heating_time, 1)
    
    # 2. Heating Duration - use Rise Time (real_heating_duration)
    if process.real_heating_duration:
        analysis["heating_duration"] = round(process.real_heating_duration, 1)
    
    # 3. Time Efficiency - use time_efficiency_percent property
    if process.time_efficiency_percent:
        analysis["heating_efficiency"] = process.time_efficiency_percent
    
    # 4. Peak Temp - from model field
    if process.max_temp:
        analysis["peak_temp"] = round(process.max_temp, 1)
    
    # 5. Average Steam Temp - from model field
    if process.avg_steam_temp:
        analysis["avg_steam_temp"] = round(process.avg_steam_temp, 1)
    
    # 6. Average Steam Pressure - from model field
    if process.avg_steam_pressure:
        analysis["avg_steam_pressure"] = round(process.avg_steam_pressure, 2)
    
    # Get ProcessingConfig for cooling calculations (still needed)
    if ProcessingConfig:
        try:
            cfg = ProcessingConfig()
        except:
            class DefaultConfig:
                MAX_COOL_RATE = 2.0
            cfg = DefaultConfig()
    else:
        class DefaultConfig:
            MAX_COOL_RATE = 2.0
        cfg = DefaultConfig()
    
    # Ideal Cooling Duration (keep existing logic)
    if process.cooling_duration and process.max_temp:
        try:
            delta_T = process.max_temp - 30.0  # Approx end temp
            if delta_T > 0:
                t_ideal_cool = delta_T / cfg.MAX_COOL_RATE
                analysis["ideal_cooling_time"] = round(t_ideal_cool, 1)
                
                if process.cooling_duration > 0:
                    analysis["cooling_efficiency"] = round(
                        (t_ideal_cool / process.cooling_duration) * 100, 1
                    )
        except (ValueError, ZeroDivisionError):
            pass
            
    # Energy Estimate (keep existing logic)
    if process.max_temp and process.start_temp:
        try:
            mass_kg = 3200  # Bath volume
            cp = 4.18  # kJ/kg.C
            dt = process.max_temp - process.start_temp
            
            if dt > 0:
                q_kj = mass_kg * cp * dt
                q_kwh = q_kj * 0.0002778
                analysis["energy_kwh"] = round(q_kwh, 2)
                
                # Cost estimate (Rp 1447/kWh)
                analysis["energy_cost"] = f"{int(q_kwh * 1447):,}"
        except (ValueError, ZeroDivisionError):
            pass
    
    # Serialize for JS
    import json

    # === 4. Prev / Next batch for the same machine (skip deleted batch numbers) ===
    prev_process = DyeingProcess.objects.filter(
        machine=process.machine,
        batch_number__lt=process.batch_number
    ).order_by('-batch_number').first()

    next_process = DyeingProcess.objects.filter(
        machine=process.machine,
        batch_number__gt=process.batch_number
    ).order_by('batch_number').first()

    context = {
        "process": process,
        "table_data": table_data,
        "timestamps_json": json.dumps(timestamps),
        "main_temps_json": json.dumps(main_temps),
        "steam_vals_json": json.dumps(steam_vals),
        "hto_vals_json": json.dumps(hto_vals),
        "analysis": analysis,
        "factory_name": "PT. SURITEX",
        "prev_batch": prev_process,
        "next_batch": next_process,
    }
    return render(request, "history_report.html", context)


@login_required
@position_required('history_report')
def history_report_legacy(request, batch_id):
    """
    Legacy URL support for old ID-based links.
    Redirects to new stable URL using machine_code + batch_number.
    """
    from django.shortcuts import redirect
    
    process = get_object_or_404(
        DyeingProcess.objects.select_related("machine"),
        id=batch_id
    )
    
    # Redirect to canonical SCADA report URL
    return redirect(f"/history/report/{process.id}?machine={process.machine.code}&batch={process.batch_number}")

@login_required
def dyeing_analytics_report(request, identity_pk):
    """
    Standalone per-batch Dyeing Analytics Report.
    Menampilkan data Identity + Process lengkap dengan grafik temperature profile
    dan phase breakdown. Format A4, print-ready.
    """
    import json

    # 1. Fetch DyeingIdentity dengan relasi lengkap (fallback ke dyeing_process_id atau batch_number jika perlu)
    identity = (
        DyeingIdentity.objects
        .select_related('dyeing_process', 'machine', 'machine__group', 'program')
        .filter(pk=identity_pk)
        .first()
    )
    if not identity:
        identity = (
            DyeingIdentity.objects
            .select_related('dyeing_process', 'machine', 'machine__group', 'program')
            .filter(dyeing_process_id=identity_pk)
            .first()
        )
    if not identity:
        identity = (
            DyeingIdentity.objects
            .select_related('dyeing_process', 'machine', 'machine__group', 'program')
            .filter(dyeing_process__batch_number=identity_pk)
            .first()
        )
    if not identity:
        raise Http404("Dyeing identity / process tidak ditemukan.")

    process = identity.dyeing_process

    if not process:
        return render(request, 'dyeing_analytics_report.html', {
            'identity': identity,
            'process': None,
            'error_message': 'Batch dyeing untuk identity ini belum terhubung (orphan).',
            'company_profile': CompanyProfile.objects.first(),
        })

    # 2. Prev / Next navigation (per mesin, urut start_time)
    prev_identity = (
        DyeingIdentity.objects
        .filter(
            machine=identity.machine,
            dyeing_process__isnull=False,
            dyeing_process__start_time__lt=process.start_time,
        )
        .order_by('-dyeing_process__start_time')
        .select_related('dyeing_process')
        .first()
    )
    next_identity = (
        DyeingIdentity.objects
        .filter(
            machine=identity.machine,
            dyeing_process__isnull=False,
            dyeing_process__start_time__gt=process.start_time,
        )
        .order_by('dyeing_process__start_time')
        .select_related('dyeing_process')
        .first()
    )

    # 3. Chart data — semua MachineMinuteLog dalam range batch
    start_dt = process.start_time
    end_dt = process.end_time or timezone.now()

    main_logs = (
        MachineMinuteLog.objects
        .filter(machine=process.machine, timestamp__range=(start_dt, end_dt))
        .order_by('timestamp')
        .values_list('timestamp', 'temperature')
    )

    # Ambil Steam logs untuk chart
    steam_logs = (
        MachineMinuteLog.objects
        .filter(machine__code='Steam_Pr', timestamp__range=(start_dt, end_dt))
        .order_by('timestamp')
        .values_list('timestamp', 'temperature')
    )
    steam_map = {
        ts.replace(second=0, microsecond=0): temp
        for ts, temp in steam_logs
        if temp is not None
    }

    timestamps = []
    main_temps = []
    steam_vals = []

    for ts, temp in main_logs:
        ts_clean = ts.replace(second=0, microsecond=0)
        timestamps.append(localtime(ts_clean).strftime('%Y-%m-%d %H:%M'))
        main_temps.append(temp)
        steam_vals.append(steam_map.get(ts_clean))

    # 4. Derived metrics
    loss_time = None
    efficiency = None
    grade = None

    if identity.program and identity.program.durasi_ideal is not None and \
       process.duration_effective is not None and process.duration_effective > 0:
        loss_time = round(identity.program.durasi_ideal - process.duration_effective, 1)
        efficiency = round((identity.program.durasi_ideal / process.duration_effective) * 100, 1)
        if efficiency >= 80:
            grade = 'A'
        elif efficiency >= 60:
            grade = 'B'
        else:
            grade = 'C'

    # 5. Phase percentages untuk breakdown chart
    # real_heating_duration = fase naik suhu aktual (Rise Time / Heat)
    # steady_duration  = fase suhu dijaga (Hold/Steady) — hanya tampil jika ada
    # cooling_duration = fase pendinginan (Cool)
    heat_dur  = process.real_heating_duration or 0
    hold_dur  = process.steady_duration or 0   # "Hold" / steady
    cool_dur  = process.cooling_duration or 0
    total_dur = heat_dur + hold_dur + cool_dur

    phase_pct = {}
    if total_dur > 0:
        phase_pct['heat']    = round(heat_dur / total_dur * 100, 1)
        phase_pct['cooling'] = round(cool_dur / total_dur * 100, 1)
        if hold_dur > 0:
            phase_pct['hold'] = round(hold_dur / total_dur * 100, 1)


    # 6. Average steam pressure sebagai garis datar di chart
    avg_steam_pressure = process.avg_steam_pressure  # sudah tersimpan di DyeingProcess

    # === NEW: PERHITUNGAN DAYA & UAP ===
    ideal_consumption = process.ideal_power_consumption_kwh

    actual_consumption = None
    if process.power_consumption_kwh is not None:
        actual_consumption = process.power_consumption_kwh
    else:
        ref_start = process.heating_start_time or process.start_time
        if ref_start and process.machine_nominal_power:
            from django.utils import timezone
            now = timezone.now()
            duration_hours = (now - ref_start).total_seconds() / 3600.0
            actual_consumption = round(duration_hours * process.machine_nominal_power, 2)

    steam_usage_estimasi = None
    if getattr(process, 'predicted_steam_kg', None) is not None:
        steam_usage_estimasi = round(process.predicted_steam_kg, 2)
    elif process.machine.batch_steam:
        steam_usage_estimasi = round(process.machine.batch_steam, 2)
    elif process.machine.average_steam_usage and heat_dur:
        steam_usage_estimasi = round((process.machine.average_steam_usage / 60.0) * heat_dur, 2)
    # ===================================

    context = {
        'identity': identity,
        'process': process,
        'prev_identity': prev_identity,
        'next_identity': next_identity,
        'loss_time': loss_time,
        'efficiency': efficiency,
        'grade': grade,
        'phase_pct': phase_pct,
        'total_dur': total_dur,
        'heat_dur': heat_dur,
        'hold_dur': hold_dur,
        'cool_dur': cool_dur,
        'avg_steam_pressure': avg_steam_pressure,
        'actual_consumption': actual_consumption,
        'ideal_consumption': ideal_consumption,
        'steam_usage_estimasi': steam_usage_estimasi,
        'timestamps_json': json.dumps(timestamps),
        'main_temps_json': json.dumps(main_temps),
        'steam_vals_json': json.dumps(steam_vals),
        'company_profile': CompanyProfile.objects.first(),
    }
    return render(request, 'dyeing_analytics_report.html', context)


@login_required
@position_required('snapshot_history')
def snapshot_history(request):
    """
    Display historical machine status snapshots with customizable filtering.
    Shows timestamp, machine statuses/details, steam totals, and HTO totals with differences.
    """
    from django.core.paginator import Paginator
    from .models import MachineStatusSnapshot
    import json
    
    # Parse filter parameters
    interval = int(request.GET.get('interval', 5))  # 1, 5, 15, 30, 60 minutes
    date_from_str = request.GET.get('date_from', timezone.now().date().isoformat())
    date_to_str = request.GET.get('date_to', timezone.now().date().isoformat())
    
    # Parse date strings
    try:
        date_from = datetime.strptime(date_from_str, '%Y-%m-%d').date()
    except (ValueError, AttributeError):
        date_from = timezone.now().date()
    
    try:
        date_to = datetime.strptime(date_to_str, '%Y-%m-%d').date()
    except (ValueError, AttributeError):
        date_to = timezone.now().date()
    
    # Smart default: If using default dates (today) and no GET params provided,
    # check if data exists for today. If not, use latest snapshot date.
    if not request.GET.get('date_from') and not request.GET.get('date_to'):
        # Check if any snapshots exist for today
        today = timezone.now().date()
        start_today = timezone.make_aware(datetime.combine(today, datetime.min.time()))
        end_today = timezone.make_aware(datetime.combine(today, datetime.max.time()))
        
        today_count = MachineStatusSnapshot.objects.filter(
            timestamp__range=(start_today, end_today)
        ).count()
        
        if today_count == 0:
            # No data for today, use latest snapshot date
            latest_snapshot = MachineStatusSnapshot.objects.order_by('-timestamp').first()
            if latest_snapshot:
                date_from = latest_snapshot.timestamp.date()
                date_to = latest_snapshot.timestamp.date()

    
    # Machine group and machine filtering
    selected_group_codes = request.GET.getlist('groups')  # Multiple groups
    selected_machine_codes = request.GET.getlist('machines')  # Multiple machines
    display_mode = request.GET.get('display_mode', 'both')  # 'status', 'detail', 'both'
    
    # Get all machine groups for filter dropdown
    all_groups = MachineGroup.objects.filter(machine__is_active=True).distinct().order_by('code')
    
    # Get ALL machines for filter dropdown (not filtered by selection)
    all_machines = Machine.objects.filter(is_active=True).order_by('group__code', 'code')
    
    # Get machines based on selected groups (for table display)
    machines_query = Machine.objects.filter(is_active=True)
    if selected_group_codes:
        machines_query = machines_query.filter(group__code__in=selected_group_codes)
    
    # Further filter by selected machines if specified
    if selected_machine_codes:
        machines_query = machines_query.filter(code__in=selected_machine_codes)
    
    # Get ordered list of machines for column headers
    machine_list = list(machines_query.order_by('group__code', 'code'))
    machine_codes = [m.code for m in machine_list]
    
    # Create machine lookup dict for steam/HTO calculations
    machine_dict = {m.code: m for m in machine_list}
    
    # Query snapshots in date range
    start_datetime = timezone.make_aware(datetime.combine(date_from, datetime.min.time()))
    end_datetime = timezone.make_aware(datetime.combine(date_to, datetime.max.time()))
    
    # [K4] Filter interval dilakukan di level PostgreSQL menggunakan ExtractMinute
    # Sebelumnya: semua snapshot dimuat ke RAM Python dulu, baru difilter di Python (sangat boros)
    # Sesudah: hanya baris yang lolos filter yang dikirim dari DB ke Python
    from django.db.models.functions import ExtractMinute

    snapshots_qs = MachineStatusSnapshot.objects.filter(
        timestamp__range=(start_datetime, end_datetime)
    ).order_by('-timestamp')  # Descending order - newest first

    if interval > 1:
        valid_minutes = [i * interval for i in range(60 // interval)]
        snapshots_qs = snapshots_qs.annotate(
            minute_val=ExtractMinute('timestamp')
        ).filter(minute_val__in=valid_minutes)

    filtered_snapshots = list(snapshots_qs)

    # Get ALL active machines for total calculations (not filtered by selection)
    all_machines_for_totals = Machine.objects.filter(is_active=True)
    all_machines_dict = {m.code: m for m in all_machines_for_totals}
    
    # Prepare table data
    table_data = []
    prev_steam_total = None
    prev_hto_total = None
    
    for snapshot in filtered_snapshots:
        row = {
            'timestamp': snapshot.timestamp,
            'machine_data': [],  # Changed from dict to list for easier template iteration
            'total_steam': 0.0,
            'total_hto': 0.0,
            'delta_steam': None,
            'delta_hto': None,
        }
        
        # Extract data for each selected machine in order (for display)
        for machine in machine_list:
            machine_code = machine.code
            if machine_code in snapshot.snapshot_data:
                snap_data = snapshot.snapshot_data[machine_code]
                machine_info = {
                    'code': machine_code,
                    'status': snap_data.get('status', 'Unknown'),
                    'detail': snap_data.get('detail', ''),
                    'mode': snap_data.get('mode', 'AUTO'),
                }
            else:
                # Machine not in snapshot
                machine_info = {
                    'code': machine_code,
                    'status': '-',
                    'detail': '-',
                    'mode': 'AUTO',
                }
            
            row['machine_data'].append(machine_info)
        
        # Calculate totals using ALL machines (factory-wide), not just filtered ones
        for machine_code, snap_data in snapshot.snapshot_data.items():
            machine = all_machines_dict.get(machine_code)
            if machine:
                is_active = False
                
                # Determine if machine is active based on mode and status
                from monitoring.utils.steam_active import is_steam_active_from_snapshot
                is_active = is_steam_active_from_snapshot(snap_data)
                
                if is_active:
                    row['total_steam'] += (machine.average_steam_usage or 0.0)
                    row['total_hto'] += (machine.avg_hto_calories or 0.0)
        
        # Calculate differences - in descending order, we compare with NEXT row (which is earlier in time)
        # So delta = current - next (to show increase/decrease from previous moment)
        if prev_steam_total is not None:
            row['delta_steam'] = prev_steam_total - row['total_steam']  # Reversed for descending
        if prev_hto_total is not None:
            row['delta_hto'] = prev_hto_total - row['total_hto']  # Reversed for descending
        
        prev_steam_total = row['total_steam']
        prev_hto_total = row['total_hto']
        
        table_data.append(row)
    
    # Pagination
    paginator = Paginator(table_data, 50)  # 50 rows per page
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    # Get data availability range for user info
    first_snapshot = MachineStatusSnapshot.objects.order_by('timestamp').first()
    last_snapshot = MachineStatusSnapshot.objects.order_by('-timestamp').first()
    
    # Context for template
    context = {
        'page_obj': page_obj,
        'machine_list': machine_list,  # For table columns (filtered)
        'all_machines': all_machines,  # For filter dropdown (all active machines)
        'all_groups': all_groups,
        'selected_groups': selected_group_codes,
        'selected_machines': selected_machine_codes,
        'display_mode': display_mode,
        'interval': interval,
        'date_from': date_from.isoformat(),
        'date_to': date_to.isoformat(),
        'interval_options': [1, 5, 15, 30, 60],
        'first_snapshot_date': first_snapshot.timestamp.date() if first_snapshot else None,
        'last_snapshot_date': last_snapshot.timestamp.date() if last_snapshot else None,
    }
    
    return render(request, 'snapshot_history.html', context)

@login_required
def machine_performance_summary(request):
    """
    View untuk menampilkan summary performa mesin (web version of admin summary).
    Filters: Month and Year.
    """
    from django.db.models import Avg, Count, Q
    from django.db.models.functions import TruncMonth
    from datetime import datetime
    
    # Get filter parameters
    today = timezone.now()
    current_year = today.year
    current_month = today.month
    
    year_param = int(request.GET.get('year', current_year))
    month_param = int(request.GET.get('month', current_month))
    
    # Calculate date range
    start_date = datetime(year_param, month_param, 1)
    if month_param == 12:
        end_date = datetime(year_param + 1, 1, 1)
    else:
        end_date = datetime(year_param, month_param + 1, 1)
        
    start_date = timezone.make_aware(start_date)
    end_date = timezone.make_aware(end_date)
    
    # Base QuerySet
    dyeing_filter = Q(
        dyeing_processes__start_time__gte=start_date,
        dyeing_processes__start_time__lt=end_date
    )
    
    # 1. Per-Machine Aggregation
    machine_qs = Machine.objects.filter(dyeing_filter).annotate(
        total_batches=Count('dyeing_processes', distinct=True),
        avg_heating_duration=Avg('dyeing_processes__heating_duration'),
        avg_heating_avg_gradient=Avg('dyeing_processes__heating_avg_gradient'),
        avg_steady_duration=Avg('dyeing_processes__steady_duration'),
        avg_cooling_duration=Avg('dyeing_processes__cooling_duration'),
        avg_cooling_avg_gradient=Avg('dyeing_processes__cooling_avg_gradient'),
        avg_start_temp=Avg('dyeing_processes__start_temp'),
        avg_end_temp=Avg('dyeing_processes__end_temp'),
        avg_max_temp=Avg('dyeing_processes__max_temp'),
        avg_heating_efficiency=Avg('dyeing_processes__avg_heating_efficiency'),
        avg_real_heating_duration=Avg('dyeing_processes__real_heating_duration'),
        avg_duration_effective=Avg('dyeing_processes__duration_effective'),
        avg_heating_gradient_duration=Avg('dyeing_processes__heating_gradient_duration'),
        avg_heating_span=Avg('dyeing_processes__heating_span'),
        avg_ideal_heating_time=Avg('dyeing_processes__ideal_heating_time'),
        avg_heating_lag_time=Avg('dyeing_processes__heating_lag_time'),
        avg_avg_steam_temp=Avg('dyeing_processes__avg_steam_temp'),
        avg_avg_steam_pressure=Avg('dyeing_processes__avg_steam_pressure'),
    ).order_by('code')
    
    # 2. Global Aggregation (Average of all batches in range)
    # We aggregate directly from DyeingProcess to get true weighted averages
    global_stats = DyeingProcess.objects.filter(
        start_time__gte=start_date,
        start_time__lt=end_date
    ).aggregate(
        total_batches=Count('id'),
        avg_heating_duration=Avg('heating_duration'),
        avg_heating_avg_gradient=Avg('heating_avg_gradient'),
        avg_steady_duration=Avg('steady_duration'),
        avg_cooling_duration=Avg('cooling_duration'),
        avg_cooling_avg_gradient=Avg('cooling_avg_gradient'),
        avg_start_temp=Avg('start_temp'),
        avg_end_temp=Avg('end_temp'),
        avg_max_temp=Avg('max_temp'),
        avg_heating_efficiency=Avg('avg_heating_efficiency'),
        avg_real_heating_duration=Avg('real_heating_duration'),
        avg_duration_effective=Avg('duration_effective'),
        avg_heating_gradient_duration=Avg('heating_gradient_duration'),
        avg_heating_span=Avg('heating_span'),
        avg_ideal_heating_time=Avg('ideal_heating_time'),
        avg_heating_lag_time=Avg('heating_lag_time'),
        avg_avg_steam_temp=Avg('avg_steam_temp'),
        avg_avg_steam_pressure=Avg('avg_steam_pressure'),
    )
    
    # Prepare list of years for filter (e.g., from first batch to now)
    first_batch = DyeingProcess.objects.order_by('start_time').first()
    start_year = first_batch.start_time.year if first_batch else current_year
    years = range(start_year, current_year + 2)
    
    # Sorting
    sort_param = request.GET.get('sort', 'code')
    
    # Validate sort param to prevent injection or errors
    valid_sort_fields = [
        'code', '-code',
        'total_batches', '-total_batches',
        'avg_heating_efficiency', '-avg_heating_efficiency',
        'avg_real_heating_duration', '-avg_real_heating_duration',
        'avg_ideal_heating_time', '-avg_ideal_heating_time',
        'avg_start_temp', '-avg_start_temp',
        'avg_max_temp', '-avg_max_temp',
        'avg_heating_duration', '-avg_heating_duration',
        'avg_steady_duration', '-avg_steady_duration',
        'avg_cooling_duration', '-avg_cooling_duration',
        'avg_avg_steam_temp', '-avg_avg_steam_temp',
        'avg_avg_steam_pressure', '-avg_avg_steam_pressure',
        'avg_end_temp', '-avg_end_temp', # Added just in case
        'avg_heating_avg_gradient', '-avg_heating_avg_gradient',
        'avg_cooling_avg_gradient', '-avg_cooling_avg_gradient',
        'avg_duration_effective', '-avg_duration_effective',
        'avg_heating_gradient_duration', '-avg_heating_gradient_duration',
        'avg_heating_span', '-avg_heating_span',
        'avg_heating_lag_time', '-avg_heating_lag_time',
    ]
    
    if sort_param not in valid_sort_fields:
        sort_param = 'code'
        
    machine_qs = machine_qs.order_by(sort_param)
    
    context = {
        'page_title': 'Machine Performance Summary',
        'machines': machine_qs,
        'global_stats': global_stats,
        'years': years,
        'selected_year': year_param,
        'selected_month': month_param,
        'current_sort': sort_param,
        'months': [
            (1, 'January'), (2, 'February'), (3, 'March'), (4, 'April'),
            (5, 'May'), (6, 'June'), (7, 'July'), (8, 'August'),
            (9, 'September'), (10, 'October'), (11, 'November'), (12, 'December')
        ]
    }
    
    return render(request, 'machine_performance_summary.html', context)


# ========================================
# CRITICAL ALERT SYSTEM API ENDPOINTS
# ========================================

@login_required
def get_active_alerts(request):
    """
    API endpoint to get all active alerts with pagination and filtering.
    Returns alerts ordered by severity (CRITICAL first) and creation time (newest first).
    """
    from .models import Alert
    from django.core.paginator import Paginator
    
    # FILTERING ###############
#     Get severity filter
    severity_filter = request.GET.get('severity', '')  # CRITICAL, WARNING, INFO
    
    # Base queryset: active alerts only
    alerts_qs = Alert.objects.filter(is_active=True).select_related('machine')
    
    # Apply severity filter if provided
    
    if severity_filter and severity_filter in ['CRITICAL', 'WARNING', 'INFO']:
        alerts_qs = alerts_qs.filter(severity=severity_filter)
    
    # Order by: CRITICAL > WARNING > INFO, then by created_at (newest first)
    severity_order = {
        'CRITICAL': 1,
        'WARNING': 2,
        'INFO': 3,
    }
    
    # Use Case/When for proper SQL ordering
    from django.db.models import Case, When, IntegerField
    alerts_qs = alerts_qs.annotate(
        severity_rank=Case(
            When(severity='CRITICAL', then=1),
            When(severity='WARNING', then=2),
            When(severity='INFO', then=3),
            default=4,
            output_field=IntegerField()
        )
    ).order_by('severity_rank', '-created_at')
    
    # Pagination (optional, default: return all active alerts)
    limit = int(request.GET.get('limit', 50))  # Max 50 alerts by default
    alerts_qs = alerts_qs[:limit]
    
    # Serialize to JSON
    alerts_data = []
    for alert in alerts_qs:
        alerts_data.append({
            'id': alert.id,
            'severity': alert.severity,
            'type': alert.alert_type,
            'type_display': alert.get_alert_type_display(),
            'title': alert.title,
            'message': alert.message,
            'machine_code': alert.machine.code if alert.machine else None,
            'machine_name': alert.machine.name if alert.machine else None,
            'current_value': alert.current_value,
            'threshold': alert.threshold_value,
            'created_at': localtime(alert.created_at).isoformat(),
            'is_acknowledged': alert.is_acknowledged,
            'acknowledged_by': alert.acknowledged_by.username if alert.acknowledged_by else None,
            'time_ago': _get_time_ago(alert.created_at),  # Helper function below
        })
    
    return JsonResponse({
        'count': len(alerts_data),
        'alerts': alerts_data
    })


@login_required
def acknowledge_alert(request, alert_id):
    """
    API endpoint to acknowledge an alert (mark as acknowledged but keep active).
    Alert will remain active until the critical condition is resolved.
    Method: POST
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)
    
    from .models import Alert
    
    try:
        alert = Alert.objects.get(id=alert_id)
        alert.is_acknowledged = True
        alert.acknowledged_at = timezone.now()
        alert.acknowledged_by = request.user
        # Keep alert active until condition resolves (don't set is_active = False)
        alert.save(update_fields=['is_acknowledged', 'acknowledged_at', 'acknowledged_by'])
        
        return JsonResponse({
            'success': True,
            'message': 'Alert acknowledged successfully. Alert will remain visible until condition resolves.'
        })
    except Alert.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Alert not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
def get_alert_count(request):
    """
    API endpoint to get count of unacknowledged active alerts.
    Used for badge counter on notification bell.
    """
    from .models import Alert
    
    # [K5] Menggabungkan 3 query terpisah menjadi 1 query aggregate
    # API ini dipanggil berkali-kali oleh frontend untuk badge notifikasi
    # Sebelumnya: 3 round-trips ke PostgreSQL per polling
    # Sesudah: 1 round-trip dengan conditional COUNT
    from django.db.models import Count, Q

    counts = Alert.objects.filter(is_active=True, is_acknowledged=False).aggregate(
        total=Count('id'),
        critical=Count('id', filter=Q(severity='CRITICAL')),
        warning=Count('id', filter=Q(severity='WARNING')),
    )

    return JsonResponse({
        'total_count': counts['total'],
        'critical_count': counts['critical'],
        'warning_count': counts['warning'],
    })


def _get_time_ago(dt):
    """Helper function to get human-readable time difference."""
    from django.utils import timezone
    
    now = timezone.now()
    diff = now - dt
    
    if diff.days > 0:
        return f"{diff.days}d ago"
    elif diff.seconds >= 3600:
        hours = diff.seconds // 3600
        return f"{hours}h ago"
    elif diff.seconds >= 60:
        minutes = diff.seconds // 60
        return f"{minutes}m ago"
    else:
        return "just now"

@login_required
def daily_batch_overview(request):
    """
    Menampilkan semua batch DyeingProcess dalam satu hari dengan preview grafik (Sparklines)
    dan pagination. Klik grafik akan diarahkan ke dyeing_analytics_report.
    """
    from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
    from django.utils import timezone as dt_timezone
    import json
    from datetime import datetime
    
    # 1. Get Date filter
    date_str = request.GET.get('date')
    if date_str:
        try:
            selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            selected_date = dt_timezone.localtime(dt_timezone.now()).date()
    else:
        selected_date = dt_timezone.localtime(dt_timezone.now()).date()
        
    # 2. Query DyeingProcess
    # Filter by the date of start_time
    qs = DyeingProcess.objects.filter(
        start_time__date=selected_date
    ).select_related('machine', 'machine__group', 'identity', 'identity__program').order_by('machine__code', 'start_time')
    
    # 3. Pagination (20 per page)
    paginator = Paginator(qs, 20)
    page_number = request.GET.get('page', 1)
    
    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)
        
    processes = page_obj.object_list
    
    # 4. Fetch logs for the paginated items and downsample
    chart_data = {}
    
    if processes:
        for process in processes:
            start_dt = process.start_time
            end_dt = process.end_time or dt_timezone.now()
            
            logs = MachineMinuteLog.objects.filter(
                machine=process.machine,
                timestamp__range=(start_dt, end_dt)
            ).order_by('timestamp').values_list('timestamp', 'temperature')
            
            logs_list = list(logs)
            total_logs = len(logs_list)
            
            target_points = 80  # Max 80 points to keep client rendering fast
            if total_logs > target_points:
                step = total_logs // target_points
                downsampled = logs_list[::step]
            else:
                downsampled = logs_list
                
            timestamps = []
            temps = []
            for ts, temp in downsampled:
                # Format to 'HH:MM' for x-axis
                timestamps.append(dt_timezone.localtime(ts).strftime('%H:%M'))
                temps.append(temp)
                
            chart_data[str(process.pk)] = {
                'timestamps': timestamps,
                'temperatures': temps
            }
            
            # Calculate derived metrics for display
            loss_time = None
            efficiency = None
            program = process.identity.program if hasattr(process, 'identity') and process.identity else None
            
            if program and program.durasi_ideal is not None and \
               process.duration_effective is not None and process.duration_effective > 0:
                loss_time = round(process.duration_effective - program.durasi_ideal, 1)
                efficiency = round((program.durasi_ideal / process.duration_effective) * 100, 1)
                
            process.display_loss_time = loss_time
            process.display_efficiency = efficiency
            process.display_program = program.nama if program else "N/A"
            process.display_start_time = dt_timezone.localtime(process.start_time).strftime('%H:%M')
            process.display_end_time = dt_timezone.localtime(process.end_time).strftime('%H:%M') if process.end_time else 'Now'

    context = {
        'page_obj': page_obj,
        'selected_date': selected_date.strftime('%Y-%m-%d'),
        'chart_data_json': json.dumps(chart_data),
        'total_batches_today': qs.count(),
    }
    
    return render(request, 'daily_batch_overview.html', context)


import pytz
from django.utils.dateparse import parse_datetime

def apidog_dyeing_process_lookup_api(request):
    """
    Lookup DyeingProcess by machine_code and time.
    Returns batch summary and parallel arrays for temperature and pressure time-series.
    """
    machine_code = request.GET.get('machine_code')
    time_str = request.GET.get('time')
    
    if not machine_code or not time_str:
        return JsonResponse({"success": False, "error": "machine_code and time are required"}, status=400)
    
    try:
        # Parse time string and convert to UTC
        # Assuming input is in WIB (Asia/Jakarta)
        wib_tz = pytz.timezone('Asia/Jakarta')
        
        # If naive, assume it's WIB
        parsed_time = parse_datetime(time_str)
        if parsed_time is None:
            return JsonResponse({"success": False, "error": "Invalid time format. Use ISO format, e.g., 2026-05-20T10:30:00"}, status=400)
            
        if timezone.is_naive(parsed_time):
            local_time = wib_tz.localize(parsed_time)
            query_time = local_time.astimezone(pytz.UTC)
        else:
            # If already aware, just use it
            query_time = parsed_time
            
    except Exception as e:
        return JsonResponse({"success": False, "error": f"Error parsing time: {str(e)}"}, status=400)

    # Lookup Machine
    try:
        machine = Machine.objects.get(code=machine_code)
    except Machine.DoesNotExist:
        return JsonResponse({"success": False, "error": f"Machine with code {machine_code} not found"}, status=404)

    # Lookup DyeingProcess where start_time <= query_time <= end_time
    # Or start_time <= query_time and end_time is None (process still running)
    from django.db.models import Q
    processes = DyeingProcess.objects.filter(
        Q(machine=machine),
        Q(start_time__lte=query_time),
        Q(end_time__gte=query_time) | Q(end_time__isnull=True)
    ).order_by('-start_time')

    if not processes.exists():
        return JsonResponse({"success": False, "error": f"No dyeing process found for {machine_code} at {query_time.strftime('%Y-%m-%d %H:%M:%S UTC')}"}, status=404)
        
    process = processes.first()
    
    # Helper to convert output times to WIB
    def to_wib_iso(dt):
        if dt:
            return dt.astimezone(wib_tz).isoformat()
        return None

    # Process basic info
    batch_info = {
        "batch_number": process.batch_number,
        "start_time": to_wib_iso(process.start_time),
        "end_time": to_wib_iso(process.end_time),
        "start_temp": process.start_temp,
        "max_temp": process.max_temp,
        "is_complete": process.is_complete,
        "total_duration": process.total_duration,
        "avg_steam_pressure": process.avg_steam_pressure,
    }
    
    # Add Identity Info if available
    try:
        identity = process.identity
        if identity:
            batch_info.update({
                "nomor_order": identity.nomor_order,
                "artikel_kain": identity.artikel_kain,
                "batch": identity.batch,
                "nomor_warna": identity.nomor_warna,
                "program": identity.program.nama if identity.program else None,
                "operator": identity.operator,
                "jenis_proses": identity.jenis_proses,
            })
    except Exception:
        pass

    # Fetch Time-Series Data
    # Determine bounds
    ts_start = process.start_time
    ts_end = process.end_time or timezone.now()
    
    # Fetch Temperature Logs
    temp_logs = MachineMinuteLog.objects.filter(
        machine=machine,
        timestamp__range=(ts_start, ts_end)
    ).order_by('timestamp').values('timestamp', 'temperature')
    
    # Create parallel arrays for Temperature
    # Users requested array of objects: "okay. Tapi itu kalau bisa array bukan single. Menurut mu bagaimana?"
    # Wait, "array bukan single" could mean array of objects: `[{"time":..., "temp":..., "press":...}]`
    # Let's align both Temp and Pressure by timestamp (truncate to minute)
    
    # Let's fetch Pressure Logs (Steam_Pr)
    try:
        steam_machine = Machine.objects.get(code="Steam_Pr")
        press_logs = MachineMinuteLog.objects.filter(
            machine=steam_machine,
            timestamp__range=(ts_start, ts_end)
        ).order_by('timestamp').values('timestamp', 'temperature') # pressure is stored in temperature field of Steam_Pr
    except Machine.DoesNotExist:
        press_logs = []
        
    # Build dictionary by minute for easy merging
    time_series_dict = {}
    
    for log in temp_logs:
        # Round down to minute to align easily
        ts = log['timestamp'].replace(second=0, microsecond=0)
        ts_str = to_wib_iso(ts)
        if ts_str not in time_series_dict:
            time_series_dict[ts_str] = {"timestamp": ts_str, "temperature": None, "pressure": None}
        time_series_dict[ts_str]["temperature"] = log['temperature']
        
    for log in press_logs:
        ts = log['timestamp'].replace(second=0, microsecond=0)
        ts_str = to_wib_iso(ts)
        if ts_str not in time_series_dict:
            time_series_dict[ts_str] = {"timestamp": ts_str, "temperature": None, "pressure": None}
        time_series_dict[ts_str]["pressure"] = log['temperature']
        
    # Sort and convert to list of objects
    sorted_timestamps = sorted(time_series_dict.keys())
    time_series_array = [time_series_dict[ts] for ts in sorted_timestamps]

    response_data = {
        "batch_info": batch_info,
        "time_series": time_series_array
    }

    return JsonResponse({
        "success": True,
        "data": response_data
    })

# --- CETAK STANDARD FLOW PROCESS ---

from monitoring.models import (
    StandardFlowProcess, FlowProcessGreige, FlowProcessCreeping,
    FlowProcessDryer, FlowProcessPreset, FlowProcessWR, FlowProcessCelup,
    FlowProcessDryerFinal, FlowProcessFinalSet
)

@login_required
def cetak_standard_flow(request, pk):
    master_flow = get_object_or_404(StandardFlowProcess, pk=pk)
    
    # Collect all child processes
    processes = []
    processes.extend(list(master_flow.flowprocessgreige_set.all()))
    processes.extend(list(master_flow.flowprocesscreeping_set.all()))
    processes.extend(list(master_flow.flowprocessdryer_set.all()))
    processes.extend(list(master_flow.flowprocesspreset_set.all()))
    processes.extend(list(master_flow.flowprocesswr_set.all()))
    processes.extend(list(master_flow.flowprocesscelup_set.all()))
    processes.extend(list(master_flow.flowprocessdryerfinal_set.all()))
    processes.extend(list(master_flow.flowprocessfinalset_set.all()))
    
    # Sort by urutan
    processes.sort(key=lambda x: x.urutan)
    
    exclude_fields = ['id', 'master_flow', 'master_flow_id', 'urutan']
    
    master_field_order = [
        'mesin', 'panjang_std', 'lebar', 'pick_mesin', 'pick_greige', 'berat_greige', 'gramasi',
        'program', 'temperatur', 'waktu', 'speed', 'set_lebar', 'blower', 'over_feed', 
        'tekanan_pompa', 'volume_air', 'nozzle', 'isi_per_tube', 'isi_per_batch',
        'coustic', 'persen_wr', 'silinder_dry', 'scutcher', 'centrifugal',
        'obat_list'
    ]
    
    field_labels = {
        'mesin': 'Mesin',
        'panjang_std': 'Panjang (YD)',
        'lebar': 'Lebar (CM)',
        'pick_mesin': 'Pick Mesin (T)',
        'pick_greige': 'Pick Greige (T)',
        'berat_greige': 'Berat Greige (KG)',
        'gramasi': 'Gramasi (GR/M2)',
        'program': 'Program',
        'temperatur': 'Temp °C',
        'waktu': 'Waktu (min)',
        'speed': 'Speed',
        'set_lebar': 'Set Lebar',
        'blower': 'Blower',
        'over_feed': 'Over Feed',
        'tekanan_pompa': 'Tekanan Pompa',
        'volume_air': 'Volume Air (L)',
        'nozzle': 'Nozzle',
        'isi_per_tube': 'Isi Per Tube',
        'isi_per_batch': 'Isi Per Batch',
        'coustic': 'Coustic',
        'persen_wr': '%WR',
        'silinder_dry': 'Silinder Dry',
        'scutcher': 'Scutcher',
        'centrifugal': 'Centrifugal',
        'obat_list': 'Obat',
        'catatan_koreksi': 'Catatan Koreksi',
        'resep': 'Resep',
    }

    # Build independent columns per process
    process_columns = []
    max_top_fields = 0
    for p in processes:
        p_top_fields = []
        
        # Pre-compute obat lists for Dryer Final
        if hasattr(p, 'obat_antistatic') or hasattr(p, 'obat_softener'):
            anti = list(p.obat_antistatic.all())
            soft = list(p.obat_softener.all())
            if anti or soft:
                p.has_obat = True
                p.anti_list = anti
                p.soft_list = soft
                
        for f in master_field_order:
            if f == 'obat_list':
                if getattr(p, 'has_obat', False):
                    anti = getattr(p, 'anti_list', [])
                    soft = getattr(p, 'soft_list', [])
                    if anti:
                        p_top_fields.append({"label": "Antistatic", "value": "", "is_merged": True})
                        for a in anti:
                            p_top_fields.append({"label": a.nama, "value": f"{a.persentase}%", "is_merged": False})
                    if soft:
                        p_top_fields.append({"label": "Softener", "value": "", "is_merged": True})
                        for s in soft:
                            p_top_fields.append({"label": s.nama, "value": f"{s.persentase}%", "is_merged": False})
            else:
                if hasattr(p, f):
                    val = getattr(p, f)
                    if isinstance(val, bool):
                        if val:
                            p_top_fields.append({"label": field_labels.get(f, f), "value": "Ya", "is_merged": False})
                    elif val is not None and val != "":
                        p_top_fields.append({"label": field_labels.get(f, f), "value": val, "is_merged": False})
                        
        # Slot Baris Khusus Catatan / Resep (agar Catatan Koreksi di Greige dan Resep di Creeping/Celup sejajar sebaris)
        note_label = ""
        note_val = ""
        if hasattr(p, 'catatan_koreksi') and p.catatan_koreksi:
            note_label = "Catatan Koreksi"
            note_val = p.catatan_koreksi
        elif hasattr(p, 'resep') and p.resep:
            note_label = "Resep"
            note_val = p.resep
            
        p_note_field = {"label": note_label, "value": note_val, "is_merged": False}

        # Append standard bottom fields
        p_bottom_fields = [
            {"label": "LEBAR", "value": p.hasil_lebar if p.hasil_lebar else "-", "is_merged": False},
            {"label": "PICK", "value": p.hasil_pick if p.hasil_pick else "-", "is_merged": False},
            {"label": "GRAMASI G/M2", "value": p.hasil_gramasi if p.hasil_gramasi else "-", "is_merged": False},
            {"label": "SUSUT PICK", "value": "-", "is_merged": False},
            {"label": "PANJANG PROSES", "value": p.hasil_panjang_jadi if p.hasil_panjang_jadi else "-", "is_merged": False},
        ]

        if len(p_top_fields) > max_top_fields:
            max_top_fields = len(p_top_fields)

        process_columns.append({
            'header': f"{p._meta.verbose_name.title().replace('Flow Process ', '')} #{p.urutan}",
            'top_fields': p_top_fields,
            'note_field': p_note_field,
            'bottom_fields': p_bottom_fields,
        })
            
    # Pad top_fields agar baris Catatan/Resep jatuh persis di baris yang sama di seluruh kolom
    for col in process_columns:
        while len(col['top_fields']) < max_top_fields:
            col['top_fields'].append({"label": "", "value": "", "is_merged": False})
        col['fields'] = col['top_fields'] + [col['note_field']] + col['bottom_fields']
            
    max_fields = max_top_fields + 1 + 5
            
    # Transpose for HTML row rendering
    vertical_rows = []
    for i in range(max_fields):
        row_data = []
        for col in process_columns:
            row_data.append(col['fields'][i])
        vertical_rows.append(row_data)
        
    process_headers = [col['header'] for col in process_columns]

    context = {
        'master': master_flow,
        'kain': master_flow.master_kain,
        'lusi_list': master_flow.master_kain.benang_lusi.all().order_by('urutan'),
        'pakan_list': master_flow.master_kain.benang_pakan.all().order_by('urutan'),
        'process_headers': process_headers,
        'vertical_rows': vertical_rows,
    }
    return render(request, 'monitoring/print_flow_process.html', context)


def machine_monthly_full_report(request, machine_id, date_str=None):
    """
    Laporan Komprehensif Bulanan Mesin (30 Hari) Siap Print (A4).
    Menampilkan:
    1. Scorecard Kesehatan Mesin (MHI, Grade, Availability, Tekanan Uap Rata-rata)
    2. Matriks Kepatuhan per Master Program (Resep) - Semua program tanpa dropdown
    3. Diagnostik Visual 4 Program Teratas:
       - Grafik Riwayat Durasi (Heating, Keep, Cooling vs Line Avg Pressure) + Tabel Komparasi
       - Grafik Korelasi Regresi Heating vs Tekanan Uap + Tabel Diagnostik Pemanas & Boiler
       - Grafik Korelasi Regresi Cooling vs Tekanan Uap + Tabel Diagnostik Pendingin & Sirkulasi
    4. Rekomendasi Perspektif Finansial & Diagnosis Preskriptif (Tanpa tabel batch mentah)
    5. Lembar Verifikasi Tanda Tangan Cetak
    """
    import json
    from datetime import datetime, timedelta
    from django.utils import timezone
    from django.shortcuts import get_object_or_404, render
    from monitoring.models import Machine
    from monitoring.utils.machine_fleet_summary import compute_machine_fleet_summary, linear_regression

    if not date_str or date_str in ("undefined", "null", ""):
        date_str = timezone.localtime(timezone.now()).strftime("%Y-%m-%d")

    # Fetch 30-day comprehensive summary
    summary = compute_machine_fleet_summary(date_str, window_str="30D")
    
    machine_data = None
    for m in summary.get("machines", []):
        if m.get("machine_id") == machine_id:
            machine_data = m
            break

    if not machine_data:
        machine_obj = get_object_or_404(Machine, pk=machine_id)
        machine_data = {
            "machine_id": machine_obj.id,
            "machine_name": machine_obj.name,
            "machine_code": machine_obj.code,
            "group_name": machine_obj.group.name if machine_obj.group else "-",
            "nominal_power_kw": getattr(machine_obj, 'nominal_power', 0.0) or 0.0,
            "evaluated_batches_count": 0,
            "health_score": 0.0,
            "health_grade": "D",
            "availability_pct": 0.0,
            "uptime_str": "0 Jam",
            "avg_steam_pressure": 0.0,
            "primary_diagnosis": {
                "tag": "NO_DATA",
                "title": "Tidak Ada Aktivitas Batch",
                "tone": "slate",
                "summary": "Mesin tidak mencatat batch proses dalam 30 hari terakhir.",
                "prescription": "Periksa koneksi sensor dan jadwal produksi."
            },
            "programs": [],
            "recent_batches": [],
            "waste_steam_kg": 0.0,
            "waste_power_kwh": 0.0,
            "waste_cost_rp": 0,
            "avg_waste_rp_batch": 0,
            "projected_30d_rp": 0,
            "projected_30d_steam_kg": 0,
            "projected_30d_power_kwh": 0,
        }

    # 1. Sort programs by batch count descending
    programs_list = machine_data.get("programs", [])
    sorted_programs = sorted(programs_list, key=lambda p: p.get("batch_count", 0), reverse=True)
    top_4_programs = sorted_programs[:4]

    # Pre-fetch interval pendinginan aktif seluruh pabrik (30 hari) untuk audit beban cooling serentak
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
    except (ValueError, TypeError):
        dt = timezone.localtime(timezone.now()).date()
    day_start = timezone.make_aware(datetime.combine(dt, datetime.min.time()).replace(hour=6, minute=0, second=0))
    day_end = day_start + timedelta(days=1)
    one_month_ago = day_end - timedelta(days=30)
    factory_cooling_intervals = []
    all_cooling_procs = DyeingProcess.objects.filter(
        is_valid_process=True,
        start_time__gte=one_month_ago,
        cooling_start_time__isnull=False
    ).values('id', 'cooling_start_time', 'reached_70c_time', 'end_time', 'cooling_duration')

    for cp in all_cooling_procs:
        cs = cp['cooling_start_time']
        ce = cp['reached_70c_time'] or (cs + timedelta(minutes=cp['cooling_duration']) if cp['cooling_duration'] else cp['end_time'])
        if cs and ce and ce > cs:
            factory_cooling_intervals.append((cp['id'], cs, ce))

    # Pre-fetch batas waktu batch mesin ini
    recent_batches_all = machine_data.get("recent_batches", [])
    m_batch_ids = [b.get("id") for b in recent_batches_all if b.get("id")]
    batch_timings = {
        p['id']: p
        for p in DyeingProcess.objects.filter(id__in=m_batch_ids).values(
            'id', 'cooling_start_time', 'reached_70c_time', 'end_time', 'cooling_duration'
        )
    }

    diagnostic_programs = []
    for idx, prog in enumerate(top_4_programs):
        pname = prog.get("program_name")
        p_batches = [b for b in reversed(recent_batches_all) if b.get("program_name") == pname]
        
        # 1. Riwayat Durasi Data
        chart_labels = [f"#{b.get('batch_number')} ({b.get('date_str')})" for b in p_batches]
        heat_data = [b.get("heat_mins") or 0 for b in p_batches]
        keep_data = [b.get("steady_mins") or 0 for b in p_batches]
        cool_data = [b.get("cool_mins") or 0 for b in p_batches]
        press_data = [b.get("avg_pressure") for b in p_batches]
        
        ideal_heat = prog.get("ideal_heat") or 60.0
        ideal_cool = prog.get("ideal_cool") or 20.0

        # 2. HEATING SCATTER: Durasi Heating vs Tekanan Uap (Kuadran Standar Machine-Daily-Report)
        heating_pts = []
        heating_colors = []
        for b in p_batches:
            if b.get("avg_pressure") is not None and b.get("heat_mins") is not None:
                p_bar = round(float(b["avg_pressure"]), 2)
                h_min = round(float(b["heat_mins"]), 1)
                dh = round(float(b.get("delta_heat") or (h_min - ideal_heat)), 1)
                
                # Pengelompokan Kuadran Heating
                if h_min <= ideal_heat + 5:
                    quad = "OPTIMAL"
                    color = "#10b981"  # Emerald
                    quad_label = "Optimal (Sesuai Resep)"
                elif p_bar >= 3.8:
                    quad = "MECHANICAL_DEGRADATION"
                    color = "#ef4444"  # Red
                    quad_label = "Kerak HE / Katup (Uap Cukup)"
                else:
                    quad = "BOILER_DROP"
                    color = "#f97316"  # Orange
                    quad_label = "Drop Boiler (< 3.8 bar)"
                    
                heating_pts.append({
                    "x": p_bar,
                    "y": h_min,
                    "batch": b.get("batch_number"),
                    "date": b.get("date_str"),
                    "delta": dh,
                    "quadrant": quad,
                    "quadrant_label": quad_label,
                    "color": color
                })
                heating_colors.append(color)
        
        reg_heat = linear_regression([{"x": pt["x"], "y": pt["y"]} for pt in heating_pts])
        heat_trendline = []
        if reg_heat and len(heating_pts) >= 2:
            min_x = min(pt["x"] for pt in heating_pts)
            max_x = max(pt["x"] for pt in heating_pts)
            slope = reg_heat.get("slope", 0)
            intercept = reg_heat.get("intercept", 0)
            heat_trendline = [
                {"x": round(min_x, 2), "y": round(slope * min_x + intercept, 1)},
                {"x": round(max_x, 2), "y": round(slope * max_x + intercept, 1)}
            ]

        total_h = len(heating_pts)
        heat_opt_cnt = sum(1 for pt in heating_pts if pt["quadrant"] == "OPTIMAL")
        heat_mech_cnt = sum(1 for pt in heating_pts if pt["quadrant"] == "MECHANICAL_DEGRADATION")
        heat_boiler_cnt = sum(1 for pt in heating_pts if pt["quadrant"] == "BOILER_DROP")

        heat_opt_pct = round(heat_opt_cnt / max(1, total_h) * 100, 1)
        heat_mech_pct = round(heat_mech_cnt / max(1, total_h) * 100, 1)
        heat_boiler_pct = round(heat_boiler_cnt / max(1, total_h) * 100, 1)

        # Heating Verdict
        if heat_boiler_pct >= 40.0:
            heat_verdict_title = "Didominasi Drop Suplai Boiler Pabrik"
            heat_verdict_desc = f"{heat_boiler_pct}% batch mengalami perlambatan akibat suplai uap drop < 3.8 bar. Korelasi r = {reg_heat.get('r') if reg_heat else '-'}. Kerusakan bukan murni mekanik mesin."
            heat_verdict_badge = "bg-amber-100 text-amber-900 border-amber-300"
        elif heat_mech_pct >= 25.0 or (reg_heat and (reg_heat.get('pred_at_4_5_bar') or 0) > ideal_heat + 10):
            heat_verdict_title = "Terindikasi Kerak Heat Exchanger / Katup Uap"
            heat_verdict_desc = f"{heat_mech_pct}% batch molor padahal uap stabil (>= 3.8 bar). Waktu pemanasan di 4.5 bar diproyeksi tetap terlambat ({reg_heat.get('pred_at_4_5_bar') if reg_heat else '-'} mnt). Perlu descaling HE."
            heat_verdict_badge = "bg-rose-100 text-rose-900 border-rose-300"
        else:
            heat_verdict_title = "Sistem Pemanasan Berjalan Prima"
            heat_verdict_desc = f"{heat_opt_pct}% batch tepat waktu sesuai resep standar ({ideal_heat} mnt). Tidak ada degradasi termal signifikan."
            heat_verdict_badge = "bg-emerald-100 text-emerald-900 border-emerald-300"

        # 3. COOLING SCATTER: Durasi Cooling vs Beban Mesin Cooling Bersamaan (Fair Comparison)
        cooling_pts = []
        cooling_colors = []
        for b in p_batches:
            if b.get("cool_mins") is not None:
                c_min = round(float(b["cool_mins"]), 1)
                dc = round(float(b.get("delta_cool") or (c_min - ideal_cool)), 1)
                
                # Hitung beban mesin cooling serentak pabrik saat batch ini berlangsung
                bt = batch_timings.get(b.get("id"))
                avg_mc = 1.0
                if bt:
                    cs = bt['cooling_start_time']
                    ce = bt['reached_70c_time'] or (cs + timedelta(minutes=bt['cooling_duration']) if (cs and bt['cooling_duration']) else bt['end_time'])
                    if not cs and bt['end_time'] and bt['cooling_duration']:
                        ce = bt['end_time']
                        cs = ce - timedelta(minutes=bt['cooling_duration'])
                    if cs and ce and ce > cs:
                        dur = (ce - cs).total_seconds() / 60.0
                        overlap_mins = 0.0
                        for opid, ocs, oce in factory_cooling_intervals:
                            if ocs < ce and oce > cs:
                                ov_s = max(cs, ocs)
                                ov_e = min(ce, oce)
                                overlap_mins += (ov_e - ov_s).total_seconds() / 60.0
                        avg_mc = round(overlap_mins / dur, 1)

                # Pengelompokan Kuadran Cooling (Fair: vs Beban Air Pendingin)
                if c_min <= ideal_cool + 5:
                    c_quad = "OPTIMAL"
                    c_color = "#10b981"  # Emerald
                    c_quad_label = "Optimal (Sesuai Resep)"
                elif avg_mc < 4.0:
                    c_quad = "INTERNAL_DEGRADATION"
                    c_color = "#ef4444"  # Red
                    c_quad_label = "Kerak HE / Katup (Pabrik Sepi)"
                else:
                    c_quad = "CONCURRENT_LOAD"
                    c_color = "#0284c7"  # Sky Blue
                    c_quad_label = "Beban Puncak Serentak (>= 4 Mesin)"

                cooling_pts.append({
                    "x": avg_mc,
                    "y": c_min,
                    "batch": b.get("batch_number"),
                    "date": b.get("date_str"),
                    "delta": dc,
                    "quadrant": c_quad,
                    "quadrant_label": c_quad_label,
                    "color": c_color
                })
                cooling_colors.append(c_color)

        reg_cool = linear_regression([{"x": pt["x"], "y": pt["y"]} for pt in cooling_pts])
        cool_trendline = []
        if reg_cool and len(cooling_pts) >= 2:
            min_x = min(pt["x"] for pt in cooling_pts)
            max_x = max(pt["x"] for pt in cooling_pts)
            slope = reg_cool.get("slope", 0)
            intercept = reg_cool.get("intercept", 0)
            cool_trendline = [
                {"x": round(min_x, 1), "y": round(slope * min_x + intercept, 1)},
                {"x": round(max_x, 1), "y": round(slope * max_x + intercept, 1)}
            ]

        total_c = len(cooling_pts)
        cool_opt_cnt = sum(1 for pt in cooling_pts if pt["quadrant"] == "OPTIMAL")
        cool_mech_cnt = sum(1 for pt in cooling_pts if pt["quadrant"] == "INTERNAL_DEGRADATION")
        cool_load_cnt = sum(1 for pt in cooling_pts if pt["quadrant"] == "CONCURRENT_LOAD")

        cool_opt_pct = round(cool_opt_cnt / max(1, total_c) * 100, 1)
        cool_mech_pct = round(cool_mech_cnt / max(1, total_c) * 100, 1)
        cool_load_pct = round(cool_load_cnt / max(1, total_c) * 100, 1)
        avg_load_val = round(sum(pt["x"] for pt in cooling_pts) / max(1, total_c), 1)

        # Cooling Verdict
        if cool_load_pct >= 40.0:
            cool_verdict_title = "Didominasi Perebutan Air Pendingin Pabrik"
            cool_verdict_desc = f"{cool_load_pct}% batch melambat saat puncak beban pendinginan pabrik (>= 4.0 mesin cooling serentak, rata-rata {avg_load_val} mesin). Suplai air pendingin terbagi; perlu staggering jadwal."
            cool_verdict_badge = "bg-sky-100 text-sky-900 border-sky-300"
        elif cool_mech_pct >= 25.0:
            cool_verdict_title = "Terindikasi Kerak Heat Exchanger / Katup Pendingin Macet"
            cool_verdict_desc = f"{cool_mech_pct}% batch molor saat pabrik sepi (< 4.0 mesin cooling). Suplai air pendingin longgar namun penyerapan dingin mesin tetap lambat. Jadwalkan descaling HE & cek filter inlet."
            cool_verdict_badge = "bg-rose-100 text-rose-900 border-rose-300"
        else:
            cool_verdict_title = "Sistem Pendinginan Prima"
            cool_verdict_desc = f"{cool_opt_pct}% batch pendinginan tepat waktu sesuai resep ({ideal_cool} mnt). Sirkulasi pendinginan mesin bekerja sangat baik."
            cool_verdict_badge = "bg-emerald-100 text-emerald-900 border-emerald-300"

        diagnostic_programs.append({
            "index": idx + 1,
            "chart_id": f"prog_{idx + 1}",
            "program_name": pname,
            "batch_count": prog.get("batch_count", 0),
            "info": prog,
            "durations_chart_json": json.dumps({
                "labels": chart_labels,
                "heat": heat_data,
                "keep": keep_data,
                "cool": cool_data,
                "pressure": press_data,
                "avg_heat": prog.get("avg_heat"),
                "avg_keep": prog.get("avg_steady"),
                "avg_cool": prog.get("avg_cool"),
                "ideal_heat": ideal_heat,
                "ideal_keep": prog.get("ideal_steady"),
                "ideal_cool": ideal_cool,
            }),
            "heat_scatter_json": json.dumps({
                "points": heating_pts,
                "colors": heating_colors,
                "trendline": heat_trendline,
                "ideal_heat": ideal_heat,
                "r": reg_heat.get("r") if reg_heat else None,
                "slope": reg_heat.get("slope") if reg_heat else None,
                "intercept": reg_heat.get("intercept") if reg_heat else None,
                "pred_4_5": reg_heat.get("pred_at_4_5_bar") if reg_heat else None
            }),
            "cool_scatter_json": json.dumps({
                "points": cooling_pts,
                "colors": cooling_colors,
                "trendline": cool_trendline,
                "ideal_cool": ideal_cool,
                "load_threshold": 4.0,
                "r": reg_cool.get("r") if reg_cool else None,
                "slope": reg_cool.get("slope") if reg_cool else None,
                "intercept": reg_cool.get("intercept") if reg_cool else None
            }),
            "diag_heat": {
                "total_batches": total_h,
                "optimal_count": heat_opt_cnt,
                "optimal_pct": heat_opt_pct,
                "mech_count": heat_mech_cnt,
                "mech_pct": heat_mech_pct,
                "boiler_count": heat_boiler_cnt,
                "boiler_pct": heat_boiler_pct,
                "r": reg_heat.get("r") if reg_heat else "-",
                "slope": reg_heat.get("slope") if reg_heat else "-",
                "pred_4_5": reg_heat.get("pred_at_4_5_bar") if reg_heat else "-",
                "verdict_title": heat_verdict_title,
                "verdict_desc": heat_verdict_desc,
                "verdict_badge": heat_verdict_badge
            },
            "diag_cool": {
                "total_batches": total_c,
                "optimal_count": cool_opt_cnt,
                "optimal_pct": cool_opt_pct,
                "mech_count": cool_mech_cnt,
                "mech_pct": cool_mech_pct,
                "load_count": cool_load_cnt,
                "load_pct": cool_load_pct,
                "avg_concurrent": avg_load_val,
                "r": reg_cool.get("r") if reg_cool else "-",
                "slope": reg_cool.get("slope") if reg_cool else "-",
                "verdict_title": cool_verdict_title,
                "verdict_desc": cool_verdict_desc,
                "verdict_badge": cool_verdict_badge
            }
        })

    # Financial Actions Recommendations
    rec_actions = []
    waste_rp = machine_data.get("projected_30d_rp", 0) or 0
    if machine_data.get("waste_steam_kg", 0) > 800:
        rec_actions.append({
            "action": "Chemical Descaling Tabung Heat Exchanger & Inspeksi Steam Trap",
            "component": "Penukar Panas (HE) & Katup Uap",
            "impact": "Memangkas waktu siklus pemanasan rata-rata 15-25 menit per batch",
            "est_savings": f"Rp {round(waste_rp * 0.6):,}".replace(",", ".")
        })
    if machine_data.get("waste_power_kwh", 0) > 150:
        rec_actions.append({
            "action": "Audit Waktu Holding & Optimalisasi Resep Standar",
            "component": "SOP Operator & Sirkulasi Pompa Utama",
            "impact": "Mengurangi pemborosan listrik motor sirkulasi saat holding berlebih",
            "est_savings": f"Rp {round(waste_rp * 0.25):,}".replace(",", ".")
        })
    rec_actions.append({
        "action": "Inspeksi Kalibrasi Katup Pneumatik & Strainer Pendingin",
        "component": "Cooling Valve & Saringan Air Masuk",
        "impact": "Menstabilkan laju pendinginan kain dan mencegah over-cooling",
        "est_savings": f"Rp {round(waste_rp * 0.15):,}".replace(",", ".")
    })

    context = {
        "company_profile": CompanyProfile.objects.first(),
        "m": machine_data,
        "date_str": date_str,
        "date_range_label": summary.get("date_range_label", ""),
        "print_date": timezone.localtime(timezone.now()).strftime("%d %B %Y, %H:%M WIB"),
        "all_programs": sorted_programs,
        "top_programs": diagnostic_programs,
        "rec_actions": rec_actions,
        "factory_name": "PT. SURITEX",
    }
    return render(request, "monitoring/machine_monthly_full_report.html", context)
