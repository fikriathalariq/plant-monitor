import React, {
  useCallback, useEffect, useMemo, useReducer, useRef, useState,
} from 'react';
import {
  ChevronLeft, ChevronRight, Save, Upload, Copy, Plus,
  Printer, RefreshCw, CalendarClock,
} from 'lucide-react';
import { TimeAxis, TimeGrid, SHIFT_MINUTES } from '../components/TimeGridAxis';
import { SteamHeatmap, STEAM_HEAT_LEGEND } from '../components/SteamHeatmap';
import PlanningBatchEditModal from '../components/planning/PlanningBatchEditModal';
import { PHASE_COLORS } from '../lib/phaseColors';
import {
  useGetPlanningMetaQuery,
  useListPlansQuery,
  useCreatePlanMutation,
  useUpdatePlanMutation,
  usePublishPlanMutation,
  useDuplicatePlanMutation,
  useLazyGetPlanQuery,
  usePatchBatchMutation,
  useDeleteBatchMutation,
} from '../store/planningApi';
import {
  GRID_MINUTES,
  batchTotalDuration,
  clamp,
  computeSteamTimeline,
  createRunningBlock,
  detectModeMismatches,
  hasOverlap,
  minutesToPct,
  newClientId,
  offsetToClockLabel,
  pctToMinutes,
  planFromApi,
  planToPayload,
  snapToGrid,
  splitDefaultPhases,
} from '../lib/planningGeometry';

const STICKY_GROUP_TOP = 'top-14';
const PLANNING_PHASE_LABEL = {
  HEAT: 'Heat',
  STEADY: 'Hold',
  COOL: 'Cool',
  RUNNING: 'ON',
};

function PlanningPrintLegend() {
  return (
    <div className="snapshot-print-legend hidden print:flex flex-wrap items-center gap-x-2.5 gap-y-0.5 mt-1">
      {['HEAT', 'STEADY', 'COOL', 'RUNNING'].map((key) => (
        <span key={key} className="flex items-center gap-1 text-[8px] text-gray-600">
          <span className={`inline-block w-2.5 h-1.5 ${(PHASE_COLORS[key] || {}).bg}`} />
          {PLANNING_PHASE_LABEL[key]}
        </span>
      ))}
      <span className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-[8px] text-gray-600">
        <span className="text-gray-500 font-medium">Uap:</span>
        {STEAM_HEAT_LEGEND.map((item) => (
          <span key={item.label} className="flex items-center gap-0.5">
            <span
              className={`inline-block w-2.5 h-1.5 ${item.border ? 'border border-gray-300' : ''}`}
              style={{ backgroundColor: item.color }}
            />
            {item.label}
          </span>
        ))}
      </span>
    </div>
  );
}

