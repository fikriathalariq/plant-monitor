import React, { useState, useMemo, useRef, useCallback, useEffect } from 'react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, Legend, ResponsiveContainer,
} from 'recharts';
import {
  RefreshCw, RotateCcw, ZoomIn, ZoomOut, Crosshair, Printer, X, Download, BarChart3, Search,
} from 'lucide-react';
import {
  useGetAnalyticsMachinesQuery, useGetAnalyticsMultiQuery, useGetSteamHtoAnalyticsQuery, useGetSnapshotDetailQuery,
} from '../store/analyticsApi';
import MultiSelectDropdown from '../components/MultiSelectDropdown';
import MachineChecklist from '../components/MachineChecklist';
import MultiMachineTempChart, { getValuesAtTimestamp, parseTs } from '../components/MultiMachineTempChart';
import ChartChannelsTable from '../components/ChartChannelsTable';
import DateTimePicker from '../components/DateTimePicker';

function formatDT(date) {
  const pad = (n) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function formatCursorTime(ts) {
  const d = parseTs(ts);
  const p = (n) => String(n).padStart(2, '0');
  return `${p(d.getDate())}/${p(d.getMonth() + 1)}/${d.getFullYear()} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

function formatCursorDateParts(ts) {
  const d = parseTs(ts);
  const p = (n) => String(n).padStart(2, '0');
  return {
    date: `${p(d.getDate())}/${p(d.getMonth() + 1)}/${d.getFullYear()}`,
    time: `${p(d.getHours())}:${p(d.getMinutes())}`,
  };
}

const MAX_RANGE_DAYS = 7;

const AnalyticsGrafik = () => {
  const now = new Date();
  const dayAgo = new Date(now.getTime() - 24 * 3600 * 1000);
  const defaultStart = formatDT(dayAgo);
  const defaultEnd = formatDT(now);

  // Draft = UI filter sedang diedit; Applied = filter yang dipakai query (hanya setelah Tampilkan)
  const [draftStart, setDraftStart] = useState(defaultStart);
  const [draftEnd, setDraftEnd] = useState(defaultEnd);
  const [draftMachines, setDraftMachines] = useState([]);
  const [appliedStart, setAppliedStart] = useState(defaultStart);
  const [appliedEnd, setAppliedEnd] = useState(defaultEnd);
  const [appliedMachines, setAppliedMachines] = useState([]);
  const [hasAppliedOnce, setHasAppliedOnce] = useState(false);
  const [filterError, setFilterError] = useState('');

  const [selectedGroups, setSelectedGroups] = useState([]);
  const [yMin, setYMin] = useState('');
  const [yMax, setYMax] = useState('');
  const [y1Min, setY1Min] = useState('');
  const [y1Max, setY1Max] = useState('');
  const [zoomMode, setZoomMode] = useState('xy');
  const [cursorMode, setCursorMode] = useState(false);
  const [cursors, setCursors] = useState([]);
  const [showPrintPreview, setShowPrintPreview] = useState(false);
  const [printImage, setPrintImage] = useState('');
  const [showResetZoom, setShowResetZoom] = useState(false);
  const [hiddenChannels, setHiddenChannels] = useState([]);
  const [drillTimestamp, setDrillTimestamp] = useState(null);
  const [drillType, setDrillType] = useState('steam');

  const chartRef = useRef(null);
  const chartPanelRef = useRef(null);
  const printChartBoxRef = useRef(null);

  const isDirty = useMemo(() => (
    draftStart !== appliedStart
    || draftEnd !== appliedEnd
    || draftMachines.join(',') !== appliedMachines.join(',')
  ), [draftStart, draftEnd, draftMachines, appliedStart, appliedEnd, appliedMachines]);

  useEffect(() => {
    setHiddenChannels((prev) => prev.filter((c) => appliedMachines.includes(c)));
  }, [appliedMachines]);

  useEffect(() => {
    setCursors([]);
  }, [appliedStart, appliedEnd, appliedMachines.join(',')]);

  const { data: machineList } = useGetAnalyticsMachinesQuery();
  const {
    data: multiData,
    isFetching: loadingChart,
    isError: multiError,
    refetch: refetchChart,
  } = useGetAnalyticsMultiQuery(
    { machines: appliedMachines.join(','), start: appliedStart, end: appliedEnd },
    { skip: !hasAppliedOnce || appliedMachines.length === 0 },
  );
  const {
    data: steamHto,
    isFetching: loadingSteamHto,
    isError: steamError,
    refetch: refetchSteamHto,
  } = useGetSteamHtoAnalyticsQuery(
    { start: appliedStart, end: appliedEnd, interval: 5 },
    { skip: !hasAppliedOnce },
  );
  const { data: snapshotDetail } = useGetSnapshotDetailQuery(
    { timestamp: drillTimestamp, type: drillType },
    { skip: !drillTimestamp },
  );

  const groups = useMemo(() => {
    if (!machineList) return [];
    const map = new Map();
    machineList.forEach((m) => {
      if (m.group_code) map.set(m.group_code, m.group || m.group_code);
    });
    return Array.from(map, ([code, name]) => ({ code, name }))
      .sort((a, b) => a.code.localeCompare(b.code));
  }, [machineList]);

  const groupOptions = useMemo(
    () => groups.map((g) => ({ value: g.code, label: g.name })),
    [groups],
  );

  const filteredMachines = useMemo(() => {
    if (!machineList) return [];
    if (selectedGroups.length === 0) return machineList;
    return machineList.filter((m) => m.group_code && selectedGroups.includes(m.group_code));
  }, [machineList, selectedGroups]);

  const machineChecklistOptions = useMemo(
    () => filteredMachines.map((m) => ({ value: m.code, label: m.name })),
    [filteredMachines],
  );

  const machineNames = useMemo(() => {
    const map = {};
    (machineList || []).forEach((m) => { map[m.code] = m.name; });
    return map;
  }, [machineList]);

  const machineUnits = useMemo(() => {
    const map = {};
    (machineList || []).forEach((m) => { map[m.code] = m.unit; });
    return map;
  }, [machineList]);

  const hasSecondaryAxis = useMemo(() => {
    if (!multiData || appliedMachines.length === 0) return false;
    const units = appliedMachines.map((code) => multiData.meta?.[code]?.unit || '');
    const unique = [...new Set(units)].filter((u) => u !== '');
    return unique.length > 1;
  }, [multiData, appliedMachines]);

  const handleZoomChange = useCallback((zoomed) => {
    setShowResetZoom(zoomed);
  }, []);

  const handleResetZoom = () => {
    chartRef.current?.resetZoom();
    setShowResetZoom(false);
  };

  const handleZoomIn = () => chartRef.current?.zoomIn();
  const handleZoomOut = () => chartRef.current?.zoomOut();

  const handleToggleChannel = useCallback((code) => {
    setHiddenChannels((prev) => (
      prev.includes(code) ? prev.filter((c) => c !== code) : [...prev, code]
    ));
  }, []);

  const handleSelectAllMachines = useCallback(() => {
    setFilterError('');
    setDraftMachines(filteredMachines.map((m) => m.code));
  }, [filteredMachines]);

  const handleClearMachines = useCallback(() => {
    setFilterError('');
    setDraftMachines([]);
  }, []);

  const setDraftStartSafe = useCallback((v) => {
    setFilterError('');
    setDraftStart(v);
  }, []);

  const setDraftEndSafe = useCallback((v) => {
    setFilterError('');
    setDraftEnd(v);
  }, []);

  const setDraftMachinesSafe = useCallback((v) => {
    setFilterError('');
    setDraftMachines(v);
  }, []);

  const validateDraftFilters = useCallback(() => {
    if (draftMachines.length === 0) {
      return 'Pilih minimal 1 mesin sebelum menampilkan grafik.';
    }
    const startMs = parseTs(draftStart).getTime();
    const endMs = parseTs(draftEnd).getTime();
    if (Number.isNaN(startMs) || Number.isNaN(endMs)) {
      return 'Format tanggal tidak valid.';
    }
    if (startMs >= endMs) {
      return 'Tanggal Dari harus lebih awal dari Sampai.';
    }
    const daySpan = (endMs - startMs) / (24 * 3600 * 1000);
    if (daySpan > MAX_RANGE_DAYS) {
      return `Rentang maksimal ${MAX_RANGE_DAYS} hari. Perkecil periode lalu tekan Tampilkan.`;
    }
    return '';
  }, [draftMachines, draftStart, draftEnd]);

  const handleApplyFilters = useCallback(() => {
    const err = validateDraftFilters();
    if (err) {
      setFilterError(err);
      return;
    }
    setFilterError('');
    setAppliedStart(draftStart);
    setAppliedEnd(draftEnd);
    setAppliedMachines([...draftMachines]);
    setHasAppliedOnce(true);
    setShowResetZoom(false);
  }, [validateDraftFilters, draftStart, draftEnd, draftMachines]);

  const handleRefresh = useCallback(() => {
    if (!hasAppliedOnce) return;
    if (appliedMachines.length > 0) refetchChart();
    refetchSteamHto();
  }, [hasAppliedOnce, appliedMachines.length, refetchChart, refetchSteamHto]);

  const handleCursorPlace = useCallback((timestamp) => {
    setCursors((prev) => {
      if (prev.some((c) => c.timestamp === timestamp)) return prev;
      return [...prev, { id: `${timestamp}-${Date.now()}`, timestamp }];
    });
  }, []);

  const handleRemoveCursor = useCallback((id) => {
    setCursors((prev) => prev.filter((c) => c.id !== id));
  }, []);

  const handleClearCursors = useCallback(() => setCursors([]), []);

  const handleExportPNG = async () => {
    const img = await chartRef.current?.getChartImage?.({ scale: 2 });
    if (!img) return;
    const link = document.createElement('a');
    link.href = img;
    link.download = `grafik-suhu-multi-mesin-${Date.now()}.png`;
    link.click();
  };

  const handleOpenPrintPreview = () => {
    setPrintImage('');
    setShowPrintPreview(true);
  };

  // Render ulang grafik persis sesuai ukuran kotak cetak (bebas letterbox) begitu preview terbuka.
  useEffect(() => {
    if (!showPrintPreview) return undefined;
    let cancelled = false;
    let pendingFrame = null;

    const measureAndRender = async () => {
      const box = printChartBoxRef.current;
      // Ukuran fisik tetap → rasio preview = rasio cetak.
      // PRINT_SCALE = 3 → ~280 dpi. pixelScale harus = PRINT_SCALE agar font/garis
      // proporsional di canvas besar; fontBoost menambah keterbacaan di kertas A4.
      const PRINT_SCALE = 3;
      const w = Math.max(900, Math.round((box?.clientWidth || 1065) * PRINT_SCALE));
      const h = Math.max(600, Math.round((box?.clientHeight || 640) * PRINT_SCALE));
      const img = await chartRef.current?.getChartImage?.({
        width: w,
        height: h,
        pixelScale: PRINT_SCALE,
        fontBoost: 0.92,
      });
      if (!cancelled) setPrintImage(img || '');
    };

    // Dua rAF berturut-turut agar layout modal (ukuran kotak grafik) sudah pasti final sebelum diukur.
    pendingFrame = requestAnimationFrame(() => {
      pendingFrame = requestAnimationFrame(measureAndRender);
    });

    return () => {
      cancelled = true;
      if (pendingFrame) cancelAnimationFrame(pendingFrame);
    };
  }, [showPrintPreview]);

  const handlePrint = () => {
    const style = document.createElement('style');
    style.id = 'grafik-print-page-style';
    style.textContent = '@page { size: A4 landscape; margin: 0; }';
    document.head.appendChild(style);
    document.body.classList.add('printing-grafik');
    const cleanup = () => {
      document.body.classList.remove('printing-grafik');
      document.getElementById('grafik-print-page-style')?.remove();
    };
    window.addEventListener('afterprint', cleanup, { once: true });
    window.print();
  };

  const axisLimits = useMemo(
    () => ({ yMin, yMax, y1Min, y1Max }),
    [yMin, yMax, y1Min, y1Max],
  );

  const steamHtoChartData = useMemo(() => {
    if (!steamHto) return [];
    return steamHto.timestamps.map((ts, i) => ({
      time: ts.slice(11),
      fullTs: ts,
      steam: steamHto.steam_totals[i],
      hto: steamHto.hto_totals[i],
    }));
  }, [steamHto]);

  return (
    <div className="p-4 sm:p-6 bg-gray-50 min-h-full pb-20 md:pb-6 space-y-6">
      {/* Multi-machine chart */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-4 sm:p-5 print:hidden">
        <h2 className="text-lg font-bold text-gray-800 mb-4">Grafik Suhu Multi-Mesin</h2>

        {/* Filter: Machine (kiri, selalu terbuka) + Machine Group / Dari / Sampai (kanan) */}
        <div className="grid grid-cols-1 lg:grid-cols-[1.15fr_1fr] gap-4 mb-4">
          <MachineChecklist
            options={machineChecklistOptions}
            selected={draftMachines}
            onChange={setDraftMachinesSafe}
            onSelectAll={handleSelectAllMachines}
            onClearAll={handleClearMachines}
          />

          <div className="space-y-3">
            <div>
              <label className="block text-sm font-medium text-gray-600 mb-1">Machine Group</label>
              <MultiSelectDropdown
                options={groupOptions}
                selected={selectedGroups}
                onChange={setSelectedGroups}
                placeholder=""
                emptyLabel="Semua grup"
                allLabel="Tampilkan semua grup"
                className="min-w-0 w-full"
              />
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium text-gray-600 mb-1">Dari</label>
                <DateTimePicker value={draftStart} onChange={setDraftStartSafe} />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-600 mb-1">Sampai</label>
                <DateTimePicker value={draftEnd} onChange={setDraftEndSafe} />
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2 pt-1">
              <button
                type="button"
                onClick={handleApplyFilters}
                disabled={loadingChart || loadingSteamHto}
                className={`inline-flex items-center gap-1.5 px-4 py-2 text-sm font-semibold rounded-md disabled:opacity-50 ${
                  isDirty || !hasAppliedOnce
                    ? 'bg-[#1e3a5f] text-white hover:bg-[#2d4a6f]'
                    : 'bg-gray-200 text-gray-600'
                }`}
              >
                <Search className={`w-4 h-4 ${(loadingChart || loadingSteamHto) ? 'animate-pulse' : ''}`} />
                {(loadingChart || loadingSteamHto) ? 'Memuat...' : 'Tampilkan'}
              </button>
              {isDirty && hasAppliedOnce && (
                <span className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-1">
                  Filter diubah — tekan Tampilkan untuk memuat ulang
                </span>
              )}
              {!hasAppliedOnce && (
                <span className="text-xs text-gray-500">
                  Pilih mesin & periode, lalu tekan Tampilkan (tidak auto-load)
                </span>
              )}
            </div>
            {filterError && (
              <p className="text-sm text-red-600 bg-red-50 border border-red-100 rounded-md px-3 py-2">{filterError}</p>
            )}
          </div>
        </div>

        {/* Kontrol sumbu Y */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4 p-3.5 bg-gray-50 rounded-lg border border-gray-100">
          <div>
            <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Min Y</label>
            <input
              type="number"
              value={yMin}
              onChange={(e) => setYMin(e.target.value)}
              placeholder="Auto"
              className="w-full border border-gray-300 rounded-md text-sm px-3 py-2"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Max Y</label>
            <input
              type="number"
              value={yMax}
              onChange={(e) => setYMax(e.target.value)}
              placeholder="150"
              className="w-full border border-gray-300 rounded-md text-sm px-3 py-2"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Min Y-Sekunder</label>
            <input
              type="number"
              value={y1Min}
              onChange={(e) => setY1Min(e.target.value)}
              placeholder="Auto"
              disabled={!hasSecondaryAxis}
              className="w-full border border-gray-300 rounded-md text-sm px-3 py-2 disabled:opacity-40"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Max Y-Sekunder</label>
            <input
              type="number"
              value={y1Max}
              onChange={(e) => setY1Max(e.target.value)}
              placeholder="Auto"
              disabled={!hasSecondaryAxis}
              className="w-full border border-gray-300 rounded-md text-sm px-3 py-2 disabled:opacity-40"
            />
          </div>
        </div>

        <p className="text-xs text-gray-400 mb-2">
          Zoom XY: Shift + drag di grafik · Zoom Y: drag di strip sumbu kiri · Zoom X: drag di strip sumbu bawah · Ctrl + drag = pan
        </p>

        {/* Panel grafik industrial — header ala port 8000: judul kiri, aksi kanan */}
        <div ref={chartPanelRef} id="chart-print-area" className="border border-[#9ec5e8] rounded-sm overflow-hidden bg-white shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-2 px-3 py-2.5 bg-[#e8f2fa] border-b border-[#9ec5e8]">
            <div className="flex items-center gap-2">
              <BarChart3 className="w-4 h-4 text-[#1e3a5f]" />
              <h3 className="text-sm sm:text-base font-bold text-[#1e3a5f]">Visualisasi Data</h3>
            </div>

            <div className="flex flex-wrap items-center gap-1.5">
              {showResetZoom && (
                <button
                  type="button"
                  onClick={handleResetZoom}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-sm border border-[#9ec5e8] rounded-md bg-white hover:bg-[#d4e8f7] text-[#1e3a5f] font-medium"
                >
                  <RotateCcw className="w-4 h-4" />
                  Reset Zoom
                </button>
              )}
              <button
                type="button"
                onClick={handleZoomIn}
                disabled={appliedMachines.length === 0 || !multiData}
                className="p-2 rounded-md hover:bg-[#d4e8f7] disabled:opacity-40 text-[#1e3a5f]"
                title="Zoom In"
              >
                <ZoomIn className="w-4 h-4" />
              </button>
              <button
                type="button"
                onClick={handleZoomOut}
                disabled={appliedMachines.length === 0 || !multiData}
                className="p-2 rounded-md hover:bg-[#d4e8f7] disabled:opacity-40 text-[#1e3a5f]"
                title="Zoom Out"
              >
                <ZoomOut className="w-4 h-4" />
              </button>
              <select
                value={zoomMode}
                onChange={(e) => setZoomMode(e.target.value)}
                className="text-xs border border-[#9ec5e8] rounded-md px-2 py-1.5 bg-white text-[#1e3a5f] font-medium"
                title="Mode zoom"
              >
                <option value="xy">Zoom XY</option>
                <option value="y">Zoom Y-axis</option>
                <option value="x">Zoom X-axis</option>
              </select>
              <button
                type="button"
                onClick={() => setCursorMode((v) => !v)}
                disabled={appliedMachines.length === 0 || !multiData}
                className={`p-2 rounded-md disabled:opacity-40 ${
                  cursorMode ? 'bg-red-100 text-red-700' : 'hover:bg-[#d4e8f7] text-[#1e3a5f]'
                }`}
                title="Measurement Cursor — klik grafik untuk taruh titik"
              >
                <Crosshair className="w-4 h-4" />
              </button>
              {cursors.length > 0 && (
                <button
                  type="button"
                  onClick={handleClearCursors}
                  className="text-xs px-2 py-1 text-red-600 hover:bg-red-50 rounded-md font-medium"
                >
                  Reset kursor
                </button>
              )}
              <div className="w-px h-6 bg-[#9ec5e8] mx-0.5" />
              <button
                type="button"
                onClick={handleRefresh}
                disabled={!hasAppliedOnce || loadingChart || loadingSteamHto}
                className="p-2 rounded-md hover:bg-[#d4e8f7] disabled:opacity-40 text-[#1e3a5f]"
                title="Muat ulang data (filter yang sudah diterapkan)"
              >
                <RefreshCw className={`w-4 h-4 ${loadingChart || loadingSteamHto ? 'animate-spin' : ''}`} />
              </button>
              <button
                type="button"
                onClick={handleExportPNG}
                disabled={appliedMachines.length === 0 || !multiData}
                className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-sm border border-[#9ec5e8] rounded-md bg-white hover:bg-[#d4e8f7] disabled:opacity-40 text-[#1e3a5f] font-medium"
                title="Unduh grafik sebagai PNG"
              >
                <Download className="w-4 h-4" />
                PNG
              </button>
              <button
                type="button"
                onClick={handleOpenPrintPreview}
                disabled={appliedMachines.length === 0 || !multiData}
                className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-sm border border-[#9ec5e8] rounded-md bg-white hover:bg-[#d4e8f7] disabled:opacity-40 text-[#1e3a5f] font-medium"
                title="Print Preview"
              >
                <Printer className="w-4 h-4" />
                Print
              </button>
            </div>
          </div>
          {cursorMode && (
            <div className="px-3 py-1 bg-red-50 border-b border-red-100 text-xs text-red-600 font-medium">
              Mode kursor aktif — klik pada grafik untuk menaruh titik ukur.
            </div>
          )}

          {/* Chart */}
          <div className="h-[28rem] bg-white">
            {!hasAppliedOnce ? (
              <div className="h-full flex items-center justify-center text-[#5a7a9a] text-sm px-4 text-center">
                Pilih mesin dan periode, lalu tekan <strong className="mx-1">Tampilkan</strong> untuk memuat grafik.
              </div>
            ) : appliedMachines.length === 0 ? (
              <div className="h-full flex items-center justify-center text-[#5a7a9a] text-sm">
                Pilih minimal 1 mesin untuk menampilkan grafik.
              </div>
            ) : loadingChart && !multiData ? (
              <div className="h-full flex items-center justify-center text-[#5a7a9a] text-sm">Memuat data...</div>
            ) : multiError ? (
              <div className="h-full flex items-center justify-center text-red-600 text-sm">
                Gagal memuat grafik. Coba tekan Tampilkan / Refresh lagi.
              </div>
            ) : (
              <MultiMachineTempChart
                ref={chartRef}
                multiData={multiData}
                selectedMachines={appliedMachines}
                machineNames={machineNames}
                hiddenChannels={hiddenChannels}
                axisLimits={axisLimits}
                zoomMode={zoomMode}
                cursorMode={cursorMode}
                cursors={cursors}
                onCursorPlace={handleCursorPlace}
                onZoomChange={handleZoomChange}
                onToggleChannel={handleToggleChannel}
              />
            )}
          </div>

          {/* Channels table */}
          {hasAppliedOnce && appliedMachines.length > 0 && multiData && (
            <ChartChannelsTable
              selectedMachines={appliedMachines}
              machineNames={machineNames}
              machineUnits={machineUnits}
              multiData={multiData}
              hiddenChannels={hiddenChannels}
              onToggleChannel={handleToggleChannel}
              scaleMin={yMin}
              scaleMax={yMax}
              cursors={cursors}
              onRemoveCursor={handleRemoveCursor}
              onClearCursors={handleClearCursors}
            />
          )}
        </div>
      </div>

      {/* Steam & HTO analytics */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-4 sm:p-5 print:hidden">
        <h2 className="text-lg font-bold text-gray-800 mb-4">Steam & HTO Analytics</h2>
        <div className="h-72">
          {!hasAppliedOnce ? (
            <div className="h-full flex items-center justify-center text-gray-400 text-sm px-4 text-center">
              Tekan <strong className="mx-1">Tampilkan</strong> untuk memuat Steam & HTO pada periode yang dipilih.
            </div>
          ) : loadingSteamHto && !steamHto ? (
            <div className="h-full flex items-center justify-center text-gray-400 text-sm">Memuat...</div>
          ) : steamError ? (
            <div className="h-full flex items-center justify-center text-red-600 text-sm">
              Gagal memuat Steam & HTO. Coba Refresh.
            </div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart
                data={steamHtoChartData}
                margin={{ top: 10, right: 10, left: -10, bottom: 0 }}
                onClick={(e) => {
                  if (e?.activePayload?.[0]) setDrillTimestamp(e.activePayload[0].payload.fullTs);
                }}
              >
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f3f4f6" />
                <XAxis dataKey="time" tick={{ fontSize: 11 }} minTickGap={40} />
                <YAxis yAxisId="left" tick={{ fontSize: 11 }} />
                <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11 }} />
                <RechartsTooltip />
                <Legend wrapperStyle={{ fontSize: '12px' }} />
                <Line yAxisId="left" type="monotone" dataKey="steam" name="Steam (kg/h)" stroke="#f59e0b" dot={false} strokeWidth={2} />
                <Line yAxisId="right" type="monotone" dataKey="hto" name="HTO (kCal/h)" stroke="#10b981" dot={false} strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>
        <p className="text-xs text-gray-400 mt-2">Klik titik pada grafik untuk melihat rincian mesin pada waktu tersebut (drill-down).</p>
      </div>

      {/* Print preview — full-bleed A4 landscape, mirip cara port 8000 mencetak grafik */}
      {showPrintPreview && (
        <>
          <div className="fixed inset-0 bg-black/50 z-50 print:hidden" onClick={() => setShowPrintPreview(false)} aria-hidden />
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 pointer-events-none print:static print:p-0 print:block">
            <div
              className="bg-white rounded-lg shadow-xl w-full max-w-[1200px] max-h-[95vh] overflow-y-auto pointer-events-auto print:shadow-none print:max-w-none print:max-h-none print:overflow-visible print:rounded-none print:w-auto"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between px-4 py-2 border-b border-gray-200 print:hidden">
                <div>
                  <h3 className="font-semibold text-sm text-gray-800">Print Preview — Grafik Suhu Multi-Mesin</h3>
                  <p className="text-xs text-gray-500 mt-0.5">Format: A4 landscape, penuh halaman</p>
                </div>
                <button type="button" onClick={() => setShowPrintPreview(false)} className="text-gray-400 hover:text-gray-700">
                  <X className="w-5 h-5" />
                </button>
              </div>

              <div className="p-2.5 bg-slate-100 overflow-x-auto print:p-0 print:bg-white print:overflow-visible">
                <div
                  id="print-preview-content"
                  className={`grafik-print-sheet bg-white border border-gray-300 shadow-sm print:border-0 print:shadow-none ${
                    cursors.length > 0 ? 'grafik-print-has-analog' : ''
                  }`}
                >
                  <section className="grafik-print-page grafik-print-page-chart">
                    <header className="grafik-print-header">
                      <div>
                        <h1 className="grafik-print-title">Grafik Suhu Multi-Mesin</h1>
                        <div className="grafik-print-meta">
                          <span><strong>Periode:</strong> {appliedStart} — {appliedEnd}</span>
                          <span><strong>Mesin:</strong> {appliedMachines.map((c) => machineNames[c] || c).join(', ')}</span>
                        </div>
                      </div>
                      <div className="grafik-print-stamp">
                        Dicetak: {formatCursorTime(formatDT(new Date()))}
                      </div>
                    </header>
                    <div ref={printChartBoxRef} className="grafik-print-chart">
                      {printImage ? (
                        <img src={printImage} alt="Grafik Suhu Multi-Mesin" />
                      ) : (
                        <p className="text-sm text-gray-400 self-center justify-self-center m-auto">Memuat grafik...</p>
                      )}
                    </div>
                  </section>

                  {cursors.length > 0 && (
                    <section className="grafik-print-page grafik-print-page-analog">
                      <h2 className="grafik-print-analog-title">
                        Measurement Cursor <span>— Analog</span>
                      </h2>
                      <div className="grafik-print-analog-wrap">
                        <table className="grafik-print-analog-table">
                          <colgroup>
                            <col style={{ width: '8%' }} />
                            <col style={{ width: '18%' }} />
                            <col style={{ width: '40%' }} />
                            <col style={{ width: '18%' }} />
                            <col style={{ width: '16%' }} />
                          </colgroup>
                          <thead>
                            <tr>
                              <th>#</th>
                              <th>Waktu</th>
                              <th>Channel</th>
                              <th className="text-right">Nilai</th>
                              <th>Satuan</th>
                            </tr>
                          </thead>
                          <tbody>
                            {cursors.map((cur, ci) => {
                              const readings = getValuesAtTimestamp(multiData, cur.timestamp, appliedMachines);
                              const parts = formatCursorDateParts(cur.timestamp);
                              return readings.map((r, ri) => {
                                const name = machineNames[r.code] || r.code;
                                const isAlt = ri % 2 === 1;
                                return (
                                  <tr key={`${cur.id}-${r.code}`} className={isAlt ? 'is-alt' : ''}>
                                    {ri === 0 && (
                                      <>
                                        <td rowSpan={readings.length} className="cell-idx">
                                          M{ci + 1}
                                        </td>
                                        <td rowSpan={readings.length} className="cell-waktu">
                                          <span className="block">{parts.date}</span>
                                          <span className="block">{parts.time}</span>
                                        </td>
                                      </>
                                    )}
                                    <td className="cell-channel">{name}</td>
                                    <td className="cell-nilai">
                                      {r.value != null ? r.value.toFixed(1) : '—'}
                                    </td>
                                    <td className="cell-satuan">
                                      {r.unit || machineUnits[r.code] || '—'}
                                    </td>
                                  </tr>
                                );
                              });
                            })}
                          </tbody>
                        </table>
                      </div>
                    </section>
                  )}
                </div>
              </div>

              <div className="flex justify-end gap-2 px-4 py-2 border-t border-gray-200 print:hidden">
                <button
                  type="button"
                  onClick={() => setShowPrintPreview(false)}
                  className="px-3 py-1.5 text-sm border border-gray-300 rounded-md hover:bg-gray-50"
                >
                  Tutup
                </button>
                <button
                  type="button"
                  onClick={handlePrint}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm bg-[#1e3a5f] text-white rounded-md hover:bg-[#2d4a6f]"
                >
                  <Printer className="w-4 h-4" />
                  Cetak A4 Landscape
                </button>
              </div>
            </div>
          </div>
        </>
      )}

      {/* Print + preview styles — full-bleed per halaman, ala port 8000 */}
      <style>{`
        .grafik-print-sheet {
          width: 297mm;
          max-width: 100%;
          margin: 0 auto;
          box-sizing: border-box;
          color: #0b1c30;
          font-family: Inter, system-ui, sans-serif;
        }
        /*
          Ukuran halaman DIKUNCI fisik (297mm x 210mm), bukan relatif ke tinggi layar.
          Ini memastikan proporsi header vs area grafik yang dipakai untuk generate
          gambar grafik SELALU sama persis dengan hasil cetak sungguhan — kalau dulu
          dipakai aspect-ratio + max-height relatif viewport, di layar pendek proporsi
          header jadi lebih besar dari seharusnya sehingga grafik hasil cetak jadi kecil.
          Kalau halaman ini lebih tinggi dari layar, modal preview akan discroll saja.
        */
        .grafik-print-page {
          width: 297mm;
          height: 210mm;
          box-sizing: border-box;
          display: flex;
          flex-direction: column;
          /* ~2 cm margin atas (di atas judul) & bawah (di bawah sumbu X) */
          padding: 20mm 8mm;
          overflow: hidden;
        }
        .grafik-print-page + .grafik-print-page {
          margin-top: 12px;
          border-top: 1px dashed #c6c6cd;
          padding-top: 10mm;
        }
        .grafik-print-header {
          display: flex;
          justify-content: space-between;
          align-items: flex-end;
          gap: 12px;
          border-bottom: 2px solid #0b1c30;
          padding-bottom: 4px;
          margin-bottom: 4px;
          flex: 0 0 auto;
        }
        .grafik-print-title {
          font-size: 16pt;
          line-height: 1.2;
          font-weight: 700;
          margin: 0 0 2px;
          color: #0b1c30;
        }
        .grafik-print-meta {
          display: flex;
          flex-direction: column;
          gap: 1px;
          font-size: 9pt;
          line-height: 1.3;
          color: #45464d;
        }
        .grafik-print-stamp {
          font-size: 9pt;
          color: #45464d;
          text-align: right;
          white-space: nowrap;
          flex-shrink: 0;
        }
        .grafik-print-chart {
          flex: 1 1 auto;
          min-height: 0;
          min-width: 0;
          border: 1.5px solid #c6c6cd;
          display: flex;
          overflow: hidden;
          background: #fff;
        }
        .grafik-print-chart img {
          display: block;
          width: 100%;
          height: 100%;
          object-fit: fill;
          object-position: center;
        }
        .grafik-print-analog-title {
          font-size: 11pt;
          font-weight: 600;
          margin: 0 0 5px;
          color: #0b1c30;
          flex: 0 0 auto;
        }
        .grafik-print-analog-title span {
          font-weight: 400;
          color: #45464d;
        }
        .grafik-print-analog-wrap {
          border: 1.5px solid #0b1c30;
          overflow: hidden;
          background: #fff;
          flex: 1 1 auto;
          min-height: 0;
        }
        .grafik-print-analog-table {
          width: 100%;
          border-collapse: collapse;
          table-layout: fixed;
          font-size: 9pt;
          line-height: 1.3;
        }
        .grafik-print-analog-table thead {
          background: #0b1c30;
          color: #fff;
        }
        .grafik-print-analog-table th {
          padding: 6px 8px;
          font-size: 8pt;
          font-weight: 700;
          letter-spacing: 0.04em;
          text-transform: uppercase;
          text-align: left;
          border-bottom: 1px solid #0b1c30;
        }
        .grafik-print-analog-table th.text-right,
        .grafik-print-analog-table td.cell-nilai {
          text-align: right;
        }
        .grafik-print-analog-table td {
          padding: 5px 8px;
          border-bottom: 1px solid #c6c6cd;
          vertical-align: top;
          overflow-wrap: anywhere;
          word-break: break-word;
        }
        .grafik-print-analog-table tr.is-alt td {
          background: #f3f6fb;
        }
        .grafik-print-analog-table .cell-idx {
          font-weight: 700;
          color: #b91c1c;
          font-size: 9pt;
        }
        .grafik-print-analog-table .cell-waktu {
          font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
          font-size: 8pt;
          white-space: nowrap;
        }
        .grafik-print-analog-table .cell-nilai {
          font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
          font-weight: 700;
          font-size: 9pt;
        }
        .grafik-print-analog-table .cell-satuan {
          text-align: center;
          color: #45464d;
        }

        @media print {
          @page {
            size: A4 landscape;
            margin: 0;
          }
          body.printing-grafik * {
            visibility: hidden !important;
          }
          body.printing-grafik #print-preview-content,
          body.printing-grafik #print-preview-content * {
            visibility: visible !important;
          }
          body.printing-grafik #print-preview-content {
            position: absolute !important;
            left: 0 !important;
            top: 0 !important;
            width: 297mm !important;
            margin: 0 !important;
            box-sizing: border-box !important;
            background: #fff !important;
            border: none !important;
            box-shadow: none !important;
            -webkit-print-color-adjust: exact !important;
            print-color-adjust: exact !important;
          }
          body.printing-grafik #print-preview-content .grafik-print-page {
            page-break-after: always !important;
            break-after: page !important;
          }
          body.printing-grafik #print-preview-content .grafik-print-page:last-child {
            page-break-after: auto !important;
            break-after: auto !important;
          }
          body.printing-grafik #print-preview-content .grafik-print-page + .grafik-print-page {
            margin-top: 0 !important;
            border-top: none !important;
          }
          body.printing-grafik #print-preview-content .grafik-print-analog-table thead {
            background: #0b1c30 !important;
            color: #fff !important;
          }
          body.printing-grafik #print-preview-content .grafik-print-analog-table tr.is-alt td {
            background: #f3f6fb !important;
          }
          body.printing-grafik aside,
          body.printing-grafik header.no-print,
          body.printing-grafik .no-print,
          body.printing-grafik .print\\:hidden {
            display: none !important;
          }
        }
      `}</style>

      {/* Snapshot drill-down modal */}
      {drillTimestamp && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={() => setDrillTimestamp(null)}>
          <div className="bg-white rounded-xl shadow-xl max-w-lg w-full max-h-[80vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <div className="px-4 py-3 border-b border-gray-200 flex items-center justify-between sticky top-0 bg-white">
              <div>
                <h3 className="font-semibold text-sm text-gray-800">Detail Snapshot: {drillTimestamp}</h3>
                <div className="flex gap-2 mt-1">
                  <button type="button" onClick={() => setDrillType('steam')} className={`text-xs px-2 py-0.5 rounded-full ${drillType === 'steam' ? 'bg-amber-100 text-amber-700' : 'bg-gray-100 text-gray-500'}`}>Steam</button>
                  <button type="button" onClick={() => setDrillType('hto')} className={`text-xs px-2 py-0.5 rounded-full ${drillType === 'hto' ? 'bg-red-100 text-red-700' : 'bg-gray-100 text-gray-500'}`}>HTO</button>
                </div>
              </div>
              <button type="button" onClick={() => setDrillTimestamp(null)} className="text-gray-400 hover:text-gray-700 text-xl leading-none">&times;</button>
            </div>
            <div className="p-4">
              {!snapshotDetail ? (
                <p className="text-sm text-gray-400">Memuat...</p>
              ) : snapshotDetail.error ? (
                <p className="text-sm text-gray-400">{snapshotDetail.error}</p>
              ) : (
                <>
                  <p className="text-xs text-gray-500 mb-3">
                    Total usage: <span className="font-bold text-gray-800">{snapshotDetail.total_usage} {snapshotDetail.unit}</span> dari {snapshotDetail.total_active_machines} mesin aktif
                  </p>
                  <div className="space-y-1.5">
                    {snapshotDetail.machines.map((m) => (
                      <div key={m.code} className="flex items-center justify-between text-xs border-b border-gray-50 pb-1.5">
                        <div>
                          <span className="font-semibold text-gray-700">{m.name}</span>
                          <span className="text-gray-400 ml-1">({m.group})</span>
                        </div>
                        <div className="text-right">
                          <span className={`font-bold ${m.is_currently_active ? 'text-green-600' : 'text-gray-400'}`}>{m.usage_value} {m.unit}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AnalyticsGrafik;
