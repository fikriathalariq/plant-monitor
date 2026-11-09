from datetime import datetime, timedelta
from collections import defaultdict
from django.utils import timezone
from monitoring.models import (
    Machine,
    MachineMinuteLog,
    MachineStatusSnapshot,
    GlobalSettings,
    Alert,
    BoilerDailyMetric,
    DyeingProcess,
)
from monitoring.utils.steam_active import is_steam_active_from_snapshot


class BoilerAnalyticsService:
    """
    Service terpusat untuk analitik boiler (Steam & HTO), agregasi telemetri 10-menit,
    deteksi event regulasi tekanan/suhu, persistensi metrik harian, dan baseline mingguan.
    """

    MACHINES = ["Steam_Pr", "Speed_RB_Steam", "Temp_RB_Steam", "Oil_Temp", "Temp_R_Bakar", "Speed_R_Bakar"]
    INTERVAL_MINUTES = 10
    TARGET_POINTS = 144

    @classmethod
    def compute_chart_data(cls, start_time, end_time, settings):
        """Build chart_data and pressure_dist for one boiler day window (06:00–06:00)."""
        interval_minutes = cls.INTERVAL_MINUTES
        target_points = cls.TARGET_POINTS

        snapshots = MachineStatusSnapshot.objects.filter(
            timestamp__gte=start_time,
            timestamp__lt=end_time
        ).order_by('timestamp')

        all_machines = Machine.objects.filter(is_active=True).select_related('group')
        machines_dict = {m.code: m for m in all_machines}

        interval_data = defaultdict(lambda: {'steam_total': 0.0, 'hto_total': 0.0, 'power_total': 0.0, 'active_count': 0, 'count': 0})
        for snapshot in snapshots:
            time_diff = (snapshot.timestamp - start_time).total_seconds() / 60
            bucket_index = int(time_diff / interval_minutes)
            if bucket_index >= target_points:
                bucket_index = target_points - 1
            if bucket_index < 0:
                bucket_index = 0

            steam_total = 0.0
            steam_total_jet = 0.0
            steam_total_non_jet = 0.0
            hto_total = 0.0
            power_total = 0.0
            active_count = 0
            for machine_code, snap_data in snapshot.snapshot_data.items():
                machine = machines_dict.get(machine_code)
                if machine:
                    # Steam
                    is_steam_active = is_steam_active_from_snapshot(snap_data)
                    if is_steam_active:
                        steam_total += (machine.average_steam_usage or 0)
                        if machine.group and machine.group.process_type == 'JET':
                            steam_total_jet += (machine.average_steam_usage or 0)
                        else:
                            steam_total_non_jet += (machine.average_steam_usage or 0)

                    # HTO & Power
                    status = snap_data.get('status')
                    detail = snap_data.get('detail')
                    is_machine_active = (status in ["HEAT", "STEADY", "Running", "COOL"]) or (detail in ["HEAT", "STEADY", "Running", "COOL"])
                    
                    if is_machine_active:
                        is_boiler = bool(machine.group and machine.group.code == "MC_BOILER")
                        if not is_boiler:
                            power_total += (machine.nominal_power or 0.0)
                            active_count += 1
                            if machine.avg_hto_calories and machine.avg_hto_calories > 0:
                                hto_total += machine.avg_hto_calories

            bucket = interval_data[bucket_index]
            bucket['steam_total'] += steam_total
            bucket['steam_total_jet'] = bucket.get('steam_total_jet', 0.0) + steam_total_jet
            bucket['steam_total_non_jet'] = bucket.get('steam_total_non_jet', 0.0) + steam_total_non_jet
            bucket['hto_total'] += hto_total
            bucket['power_total'] += power_total
            bucket['active_count'] += active_count
            bucket['count'] += 1

        logs_qs = MachineMinuteLog.objects.filter(
            machine__code__in=cls.MACHINES,
            timestamp__gte=start_time,
            timestamp__lt=end_time
        ).values('timestamp', 'machine__code', 'temperature')

        boiler_data = defaultdict(lambda: {m: {'total': 0.0, 'count': 0} for m in cls.MACHINES})
        minute_raw = defaultdict(lambda: {m: {'total': 0.0, 'count': 0} for m in cls.MACHINES})
        for log in logs_qs:
            ts = log['timestamp']
            val = log['temperature']
            code = log['machine__code']
            if val is not None:
                m_diff = int((ts - start_time).total_seconds() / 60)
                if 0 <= m_diff < target_points * interval_minutes:
                    minute_raw[m_diff][code]['total'] += val
                    minute_raw[m_diff][code]['count'] += 1

                time_diff = (ts - start_time).total_seconds() / 60
                bucket_index = int(time_diff / interval_minutes)
                if 0 <= bucket_index < target_points:
                    boiler_data[bucket_index][code]['total'] += val
                    boiler_data[bucket_index][code]['count'] += 1

        minute_data = []
        for m_idx in range(target_points * interval_minutes):
            pt_time = start_time + timedelta(minutes=m_idx)
            raw_point = {'time': timezone.localtime(pt_time).strftime('%H:%M')}
            for code in cls.MACHINES:
                info = minute_raw[m_idx][code]
                raw_point[code] = (info['total'] / info['count']) if info['count'] > 0 else None
            minute_data.append(raw_point)

        bucket_hours = interval_minutes / 60
        chart_data = []
        pressure_dist = {'ideal': 0, 'under': 0, 'over': 0}

        for i in range(target_points):
            bucket_time = start_time + timedelta(minutes=i * interval_minutes)
            data_point = {
                'time': timezone.localtime(bucket_time).strftime('%H:%M'),
                'datetime': timezone.localtime(bucket_time).strftime('%Y-%m-%d %H:%M'),
            }

            snap_bucket = interval_data[i]
            count = snap_bucket['count']
            if count > 0:
                data_point['steam_usage'] = round(snap_bucket['steam_total'] / count, 1)
                data_point['usage_jet'] = round(snap_bucket.get('steam_total_jet', 0.0) / count, 1)
                data_point['usage_non_jet'] = round(snap_bucket.get('steam_total_non_jet', 0.0) / count, 1)
                data_point['hto_usage'] = round(snap_bucket['hto_total'] / count, 1)
                data_point['active_machines'] = round(snap_bucket['active_count'] / count, 1)
                data_point['power_usage'] = round(snap_bucket['power_total'] / count, 1)
            else:
                data_point['steam_usage'] = 0.0
                data_point['usage_jet'] = 0.0
                data_point['usage_non_jet'] = 0.0
                data_point['hto_usage'] = 0.0
                data_point['active_machines'] = 0.0
                data_point['power_usage'] = 0.0

            boiler_bucket = boiler_data[i]
            for code in cls.MACHINES:
                entry = boiler_bucket[code]
                if entry['count'] > 0:
                    val = entry['total'] / entry['count']
                    data_point[code] = round(val, 2)
                else:
                    data_point[code] = None

            speed_rb = data_point.get('Speed_RB_Steam')
            speed_r_bakar = data_point.get('Speed_R_Bakar')

            data_point['fuel_kg_steam'] = (
                round(speed_rb * settings.fuel_factor_steam_boiler * bucket_hours, 2)
                if speed_rb is not None and settings.fuel_factor_steam_boiler > 0 else None
            )
            data_point['fuel_kg_hto'] = (
                round(speed_r_bakar * settings.fuel_factor_hto_boiler * bucket_hours, 2)
                if speed_r_bakar is not None and settings.fuel_factor_hto_boiler > 0 else None
            )

            pr = data_point.get('Steam_Pr')
            if pr is not None and pr > 0:
                if pr < 3.5:
                    pressure_dist['under'] += 1
                elif pr > 5.5:
                    pressure_dist['over'] += 1
                else:
                    pressure_dist['ideal'] += 1

            chart_data.append(data_point)

        return minute_data, chart_data, pressure_dist

    @classmethod
    def compute_kpi_summary(cls, chart_data, pressure_dist, settings):
        """Aggregate daily KPIs from chart_data buckets."""
        bucket_hours = cls.INTERVAL_MINUTES / 60

        total_steam_usage_kg = 0.0
        pressure_values = []
        oil_temp_values = []
        total_fuel_steam = 0.0
        total_fuel_hto = 0.0
        has_fuel_steam = settings.fuel_factor_steam_boiler > 0
        has_fuel_hto = settings.fuel_factor_hto_boiler > 0

        total_steam_usage_jet_kg = 0.0
        total_steam_usage_non_jet_kg = 0.0
        for point in chart_data:
            steam_rate = point.get('steam_usage') or 0
            total_steam_usage_kg += steam_rate * bucket_hours
            total_steam_usage_jet_kg += (point.get('usage_jet') or 0) * bucket_hours
            total_steam_usage_non_jet_kg += (point.get('usage_non_jet') or 0) * bucket_hours

            pr = point.get('Steam_Pr')
            if pr is not None and pr > 0:
                pressure_values.append(pr)

            oil_temp = point.get('Oil_Temp')
            if oil_temp is not None and oil_temp > 0:
                oil_temp_values.append(oil_temp)

            fuel_steam = point.get('fuel_kg_steam')
            if fuel_steam is not None:
                total_fuel_steam += fuel_steam

            fuel_hto = point.get('fuel_kg_hto')
            if fuel_hto is not None:
                total_fuel_hto += fuel_hto

        total_fuel_kg = None
        if has_fuel_steam or has_fuel_hto:
            total_fuel_kg = round(total_fuel_steam + total_fuel_hto, 1)

        specific_fuel_consumption = None
        if total_fuel_steam and total_fuel_steam > 0:
            specific_fuel_consumption = round(total_steam_usage_kg / total_fuel_steam, 2)

        total_pressure_buckets = pressure_dist['ideal'] + pressure_dist['under'] + pressure_dist['over']
        pressure_ideal_percent = (
            round((pressure_dist['ideal'] / total_pressure_buckets) * 100, 1)
            if total_pressure_buckets > 0 else None
        )

        return {
            "total_steam_usage_kg": round(total_steam_usage_kg, 1),
            "total_steam_usage_jet_kg": round(total_steam_usage_jet_kg, 1),
            "total_steam_usage_non_jet_kg": round(total_steam_usage_non_jet_kg, 1),
            "avg_pressure": round(sum(pressure_values) / len(pressure_values), 2) if pressure_values else None,
            "avg_oil_temp": round(sum(oil_temp_values) / len(oil_temp_values), 1) if oil_temp_values else None,
            "total_fuel_kg": total_fuel_kg,
            "total_fuel_steam_kg": round(total_fuel_steam, 1) if has_fuel_steam else None,
            "total_fuel_hto_kg": round(total_fuel_hto, 1) if has_fuel_hto else None,
            "specific_fuel_consumption": specific_fuel_consumption,
            "pressure_ideal_percent": pressure_ideal_percent,
        }

    @classmethod
    def bucket_boiler_month_data(cls, month_start, days_in_month):
        """
        Bulk-query one month of boiler data (1 snapshot query + 1 minute-log query)
        and bucket it into per-day chart_data / pressure_dist pairs.
        """
        settings = GlobalSettings.load()
        interval_minutes = cls.INTERVAL_MINUTES
        target_points = cls.TARGET_POINTS
        month_end = month_start + timedelta(days=days_in_month)
        bucket_hours = interval_minutes / 60

        steam_buckets = [
            [{'steam_total': 0.0, 'count': 0} for _ in range(target_points)]
            for _ in range(days_in_month)
        ]
        boiler_buckets = [
            [{m: {'total': 0.0, 'count': 0} for m in cls.MACHINES} for _ in range(target_points)]
            for _ in range(days_in_month)
        ]

        def _day_and_bucket(ts):
            time_diff = (ts - month_start).total_seconds() / 60
            day_index = int(time_diff // (24 * 60))
            minute_in_day = time_diff % (24 * 60)
            bucket_index = int(minute_in_day // interval_minutes)
            if bucket_index >= target_points:
                bucket_index = target_points - 1
            if bucket_index < 0:
                bucket_index = 0
            return day_index, bucket_index

        all_machines = Machine.objects.filter(is_active=True).select_related('group')
        machines_dict = {m.code: m for m in all_machines}

        snapshots_qs = MachineStatusSnapshot.objects.filter(
            timestamp__gte=month_start,
            timestamp__lt=month_end,
        ).order_by('timestamp')

        for snapshot in snapshots_qs:
            day_idx, bucket_idx = _day_and_bucket(snapshot.timestamp)
            if not (0 <= day_idx < days_in_month):
                continue

            steam_total = 0.0
            steam_total_jet = 0.0
            steam_total_non_jet = 0.0
            for machine_code, snap_data in snapshot.snapshot_data.items():
                machine = machines_dict.get(machine_code)
                if machine and is_steam_active_from_snapshot(snap_data):
                    usage = machine.average_steam_usage or 0
                    steam_total += usage
                    if machine.group and machine.group.process_type == 'JET':
                        steam_total_jet += usage
                    else:
                        steam_total_non_jet += usage

            entry = steam_buckets[day_idx][bucket_idx]
            entry['steam_total'] += steam_total
            entry['steam_total_jet'] = entry.get('steam_total_jet', 0.0) + steam_total_jet
            entry['steam_total_non_jet'] = entry.get('steam_total_non_jet', 0.0) + steam_total_non_jet
            entry['count'] += 1

        logs_qs = MachineMinuteLog.objects.filter(
            machine__code__in=cls.MACHINES,
            timestamp__gte=month_start,
            timestamp__lt=month_end,
        ).values('timestamp', 'machine__code', 'temperature')

        for log in logs_qs:
            val = log['temperature']
            if val is None:
                continue
            day_idx, bucket_idx = _day_and_bucket(log['timestamp'])
            if not (0 <= day_idx < days_in_month):
                continue
            code = log['machine__code']
            if code in boiler_buckets[day_idx][bucket_idx]:
                entry = boiler_buckets[day_idx][bucket_idx][code]
                entry['total'] += val
                entry['count'] += 1

        results = []
        for day_index in range(days_in_month):
            day_start = month_start + timedelta(days=day_index)
            chart_data = []
            pressure_dist = {'ideal': 0, 'under': 0, 'over': 0}

            for i in range(target_points):
                bucket_time = day_start + timedelta(minutes=i * interval_minutes)
                data_point = {
                    'time': timezone.localtime(bucket_time).strftime('%H:%M'),
                    'datetime': timezone.localtime(bucket_time).strftime('%Y-%m-%d %H:%M'),
                }

                sb = steam_buckets[day_index][i]
                cnt = sb['count']
                if cnt > 0:
                    data_point['steam_usage'] = round(sb['steam_total'] / cnt, 1)
                    data_point['usage_jet'] = round(sb.get('steam_total_jet', 0.0) / cnt, 1)
                    data_point['usage_non_jet'] = round(sb.get('steam_total_non_jet', 0.0) / cnt, 1)
                else:
                    data_point['steam_usage'] = 0.0
                    data_point['usage_jet'] = 0.0
                    data_point['usage_non_jet'] = 0.0

                bb = boiler_buckets[day_index][i]
                for code in cls.MACHINES:
                    entry = bb[code]
                    if entry['count'] > 0:
                        data_point[code] = round(entry['total'] / entry['count'], 2)
                    else:
                        data_point[code] = None

                speed_rb = data_point.get('Speed_RB_Steam')
                speed_r_bakar = data_point.get('Speed_R_Bakar')

                data_point['fuel_kg_steam'] = (
                    round(speed_rb * settings.fuel_factor_steam_boiler * bucket_hours, 2)
                    if speed_rb is not None and settings.fuel_factor_steam_boiler > 0 else None
                )
                data_point['fuel_kg_hto'] = (
                    round(speed_r_bakar * settings.fuel_factor_hto_boiler * bucket_hours, 2)
                    if speed_r_bakar is not None and settings.fuel_factor_hto_boiler > 0 else None
                )

                pr = data_point.get('Steam_Pr')
                if pr is not None and pr > 0:
                    if pr < 3.5:
                        pressure_dist['under'] += 1
                    elif pr > 5.5:
                        pressure_dist['over'] += 1
                    else:
                        pressure_dist['ideal'] += 1

                chart_data.append(data_point)

            results.append((chart_data, pressure_dist))

        return results, settings

    @classmethod
    def get_alert_history(cls, start_time, end_time):
        """Return alert history list and severity counts for boiler machines."""
        alerts_qs = Alert.objects.filter(
            machine__code__in=cls.MACHINES,
            created_at__gte=start_time,
            created_at__lt=end_time
        ).select_related('machine').order_by('created_at')

        alert_history = []
        critical_count = 0
        warning_count = 0

        for alert in alerts_qs:
            if alert.severity == Alert.SEVERITY_CRITICAL:
                critical_count += 1
            elif alert.severity == Alert.SEVERITY_WARNING:
                warning_count += 1

            alert_history.append({
                "severity": alert.severity,
                "alert_type": alert.alert_type,
                "title": alert.title,
                "message": alert.message,
                "current_value": alert.current_value,
                "threshold_value": alert.threshold_value,
                "created_at": timezone.localtime(alert.created_at).strftime("%Y-%m-%d %H:%M"),
                "is_acknowledged": alert.is_acknowledged,
                "machine_code": alert.machine.code if alert.machine else None,
            })

        return alert_history, critical_count, warning_count

    @classmethod
    def get_logical_today(cls):
        """Tanggal operasional boiler saat ini (hari dimulai 06:00)."""
        logical_now = timezone.localtime() - timedelta(hours=6)
        return logical_now.date()

    @classmethod
    def upsert_daily_metric(
        cls,
        target_date,
        chart_data=None,
        pressure_dist=None,
        alert_critical=None,
        alert_warning=None,
    ):
        """
        Hitung KPI boiler untuk satu hari (06:00–06:00) dan simpan ke BoilerDailyMetric.
        chart_data/pressure_dist opsional — jika sudah dihitung (bulk month), lewati query ulang.
        """
        if isinstance(target_date, str):
            target_date = datetime.strptime(target_date, "%Y-%m-%d").date()

        start_time = timezone.make_aware(
            datetime.combine(target_date, datetime.min.time()).replace(hour=6, minute=0, second=0)
        )
        end_time = start_time + timedelta(days=1)

        settings = GlobalSettings.load()

        if chart_data is None or pressure_dist is None:
            _, chart_data, pressure_dist = cls.compute_chart_data(start_time, end_time, settings)

        kpi = cls.compute_kpi_summary(chart_data, pressure_dist, settings)

        if alert_critical is None or alert_warning is None:
            _, alert_critical, alert_warning = cls.get_alert_history(start_time, end_time)

        has_data = any(
            (p.get('Steam_Pr') or 0) > 0 or (p.get('steam_usage') or 0) > 0
            for p in chart_data
        )

        # PINN Efficiency Logic
        start_time = timezone.make_aware(datetime.combine(target_date, datetime.min.time())).replace(hour=6)
        end_time = start_time + timedelta(days=1)
        
        jet_processes = DyeingProcess.objects.filter(
            machine__group__process_type='JET',
            start_time__gte=start_time,
            start_time__lt=end_time,
            is_valid_process=True
        )
        sum_lapis_1 = sum((p.predicted_steam_kg or 0) for p in jet_processes)
        sum_lapis_3 = sum((p.predicted_steam_ideal_kg if p.predicted_steam_ideal_kg is not None else (p.predicted_steam_kg or 0)) for p in jet_processes)
        
        ratio = (sum_lapis_3 / sum_lapis_1) if sum_lapis_1 > 0 else 1.0
        
        actual_jet = kpi.get('total_steam_usage_jet_kg', 0.0)
        actual_non_jet = kpi.get('total_steam_usage_non_jet_kg', 0.0)
        
        ideal_jet = actual_jet * ratio
        total_steam_ideal = actual_non_jet + ideal_jet
        
        eff_pct = None
        if kpi['total_steam_usage_kg'] > 0:
            eff_pct = round((total_steam_ideal / kpi['total_steam_usage_kg']) * 100, 1)

        metric, _ = BoilerDailyMetric.objects.update_or_create(
            date=target_date,
            defaults={
                'total_steam_usage_kg': kpi['total_steam_usage_kg'],
                'total_steam_ideal_usage_kg': round(total_steam_ideal, 1),
                'steam_efficiency_percent': eff_pct,
                'avg_pressure': kpi['avg_pressure'],
                'avg_oil_temp': kpi['avg_oil_temp'],
                'total_fuel_kg': kpi['total_fuel_kg'],
                'total_fuel_steam_kg': kpi['total_fuel_steam_kg'],
                'total_fuel_hto_kg': kpi['total_fuel_hto_kg'],
                'specific_fuel_consumption': kpi['specific_fuel_consumption'],
                'pressure_ideal_percent': kpi['pressure_ideal_percent'],
                'pressure_ideal_count': pressure_dist['ideal'],
                'pressure_under_count': pressure_dist['under'],
                'pressure_over_count': pressure_dist['over'],
                'alert_count_critical': alert_critical,
                'alert_count_warning': alert_warning,
                'alert_count_total': alert_critical + alert_warning,
                'has_data': has_data,
            },
        )
        return metric

    @classmethod
    def daily_metric_to_day_dict(cls, metric):
        """Serialisasi BoilerDailyMetric ke format response kalender."""
        return {
            "date": metric.date.strftime("%Y-%m-%d"),
            "total_steam_usage_kg": metric.total_steam_usage_kg,
            "steam_efficiency_percent": metric.steam_efficiency_percent,
            "avg_pressure": metric.avg_pressure,
            "avg_oil_temp": metric.avg_oil_temp,
            "total_fuel_kg": metric.total_fuel_kg,
            "total_fuel_steam_kg": metric.total_fuel_steam_kg,
            "total_fuel_hto_kg": metric.total_fuel_hto_kg,
            "specific_fuel_consumption": metric.specific_fuel_consumption,
            "pressure_ideal_percent": metric.pressure_ideal_percent,
            "alert_count_critical": metric.alert_count_critical,
            "alert_count_warning": metric.alert_count_warning,
            "alert_count_total": metric.alert_count_total,
            "pressure_dist": {
                "ideal": metric.pressure_ideal_count,
                "under": metric.pressure_under_count,
                "over": metric.pressure_over_count,
            },
            "from_cache": True,
        }

    @classmethod
    def detect_regulations(cls, minute_data, settings):
        speed_max = settings.boiler_regulation_speed_max
        events = []
        
        def _detect_channel(speed_key, temp_key, min_temp, channel_name):
            channel_events = []
            current_event = None
            for log in minute_data:
                speed = log.get(speed_key)
                temp = log.get(temp_key)
                
                if speed is not None and temp is not None:
                    if speed <= speed_max and temp >= min_temp:
                        if current_event is None:
                            current_event = {
                                'channel': channel_name,
                                'start_time': log.get('time', '00:00'),
                                'duration_minutes': 1,
                                'peak_value': temp
                            }
                        else:
                            current_event['duration_minutes'] += 1
                            current_event['peak_value'] = max(current_event['peak_value'], temp)
                    else:
                        if current_event is not None:
                            channel_events.append(current_event)
                            current_event = None
            if current_event is not None:
                channel_events.append(current_event)
            
            return channel_events

        events.extend(_detect_channel('Speed_RB_Steam', 'Steam_Pr', settings.boiler_regulation_pressure_min, 'STEAM'))
        events.extend(_detect_channel('Speed_R_Bakar', 'Oil_Temp', settings.boiler_regulation_hto_oil_temp_min, 'HTO'))
        
        return events

    @classmethod
    def regulation_events_to_alerts(cls, regulation_events, date_str):
        alerts = []
        for ev in regulation_events:
            if ev['channel'] == 'STEAM':
                title = f"Regulasi Boiler Steam – {ev['duration_minutes']} menit"
                message = f"Speed batu bara turun drastis saat tekanan steam mencapai {ev['peak_value']} bar"
                machine_code = "Speed_RB_Steam"
            else:
                title = f"Regulasi Boiler HTO – {ev['duration_minutes']} menit"
                message = f"Speed HTO turun drastis saat suhu oli mencapai {ev['peak_value']} °C"
                machine_code = "Speed_R_Bakar"
            
            created_at_str = f"{date_str} {ev['start_time']}"
            alerts.append({
                "severity": "WARNING",
                "alert_type": "REGULATION",
                "title": title,
                "message": message,
                "current_value": ev['peak_value'],
                "threshold_value": None,
                "created_at": created_at_str,
                "is_acknowledged": False,
                "machine_code": machine_code,
                "regulation_meta": ev,
            })
        return alerts

    @classmethod
    def get_summary(cls, date_str):
        """Menghasilkan payload lengkap untuk endpoint get_boiler_summary."""
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            return {"error": "Invalid date format, use YYYY-MM-DD"}

        settings = GlobalSettings.load()

        start_time = timezone.make_aware(dt.replace(hour=6, minute=0, second=0, microsecond=0))
        end_time = start_time + timedelta(days=1)

        minute_data, chart_data, pressure_dist = cls.compute_chart_data(start_time, end_time, settings)
        kpi_summary = cls.compute_kpi_summary(chart_data, pressure_dist, settings)
        alert_history, critical_count, warning_count = cls.get_alert_history(start_time, end_time)

        regulation_events = cls.detect_regulations(minute_data, settings)
        steam_count = sum(1 for e in regulation_events if e['channel'] == 'STEAM')
        hto_count = sum(1 for e in regulation_events if e['channel'] == 'HTO')
        regulation_alerts = cls.regulation_events_to_alerts(regulation_events, start_time.strftime("%Y-%m-%d"))
        
        alert_history = sorted(
            alert_history + regulation_alerts,
            key=lambda x: str(x['created_at']), reverse=True
        )
        warning_count += len(regulation_alerts)

        kpi_summary["alert_count_critical"] = critical_count
        kpi_summary["alert_count_warning"] = warning_count
        kpi_summary["alert_count_total"] = len(alert_history)

        return {
            "date_range": f"{start_time.strftime('%d %b %Y %H:%M')} - {end_time.strftime('%d %b %Y %H:%M')}",
            "chart_data": chart_data,
            "pressure_dist": pressure_dist,
            "kpi_summary": kpi_summary,
            "alert_history": alert_history,
            "regulation_summary": {
                "total": len(regulation_events),
                "steam_count": steam_count,
                "hto_count": hto_count,
            },
            "fuel_config": {
                "steam_calibrated": settings.fuel_factor_steam_boiler > 0,
                "hto_calibrated": settings.fuel_factor_hto_boiler > 0,
                "fuel_factor_steam_boiler": settings.fuel_factor_steam_boiler,
                "fuel_factor_hto_boiler": settings.fuel_factor_hto_boiler,
                "steam_sensor_hz": "Speed_RB_Steam",
                "hto_sensor_hz": "Speed_R_Bakar",
                "formula": "kg/jam = Hz × faktor",
            },
        }

    @classmethod
    def get_weekly_baseline(cls, date_str):
        """Menghasilkan payload lengkap untuk endpoint get_boiler_weekly_baseline."""
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            return {"error": "Invalid date format, use YYYY-MM-DD"}

        settings = GlobalSettings.load()

        selected_start = timezone.make_aware(dt.replace(hour=6, minute=0, second=0, microsecond=0))

        start_date_7d = (selected_start - timedelta(days=7)).date()
        end_date_7d = (selected_start - timedelta(days=1)).date()
        cached_metrics = {
            m.date: m
            for m in BoilerDailyMetric.objects.filter(date__gte=start_date_7d, date__lte=end_date_7d)
        }

        daily_kpis = []
        for day_offset in range(7, 0, -1):
            day_date = (selected_start - timedelta(days=day_offset)).date()
            metric = cached_metrics.get(day_date)
            if not metric:
                try:
                    metric = cls.upsert_daily_metric(day_date)
                except Exception:
                    metric = None

            if metric:
                daily_kpis.append({
                    "total_steam_usage_kg": metric.total_steam_usage_kg,
                    "avg_pressure": metric.avg_pressure,
                    "avg_oil_temp": metric.avg_oil_temp,
                    "total_fuel_kg": metric.total_fuel_kg,
                    "specific_fuel_consumption": metric.specific_fuel_consumption,
                    "pressure_ideal_percent": metric.pressure_ideal_percent,
                    "alert_count_total": metric.alert_count_total,
                    "alert_count_critical": metric.alert_count_critical,
                    "alert_count_warning": metric.alert_count_warning,
                })

        if not daily_kpis:
            return {"error": "No baseline data available"}

        def _avg(values):
            valid = [v for v in values if v is not None]
            return round(sum(valid) / len(valid), 2) if valid else None

        return {
            "period": f"7 hari sebelum {dt.strftime('%d %b %Y')}",
            "days_counted": len(daily_kpis),
            "avg_total_steam_usage_kg": _avg([k["total_steam_usage_kg"] for k in daily_kpis]),
            "avg_pressure": _avg([k["avg_pressure"] for k in daily_kpis]),
            "avg_oil_temp": _avg([k["avg_oil_temp"] for k in daily_kpis]),
            "avg_total_fuel_kg": _avg([k["total_fuel_kg"] for k in daily_kpis if k["total_fuel_kg"] is not None]),
            "avg_specific_fuel_consumption": _avg([k["specific_fuel_consumption"] for k in daily_kpis if k["specific_fuel_consumption"] is not None]),
            "avg_pressure_ideal_percent": _avg([k["pressure_ideal_percent"] for k in daily_kpis if k["pressure_ideal_percent"] is not None]),
            "avg_alert_count_total": round(sum(k["alert_count_total"] for k in daily_kpis) / len(daily_kpis), 1),
            "avg_alert_count_critical": round(sum(k["alert_count_critical"] for k in daily_kpis) / len(daily_kpis), 1),
        }

    @classmethod
    def get_monthly_calendar(cls, year: int, month: int):
        """Menghasilkan payload lengkap untuk endpoint get_boiler_monthly_calendar."""
        if not (1 <= month <= 12):
            return {"error": "Month must be between 1 and 12"}

        settings = GlobalSettings.load()
        month_start = timezone.make_aware(datetime(year, month, 1, 6, 0, 0))
        next_month = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)
        month_end = timezone.make_aware(next_month.replace(hour=6, minute=0, second=0, microsecond=0))
        days_in_month = (month_end - month_start).days
        logical_today = cls.get_logical_today()

        first_date = month_start.date()
        last_date = (month_start + timedelta(days=days_in_month - 1)).date()

        cached_metrics = {
            m.date: m
            for m in BoilerDailyMetric.objects.filter(
                date__gte=first_date,
                date__lte=last_date,
            )
        }

        days_to_refresh = []
        for day_index in range(days_in_month):
            day_date = (month_start + timedelta(days=day_index)).date()
            if day_date > logical_today:
                continue
            if day_date not in cached_metrics or day_date == logical_today:
                days_to_refresh.append(day_index)

        cache_hits = days_in_month - len(days_to_refresh)

        if len(days_to_refresh) > 1:
            daily_chart_pairs, _settings = cls.bucket_boiler_month_data(month_start, days_in_month)

            alerts_qs = Alert.objects.filter(
                machine__code__in=cls.MACHINES,
                created_at__gte=month_start,
                created_at__lt=month_end,
            ).values('created_at', 'severity')

            alert_counts = defaultdict(lambda: {'critical': 0, 'warning': 0})
            for alert in alerts_qs:
                total_minutes = (alert['created_at'] - month_start).total_seconds() / 60
                day_index = int(total_minutes // (24 * 60))
                if 0 <= day_index < days_in_month:
                    if alert['severity'] == Alert.SEVERITY_CRITICAL:
                        alert_counts[day_index]['critical'] += 1
                    elif alert['severity'] == Alert.SEVERITY_WARNING:
                        alert_counts[day_index]['warning'] += 1

            for day_index in days_to_refresh:
                day_date = (month_start + timedelta(days=day_index)).date()
                chart_data, pressure_dist = daily_chart_pairs[day_index]
                counts = alert_counts.get(day_index, {'critical': 0, 'warning': 0})
                cls.upsert_daily_metric(
                    day_date,
                    chart_data=chart_data,
                    pressure_dist=pressure_dist,
                    alert_critical=counts['critical'],
                    alert_warning=counts['warning'],
                )

            cached_metrics = {
                m.date: m
                for m in BoilerDailyMetric.objects.filter(
                    date__gte=first_date,
                    date__lte=last_date,
                )
            }
        elif len(days_to_refresh) == 1:
            day_date = (month_start + timedelta(days=days_to_refresh[0])).date()
            cls.upsert_daily_metric(day_date)
            metric = BoilerDailyMetric.objects.get(date=day_date)
            cached_metrics[day_date] = metric

        days = [
            cls.daily_metric_to_day_dict(cached_metrics[(month_start + timedelta(days=i)).date()])
            for i in range(days_in_month)
            if (month_start + timedelta(days=i)).date() in cached_metrics
        ]

        if len(days) < days_in_month:
            existing_dates = {d['date'] for d in days}
            for day_index in range(days_in_month):
                day_date = (month_start + timedelta(days=day_index)).date()
                date_str = day_date.strftime("%Y-%m-%d")
                if date_str not in existing_dates:
                    days.append({
                        "date": date_str,
                        "total_steam_usage_kg": 0,
                        "avg_pressure": None,
                        "avg_oil_temp": None,
                        "total_fuel_kg": None,
                        "specific_fuel_consumption": None,
                        "pressure_ideal_percent": None,
                        "alert_count_critical": 0,
                        "alert_count_warning": 0,
                        "alert_count_total": 0,
                        "pressure_dist": {"ideal": 0, "under": 0, "over": 0},
                        "from_cache": False,
                    })
            days.sort(key=lambda d: d['date'])

        return {
            "year": year,
            "month": month,
            "days": days,
            "cache_hits": cache_hits,
            "days_computed": days_in_month - cache_hits,
            "fuel_config": {
                "steam_calibrated": settings.fuel_factor_steam_boiler > 0,
                "hto_calibrated": settings.fuel_factor_hto_boiler > 0,
            },
        }