function toISODate(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function getCurrentShiftDateISO() {
  const now = new Date();
  const d = new Date(now);
  if (now.getHours() < 6) d.setDate(d.getDate() - 1);
  return toISODate(d);
}

function addDaysISO(iso, delta) {
  const d = new Date(`${iso}T12:00:00`);
  d.setDate(d.getDate() + delta);
  return toISODate(d);
}

function emptyPlan(shiftDate) {
  return {
    id: null,
    version: 1,
    shiftDate,
    name: '',
    notes: '',
    status: 'DRAFT',
    batchesByMachine: {},
    isDirty: false,
  };
}

function planReducer(state, action) {
  switch (action.type) {
    case 'LOAD':
      return { ...action.plan, isDirty: false };
    case 'RESET_EMPTY':
      return emptyPlan(action.shiftDate);
    case 'SET_META':
      return { ...state, name: action.name ?? state.name, notes: action.notes ?? state.notes, isDirty: true };
    case 'ADD_BATCH': {
      const { machineCode, batch } = action;
      const list = [...(state.batchesByMachine[machineCode] || []), batch];
      list.sort((a, b) => a.startOffsetMinutes - b.startOffsetMinutes);
      return {
        ...state,
        isDirty: true,
        batchesByMachine: { ...state.batchesByMachine, [machineCode]: list },
      };
    }
    case 'REMOVE_BATCH': {
      const { machineCode, clientId } = action;
      const list = (state.batchesByMachine[machineCode] || []).filter((b) => b.clientId !== clientId);
      return {
        ...state,
        isDirty: true,
        batchesByMachine: { ...state.batchesByMachine, [machineCode]: list },
      };
    }
    case 'UPDATE_BATCH': {
      const { machineCode, batch } = action;
      const list = (state.batchesByMachine[machineCode] || []).map((b) => (
        b.clientId === batch.clientId ? batch : b
      ));
      list.sort((a, b) => a.startOffsetMinutes - b.startOffsetMinutes);
      return {
        ...state,
        isDirty: true,
        batchesByMachine: { ...state.batchesByMachine, [machineCode]: list },
      };
    }
    case 'MOVE_BATCH': {
      const { machineCode, clientId, startOffsetMinutes } = action;
      const list = (state.batchesByMachine[machineCode] || []).map((b) => (
        b.clientId === clientId ? { ...b, startOffsetMinutes } : b
      ));
      list.sort((a, b) => a.startOffsetMinutes - b.startOffsetMinutes);
      return {
        ...state,
        isDirty: true,
        batchesByMachine: { ...state.batchesByMachine, [machineCode]: list },
      };
    }
    case 'RESIZE_PHASE_BOUNDARY': {
      const { machineCode, clientId, leftIndex, leftDur, rightDur } = action;
      const list = (state.batchesByMachine[machineCode] || []).map((b) => {
        if (b.clientId !== clientId) return b;
        const blocks = b.blocks.map((bl, i) => {
          if (i === leftIndex) return { ...bl, durationMinutes: leftDur };
          if (i === leftIndex + 1) return { ...bl, durationMinutes: rightDur };
          return bl;
        });
        return { ...b, blocks };
      });
      return {
        ...state,
        isDirty: true,
        batchesByMachine: { ...state.batchesByMachine, [machineCode]: list },
      };
    }
    case 'RESIZE_BATCH_END': {
      const { machineCode, clientId, endPhase, duration } = action;
      const list = (state.batchesByMachine[machineCode] || []).map((b) => {
        if (b.clientId !== clientId) return b;
        const blocks = b.blocks.map((bl) => (
          bl.phase === endPhase ? { ...bl, durationMinutes: duration } : bl
        ));
        return { ...b, blocks };
      });
      return {
        ...state,
        isDirty: true,
        batchesByMachine: { ...state.batchesByMachine, [machineCode]: list },
      };
    }
    case 'CONVERT_TO_MANUAL': {
      const { machineCode, clientId } = action;
      const list = (state.batchesByMachine[machineCode] || []).map((b) => {
        if (b.clientId !== clientId) return b;
        const total = batchTotalDuration(b);
        return {
          ...b,
          programId: null,
          programName: '',
          blocks: createRunningBlock(Math.max(GRID_MINUTES, total)),
        };
      });
      return {
        ...state,
        isDirty: true,
        batchesByMachine: { ...state.batchesByMachine, [machineCode]: list },
      };
    }
    case 'CONVERT_TO_AUTO': {
      const { machineCode, clientId } = action;
      const list = (state.batchesByMachine[machineCode] || []).map((b) => {
        if (b.clientId !== clientId) return b;
        const total = batchTotalDuration(b);
        return {
          ...b,
          blocks: splitDefaultPhases(Math.max(GRID_MINUTES * 4, total)),
        };
      });
      return {
        ...state,
        isDirty: true,
        batchesByMachine: { ...state.batchesByMachine, [machineCode]: list },
      };
    }
    default:
      return state;
  }
}

function PlanningBatchBlock({
  batch,
  machineCode,
  operationMode = 'AUTO',
  isConflict,
  onMouseDownMove,
  onMouseDownBoundary,
  onMouseDownEnd,
  onRemove,
  onDoubleClick,
}) {
  const total = batchTotalDuration(batch);
  if (total <= 0) return null;
  const left = minutesToPct(batch.startOffsetMinutes);
  const width = minutesToPct(total);
  const isManual = operationMode === 'MANUAL';
  const isContinuation = !!batch.isContinuation;
  const endOffset = batch.startOffsetMinutes + total;
  const isOverflow = endOffset > SHIFT_MINUTES;
  const overflowMinutes = isOverflow ? endOffset - SHIFT_MINUTES : 0;

  const baseTitle = batch.label || (isManual ? 'Running' : 'Proses');
  const title = isContinuation
    ? `${baseTitle} · lanjutan dari plan hari sebelumnya (${total}m tersisa) · drag/hapus/edit langsung disimpan ke plan sumber`
    : (isOverflow
      ? `${baseTitle} · total ${total}m · berlanjut ${overflowMinutes}m ke shift hari berikutnya (selesai ${offsetToClockLabel(endOffset % SHIFT_MINUTES)} besok)`
      : baseTitle);

  return (
    <div
      data-batch-block
      className={`absolute top-0.5 bottom-0.5 z-10 flex overflow-hidden rounded-sm shadow-sm border ${
        isConflict ? 'border-red-500 ring-2 ring-red-400/60' : 'border-black/10'
      } ${isContinuation ? 'opacity-60 [background-image:repeating-linear-gradient(45deg,rgba(255,255,255,0.25)_0px,rgba(255,255,255,0.25)_3px,transparent_3px,transparent_6px)]' : ''}`}
      style={{ left: `${left}%`, width: `${width}%` }}
      title={title}
      onDoubleClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        onDoubleClick?.(machineCode, batch);
      }}
    >
      {isContinuation && (
        <span
          className="absolute left-0 top-0 bottom-0 w-2.5 flex items-center justify-center bg-black/35 z-20 pointer-events-none"
          aria-hidden
        >
          <span className="text-white text-[8px] leading-none">◀</span>
        </span>
      )}
      {batch.blocks.map((block, i) => {
        if (block.durationMinutes <= 0) return null;
        const wPct = (block.durationMinutes / total) * 100;
        const color = PHASE_COLORS[block.phase] || PHASE_COLORS.OFF;
        return (
          <div
            key={`${block.phase}-${i}`}
            className={`relative h-full ${color.bg} flex-shrink-0`}
            style={{ width: `${wPct}%` }}
            onMouseDown={(e) => onMouseDownMove(e, machineCode, batch)}
          >
            {!isManual && !isContinuation && i > 0 && (
              <div
                className="absolute left-0 top-0 bottom-0 w-1.5 -ml-0.5 cursor-ew-resize z-20 hover:bg-white/50 print:hidden"
                onMouseDown={(e) => {
                  e.stopPropagation();
                  onMouseDownBoundary(e, machineCode, batch, i - 1);
                }}
                title="Resize batas fase"
              />
            )}
            {(block.phase === 'COOL' || block.phase === 'RUNNING') && (
              <div
                className="absolute right-0 top-0 bottom-0 w-1.5 cursor-ew-resize z-20 hover:bg-white/50 print:hidden"
                onMouseDown={(e) => {
                  e.stopPropagation();
                  onMouseDownEnd(e, machineCode, batch, block.phase);
                }}
                title="Perpanjang/perpendek"
              />
            )}
            {wPct > 8 && (
              <span className="pointer-events-none absolute inset-0 flex items-center justify-center text-[8px] font-semibold text-white/90 drop-shadow">
                {PLANNING_PHASE_LABEL[block.phase] || block.phase}
              </span>
            )}
          </div>
        );
      })}
      <button
        type="button"
        className="absolute -top-1 -right-1 z-30 w-4 h-4 rounded-full bg-slate-800 text-white text-[10px] leading-none hover:bg-red-600 print:hidden opacity-70 hover:opacity-100"
        onClick={(e) => {
          e.stopPropagation();
          onRemove(machineCode, batch.clientId);
        }}
        onMouseDown={(e) => e.stopPropagation()}
        title={isContinuation ? 'Hapus proses (di plan sumber)' : 'Hapus proses'}
      >
        ×
      </button>
    </div>
  );
}

