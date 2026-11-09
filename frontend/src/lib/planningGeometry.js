/**
 * Geometry & steam helpers for Production Planning (pure functions, no React).
 */
export const SHIFT_MINUTES = 24 * 60;
export const GRID_MINUTES = 15;
export const DEFAULT_PHASE_RATIOS = [30, 60, 20]; // Heat / Hold / Cool proportions

export const STEAM_ACTIVE_PHASES_BY_MODE = {
  AUTO: new Set(['HEAT', 'STEADY']),
  MANUAL: new Set(['RUNNING']),
};

export function minutesToPct(minutes, total = SHIFT_MINUTES) {
  return (minutes / total) * 100;
}

export function pctToMinutes(pct, total = SHIFT_MINUTES) {
  return Math.round((pct / 100) * total);
}

export function snapToGrid(minutes, grid = GRID_MINUTES) {
  return Math.max(0, Math.round(minutes / grid) * grid);
}

export function clamp(n, lo, hi) {
  return Math.min(hi, Math.max(lo, n));
}

export function batchTotalDuration(batch) {
  return (batch.blocks || []).reduce((s, b) => s + (b.durationMinutes || 0), 0);
}

export function rangesOverlap(aStart, aEnd, bStart, bEnd) {
  return aStart < bEnd && bStart < aEnd;
}

/** True if moving/placing `candidate` would overlap another batch on same machine. */
export function hasOverlap(batches, candidateClientId, startOffset, duration) {
  const end = startOffset + duration;
  return (batches || []).some((b) => {
    if (b.clientId === candidateClientId) return false;
    const bEnd = b.startOffsetMinutes + batchTotalDuration(b);
    return rangesOverlap(startOffset, end, b.startOffsetMinutes, bEnd);
  });
}

/**
 * Split totalMinutes across HEAT/STEADY/COOL using DEFAULT_PHASE_RATIOS.
 */
export function splitDefaultPhases(totalMinutes, grid = GRID_MINUTES) {
  const total = Math.max(grid, snapToGrid(totalMinutes, grid));
  const sumR = DEFAULT_PHASE_RATIOS.reduce((a, b) => a + b, 0);
  let heat = snapToGrid(Math.round((total * DEFAULT_PHASE_RATIOS[0]) / sumR), grid);
  let hold = snapToGrid(Math.round((total * DEFAULT_PHASE_RATIOS[1]) / sumR), grid);
  let cool = total - heat - hold;
  if (cool < 0) {
    hold = Math.max(0, hold + cool);
    cool = 0;
  }
  if (heat < grid && total >= grid) {
    heat = grid;
    hold = Math.max(0, total - heat - cool);
  }
  return [
    { phase: 'HEAT', durationMinutes: heat },
    { phase: 'STEADY', durationMinutes: hold },
    { phase: 'COOL', durationMinutes: cool },
  ];
}

/** Satu blok RUNNING untuk mesin MANUAL. */
export function createRunningBlock(totalMinutes, grid = GRID_MINUTES) {
  const total = Math.max(grid, snapToGrid(totalMinutes, grid));
  return [{ phase: 'RUNNING', durationMinutes: total }];
}

/**
 * Client-side steam timeline (kg/h per minute) — mirrors backend steam_calc.
 * machinesByCode: { [code]: { average_steam_usage, operation_mode } }
 */
export function computeSteamTimeline(batchesByMachine, machinesByCode) {
  const values = new Array(SHIFT_MINUTES).fill(0);

  Object.entries(batchesByMachine || {}).forEach(([code, batches]) => {
    const machine = machinesByCode?.[code];
    const usage = Number(machine?.average_steam_usage || 0);
    if (usage <= 0) return;
    const mode = machine?.operation_mode || 'AUTO';
    const active = STEAM_ACTIVE_PHASES_BY_MODE[mode] || STEAM_ACTIVE_PHASES_BY_MODE.AUTO;

    (batches || []).forEach((batch) => {
      let cursor = batch.startOffsetMinutes || 0;
      (batch.blocks || []).forEach((block) => {
        const dur = block.durationMinutes || 0;
        if (dur > 0 && active.has(block.phase)) {
          const end = Math.min(cursor + dur, SHIFT_MINUTES);
          const start = Math.max(0, cursor);
          for (let t = start; t < end; t += 1) {
            values[t] += usage;
          }
        }
        cursor += dur;
      });
    });
  });

  const rounded = values.map((v) => Math.round(v * 10) / 10);
  return {
    values: rounded,
    max_kg_h: rounded.length ? Math.max(...rounded) : 0,
    unit: 'kg/h',
  };
}

