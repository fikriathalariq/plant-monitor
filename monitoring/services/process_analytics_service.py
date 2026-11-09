from datetime import datetime, timedelta
from django.utils import timezone
from django.db.models import Q
from django.core.cache import cache
from ninja.errors import HttpError

from monitoring.models import (
    Machine, DyeingProcess, DyeingIdentity, MachineMinuteLog,
    MachineStatusSnapshot, GlobalSettings, DataAnomaly, AnomalyThresholdMaster,
    MachinePhysicsProfile
)
from monitoring.utils.steam_active import is_steam_active_from_snapshot
from monitoring.utils.cooling_active import is_cooling_active_from_snapshot


class ProcessAnalyticsService:
    @classmethod
    def compute_analytics(cls, process_id: str, machine: str = None, batch: str = None, request=None) -> dict:
        from monitoring.models import (
            GlobalSettings, MachineStatusSnapshot, DataAnomaly, AnomalyThresholdMaster
        )
        from monitoring.utils.steam_active import is_steam_active_from_snapshot
        from monitoring.utils.cooling_active import is_cooling_active_from_snapshot
        from django.core.cache import cache
        from django.db.models import Q

        process = None
        if process_id and str(process_id).isdigit():
            pid = int(process_id)
            process = DyeingProcess.objects.select_related('machine', 'machine__group', 'identity', 'identity__program').filter(id=pid).first()
            if not process:
                from monitoring.models import DyeingIdentity
                ident = DyeingIdentity.objects.filter(id=pid).select_related('dyeing_process', 'dyeing_process__machine', 'dyeing_process__machine__group', 'dyeing_process__identity__program').first()
                if ident and ident.dyeing_process:
                    process = ident.dyeing_process

        # Fallback 1: Cek query params machine & batch
        lookup_machine = machine or (getattr(request, 'GET', None) or {}).get('machine')
        lookup_batch = batch or (getattr(request, 'GET', None) or {}).get('batch')

        # Fallback 2: Cek cache metadata batch jika batch baru saja di-reprocess
        if not process and process_id and str(process_id).isdigit():
            try:
                cached_meta = cache.get(f"dyeing_process_meta_{process_id}")
                if cached_meta:
                    lookup_machine = lookup_machine or cached_meta.get("machine")
                    lookup_batch = lookup_batch or cached_meta.get("batch")
            except Exception:
                pass

        # Resolusi cerdas ke batch terbaru jika process_id berubah karena reprocessing
        if not process and (lookup_machine or lookup_batch):
            qs = DyeingProcess.objects.select_related('machine', 'machine__group', 'identity', 'identity__program')
            if lookup_machine:
                qs = qs.filter(Q(machine__code__iexact=lookup_machine) | Q(machine__name__iexact=lookup_machine))
            if lookup_batch:
                try:
                    b_num = int(lookup_batch)
                    qs = qs.filter(Q(batch_number=b_num) | Q(identity__batch__iexact=str(lookup_batch)))
                except ValueError:
                    qs = qs.filter(identity__batch__iexact=str(lookup_batch))
            process = qs.order_by('-start_time', '-id').first()

        if not process:
            raise HttpError(404, f"Data laporan audit untuk Proses #{process_id} tidak ditemukan di sistem database.")

        # Simpan mapping ID ke cache agar link ini tetap valid selama 3 hari ke depan meskipun di-reprocess
        try:
            cache.set(f"dyeing_process_meta_{process.id}", {
                "machine": process.machine.code,
                "batch": process.batch_number,
            }, timeout=259200)
        except Exception:
            pass
        identity = getattr(process, 'identity', None)
        program = identity.program if identity else None
        settings = GlobalSettings.load()
        threshold = getattr(settings, 'steam_healthy_threshold', 3.8)

        # 1. Basic KPI & Timing
        loss_time = None
        efficiency = None
        grade = "-"

        if program and program.durasi_ideal and process.duration_effective:
            loss_time = round(process.duration_effective - program.durasi_ideal, 1)
            efficiency = round((program.durasi_ideal / process.duration_effective) * 100, 1)
            if efficiency >= 80:
                grade = 'A'
            elif efficiency >= 60:
                grade = 'B'
            else:
                grade = 'C'

        heat_dur = process.real_heating_duration or process.heating_duration or 0
        hold_dur = process.steady_duration or 0
        cool_dur = process.cooling_duration or 0
        total_dur = heat_dur + hold_dur + cool_dur

        phase_pct = {}
        if total_dur > 0:
            phase_pct['heat'] = round(heat_dur / total_dur * 100, 1)
            phase_pct['cooling'] = round(cool_dur / total_dur * 100, 1)
            if hold_dur > 0:
                phase_pct['hold'] = round(hold_dur / total_dur * 100, 1)

        # 2. Time-series Chart Data + Plant Steam Demand + Boiler Coal Speed
        start_dt = process.start_time
        end_dt = process.end_time or timezone.now()

        logs = list(
            MachineMinuteLog.objects.filter(
                machine=process.machine, timestamp__range=(start_dt, end_dt)
            ).order_by('timestamp').values_list('timestamp', 'temperature', 'thermal_state', 'gradient')
        )

        target_points = 90
        if len(logs) > target_points:
            step = max(1, len(logs) // target_points)
            downsampled = logs[::step]
            if logs[-1] != downsampled[-1]:
                downsampled.append(logs[-1])
        else:
            downsampled = logs

        # Steam_Pr & Speed_RB_Steam logs
        boiler_logs = MachineMinuteLog.objects.filter(
            machine__code__in=['Steam_Pr', 'Speed_RB_Steam'],
            timestamp__range=(start_dt - timedelta(minutes=2), end_dt + timedelta(minutes=2))
        ).values_list('machine__code', 'timestamp', 'temperature')

        steam_dict = {}
        coal_dict = {}
        for m_code, ts, val in boiler_logs:
            t_min = ts.replace(second=0, microsecond=0)
            if m_code == 'Steam_Pr':
                steam_dict[t_min] = val
            elif m_code == 'Speed_RB_Steam':
                coal_dict[t_min] = val

        # Plant-wide steam demand from MachineStatusSnapshot during batch window
        all_steam_machines = Machine.objects.filter(is_active=True, average_steam_usage__gt=0)
        steam_machine_map = {m.code: m.average_steam_usage for m in all_steam_machines}

        snapshots = list(
            MachineStatusSnapshot.objects.filter(
                timestamp__range=(start_dt - timedelta(minutes=12), end_dt + timedelta(minutes=12))
            ).order_by('timestamp').values('timestamp', 'snapshot_data')
        )

        snap_series = []
        cool_snap_series = []
        for snap in snapshots:
            s_total = 0.0
            s_count = 0
            cool_count = 0
            cool_machines = []
            s_data = snap['snapshot_data'] or {}
            for m_code, m_state in s_data.items():
                avg_u = steam_machine_map.get(m_code)
                if avg_u and is_steam_active_from_snapshot(m_state):
                    s_total += avg_u
                    s_count += 1
                if is_cooling_active_from_snapshot(m_state, m_code):
                    cool_count += 1
                    cool_machines.append(m_code)
            snap_series.append((snap['timestamp'], round(s_total, 1), s_count))
            cool_snap_series.append((snap['timestamp'], cool_count, cool_machines))

        def _nearest_snapshot(ts):
            if not snap_series:
                return 0.0, 0
            best = min(snap_series, key=lambda x: abs((x[0] - ts).total_seconds()))
            if abs((best[0] - ts).total_seconds()) <= 900:
                return best[1], best[2]
            return 0.0, 0

        def _nearest_cooling_snapshot(ts):
            if not cool_snap_series:
                return 0, []
            best = min(cool_snap_series, key=lambda x: abs((x[0] - ts).total_seconds()))
            if abs((best[0] - ts).total_seconds()) <= 900:
                return best[1], best[2]
            return 0, []

        fuel_factor = getattr(settings, 'fuel_factor_steam_boiler', 0.0) or 0.0
        chart_data = []
        pressures_all = []
        demands_all = []
        coal_hz_all = []
        low_pr_points = []
        normal_pr_points = []

        for ts, temp, t_state, grad in downsampled:
            t_key = ts.replace(second=0, microsecond=0)
            steam_val = steam_dict.get(t_key)
            if steam_val is None:
                steam_val = steam_dict.get(t_key - timedelta(minutes=1)) or steam_dict.get(t_key + timedelta(minutes=1)) or 0
            coal_hz = coal_dict.get(t_key)
            if coal_hz is None:
                coal_hz = coal_dict.get(t_key - timedelta(minutes=1)) or coal_dict.get(t_key + timedelta(minutes=1))

            plant_demand, active_cnt = _nearest_snapshot(ts)
            cool_cnt, cool_list = _nearest_cooling_snapshot(ts)
            coal_kg_h = round(coal_hz * fuel_factor, 1) if (coal_hz is not None and fuel_factor > 0) else None
            time_str = timezone.localtime(ts).strftime('%H:%M')
            grad_val = grad if grad is not None else 0.0

            pt = {
                "time": time_str,
                "temp": round(temp, 1) if temp is not None else None,
                "pressure": round(steam_val, 2) if steam_val is not None else 0,
                "thermal_state": t_state or "-",
                "gradient": round(grad_val, 2),
                "cooling_rate": round(max(0.0, -grad_val), 2),
                "plant_steam_kg_h": plant_demand,
                "active_steam_machines": active_cnt,
                "active_cooling_machines": cool_cnt,
                "cooling_machines": ", ".join(cool_list) if cool_list else "-",
                "coal_speed_hz": round(coal_hz, 2) if coal_hz is not None else None,
                "coal_feed_kg_h": coal_kg_h,
            }
            chart_data.append(pt)

            if steam_val and steam_val > 0:
                pressures_all.append((steam_val, time_str))
                if steam_val < threshold:
                    low_pr_points.append(pt)
                else:
                    normal_pr_points.append(pt)
            if plant_demand > 0:
                demands_all.append((plant_demand, active_cnt, time_str))
            if coal_hz is not None:
                coal_hz_all.append(coal_hz)

        avg_steam = process.avg_steam_pressure
        if avg_steam is None and pressures_all:
            avg_steam = sum(p[0] for p in pressures_all) / len(pressures_all)

        # 3. Plant & Boiler Context Diagnosis (Penyebab Turunnya Pressure)
        min_pr_val, min_pr_time = (min(pressures_all, key=lambda x: x[0]) if pressures_all else (None, "-"))
        peak_demand_val, peak_active_cnt, peak_demand_time = (
            max(demands_all, key=lambda x: x[0]) if demands_all else (0.0, 0, "-")
        )
        avg_demand_val = round(sum(x[0] for x in demands_all) / len(demands_all), 1) if demands_all else 0.0
        avg_active_cnt = round(sum(x[1] for x in demands_all) / len(demands_all), 1) if demands_all else 0.0
        avg_coal_hz = round(sum(coal_hz_all) / len(coal_hz_all), 2) if coal_hz_all else None
        low_pr_pct = round((len(low_pr_points) / len(pressures_all)) * 100, 1) if pressures_all else 0.0
        steam_healthy_pct = round(100.0 - low_pr_pct, 1) if pressures_all else None

        demand_low_pr = (
            round(sum(x["plant_steam_kg_h"] for x in low_pr_points) / len(low_pr_points), 1)
            if low_pr_points else None
        )
        demand_norm_pr = (
            round(sum(x["plant_steam_kg_h"] for x in normal_pr_points) / len(normal_pr_points), 1)
            if normal_pr_points else None
        )
        coal_low_pr_vals = [x["coal_speed_hz"] for x in low_pr_points if x["coal_speed_hz"] is not None]
        coal_norm_pr_vals = [x["coal_speed_hz"] for x in normal_pr_points if x["coal_speed_hz"] is not None]
        coal_low_pr = round(sum(coal_low_pr_vals) / len(coal_low_pr_vals), 2) if coal_low_pr_vals else None
        coal_norm_pr = round(sum(coal_norm_pr_vals) / len(coal_norm_pr_vals), 2) if coal_norm_pr_vals else None

        if low_pr_pct > 15:
            is_peak_load_cause = (
                (demand_low_pr and demand_norm_pr and demand_low_pr > demand_norm_pr * 1.08)
                or (peak_active_cnt >= 7)
            )
            is_coal_lag_cause = (
                coal_low_pr is not None and (
                    coal_low_pr <= 1.0 or (coal_norm_pr and coal_low_pr < coal_norm_pr * 0.9)
                )
            )
            if is_peak_load_cause and is_coal_lag_cause:
                pr_cause_title = "Kombinasi Beban Puncak Pabrik & Respons Stoker Boiler Terlambat"
                pr_cause_tone = "red"
                pr_cause_detail = (
                    f"Tekanan uap turun di bawah {threshold} bar selama {low_pr_pct}% waktu proses (titik terendah {round(min_pr_val, 2)} bar pukul {min_pr_time}). "
                    f"Saat pressure drop, beban tarikan uap pabrik mencapai {demand_low_pr or peak_demand_val} kg/jam (puncak {peak_active_cnt} mesin aktif bersamaan), "
                    f"sementara speed batu bara boiler turun/rendah di {coal_low_pr} Hz."
                )
                pr_cause_action = (
                    "1) Terapkan staggering jadwal Heating agar tidak >6 mesin besar naik suhu serentak; "
                    "2) Evaluasi respons modulasi stoker batu bara boiler agar tidak terlambat menaikkan Hz saat beban naik."
                )
            elif is_peak_load_cause:
                pr_cause_title = "Tarikan Beban Puncak Pabrik (Concurrent Heating Demand)"
                pr_cause_tone = "amber"
                pr_cause_detail = (
                    f"Tekanan uap drop hingga {round(min_pr_val, 2)} bar pukul {min_pr_time} ({low_pr_pct}% durasi di bawah {threshold} bar). "
                    f"Boiler sudah memacu speed batu bara ({coal_low_pr or avg_coal_hz or '-'} Hz), namun beban pemakaian uap pabrik melonjak ke "
                    f"{demand_low_pr or peak_demand_val} kg/jam ({peak_active_cnt} mesin aktif bersamaan pukul {peak_demand_time})."
                )
                pr_cause_action = (
                    "Bukan kesalahan internal mesin ini. Atur penjadwalan jam mulai Heating (staggering 15–20 menit antar-mesin Jet) "
                    "untuk meratakan kurva beban uap pabrik."
                )
            elif is_coal_lag_cause:
                pr_cause_title = "Penurunan Speed Umpan Batu Bara / Regulasi Boiler"
                pr_cause_tone = "red"
                pr_cause_detail = (
                    f"Beban uap pabrik relatif normal (rata-rata {avg_demand_val} kg/jam), namun tekanan drop ke {round(min_pr_val, 2)} bar pukul {min_pr_time} "
                    f"karena speed feeder batu bara boiler rendah ({coal_low_pr} Hz vs normal {coal_norm_pr or avg_coal_hz} Hz)."
                )
                pr_cause_action = (
                    "Koordinasikan dengan tim Boiler untuk menjaga kestabilan umpan batu bara (Speed_RB_Steam), "
                    "cek kualitas/kalori batu bara, dan hindari jeda pengisian hopper."
                )
            else:
                pr_cause_title = "Fluktuasi Suplai Tekanan Header Uap"
                pr_cause_tone = "amber"
                pr_cause_detail = (
                    f"Terdapat {low_pr_pct}% waktu proses dengan tekanan uap < {threshold} bar (minimum {round(min_pr_val, 2)} bar pukul {min_pr_time}) "
                    f"pada beban rata-rata pabrik {avg_demand_val} kg/jam."
                )
                pr_cause_action = "Periksa kestabilan tekanan header utama dan jalur distribusi pipa menuju grup mesin ini."
        else:
            pr_cause_title = "Suplai Tekanan Uap Boiler Stabil & Sehat"
            pr_cause_tone = "emerald"
            pr_cause_detail = (
                f"Tekanan uap terjaga sehat selama {steam_healthy_pct or 100}% waktu proses (rata-rata {round(avg_steam, 2) if avg_steam else '-'} bar) "
                f"meski beban pabrik rata-rata {avg_demand_val} kg/jam (puncak {peak_active_cnt} mesin aktif)."
            )
            pr_cause_action = "Suplai uap dari boiler mendukung penuh performa pemanasan mesin pada batch ini."

        plant_boiler_context = {
            "threshold_bar": threshold,
            "avg_pressure_bar": round(avg_steam, 2) if avg_steam is not None else None,
            "min_pressure_bar": round(min_pr_val, 2) if min_pr_val is not None else None,
            "min_pressure_time": min_pr_time,
            "steam_healthy_pct": steam_healthy_pct,
            "low_pressure_pct": low_pr_pct,
            "avg_plant_demand_kg_h": avg_demand_val,
            "peak_plant_demand_kg_h": peak_demand_val,
            "peak_demand_time": peak_demand_time,
            "avg_active_machines": avg_active_cnt,
            "peak_active_machines": peak_active_cnt,
            "avg_coal_speed_hz": avg_coal_hz,
            "demand_during_low_pr_kg_h": demand_low_pr,
            "demand_during_normal_pr_kg_h": demand_norm_pr,
            "coal_hz_during_low_pr": coal_low_pr,
            "coal_hz_during_normal_pr": coal_norm_pr,
            "diagnosis": {
                "title": pr_cause_title,
                "tone": pr_cause_tone,
                "detail": pr_cause_detail,
                "action": pr_cause_action,
            },
        }

        # 3.B Cooling Context & Concurrent Cooling Diagnosis
        cool_dur = process.cooling_duration or 0.0
        cool_ideal_ref = program.durasi_cooling_ideal if program else None
        overrun_cool_mins = max(0.0, cool_dur - cool_ideal_ref) if cool_ideal_ref else max(0.0, cool_dur - 30.0)

        # Identifikasi titik mulai cooling untuk chart khusus cooling s/d end_time (sesuai request user)
        cool_start_dt = process.cooling_start_time
        if not cool_start_dt:
            if logs:
                peak_log = max(logs, key=lambda x: x[1] if x[1] is not None else 0)
                cool_start_dt = peak_log[0]
            else:
                cool_start_dt = start_dt

        cool_end_dt = process.end_time or end_dt

        # Ambil logs fase cooling s/d end_time
        cool_logs = [l for l in logs if l[0] >= cool_start_dt and l[0] <= cool_end_dt]
        if len(cool_logs) > 60:
            c_step = max(1, len(cool_logs) // 60)
            c_downsampled = cool_logs[::c_step]
            if cool_logs[-1] != c_downsampled[-1]:
                c_downsampled.append(cool_logs[-1])
        else:
            c_downsampled = cool_logs

        cooling_chart_data = []
        concurrent_counts_in_cooling = []
        concurrent_all_machines_set = set()
        peak_cool_machines = 0
        peak_cool_time = "-"

        for c_ts, c_temp, c_state, c_grad in c_downsampled:
            c_time_str = timezone.localtime(c_ts).strftime('%H:%M')
            c_cnt, c_list = _nearest_cooling_snapshot(c_ts)
            concurrent_counts_in_cooling.append(c_cnt)
            if c_cnt > peak_cool_machines:
                peak_cool_machines = c_cnt
                peak_cool_time = c_time_str
            for m in c_list:
                if m != process.machine.code:
                    concurrent_all_machines_set.add(m)
            g_val = c_grad if c_grad is not None else 0.0
            cooling_chart_data.append({
                "time": c_time_str,
                "temp": round(c_temp, 1) if c_temp is not None else None,
                "gradient": round(g_val, 2),
                "cooling_rate": round(max(0.0, -g_val), 2),
                "active_cooling_machines": c_cnt,
                "cooling_machines": ", ".join(c_list) if c_list else "-",
            })

        avg_cool_cnt = round(sum(concurrent_counts_in_cooling) / len(concurrent_counts_in_cooling), 1) if concurrent_counts_in_cooling else 0.0
        avg_cool_grad = process.cooling_avg_gradient
        if (avg_cool_grad is None or avg_cool_grad == 0) and cooling_chart_data:
            rates = [pt['cooling_rate'] for pt in cooling_chart_data if pt['cooling_rate'] > 0]
            avg_cool_grad = round(sum(rates) / len(rates), 2) if rates else None
        else:
            avg_cool_grad = round(abs(avg_cool_grad), 2) if avg_cool_grad else None

        ideal_cool_grad = None
        if cool_ideal_ref and cool_ideal_ref > 0 and process.max_temp:
            ideal_cool_grad = round(max(0.0, (process.max_temp - 70.0) / cool_ideal_ref), 2)

        is_cool_delayed = (cool_ideal_ref and cool_dur > cool_ideal_ref * 1.2 and overrun_cool_mins >= 8) or (not cool_ideal_ref and cool_dur > 45)

        if not is_cool_delayed:
            cool_cause_title = "Performa Pendinginan Mesin Prima & Suplai Air Pendingin Cukup"
            cool_cause_tone = "emerald"
            cool_cause_detail = (
                f"Fase cooling berjalan efisien selama {round(cool_dur)} menit (laju rata-rata {avg_cool_grad or '-'} °C/menit) "
                f"hingga suhu akhir {round(process.end_temp or 0, 1)}°C. Proses tetap lancar meskipun terdapat {peak_cool_machines} mesin "
                f"lain yang juga cooling bersamaan di pabrik (rata-rata {avg_cool_cnt} mesin)."
            )
            cool_cause_action = "Performa penukar panas (Heat Exchanger) dan suplai air pendingin bekerja prima mendukung siklus waktu batch ini."
        else:
            peer_list_sample = list(concurrent_all_machines_set)[:5]
            peer_str = ", ".join(peer_list_sample) + ("..." if len(concurrent_all_machines_set) > 5 else "")
            if peak_cool_machines >= 4 or avg_cool_cnt >= 2.5:
                cool_cause_title = "Indikasi Perebutan Air Pendingin (Beban Puncak Mesin Cooling Bersamaan)"
                cool_cause_tone = "amber"
                cool_cause_detail = (
                    f"Fase cooling berlangsung lambat selama {round(cool_dur)} menit (lebih lama +{round(overrun_cool_mins)} menit dari target "
                    f"{round(cool_ideal_ref or 30)} menit, laju rata-rata {avg_cool_grad or '-'} °C/menit). Selama fase ini, terpantau puncak "
                    f"lonjakan beban di mana {peak_cool_machines} mesin melakukan cooling serentak pukul {peak_cool_time} "
                    f"(rata-rata {avg_cool_cnt} mesin: {peer_str or '-'}). Lonjakan mesin serentak membagi suplai debit/tekanan cooling water pabrik, "
                    f"menurunkan efisiensi perpindahan panas Heat Exchanger."
                )
                cool_cause_action = (
                    "Bukan murni kerusakan mesin ini. Terapkan jeda bertahap (staggering 10–15 menit) pelepasan proses cooling antar-mesin Jet, "
                    "atau evaluasi kestabilan tekanan pompa booster sirkulasi cooling tower saat jam sibuk pabrik."
                )
            else:
                cool_cause_title = "Terindikasi Kendala Internal Mesin: Penukar Panas (HE) / Katup Pendingin"
                cool_cause_tone = "red"
                cool_cause_detail = (
                    f"Proses cooling molor mencapai {round(cool_dur)} menit (lebih lama +{round(overrun_cool_mins)} menit dari target "
                    f"{round(cool_ideal_ref or 30)} menit) dengan laju lambat ({avg_cool_grad or '-'} °C/menit), padahal beban pabrik tergolong "
                    f"sepi (hanya puncak {peak_cool_machines} mesin, rata-rata {avg_cool_cnt} mesin cooling). Suplai air pendingin pabrik longgar, "
                    f"namun serapan pendinginan internal mesin tetap rendah."
                )
                cool_cause_action = (
                    "Lakukan pengecekan pemeliharaan (PM) pada mesin ini: 1) Cek bukaan pneumatic cooling valve & aktuator; "
                    "2) Bersihkan filter strainer inlet air pendingin; 3) Jadwalkan descaling / flushing pipa Heat Exchanger dari kerak kapur/kotoran."
                )

        cooling_context = {
            "cooling_start_time": timezone.localtime(cool_start_dt).strftime('%H:%M') if cool_start_dt else "-",
            "reached_70c_time": timezone.localtime(process.reached_70c_time).strftime('%H:%M') if process.reached_70c_time else "-",
            "end_time": timezone.localtime(cool_end_dt).strftime('%H:%M') if cool_end_dt else "-",
            "cooling_duration_mins": round(cool_dur, 1),
            "cooling_ideal_mins": round(cool_ideal_ref, 1) if cool_ideal_ref else None,
            "overrun_mins": round(overrun_cool_mins, 1),
            "avg_cooling_gradient": avg_cool_grad,
            "ideal_cooling_gradient": ideal_cool_grad,
            "peak_concurrent_machines": peak_cool_machines,
            "peak_concurrent_time": peak_cool_time,
            "avg_concurrent_machines": avg_cool_cnt,
            "concurrent_machines_list": list(concurrent_all_machines_set),
            "cooling_chart_data": cooling_chart_data,
            "diagnosis": {
                "title": cool_cause_title,
                "tone": cool_cause_tone,
                "detail": cool_cause_detail,
                "action": cool_cause_action,
            },
        }

        # 4. Energy & Financial Audit (Harga Listrik, Harga Steam, Losses & Potensi Keuntungan)
        steam_rate = getattr(settings, 'steam_cost_per_kg', 350.0) or 350.0
        lwbp_rate = getattr(settings, 'electricity_base_rate', 1035.8) or 1035.8
        wbp_mult = getattr(settings, 'wbp_multiplier', 1.4) or 1.4
        wbp_rate = round(lwbp_rate * wbp_mult, 2)
        nom_kw = process.machine_nominal_power or getattr(process.machine, 'nominal_power', 0) or 0

        # Deteksi Multi-Heating / Re-Heating (>= 2x naik suhu dalam 1 proses sebelum <70°C)
        from monitoring.utils.batch_analyzer import detect_multi_heating_cycles
        multi_heat = detect_multi_heating_cycles(
            logs,
            start_bound=process.heating_start_time or process.start_time,
            end_bound=process.reached_70c_time or end_dt,
        )
        is_multi_heating = multi_heat['is_multi_heating']
        reheat_extra_mins = multi_heat['reheat_extra_mins'] if is_multi_heating else 0.0

        l1_steam = process.predicted_steam_kg or 0.0
        l2_steam = process.predicted_steam_best_kg or l1_steam
        l3_steam = process.predicted_steam_ideal_kg or l2_steam

        # Jika terjadi Re-Heating (>= 2x siklus naik suhu), pisahkan porsi uap ekstra
        # dari siklus ke-2 dst agar tidak salah diatribusikan ke Faktor Suplai Boiler.
        reheat_steam_loss_kg = 0.0
        if is_multi_heating and l1_steam > l3_steam:
            try:
                from monitoring.models import MachinePhysicsProfile
                from monitoring.services.pinn_engine import PINNSteamPredictor
                prof = (
                    MachinePhysicsProfile.objects.filter(machine=process.machine, is_active=True).first()
                    or MachinePhysicsProfile.get_best_for_machine(process.machine)
                )
                if prof:
                    l1_single_cycle = round(
                        PINNSteamPredictor().predict(
                            process, prof.to_physics_dict(), weights=None, force_ideal=False, single_cycle_only=True
                        ),
                        1,
                    )
                    reheat_steam_loss_kg = max(0.0, round(l1_steam - l1_single_cycle, 1))
            except Exception:
                pass
            if reheat_steam_loss_kg == 0.0 and multi_heat['cycles']:
                c1_m = multi_heat['cycles'][0]['total_mins']
                all_m = sum(c['total_mins'] for c in multi_heat['cycles'])
                if all_m > c1_m > 0:
                    reheat_steam_loss_kg = round(l1_steam * ((all_m - c1_m) / all_m), 1)
            reheat_steam_loss_kg = min(reheat_steam_loss_kg, max(0.0, l1_steam - l3_steam))

        steam_loss_total_kg = max(0.0, l1_steam - l3_steam)
        steam_loss_machine_kg = max(0.0, l1_steam - l2_steam)
        steam_loss_supply_kg = max(0.0, min(l1_steam, l2_steam) - l3_steam - reheat_steam_loss_kg)
        reheat_steam_loss_rp = round(reheat_steam_loss_kg * steam_rate)

        steam_cost_actual_rp = round(l1_steam * steam_rate)
        steam_cost_ideal_rp = round(l3_steam * steam_rate)
        steam_loss_total_rp = round(steam_loss_total_kg * steam_rate)
        steam_loss_machine_rp = round(steam_loss_machine_kg * steam_rate)
        steam_loss_supply_rp = round(steam_loss_supply_kg * steam_rate)
        steam_eff_pct = round((l3_steam / l1_steam) * 100, 1) if l1_steam > 0 else None

        # Operator delay minutes & fabric handling allowance (<70C to OFF up to 45 mins)
        keep_ideal_m = (program.durasi_keeping_ideal or 0) if program else 0
        over_hold_mins = max(0.0, hold_dur - keep_ideal_m) if keep_ideal_m > 0 else 0.0
        late_stop_mins = 0.0
        if process.reached_70c_time and process.end_time and process.end_time > process.reached_70c_time:
            late_stop_mins = max(0.0, (process.end_time - process.reached_70c_time).total_seconds() / 60.0)
        pre_heat_idle_mins = 0.0
        if process.heating_start_time and process.start_time and process.heating_start_time > process.start_time:
            pre_heat_idle_mins = max(0.0, (process.heating_start_time - process.start_time).total_seconds() / 60.0)

        # Deteksi Anomali & Stagnasi Fase Cooling (suhu tertahan >= 70°C atau cooling molor drastis)
        # Catatan: jika is_multi_heating=True, rentang cooling_start_time -> reached_70c_time
        # berisi siklus Re-Heating ke-2 dst, sehingga tidak diklasifikasikan sebagai stagnasi cooling biasa.
        cool_ideal_m = (program.durasi_cooling_ideal or 0.0) if program else 0.0
        cool_overrun_mins = max(0.0, cool_dur - cool_ideal_m) if cool_ideal_m > 0 else 0.0
        cooling_stagnant_mins = 0.0
        stag_start_str = None
        stag_end_str = None
        stag_avg_temp = None

        if process.cooling_start_time and logs and not is_multi_heating:
            c_end_bound = process.reached_70c_time or end_dt
            cool_logs = [
                (ts, temp) for ts, temp, *rest in logs
                if ts >= process.cooling_start_time
                and ts <= c_end_bound
                and temp is not None
                and temp >= 70.0
            ]
            if len(cool_logs) >= 10:
                # Periksa jendela 5 menit (5 log @1 menit): jika suhu tidak turun (< 0.4°C per 5 menit),
                # berarti proses pendinginan tertahan/stagnan di tengah jalan sebelum mencapai 70°C.
                stag_indices = []
                win = 5
                for idx in range(win, len(cool_logs)):
                    t_prev = cool_logs[idx - win][1]
                    t_curr = cool_logs[idx][1]
                    dt_m = max(1.0, (cool_logs[idx][0] - cool_logs[idx - win][0]).total_seconds() / 60.0)
                    drop_rate = (t_prev - t_curr) / dt_m  # °C per menit
                    if drop_rate < 0.08:  # < 0.4°C dalam 5 menit (stagnan / plateau)
                        stag_indices.append(idx)
                if stag_indices:
                    cooling_stagnant_mins = float(len(stag_indices))
                    first_idx = max(0, stag_indices[0] - win)
                    last_idx = stag_indices[-1]
                    stag_start_str = timezone.localtime(cool_logs[first_idx][0]).strftime('%H:%M')
                    stag_end_str = timezone.localtime(cool_logs[last_idx][0]).strftime('%H:%M')
                    stag_temps = [cool_logs[i][1] for i in stag_indices]
                    stag_avg_temp = round(sum(stag_temps) / len(stag_temps), 1)

        # Durasi keluar-masuk kain (pasca-cooling <70°C s/d OFF) maksimal 45 menit
        # dimasukkan sebagai tambahan pada Durasi Ideal Listrik (bukan dihitung sebagai Loss Listrik)
        FABRIC_HANDLING_MAX_MINS = 45.0
        fabric_handling_allowance_mins = min(late_stop_mins, FABRIC_HANDLING_MAX_MINS)
        excess_late_stop_mins = max(0.0, late_stop_mins - FABRIC_HANDLING_MAX_MINS)

        recipe_ideal_mins = (program.durasi_ideal or 0.0) if program else (process.program_ideal_duration_mins or 0.0)
        elec_ideal_duration_mins = (recipe_ideal_mins + fabric_handling_allowance_mins) if recipe_ideal_mins > 0 else 0.0

        pwr_actual_kwh = process.power_consumption_kwh or 0.0
        if elec_ideal_duration_mins > 0 and nom_kw > 0:
            pwr_ideal_kwh = round((elec_ideal_duration_mins / 60.0) * nom_kw, 2)
        elif process.ideal_power_consumption_kwh:
            pwr_ideal_kwh = round(process.ideal_power_consumption_kwh + (fabric_handling_allowance_mins / 60.0) * nom_kw, 2)
        else:
            pwr_ideal_kwh = pwr_actual_kwh

        pwr_lwbp_kwh = process.power_consumption_lwbp_kwh or 0.0
        pwr_wbp_kwh = process.power_consumption_wbp_kwh or 0.0
        pwr_loss_kwh = max(0.0, pwr_actual_kwh - pwr_ideal_kwh)

        pwr_cost_lwbp_rp = round(process.power_cost_lwbp or (pwr_lwbp_kwh * lwbp_rate))
        pwr_cost_wbp_rp = round(process.power_cost_wbp or (pwr_wbp_kwh * wbp_rate))
        pwr_cost_actual_rp = round(process.power_cost_total or (pwr_cost_lwbp_rp + pwr_cost_wbp_rp))
        pwr_cost_ideal_rp = round(pwr_ideal_kwh * lwbp_rate)
        pwr_loss_overrun_rp = round(pwr_loss_kwh * lwbp_rate)
        pwr_loss_wbp_surcharge_rp = round(pwr_wbp_kwh * (wbp_rate - lwbp_rate))
        pwr_loss_total_rp = max(0, pwr_cost_actual_rp - pwr_cost_ideal_rp)
        pwr_eff_pct = round(min(100.0, (pwr_ideal_kwh / pwr_actual_kwh) * 100), 1) if pwr_actual_kwh > 0 else None

        out_yd = identity.output_yard if (identity and identity.output_yard) else None
        total_actual_rp = steam_cost_actual_rp + pwr_cost_actual_rp
        total_ideal_rp = steam_cost_ideal_rp + pwr_cost_ideal_rp
        total_loss_rp = steam_loss_total_rp + pwr_loss_total_rp

        cost_per_yd_actual = round(total_actual_rp / out_yd) if (out_yd and out_yd > 0) else None
        cost_per_yd_ideal = round(total_ideal_rp / out_yd) if (out_yd and out_yd > 0) else None
        loss_per_yd = round(total_loss_rp / out_yd) if (out_yd and out_yd > 0) else None

        cool_stag_waste_mins = cooling_stagnant_mins if cooling_stagnant_mins >= 15 else 0.0
        operator_waste_mins = over_hold_mins + excess_late_stop_mins + cool_stag_waste_mins + reheat_extra_mins
        operator_loss_kwh = (operator_waste_mins / 60.0) * nom_kw
        operator_loss_rp = min(pwr_loss_overrun_rp, round(operator_loss_kwh * lwbp_rate))
        remaining_overrun_rp = max(0, pwr_loss_overrun_rp - operator_loss_rp)

        if low_pr_pct > 15:
            supply_pwr_share_rp = round(remaining_overrun_rp * 0.65)
            machine_pwr_share_rp = remaining_overrun_rp - supply_pwr_share_rp
        else:
            supply_pwr_share_rp = 0
            machine_pwr_share_rp = remaining_overrun_rp

        bucket_supply_rp = steam_loss_supply_rp + supply_pwr_share_rp
        bucket_machine_rp = steam_loss_machine_rp + machine_pwr_share_rp
        bucket_operator_rp = operator_loss_rp + reheat_steam_loss_rp
        bucket_wbp_rp = pwr_loss_wbp_surcharge_rp
        bucket_sum = max(1, bucket_supply_rp + bucket_machine_rp + bucket_operator_rp + bucket_wbp_rp)

        op_parts = []
        if is_multi_heating:
            op_parts.append(
                f"re-heating / {multi_heat['cycle_count']}x naik suhu (+{round(reheat_extra_mins)}m waktu & +{round(reheat_steam_loss_kg, 1)} kg uap)"
            )
        if over_hold_mins > 0:
            op_parts.append(f"over-holding (+{round(over_hold_mins)}m)")
        if cool_stag_waste_mins > 0:
            op_parts.append(f"stagnasi fase cooling di ~{stag_avg_temp}°C (+{round(cool_stag_waste_mins)}m)")
        if excess_late_stop_mins > 0:
            op_parts.append(f"durasi pasca-cooling >45m (+{round(excess_late_stop_mins)}m)")

        if op_parts:
            op_desc = f"Kerugian akibat {' & '.join(op_parts)}."
        else:
            op_desc = "Tidak ada keterlambatan operasional (holding & cooling sesuai target, waktu keluar-masuk kain ≤45 menit)."

        loss_attribution = [
            {
                "key": "steam_supply",
                "label": "Faktor Suplai Uap / Tekanan Boiler",
                "amount_rp": bucket_supply_rp,
                "share_pct": round((bucket_supply_rp / bucket_sum) * 100, 1) if total_loss_rp > 0 else 0,
                "desc": "Kerugian akibat tekanan uap drop / fraksi uap basah (Lapis 2 vs Lapis 3) & waktu tunggu pemanasan.",
            },
            {
                "key": "machine_condition",
                "label": "Faktor Fisik & Komponen Mesin",
                "amount_rp": bucket_machine_rp,
                "share_pct": round((bucket_machine_rp / bucket_sum) * 100, 1) if total_loss_rp > 0 else 0,
                "desc": "Kerugian akibat performa termal mesin (steam trap/insulasi/HE Lapis 1 vs Lapis 2) & laju cooling.",
            },
            {
                "key": "operator_delay",
                "label": "Faktor Operasional & Keterlambatan Operator",
                "amount_rp": bucket_operator_rp,
                "share_pct": round((bucket_operator_rp / bucket_sum) * 100, 1) if total_loss_rp > 0 else 0,
                "desc": op_desc,
            },
            {
                "key": "wbp_tariff",
                "label": "Faktor Penjadwalan Jam Puncak (Tarif WBP)",
                "amount_rp": bucket_wbp_rp,
                "share_pct": round((bucket_wbp_rp / bucket_sum) * 100, 1) if total_loss_rp > 0 else 0,
                "desc": f"Selisih tarif mahal WBP (17:00–22:00) sebesar {round(pwr_wbp_kwh, 1)} kWh × Rp {round(wbp_rate - lwbp_rate)}/kWh.",
            },
        ]
        loss_attribution.sort(key=lambda x: x["amount_rp"], reverse=True)

        # Monthly batch frequency on this machine (last 30 days before/around batch)
        ref_end = process.start_time + timedelta(days=1)
        ref_start_30d = ref_end - timedelta(days=30)
        recent_30d_count = DyeingProcess.objects.filter(
            machine=process.machine,
            is_valid_process=True,
            start_time__gte=ref_start_30d,
            start_time__lte=ref_end,
        ).count()
        monthly_freq = max(recent_30d_count, 45)

        energy_financials = {
            "tariffs": {
                "steam_rp_per_kg": steam_rate,
                "lwbp_rp_per_kwh": round(lwbp_rate, 1),
                "wbp_rp_per_kwh": wbp_rate,
                "wbp_window": "17:00 - 22:00",
                "nominal_power_kw": nom_kw,
            },
            "steam": {
                "actual_kg": round(l1_steam, 1),
                "best_machine_kg": round(l2_steam, 1),
                "ideal_kg": round(l3_steam, 1),
                "loss_total_kg": round(steam_loss_total_kg, 1),
                "loss_machine_cond_kg": round(steam_loss_machine_kg, 1),
                "loss_supply_press_kg": round(steam_loss_supply_kg, 1),
                "cost_actual_rp": steam_cost_actual_rp,
                "cost_ideal_rp": steam_cost_ideal_rp,
                "loss_total_rp": steam_loss_total_rp,
                "loss_machine_cond_rp": steam_loss_machine_rp,
                "loss_supply_press_rp": steam_loss_supply_rp,
                "eff_pct": steam_eff_pct,
            },
            "power": {
                "actual_kwh": round(pwr_actual_kwh, 2),
                "ideal_kwh": round(pwr_ideal_kwh, 2),
                "recipe_ideal_mins": round(recipe_ideal_mins, 1),
                "fabric_allowance_mins": round(fabric_handling_allowance_mins, 1),
                "elec_ideal_duration_mins": round(elec_ideal_duration_mins, 1),
                "lwbp_kwh": round(pwr_lwbp_kwh, 2),
                "wbp_kwh": round(pwr_wbp_kwh, 2),
                "loss_kwh": round(pwr_loss_kwh, 2),
                "cost_lwbp_rp": pwr_cost_lwbp_rp,
                "cost_wbp_rp": pwr_cost_wbp_rp,
                "cost_actual_rp": pwr_cost_actual_rp,
                "cost_ideal_rp": pwr_cost_ideal_rp,
                "loss_total_rp": pwr_loss_total_rp,
                "loss_overrun_rp": pwr_loss_overrun_rp,
                "loss_wbp_surcharge_rp": pwr_loss_wbp_surcharge_rp,
                "eff_pct": pwr_eff_pct,
            },
            "totals": {
                "output_yard": round(out_yd, 1) if out_yd else None,
                "total_actual_rp": total_actual_rp,
                "total_ideal_rp": total_ideal_rp,
                "total_loss_rp": total_loss_rp,
                "cost_per_yard_actual_rp": cost_per_yd_actual,
                "cost_per_yard_ideal_rp": cost_per_yd_ideal,
                "loss_per_yard_rp": loss_per_yd,
                "monthly_batch_freq": monthly_freq,
                "projected_monthly_saving_rp": round(total_loss_rp * monthly_freq),
                "projected_annual_saving_rp": round(total_loss_rp * monthly_freq * 12),
            },
            "loss_attribution": loss_attribution,
        }

        # 5. Historical Program Benchmark (Apakah Mesin Normal atau Tidak? — Khusus Mesin Ini & Program yang Sama)
        program_benchmark = None
        if program:
            same_machine_qs = list(
                DyeingProcess.objects.filter(
                    machine=process.machine,
                    identity__program=program,
                    is_complete=True,
                    is_valid_process=True,
                    duration_effective__gt=0,
                )
                .select_related('machine', 'identity')
                .order_by('-start_time')[:40]
            )
            if process not in same_machine_qs:
                same_machine_qs.insert(0, process)

            same_m_list = [b for b in same_machine_qs if b.id != process.id][:20]
            ref_pool = same_m_list if same_m_list else [process]
            peer_qs = same_machine_qs

            def _stat_avg(items, getter):
                vals = [getter(x) for x in items if getter(x) is not None and getter(x) > 0]
                return round(sum(vals) / len(vals), 1) if vals else None

            avg_heat_hist = _stat_avg(ref_pool, lambda b: b.real_heating_duration or b.heating_duration)
            avg_hold_hist = _stat_avg(ref_pool, lambda b: b.steady_duration)
            avg_cool_hist = _stat_avg(ref_pool, lambda b: b.cooling_duration)
            avg_tot_hist = _stat_avg(ref_pool, lambda b: b.duration_effective)
            avg_pr_hist = _stat_avg(ref_pool, lambda b: b.avg_steam_pressure)
            avg_steam_hist = _stat_avg(ref_pool, lambda b: b.predicted_steam_kg)

            # Chart series: maksimal 20 batch dari MESIN YANG SAMA & PROGRAM YANG SAMA diurutkan kronologis
            chart_pool = same_m_list[:19] + [process]
            chart_pool = sorted({b.id: b for b in chart_pool}.values(), key=lambda x: x.start_time)

            history_series = []
            for b in chart_pool:
                b_heat = round(b.real_heating_duration or b.heating_duration or 0, 1)
                b_hold = round(b.steady_duration or 0, 1)
                b_cool = round(b.cooling_duration or 0, 1)
                b_pr = round(b.avg_steam_pressure, 2) if b.avg_steam_pressure is not None else None
                history_series.append({
                    "id": b.id,
                    "label": f"#{b.batch_number}" if b.machine_id == process.machine_id else f"{b.machine.name} #{b.batch_number}",
                    "machine_name": b.machine.name,
                    "date": timezone.localtime(b.start_time).strftime('%d/%m'),
                    "heat_mins": b_heat,
                    "hold_mins": b_hold,
                    "cool_mins": b_cool,
                    "total_mins": round(b.duration_effective or (b_heat + b_hold + b_cool), 1),
                    "avg_pressure": b_pr,
                    "steam_kg": round(b.predicted_steam_kg or 0, 1),
                    "is_current": b.id == process.id,
                    "is_same_machine": b.machine_id == process.machine_id,
                })

            # Machine Health Evaluation (Normal vs Tidak Normal)
            heat_ideal_ref = program.durasi_heating_ideal or avg_heat_hist or 0
            cool_ideal_ref = program.durasi_cooling_ideal or avg_cool_hist or 0

            heat_diff_vs_hist = (heat_dur - avg_heat_hist) if (avg_heat_hist and heat_dur) else 0
            cool_diff_vs_hist = (cool_dur - avg_cool_hist) if (avg_cool_hist and cool_dur) else 0

            # Heating verdict
            if heat_dur and heat_ideal_ref and heat_dur > heat_ideal_ref * 1.2:
                if avg_steam and avg_steam < threshold:
                    heat_status = "TERHAMBAT SUPLAI UAP"
                    heat_tone = "amber"
                    heat_eval = (
                        f"Durasi Heating ({round(heat_dur)} mnt) lebih lambat dari histori ({avg_heat_hist or '-'} mnt) & resep ({round(heat_ideal_ref)} mnt), "
                        f"namun disebabkan oleh tekanan uap rata-rata yang rendah ({round(avg_steam, 2)} bar < {threshold} bar). "
                        f"Secara mekanis sistem pemanas mesin masih merespons sesuai tekanan yang tersedia."
                    )
                else:
                    heat_status = "TIDAK NORMAL (LAMBAT PADA TEKANAN CUKUP)"
                    heat_tone = "red"
                    heat_eval = (
                        f"PERHATIAN: Tekanan uap rata-rata sudah memadai ({round(avg_steam, 2) if avg_steam else '-'} bar), namun durasi Heating mencapai "
                        f"{round(heat_dur)} mnt (histori rata-rata: {avg_heat_hist or '-'} mnt, ideal: {round(heat_ideal_ref)} mnt). "
                        f"Indikasi kuat kendala internal mesin: bukaan control valve uap tidak 100%, strainer uap mampet, atau steam trap tertahan."
                    )
            else:
                heat_status = "NORMAL"
                heat_tone = "emerald"
                heat_eval = (
                    f"Performa pemanasan mesin NORMAL ({round(heat_dur)} mnt vs rata-rata histori {avg_heat_hist or '-'} mnt "
                    f"pada tekanan {round(avg_steam, 2) if avg_steam else '-'} bar, gradien +{round(process.heating_avg_gradient or 0, 2)} °C/mnt)."
                )

            # Cooling verdict
            if is_multi_heating:
                v0 = multi_heat['valleys'][0]
                c_last = multi_heat['cycles'][-1]
                final_cm = multi_heat['final_cooling_mins']
                cool_status = f"TERINTERUPSI RE-HEATING ({multi_heat['cycle_count']}x NAIK SUHU)"
                cool_tone = "red"
                cool_eval = (
                    f"Rentang pasca-cooling pertama mencapai {round(cool_dur)} mnt karena pada pukul {v0['cool_start_str']}–{v0['valley_str']} "
                    f"suhu turun parsial ke {v0['valley_temp']}°C lalu dipanaskan ulang (Re-Heating) ke {c_last['peak_temp']}°C hingga {c_last['hold_end_str']} "
                    f"(+{round(reheat_extra_mins)} mnt siklus tambahan). "
                    f"Pendinginan akhir sebenarnya hanya memakan {round(final_cm)} mnt (histori: {avg_cool_hist or '-'} mnt) — Heat Exchanger mesin normal."
                )
            elif cool_dur and cool_ideal_ref and cool_dur > max(cool_ideal_ref * 1.25, (avg_cool_hist or cool_ideal_ref) + 8):
                if cooling_stagnant_mins >= 15:
                    cool_status = "TIDAK NORMAL (STAGNASI / JEDA COOLING)"
                    cool_tone = "red"
                    cool_eval = (
                        f"Durasi Cooling ({round(cool_dur)} mnt vs ideal {round(cool_ideal_ref)} mnt) molor ekstrem karena suhu tertahan/stagnan "
                        f"di ~{stag_avg_temp}°C selama {round(cooling_stagnant_mins)} mnt ({stag_start_str}–{stag_end_str}) sebelum turun ke <70°C. "
                        f"Indikasi proses pendinginan/pembuangan air panas terhenti atau katup cooling tidak dibuka penuh oleh operator."
                    )
                else:
                    cool_status = "TIDAK NORMAL (COOLING LAMBAT)"
                    cool_tone = "red"
                    cool_eval = (
                        f"Durasi Cooling ({round(cool_dur)} mnt) lebih lambat +{round(cool_dur - (avg_cool_hist or cool_ideal_ref))} mnt dibanding histori program yang sama "
                        f"({avg_cool_hist or '-'} mnt) dan target ideal ({round(cool_ideal_ref)} mnt). "
                        f"Indikasi Heat Exchanger (HE) mulai berkerak (scaling), katup air pendingin kurang membuka, atau suhu cooling water naik."
                    )
            else:
                cool_status = "NORMAL"
                cool_tone = "emerald"
                cool_eval = (
                    f"Performa pendinginan mesin NORMAL ({round(cool_dur)} mnt vs histori {avg_cool_hist or '-'} mnt, "
                    f"gradien {round(process.cooling_avg_gradient or 0, 2)} °C/mnt)."
                )

            overall_normal = (heat_tone == "emerald" and cool_tone == "emerald")
            program_benchmark = {
                "program_name": program.nama,
                "sample_count_same_machine": len(same_m_list),
                "sample_count_total": len(peer_qs),
                "overall_machine_status": "KONDISI MESIN NORMAL" if overall_normal else (
                    "MESIN NORMAL (TERKENDALA SUPLAI UAP)" if (heat_tone == "amber" and cool_tone == "emerald")
                    else "TERDETEKSI GEJALA TIDAK NORMAL PADA MESIN"
                ),
                "overall_tone": "emerald" if overall_normal else ("amber" if (heat_tone == "amber" and cool_tone == "emerald") else "red"),
                "comparison": {
                    "current": {
                        "heat_mins": round(heat_dur, 1),
                        "hold_mins": round(hold_dur, 1),
                        "cool_mins": round(cool_dur, 1),
                        "total_mins": round(process.duration_effective or total_dur, 1),
                        "avg_pressure": round(avg_steam, 2) if avg_steam else None,
                        "steam_kg": round(l1_steam, 1),
                    },
                    "historical_avg": {
                        "heat_mins": avg_heat_hist,
                        "hold_mins": avg_hold_hist,
                        "cool_mins": avg_cool_hist,
                        "total_mins": avg_tot_hist,
                        "avg_pressure": avg_pr_hist,
                        "steam_kg": avg_steam_hist,
                    },
                    "recipe_ideal": {
                        "heat_mins": round(program.durasi_heating_ideal, 1) if program.durasi_heating_ideal else None,
                        "hold_mins": round(program.durasi_keeping_ideal, 1) if program.durasi_keeping_ideal else None,
                        "cool_mins": round(program.durasi_cooling_ideal, 1) if program.durasi_cooling_ideal else None,
                        "total_mins": round(program.durasi_ideal, 1) if program.durasi_ideal else None,
                        "avg_pressure": threshold,
                        "steam_kg": round(l3_steam, 1),
                    },
                },
                "heating_diagnosis": {
                    "status": heat_status,
                    "tone": heat_tone,
                    "detail": heat_eval,
                    "diff_vs_hist_mins": round(heat_diff_vs_hist, 1),
                },
                "cooling_diagnosis": {
                    "status": cool_status,
                    "tone": cool_tone,
                    "detail": cool_eval,
                    "diff_vs_hist_mins": round(cool_diff_vs_hist, 1),
                },
                "history_series": history_series,
            }

        # 6. Operator & Process Anomaly Forensics
        forensic_findings = []

        # Finding 0: Multiple Heating Cycles / Re-Heating (>= 2x naik suhu dalam 1 proses sebelum <70°C)
        if is_multi_heating:
            cyc_parts = []
            for c in multi_heat['cycles']:
                cyc_parts.append(
                    f"Siklus #{c['cycle_no']}: naik {c['start_str']}–{c['hold_start_str']} ({c['start_temp']}°C → {c['peak_temp']}°C, {round(c['heat_mins'])}m) "
                    f"& holding s/d {c['hold_end_str']} ({round(c['hold_mins'])}m)"
                )
            val_parts = []
            for v in multi_heat['valleys']:
                val_parts.append(
                    f"Cooling parsial #{v['valley_no']} ({v['cool_start_str']}–{v['valley_str']}): turun dari {v['from_peak_temp']}°C ke {v['valley_temp']}°C "
                    f"(-{v['drop_delta_c']}°C selama {round(v['cool_mins'])}m, belum mencapai <70°C) lalu dipanaskan ulang ke {v['to_peak_temp']}°C (+{v['rise_delta_c']}°C)"
                )
            rh_kwh = round((reheat_extra_mins / 60.0) * nom_kw, 1)
            rh_pwr_rp = round(rh_kwh * lwbp_rate)
            rh_tot_rp = rh_pwr_rp + reheat_steam_loss_rp
            masalah_note = f" Catatan operator: \"{identity.masalah}\"." if (identity and identity.masalah) else ""
            v_first = multi_heat['valleys'][0]
            forensic_findings.append({
                "code": "MULTIPLE_HEATING_CYCLES",
                "severity": "CRITICAL",
                "title": (
                    f"Terdeteksi {multi_heat['cycle_count']}x Siklus Pemanasan (Re-Heating) dalam 1 Batch "
                    f"(Turun ke {v_first['valley_temp']}°C Lalu Naik Kembali ke {v_first['to_peak_temp']}°C, +{round(reheat_extra_mins)} Menit)"
                ),
                "category": "Anomali Pemanasan Berulang (Re-Heating / Interupsi Proses)",
                "detail": (
                    f"Dalam satu batch terdeteksi {multi_heat['cycle_count']} kali proses kenaikan suhu karena pendinginan pertama berhenti di {v_first['valley_temp']}°C "
                    f"(di atas ambang 70°C) lalu dipanaskan ulang kembali. "
                    f"Rincian: {'; '.join(cyc_parts)}. Interupsi: {'; '.join(val_parts)}.{masalah_note}"
                ),
                "impact": (
                    f"Penambahan waktu siklus +{round(reheat_extra_mins)} menit, pemborosan uap ekstra siklus ulang +{round(reheat_steam_loss_kg, 1)} kg "
                    f"(Rp {reheat_steam_loss_rp:,}), serta listrik sirkulasi +{rh_kwh} kWh (Rp {rh_pwr_rp:,}) — total kerugian re-heating Rp {rh_tot_rp:,}."
                ),
                "recommendation": (
                    "Evaluasi penyebab pengulangan proses pada tengah jalan (seperti kain macet pada nozzle/reel, koreksi warna/shading ulang, "
                    "atau gangguan sirkulasi) agar tidak terjadi pemanasan uap ganda dalam satu batch."
                ),
            })

        # Finding 1: Over-holding at Peak Temp
        if keep_ideal_m > 0 and over_hold_mins > 8:
            oh_kwh = round((over_hold_mins / 60.0) * nom_kw, 1)
            oh_rp = round(oh_kwh * lwbp_rate)
            forensic_findings.append({
                "code": "OVER_HOLDING",
                "severity": "CRITICAL" if over_hold_mins > 25 else "WARNING",
                "title": f"Over-Holding pada Suhu Puncak (+{round(over_hold_mins)} Menit di Atas Ideal)",
                "category": "Indikasi Operasional / Tunggu Sampel",
                "detail": (
                    f"Fase Holding/Keeping berlangsung selama {round(hold_dur)} menit, padahal standar program hanya {round(keep_ideal_m)} menit. "
                    f"Indikasi operator menunggu konfirmasi matching warna (lab), penambahan obat (shading), atau terlambat memindahkan tahapan."
                ),
                "impact": f"Pemborosan +{round(over_hold_mins)} menit waktu mesin, +{oh_kwh} kWh listrik (Rp {oh_rp:,}), serta radiasi uap terus-menerus pada suhu {round(process.max_temp or 130)}°C.",
                "recommendation": "Tetapkan batas waktu tunggu sampel warna maksimal 10 menit dan siapkan dyestuff koreksi lebih cepat.",
            })

        # Finding 2: Post-cooling idle (Hanya dievaluasi jika > 45 menit setelah <70°C)
        if late_stop_mins > 45:
            ls_kwh = round((excess_late_stop_mins / 60.0) * nom_kw, 1)
            ls_rp = round(ls_kwh * lwbp_rate)
            r70_str = timezone.localtime(process.reached_70c_time).strftime('%H:%M') if process.reached_70c_time else "-"
            end_str = timezone.localtime(process.end_time).strftime('%H:%M') if process.end_time else "-"
            forensic_findings.append({
                "code": "LATE_STOP_AFTER_COOLING",
                "severity": "WARNING" if late_stop_mins <= 60 else "CRITICAL",
                "title": f"Durasi Pasca-Cooling Melebihi Batas 45 Menit ({round(late_stop_mins)} Menit Setelah <70°C, Molor +{round(excess_late_stop_mins)} Menit)",
                "category": "Evaluasi Waktu Bongkar-Muat Kain",
                "detail": (
                    f"Suhu mesin sudah turun mencapai 70°C pada pukul {r70_str}, dan mesin baru berhenti (OFF) pada pukul {end_str} "
                    f"({round(late_stop_mins)} menit kemudian). Setelah dikurangi toleransi wajar keluar-masuk kain (45 menit), "
                    f"terdapat kelebihan waktu +{round(excess_late_stop_mins)} menit."
                ),
                "impact": f"Kelebihan durasi sirkulasi listrik di atas batas toleransi 45 menit selama +{round(excess_late_stop_mins)} menit (+{ls_kwh} kWh / Rp {ls_rp:,}).",
                "recommendation": "Evaluasi apakah terjadi kendala saat keluar-masuk kain (unloading/loading) atau keterlambatan mematikan mesin setelah proses selesai.",
            })

        # Finding 2b: Cooling Phase Anomaly (Stagnasi Suhu di Tengah Cooling >=70°C atau Durasi Cooling Molor)
        cool_start_str = timezone.localtime(process.cooling_start_time).strftime('%H:%M') if process.cooling_start_time else "-"
        r70_or_end_str = (
            timezone.localtime(process.reached_70c_time).strftime('%H:%M')
            if process.reached_70c_time
            else (timezone.localtime(process.end_time).strftime('%H:%M') if process.end_time else "-")
        )
        if cooling_stagnant_mins >= 15 and (cool_overrun_mins > 10 or cool_dur > 35):
            cs_waste_m = max(cooling_stagnant_mins, cool_overrun_mins) if cool_ideal_m > 0 else cooling_stagnant_mins
            cs_kwh = round((cooling_stagnant_mins / 60.0) * nom_kw, 1)
            cs_rp = round(cs_kwh * lwbp_rate)
            ideal_info = f"; target ideal resep: {round(cool_ideal_m)} menit, molor +{round(cool_overrun_mins)} menit" if cool_ideal_m > 0 else ""
            forensic_findings.append({
                "code": "COOLING_STAGNATION_ANOMALY",
                "severity": "CRITICAL" if (cooling_stagnant_mins >= 30 or cool_overrun_mins >= 45) else "WARNING",
                "title": (
                    f"Stagnasi / Jeda pada Fase Cooling selama {round(cooling_stagnant_mins)} Menit di Suhu ~{stag_avg_temp}°C "
                    f"(Total Cooling {round(cool_dur)} Menit{f', +{round(cool_overrun_mins)}m di Atas Ideal' if cool_ideal_m > 0 else ''})"
                ),
                "category": "Anomali Fase Cooling & Kedisiplinan Operasional",
                "detail": (
                    f"Fase Cooling dimulai pukul {cool_start_str} dan baru mencapai <70°C pukul {r70_or_end_str} "
                    f"(total {round(cool_dur)} menit{ideal_info}). Pada rentang pukul {stag_start_str} s/d {stag_end_str} "
                    f"({round(cooling_stagnant_mins)} menit), penurunan suhu berhenti/tertahan di sekitar {stag_avg_temp}°C (di atas ambang 70°C) "
                    f"sebelum akhirnya didinginkan kembali."
                ),
                "impact": (
                    f"Mesin bersirkulasi tanpa progres pendinginan selama {round(cooling_stagnant_mins)} menit "
                    f"(pemborosan listrik +{cs_kwh} kWh / Rp {cs_rp:,} dan kehilangan kapasitas waktu mesin +{round(cs_waste_m)} menit)."
                ),
                "recommendation": (
                    "Evaluasi aktivitas operator pada jam stagnasi tersebut: pastikan katup cooling water / proses drain-fill "
                    "tidak ditinggalkan atau tertahan di tengah jalan sebelum suhu turun di bawah 70°C."
                ),
            })
        elif not is_multi_heating and cool_dur > 0 and (
            (cool_ideal_m > 0 and cool_overrun_mins > 15 and cool_dur > cool_ideal_m * 1.4)
            or (cool_ideal_m == 0 and cool_dur > 45)
        ):
            co_m = cool_overrun_mins if cool_ideal_m > 0 else (cool_dur - 30.0)
            co_kwh = round((co_m / 60.0) * nom_kw, 1)
            co_rp = round(co_kwh * lwbp_rate)
            forensic_findings.append({
                "code": "SLOW_COOLING_ANOMALY",
                "severity": "CRITICAL" if co_m >= 40 else "WARNING",
                "title": (
                    f"Durasi Cooling Molor Signifikan ({round(cool_dur)} Menit"
                    f"{f' vs Ideal {round(cool_ideal_m)} Menit, +{round(cool_overrun_mins)} Menit' if cool_ideal_m > 0 else ''})"
                ),
                "category": "Anomali Fase Cooling / Performa Pendinginan",
                "detail": (
                    f"Penurunan suhu dari puncak ke <70°C ({cool_start_str} s/d {r70_or_end_str}) memakan waktu {round(cool_dur)} menit "
                    f"dengan laju rata-rata {round(process.cooling_avg_gradient or 0, 2)} °C/menit"
                    f"{f', melampaui target ideal program ({round(cool_ideal_m)} menit) sebesar +{round(cool_overrun_mins)} menit' if cool_ideal_m > 0 else ''}."
                ),
                "impact": f"Memperpanjang waktu siklus mesin +{round(co_m)} menit dan menambah konsumsi listrik sirkulasi +{co_kwh} kWh (Rp {co_rp:,}).",
                "recommendation": "Periksa bukaan katup air pendingin (cooling valve), tekanan suplai cooling water, serta kebersihan pipa Heat Exchanger (scaling).",
            })

        # Finding 3: Mid-heating pause / stagnation
        heat_span = process.heating_span or 0
        if heat_span > 0 and heat_dur > 0 and (heat_span - heat_dur) > 10:
            pause_m = round(heat_span - heat_dur, 1)
            forensic_findings.append({
                "code": "MID_HEATING_PAUSE",
                "severity": "WARNING",
                "title": f"Jeda / Stagnasi di Tengah Fase Heating ({pause_m} Menit)",
                "category": "Anomali Kurva Pemanasan",
                "detail": (
                    f"Rentang waktu dari awal hingga akhir Heating memakan {round(heat_span)} menit, tetapi kenaikan suhu aktif hanya {round(heat_dur)} menit. "
                    f"Terdapat {pause_m} menit di mana suhu tertahan di tengah jalan (dosing obat bertahap atau interupsi pemanasan)."
                ),
                "impact": f"Memperpanjang waktu siklus dan meningkatkan kehilangan panas radiasi dinding mesin.",
                "recommendation": "Periksa apakah jeda tersebut merupakan step dosing standar resep atau interupsi tidak terencana oleh operator.",
            })

        # Finding 4: Pre-heating idle
        if pre_heat_idle_mins > 20:
            forensic_findings.append({
                "code": "PRE_HEAT_IDLE",
                "severity": "INFO",
                "title": f"Persiapan Awal Sebelum Heating Cukup Lama ({round(pre_heat_idle_mins)} Menit)",
                "category": "Persiapan & Loading",
                "detail": (
                    f"Mesin terdeteksi mulai aktif pukul {timezone.localtime(process.start_time).strftime('%H:%M')}, "
                    f"namun pemanasan efektif (Real Heat) baru dimulai pukul {timezone.localtime(process.heating_start_time).strftime('%H:%M')}."
                ),
                "impact": f"Waktu sirkulasi dingin awal selama {round(pre_heat_idle_mins)} menit sebelum katup uap dibuka.",
                "recommendation": "Pastikan kain dan larutan obat sudah siap sebelum pompa sirkulasi utama dinyalakan.",
            })

        # Finding 5: Start Temp High
        if process.start_temp and process.start_temp > 60:
            forensic_findings.append({
                "code": "START_TEMP_HIGH",
                "severity": "WARNING",
                "title": f"Suhu Awal Pengisian Terlalu Tinggi ({round(process.start_temp, 1)}°C > 60°C)",
                "category": "Prosedur Awal Proses",
                "detail": "Proses dimulai pada suhu di atas 60°C yang berisiko menyebabkan belang warna (uneven dyeing) atau menandakan sisa air panas belum terkuras.",
                "impact": "Risiko cacat kualitas pencelupan (re-process / cuci ulang).",
                "recommendation": "Pastikan pembilasan dan pendinginan selesai sebelum memulai obat batch baru.",
            })

        # Finding 6: Database DataAnomaly records
        db_anomalies = DataAnomaly.objects.filter(process_record=process)
        for anom in db_anomalies:
            flags_list = anom.details.get("flags", []) if isinstance(anom.details, dict) else []
            stat_flags = [f for f in flags_list if f in ('SUHU', 'SUHU_HARD', 'HEAT', 'KEEP', 'COOL')]

            if anom.is_resolved:
                forensic_findings.append({
                    "code": anom.anomaly_type,
                    "severity": "INFO",
                    "title": f"Status Resolusi Anomali: Selesai ({anom.resolved_action or 'SOLVED'})",
                    "category": "Tindak Lanjut Engineering",
                    "detail": f"Anomali ini telah diverifikasi dan diselesaikan ({anom.resolved_action}). Catatan: {anom.resolution_notes or '-'}",
                    "impact": "Data anomali telah diarsip / diselesaikan.",
                    "recommendation": "Tidak diperlukan tindakan lanjutan.",
                })
            elif stat_flags:
                # Hanya tampilkan jika ada deviasi statistik yang belum tercakup oleh kartu fisik di atas
                forensic_findings.append({
                    "code": anom.anomaly_type,
                    "severity": anom.severity,
                    "title": f"Deviasi Statistik Master Program: {anom.anomaly_type} ({', '.join(stat_flags)})",
                    "category": "Sistem Deteksi Statistik Mesin-Program",
                    "detail": f"Terdeteksi deviasi di luar batas normal kalibrasi mesin untuk parameter: {', '.join(stat_flags)}.",
                    "impact": "Menunjukkan profil waktu/suhu batch ini menyimpang dari histori normal mesin dan program terkait.",
                    "recommendation": "Verifikasi kesesuaian input resep/program dan parameter kontrol mesin.",
                })

        # Jika tidak ada anomali yang melebihi ambang batas evaluasi, biarkan kosong agar tidak ditampilkan

        return {
            "id": process.id,
            "identity_id": identity.id if identity else None,
            "machine_id": process.machine.id,
            "machine_name": process.machine.name,
            "machine_group": process.machine.group.name if process.machine.group else "-",
            "batch_number": process.batch_number,
            "start_time_iso": process.start_time.isoformat() if process.start_time else None,
            "report_date": timezone.localtime(process.start_time - timedelta(hours=6)).strftime('%Y-%m-%d'),
            "is_complete": process.is_complete,
            "thermal_status": process.machine.last_thermal_status if not process.is_complete else None,
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
                "output_yard": round(out_yd, 1) if out_yd else "-",
                "nozzle_main_pump": identity.nozzle_main_pump if identity and identity.nozzle_main_pump else "-",
                "cycle_puncak": identity.cycle_puncak if identity and identity.cycle_puncak else "-",
                "cycle_60": identity.cycle_60 if identity and identity.cycle_60 else "-",
                "start_time": timezone.localtime(process.start_time).strftime('%d %b %Y, %H:%M') if process.start_time else "-",
                "heat_start_time": timezone.localtime(process.heating_start_time).strftime('%d %b %Y, %H:%M') if process.heating_start_time else "-",
                "reached_70c_time": timezone.localtime(process.reached_70c_time).strftime('%d %b %Y, %H:%M') if process.reached_70c_time else "-",
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
                "end_temp": round(process.end_temp, 1) if process.end_temp else None,
                "heat_gradient": round(process.heating_avg_gradient, 2) if process.heating_avg_gradient else None,
                "cool_gradient": round(process.cooling_avg_gradient, 2) if process.cooling_avg_gradient else None,
                "max_temp_prg": program.suhu_max if program else None,
                "ideal_heat": round(process.ideal_heating_time, 1) if process.ideal_heating_time else None,
                "avg_steam": round(avg_steam, 2) if avg_steam else None,
                "over_hold_mins": round(over_hold_mins, 1),
                "late_stop_mins": round(late_stop_mins, 1),
                "pre_heat_idle_mins": round(pre_heat_idle_mins, 1),
            },
            "phase_breakdown": phase_pct,
            "chart_data": chart_data,
            "avg_steam": round(avg_steam, 2) if avg_steam else None,
            "energy_financials": energy_financials,
            "program_benchmark": program_benchmark,
            "operator_forensics": forensic_findings,
            "plant_boiler_context": plant_boiler_context,
            "cooling_context": cooling_context,
        }

    @classmethod
    def get_process_analytics(cls, request, process_id: str, machine: str = None, batch: str = None) -> dict:
        return cls.compute_analytics(process_id=process_id, machine=machine, batch=batch, request=request)