function MachineRow({
  machine,
  batches,
  dragConflictId,
  onTrackMouseDown,
  onMouseDownMove,
  onMouseDownBoundary,
  onMouseDownEnd,
  onRemove,
  onDoubleClick,
}) {
  const mode = machine.operation_mode || 'AUTO';
  // Batch yang overflow (start + total > SHIFT_MINUTES) di-clip visual oleh `overflow-hidden`
  // pada <td data-chart-track>. Indikator ▶ HARUS jadi sibling di sini (anchor ke track, 100%
  // = akhir hari), BUKAN nested di dalam div batch (yang lebarnya bisa >100% saat overflow,
  // sehingga elemen di dalamnya ikut ter-clip dan tidak pernah kelihatan).
  const hasOverflowingBatch = (batches || []).some(
    (b) => b.startOffsetMinutes + batchTotalDuration(b) > SHIFT_MINUTES,
  );
  return (
    <tr className="snapshot-machine-row group">
      <td
        className="sticky left-0 z-10 min-w-0 px-2 py-2 print:py-0 print:leading-none border-r border-b border-gray-100 align-middle bg-white print:static"
        title={`${machine.name} (${machine.code}) · ${mode}`}
      >
        <span className="text-[10px] sm:text-xs text-gray-700 font-medium leading-tight line-clamp-2 print:line-clamp-none">
          {machine.name}
        </span>
        <span className="block text-[8px] text-gray-400 uppercase tracking-wide print:hidden">
          {mode}
          {(machine.average_steam_usage || 0) <= 0 ? ' · tanpa data uap' : ''}
        </span>
      </td>
      <td
        data-chart-track
        className="relative h-7 sm:h-6 print:h-4 p-0 w-full min-w-0 bg-slate-100 border-b border-gray-100 cursor-crosshair select-none overflow-hidden"
        onMouseDown={(e) => onTrackMouseDown(e, machine.code, mode)}
      >
        <TimeGrid progressPct={100} overlay showNow={false} />
        {(batches || []).map((batch) => (
          <PlanningBatchBlock
            key={batch.clientId}
            batch={batch}
            machineCode={machine.code}
            operationMode={mode}
            isConflict={dragConflictId === batch.clientId}
            onMouseDownMove={onMouseDownMove}
            onMouseDownBoundary={onMouseDownBoundary}
            onMouseDownEnd={onMouseDownEnd}
            onRemove={onRemove}
            onDoubleClick={onDoubleClick}
          />
        ))}
        {hasOverflowingBatch && (
          <div
            className="absolute right-0 top-0 bottom-0 w-3 flex items-center justify-center bg-black/35 z-30 pointer-events-none"
            aria-hidden
          >
            <span className="text-white text-[9px] leading-none">▶</span>
          </div>
        )}
      </td>
    </tr>
  );
}

