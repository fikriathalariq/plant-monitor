import math
from datetime import datetime
from collections import defaultdict


class BatchCostCalculator:
    """
    Kalkulator finansial dan konsumsi energi listrik per batch produksi tekstil.
    Menghitung tarif WBP vs LWBP dan deviasi konsumsi terhadap baseline ideal.
    """
    DEFAULT_LWBP_RATE = 1035.8

    @classmethod
    def compute_electricity(cls, p, program=None, lwbp_rate=None, wbp_rate=None):
        """
        Hitung metrik listrik batch dengan menambahkan durasi keluar-masuk kain
        (pasca-cooling <70°C s/d OFF maksimal 45 menit) ke dalam Durasi Ideal Listrik.
        """
        if lwbp_rate is None:
            lwbp_rate = cls.DEFAULT_LWBP_RATE

        if program is None:
            ident = getattr(p, 'identity', None)
            program = ident.program if ident else None

        if wbp_rate is None:
            wbp_rate = round(lwbp_rate * 1.4, 2)

        late_stop_mins = 0.0
        if p.reached_70c_time and p.end_time and p.end_time > p.reached_70c_time:
            late_stop_mins = max(0.0, (p.end_time - p.reached_70c_time).total_seconds() / 60.0)

        fabric_allowance_mins = min(late_stop_mins, 45.0)
        recipe_ideal_mins = (program.durasi_ideal or 0.0) if (program and program.durasi_ideal) else (p.program_ideal_duration_mins or 0.0)
        elec_ideal_duration_mins = (recipe_ideal_mins + fabric_allowance_mins) if recipe_ideal_mins > 0 else 0.0

        nom_kw = p.machine_nominal_power or getattr(p.machine, 'nominal_power', 0) or 0
        actual_kwh = p.power_consumption_kwh
        lwbp_kwh = p.power_consumption_lwbp_kwh or 0.0
        wbp_kwh = p.power_consumption_wbp_kwh or 0.0

        cost_lwbp_rp = round(p.power_cost_lwbp if p.power_cost_lwbp is not None else (lwbp_kwh * lwbp_rate), 2)
        cost_wbp_rp = round(p.power_cost_wbp if p.power_cost_wbp is not None else (wbp_kwh * wbp_rate), 2)
        cost_actual_rp = round(p.power_cost_total if p.power_cost_total is not None else (cost_lwbp_rp + cost_wbp_rp), 2)

        ideal_kwh = None
        if elec_ideal_duration_mins > 0 and nom_kw > 0:
            ideal_kwh = round((elec_ideal_duration_mins / 60.0) * nom_kw, 2)
        elif p.ideal_power_consumption_kwh is not None:
            ideal_kwh = round(p.ideal_power_consumption_kwh + (fabric_allowance_mins / 60.0) * nom_kw, 2)

        raw_diff_kwh = None
        pos_loss_kwh = 0.0
        power_eff = None
        cost_ideal_rp = None
        cost_loss_rp = 0.0

        if actual_kwh is not None and ideal_kwh is not None:
            raw_diff_kwh = round(actual_kwh - ideal_kwh, 2)
            pos_loss_kwh = round(max(0.0, actual_kwh - ideal_kwh), 2)
            if actual_kwh > 0:
                power_eff = round(min(100.0, (ideal_kwh / actual_kwh) * 100.0), 1)
            cost_ideal_rp = round(ideal_kwh * lwbp_rate, 2)
            if cost_actual_rp > 0:
                cost_loss_rp = round(max(0.0, cost_actual_rp - cost_ideal_rp), 2)
            else:
                cost_loss_rp = round(pos_loss_kwh * lwbp_rate, 2)

        return {
            "actual_kwh": actual_kwh,
            "ideal_kwh": ideal_kwh,
            "raw_diff_kwh": raw_diff_kwh,
            "pos_loss_kwh": pos_loss_kwh,
            "power_eff": power_eff,
            "cost_lwbp_rp": cost_lwbp_rp,
            "cost_wbp_rp": cost_wbp_rp,
            "cost_actual_rp": cost_actual_rp,
            "cost_ideal_rp": cost_ideal_rp,
            "cost_loss_rp": cost_loss_rp,
            "recipe_ideal_mins": round(recipe_ideal_mins, 1),
            "fabric_allowance_mins": round(fabric_allowance_mins, 1),
            "elec_ideal_duration_mins": round(elec_ideal_duration_mins, 1),
            "late_stop_mins": round(late_stop_mins, 1),
        }


