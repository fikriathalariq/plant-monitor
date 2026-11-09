import React, { useState, useEffect, useMemo } from 'react';
import {
  Flame,
  Droplet,
  RefreshCw,
  CheckCircle2,
  AlertCircle,
  Save,
  RotateCcw,
  ChevronDown,
  ChevronUp,
  Search,
  X,
  Info,
} from 'lucide-react';
import { useGetManualMachinesQuery, useUpdateManualMachinesMutation } from '../store/machinesApi';

// =========================================================================
// HELPER FORMATTING
// =========================================================================
function formatNumber(value, decimals = 1) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '0';
  return Number(value).toLocaleString('id-ID', { maximumFractionDigits: decimals });
}

function formatHto(val) {
  const n = Number(val) || 0;
  if (n === 0) return '0 kcal';
  if (n >= 1000000) {
    return `${(n / 1000000).toLocaleString('id-ID', { maximumFractionDigits: 1 })} jt kcal`;
  }
  if (n >= 1000) {
    return `${(n / 1000).toLocaleString('id-ID', { maximumFractionDigits: 0 })} rb kcal`;
  }
  return `${n.toLocaleString('id-ID')} kcal`;
}

function formatDelta(value, isHto = false) {
  const n = Number(value) || 0;
  if (Math.abs(n) < 0.1) return '0';
  const prefix = n > 0 ? '+' : '−';
  const absVal = Math.abs(n);
  if (isHto) {
    return `${prefix}${formatHto(absVal)}`;
  }
  return `${prefix}${formatNumber(absVal, 1)}`;
}

// =========================================================================
// TOGGLE SWITCH (SMOOTH IOS-STYLE)
// =========================================================================
function ToggleSwitch({ checked, switchColor, onChange }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={(e) => {
        e.stopPropagation();
        onChange();
      }}
      className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-2 ${
        checked ? (switchColor || 'bg-emerald-600') : 'bg-slate-200 hover:bg-slate-300'
      }`}
    >
      <span
        className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-md ring-0 transition duration-200 ease-in-out ${
          checked ? 'translate-x-5' : 'translate-x-0'
        }`}
      />
    </button>
  );
}

