import React, { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import {
  RefreshCw, ChevronLeft, ChevronRight, ChevronDown, Printer, Maximize2, Minimize2, X,
} from 'lucide-react';
import { useGetSnapshotMetaQuery, useGetSnapshotTimelineQuery } from '../store/snapshotsApi';
import { PHASE_COLORS } from '../lib/phaseColors';
import { TimeGrid, TimeAxis, SHIFT_MINUTES } from '../components/TimeGridAxis';
import { SteamHeatmap, STEAM_HEAT_LEGEND } from '../components/SteamHeatmap';
import { SteamPressureRow } from '../components/SteamPressureRow';
import { CrosshairPanel, computeHoverStats } from '../components/CrosshairPanel';

// time axis h-8 (32) + steam h-6 (24) + pressure h-7 (28) = 84px
const STICKY_GROUP_TOP = 'top-[84px]';
const LONG_PRESS_MS = 400;
const DRAG_MOVE_TOLERANCE = 6;
const MIN_RANGE_PCT = 0.3;

function toISODate(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

/** Tanggal awal shift (06:00) — selaras dengan _current_shift_start di backend. */
function getCurrentShiftDateISO() {
  const now = new Date();
  const d = new Date(now);
  if (now.getHours() < 6) {
    d.setDate(d.getDate() - 1);
  }
  return toISODate(d);
}

function addDaysISO(iso, delta) {
  const d = new Date(`${iso}T12:00:00`);
  d.setDate(d.getDate() + delta);
  return toISODate(d);
}

function pctToTimeLabel(pct, shiftStartIso) {
  const start = new Date(shiftStartIso);
  const minutes = Math.round((pct / 100) * SHIFT_MINUTES);
  const t = new Date(start.getTime() + minutes * 60000);
  const h = String(t.getHours()).padStart(2, '0');
  const m = String(t.getMinutes()).padStart(2, '0');
  return `${h}:${m}`;
}

function pctFromChartEvent(e) {
  const chartRect = e.currentTarget.getBoundingClientRect();
  return Math.min(100, Math.max(0, ((e.clientX - chartRect.left) / chartRect.width) * 100));
}

function formatDurationMinutes(totalMinutes) {
  const minutes = Math.max(0, Math.round(totalMinutes));
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (h > 0 && m > 0) return `${h} jam ${m} menit`;
  if (h > 0) return `${h} jam`;
  return `${m} menit`;
}

function buildRangeBand(startPct, endPct, chartEl, overlayEl) {
  const chartRect = chartEl.getBoundingClientRect();
  const overlayRect = overlayEl.getBoundingClientRect();
  const lo = Math.min(startPct, endPct);
  const hi = Math.max(startPct, endPct);
  const widthPct = hi - lo;
  const bandLeft = chartRect.left - overlayRect.left + (lo / 100) * chartRect.width;
  const bandWidth = (widthPct / 100) * chartRect.width;
  return { lo, hi, widthPct, bandLeft, bandWidth };
}

function TimelineBar({
  machine, progressPct, isHovered, onRowEnter, onChartMove, onChartLeave, onChartMouseDown,
}) {
  const rowBg = isHovered ? 'bg-sky-50/90' : 'bg-white';

  return (
    <tr className="snapshot-machine-row">
      <td
        className={`sticky left-0 z-10 min-w-0 px-2 py-2 print:py-0 print:leading-none border-r border-b border-gray-100 align-middle box-border print:static print:bg-white transition-colors ${rowBg}`}
        title={`${machine.name} (${machine.code})`}
        onMouseEnter={onRowEnter}
      >
        <span className="text-[10px] sm:text-xs text-gray-700 font-medium leading-tight line-clamp-2 print:line-clamp-none">
          {machine.name}
        </span>
      </td>
      <td
        data-chart-track
        className={`relative h-6 sm:h-5 print:h-4 p-0 w-full min-w-0 bg-slate-200/80 border-b border-gray-100 box-border cursor-crosshair transition-colors select-none ${isHovered ? 'bg-sky-100/70' : ''}`}
        onMouseEnter={onRowEnter}
        onMouseMove={onChartMove}
        onMouseLeave={onChartLeave}
        onMouseDown={onChartMouseDown}
      >
        <div className="absolute inset-0 bg-slate-200/80 z-[-1]" />
        <div className="absolute inset-0 z-0 flex min-w-0 pointer-events-none">
          {machine.segments.map((seg, i) => {
            const color = PHASE_COLORS[seg.state] || PHASE_COLORS.OFF;
            return (
              <div
                key={i}
                className={`${color.bg} h-full flex-shrink-0`}
                style={{ width: `${seg.width_pct}%` }}
              />
            );
          })}
        </div>
        {progressPct < 100 && (
          <div
            className="absolute top-0 bottom-0 right-0 z-[1] bg-slate-100/60 print:hidden pointer-events-none"
            style={{ width: `${100 - progressPct}%` }}
          />
        )}
        <TimeGrid progressPct={progressPct} overlay showNow />
      </td>
    </tr>
  );
}

function SnapshotPrintLegend({ progressPct }) {
  return (
    <div className="snapshot-print-legend hidden print:flex flex-wrap items-center gap-x-2.5 gap-y-0.5 mt-1">
      {Object.entries(PHASE_COLORS).map(([key, val]) => (
        <span key={key} className="flex items-center gap-1 text-[8px] text-gray-600">
          <span className={`inline-block w-2.5 h-1.5 ${val.bg}`} />
          {val.label}
        </span>
      ))}
      {progressPct < 100 && (
        <span className="flex items-center gap-1 text-[8px] text-gray-400">
          <span className="inline-block w-2.5 h-1.5 bg-slate-100 border border-dashed border-gray-300" />
          Belum terjadi
        </span>
      )}
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
        <span className="text-gray-500 font-medium ml-1">Prss:</span>
        <span className="flex items-center gap-0.5">
          <span className="inline-block w-2.5 h-1.5 bg-red-500" />
          &lt;3
        </span>
        <span className="flex items-center gap-0.5">
          <span className="inline-block w-2.5 h-1.5 bg-amber-500" />
          3–4.5
        </span>
        <span className="flex items-center gap-0.5">
          <span className="inline-block w-2.5 h-1.5 bg-emerald-500" />
          ≥4.5 barg
        </span>
      </span>
    </div>
  );
}

function GroupMultiSelect({ groups, selected, onChange }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    const close = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, []);

  const toggle = (code) => {
    onChange(
      selected.includes(code) ? selected.filter((c) => c !== code) : [...selected, code],
    );
  };

  const label = selected.length === 0
    ? 'Semua grup'
    : selected.length === 1
      ? groups.find((g) => g.code === selected[0])?.name || '1 grup'
      : `${selected.length} grup dipilih`;

  return (
    <div className="relative w-full sm:w-auto sm:min-w-[10rem] sm:max-w-xs" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between gap-2 px-3 py-2 text-xs sm:text-sm border border-gray-200 rounded-lg bg-white hover:border-gray-300 text-left"
      >
        <span className="truncate text-gray-700">{label}</span>
        <ChevronDown className={`w-4 h-4 text-gray-400 shrink-0 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="absolute z-50 mt-1 w-full min-w-[14rem] max-h-56 overflow-y-auto bg-white border border-gray-200 rounded-lg shadow-lg py-1">
          <button
            type="button"
            onClick={() => { onChange([]); setOpen(false); }}
            className="w-full text-left px-3 py-1.5 text-xs text-indigo-600 hover:bg-gray-50 font-medium"
          >
            Tampilkan semua grup
          </button>
          <div className="border-t border-gray-100 my-1" />
          {groups.map((g) => (
            <label
              key={g.code}
              className="flex items-center gap-2.5 px-3 py-2 hover:bg-gray-50 cursor-pointer text-sm text-gray-700"
            >
              <input
                type="checkbox"
                className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                checked={selected.includes(g.code)}
                onChange={() => toggle(g.code)}
              />
              <span className="truncate">{g.name}</span>
            </label>
          ))}
        </div>
      )}
    </div>
  );
}

const SnapshotHistoryPivot = () => {
  const [selectedGroups, setSelectedGroups] = useState([]);
  const [selectedDate, setSelectedDate] = useState(getCurrentShiftDateISO);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [hover, setHover] = useState(null);
  const [dragPreview, setDragPreview] = useState(null);
  const [rangeSelect, setRangeSelect] = useState(null);
  const panelRef = useRef(null);
  const overlayRef = useRef(null);
  const dragRef = useRef(null);

  const { data: meta } = useGetSnapshotMetaQuery();
  const {
    data: rawData, isLoading, isFetching, isError, error, refetch,
  } = useGetSnapshotTimelineQuery({
    date: selectedDate,
    groups: selectedGroups.length ? selectedGroups.join(',') : undefined,
  });

  const data = rawData?.shift_date === selectedDate ? rawData : undefined;
  const progressPct = data?.progress_pct ?? 100;
  const todayShiftDate = getCurrentShiftDateISO();
  const minDate = rawData?.min_shift_date || meta?.first_snapshot_date;
  const maxDate = rawData?.max_shift_date || todayShiftDate;
  const isToday = selectedDate === todayShiftDate;
  const isLoadingDate = isLoading || (isFetching && !data);

  const hoverStats = useMemo(
    () => (hover?.pct != null ? computeHoverStats(data, hover.pct) : null),
    [data, hover?.pct],
  );

  useEffect(() => {
    const onFs = () => setIsFullscreen(!!document.fullscreenElement);
    document.addEventListener('fullscreenchange', onFs);
    return () => document.removeEventListener('fullscreenchange', onFs);
  }, []);

  const handleGroupsChange = (codes) => {
    setSelectedGroups(codes);
  };

  const goToDate = (iso) => {
    setSelectedDate(iso ?? getCurrentShiftDateISO());
    setHover(null);
    setDragPreview(null);
    setRangeSelect(null);
    dragRef.current = null;
  };

  const finalizeRange = useCallback((startPct, endPct, machineCode, machineName, chartEl) => {
    if (!data?.shift_start || !overlayRef.current || !chartEl) return;
    const lo = Math.min(startPct, endPct);
    const hi = Math.max(startPct, endPct);
    if (hi - lo < MIN_RANGE_PCT) return;

    const band = buildRangeBand(lo, hi, chartEl, overlayRef.current);
    const startLabel = pctToTimeLabel(lo, data.shift_start);
    const endLabel = pctToTimeLabel(hi, data.shift_start);
    const durationMinutes = ((hi - lo) / 100) * SHIFT_MINUTES;

    setRangeSelect({
      startPct: lo,
      endPct: hi,
      startLabel,
      endLabel,
      durationLabel: formatDurationMinutes(durationMinutes),
      machineCode,
      machineName,
      ...band,
    });
    setDragPreview(null);
    setHover(null);
  }, [data?.shift_start]);

  const handleChartMouseDown = useCallback((e, machineCode, machineName) => {
    if (e.button !== 0 || !data?.shift_start) return;
    e.preventDefault();

    if (rangeSelect) {
      setRangeSelect(null);
      return;
    }

    const chartEl = e.currentTarget;
    const startPct = pctFromChartEvent(e);

    dragRef.current = {
      chartEl,
      startPct,
      currentPct: startPct,
      startX: e.clientX,
      startY: e.clientY,
      machineCode,
      machineName,
      active: false,
      timerId: setTimeout(() => {
        if (!dragRef.current) return;
        dragRef.current.active = true;
        const band = overlayRef.current
          ? buildRangeBand(startPct, startPct, chartEl, overlayRef.current)
          : null;
        setDragPreview({
          startPct,
          endPct: startPct,
          machineCode,
          machineName,
          ...(band || {}),
        });
        setHover(null);
      }, LONG_PRESS_MS),
    };
  }, [data?.shift_start, rangeSelect]);

  useEffect(() => {
    const onDocumentMouseMove = (e) => {
      const drag = dragRef.current;
      if (!drag) return;

      if (!drag.active) {
        const dx = Math.abs(e.clientX - drag.startX);
        const dy = Math.abs(e.clientY - drag.startY);
        if (dx > DRAG_MOVE_TOLERANCE || dy > DRAG_MOVE_TOLERANCE) {
          clearTimeout(drag.timerId);
          dragRef.current = null;
        }
        return;
      }

      const chartRect = drag.chartEl.getBoundingClientRect();
      const currentPct = Math.min(100, Math.max(0, ((e.clientX - chartRect.left) / chartRect.width) * 100));
      drag.currentPct = currentPct;

      if (overlayRef.current) {
        const band = buildRangeBand(drag.startPct, currentPct, drag.chartEl, overlayRef.current);
        setDragPreview({
          startPct: drag.startPct,
          endPct: currentPct,
          machineCode: drag.machineCode,
          machineName: drag.machineName,
          ...band,
        });
      }
    };

    const onDocumentMouseUp = () => {
      const drag = dragRef.current;
      if (!drag) return;

      clearTimeout(drag.timerId);

      if (drag.active) {
        finalizeRange(
          drag.startPct,
          drag.currentPct,
          drag.machineCode,
          drag.machineName,
          drag.chartEl,
        );
      }

      dragRef.current = null;
      setDragPreview(null);
    };

    document.addEventListener('mousemove', onDocumentMouseMove);
    document.addEventListener('mouseup', onDocumentMouseUp);
    return () => {
      document.removeEventListener('mousemove', onDocumentMouseMove);
      document.removeEventListener('mouseup', onDocumentMouseUp);
    };
  }, [finalizeRange]);

  useEffect(() => {
    if (!rangeSelect) return undefined;
    const dismiss = (e) => {
      if (e.button === 0 || e.button === 2) {
        setRangeSelect(null);
      }
    };
    document.addEventListener('mousedown', dismiss);
    return () => document.removeEventListener('mousedown', dismiss);
  }, [rangeSelect]);

  const handleChartMove = useCallback((e, machineCode, machineName) => {
    if (dragRef.current?.active || rangeSelect) return;
    if (!data?.shift_start || !overlayRef.current) return;
    const chartRect = e.currentTarget.getBoundingClientRect();
    const containerRect = overlayRef.current.getBoundingClientRect();
    const pct = Math.min(100, Math.max(0, ((e.clientX - chartRect.left) / chartRect.width) * 100));
    const lineLeft = chartRect.left - containerRect.left + (pct / 100) * chartRect.width;
    const flipX = lineLeft > containerRect.width - 180;
    const flipY = e.clientY - containerRect.top < 70;
    setHover({
      pct,
      timeLabel: pctToTimeLabel(pct, data.shift_start),
      machineCode,
      machineName,
      lineLeft,
      panelTop: e.clientY - containerRect.top,
      flipX,
      flipY,
    });
  }, [data?.shift_start, rangeSelect]);

  const handleChartLeave = useCallback(() => {
    if (dragRef.current?.active) return;
    setHover(null);
  }, []);

  const handleRowEnter = useCallback((machineCode, machineName) => {
    setHover((prev) => (
      prev?.lineLeft != null
        ? { ...prev, machineCode, machineName }
        : { machineCode, machineName }
    ));
  }, []);

  const toggleFullscreen = async () => {
    if (!panelRef.current) return;
    if (!document.fullscreenElement) {
      await panelRef.current.requestFullscreen?.();
    } else {
      await document.exitFullscreen?.();
    }
  };

  const handlePrint = () => {
    const style = document.createElement('style');
    style.id = 'snapshot-print-page-style';
    style.textContent = '@page { size: A4 landscape; margin: 8mm; }';
    document.head.appendChild(style);
    document.documentElement.classList.add('printing-snapshot');
    document.body.classList.add('printing-snapshot');
    const cleanup = () => {
      document.documentElement.classList.remove('printing-snapshot');
      document.body.classList.remove('printing-snapshot');
      document.getElementById('snapshot-print-page-style')?.remove();
    };
    window.addEventListener('afterprint', cleanup, { once: true });
    
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        window.print();
      });
    });
  };

  const dateSubtitle = data?.is_current_shift
    ? '06:00 → sekarang'
    : data?.shift_label?.split('–')[1]?.trim() || '';

  return (
    <div className="snapshot-print-flow flex flex-col flex-1 min-h-0 h-full w-full min-w-0 print:h-auto print:overflow-visible">
      <div className="no-print shrink-0 px-3 sm:px-4 py-2.5 border-b border-gray-200 bg-white flex flex-col sm:flex-row sm:flex-wrap sm:items-center gap-2 sm:gap-3">
        <div className="flex items-center gap-2 w-full sm:w-auto">
          <GroupMultiSelect
            groups={meta?.groups || []}
            selected={selectedGroups}
            onChange={handleGroupsChange}
          />

          <div className="flex items-center gap-1 ml-auto sm:hidden">
            <button type="button" onClick={handlePrint} className="p-2 rounded-lg border border-gray-200 hover:bg-gray-50 text-gray-600" title="Cetak A4 landscape">
              <Printer className="w-4 h-4" />
            </button>
            <button type="button" onClick={toggleFullscreen} className="p-2 rounded-lg border border-gray-200 hover:bg-gray-50 text-gray-600" title={isFullscreen ? 'Keluar layar penuh' : 'Layar penuh'}>
              {isFullscreen ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
            </button>
            <button type="button" onClick={refetch} className="p-2 rounded-lg border border-gray-200 hover:bg-gray-50" title="Refresh">
              <RefreshCw className={`w-4 h-4 text-gray-500 ${isFetching ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>

        <div className="flex items-center gap-2 w-full sm:w-auto">
          <div className="flex items-center gap-1 border border-gray-200 rounded-lg bg-gray-50 px-1">
            <button
              type="button"
              onClick={() => goToDate(addDaysISO(selectedDate, -1))}
              disabled={!minDate || selectedDate <= minDate}
              className="p-1.5 rounded-md disabled:opacity-30 hover:bg-white"
              title="Hari sebelumnya"
            >
              <ChevronLeft size={18} className="text-gray-600" />
            </button>
            <input
              type="date"
              value={selectedDate}
              min={minDate}
              max={maxDate}
              onChange={(e) => goToDate(e.target.value)}
              className="text-xs sm:text-sm text-gray-700 font-medium px-1 py-1 bg-transparent border-0 focus:ring-0 tabular-nums cursor-pointer"
              title="Pilih tanggal shift (mulai 06:00)"
            />
            <button
              type="button"
              onClick={() => goToDate(addDaysISO(selectedDate, 1))}
              disabled={!maxDate || selectedDate >= maxDate}
              className="p-1.5 rounded-md disabled:opacity-30 hover:bg-white"
              title="Hari berikutnya"
            >
              <ChevronRight size={18} className="text-gray-600" />
            </button>
          </div>

          {!isToday && (
            <button
              type="button"
              onClick={() => goToDate(null)}
              className="text-xs text-indigo-600 hover:text-indigo-800 font-medium px-2 py-1 rounded-md hover:bg-indigo-50 whitespace-nowrap"
            >
              Hari ini
            </button>
          )}

          {data?.is_current_shift && (
            <span className="hidden lg:inline text-xs text-cyan-700 bg-cyan-50 border border-cyan-200 rounded-md px-2 py-1 whitespace-nowrap">
              Shift berjalan
            </span>
          )}
        </div>

        {data?.shift_label && (
          <span className="hidden md:inline text-[11px] text-gray-500 truncate max-w-[16rem]" title={data.shift_label}>
            {data.shift_label}
          </span>
        )}

        {rangeSelect && (
          <span className="hidden sm:inline text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-md px-2 py-1 tabular-nums truncate max-w-[22rem]">
            <span className="font-medium">{rangeSelect.machineName}</span>
            {' · '}
            {rangeSelect.startLabel}
            {' – '}
            {rangeSelect.endLabel}
            {' · '}
            <span className="font-semibold">{rangeSelect.durationLabel}</span>
          </span>
        )}

        {hover?.machineName && hover?.timeLabel && !rangeSelect && !dragPreview && (
          <span className="hidden sm:inline text-xs text-gray-500 tabular-nums truncate max-w-[18rem]">
            <span className="font-medium text-gray-700">{hover.machineName}</span>
            {' · '}
            <span className="font-semibold text-cyan-700">{hover.timeLabel}</span>
          </span>
        )}

        <div className="hidden sm:flex items-center gap-1.5 sm:ml-auto">
          {meta && (
            <span className="hidden xl:inline text-[10px] text-gray-400 tabular-nums mr-1">
              {meta.first_snapshot_date} — {meta.last_snapshot_date}
            </span>
          )}
          <button type="button" onClick={handlePrint} className="p-2 rounded-lg border border-gray-200 hover:bg-gray-50 text-gray-600" title="Cetak A4 landscape">
            <Printer className="w-4 h-4" />
          </button>
          <button type="button" onClick={toggleFullscreen} className="p-2 rounded-lg border border-gray-200 hover:bg-gray-50 text-gray-600" title={isFullscreen ? 'Keluar layar penuh' : 'Layar penuh'}>
            {isFullscreen ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
          </button>
          <button type="button" onClick={refetch} className="p-2 rounded-lg border border-gray-200 hover:bg-gray-50" title="Refresh">
            <RefreshCw className={`w-4 h-4 text-gray-500 ${isFetching ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      <div
        ref={panelRef}
        className={`snapshot-print-flow flex flex-col flex-1 min-h-0 min-w-0 w-full bg-white print:h-auto print:overflow-visible ${isFullscreen ? 'p-2 bg-slate-900' : ''}`}
      >
        {isFullscreen && (
          <div className="no-print flex items-center justify-between mb-2 text-white shrink-0">
            <span className="text-sm font-medium">{data?.shift_label}</span>
            <button type="button" onClick={() => document.exitFullscreen?.()} className="p-1.5 rounded-md hover:bg-white/10">
              <X className="w-5 h-5" />
            </button>
          </div>
        )}

        <div className="snapshot-print-flow snapshot-print-root flex flex-col flex-1 min-h-0 min-w-0 w-full print:h-auto print:overflow-visible print:block">
          {isError ? (
            <div className="p-8 text-center flex-1 flex items-center justify-center">
              <div>
                <p className="text-sm text-red-600 font-medium mb-1">Gagal memuat timeline</p>
                <p className="text-xs text-gray-500">
                  {error?.status === 404 ? 'Restart Waitress lalu refresh.' : 'Periksa koneksi backend.'}
                </p>
              </div>
            </div>
          ) : !data && rawData && rawData.shift_date !== selectedDate ? (
            <div className="p-8 text-center flex-1 flex items-center justify-center">
              <div>
                <p className="text-sm text-amber-700 font-medium mb-1">Data tanggal tidak sesuai</p>
                <p className="text-xs text-gray-500">
                  Backend mengembalikan {rawData.shift_date}, diminta {selectedDate}.
                  Restart Waitress lalu refresh halaman.
                </p>
              </div>
            </div>
          ) : isLoadingDate ? (
            <div className="p-8 text-center text-gray-400 text-sm flex-1 flex items-center justify-center">Memuat data...</div>
          ) : (
            <>
              <div className="no-print sm:hidden shrink-0 px-3 pt-1.5 flex items-center gap-1 text-[10px] text-gray-400">
                <ChevronLeft className="w-3 h-3" />
                <ChevronRight className="w-3 h-3 -ml-2" />
                Geser tabel untuk melihat jam lainnya
              </div>

              <div
                ref={overlayRef}
                className="snapshot-print-flow relative flex-1 min-h-0 min-w-0 print:h-auto print:overflow-visible"
                onMouseLeave={handleChartLeave}
              >
                {hover?.lineLeft != null && !rangeSelect && !dragPreview && (
                  <>
                    <div
                      className="pointer-events-none absolute top-0 bottom-0 z-40 print:hidden"
                      style={{ left: hover.lineLeft }}
                    >
                      <div className="w-px h-full bg-cyan-500/90 shadow-[0_0_4px_rgba(6,182,212,0.5)]" />
                    </div>
                    <CrosshairPanel
                      timeLabel={hover.timeLabel}
                      stats={hoverStats}
                      left={hover.lineLeft}
                      top={hover.panelTop ?? 48}
                      flipX={!!hover.flipX}
                      flipY={!!hover.flipY}
                    />
                  </>
                )}

                {(dragPreview || rangeSelect) && (
                  <div
                    className="pointer-events-none absolute top-0 bottom-0 z-[35] print:hidden"
                    style={{
                      left: (dragPreview || rangeSelect).bandLeft,
                      width: Math.max((dragPreview || rangeSelect).bandWidth, 2),
                    }}
                  >
                    <div className={`absolute inset-0 ${rangeSelect ? 'bg-amber-400/30 border-x-2 border-amber-500/80' : 'bg-amber-300/25 border-x border-amber-400/70'}`} />
                    {rangeSelect && (
                      <div className="absolute top-2 left-1/2 -translate-x-1/2 px-2 py-1 rounded-md bg-amber-900/90 text-[10px] sm:text-xs font-semibold text-amber-50 tabular-nums whitespace-nowrap shadow-lg z-50">
                        {rangeSelect.startLabel}
                        {' → '}
                        {rangeSelect.endLabel}
                        <span className="mx-1.5 text-amber-200">|</span>
                        {rangeSelect.durationLabel}
                      </div>
                    )}
                  </div>
                )}

                <div className="snapshot-print-scroll h-full min-h-0 min-w-0 overflow-y-auto overflow-x-auto border border-gray-200 rounded-lg m-2 sm:m-3 print:m-0 print:border-0 print:overflow-visible print:h-auto">
                  <table
                    key={selectedDate}
                    className="snapshot-print-table w-full min-w-[68.25rem] print:min-w-0 border-separate border-spacing-0"
                  >
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
                            Laporan Jadwal Aktif Mesin Produksi
                          </p>
                          <p className="text-[10px] text-gray-600 mt-0.5 tabular-nums">
                            Shift {selectedDate}
                            {dateSubtitle ? ` · ${dateSubtitle}` : ''}
                            {' · '}
                            Dicetak: {new Date().toLocaleString('id-ID', { dateStyle: 'medium', timeStyle: 'short' })}
                          </p>
                          <SnapshotPrintLegend progressPct={progressPct} />
                        </th>
                      </tr>
                      <tr>
                        <th
                          scope="col"
                          className="sticky top-0 left-0 z-30 min-w-0 px-2 py-2 bg-slate-100 border-r border-b border-gray-200 text-left font-semibold align-bottom box-border h-8 print:static"
                        >
                          <span className="text-[10px] text-gray-500 uppercase tracking-wide">Mesin</span>
                        </th>
                        <th
                          scope="col"
                          className="sticky top-0 z-20 min-w-0 p-0 border-b border-gray-200 box-border font-normal print:static"
                        >
                          <TimeAxis timeLabels={data?.time_labels} progressPct={progressPct} />
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
                          className="sticky top-8 z-20 min-w-0 p-0 border-b border-gray-200 box-border font-normal print:static cursor-crosshair"
                          onMouseMove={(e) => handleChartMove(e, null, 'Uap')}
                          onMouseLeave={handleChartLeave}
                        >
                          <SteamHeatmap heatmap={data?.steam_heatmap} progressPct={progressPct} />
                        </th>
                      </tr>
                      <tr className="steam-pressure-row">
                        <th
                          scope="col"
                          className="sticky top-14 left-0 z-30 min-w-0 px-2 bg-slate-50 border-r border-b border-gray-200 text-left font-semibold align-middle box-border h-7 print:static print:h-5"
                        >
                          <span className="text-[9px] text-slate-700 uppercase tracking-wide leading-tight">
                            Prss
                            <span className="block text-[8px] font-normal text-slate-500/90 normal-case">barg</span>
                          </span>
                        </th>
                        <th
                          scope="col"
                          data-chart-cell
                          className="sticky top-14 z-20 min-w-0 p-0 border-b border-gray-200 box-border font-normal print:static cursor-crosshair"
                          onMouseMove={(e) => handleChartMove(e, null, 'Tekanan')}
                          onMouseLeave={handleChartLeave}
                        >
                          <SteamPressureRow pressure={data?.steam_pressure} progressPct={progressPct} />
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {(data?.groups || []).length === 0 ? (
                        <tr>
                          <td colSpan={2} className="py-10 text-center text-gray-400 text-sm">
                            Tidak ada data pada shift ini.
                          </td>
                        </tr>
                      ) : (
                        data.groups.map((group) => (
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
                              <TimelineBar
                                key={m.code}
                                machine={m}
                                progressPct={progressPct}
                                isHovered={hover?.machineCode === m.code || rangeSelect?.machineCode === m.code || dragPreview?.machineCode === m.code}
                                onRowEnter={() => handleRowEnter(m.code, m.name)}
                                onChartMove={(e) => handleChartMove(e, m.code, m.name)}
                                onChartLeave={handleChartLeave}
                                onChartMouseDown={(e) => handleChartMouseDown(e, m.code, m.name)}
                              />
                            ))}
                          </React.Fragment>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="no-print shrink-0 flex flex-nowrap sm:flex-wrap items-center gap-x-3 gap-y-1.5 px-3 sm:px-4 py-2 border-t border-gray-100 bg-gray-50/80 overflow-x-auto sm:overflow-visible">
                {Object.entries(PHASE_COLORS).map(([key, val]) => (
                  <span key={key} className="flex items-center gap-1.5 text-[10px] text-gray-600 shrink-0">
                    <span className={`inline-block w-3.5 h-2.5 ${val.bg}`} />
                    {val.label}
                  </span>
                ))}
                {progressPct < 100 && (
                  <span className="flex items-center gap-1.5 text-[10px] text-gray-400 shrink-0">
                    <span className="inline-block w-3.5 h-2.5 bg-slate-100 border border-dashed border-gray-300" />
                    Belum terjadi
                  </span>
                )}
                <span className="flex flex-nowrap sm:flex-wrap items-center gap-x-2 gap-y-1 text-[10px] text-gray-600 sm:ml-auto shrink-0">
                  <span className="text-gray-500 font-medium shrink-0">Uap (kg/h):</span>
                  {STEAM_HEAT_LEGEND.map((item) => (
                    <span key={item.label} className="flex items-center gap-1 shrink-0">
                      <span
                        className={`inline-block w-3.5 h-2.5 ${item.border ? 'border border-gray-300' : ''}`}
                        style={{ backgroundColor: item.color }}
                      />
                      {item.label}
                    </span>
                  ))}
                  <span className="text-gray-500 font-medium shrink-0 ml-1">Prss:</span>
                  <span className="flex items-center gap-1 shrink-0">
                    <span className="inline-block w-3.5 h-2.5 bg-red-500" />
                    &lt;3
                  </span>
                  <span className="flex items-center gap-1 shrink-0">
                    <span className="inline-block w-3.5 h-2.5 bg-amber-500" />
                    3–4.5
                  </span>
                  <span className="flex items-center gap-1 shrink-0">
                    <span className="inline-block w-3.5 h-2.5 bg-emerald-500" />
                    ≥4.5
                  </span>
                </span>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default SnapshotHistoryPivot;