export function newClientId() {
  return `b_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

/** Menit sejak 06:00 → "HH:mm" clock time. */
export function offsetToClockLabel(offsetMinutes) {
  const total = ((6 * 60) + (offsetMinutes || 0)) % (24 * 60);
  const h = Math.floor(total / 60);
  const m = total % 60;
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
}

/** "HH:mm" → menit sejak 06:00 (0–1439). */
export function clockLabelToOffset(hhmm) {
  const [hs, ms] = String(hhmm || '06:00').split(':');
  const h = Number(hs);
  const m = Number(ms);
  if (Number.isNaN(h) || Number.isNaN(m)) return 0;
  let mins = h * 60 + m;
  // Shift starts at 06:00: times before 06:00 are next calendar day within shift
  if (mins < 6 * 60) mins += 24 * 60;
  return clamp(mins - 6 * 60, 0, SHIFT_MINUTES - 1);
}

export function planFromApi(apiPlan) {
  const batchesByMachine = {};
  (apiPlan.groups || []).forEach((g) => {
    (g.machines || []).forEach((m) => {
      batchesByMachine[m.code] = (m.batches || []).map((b) => ({
        clientId: b.is_continuation ? `cont_${b.id}` : `srv_${b.id}`,
        id: b.id,
        label: b.label || '',
        startOffsetMinutes: b.start_offset_minutes,
        programId: b.program_id ?? null,
        programName: b.program_name || '',
        blocks: (b.blocks || []).map((bl) => ({
          phase: bl.phase,
          durationMinutes: bl.duration_minutes,
        })),
        // Batch "lanjutan" dari plan hari sebelumnya (overflow > 24 jam). Editable, tapi
        // menulis ke plan sumber (bukan plan yg sedang dibuka) via PATCH/DELETE /batches/{id}.
        // Lihat PLANNING_V3_IMPORT_FIX_AND_CROSSDAY_PLAN.md §10.
        isContinuation: !!b.is_continuation,
        sourcePlanId: b.source_plan_id ?? null,
        sourcePlanVersion: b.source_plan_version ?? null,
        sourceStartOffsetMinutes: b.source_start_offset_minutes ?? null,
        sourceBlocks: (b.source_blocks || []).map((bl) => ({
          phase: bl.phase,
          durationMinutes: bl.duration_minutes,
        })),
      }));
    });
  });
  return {
    id: apiPlan.id,
    version: apiPlan.version,
    shiftDate: apiPlan.shift_date,
    name: apiPlan.name || '',
    notes: apiPlan.notes || '',
    status: apiPlan.status,
    batchesByMachine,
    isDirty: false,
  };
}

export function planToPayload(plan, machinesByCode = {}) {
  const batches = [];
  Object.entries(plan.batchesByMachine || {}).forEach(([machineCode, list]) => {
    const mode = machinesByCode[machineCode]?.operation_mode || 'AUTO';
    (list || []).forEach((b) => {
      // Batch "lanjutan" milik plan HARI SEBELUMNYA — jangan ikut tersimpan/terduplikasi di
      // plan ini. Editnya lewat PATCH/DELETE /batches/{id} tersendiri (lihat §10).
      if (b.isContinuation) return;
      batches.push({
        machine_code: machineCode,
        label: b.label || '',
        start_offset_minutes: b.startOffsetMinutes,
        client_id: b.clientId,
        program_id: mode === 'AUTO' ? (b.programId ?? null) : null,
        blocks: (b.blocks || []).map((bl) => ({
          phase: bl.phase,
          duration_minutes: bl.durationMinutes,
        })),
      });
    });
  });
  return {
    version: plan.version,
    name: plan.name,
    notes: plan.notes,
    batches,
  };
}

/**
 * Detect batches whose structure doesn't match current machine.operation_mode.
 * Returns [{ machineCode, machineName, fromMode, toMode, batch }]
 */
export function detectModeMismatches(batchesByMachine, machinesByCode) {
  const issues = [];
  Object.entries(batchesByMachine || {}).forEach(([code, list]) => {
    const machine = machinesByCode?.[code];
    if (!machine) return;
    const mode = machine.operation_mode || 'AUTO';
    (list || []).forEach((batch) => {
      if (batch.isContinuation) return; // milik plan lain, jangan blokir save/publish plan ini
      const phases = (batch.blocks || []).map((b) => b.phase);
      const looksAuto = phases.length === 3
        && phases[0] === 'HEAT' && phases[1] === 'STEADY' && phases[2] === 'COOL';
      const looksManual = phases.length === 1 && phases[0] === 'RUNNING';
      if (mode === 'MANUAL' && looksAuto) {
        issues.push({
          machineCode: code,
          machineName: machine.name || code,
          fromMode: 'AUTO',
          toMode: 'MANUAL',
          batch,
        });
      } else if (mode === 'AUTO' && looksManual) {
        issues.push({
          machineCode: code,
          machineName: machine.name || code,
          fromMode: 'MANUAL',
          toMode: 'AUTO',
          batch,
        });
      }
    });
  });
  return issues;
}