// =========================================================================
// MACHINE CARD COMPONENT
// Industrial badge for machine code replacing gear icon.
// Colors:
// - Manual Running: Green/Emerald
// - Auto HEAT/KEEP: Red/Rose
// - Preview / Modified: Orange/Amber
// - Offline / Stop: Slate
// =========================================================================
function MachineCard({
  machine: m,
  isChecked,
  isManual,
  isInitialOn,
  onToggle,
}) {
  const isDirty = isChecked !== isInitialOn;
  const hasSteam = (m.steam || 0) > 0;
  const hasHto = (m.hto || 0) > 0;

  // Visual card container styles
  let containerStyle = '';
  let badgeStyle = '';
  let switchColor = '';

  if (isManual) {
    if (isChecked) {
      if (isDirty) {
        // Was OFF, now ON in preview: Orange / Amber
        containerStyle = 'bg-amber-50/50 border-amber-300 shadow-xs hover:border-amber-400 ring-1 ring-amber-400/20';
        badgeStyle = 'bg-amber-600 text-white border-amber-500';
        switchColor = 'bg-amber-500';
      } else {
        // Actual Running: Green / Emerald (User requested: tetap hijau)
        containerStyle = 'bg-gradient-to-br from-white to-emerald-50/60 border-2 border-emerald-500 shadow-sm hover:border-emerald-600 ring-1 ring-emerald-500/20';
        badgeStyle = 'bg-emerald-600 text-white border-emerald-600 shadow-xs';
        switchColor = 'bg-emerald-600';
      }
    } else {
      if (isDirty) {
        // Was Running, now OFF in preview: Orange / Amber warning
        containerStyle = 'bg-amber-50/30 border-amber-200 hover:border-amber-300';
        badgeStyle = 'bg-slate-100 text-slate-700 border-slate-200';
        switchColor = 'bg-slate-200';
      } else {
        // Actual Offline: Slate netral
        containerStyle = 'bg-white border-slate-200/90 hover:border-slate-300';
        badgeStyle = 'bg-slate-100 text-slate-700 border-slate-200';
        switchColor = 'bg-slate-200';
      }
    }
  } else {
    // AUTO Machine (HEAT is RED/ROSE, STEADY is BLUE, Preview is Orange)
    const isSteady = m.thermal_status === 'STEADY';

    if (isChecked) {
      if (isDirty) {
        // Was OFF, now ON in preview: Orange / Amber
        containerStyle = 'bg-amber-50/50 border-2 border-dashed border-amber-400 shadow-xs hover:border-amber-500';
        badgeStyle = 'bg-amber-600 text-white border-amber-500';
        switchColor = 'bg-amber-500';
      } else if (isSteady) {
        // Actual STEADY: Blue (matching Home.jsx)
        containerStyle = 'bg-gradient-to-br from-white to-blue-50/50 border-2 border-blue-500 shadow-sm hover:border-blue-600 ring-1 ring-blue-500/20';
        badgeStyle = 'bg-blue-600 text-white border-blue-600 shadow-xs';
        switchColor = 'bg-blue-600';
      } else {
        // Actual HEAT: Vibrant Red / Crimson (matching Home.jsx)
        containerStyle = 'bg-gradient-to-br from-white to-rose-50/50 border-2 border-rose-500 shadow-sm hover:border-rose-600 ring-1 ring-rose-500/20';
        badgeStyle = 'bg-[#e11d48] text-white border-rose-600 shadow-xs';
        switchColor = 'bg-[#e11d48]';
      }
    } else {
      if (isDirty) {
        // Was Running, now OFF in preview: Orange dashed
        containerStyle = 'bg-amber-50/30 border-2 border-dashed border-amber-300 hover:border-amber-400';
        badgeStyle = 'bg-slate-100 text-slate-500 border-slate-200';
        switchColor = 'bg-slate-200';
      } else {
        // Actual OFF: Slate dashed
        containerStyle = 'bg-slate-50/50 border-2 border-dashed border-slate-300 hover:border-slate-400 opacity-80 hover:opacity-100';
        badgeStyle = 'bg-slate-100 text-slate-500 border-slate-200';
        switchColor = 'bg-slate-200';
      }
    }
  }

  return (
    <div
      onClick={onToggle}
      className={`rounded-xl border p-3 flex items-center justify-between gap-3 cursor-pointer transition-all select-none group ${containerStyle}`}
    >
      <div className="flex items-center gap-3 min-w-0 flex-1">
        {/* MACHINE CODE BADGE (Prominent Code Plate replacing gear icon) */}
        <div
          className={`w-16 sm:w-20 h-12 shrink-0 rounded-lg flex items-center justify-center text-center px-1.5 py-1 font-mono font-bold leading-tight border transition-all ${badgeStyle}`}
          title={`Kode Mesin: ${m.code}`}
        >
          <span className="truncate max-w-full text-xs sm:text-[13px] tracking-tight">
            {m.code}
          </span>
        </div>

        {/* MACHINE INFO */}
        <div className="min-w-0 flex-1 flex flex-col justify-center">
          {/* Machine Name */}
          <h4
            className="text-xs sm:text-sm font-bold text-slate-900 leading-tight truncate"
            title={m.name}
          >
            {m.name}
          </h4>

          {/* Operational Status Pill */}
          <div className="flex items-center gap-1.5 mt-0.5">
            {isManual ? (
              isChecked ? (
                isDirty ? (
                  <span className="inline-flex items-center gap-1 text-[11px] font-bold text-amber-700">
                    <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse"></span>
                    Running · PREVIEW
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 text-[11px] font-bold text-emerald-700">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
                    Running · MANUAL
                  </span>
                )
              ) : (
                isDirty ? (
                  <span className="inline-flex items-center gap-1 text-[11px] font-medium text-amber-700">
                    <span className="w-1.5 h-1.5 rounded-full bg-amber-400"></span>
                    OFF · PREVIEW
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 text-[11px] font-medium text-slate-500">
                    <span className="w-1.5 h-1.5 rounded-full bg-slate-300"></span>
                    Offline · MANUAL
                  </span>
                )
              )
            ) : (
              isChecked ? (
                isDirty ? (
                  <span className="inline-flex items-center gap-1 text-[11px] font-bold text-amber-700">
                    <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse"></span>
                    {m.thermal_status === 'STEADY' ? 'STEADY' : 'HEAT'} · PREVIEW
                  </span>
                ) : m.thermal_status === 'STEADY' ? (
                  <span className="inline-flex items-center gap-1 text-[11px] font-bold text-blue-700">
                    <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse"></span>
                    STEADY · AUTO IoT
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 text-[11px] font-bold text-rose-700">
                    <span className="w-1.5 h-1.5 rounded-full bg-rose-500 animate-pulse"></span>
                    HEAT · AUTO IoT
                  </span>
                )
              ) : (
                isDirty ? (
                  <span className="inline-flex items-center gap-1 text-[11px] font-medium text-amber-700">
                    <span className="w-1.5 h-1.5 rounded-full bg-amber-400"></span>
                    OFF · PREVIEW
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 text-[11px] font-medium text-slate-400">
                    <span className="w-1.5 h-1.5 rounded-full bg-slate-300"></span>
                    OFF · AUTO IoT
                  </span>
                )
              )
            )}

            {isDirty && (
              <span className="text-[10px] font-bold px-1 rounded bg-amber-100 text-amber-800 border border-amber-200">
                Diubah
              </span>
            )}
          </div>

          {/* Energy Rating Chips (No Blue - using amber and warm tones) */}
          <div className="flex items-center flex-wrap gap-1.5 mt-1">
            {hasSteam && (
              <span
                className={`inline-flex items-center gap-1 text-[10px] font-semibold px-1.5 py-0.5 rounded border ${
                  isChecked
                    ? 'bg-slate-100 text-slate-800 border-slate-300'
                    : 'bg-slate-100/80 text-slate-500 border-slate-200/60'
                }`}
              >
                <Flame className="w-3 h-3 text-amber-500 shrink-0" />
                {formatNumber(m.steam)} kg/h
              </span>
            )}
            {hasHto && (
              <span
                className={`inline-flex items-center gap-1 text-[10px] font-semibold px-1.5 py-0.5 rounded border ${
                  isChecked
                    ? 'bg-amber-50 text-amber-800 border-amber-200/90'
                    : 'bg-slate-100/80 text-slate-500 border-slate-200/60'
                }`}
              >
                <Droplet className="w-3 h-3 text-rose-500 shrink-0" />
                {formatHto(m.hto)}
              </span>
            )}
            {!hasSteam && !hasHto && (
              <span className="text-[10px] text-slate-400 italic">Non-termal</span>
            )}
          </div>
        </div>
      </div>

      {/* TOGGLE SWITCH */}
      <div className="shrink-0 pl-1">
        <ToggleSwitch
          checked={isChecked}
          switchColor={switchColor}
          onChange={onToggle}
        />
      </div>
    </div>
  );
}

