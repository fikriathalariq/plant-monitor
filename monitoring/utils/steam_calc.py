"""
Kalkulasi agregat pemakaian uap (kg/h) per menit shift.

AUTO: fase ∈ {HEAT, STEADY} memakai uap; COOL tidak.
MANUAL: fase RUNNING memakai uap (selaras is_manual_on / Running).
"""
from collections import defaultdict

from monitoring.utils.shift_time import TOTAL_BUCKETS

STEAM_ACTIVE_PHASES = frozenset({"HEAT", "STEADY"})
STEAM_ACTIVE_PHASES_BY_MODE = {
    "AUTO": frozenset({"HEAT", "STEADY"}),
    "MANUAL": frozenset({"RUNNING"}),
}


def steam_active_phases_for_mode(operation_mode="AUTO"):
    return STEAM_ACTIVE_PHASES_BY_MODE.get(operation_mode or "AUTO", STEAM_ACTIVE_PHASES)


def compute_steam_timeline_from_plan_batches(batches, steam_usage_by_machine_id, total_minutes=TOTAL_BUCKETS):
    """
    Hitung array kg/h per menit dari daftar ProductionPlanBatch (sudah di-prefetch blocks).

    batches: iterable of ProductionPlanBatch (dengan .blocks dan .machine / .machine_id)
    steam_usage_by_machine_id: dict[int, float] machine.id -> average_steam_usage
    """
    values = [0.0] * total_minutes

    for batch in batches:
        usage = float(steam_usage_by_machine_id.get(batch.machine_id, 0) or 0)
        if usage <= 0:
            continue
        mode = getattr(batch.machine, "operation_mode", "AUTO") if hasattr(batch, "machine") else "AUTO"
        active = steam_active_phases_for_mode(mode)
        offset = int(batch.start_offset_minutes or 0)
        cursor = offset
        for block in batch.blocks.all():
            dur = int(block.duration_minutes or 0)
            if dur <= 0:
                continue
            if block.phase in active:
                end = min(cursor + dur, total_minutes)
                start = max(0, cursor)
                for t in range(start, end):
                    values[t] += usage
            cursor += dur
            if cursor >= total_minutes:
                break

    rounded = [round(v, 1) for v in values]
    max_kg_h = max(rounded) if rounded else 0.0
    return {
        "values": rounded,
        "max_kg_h": max_kg_h,
        "unit": "kg/h",
    }


def compute_carryover_blocks(prev_batches, total_minutes=TOTAL_BUCKETS):
    """
    Dari batch-batch plan HARI SEBELUMNYA (prev_batches, dgn .blocks & .machine prefetched),
    hitung sisa ("tail") blok yang meluber ke hari ini (menit >= total_minutes, di-rebase ke
    offset 0). Hanya batch yang benar overflow yang masuk hasil.

    Return: dict[machine_code] -> list of {
        "source_batch_id", "source_plan_id", "label", "machine" (instance),
        "source_start_offset_minutes", "source_blocks" (list utuh {phase,duration_minutes}),
        "tail_blocks" (potongan yg jatuh di hari ini, {phase,duration_minutes}),
    }
    """
    result = defaultdict(list)
    for batch in prev_batches:
        source_blocks = []
        tail_blocks = []
        cursor = batch.start_offset_minutes
        for block in batch.blocks.all():
            dur = int(block.duration_minutes or 0)
            source_blocks.append({"phase": block.phase, "duration_minutes": dur})
            block_start = cursor
            block_end = cursor + dur
            if block_end > total_minutes:
                tail_dur = block_end - max(block_start, total_minutes)
                if tail_dur > 0:
                    tail_blocks.append({"phase": block.phase, "duration_minutes": tail_dur})
            cursor = block_end
        if tail_blocks:
            result[batch.machine.code].append({
                "source_batch_id": batch.id,
                "source_plan_id": batch.plan_id,
                "label": batch.label,
                "machine": batch.machine,
                "source_start_offset_minutes": batch.start_offset_minutes,
                "source_blocks": source_blocks,
                "tail_blocks": tail_blocks,
            })
    return result


def compute_carryover_steam_contribution(carryover_by_machine, total_minutes=TOTAL_BUCKETS):
    """Array kg/h tambahan dari tail_blocks carryover (dimulai dari menit 0 hari ini)."""
    values = [0.0] * total_minutes
    for entries in carryover_by_machine.values():
        for entry in entries:
            machine = entry["machine"]
            usage = float(getattr(machine, "average_steam_usage", 0) or 0)
            if usage <= 0:
                continue
            mode = getattr(machine, "operation_mode", "AUTO") or "AUTO"
            active = steam_active_phases_for_mode(mode)
            cursor = 0
            for block in entry["tail_blocks"]:
                dur = int(block["duration_minutes"] or 0)
                if dur <= 0:
                    continue
                if block["phase"] in active:
                    end = min(cursor + dur, total_minutes)
                    for t in range(max(0, cursor), end):
                        values[t] += usage
                cursor += dur
                if cursor >= total_minutes:
                    break
    return values


def compute_steam_timeline_from_minute_buckets(steam_buckets, data_end, total_minutes=TOTAL_BUCKETS):
    """
    Dari dict bucket_index -> kg/h (seperti di api_snapshots) jadi struktur steam_heatmap.
    """
    values = [round(steam_buckets.get(i, 0), 1) for i in range(data_end)]
    max_kg_h = max(values) if values else 0.0
    return {
        "values": values,
        "max_kg_h": max_kg_h,
        "unit": "kg/h",
    }


def is_steam_active_state(state, operation_mode="AUTO"):
    """State timeline dianggap memakai uap (mirror _log_is_steam_active)."""
    if operation_mode == "MANUAL":
        return state == "RUNNING"
    return state in STEAM_ACTIVE_PHASES
