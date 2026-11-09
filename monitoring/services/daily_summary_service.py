from datetime import datetime, timedelta
from collections import defaultdict
from django.utils import timezone
from django.db.models import Q

from monitoring.models import (
    Machine, MachineGroup, DyeingProcess, MachineMinuteLog, MachineStatusSnapshot, GlobalSettings
)
from monitoring.utils.steam_active import is_steam_active_from_snapshot
from monitoring.services.batch_cost_calculator import BatchCostCalculator, ProcessDiagnosticService

sort_machines_custom = ProcessDiagnosticService.sort_machines_custom
classify_process_problems = ProcessDiagnosticService.classify_process_problems
_compute_downtime_ranking = ProcessDiagnosticService.compute_downtime_ranking
_compute_batch_electricity_metrics = BatchCostCalculator.compute_electricity
_compute_changeover_stats = ProcessDiagnosticService.compute_changeover_stats


class DailySummaryService:
    @classmethod
    def compute_daily_summary(cls, date: str) -> dict:
        """Logika inti daily-summary, dipisah dari guard permission agar bisa
        dipanggil langsung secara internal (misal oleh dashboard steam-sales)
        tanpa terkena gerbang izin halaman 'daily_report'."""
        # Parsing date
        try:
            dt = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            return {"error": "Invalid date format, use YYYY-MM-DD"}
        # Set range: 06:00 to 06:00 next day
        start_time = timezone.make_aware(dt.replace(hour=6, minute=0, second=0, microsecond=0))
        end_time = start_time + timedelta(days=1)
        # ─────────────────────────────────────────────────────────────────
        # 1. STEAM TRAFFIC (24 Jam) & TOTAL STEAM (dari MachineStatusSnapshot)
        # ─────────────────────────────────────────────────────────────────
        from monitoring.models import MachineStatusSnapshot
        snapshots = MachineStatusSnapshot.objects.filter(
            timestamp__gte=start_time,
            timestamp__lt=end_time
        ).order_by('timestamp')
        all_steam_machines = Machine.objects.filter(is_active=True, average_steam_usage__gt=0).select_related('group')
        machines_dict = {m.code: m for m in all_steam_machines}
        interval_minutes = 10
        TARGET_POINTS = 144
        interval_data = defaultdict(lambda: {'steam_total': 0.0, 'count': 0})
        for snapshot in snapshots:
            time_diff = (snapshot.timestamp - start_time).total_seconds() / 60
            bucket_index = int(time_diff / interval_minutes)
            if bucket_index >= TARGET_POINTS: bucket_index = TARGET_POINTS - 1
            if bucket_index < 0: bucket_index = 0
            steam_total = 0.0
            for machine_code, snap_data in snapshot.snapshot_data.items():
                machine = machines_dict.get(machine_code)
                if machine:
                    is_active = False
                    from monitoring.utils.steam_active import is_steam_active_from_snapshot
                    is_active = is_steam_active_from_snapshot(snap_data)
                    if is_active:
                        steam_total += machine.average_steam_usage
            interval_data[bucket_index]['steam_total'] += steam_total
            interval_data[bucket_index]['count'] += 1
        steam_pr_logs = MachineMinuteLog.objects.filter(
            machine__code="Steam_Pr",
            timestamp__gte=start_time,
            timestamp__lt=end_time
        ).order_by('timestamp')
        pressure_data = defaultdict(lambda: {'total': 0.0, 'count': 0})
        for log in steam_pr_logs:
            if log.temperature is not None:
                time_diff = (log.timestamp - start_time).total_seconds() / 60
                bucket_index = int(time_diff / interval_minutes)
                if bucket_index >= TARGET_POINTS: bucket_index = TARGET_POINTS - 1
                if bucket_index < 0: bucket_index = 0
                pressure_data[bucket_index]['total'] += log.temperature
                pressure_data[bucket_index]['count'] += 1
        steam_series = []
        total_steam_usage = 0.0
        for i in range(TARGET_POINTS):
            bucket_start = start_time + timedelta(minutes=i * interval_minutes)
            avg_steam = 0.0
            avg_steam_jet = 0.0
            avg_steam_non_jet = 0.0
            if interval_data[i]['count'] > 0:
                c = interval_data[i]['count']
                avg_steam = interval_data[i]['steam_total'] / c
                avg_steam_jet = interval_data[i].get('steam_total_jet', 0.0) / c
                avg_steam_non_jet = interval_data[i].get('steam_total_non_jet', 0.0) / c
            avg_pressure = 0.0
            if pressure_data[i]['count'] > 0:
                avg_pressure = pressure_data[i]['total'] / pressure_data[i]['count']
            steam_series.append({
                "time": timezone.localtime(bucket_start).strftime("%H:%M"),
                "usage": round(avg_steam, 1),
                "usage_jet": round(avg_steam_jet, 1),
                "usage_non_jet": round(avg_steam_non_jet, 1),
                "pressure": round(avg_pressure, 2)
            })
            total_steam_usage += avg_steam * (interval_minutes / 60.0)
        # ─────────────────────────────────────────────────────────────────
        # 2. DYEING PROCESSES — Heatmap & History Table (termasuk Data Kain)
        # ─────────────────────────────────────────────────────────────────
        processes = DyeingProcess.objects.filter(
            start_time__gte=start_time,
            start_time__lt=end_time,
            is_valid_process=True
        ).exclude(
            machine__group__code='MC_BOILER'
        ).select_related('machine', 'machine__group', 'identity', 'identity__program')
        process_counts = {}
        history_table = {}
        from monitoring.models import GlobalSettings
        settings = GlobalSettings.load()
        threshold = getattr(settings, 'steam_healthy_threshold', 3.8)

        total_power_lwbp_kwh = 0.0
        total_power_wbp_kwh = 0.0
        total_power_kwh = 0.0
        total_fresh_yd = 0.0
        total_creaping_yd = 0.0
        total_other_yd = 0.0

        for p in processes:
            m_id = p.machine_id
            if m_id not in process_counts:
                process_counts[m_id] = 0
            process_counts[m_id] += 1
            group_name = p.machine.group.name if p.machine.group else "Lain-lain"
            if group_name not in history_table:
                history_table[group_name] = []
            # Ambil data kain dari DyeingIdentity (jika sudah diisi)
            identity = getattr(p, 'identity', None)

            # Akumulasi Listrik Global
            if p.power_consumption_lwbp_kwh: total_power_lwbp_kwh += p.power_consumption_lwbp_kwh
            if p.power_consumption_wbp_kwh: total_power_wbp_kwh += p.power_consumption_wbp_kwh
            if p.power_consumption_kwh: total_power_kwh += p.power_consumption_kwh

            # Akumulasi Yard Global
            if identity:
                jp = identity.jenis_proses or ""
                oy = identity.output_yard or 0.0
                if jp == "FRESH": total_fresh_yd += oy
                elif jp.startswith("CREAPING"): total_creaping_yd += oy
                else: total_other_yd += oy

            nomor_order  = identity.nomor_order  if identity and identity.nomor_order  else "-"
            artikel_kain = identity.artikel_kain if identity and identity.artikel_kain else "-"
            batch_kain   = identity.batch        if identity and identity.batch        else "-"
            history_table[group_name].append({
                "id":           p.id,
                "machine_id":   p.machine.id,
                "machine_name": p.machine.name,
                "machine_code": p.machine.code,
                "batch_number": p.batch_number,
                "start_time":   timezone.localtime(p.start_time).strftime("%H:%M") if p.start_time else "-",
                "end_time":     timezone.localtime(p.end_time).strftime("%H:%M")   if p.end_time   else "-",
                "duration":     round(p.total_duration, 1) if p.total_duration else "-",
                "max_temp":     round(p.max_temp, 1)       if p.max_temp       else "-",
                "status":       "Selesai" if p.is_complete else "Berjalan",
                # Data kain
                "nomor_order":  nomor_order,
                "artikel_kain": artikel_kain,
                "batch_kain":   batch_kain,
                "jenis_proses": identity.jenis_proses if identity and identity.jenis_proses else "-",
                "output_yard":  identity.output_yard if identity and identity.output_yard else 0.0,
            })
        history_groups = []
        for gname, items in history_table.items():
            items.sort(key=lambda x: x["start_time"])
            sort_machines_custom(items, name_key="machine_name")
            history_groups.append({"group_name": gname, "items": items})
        history_groups.sort(key=lambda x: x["group_name"])
        # ─────────────────────────────────────────────────────────────────
        # 3. HEATMAP GROUPS
        # ─────────────────────────────────────────────────────────────────
        groups = MachineGroup.objects.filter(machine__is_active=True).exclude(code='MC_BOILER').distinct().order_by('name')
        active_machines_all = list(Machine.objects.filter(is_active=True).exclude(group__code='MC_BOILER').select_related('group').order_by('name'))
        machines_by_group_dict = defaultdict(list)
        for m in active_machines_all:
            if m.group_id:
                machines_by_group_dict[m.group_id].append(m)

        groups_data = []
        for group in groups:
            machines = machines_by_group_dict.get(group.id, [])
            if not machines:
                continue
            group_processes = 0
            machines_data = []
            for m in machines:
                count = process_counts.get(m.id, 0)
                group_processes += count
                machines_data.append({"id": m.id, "name": m.name, "process_count": count})

            sort_machines_custom(machines_data, name_key="name")

            groups_data.append({
                "group_name":            group.name,
                "machine_count":         len(machines),
                "total_group_processes": group_processes,
                "machines":              machines_data,
            })
        # ─────────────────────────────────────────────────────────────────
        # 4. MACHINE AVAILABILITY CHART
        #    Downsampling ke 5 menit. State mapping:
        #    HEAT → "HEAT", STEADY → "STEADY", COOL → "COOL",
        #    Running (MANUAL) → "RUNNING", selebihnya → "OFF"
        # ─────────────────────────────────────────────────────────────────
        AVAIL_INTERVAL = interval_minutes   # pakai interval snapshot (misal 10 menit)
        TOTAL_MINUTES  = 24 * 60
        machine_buckets = defaultdict(dict)
        machine_meta    = {}
        code_to_id      = {}
        # Ambil data meta mesin yang valid (exclude BOILER & Sensor)
        valid_machines = Machine.objects.filter(is_active=True).exclude(
            group__code='MC_BOILER'
        ).exclude(code__in=['Steam_Pr', 'Oil_Temp']).select_related('group')
        for m in valid_machines:
            machine_meta[m.id] = {
                "id":         m.id,
                "name":       m.name,
                "group_name": m.group.name if m.group else "Lain-lain",
            }
            code_to_id[m.code] = m.id
        # Menggunakan ulang 'snapshots' dari proses di atas (0 query log tambahan!)
        for snapshot in snapshots:
            time_diff = (snapshot.timestamp - start_time).total_seconds() / 60
            bucket_index = int(time_diff / AVAIL_INTERVAL)
            if 0 <= bucket_index < (TOTAL_MINUTES // AVAIL_INTERVAL):
                for machine_code, snap_data in snapshot.snapshot_data.items():
                    m_id = code_to_id.get(machine_code)
                    if m_id:
                        if snap_data.get('mode') == 'MANUAL':
                            state = "RUNNING" if snap_data.get('status') == "Running" else "OFF"
                        else:
                            ts = snap_data.get('detail', '')
                            if ts in ("HEAT", "STEADY", "COOL"): state = ts
                            else: state = "OFF"
                        machine_buckets[m_id][bucket_index] = state
        # Konversi bucket → segments (runs of same state)
        def buckets_to_segments(buckets):
            total_buckets = TOTAL_MINUTES // AVAIL_INTERVAL   # 288
            segments = []
            current_state = None
            seg_start     = 0
            for i in range(total_buckets):
                s = buckets.get(i, "OFF")
                if s != current_state:
                    if current_state is not None:
                        segments.append({
                            "state":     current_state,
                            "start_pct": round(seg_start / total_buckets * 100, 2),
                            "width_pct": round((i - seg_start) / total_buckets * 100, 2),
                        })
                    current_state = s
                    seg_start     = i
            # Tutup segment terakhir
            total_buckets_real = TOTAL_MINUTES // AVAIL_INTERVAL
            if current_state is not None:
                segments.append({
                    "state":     current_state,
                    "start_pct": round(seg_start / total_buckets_real * 100, 2),
                    "width_pct": round((total_buckets_real - seg_start) / total_buckets_real * 100, 2),
                })
            return segments
        # Susun per group
        avail_group_map = defaultdict(list)
        for m_id, meta in machine_meta.items():
            segs = buckets_to_segments(machine_buckets.get(m_id, {}))
            avail_group_map[meta["group_name"]].append({
                "machine_id":   meta["id"],
                "machine_name": meta["name"],
                "segments":     segs,
            })

        # ─────────────────────────────────────────────────────────────────
        # 5. AVAILABILITY SUMMARY LIST
        # ─────────────────────────────────────────────────────────────────
        machine_availabilities = []

        from django.db.models import Q
        # Pre-fetch all JET DyeingProcess records in 1 bulk query
        jet_machine_ids = [m.id for m in valid_machines if m.group and getattr(m.group, 'process_type', None) == 'JET']
        jet_processes_by_mc = defaultdict(list)
        if jet_machine_ids:
            all_jet_proc_qs = (
                DyeingProcess.objects
                .filter(machine_id__in=jet_machine_ids, is_valid_process=True)
                .filter(
                    Q(start_time__gte=start_time, start_time__lt=end_time) | 
                    Q(start_time__lt=start_time, end_time__gt=start_time) |
                    Q(start_time__lt=start_time, end_time__isnull=True)
                )
                .only("machine_id", "heating_start_time", "start_time", "end_time")
            )
            for proc in all_jet_proc_qs:
                jet_processes_by_mc[proc.machine_id].append(proc)

        for m in valid_machines:
            total_uptime_minutes = 0.0

            # For JET machines, calculate uptime from DyeingProcess (Rise Time to End Time)
            if m.group and getattr(m.group, 'process_type', None) == 'JET':
                m_processes = jet_processes_by_mc.get(m.id, [])
                for p in m_processes:
                    r_start = p.heating_start_time if p.heating_start_time else p.start_time
                    r_end = p.end_time if p.end_time else min(timezone.now(), end_time)

                    # Clamp limits to current day window (06:00 to 06:00)
                    r_start = max(r_start, start_time)
                    r_end = min(r_end, end_time)

                    if r_end > r_start:
                        total_uptime_minutes += (r_end - r_start).total_seconds() / 60.0

            else:
                # For MANUAL or other machines, use the snapshot data
                m_id = m.id
                if m_id in machine_buckets:
                    for b_idx, state in machine_buckets[m_id].items():
                        if state in ["RUNNING", "HEAT", "STEADY", "COOL"]:
                            total_uptime_minutes += AVAIL_INTERVAL

            if total_uptime_minutes > 0:
                total_uptime_minutes = min(total_uptime_minutes, 1440.0)
                availability_pct = (total_uptime_minutes / 1440.0) * 100.0

                hours = int(total_uptime_minutes // 60)
                mins = int(total_uptime_minutes % 60)
                uptime_str = f"{hours}h {mins}m" if hours > 0 else f"{mins}m"

                machine_availabilities.append({
                    "machine_id": m.id,
                    "machine_name": m.name,
                    "group_name": m.group.name if m.group else "Lain-lain",
                    "availability": round(availability_pct, 1),
                    "uptime_str": uptime_str,
                    "uptime_minutes": round(total_uptime_minutes, 1)
                })

        machine_availabilities.sort(key=lambda x: x['availability'], reverse=True)

        avg_avail = 0.0
        if len(machine_availabilities) > 0:
            avg_avail = sum(x['availability'] for x in machine_availabilities) / len(machine_availabilities)

        availability_summary = {
            "average": round(avg_avail, 1),
            "machines": machine_availabilities
        }

        # Sort machines within group by name
        availability_groups = []
        for gname, machines_avail in sorted(avail_group_map.items()):
            sort_machines_custom(machines_avail, name_key="machine_name")
            availability_groups.append({
                "group_name": gname,
                "machines":   machines_avail,
            })

        # ─────────────────────────────────────────────────────────────────
        # 6. EFFICIENCY PROBLEM BREAKDOWN & EFFICIENCY SUMMARY
        # ─────────────────────────────────────────────────────────────────
        eff_problem_data = {
            "PRESSURE_LOW": {"label": "Tekanan Steam Kurang", "color": "red", "processes": []},
            "HEATING_SLOW": {"label": "Heating Lambat", "color": "orange", "processes": []},
            "COOLING_SLOW": {"label": "Cooling Lambat", "color": "blue", "processes": []},
            "START_TEMP_HIGH": {"label": "Suhu Awal Tinggi", "color": "purple", "processes": []},
            "OTHERS": {"label": "Masalah Lainnya", "color": "gray", "processes": []}
        }

        total_low_efficiency = 0
        total_analyzed = 0

        # Changeover time per mesin (gap antar batch selesai → batch berikutnya)
        machine_changeover, plant_avg_changeover = _compute_changeover_stats(processes)

        # For Efficiency Summary (Average per Machine)
        machine_eff_stats = defaultdict(lambda: {
            'total_eff': 0, 'total_loss_time': 0, 'count': 0, 'batch_count': 0, 'name': '', 'processes': [],
            'total_steam': 0, 'total_steam_ideal': 0, 'total_steam_ideal_measured': 0, 'total_steam_with_ideal': 0,
            'total_power': 0, 'total_power_ideal': 0, 'total_power_ideal_measured': 0, 'total_power_actual_measured': 0,
            'steam_ok_count': 0, 'total_steam_loss_kg': 0, 'total_steam_loss_rp': 0,
            'total_power_lwbp_rp': 0, 'total_power_wbp_rp': 0, 'total_power_loss_rp': 0, 'total_power_total_rp': 0,
            'total_output_yd': 0, 'total_steam_cost_rp': 0, 'total_power_lwbp_kwh': 0, 'total_power_wbp_kwh': 0,
            'group_name': 'Lain-lain', 'total_actual_mins': 0, 'total_ideal_mins': 0, 'total_pos_loss_time': 0,
            'total_power_loss_kwh': 0, 'total_pressure': 0.0, 'pressure_count': 0, 'total_delay_heat': 0.0, 'total_delay_cool': 0.0
        })

        from monitoring.models import GlobalSettings
        settings = GlobalSettings.load()
        threshold = getattr(settings, 'steam_healthy_threshold', 3.8)
        lwbp_rate = getattr(settings, 'electricity_base_rate', 1035.8) or 1035.8
        wbp_mult = getattr(settings, 'wbp_multiplier', 1.4) or 1.4
        wbp_rate = round(lwbp_rate * wbp_mult, 2)
        steam_rate = getattr(settings, 'steam_cost_per_kg', 350.0) or 350.0

        for p in processes:
            identity = getattr(p, 'identity', None)
            program = identity.program if identity else None

            m_id = p.machine.id
            machine_eff_stats[m_id]['name'] = p.machine.name
            machine_eff_stats[m_id]['group_name'] = p.machine.group.name if p.machine.group else 'Lain-lain'
            machine_eff_stats[m_id]['batch_count'] += 1

            # 1. Akumulasi pemakaian Steam & Listrik Aktual untuk SELURUH batch valid di mesin ini
            if p.predicted_steam_kg:
                machine_eff_stats[m_id]['total_steam'] += p.predicted_steam_kg
                machine_eff_stats[m_id]['total_steam_cost_rp'] += p.predicted_steam_kg * steam_rate
                if p.predicted_steam_ideal_kg:
                    machine_eff_stats[m_id]['total_steam_ideal'] += p.predicted_steam_ideal_kg
                    machine_eff_stats[m_id]['total_steam_ideal_measured'] += p.predicted_steam_ideal_kg
                    machine_eff_stats[m_id]['total_steam_with_ideal'] += p.predicted_steam_kg
                    steam_loss = p.predicted_steam_kg - p.predicted_steam_ideal_kg
                    if steam_loss > 0:
                        machine_eff_stats[m_id]['total_steam_loss_kg'] += steam_loss
                        machine_eff_stats[m_id]['total_steam_loss_rp'] += steam_loss * steam_rate
                else:
                    machine_eff_stats[m_id]['total_steam_ideal'] += p.predicted_steam_kg

            elec_m = _compute_batch_electricity_metrics(p, program, lwbp_rate, wbp_rate)
            if elec_m['actual_kwh']:
                machine_eff_stats[m_id]['total_power'] += elec_m['actual_kwh']
            if p.power_consumption_lwbp_kwh:
                machine_eff_stats[m_id]['total_power_lwbp_kwh'] += p.power_consumption_lwbp_kwh
            if p.power_consumption_wbp_kwh:
                machine_eff_stats[m_id]['total_power_wbp_kwh'] += p.power_consumption_wbp_kwh
            if elec_m['cost_lwbp_rp']:
                machine_eff_stats[m_id]['total_power_lwbp_rp'] += elec_m['cost_lwbp_rp']
            if elec_m['cost_wbp_rp']:
                machine_eff_stats[m_id]['total_power_wbp_rp'] += elec_m['cost_wbp_rp']
            if elec_m['cost_actual_rp']:
                machine_eff_stats[m_id]['total_power_total_rp'] += elec_m['cost_actual_rp']

            if elec_m['ideal_kwh'] is not None and elec_m['actual_kwh'] is not None:
                machine_eff_stats[m_id]['total_power_ideal'] += elec_m['ideal_kwh']
                machine_eff_stats[m_id]['total_power_ideal_measured'] += elec_m['ideal_kwh']
                machine_eff_stats[m_id]['total_power_actual_measured'] += elec_m['actual_kwh']
                if elec_m['pos_loss_kwh'] > 0:
                    machine_eff_stats[m_id]['total_power_loss_kwh'] += elec_m['pos_loss_kwh']
                if elec_m['cost_loss_rp'] > 0:
                    machine_eff_stats[m_id]['total_power_loss_rp'] += elec_m['cost_loss_rp']
            elif elec_m['actual_kwh']:
                machine_eff_stats[m_id]['total_power_ideal'] += elec_m['actual_kwh']

            if p.avg_steam_pressure is not None:
                machine_eff_stats[m_id]['total_pressure'] += p.avg_steam_pressure
                machine_eff_stats[m_id]['pressure_count'] += 1
                if p.avg_steam_pressure >= threshold:
                    machine_eff_stats[m_id]['steam_ok_count'] += 1

            if identity and identity.output_yard:
                machine_eff_stats[m_id]['total_output_yd'] += identity.output_yard

            # 2. Evaluasi Efisiensi Durasi & Pareto Masalah (khusus batch yang memiliki durasi ideal)
            if identity and program and p.duration_effective and program.durasi_ideal:
                total_analyzed += 1
                overall_eff = (program.durasi_ideal / p.duration_effective) * 100
                loss_time = p.duration_effective - program.durasi_ideal

                ideal_heat_keep = (program.durasi_heating_ideal or 0) + (program.durasi_keeping_ideal or 0)
                real_heat_keep = (p.real_heating_duration or 0) + (p.steady_duration or 0)
                delay_heat = real_heat_keep - ideal_heat_keep

                delay_cool = 0
                if program.durasi_cooling_ideal and p.cooling_duration:
                    delay_cool = p.cooling_duration - program.durasi_cooling_ideal

                delay_total = p.duration_effective - program.durasi_ideal

                nomor_order  = identity.nomor_order if identity.nomor_order else "-"
                batch_kain   = identity.batch if identity.batch else "-"

                process_info = {
                    "id": p.id,
                    "machine_name": p.machine.name,
                    "batch_number": p.batch_number,
                    "nomor_order": nomor_order,
                    "batch_kain": batch_kain,
                    "jenis_proses": identity.jenis_proses if identity and identity.jenis_proses else "-",
                    "output_yard": identity.output_yard if identity and identity.output_yard else 0.0,
                    "start_time": timezone.localtime(p.start_time).strftime("%H:%M") if p.start_time else "-",
                    "end_time": timezone.localtime(p.end_time).strftime("%H:%M") if p.end_time else "-",
                    "total_duration": round(p.total_duration, 1) if p.total_duration else "-",
                    "max_temp": round(p.max_temp, 1) if p.max_temp else "-",
                    "eff_total": round(overall_eff, 1),
                    "delay_heat": round(delay_heat, 1),
                    "delay_cool": round(delay_cool, 1),
                    "delay_total": round(delay_total, 1),
                    "avg_steam_pressure": round(p.avg_steam_pressure, 2) if p.avg_steam_pressure is not None else None,
                }

                machine_eff_stats[m_id]['total_eff'] += overall_eff
                machine_eff_stats[m_id]['total_loss_time'] += loss_time
                machine_eff_stats[m_id]['total_actual_mins'] += (p.duration_effective or 0)
                machine_eff_stats[m_id]['total_ideal_mins'] += (program.durasi_ideal or 0)
                if loss_time > 0:
                    machine_eff_stats[m_id]['total_pos_loss_time'] += loss_time
                machine_eff_stats[m_id]['count'] += 1
                if delay_heat > 0:
                    machine_eff_stats[m_id]['total_delay_heat'] += delay_heat
                if delay_cool > 0:
                    machine_eff_stats[m_id]['total_delay_cool'] += delay_cool

                machine_eff_stats[m_id]['processes'].append(process_info)

                if overall_eff < 85:
                    total_low_efficiency += 1
                    probs = classify_process_problems(p, program, pressure_threshold=threshold)

                    for prob in probs:
                        if prob in eff_problem_data:
                            eff_problem_data[prob]["processes"].append(process_info)

        # -- START CONTINUOUS MACHINES INJECTION --
        cont_machines = Machine.objects.filter(group__process_type='CONTINUOUS', is_active=True).select_related('group')
        cont_dict = {m.code: m for m in cont_machines}
        cont_stats = {m.code: {'running_mins_lwbp': 0, 'running_mins_wbp': 0, 'steam_mins': 0} for m in cont_machines}

        for snapshot in snapshots:
            local_time = timezone.localtime(snapshot.timestamp)
            is_wbp = (17 <= local_time.hour < 22)

            for code, data in snapshot.snapshot_data.items():
                if code in cont_dict:
                    status = data.get('status')
                    detail = data.get('detail')
                    is_machine_active = (status in ["HEAT", "STEADY", "Running", "COOL"]) or (detail in ["HEAT", "STEADY", "Running", "COOL"])
                    if is_machine_active:
                        if is_wbp:
                            cont_stats[code]['running_mins_wbp'] += 1
                        else:
                            cont_stats[code]['running_mins_lwbp'] += 1

                    from monitoring.utils.steam_active import is_steam_active_from_snapshot
                    if is_steam_active_from_snapshot(data):
                        cont_stats[code]['steam_mins'] += 1

        for code, stats in cont_stats.items():
            if stats['running_mins_lwbp'] > 0 or stats['running_mins_wbp'] > 0 or stats['steam_mins'] > 0:
                m = cont_dict[code]

                power_lwbp = (stats['running_mins_lwbp'] / 60.0) * (m.nominal_power or 0)
                power_wbp = (stats['running_mins_wbp'] / 60.0) * (m.nominal_power or 0)
                power = power_lwbp + power_wbp

                steam = (stats['steam_mins'] / 60.0) * (m.average_steam_usage or 0)

                total_power_kwh += power
                total_power_lwbp_kwh += power_lwbp
                total_power_wbp_kwh += power_wbp

                machine_eff_stats[m.id]['name'] = m.name
                machine_eff_stats[m.id]['group_name'] = m.group.name if m.group else 'Lain-lain'
                machine_eff_stats[m.id]['is_continuous'] = True

                machine_eff_stats[m.id]['total_power'] += power
                machine_eff_stats[m.id]['total_power_ideal'] += power
                machine_eff_stats[m.id]['total_steam'] += steam
                machine_eff_stats[m.id]['total_steam_ideal'] += steam
                machine_eff_stats[m.id]['total_power_lwbp_kwh'] += power_lwbp
                machine_eff_stats[m.id]['total_power_wbp_kwh'] += power_wbp

                power_lwbp_cost = power_lwbp * lwbp_rate
                power_wbp_cost = power_wbp * wbp_rate
                power_cost_est = power_lwbp_cost + power_wbp_cost
                steam_cost_est = steam * steam_rate

                machine_eff_stats[m.id]['total_power_total_rp'] += power_cost_est
                machine_eff_stats[m.id]['total_power_wbp_rp'] += power_wbp_cost
                machine_eff_stats[m.id]['total_power_lwbp_rp'] += power_lwbp_cost
                machine_eff_stats[m.id]['total_steam_cost_rp'] += steam_cost_est
        # -- END CONTINUOUS MACHINES INJECTION --

        # Build Efficiency Summary
        efficiency_summary_machines = []
        total_overall_eff = 0
        total_overall_count = 0

        for m_id, stats in machine_eff_stats.items():
            if stats['count'] > 0 or stats['batch_count'] > 0 or stats.get('is_continuous'):
                if stats.get('is_continuous') or stats['count'] == 0:
                    avg_eff = None
                    loss_time_str = None
                else:
                    avg_eff = stats['total_eff'] / stats['count']
                    total_loss_time = stats['total_loss_time']
                    total_overall_eff += stats['total_eff']
                    total_overall_count += stats['count']

                    hours = int(total_loss_time // 60)
                    mins = int(total_loss_time % 60)
                    loss_time_str = f"{hours}h {mins}m" if hours > 0 else f"{mins}m"
                    if total_loss_time < 0:
                        abs_loss = abs(total_loss_time)
                        h = int(abs_loss // 60)
                        m_min = int(abs_loss % 60)
                        loss_time_str = f"-{h}h {m_min}m" if h > 0 else f"-{m_min}m"

                steam_eff = None
                if stats['total_steam_with_ideal'] > 0:
                    steam_eff = min(100.0, (stats['total_steam_ideal_measured'] / stats['total_steam_with_ideal']) * 100)

                power_eff = None
                if stats['total_power_actual_measured'] > 0:
                    power_eff = min(100.0, (stats['total_power_ideal_measured'] / stats['total_power_actual_measured']) * 100)

                steam_ok_pct = None
                if stats['pressure_count'] > 0:
                    steam_ok_pct = (stats['steam_ok_count'] / stats['pressure_count']) * 100

                out_yd = stats['total_output_yd']
                total_cost_rp = stats['total_steam_cost_rp'] + stats['total_power_total_rp']
                steam_cost_per_yd = stats['total_steam_cost_rp'] / out_yd if out_yd > 0 else 0
                power_cost_per_yd = stats['total_power_total_rp'] / out_yd if out_yd > 0 else 0
                total_cost_per_yd = total_cost_rp / out_yd if out_yd > 0 else 0

                efficiency_summary_machines.append({
                    "machine_id": m_id,
                    "machine_name": stats['name'],
                    "group_name": stats.get('group_name', 'Lain-lain'),
                    "actual_duration_mins": round(stats.get('total_actual_mins', 0), 1),
                    "ideal_duration_mins": round(stats.get('total_ideal_mins', 0), 1),
                    "pos_loss_time_mins": round(stats.get('total_pos_loss_time', 0), 1),
                    "steam_ideal_kg": round(stats.get('total_steam_ideal', 0), 1),
                    "power_ideal_kwh": round(stats.get('total_power_ideal', 0), 1),
                    "power_loss_kwh": round(stats.get('total_power_loss_kwh', 0), 1),
                    "avg_eff": round(avg_eff, 1) if avg_eff is not None else None,
                    "total_loss_time_str": loss_time_str,
                    "steam_usage": round(stats['total_steam'], 1),
                    "steam_eff": round(steam_eff, 1) if steam_eff is not None else None,
                    "steam_ok_pct": round(steam_ok_pct, 1) if steam_ok_pct is not None else None,
                    "avg_steam_pressure": round(stats['total_pressure'] / stats['pressure_count'], 2) if stats.get('pressure_count', 0) > 0 else None,
                    "delay_heat_mins": round(stats.get('total_delay_heat', 0), 1),
                    "delay_cool_mins": round(stats.get('total_delay_cool', 0), 1),
                    "power_usage": round(stats['total_power'], 1),
                    "power_eff": round(power_eff, 1) if power_eff is not None else None,
                    "avg_changeover_minutes": machine_changeover.get(m_id),
                    "processes": stats['processes'],

                    "steam_loss_kg": round(stats['total_steam_loss_kg'], 1),
                    "steam_loss_rp": round(stats['total_steam_loss_rp'], 0),
                    "power_lwbp_rp": round(stats['total_power_lwbp_rp'], 0),
                    "power_wbp_rp": round(stats['total_power_wbp_rp'], 0),
                    "total_power_lwbp_kwh": round(stats.get('total_power_lwbp_kwh', 0), 1),
                    "total_power_wbp_kwh": round(stats.get('total_power_wbp_kwh', 0), 1),
                    "power_loss_rp": round(stats['total_power_loss_rp'], 0),

                    "output_yd": round(out_yd, 1),
                    "steam_cost_per_yd": round(steam_cost_per_yd, 0),
                    "power_cost_per_yd": round(power_cost_per_yd, 0),
                    "total_cost_per_yd": round(total_cost_per_yd, 0)
                })

        efficiency_summary_machines.sort(key=lambda x: x['avg_eff'] if x['avg_eff'] is not None else 999)

        efficiency_summary = {
            "average": round(total_overall_eff / total_overall_count, 1) if total_overall_count > 0 else 0,
            "machines": efficiency_summary_machines
        }

        # Proteksi ganda: Pastikan tidak ada ID proses yang terhitung ganda di PRESSURE_LOW dan HEATING_SLOW
        pressure_low_ids = set(p["id"] for p in eff_problem_data["PRESSURE_LOW"]["processes"])
        eff_problem_data["HEATING_SLOW"]["processes"] = [
            p for p in eff_problem_data["HEATING_SLOW"]["processes"]
            if p["id"] not in pressure_low_ids
        ]

        # Pareto: sort kategori by count desc + cumulative %
        problem_categories = [
            { "code": k, "label": v["label"], "count": len(v["processes"]), "color": v["color"], "processes": v["processes"] }
            for k, v in eff_problem_data.items()
            if len(v["processes"]) > 0
        ]
        problem_categories.sort(key=lambda x: x["count"], reverse=True)
        cumulative = 0
        for cat in problem_categories:
            cumulative += cat["count"]
            cat["cumulative_pct"] = round((cumulative / total_low_efficiency) * 100, 1) if total_low_efficiency > 0 else 0

        efficiency_problems = {
            "total_low_efficiency": total_low_efficiency,
            "total_analyzed": total_analyzed,
            "categories": problem_categories,
        }

        # ─────────────────────────────────────────────────────────────────
        # 7. DOWNTIME RANKING (dari bucket OFF, tanpa tabel baru)
        # ─────────────────────────────────────────────────────────────────
        downtime_ranking = _compute_downtime_ranking(machine_buckets, machine_meta, AVAIL_INTERVAL)

        # -------------------------------------------------------------
        # 8. DATA LOSSES HARIAN
        # -------------------------------------------------------------
        total_time_loss_mins = 0.0
        total_steam_loss_kg = 0.0
        total_power_loss_kwh = 0.0
        total_avail_loss_hours = 0.0

        # Availability Loss
        for m in machine_availabilities:
            if 'availability' in m:
                loss_pct = max(0.0, 100.0 - m['availability'])
                total_avail_loss_hours += (loss_pct / 100.0) * 24.0

        # Inefficiency Losses (Hanya yg positif)
        for p in processes:
            identity = getattr(p, 'identity', None)
            program = identity.program if identity else None

            # Time Loss
            if program and program.durasi_ideal and p.duration_effective:
                time_diff = p.duration_effective - program.durasi_ideal
                if time_diff > 0:
                    total_time_loss_mins += time_diff

            # Steam Loss (Lapis 1 - Lapis 3)
            if p.predicted_steam_kg and p.predicted_steam_ideal_kg:
                steam_diff = p.predicted_steam_kg - p.predicted_steam_ideal_kg
                if steam_diff > 0:
                    total_steam_loss_kg += steam_diff

            # Power Loss (dengan tambahan toleransi keluar-masuk kain <= 45 menit di durasi ideal)
            elec_m = _compute_batch_electricity_metrics(p, program, lwbp_rate)
            if elec_m['pos_loss_kwh'] > 0:
                total_power_loss_kwh += elec_m['pos_loss_kwh']

        losses_summary = {
            "time_loss_hours": round(total_time_loss_mins / 60.0, 1),
            "avail_loss_hours": round(total_avail_loss_hours, 1),
            "steam_loss_kg": round(total_steam_loss_kg, 1),
            "power_loss_kwh": round(total_power_loss_kwh, 1),
        }

        # ─────────────────────────────────────────────────────────────────
        # 8. OEE-LITE & KPI TURUNAN
        # ─────────────────────────────────────────────────────────────────
        avg_performance = efficiency_summary["average"]
        oee_combined = round(avg_avail * avg_performance / 100, 1) if avg_avail > 0 and avg_performance > 0 else 0

        total_process_count = processes.count()
        steam_per_batch = round(total_steam_usage / total_process_count, 1) if total_process_count > 0 else 0

        hours_availability = f"{round(avg_avail, 1)}%"
        performance_pct = f"{avg_performance}%"

        return {
            "date_range":         f"{start_time.strftime('%d %b %Y %H:%M')} - {end_time.strftime('%d %b %Y %H:%M')}",
            "total_steam_usage":  round(total_steam_usage, 1),
            "total_processes":    total_process_count,
            "steam_per_batch":    steam_per_batch,
            "avg_changeover_minutes": plant_avg_changeover,
            "hours_availability": hours_availability,
            "performance_pct":    performance_pct,
            "oee_lite": {
                "availability": round(avg_avail, 1),
                "performance": avg_performance,
                "combined": oee_combined,
            },
            "world_class": {
                "availability": 90,
                "performance": 95,
                "combined": 85,
            },
            "production_summary": {
                "power_kwh": round(total_power_kwh, 1),
                "power_lwbp_kwh": round(total_power_lwbp_kwh, 1),
                "power_wbp_kwh": round(total_power_wbp_kwh, 1),
                "fresh_yd": round(total_fresh_yd, 1),
                "creaping_yd": round(total_creaping_yd, 1),
                "other_yd": round(total_other_yd, 1),
            },
            "steam_series":       steam_series,
            "heatmap_groups":     groups_data,
            "history_groups":     history_groups,
            "availability_groups": availability_groups,
            "availability_summary": availability_summary,
            "efficiency_problems": efficiency_problems,
            "efficiency_summary": efficiency_summary,
            "downtime_ranking": downtime_ranking,
            "losses_summary": losses_summary,
        }

    @classmethod
    def compute_daily_summary_data(cls, date: str) -> dict:
        return cls.compute_daily_summary(date)