const ProductionPlanning = () => {
  const [selectedDate, setSelectedDate] = useState(getCurrentShiftDateISO);
  const [plan, dispatch] = useReducer(planReducer, null, () => emptyPlan(getCurrentShiftDateISO()));
  const [saveError, setSaveError] = useState(null);
  const [dragConflictId, setDragConflictId] = useState(null);
  const [statusMsg, setStatusMsg] = useState('');
  const [editTarget, setEditTarget] = useState(null); // { machineCode, batch }
  const [modeIssues, setModeIssues] = useState([]);
  const dragRef = useRef(null);

  const { data: meta } = useGetPlanningMetaQuery();
  const { data: planList, refetch: refetchList } = useListPlansQuery(selectedDate);
  const [fetchPlan] = useLazyGetPlanQuery();
  const [createPlan, { isLoading: creating }] = useCreatePlanMutation();
  const [updatePlan, { isLoading: saving }] = useUpdatePlanMutation();
  const [publishPlan, { isLoading: publishing }] = usePublishPlanMutation();
  const [duplicatePlan, { isLoading: duplicating }] = useDuplicatePlanMutation();
  const [patchBatch] = usePatchBatchMutation();
  const [deleteBatch] = useDeleteBatchMutation();

  const machinesByCode = useMemo(() => {
    const map = {};
    (meta?.machines || []).forEach((m) => { map[m.code] = m; });
    return map;
  }, [meta]);

  const programs = meta?.programs || [];

  const displayGroups = useMemo(() => {
    if (!meta?.machines) return [];
    const groupNameByCode = {};
    meta.groups?.forEach((g) => { groupNameByCode[g.code] = g.name; });
    const map = {};
    meta.machines.forEach((m) => {
      const gcode = m.group || 'Lain-lain';
      const gname = groupNameByCode[gcode] || gcode;
      if (!map[gname]) map[gname] = [];
      map[gname].push(m);
    });
    return Object.entries(map)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([group_name, machines]) => ({ group_name, machines }));
  }, [meta]);

  const steamPreview = useMemo(
    () => computeSteamTimeline(plan.batchesByMachine, machinesByCode),
    [plan.batchesByMachine, machinesByCode],
  );

  const peakInfo = useMemo(() => {
    const vals = steamPreview.values || [];
    let max = 0;
    let idx = 0;
    vals.forEach((v, i) => {
      if (v > max) { max = v; idx = i; }
    });
    const h = Math.floor(idx / 60);
    const m = idx % 60;
    const clockH = (6 + h) % 24;
    return {
      max,
      timeLabel: `${String(clockH).padStart(2, '0')}:${String(m).padStart(2, '0')}`,
    };
  }, [steamPreview]);

  const refreshModeIssues = useCallback((batchesByMachine) => {
    if (!meta?.machines) {
      setModeIssues([]);
      return;
    }
    setModeIssues(detectModeMismatches(batchesByMachine, machinesByCode));
  }, [meta, machinesByCode]);

  // Batch "lanjutan" (continuation) ditulis langsung ke plan SUMBER (hari sebelumnya) via
  // PATCH/DELETE cross-plan, lalu plan yg sedang dibuka di-refetch agar tampilan continuation
  // ikut ter-update. Lihat PLANNING_V3_IMPORT_FIX_AND_CROSSDAY_PLAN.md §10.
  const refreshCurrentPlan = useCallback(async () => {
    if (!plan.id) return;
    try {
      const detail = await fetchPlan(plan.id).unwrap();
      const loaded = planFromApi(detail);
      dispatch({ type: 'LOAD', plan: loaded });
      refreshModeIssues(loaded.batchesByMachine);
    } catch (e) {
      // Biarkan, refresh manual berikutnya (tombol reload) akan mencoba lagi.
    }
  }, [plan.id, fetchPlan, refreshModeIssues]);

  const loadPlanForDate = useCallback(async (dateIso) => {
    setSaveError(null);
    const listRes = await refetchList();
    const results = listRes?.data?.results || planList?.results || [];
    const forDate = results.filter((p) => p.shift_date === dateIso);
    if (forDate.length === 0) {
      dispatch({ type: 'RESET_EMPTY', shiftDate: dateIso });
      setModeIssues([]);
      return;
    }
    const preferred = forDate.find((p) => p.status === 'PUBLISHED') || forDate[0];
    try {
      const detail = await fetchPlan(preferred.id).unwrap();
      const loaded = planFromApi(detail);
      dispatch({ type: 'LOAD', plan: loaded });
      refreshModeIssues(loaded.batchesByMachine);
    } catch (e) {
      dispatch({ type: 'RESET_EMPTY', shiftDate: dateIso });
      setSaveError('Gagal memuat rencana.');
      setModeIssues([]);
    }
  }, [fetchPlan, refetchList, planList, refreshModeIssues]);

  useEffect(() => {
    loadPlanForDate(selectedDate);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedDate]);

  useEffect(() => {
    if (!plan.isDirty) return undefined;
    const handler = (e) => {
      e.preventDefault();
      e.returnValue = '';
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [plan.isDirty]);

  const pctFromTrack = (e, trackEl) => {
    const rect = trackEl.getBoundingClientRect();
    return clamp(((e.clientX - rect.left) / rect.width) * 100, 0, 100);
  };

  const openEditModal = useCallback((machineCode, batch) => {
    dragRef.current = null;
    setDragConflictId(null);
    setEditTarget({ machineCode, batch });
  }, []);

  const onTrackMouseDown = useCallback((e, machineCode, mode) => {
    if (e.button !== 0) return;
    if (e.target.closest('[data-batch-block]')) return;
    if (e.target.closest('button')) return;
    e.preventDefault();
    const trackEl = e.currentTarget;
    const startPct = pctFromTrack(e, trackEl);
    dragRef.current = {
      mode: 'create',
      machineCode,
      operationMode: mode || 'AUTO',
      trackEl,
      startPct,
      currentPct: startPct,
    };
  }, []);

  const onMouseDownMove = useCallback((e, machineCode, batch) => {
    if (e.button !== 0) return;
    e.preventDefault();
    e.stopPropagation();
    const trackEl = e.currentTarget.closest('[data-chart-track]');
    if (!trackEl) return;
    const startPct = pctFromTrack(e, trackEl);
    const originOffset = batch.startOffsetMinutes;
    dragRef.current = {
      mode: 'move',
      machineCode,
      clientId: batch.clientId,
      trackEl,
      originOffset,
      grabDeltaMin: pctToMinutes(startPct) - originOffset,
      duration: batchTotalDuration(batch),
      isContinuation: !!batch.isContinuation,
      sourceBatchId: batch.id,
      sourcePlanVersion: batch.sourcePlanVersion,
      sourceStartOffsetMinutes: batch.sourceStartOffsetMinutes,
      sourceBlocks: batch.sourceBlocks,
      sourceLabel: batch.label,
      sourceProgramId: batch.programId,
    };
  }, []);

  const onMouseDownBoundary = useCallback((e, machineCode, batch, leftIndex) => {
    if (e.button !== 0) return;
    e.preventDefault();
    e.stopPropagation();
    const trackEl = e.currentTarget.closest('[data-chart-track]');
    dragRef.current = {
      mode: 'resize-boundary',
      machineCode,
      clientId: batch.clientId,
      trackEl,
      leftIndex,
      leftDur0: batch.blocks[leftIndex].durationMinutes,
      rightDur0: batch.blocks[leftIndex + 1].durationMinutes,
      boundaryAbsMin: batch.startOffsetMinutes
        + batch.blocks.slice(0, leftIndex + 1).reduce((s, b) => s + b.durationMinutes, 0),
    };
  }, []);

  const onMouseDownEnd = useCallback((e, machineCode, batch, endPhase) => {
    if (e.button !== 0) return;
    e.preventDefault();
    e.stopPropagation();
    const trackEl = e.currentTarget.closest('[data-chart-track]');
    const endBlock = batch.blocks.find((b) => b.phase === endPhase);
    const other = batchTotalDuration(batch) - (endBlock?.durationMinutes || 0);
    dragRef.current = {
      mode: 'resize-end',
      machineCode,
      clientId: batch.clientId,
      trackEl,
      batchStart: batch.startOffsetMinutes,
      otherDuration: other,
      endPhase,
      end0: endBlock?.durationMinutes || 0,
      isContinuation: !!batch.isContinuation,
      sourceBatchId: batch.id,
      sourcePlanVersion: batch.sourcePlanVersion,
      sourceStartOffsetMinutes: batch.sourceStartOffsetMinutes,
      sourceBlocks: batch.sourceBlocks,
      sourceLabel: batch.label,
      sourceProgramId: batch.programId,
    };
  }, []);

  const commitContinuationMove = useCallback(async (drag) => {
    const deltaMinutes = drag.previewOffset - drag.originOffset;
    if (!deltaMinutes) return;
    const newStart = clamp((drag.sourceStartOffsetMinutes || 0) + deltaMinutes, 0, SHIFT_MINUTES - 1);
    try {
      await patchBatch({
        id: drag.sourceBatchId,
        version: drag.sourcePlanVersion,
        label: drag.sourceLabel || '',
        start_offset_minutes: newStart,
        program_id: drag.sourceProgramId ?? null,
        blocks: (drag.sourceBlocks || []).map((b) => ({
          phase: b.phase,
          duration_minutes: b.durationMinutes,
        })),
      }).unwrap();
      setStatusMsg('Proses lanjutan dipindah (disimpan ke plan sumber).');
      setTimeout(() => setStatusMsg(''), 2500);
    } catch (err) {
      setSaveError(err?.data?.detail || 'Gagal memindahkan proses lanjutan — perubahan dibatalkan.');
    } finally {
      await refreshCurrentPlan();
    }
  }, [patchBatch, refreshCurrentPlan]);

  const commitContinuationResizeEnd = useCallback(async (drag) => {
    const deltaMinutes = drag.previewDuration - (drag.end0 || 0);
    if (!deltaMinutes) return;
    const srcBlocks = drag.sourceBlocks || [];
    const blocks = srcBlocks.map((b, i) => ({
      phase: b.phase,
      duration_minutes: i === srcBlocks.length - 1
        ? Math.max(0, (b.durationMinutes || 0) + deltaMinutes)
        : b.durationMinutes,
    }));
    try {
      await patchBatch({
        id: drag.sourceBatchId,
        version: drag.sourcePlanVersion,
        label: drag.sourceLabel || '',
        start_offset_minutes: drag.sourceStartOffsetMinutes || 0,
        program_id: drag.sourceProgramId ?? null,
        blocks,
      }).unwrap();
      setStatusMsg('Durasi proses lanjutan diperbarui (disimpan ke plan sumber).');
      setTimeout(() => setStatusMsg(''), 2500);
    } catch (err) {
      setSaveError(err?.data?.detail || 'Gagal mengubah durasi proses lanjutan — perubahan dibatalkan.');
    } finally {
      await refreshCurrentPlan();
    }
  }, [patchBatch, refreshCurrentPlan]);

  const commitContinuationMoveRef = useRef(commitContinuationMove);
  const commitContinuationResizeEndRef = useRef(commitContinuationResizeEnd);
  useEffect(() => {
    commitContinuationMoveRef.current = commitContinuationMove;
    commitContinuationResizeEndRef.current = commitContinuationResizeEnd;
  }, [commitContinuationMove, commitContinuationResizeEnd]);

  useEffect(() => {
    const onMove = (e) => {
      const drag = dragRef.current;
      if (!drag?.trackEl) return;
      const pct = pctFromTrack(e, drag.trackEl);
      const minutes = pctToMinutes(pct);

      if (drag.mode === 'create') {
        drag.currentPct = pct;
        setDragConflictId(null);
        return;
      }

      if (drag.mode === 'move') {
        // Titik mulai batch tetap dibatasi 0-1439 (sesuai model start_offset_minutes), tapi
        // batch boleh meluber ke shift hari berikutnya (start + duration > SHIFT_MINUTES) --
        // hanya durasi total per batch yang dibatasi 24 jam (guard anomali, lihat handleSave).
        let next = snapToGrid(minutes - drag.grabDeltaMin);
        next = clamp(next, 0, SHIFT_MINUTES - 1);
        const list = plan.batchesByMachine[drag.machineCode] || [];
        const conflict = hasOverlap(list, drag.clientId, next, drag.duration);
        setDragConflictId(conflict ? drag.clientId : null);
        drag.previewOffset = next;
        drag.conflict = conflict;
        dispatch({
          type: 'MOVE_BATCH',
          machineCode: drag.machineCode,
          clientId: drag.clientId,
          startOffsetMinutes: next,
        });
        return;
      }

      if (drag.mode === 'resize-boundary') {
        const boundary = snapToGrid(minutes);
        const leftStart = drag.boundaryAbsMin - drag.leftDur0;
        const leftDur = clamp(boundary - leftStart, GRID_MINUTES, drag.leftDur0 + drag.rightDur0 - GRID_MINUTES);
        const rightDur = drag.leftDur0 + drag.rightDur0 - leftDur;
        dispatch({
          type: 'RESIZE_PHASE_BOUNDARY',
          machineCode: drag.machineCode,
          clientId: drag.clientId,
          leftIndex: drag.leftIndex,
          leftDur,
          rightDur,
        });
        return;
      }

      if (drag.mode === 'resize-end') {
        const end = snapToGrid(minutes);
        const duration = clamp(
          end - drag.batchStart - drag.otherDuration,
          GRID_MINUTES,
          SHIFT_MINUTES - drag.batchStart - drag.otherDuration,
        );
        drag.previewDuration = duration;
        dispatch({
          type: 'RESIZE_BATCH_END',
          machineCode: drag.machineCode,
          clientId: drag.clientId,
          endPhase: drag.endPhase,
          duration,
        });
      }
    };

    const onUp = () => {
      const drag = dragRef.current;
      if (!drag) return;

      if (drag.mode === 'create') {
        const lo = Math.min(drag.startPct, drag.currentPct);
        const hi = Math.max(drag.startPct, drag.currentPct);
        let start = snapToGrid(pctToMinutes(lo));
        let end = snapToGrid(pctToMinutes(hi));
        if (end - start < GRID_MINUTES * 2) {
          end = start + GRID_MINUTES * 4;
        }
        end = Math.min(end, SHIFT_MINUTES);
        const duration = end - start;
        const isManual = drag.operationMode === 'MANUAL';
        const blocks = isManual ? createRunningBlock(duration) : splitDefaultPhases(duration);
        const list = plan.batchesByMachine[drag.machineCode] || [];
        if (!hasOverlap(list, null, start, duration)) {
          dispatch({
            type: 'ADD_BATCH',
            machineCode: drag.machineCode,
            batch: {
              clientId: newClientId(),
              label: '',
              startOffsetMinutes: start,
              programId: null,
              programName: '',
              blocks,
            },
          });
        } else {
          setStatusMsg('Area bentrok dengan proses lain.');
          setTimeout(() => setStatusMsg(''), 2500);
        }
      }

      if (drag.mode === 'move' && drag.conflict) {
        dispatch({
          type: 'MOVE_BATCH',
          machineCode: drag.machineCode,
          clientId: drag.clientId,
          startOffsetMinutes: drag.originOffset,
        });
        setStatusMsg('Tidak bisa overlap — posisi dikembalikan.');
        setTimeout(() => setStatusMsg(''), 2500);
      } else if (drag.mode === 'move' && drag.isContinuation && drag.previewOffset != null) {
        commitContinuationMoveRef.current?.(drag);
      }

      if (drag.mode === 'resize-end' && drag.isContinuation && drag.previewDuration != null) {
        commitContinuationResizeEndRef.current?.(drag);
      }

      dragRef.current = null;
      setDragConflictId(null);
    };

    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
    return () => {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
    };
  }, [plan.batchesByMachine]);

  const handleRemove = async (machineCode, clientId) => {
    const target = (plan.batchesByMachine[machineCode] || []).find((b) => b.clientId === clientId);
    if (target?.isContinuation) {
      try {
        await deleteBatch({ id: target.id, version: target.sourcePlanVersion }).unwrap();
        setEditTarget(null);
        setStatusMsg('Proses lanjutan dihapus (dari plan sumber).');
        setTimeout(() => setStatusMsg(''), 2000);
      } catch (err) {
        setSaveError(err?.data?.detail || 'Gagal menghapus proses lanjutan.');
      } finally {
        await refreshCurrentPlan();
      }
      return;
    }
    dispatch({ type: 'REMOVE_BATCH', machineCode, clientId });
    setEditTarget(null);
    setStatusMsg('Proses dihapus.');
    setTimeout(() => setStatusMsg(''), 2000);
  };

  const handleSave = async () => {
    if (modeIssues.length > 0) {
      setSaveError('Selesaikan dulu konflik mode mesin (AUTO↔MANUAL) sebelum menyimpan.');
      return;
    }
    setSaveError(null);
    try {
      if (!plan.id) {
        const created = await createPlan({
          shift_date: selectedDate,
          name: plan.name || `Rencana ${selectedDate}`,
          notes: plan.notes,
        }).unwrap();
        const payload = planToPayload(
          { ...plan, version: created.version, id: created.id },
          machinesByCode,
        );
        const saved = await updatePlan({ id: created.id, ...payload }).unwrap();
        dispatch({ type: 'LOAD', plan: planFromApi(saved) });
      } else {
        const saved = await updatePlan({
          id: plan.id,
          ...planToPayload(plan, machinesByCode),
        }).unwrap();
        dispatch({ type: 'LOAD', plan: planFromApi(saved) });
      }
      setStatusMsg('Tersimpan.');
      setTimeout(() => setStatusMsg(''), 2000);
      refetchList();
      setModeIssues([]);
    } catch (err) {
      const msg = err?.data?.detail || err?.error || 'Gagal menyimpan.';
      if (err?.status === 409) {
        setSaveError('Rencana sudah diubah pihak lain. Muat ulang halaman.');
      } else {
        setSaveError(typeof msg === 'string' ? msg : JSON.stringify(msg));
      }
    }
  };

  const handlePublish = async () => {
    try {
      let id = plan.id;
      if (!id) {
        const created = await createPlan({
          shift_date: selectedDate,
          name: plan.name || `Rencana ${selectedDate}`,
        }).unwrap();
        id = created.id;
        await updatePlan({
          id,
          ...planToPayload({ ...plan, version: created.version }, machinesByCode),
        }).unwrap();
      } else if (plan.isDirty) {
        await updatePlan({ id, ...planToPayload(plan, machinesByCode) }).unwrap();
      }
      const published = await publishPlan(id).unwrap();
      dispatch({ type: 'LOAD', plan: planFromApi(published) });
      setStatusMsg('Dipublish.');
      refetchList();
    } catch (err) {
      setSaveError(err?.data?.detail || 'Gagal publish.');
    }
  };

  const handleNew = async () => {
    if (plan.isDirty && !window.confirm('Perubahan belum disimpan. Buat rencana baru?')) return;
    try {
      const created = await createPlan({
        shift_date: selectedDate,
        name: `Rencana ${selectedDate}`,
      }).unwrap();
      dispatch({ type: 'LOAD', plan: planFromApi(created) });
      setModeIssues([]);
      refetchList();
    } catch (err) {
      setSaveError(err?.data?.detail || 'Gagal membuat rencana.');
    }
  };

  const handleDuplicate = async () => {
    if (!plan.id) {
      setStatusMsg('Simpan dulu sebelum menduplikat.');
      return;
    }
    const target = window.prompt('Duplikat ke tanggal shift (YYYY-MM-DD):', addDaysISO(selectedDate, 1));
    if (!target) return;
    try {
      const dup = await duplicatePlan({ id: plan.id, shift_date: target }).unwrap();
      setSelectedDate(target);
      dispatch({ type: 'LOAD', plan: planFromApi(dup) });
      setStatusMsg('Diduplikat.');
    } catch (err) {
      setSaveError(err?.data?.detail || 'Gagal duplikat.');
    }
  };

  const handlePrint = () => {
    const style = document.createElement('style');
    style.id = 'planning-print-page-style';
    style.textContent = '@page { size: A4 landscape; margin: 8mm; }';
    document.head.appendChild(style);
    document.documentElement.classList.add('printing-production-planning');
    document.body.classList.add('printing-production-planning');
    const cleanup = () => {
      document.documentElement.classList.remove('printing-production-planning');
      document.body.classList.remove('printing-production-planning');
      document.getElementById('planning-print-page-style')?.remove();
    };
    window.addEventListener('afterprint', cleanup, { once: true });
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        window.print();
      });
    });
  };

  const draftsForDate = (planList?.results || []).filter((p) => p.shift_date === selectedDate);

  const timeLabels = useMemo(() => (
    Array.from({ length: 25 }, (_, i) => ({
      label: String((6 + i) % 24).padStart(2, '0'),
      pct: (i / 24) * 100,
    }))
  ), []);

  const editMachine = editTarget ? machinesByCode[editTarget.machineCode] : null;

  return (
    <div className="snapshot-print-flow flex flex-col flex-1 min-h-0 h-full w-full min-w-0 print:h-auto print:overflow-visible">
      <div className="no-print shrink-0 px-3 sm:px-4 py-2.5 border-b border-gray-200 bg-white flex flex-col sm:flex-row sm:flex-wrap sm:items-center gap-2 sm:gap-3">
        <div className="flex items-center gap-1 border border-gray-200 rounded-lg bg-gray-50 px-1">
          <button type="button" onClick={() => setSelectedDate(addDaysISO(selectedDate, -1))} className="p-1.5 rounded-md hover:bg-white">
            <ChevronLeft size={18} className="text-gray-600" />
          </button>
          <input
            type="date"
            value={selectedDate}
            onChange={(e) => setSelectedDate(e.target.value)}
            className="text-xs sm:text-sm text-gray-700 font-medium px-1 py-1 bg-transparent border-0 focus:ring-0 tabular-nums"
          />
          <button type="button" onClick={() => setSelectedDate(addDaysISO(selectedDate, 1))} className="p-1.5 rounded-md hover:bg-white">
            <ChevronRight size={18} className="text-gray-600" />
          </button>
        </div>

        <span className={`text-[10px] font-semibold px-2 py-1 rounded-md border ${
          plan.status === 'PUBLISHED'
            ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
            : 'bg-amber-50 text-amber-800 border-amber-200'
        }`}
        >
          {plan.status || 'DRAFT'}
          {plan.isDirty ? ' · belum disimpan' : ''}
        </span>

        {draftsForDate.length > 1 && (
          <select
            className="text-xs border border-gray-200 rounded-lg px-2 py-1.5"
            value={plan.id || ''}
            onChange={async (e) => {
              const id = Number(e.target.value);
              if (!id) return;
              const detail = await fetchPlan(id).unwrap();
              const loaded = planFromApi(detail);
              dispatch({ type: 'LOAD', plan: loaded });
              refreshModeIssues(loaded.batchesByMachine);
            }}
          >
            {draftsForDate.map((p) => (
              <option key={p.id} value={p.id}>
                #{p.id} {p.name || p.status} v{p.version}
              </option>
            ))}
          </select>
        )}

        <input
          type="text"
          placeholder="Nama rencana"
          value={plan.name}
          onChange={(e) => dispatch({ type: 'SET_META', name: e.target.value })}
          className="text-xs sm:text-sm border border-gray-200 rounded-lg px-2 py-1.5 min-w-[10rem] max-w-xs"
        />

        <div className="flex items-center gap-1.5 sm:ml-auto">
          <button type="button" onClick={handleNew} disabled={creating} className="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs border border-gray-200 rounded-lg hover:bg-gray-50" title="Buat rencana baru">
            <Plus className="w-3.5 h-3.5" /> Baru
          </button>
          <button type="button" onClick={handleSave} disabled={saving || modeIssues.length > 0} className="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50">
            <Save className="w-3.5 h-3.5" /> Simpan
          </button>
          <button type="button" onClick={handlePublish} disabled={publishing || modeIssues.length > 0} className="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs border border-emerald-300 text-emerald-700 rounded-lg hover:bg-emerald-50">
            <Upload className="w-3.5 h-3.5" /> Publish
          </button>
          <button type="button" onClick={handleDuplicate} disabled={duplicating || !plan.id} className="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs border border-gray-200 rounded-lg hover:bg-gray-50">
            <Copy className="w-3.5 h-3.5" /> Duplikat
          </button>
          <button type="button" onClick={handlePrint} className="p-2 rounded-lg border border-gray-200 hover:bg-gray-50" title="Cetak A4 landscape">
            <Printer className="w-4 h-4 text-gray-600" />
          </button>
          <button type="button" onClick={() => loadPlanForDate(selectedDate)} className="p-2 rounded-lg border border-gray-200 hover:bg-gray-50" title="Muat ulang">
            <RefreshCw className="w-4 h-4 text-gray-500" />
          </button>
        </div>
      </div>

      {(saveError || statusMsg) && (
        <div className={`no-print px-4 py-1.5 text-xs ${saveError ? 'bg-red-50 text-red-700' : 'bg-emerald-50 text-emerald-700'}`}>
          {saveError || statusMsg}
        </div>
      )}

      {modeIssues.length > 0 && (
        <div className="no-print mx-3 mt-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900">
          <p className="font-semibold mb-1">Mode mesin berubah sejak rencana dibuat — pilih tindakan sebelum menyimpan:</p>
          <ul className="space-y-1.5">
            {modeIssues.map((issue) => (
              <li key={`${issue.machineCode}-${issue.batch.clientId}`} className="flex flex-wrap items-center gap-2">
                <span>
                  <strong>{issue.machineName}</strong>
                  {' '}
                  ({issue.fromMode} → {issue.toMode})
                </span>
                <button
                  type="button"
                  className="px-2 py-0.5 rounded border border-amber-400 bg-white hover:bg-amber-100"
                  onClick={() => {
                    dispatch({
                      type: issue.toMode === 'MANUAL' ? 'CONVERT_TO_MANUAL' : 'CONVERT_TO_AUTO',
                      machineCode: issue.machineCode,
                      clientId: issue.batch.clientId,
                    });
                    setModeIssues((prev) => prev.filter(
                      (x) => !(x.machineCode === issue.machineCode && x.batch.clientId === issue.batch.clientId),
                    ));
                  }}
                >
                  Konversi
                </button>
                <button
                  type="button"
                  className="px-2 py-0.5 rounded border border-red-300 text-red-700 bg-white hover:bg-red-50"
                  onClick={() => {
                    dispatch({
                      type: 'REMOVE_BATCH',
                      machineCode: issue.machineCode,
                      clientId: issue.batch.clientId,
                    });
                    setModeIssues((prev) => prev.filter(
                      (x) => !(x.machineCode === issue.machineCode && x.batch.clientId === issue.batch.clientId),
                    ));
                  }}
                >
                  Hapus batch
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="no-print px-3 py-1 text-[10px] text-gray-500">
        Drag area kosong = buat · drag badan = pindah · double-click = edit form · Peak uap: {peakInfo.max.toFixed(0)} kg/h @ {peakInfo.timeLabel}
      </div>

      <div className="snapshot-print-flow snapshot-print-root snapshot-print-scroll relative flex-1 min-h-0 min-w-0 overflow-auto border border-gray-200 rounded-lg m-2 sm:m-3 print:m-0 print:border-0 print:overflow-visible print:h-auto">
        <table className="snapshot-print-table w-full min-w-[68rem] print:min-w-0 border-separate border-spacing-0">
          <colgroup>
            <col className="snapshot-print-name-col w-[4.25rem] sm:w-28" />
            <col />
          </colgroup>
          <thead>
            <tr className="snapshot-print-title-row hidden print:table-row">
              <th
                colSpan={2}
                className="text-left font-normal px-2 py-1.5 bg-white border-b border-gray-300"
              >
                <p className="text-sm font-bold text-gray-900 tracking-tight">
                  Perencanaan Produksi Mesin
                </p>
                <p className="text-[10px] text-gray-600 mt-0.5 tabular-nums">
                  Shift {selectedDate}
                  {' · '}
                  {plan.name || 'Tanpa nama'}
                  {' · '}
                  Status: {plan.status || 'DRAFT'}
                  {' · '}
                  Dicetak: {new Date().toLocaleString('id-ID', { dateStyle: 'medium', timeStyle: 'short' })}
                </p>
                <PlanningPrintLegend />
              </th>
            </tr>
            <tr>
              <th
                scope="col"
                className="sticky top-0 left-0 z-30 min-w-0 px-2 py-2 bg-slate-100 border-r border-b border-gray-200 text-left font-semibold align-bottom box-border h-8 print:static"
              >
                <span className="text-[10px] text-gray-500 uppercase tracking-wide flex items-center gap-1">
                  <CalendarClock className="w-3 h-3" /> Mesin
                </span>
              </th>
              <th
                scope="col"
                className="sticky top-0 z-20 min-w-0 p-0 border-b border-gray-200 box-border font-normal print:static"
              >
                <TimeAxis timeLabels={timeLabels} progressPct={100} />
              </th>
            </tr>
            <tr className="steam-heatmap-row">
              <th
                scope="col"
                className="sticky top-8 left-0 z-30 min-w-0 px-2 bg-amber-50 border-r border-b border-gray-200 text-left font-semibold align-middle box-border h-6 print:static print:h-5"
              >
                <span className="text-[9px] text-amber-800 uppercase tracking-wide leading-tight">
                  Uap
                  <span className="block text-[8px] font-normal text-amber-700/80 normal-case">kg/h</span>
                </span>
              </th>
              <th
                scope="col"
                data-chart-cell
                className="sticky top-8 z-20 min-w-0 p-0 border-b border-gray-200 box-border font-normal print:static"
              >
                <SteamHeatmap heatmap={steamPreview} progressPct={100} />
              </th>
            </tr>
          </thead>
          <tbody>
            {!meta ? (
              <tr>
                <td colSpan={2} className="py-10 text-center text-gray-400 text-sm">Memuat mesin...</td>
              </tr>
            ) : (
              displayGroups.map((group) => (
                <React.Fragment key={group.group_name}>
                  <tr className="snapshot-group-row">
                    <th
                      colSpan={2}
                      className={`sticky ${STICKY_GROUP_TOP} left-0 z-[15] min-w-0 px-2.5 py-1 bg-gray-100/95 border-b border-gray-200 text-left font-semibold print:static`}
                    >
                      <span className="text-[10px] text-gray-500 uppercase tracking-wide truncate block">
                        {group.group_name}
                      </span>
                    </th>
                  </tr>
                  {group.machines.map((m) => (
                    <MachineRow
                      key={m.code}
                      machine={m}
                      batches={plan.batchesByMachine[m.code] || []}
                      dragConflictId={dragConflictId}
                      onTrackMouseDown={onTrackMouseDown}
                      onMouseDownMove={onMouseDownMove}
                      onMouseDownBoundary={onMouseDownBoundary}
                      onMouseDownEnd={onMouseDownEnd}
                      onRemove={handleRemove}
                      onDoubleClick={openEditModal}
                    />
                  ))}
                </React.Fragment>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="no-print shrink-0 flex flex-wrap items-center gap-x-3 gap-y-1.5 px-3 sm:px-4 py-2 border-t border-gray-100 bg-gray-50/80">
        {['HEAT', 'STEADY', 'COOL', 'RUNNING'].map((key) => (
          <span key={key} className="flex items-center gap-1.5 text-[10px] text-gray-600">
            <span className={`inline-block w-3.5 h-2.5 ${(PHASE_COLORS[key] || {}).bg}`} />
            {PLANNING_PHASE_LABEL[key]}
          </span>
        ))}
        <span className="flex flex-wrap items-center gap-x-2 text-[10px] text-gray-600 sm:ml-auto">
          <span className="text-gray-500 font-medium">Uap (kg/h):</span>
          {STEAM_HEAT_LEGEND.map((item) => (
            <span key={item.label} className="flex items-center gap-1">
              <span
                className={`inline-block w-3.5 h-2.5 ${item.border ? 'border border-gray-300' : ''}`}
                style={{ backgroundColor: item.color }}
              />
              {item.label}
            </span>
          ))}
        </span>
      </div>

      <PlanningBatchEditModal
        open={!!editTarget}
        batch={editTarget?.batch}
        machineCode={editTarget?.machineCode}
        machineName={editMachine?.name}
        operationMode={editMachine?.operation_mode || 'AUTO'}
        siblingBatches={editTarget ? (plan.batchesByMachine[editTarget.machineCode] || []) : []}
        programs={programs}
        onClose={() => setEditTarget(null)}
        onSave={async (updated) => {
          if (updated.isContinuation) {
            try {
              await patchBatch({
                id: updated.id,
                version: updated.sourcePlanVersion,
                label: updated.label || '',
                start_offset_minutes: updated.sourceStartOffsetMinutes,
                program_id: updated.programId ?? null,
                blocks: (updated.sourceBlocks || []).map((b) => ({
                  phase: b.phase,
                  duration_minutes: b.durationMinutes,
                })),
              }).unwrap();
              setEditTarget(null);
              setStatusMsg('Proses lanjutan diperbarui (disimpan ke plan sumber).');
              setTimeout(() => setStatusMsg(''), 2500);
              await refreshCurrentPlan();
            } catch (err) {
              setSaveError(
                err?.status === 409
                  ? 'Plan sumber (hari sebelumnya) sudah diubah pihak lain. Muat ulang lalu coba lagi.'
                  : (err?.data?.detail || 'Gagal menyimpan proses lanjutan.'),
              );
            }
            return;
          }
          dispatch({
            type: 'UPDATE_BATCH',
            machineCode: editTarget.machineCode,
            batch: updated,
          });
          setEditTarget(null);
          setStatusMsg('Perubahan diterapkan (belum disimpan ke server).');
          setTimeout(() => setStatusMsg(''), 2000);
        }}
        onDelete={(clientId) => {
          handleRemove(editTarget.machineCode, clientId);
        }}
      />
    </div>
  );
};

export default ProductionPlanning;