// =========================================================================
// MAIN PAGE COMPONENT
// =========================================================================
const ManualMachineUsage = () => {
  const { data, isLoading, isFetching, error, refetch } = useGetManualMachinesQuery();
  const [updateManual, { isLoading: isSaving }] = useUpdateManualMachinesMutation();

  const [checkedIds, setCheckedIds] = useState(new Set());
  const [initialManualIds, setInitialManualIds] = useState(new Set());
  const [saveMsg, setSaveMsg] = useState(null);
  const [showDetailModal, setShowDetailModal] = useState(false);

  // Filters
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedGroupCode, setSelectedGroupCode] = useState('ALL');
  const [statusFilter, setStatusFilter] = useState('ALL'); // ALL, MANUAL_ONLY, AUTO_ONLY, RUNNING_ONLY, OFF_ONLY

  useEffect(() => {
    if (!data) return;
    const allOn = new Set();
    const manualOn = new Set();
    data.groups.forEach((g) => {
      g.machines.forEach((m) => {
        if (m.is_running) allOn.add(m.id);
        if (m.operation_mode === 'MANUAL' && m.is_running) manualOn.add(m.id);
      });
    });
    setCheckedIds(allOn);
    setInitialManualIds(manualOn);
  }, [data]);

  const machineById = useMemo(() => {
    const map = new Map();
    if (!data) return map;
    data.groups.forEach((g) => {
      g.machines.forEach((m) => map.set(m.id, m));
    });
    return map;
  }, [data]);

  // Actual baseline operational status (before preview toggles)
  const isCurrentlyOn = (m) => (
    m.operation_mode === 'MANUAL' ? initialManualIds.has(m.id) : Boolean(m.is_running)
  );

  // Toggle single machine
  const toggleMachine = (id) => {
    setSaveMsg(null);
    setCheckedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  // Revert all toggles to actual baseline live state
  const handleResetToRealtime = () => {
    if (!data) return;
    const allOn = new Set();
    data.groups.forEach((g) => {
      g.machines.forEach((m) => {
        if (isCurrentlyOn(m)) allOn.add(m.id);
      });
    });
    setCheckedIds(allOn);
    setSaveMsg({ type: 'info', text: 'Semua toggle dikembalikan ke kondisi nyata saat ini.' });
    setTimeout(() => setSaveMsg(null), 3000);
  };

  // Real-time projected stats calculation
  const stats = useMemo(() => {
    const empty = {
      currentCount: 0,
      projectedCount: 0,
      totalCount: 0,
      currentSteam: 0,
      currentHto: 0,
      projectedSteam: 0,
      projectedHto: 0,
      deltaSteam: 0,
      deltaHto: 0,
      deltaCount: 0,
    };
    if (!data) return empty;

    let currentCount = 0;
    let projectedCount = 0;
    let totalCount = 0;
    let currentSteam = 0;
    let currentHto = 0;
    let projectedSteam = 0;
    let projectedHto = 0;

    data.groups.forEach((g) => {
      g.machines.forEach((m) => {
        totalCount += 1;
        const steam = m.steam || 0;
        const hto = m.hto || 0;
        if (isCurrentlyOn(m)) {
          currentCount += 1;
          currentSteam += steam;
          currentHto += hto;
        }
        if (checkedIds.has(m.id)) {
          projectedCount += 1;
          projectedSteam += steam;
          projectedHto += hto;
        }
      });
    });

    const round1 = (n) => Math.round(n * 10) / 10;

    return {
      currentCount,
      projectedCount,
      totalCount,
      currentSteam,
      currentHto,
      projectedSteam,
      projectedHto,
      deltaSteam: round1(projectedSteam - currentSteam),
      deltaHto: Math.round(projectedHto - currentHto),
      deltaCount: projectedCount - currentCount,
    };
  }, [data, checkedIds, initialManualIds]);

  // Changed manual machines list (saveable to database)
  const changedManualMachines = useMemo(() => {
    const list = [];
    if (!data) return list;
    data.groups.forEach((g) => {
      g.machines.forEach((m) => {
        if (m.operation_mode === 'MANUAL') {
          const wasOn = initialManualIds.has(m.id);
          const isNowOn = checkedIds.has(m.id);
          if (wasOn !== isNowOn) {
            list.push({
              id: m.id,
              code: m.code,
              name: m.name,
              from: wasOn ? 'RUNNING' : 'STOP',
              to: isNowOn ? 'RUNNING' : 'STOP',
            });
          }
        }
      });
    });
    return list;
  }, [data, checkedIds, initialManualIds]);

  const hasSaveableChanges = changedManualMachines.length > 0;

  // Check if any machine differs from baseline (for Reset button activation)
  const hasAnyPreviewChanges = useMemo(() => {
    if (!data) return false;
    for (const g of data.groups) {
      for (const m of g.machines) {
        const wasOn = isCurrentlyOn(m);
        const isNowOn = checkedIds.has(m.id);
        if (wasOn !== isNowOn) return true;
      }
    }
    return false;
  }, [data, checkedIds, initialManualIds]);

  // Filter & Sort Groups:
  // - Filter uses actual status so machines being previewed DO NOT vanish
  // - Sort puts active machines on top, without jumping during preview
  const filteredGroups = useMemo(() => {
    if (!data) return [];
    const q = searchQuery.trim().toLowerCase();

    return data.groups
      .filter((g) => selectedGroupCode === 'ALL' || g.code === selectedGroupCode)
      .map((g) => {
        // 1. Filter machines
        const machines = g.machines.filter((m) => {
          // Text Search by code or name
          if (q) {
            const matchName = m.name?.toLowerCase().includes(q);
            const matchCode = m.code?.toLowerCase().includes(q);
            if (!matchName && !matchCode) return false;
          }

          // Status & Mode Filter based on ACTUAL baseline status (kebal terhadap preview)
          const isManual = m.operation_mode === 'MANUAL';
          const isActualOn = isCurrentlyOn(m);

          if (statusFilter === 'MANUAL_ONLY' && !isManual) return false;
          if (statusFilter === 'AUTO_ONLY' && isManual) return false;
          if (statusFilter === 'RUNNING_ONLY' && !isActualOn) return false;
          if (statusFilter === 'OFF_ONLY' && isActualOn) return false;

          return true;
        });

        // 2. Sort machines: Active machines on top (ascending by actual status, then code)
        // Using isCurrentlyOn(m) (actual state), so preview toggle does NOT jump cards!
        const sortedMachines = [...machines].sort((a, b) => {
          const aOn = isCurrentlyOn(a) ? 1 : 0;
          const bOn = isCurrentlyOn(b) ? 1 : 0;
          if (bOn !== aOn) {
            return bOn - aOn; // Yang aktif (1) tampil di atas yang mati (0)
          }
          return (a.code || '').localeCompare(b.code || '', undefined, { numeric: true });
        });

        return { ...g, machines: sortedMachines };
      })
      .filter((g) => g.machines.length > 0);
  }, [data, searchQuery, selectedGroupCode, statusFilter, initialManualIds]);

  // Save manual machine status to backend
  const handleSubmit = async () => {
    setSaveMsg(null);
    const machineIdsOn = [];
    checkedIds.forEach((id) => {
      const m = machineById.get(id);
      if (m?.operation_mode === 'MANUAL') machineIdsOn.push(id);
    });

    try {
      await updateManual({ machine_ids_on: machineIdsOn }).unwrap();
      setInitialManualIds(new Set(machineIdsOn));
      setSaveMsg({
        type: 'success',
        text: `Berhasil menyimpan status ${changedManualMachines.length} mesin manual.`,
      });
      setShowDetailModal(false);
      setTimeout(() => setSaveMsg(null), 4000);
    } catch (err) {
      setSaveMsg({
        type: 'error',
        text: err?.data?.detail || 'Gagal memperbarui status mesin.',
      });
    }
  };

  if (isLoading) {
    return (
      <div className="min-h-full pb-44 sm:pb-36 pt-3 px-3 sm:px-6 max-w-[1600px] mx-auto flex flex-col gap-4 font-sans antialiased">
        {/* HEADER SKELETON */}
        <header className="flex flex-col gap-3 bg-white p-3.5 sm:p-4 rounded-2xl border border-slate-200/90 shadow-2xs">
          <div className="w-32 h-6 rounded-md skeleton-shimmer" />
          <div className="flex flex-col md:flex-row gap-2.5 pt-1">
            <div className="h-9 rounded-lg skeleton-shimmer flex-1 min-w-[220px]" />
            <div className="h-9 w-44 rounded-lg skeleton-shimmer shrink-0" />
            <div className="flex items-center gap-1.5 overflow-x-auto">
              <div className="w-24 h-8 rounded-lg skeleton-shimmer" />
              <div className="w-24 h-8 rounded-lg skeleton-shimmer" />
              <div className="w-20 h-8 rounded-lg skeleton-shimmer" />
              <div className="w-20 h-8 rounded-lg skeleton-shimmer" />
            </div>
          </div>
        </header>

        {/* GROUP 1 SECTION BANNER SKELETON */}
        <div className="flex items-center justify-between px-1 pt-1">
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-full skeleton-shimmer" />
            <div className="w-44 h-5 rounded skeleton-shimmer" />
          </div>
          <div className="w-20 h-5 rounded-full skeleton-shimmer" />
        </div>

        {/* MACHINE CARDS GRID SKELETON (8 Cards) */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
          {[1, 2, 3, 4, 5, 6, 7, 8].map((i) => (
            <div
              key={i}
              className="rounded-xl border border-slate-200/90 bg-white p-3 flex items-center justify-between gap-3 shadow-2xs"
            >
              <div className="flex items-center gap-3 min-w-0 flex-1">
                {/* Machine code plate skeleton */}
                <div className="w-16 sm:w-20 h-12 shrink-0 rounded-lg skeleton-shimmer" />
                {/* Machine name & info skeleton */}
                <div className="min-w-0 flex-1 flex flex-col justify-center gap-2">
                  <div className="w-28 h-4 rounded skeleton-shimmer" />
                  <div className="w-20 h-3 rounded skeleton-shimmer" />
                </div>
              </div>
              {/* Toggle switch skeleton */}
              <div className="w-11 h-6 rounded-full skeleton-shimmer shrink-0" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex min-h-[60vh] w-full items-center justify-center p-6">
        <div className="bg-white rounded-xl border border-red-200 p-6 max-w-md text-center shadow-xs">
          <AlertCircle className="w-10 h-10 text-rose-500 mx-auto mb-3" />
          <h3 className="text-base font-bold text-slate-800">Gagal Memuat Mesin Aktif</h3>
          <p className="text-slate-600 text-xs mt-1">{error?.data?.detail || 'Silakan periksa koneksi server Anda.'}</p>
          <button
            type="button"
            onClick={refetch}
            className="mt-4 px-4 py-2 bg-slate-900 text-white rounded-lg text-xs font-semibold hover:bg-slate-800 transition-colors"
          >
            Coba Lagi
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-full pb-44 sm:pb-36 pt-3 px-3 sm:px-6 max-w-[1600px] mx-auto flex flex-col gap-4 font-sans antialiased animate-fade-in">
      {/* =========================================================================
          1. HEADER & CONTROLS
          Simple "Mesin Aktif" title without long captions
      ========================================================================= */}
      <header className="flex flex-col gap-3 bg-white p-3.5 sm:p-4 rounded-2xl border border-slate-200/90 shadow-2xs">
        <div className="flex items-center justify-between">
          <h1 className="text-lg sm:text-xl font-bold text-slate-900 leading-tight">
            Mesin Aktif
          </h1>
        </div>

        {/* Filter Toolbar: Search + Dept Select + Mode Chips */}
        <div className="flex flex-col md:flex-row gap-2.5 pt-1">
          {/* Search Input */}
          <div className="relative flex-1 min-w-[220px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" />
            <input
              type="search"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Cari kode mesin (misal: JD_01, Ehwa) atau nama..."
              className="w-full h-9 pl-9 pr-8 rounded-lg border border-slate-200 bg-slate-50/60 text-xs font-medium text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-emerald-500/30 focus:border-emerald-500 transition-all"
            />
            {searchQuery && (
              <button
                type="button"
                onClick={() => setSearchQuery('')}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 p-0.5 rounded text-slate-400 hover:text-slate-600"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>

          {/* Department Group Dropdown */}
          <div className="shrink-0 flex items-center gap-1">
            <select
              value={selectedGroupCode}
              onChange={(e) => setSelectedGroupCode(e.target.value)}
              className="h-9 px-3 rounded-lg border border-slate-200 bg-slate-50/60 text-xs font-semibold text-slate-700 focus:outline-none focus:ring-2 focus:ring-emerald-500/30 cursor-pointer"
            >
              <option value="ALL">Semua Departemen ({data?.groups?.length || 0})</option>
              {data?.groups?.map((g) => (
                <option key={g.code} value={g.code}>
                  {g.name}
                </option>
              ))}
            </select>
          </div>

          {/* Status & Mode Filter Chips */}
          <div className="flex items-center gap-1 overflow-x-auto pb-1 md:pb-0 hide-scrollbar">
            {[
              { id: 'ALL', label: 'Semua Mesin' },
              { id: 'MANUAL_ONLY', label: 'Manual Saja' },
              { id: 'AUTO_ONLY', label: 'Auto IoT' },
              { id: 'RUNNING_ONLY', label: 'Running' },
              { id: 'OFF_ONLY', label: 'Offline' },
            ].map((f) => (
              <button
                key={f.id}
                type="button"
                onClick={() => setStatusFilter(f.id)}
                className={`px-2.5 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all ${
                  statusFilter === f.id
                    ? 'bg-slate-900 text-white shadow-2xs'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>

        {/* Alerts / Feedback Banner */}
        {saveMsg && (
          <div
            className={`px-3 py-2 rounded-xl text-xs font-semibold flex items-center gap-2 animate-in fade-in duration-200 ${
              saveMsg.type === 'success'
                ? 'bg-emerald-50 text-emerald-800 border border-emerald-200'
                : saveMsg.type === 'info'
                ? 'bg-amber-50 text-amber-800 border border-amber-200'
                : 'bg-rose-50 text-rose-800 border border-rose-200'
            }`}
          >
            {saveMsg.type === 'success' && <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-600" />}
            {saveMsg.type === 'info' && <Info className="w-4 h-4 shrink-0 text-amber-600" />}
            {saveMsg.type === 'error' && <AlertCircle className="w-4 h-4 shrink-0 text-rose-600" />}
            <span>{saveMsg.text}</span>
          </div>
        )}
      </header>

      {/* =========================================================================
          2. MACHINE GROUPS GRID (TACTILE CARD VIEW WITH BOLD MACHINE CODES)
          Active machines are sorted to the top
      ========================================================================= */}
      <main className="flex flex-col gap-5">
        {filteredGroups.length === 0 ? (
          <div className="bg-white rounded-2xl border border-dashed border-slate-300 p-10 text-center flex flex-col items-center justify-center gap-2">
            <Search className="w-8 h-8 text-slate-400" />
            <h4 className="text-sm font-bold text-slate-800">Tidak Ada Mesin yang Cocok</h4>
            <p className="text-xs text-slate-500 max-w-sm">
              Coba gunakan kata kunci lain atau setel filter status ke "Semua Mesin".
            </p>
          </div>
        ) : (
          filteredGroups.map((group) => {
            const groupActiveCount = group.machines.filter((m) => isCurrentlyOn(m)).length;

            return (
              <section key={group.code} className="flex flex-col gap-2.5">
                {/* Section Header */}
                <div className="flex items-center justify-between px-1">
                  <div className="flex items-center gap-2">
                    <span className="w-2.5 h-2.5 rounded-full bg-slate-700"></span>
                    <h3 className="text-sm sm:text-base font-bold text-slate-900 leading-tight">
                      {group.name}
                    </h3>
                  </div>
                  <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 border border-slate-200 tabular-nums">
                    {groupActiveCount}/{group.machines.length} Aktif
                  </span>
                </div>

                {/* Machine Cards Grid */}
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
                  {group.machines.map((m) => {
                    const isManual = m.operation_mode === 'MANUAL';
                    const isChecked = checkedIds.has(m.id);
                    const isInitialOn = isCurrentlyOn(m);

                    return (
                      <MachineCard
                        key={m.id}
                        machine={m}
                        isChecked={isChecked}
                        isManual={isManual}
                        isInitialOn={isInitialOn}
                        onToggle={() => toggleMachine(m.id)}
                      />
                    );
                  })}
                </div>
              </section>
            );
          })
        )}
      </main>

      {/* =========================================================================
          3. FLOATING COCKPIT DOCK (FIXED AT BOTTOM)
          Live Steam & HTO calculation preview, Reset, and Save action
      ========================================================================= */}
      <div className="fixed bottom-20 sm:bottom-4 left-3 right-3 sm:left-6 sm:right-6 md:left-72 z-40">
        <div className="bg-slate-900/95 backdrop-blur-md text-white border border-slate-700/80 rounded-2xl shadow-2xl p-3 sm:px-4 sm:py-3 flex flex-col gap-2.5 max-w-4xl mx-auto animate-in slide-in-from-bottom-3 duration-200">
          
          {/* Row 1: Real-time Energy Calculation Preview & Actions */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 sm:gap-3">
            
            {/* Energy Calculation Preview: On mobile, clicking this section toggles Detail open/close */}
            <div
              onClick={() => {
                if (typeof window !== 'undefined' && window.innerWidth < 640) {
                  setShowDetailModal((v) => !v);
                }
              }}
              className="flex items-center justify-between sm:justify-start gap-3 sm:gap-6 cursor-pointer sm:cursor-default select-none group"
              title="Ketuk untuk melihat detail breakdown"
            >
              <div className="flex items-center gap-4 sm:gap-6">
                {/* Steam Indicator (Amber/Warm Flame, No Blue) */}
                <div className="flex items-center gap-2">
                  <div className="w-7 h-7 rounded-lg bg-amber-950/60 text-amber-400 flex items-center justify-center border border-amber-800/80 shrink-0">
                    <Flame className="w-4 h-4 text-amber-400" />
                  </div>
                  <div>
                    <span className="text-[10px] uppercase font-bold text-slate-400 block leading-tight">
                      Steam Boiler
                    </span>
                    <div className="flex items-baseline gap-1.5">
                      <span className="text-xs sm:text-sm font-bold text-white tabular-nums">
                        {formatNumber(stats.projectedSteam)} <span className="text-[10px] text-slate-400 font-normal">kg/h</span>
                        <span className="text-[11px] text-slate-400 font-semibold ml-1">
                          ({(stats.projectedSteam / 1000).toFixed(1).replace('.', ',')} ton/h)
                        </span>
                      </span>
                      {stats.deltaSteam !== 0 && (
                        <span
                          className={`text-[10px] font-bold px-1.5 py-0.2 rounded ${
                            stats.deltaSteam > 0
                              ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                              : 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                          }`}
                        >
                          {formatDelta(stats.deltaSteam)}
                        </span>
                      )}
                    </div>
                  </div>
                </div>

                {/* HTO Indicator */}
                <div className="flex items-center gap-2">
                  <div className="w-7 h-7 rounded-lg bg-amber-950 text-amber-400 flex items-center justify-center border border-amber-800 shrink-0">
                    <Droplet className="w-4 h-4 text-rose-400" />
                  </div>
                  <div>
                    <span className="text-[10px] uppercase font-bold text-slate-400 block leading-tight">
                      HTO Boiler
                    </span>
                    <div className="flex items-baseline gap-1.5">
                      <span className="text-xs sm:text-sm font-bold text-white tabular-nums">
                        {formatHto(stats.projectedHto)}
                      </span>
                      {stats.deltaHto !== 0 && (
                        <span
                          className={`text-[10px] font-bold px-1.5 py-0.2 rounded ${
                            stats.deltaHto > 0
                              ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                              : 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                          }`}
                        >
                          {formatDelta(stats.deltaHto, true)}
                        </span>
                      )}
                    </div>
                  </div>
                </div>

                {/* Active Machine Count (Desktop) */}
                <div className="hidden md:flex items-center gap-2 pl-2 border-l border-slate-700/80">
                  <div>
                    <span className="text-[10px] uppercase font-bold text-slate-400 block leading-tight">
                      Mesin Aktif
                    </span>
                    <span className="text-xs font-bold text-slate-200 tabular-nums">
                      {stats.projectedCount} / {stats.totalCount}
                      {stats.deltaCount !== 0 && (
                        <span className="ml-1 text-[10px] text-slate-400 font-semibold">
                          ({stats.deltaCount > 0 ? `+${stats.deltaCount}` : stats.deltaCount})
                        </span>
                      )}
                    </span>
                  </div>
                </div>
              </div>

              {/* Indikator toggle chevron khusus mobile agar jelas card bisa ditekan */}
              <div className="sm:hidden flex items-center text-slate-400 pr-0.5">
                {showDetailModal ? (
                  <ChevronDown className="w-4 h-4 text-slate-300" />
                ) : (
                  <ChevronUp className="w-4 h-4 text-slate-400 group-hover:text-white" />
                )}
              </div>
            </div>

            {/* Actions: Detail (Desktop only), Reset (Desktop only), and Save Button (Full-width on mobile) */}
            <div className="flex items-center gap-2 w-full sm:w-auto sm:ml-auto">
              {/* Detail Collapse/Expand (Desktop only - di HP cukup tekan card steam/hto) */}
              <button
                type="button"
                onClick={() => setShowDetailModal((v) => !v)}
                className="hidden sm:flex px-2.5 py-1.5 rounded-xl text-xs font-semibold text-slate-300 hover:text-white hover:bg-slate-800 transition-colors items-center gap-1 border border-slate-700"
              >
                <span>Detail</span>
                {showDetailModal ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronUp className="w-3.5 h-3.5" />}
              </button>

              {/* Reset Button (Desktop only - di HP dihapus sesuai permintaan) */}
              <button
                type="button"
                onClick={handleResetToRealtime}
                disabled={!hasAnyPreviewChanges}
                className={`hidden sm:flex items-center gap-1 px-3 py-1.5 rounded-xl text-xs font-semibold transition-all border ${
                  hasAnyPreviewChanges
                    ? 'bg-slate-800 text-amber-300 hover:text-white hover:bg-slate-700 border-slate-700 shadow-xs cursor-pointer'
                    : 'bg-slate-800/40 text-slate-600 border-slate-800/60 cursor-not-allowed'
                }`}
                title="Kembalikan semua sakelar ke kondisi aktual pabrik"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                <span>Reset</span>
              </button>

              {/* Simpan Status Button: Dibuat lebar (w-full) di layar HP seperti 8000/mesin-aktif */}
              <button
                type="button"
                onClick={handleSubmit}
                disabled={isSaving || isFetching || !hasSaveableChanges}
                className={`w-full sm:w-auto flex items-center justify-center gap-2 px-4 py-2.5 sm:py-1.5 rounded-xl text-xs font-bold transition-all shadow-md active:scale-95 ${
                  hasSaveableChanges
                    ? 'bg-emerald-500 hover:bg-emerald-400 text-slate-950 shadow-emerald-500/25 ring-2 ring-emerald-400/40 cursor-pointer'
                    : 'bg-slate-800 text-slate-500 cursor-not-allowed border border-slate-700/60'
                }`}
              >
                <Save className="w-4 h-4 sm:w-3.5 sm:h-3.5" />
                {isSaving ? (
                  'Menyimpan...'
                ) : hasSaveableChanges ? (
                  <span>Simpan Status ({changedManualMachines.length})</span>
                ) : (
                  <span>Simpan Status</span>
                )}
              </button>
            </div>
          </div>

          {/* Collapsible Detail Breakdown Panel */}
          {showDetailModal && (
            <div className="pt-2 border-t border-slate-700/80 flex flex-col gap-2.5 text-xs animate-in fade-in duration-150">
              <div className="grid grid-cols-3 gap-2 bg-slate-800/80 p-2.5 rounded-xl border border-slate-700 text-center">
                <div>
                  <span className="text-[10px] uppercase font-bold text-slate-400 block">Saat Ini (Current)</span>
                  <div className="text-slate-200 font-bold mt-0.5">
                    {formatNumber(stats.currentSteam)} kg/h · {formatHto(stats.currentHto)}
                  </div>
                </div>
                <div>
                  <span className="text-[10px] uppercase font-bold text-slate-400 block">Proyeksi (Projected)</span>
                  <div className="text-white font-bold mt-0.5">
                    {formatNumber(stats.projectedSteam)} kg/h · {formatHto(stats.projectedHto)}
                  </div>
                </div>
                <div>
                  <span className="text-[10px] uppercase font-bold text-slate-400 block">Selisih Beban (Delta)</span>
                  <div className={`font-bold mt-0.5 ${stats.deltaSteam > 0 || stats.deltaHto > 0 ? 'text-amber-400' : 'text-emerald-400'}`}>
                    {formatDelta(stats.deltaSteam)} kg/h · {formatDelta(stats.deltaHto, true)}
                  </div>
                </div>
              </div>

              {/* List of Changed Manual Machines */}
              {hasSaveableChanges ? (
                <div className="flex flex-col gap-1">
                  <span className="text-[10px] font-bold uppercase text-amber-400 tracking-wider">
                    Daftar Mesin Manual yang Akan Disimpan:
                  </span>
                  <div className="flex flex-wrap gap-1.5 max-h-24 overflow-y-auto">
                    {changedManualMachines.map((c) => (
                      <span
                        key={c.id}
                        className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-slate-800 border border-slate-700 text-[11px] font-mono"
                      >
                        <span className="font-bold text-white">{c.code}</span>:
                        <span className={c.to === 'RUNNING' ? 'text-emerald-400 font-bold' : 'text-rose-400 font-bold'}>
                          {c.from} → {c.to}
                        </span>
                      </span>
                    ))}
                  </div>
                </div>
              ) : (
                <p className="text-[11px] text-slate-400 italic">
                  Belum ada perubahan pada mesin manual. Geser sakelar mesin untuk mensimulasikan atau menyimpan status baru.
                </p>
              )}
            </div>
          )}

        </div>
      </div>
    </div>
  );
};

export default ManualMachineUsage;