class ProcessDiagnosticService:
    """
    Layanan diagnostik dan klasifikasi operasional proses pewarnaan (DyeingProcess).
    Mendeteksi anomali pemanasan (PRESSURE_LOW vs HEATING_SLOW), changeover time,
    serta downtime ranking armada mesin.
    """

    @staticmethod
    def sort_machines_custom(machine_list, name_key='name'):
        zet_order = ['ZET 9', 'ZET 8', 'ZET 7', 'ZET 6', 'ZET 5', 'ZET 4', 'ZET 1', 'ZET 10', 'ZET 11', 'ZET 12']

        def get_sort_key(m):
            name = m.get(name_key, '')
            if name.startswith('JR ') or name.startswith('JR_'):
                try:
                    num = int(name.replace('JR_', '').replace('JR ', ''))
                    return (1, -num, name)
                except:
                    return (1, 0, name)
            elif name.startswith('JD ') or name.startswith('JD_') or name == 'Jet Mini HSK':
                if name == 'Jet Mini HSK' or name == 'JD_JetMiniHisaka':
                    return (2, 9999, name)
                try:
                    num = int(name.replace('JD_', '').replace('JD ', ''))
                    return (2, num, name)
                except:
                    return (2, 999, name)
            elif name.startswith('ZET ') or name.startswith('ZET_'):
                norm = name.replace('ZET_', 'ZET ')
                try:
                    idx = zet_order.index(norm)
                    return (3, idx, name)
                except ValueError:
                    return (3, 999, name)
            return (4, 0, name)

        machine_list.sort(key=get_sort_key)

    @staticmethod
    def classify_process_problems(process, program, pressure_threshold=None):
        if not process.duration_effective or not program.durasi_ideal:
            return []

        overall_eff = (program.durasi_ideal / process.duration_effective) * 100
        if overall_eff >= 85:
            return []

        problems = []

        if pressure_threshold is None:
            try:
                from monitoring.models import GlobalSettings
                settings = GlobalSettings.load()
                pressure_threshold = getattr(settings, 'steam_healthy_threshold', 3.8) or 3.8
            except Exception:
                pressure_threshold = 3.8

        # 1. PRESSURE_LOW vs 2. HEATING_SLOW
        # PERATURAN MUTLAK:
        # Proses yang mengalami Tekanan Steam Kurang (PRESSURE_LOW) TIDAK BOLEH masuk ke Heating Lambat (HEATING_SLOW).
        # Walaupun tekanan kurang pasti menyebabkan heating lambat, penyebab utamanya adalah pasokan steam (boiler/pipa).
        # Kategori HEATING_SLOW HANYA untuk proses dengan tekanan steam CUKUP (>= threshold) tapi pemanasan tetap lambat,
        # yang mengindikasikan murni masalah mesin hari itu (valve macet, trap jebol, koil kotor, dll).
        is_pressure_low = (
            process.avg_steam_pressure is not None and
            process.avg_steam_pressure < pressure_threshold
        )

        if is_pressure_low:
            problems.append("PRESSURE_LOW")
        else:
            # 2. HEATING_SLOW (Hanya dievaluasi jika tekanan steam CUKUP / BUKAN masalah tekanan)
            ideal_heat_keep = (program.durasi_heating_ideal or 0) + (program.durasi_keeping_ideal or 0)
            real_heat = process.real_heating_duration or 0
            steady = process.steady_duration or 0

            if real_heat + steady > 0 and ideal_heat_keep > 0:
                heat_eff = (ideal_heat_keep / (real_heat + steady)) * 100
                if heat_eff < 85:
                    problems.append("HEATING_SLOW")

        # 3. COOLING_SLOW
        if program.durasi_cooling_ideal and process.cooling_duration and process.cooling_duration > 0:
            cool_eff = (program.durasi_cooling_ideal / process.cooling_duration) * 100
            if cool_eff < 85:
                problems.append("COOLING_SLOW")

        # 4. START_TEMP_HIGH
        if process.start_temp and process.start_temp > 60:
            problems.append("START_TEMP_HIGH")

        if len(problems) == 0:
            problems.append("OTHERS")

        return problems

    @staticmethod
    def compute_downtime_ranking(machine_buckets, machine_meta, interval_minutes):
        """Hitung idle time (state OFF) per mesin dari bucket availability."""
        total_buckets = (24 * 60) // interval_minutes
        ranking = []

        for m_id, meta in machine_meta.items():
            buckets = machine_buckets.get(m_id, {})
            off_minutes = 0.0
            stop_events = 0
            in_off_run = False

            for i in range(total_buckets):
                state = buckets.get(i, "OFF")
                if state == "OFF":
                    off_minutes += interval_minutes
                    if not in_off_run:
                        stop_events += 1
                        in_off_run = True
                else:
                    in_off_run = False

            if off_minutes > 0:
                hours = int(off_minutes // 60)
                mins = int(off_minutes % 60)
                idle_str = f"{hours}h {mins}m" if hours > 0 else f"{mins}m"
                ranking.append({
                    "machine_id": meta["id"],
                    "machine_name": meta["name"],
                    "idle_minutes": round(off_minutes, 1),
                    "idle_str": idle_str,
                    "stop_events": stop_events,
                })

        ranking.sort(key=lambda x: x["idle_minutes"], reverse=True)
        return ranking

    @staticmethod
    def compute_changeover_stats(processes):
        """Hitung rata-rata changeover (gap antar batch) per mesin."""
        by_machine = defaultdict(list)
        from monitoring.models import GlobalSettings
        settings = GlobalSettings.load()
        threshold = getattr(settings, 'steam_healthy_threshold', 3.8)
        for p in processes:
            if p.end_time and p.is_complete:
                by_machine[p.machine_id].append(p)

        machine_changeover = {}
        all_gaps = []

        for m_id, m_procs in by_machine.items():
            m_procs.sort(key=lambda x: x.start_time or datetime.min)
            gaps = []
            for i in range(1, len(m_procs)):
                prev = m_procs[i - 1]
                curr = m_procs[i]
                if not prev.end_time:
                    continue
                next_start = curr.heating_start_time or curr.start_time
                if not next_start:
                    continue
                gap_minutes = (next_start - prev.end_time).total_seconds() / 60.0
                if 0 < gap_minutes < 24 * 60:
                    gaps.append(gap_minutes)

            if gaps:
                avg_gap = sum(gaps) / len(gaps)
                machine_changeover[m_id] = round(avg_gap, 1)
                all_gaps.extend(gaps)

        plant_avg = round(sum(all_gaps) / len(all_gaps), 1) if all_gaps else 0
        return machine_changeover, plant_avg
