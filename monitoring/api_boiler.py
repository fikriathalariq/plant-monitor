import math
from datetime import timedelta
from collections import defaultdict
from ninja import Router
from django.utils import timezone
from django.utils.timezone import localtime

from monitoring.models import Machine, MachineMinuteLog, MachineStatusSnapshot, GlobalSettings
from monitoring.api_report import _detect_boiler_regulations
from monitoring.utils.steam_active import is_steam_active_from_machine, is_steam_active_from_snapshot

boiler_router = Router(tags=["Boiler Utility"])


@boiler_router.get("/utility-telemetry")
def get_boiler_utility_telemetry(request, channel: str = "steam", hours: int = 4):
    """
    Endpoint telemetri komprehensif untuk halaman khusus Boiler Steam & Boiler HTO (Utility Home).
    Mendukung filter range: 2, 4, 8, 12, 24 jam.
    Mengembalikan data realtime, daily KPI (regulasi & drop), serta deret waktu untuk 2 grafik.
    """
    channel = channel.lower().strip()
    if channel not in ("steam", "hto"):
        channel = "steam"

    valid_hours = (2, 4, 8, 12, 24)
    if hours not in valid_hours:
        hours = 4

    now = timezone.now()
    start_time = now - timedelta(hours=hours)

    settings = GlobalSettings.load()

    # 1. Tentukan target points & interval menit
    if hours <= 2:
        target_points = 60    # 1 titik / 2 menit
    elif hours <= 4:
        target_points = 80    # 1 titik / 3 menit
    elif hours <= 8:
        target_points = 96    # 1 titik / 5 menit
    elif hours <= 12:
        target_points = 120   # 1 titik / 6 menit
    else:  # 24h
        target_points = 144   # 1 titik / 10 menit

    interval_minutes = (hours * 60) / target_points

    # 2. Setup kode sensor sesuai channel
    if channel == "steam":
        primary_code = "Steam_Pr"
        speed_code = "Speed_RB_Steam"
        temp_code = "Temp_RB_Steam"
        drop_threshold = 3.5  # barg
        reg_min_val = getattr(settings, 'boiler_regulation_pressure_min', 5.0)
        primary_unit = "bar"
    else:
        primary_code = "Oil_Temp"
        speed_code = "Speed_R_Bakar"
        temp_code = "Temp_R_Bakar"
        drop_threshold = 235.0  # °C
        reg_min_val = getattr(settings, 'boiler_regulation_hto_oil_temp_min', 244.0)
        primary_unit = "°C"

    reg_max_speed = getattr(settings, 'boiler_regulation_speed_max', 0.5)

    # 3. Ambil seluruh mesin untuk perhitungan beban
    all_machines = list(Machine.objects.filter(is_active=True).select_related('group'))
    machines_dict = {m.code: m for m in all_machines}

    # 4. Hitung Realtime Status
    primary_mc = machines_dict.get(primary_code)
    speed_mc = machines_dict.get(speed_code)
    temp_mc = machines_dict.get(temp_code)

    current_primary_val = round(primary_mc.temperature, 2) if primary_mc and primary_mc.temperature is not None else None
    current_speed_val = round(speed_mc.temperature, 2) if speed_mc and speed_mc.temperature is not None else None
    current_temp_val = round(temp_mc.temperature, 1) if temp_mc and temp_mc.temperature is not None else None

    # Beban pemakaian saat ini
    current_steam_kg = 0.0
    current_hto_cal = 0.0
    steam_mc_count = 0
    hto_mc_count = 0

    for m in all_machines:
        if m.group and m.group.code == 'MC_BOILER':
            continue
        is_running = is_steam_active_from_machine(m)
        if (m.average_steam_usage or 0) > 0 and is_running:
            steam_mc_count += 1
            current_steam_kg += (m.average_steam_usage or 0)
        if (m.avg_hto_calories or 0) > 0 and is_running:
            hto_mc_count += 1
            current_hto_cal += (m.avg_hto_calories or 0)

    if channel == "steam":
        current_usage_val = round(current_steam_kg / 1000.0, 1)
        current_usage_str = f"{current_usage_val:.1f} ton/jam".replace('.', ',')
        active_mc_count = steam_mc_count
    else:
        current_usage_val = round(current_hto_cal / 1000000.0, 1)
        current_usage_str = f"{current_usage_val:.1f} jt kcal".replace('.', ',')
        active_mc_count = hto_mc_count

    # Status status badge
    if current_primary_val is None:
        status_badge = "NO_SIGNAL"
    elif current_speed_val is not None and current_speed_val <= reg_max_speed and current_primary_val >= reg_min_val:
        status_badge = "REGULASI"
    elif current_primary_val < drop_threshold:
        status_badge = "DROP"
    else:
        status_badge = "NORMAL"

    # 5. Hitung KPI Harian (06:00 boiler day s/d sekarang)
    local_now = localtime(now)
    boiler_day_start = local_now.replace(hour=6, minute=0, second=0, microsecond=0)
    if local_now.hour < 6:
        boiler_day_start -= timedelta(days=1)

    min_valid_temp = 0.5 if channel == "steam" else 50.0

    # Durasi Drop Harian (menit)
    daily_drop_minutes = MachineMinuteLog.objects.filter(
        machine__code=primary_code,
        timestamp__gte=boiler_day_start,
        timestamp__lte=now,
        temperature__lt=drop_threshold,
        temperature__gt=min_valid_temp
    ).count()

    # Regulasi Harian
    reg_channel = "STEAM" if channel == "steam" else "HTO"
    day_logs = MachineMinuteLog.objects.filter(
        machine__code__in=[speed_code, primary_code],
        timestamp__gte=boiler_day_start,
        timestamp__lte=now
    ).values('machine__code', 'timestamp', 'temperature')

    minute_dict = defaultdict(dict)
    for l in day_logs:
        t_key = localtime(l['timestamp']).strftime('%H:%M')
        minute_dict[t_key][l['machine__code']] = l['temperature']
        minute_dict[t_key]['time'] = t_key

    sorted_minute_data = [minute_dict[k] for k in sorted(minute_dict.keys())]
    detected_events = _detect_boiler_regulations(sorted_minute_data, settings)
    daily_reg_count = sum(1 for e in detected_events if e['channel'] == reg_channel)

    # Cek apakah ada regulasi beberapa menit sebelumnya (jendela 20 menit)
    recent_cutoff_time = local_now - timedelta(minutes=20)
    recent_cutoff_str = recent_cutoff_time.strftime('%H:%M')
    has_recent_regulation = any(
        e['channel'] == reg_channel and e['start_time'] >= recent_cutoff_str
        for e in detected_events
    )
    if current_speed_val is not None and current_speed_val <= reg_max_speed and current_primary_val is not None and current_primary_val >= reg_min_val:
        has_recent_regulation = True

    # 5b. Histori Event Regulasi & Drop Hari Ini (sejak 06:00)
    history_events = []

    # 1. Regulasi
    for e in detected_events:
        if e['channel'] == reg_channel:
            dur = e['duration_minutes']
            history_events.append({
                "time": e['start_time'],
                "type": "REGULASI",
                "label": f"Regulasi - {dur} menit",
                "duration_minutes": dur,
                "peak_value": round(e['peak_value'], 2) if e.get('peak_value') is not None else None,
            })

    # 2. Drop Pressure / Temperature
    current_drop = None
    for log in sorted_minute_data:
        temp = log.get(primary_code)
        time_str = log.get('time', '00:00')
        if temp is not None and min_valid_temp < temp < drop_threshold:
            if current_drop is None:
                current_drop = {
                    'start_time': time_str,
                    'duration_minutes': 1,
                    'min_value': temp,
                }
            else:
                current_drop['duration_minutes'] += 1
                current_drop['min_value'] = min(current_drop['min_value'], temp)
        else:
            if current_drop is not None:
                dur = current_drop['duration_minutes']
                history_events.append({
                    "time": current_drop['start_time'],
                    "type": "DROP",
                    "label": f"Drop < {drop_threshold} {primary_unit}" + (f" ({dur} menit)" if dur > 1 else ""),
                    "duration_minutes": dur,
                    "min_value": round(current_drop['min_value'], 2),
                })
                current_drop = None
    if current_drop is not None:
        dur = current_drop['duration_minutes']
        history_events.append({
            "time": current_drop['start_time'],
            "type": "DROP",
            "label": f"Drop < {drop_threshold} {primary_unit}" + (f" ({dur} menit)" if dur > 1 else ""),
            "duration_minutes": dur,
            "min_value": round(current_drop['min_value'], 2),
        })

    # Urutkan event descending (jam terbaru paling atas)
    history_events.sort(key=lambda x: x['time'], reverse=True)

    # 6. Agregasi Deret Waktu untuk 2 Grafik
    # Ambil logs sensor
    target_sensor_codes = [primary_code, speed_code, temp_code]
    sensor_logs = MachineMinuteLog.objects.filter(
        machine__code__in=target_sensor_codes,
        timestamp__gte=start_time,
        timestamp__lte=now
    ).values('machine__code', 'timestamp', 'temperature')

    bucket_sensors = defaultdict(lambda: {c: {'sum': 0.0, 'count': 0} for c in target_sensor_codes})
    for l in sensor_logs:
        val = l['temperature']
        if val is not None:
            diff_min = (l['timestamp'] - start_time).total_seconds() / 60
            b_idx = int(diff_min / interval_minutes)
            if 0 <= b_idx < target_points:
                code = l['machine__code']
                bucket_sensors[b_idx][code]['sum'] += val
                bucket_sensors[b_idx][code]['count'] += 1

    # Ambil snapshots beban pemakaian
    snapshots = MachineStatusSnapshot.objects.filter(
        timestamp__gte=start_time,
        timestamp__lte=now
    ).values('timestamp', 'snapshot_data')

    bucket_usage = defaultdict(lambda: {'total': 0.0, 'count': 0})
    for snap in snapshots:
        diff_min = (snap['timestamp'] - start_time).total_seconds() / 60
        b_idx = int(diff_min / interval_minutes)
        if 0 <= b_idx < target_points:
            snap_data = snap.get('snapshot_data') or {}
            usage_sum = 0.0
            for mc_code, s_info in snap_data.items():
                m = machines_dict.get(mc_code)
                if not m or (m.group and m.group.code == 'MC_BOILER'):
                    continue
                if is_steam_active_from_snapshot(s_info):
                    if channel == "steam":
                        usage_sum += (m.average_steam_usage or 0.0)
                    else:
                        usage_sum += (m.avg_hto_calories or 0.0)

            bucket_usage[b_idx]['total'] += usage_sum
            bucket_usage[b_idx]['count'] += 1

    chart_data = []
    for i in range(target_points):
        b_time = start_time + timedelta(minutes=i * interval_minutes)
        if b_time > now:
            break

        time_label = localtime(b_time).strftime("%H:%M")

        # Sensor values
        s_data = bucket_sensors[i]
        prim_val = round(s_data[primary_code]['sum'] / s_data[primary_code]['count'], 2) if s_data[primary_code]['count'] > 0 else None
        spd_val = round(s_data[speed_code]['sum'] / s_data[speed_code]['count'], 2) if s_data[speed_code]['count'] > 0 else None
        tmp_val = round(s_data[temp_code]['sum'] / s_data[temp_code]['count'], 1) if s_data[temp_code]['count'] > 0 else None

        # Usage value
        u_data = bucket_usage[i]
        if u_data['count'] > 0:
            raw_usage = u_data['total'] / u_data['count']
            usage_val = round(raw_usage / 1000.0, 2) if channel == "steam" else round(raw_usage / 1000000.0, 2)
        else:
            usage_val = None

        chart_data.append({
            "time": time_label,
            "timestamp": b_time.isoformat(),
            "primary_val": prim_val,
            "usage": usage_val,
            "speed_coal": spd_val,
            "temp_chamber": tmp_val,
        })

    return {
        "channel": channel,
        "hours": hours,
        "realtime": {
            "value": current_primary_val,
            "unit": primary_unit,
            "usage": current_usage_str,
            "usage_val": current_usage_val,
            "active_mc": active_mc_count,
            "speed_coal": current_speed_val,
            "temp_chamber": current_temp_val,
            "status": status_badge,
            "has_recent_regulation": has_recent_regulation,
            "combustion_badge": "Regulasi" if has_recent_regulation else "OK",
        },
        "daily_kpi": {
            "regulation_count": daily_reg_count,
            "drop_minutes": daily_drop_minutes,
            "drop_threshold": drop_threshold,
            "regulation_min_val": reg_min_val,
            "regulation_max_speed": reg_max_speed,
            "boiler_day_start": boiler_day_start.strftime("%H:%M"),
        },
        "history_events": history_events,
        "chart_data": chart_data,
    }
