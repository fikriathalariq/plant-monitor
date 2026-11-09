import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../lib/api';
import { Search, ChevronLeft, ChevronRight, Filter, RotateCcw, X, ChevronDown } from 'lucide-react';
import { ProcessStatusIcon, ProcessStatusBadge } from '../components/ProcessStatusIcon';

const defaultDraftFilters = {
  search: '',
  group: '',
  machine: '',
  start_date: '',
  end_date: '',
};

const getInitialState = (key, defaultVal) => {
  const saved = sessionStorage.getItem(key);
  if (saved) {
    try {
      return JSON.parse(saved);
    } catch (e) {
      return defaultVal;
    }
  }
  return defaultVal;
};

// Catatan: halaman ini menampilkan daftar batch DyeingProcess (paginated + search),
// setara dengan history_list.html di Django SSR. Sebelumnya komponen ini bernama
// "SnapshotHistory" di dalam App.jsx yang membingungkan karena bentrok nama dengan
// fitur "Snapshot History" yang sebenarnya (lihat SnapshotHistoryPivot.jsx).
const HistoryList = () => {
  const navigate = useNavigate();
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(() => getInitialState('history_page', 1));
  const [totalPages, setTotalPages] = useState(1);
  const [totalCount, setTotalCount] = useState(0);

  // Filters UI state
  const [mobileFilterOpen, setMobileFilterOpen] = useState(false);
  const [filtersLoading, setFiltersLoading] = useState(true);
  const [filterOptions, setFilterOptions] = useState({ groups: [], machines: [] });

  const [draftFilters, setDraftFilters] = useState(() => getInitialState('history_draftFilters', defaultDraftFilters));
  const [appliedFilters, setAppliedFilters] = useState(() => getInitialState('history_appliedFilters', defaultDraftFilters));

  useEffect(() => {
    sessionStorage.setItem('history_page', JSON.stringify(page));
  }, [page]);

  useEffect(() => {
    sessionStorage.setItem('history_draftFilters', JSON.stringify(draftFilters));
  }, [draftFilters]);

  useEffect(() => {
    sessionStorage.setItem('history_appliedFilters', JSON.stringify(appliedFilters));
  }, [appliedFilters]);

  const activeFilterCount = useMemo(() => {
    const s = appliedFilters.search?.trim() ? 1 : 0;
    const g = appliedFilters.group ? 1 : 0;
    const m = appliedFilters.machine ? 1 : 0;
    const sd = appliedFilters.start_date ? 1 : 0;
    const ed = appliedFilters.end_date ? 1 : 0;
    return s + g + m + sd + ed;
  }, [appliedFilters]);

  const machinesForSelectedGroup = useMemo(() => {
    const groupCode = draftFilters.group;
    if (!groupCode) return filterOptions.machines;
    return filterOptions.machines.filter((m) => m.group_code === groupCode);
  }, [draftFilters.group, filterOptions.machines]);

  const fetchHistory = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set('page', String(page));

      if (appliedFilters.search?.trim()) params.set('search', appliedFilters.search.trim());
      if (appliedFilters.group) params.set('group', appliedFilters.group);
      if (appliedFilters.machine) params.set('machine', appliedFilters.machine);
      if (appliedFilters.start_date) params.set('start_date', appliedFilters.start_date);
      if (appliedFilters.end_date) params.set('end_date', appliedFilters.end_date);

      const res = await api.get(`/history/?${params.toString()}`);
      setData(res.data.data);
      setTotalPages(res.data.num_pages);
      setTotalCount(res.data.total || 0);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const fetchFilters = async () => {
      setFiltersLoading(true);
      try {
        const res = await api.get('/history/filters');
        setFilterOptions(res.data);
      } catch (err) {
        console.error(err);
      } finally {
        setFiltersLoading(false);
      }
    };
    fetchFilters();
  }, []);

  useEffect(() => {
    fetchHistory();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    page,
    appliedFilters.search,
    appliedFilters.group,
    appliedFilters.machine,
    appliedFilters.start_date,
    appliedFilters.end_date,
  ]);

  const openReport = (row) => {
    navigate(`/history/report/${row.id}`);
  };

  return (
    <div className="flex flex-col h-full p-2 sm:p-3 md:p-4 bg-slate-50 overflow-hidden">
      {/* Filter Toolbar Container */}
      <div className="shrink-0 mb-2 sm:mb-2.5 bg-white border border-slate-200/90 rounded-xl p-2 sm:p-2.5 shadow-2xs">
        {/* ========================================================= */}
        {/* MOBILE VIEW (< md): Search Bar + Toggle Filter Button      */}
        {/* ========================================================= */}
        <div className="flex items-center gap-2 md:hidden">
          {/* Search Box Mobile */}
          <div className="relative flex-1 min-w-0">
            <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none">
              <Search className="w-3.5 h-3.5" />
            </span>
            <input
              type="text"
              placeholder="Cari Batch, Mesin, Order..."
              value={draftFilters.search}
              onChange={(e) => setDraftFilters((prev) => ({ ...prev, search: e.target.value }))}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  setAppliedFilters(draftFilters);
                  setPage(1);
                }
              }}
              className="w-full h-9 pl-8 pr-7 py-1 text-xs border border-slate-200 rounded-lg bg-slate-50/60 focus:bg-white text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-amber-400 focus:border-amber-400 transition-all"
            />
            {draftFilters.search && (
              <button
                type="button"
                onClick={() => {
                  setDraftFilters((prev) => ({ ...prev, search: '' }));
                  setAppliedFilters((prev) => ({ ...prev, search: '' }));
                  setPage(1);
                }}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 p-0.5"
                title="Hapus kata kunci"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>

          {/* Toggle Filter Button Mobile */}
          <button
            type="button"
            onClick={() => setMobileFilterOpen((o) => !o)}
            className={`h-9 px-2.5 sm:px-3 rounded-lg border text-xs font-bold flex items-center gap-1.5 transition-all shrink-0 active:scale-95 ${
              mobileFilterOpen || activeFilterCount > 0
                ? 'bg-amber-400 border-amber-400 text-slate-950 shadow-2xs'
                : 'bg-white border-slate-200 text-slate-700 hover:bg-slate-50'
            }`}
          >
            <Filter className="w-3.5 h-3.5" />
            <span>Filter</span>
            {activeFilterCount > 0 && (
              <span className="w-4 h-4 rounded-full bg-slate-950 text-amber-300 text-[10px] flex items-center justify-center font-mono font-bold">
                {activeFilterCount}
              </span>
            )}
            <ChevronDown className={`w-3.5 h-3.5 transition-transform duration-200 ${mobileFilterOpen ? 'rotate-180' : ''}`} />
          </button>
        </div>

        {/* Mobile Filter Chips (Muncul saat filter aktif & drawer tertutup) */}
        {!mobileFilterOpen && activeFilterCount > 0 && (
          <div className="flex md:hidden items-center gap-1.5 pt-2 overflow-x-auto hide-scrollbar text-[11px]">
            {appliedFilters.group && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-amber-50 text-amber-900 border border-amber-200 shrink-0 font-medium">
                Unit: <b>{appliedFilters.group}</b>
                <button
                  type="button"
                  onClick={() => {
                    setAppliedFilters((p) => ({ ...p, group: '', machine: '' }));
                    setDraftFilters((p) => ({ ...p, group: '', machine: '' }));
                    setPage(1);
                  }}
                  className="hover:text-rose-600 ml-0.5"
                >
                  <X className="w-3 h-3" />
                </button>
              </span>
            )}
            {appliedFilters.machine && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-amber-50 text-amber-900 border border-amber-200 shrink-0 font-medium">
                Mesin: <b>{appliedFilters.machine}</b>
                <button
                  type="button"
                  onClick={() => {
                    setAppliedFilters((p) => ({ ...p, machine: '' }));
                    setDraftFilters((p) => ({ ...p, machine: '' }));
                    setPage(1);
                  }}
                  className="hover:text-rose-600 ml-0.5"
                >
                  <X className="w-3 h-3" />
                </button>
              </span>
            )}
            {(appliedFilters.start_date || appliedFilters.end_date) && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-amber-50 text-amber-900 border border-amber-200 shrink-0 font-medium">
                📅 {appliedFilters.start_date || '...'} s/d {appliedFilters.end_date || '...'}
                <button
                  type="button"
                  onClick={() => {
                    setAppliedFilters((p) => ({ ...p, start_date: '', end_date: '' }));
                    setDraftFilters((p) => ({ ...p, start_date: '', end_date: '' }));
                    setPage(1);
                  }}
                  className="hover:text-rose-600 ml-0.5"
                >
                  <X className="w-3 h-3" />
                </button>
              </span>
            )}
            <button
              type="button"
              onClick={() => {
                setDraftFilters(defaultDraftFilters);
                setAppliedFilters(defaultDraftFilters);
                setPage(1);
              }}
              className="text-[10px] text-rose-600 hover:underline font-bold shrink-0 px-1 ml-auto"
            >
              Reset
            </button>
          </div>
        )}

        {/* Mobile Collapsible Panel (Grid 2 Kolom untuk Unit, Mesin, Tanggal) */}
        {mobileFilterOpen && (
          <div className="flex md:hidden flex-col gap-2 pt-2.5 border-t border-slate-100 mt-2 animate-in fade-in duration-150">
            {/* Grid 2 Kolom: Unit & Mesin */}
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-wide mb-1">
                  Unit
                </label>
                <select
                  value={draftFilters.group}
                  onChange={(e) => {
                    const next = e.target.value;
                    setDraftFilters((prev) => ({ ...prev, group: next, machine: '' }));
                  }}
                  disabled={filtersLoading}
                  className="w-full h-9 px-2 py-1 border border-slate-200 rounded-lg bg-slate-50/60 focus:bg-white text-xs font-semibold text-slate-800 focus:outline-none focus:ring-1 focus:ring-amber-400"
                >
                  <option value="">Semua Unit</option>
                  {filterOptions.groups.map((g) => (
                    <option key={g.code} value={g.code}>
                      {g.code}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-wide mb-1">
                  Mesin
                </label>
                <select
                  value={draftFilters.machine}
                  onChange={(e) => setDraftFilters((prev) => ({ ...prev, machine: e.target.value }))}
                  disabled={filtersLoading}
                  className="w-full h-9 px-2 py-1 border border-slate-200 rounded-lg bg-slate-50/60 focus:bg-white text-xs font-semibold text-slate-800 focus:outline-none focus:ring-1 focus:ring-amber-400"
                >
                  <option value="">Semua Mesin</option>
                  {machinesForSelectedGroup.map((m) => (
                    <option key={m.code} value={m.code}>
                      {m.code || m.name}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {/* Grid 2 Kolom: Tanggal Mulai & Tanggal Selesai */}
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-wide mb-1">
                  Tanggal Mulai
                </label>
                <input
                  type="date"
                  value={draftFilters.start_date}
                  onChange={(e) => setDraftFilters((prev) => ({ ...prev, start_date: e.target.value }))}
                  disabled={filtersLoading}
                  className="w-full h-9 px-2 py-1 border border-slate-200 rounded-lg bg-slate-50/60 focus:bg-white text-xs text-slate-700 focus:outline-none focus:ring-1 focus:ring-amber-400"
                />
              </div>

              <div>
                <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-wide mb-1">
                  Tanggal Selesai
                </label>
                <input
                  type="date"
                  value={draftFilters.end_date}
                  onChange={(e) => setDraftFilters((prev) => ({ ...prev, end_date: e.target.value }))}
                  disabled={filtersLoading}
                  className="w-full h-9 px-2 py-1 border border-slate-200 rounded-lg bg-slate-50/60 focus:bg-white text-xs text-slate-700 focus:outline-none focus:ring-1 focus:ring-amber-400"
                />
              </div>
            </div>

            {/* Tombol Aksi Mobile (Reset & Terapkan) */}
            <div className="grid grid-cols-2 gap-2 pt-1">
              <button
                type="button"
                onClick={() => {
                  setDraftFilters(defaultDraftFilters);
                  setAppliedFilters(defaultDraftFilters);
                  setPage(1);
                  setMobileFilterOpen(false);
                }}
                className="h-9 border border-slate-200 rounded-lg text-xs font-semibold text-slate-600 hover:bg-slate-100 flex items-center justify-center gap-1.5 transition-colors"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                <span>Reset</span>
              </button>

              <button
                type="button"
                onClick={() => {
                  setAppliedFilters(draftFilters);
                  setPage(1);
                  setMobileFilterOpen(false);
                }}
                disabled={filtersLoading}
                className="h-9 bg-amber-400 hover:bg-amber-300 text-slate-950 font-bold text-xs rounded-lg shadow-xs flex items-center justify-center gap-1.5 transition-all active:scale-95"
              >
                <Filter className="w-3.5 h-3.5 text-slate-950" />
                <span>Terapkan</span>
              </button>
            </div>
          </div>
        )}

        {/* ========================================================= */}
        {/* DESKTOP & TABLET VIEW (>= md): Inline Compact Toolbar     */}
        {/* ========================================================= */}
        <div className="hidden md:flex flex-wrap lg:flex-nowrap items-center gap-2">
          {/* 1. Search Box Desktop */}
          <div className="relative flex-1 min-w-[160px] sm:min-w-[200px] lg:max-w-xs">
            <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none">
              <Search className="w-3.5 h-3.5" />
            </span>
            <input
              type="text"
              placeholder="Cari Batch, Mesin, Order..."
              value={draftFilters.search}
              onChange={(e) => setDraftFilters((prev) => ({ ...prev, search: e.target.value }))}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  setAppliedFilters(draftFilters);
                  setPage(1);
                }
              }}
              className="w-full h-8.5 pl-8 pr-7 py-1 text-xs border border-slate-200 rounded-lg bg-slate-50/60 focus:bg-white text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-amber-400 focus:border-amber-400 transition-all"
            />
            {draftFilters.search && (
              <button
                type="button"
                onClick={() => setDraftFilters((prev) => ({ ...prev, search: '' }))}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 p-0.5"
                title="Hapus kata kunci"
              >
                <X className="w-3 h-3" />
              </button>
            )}
          </div>

          {/* Divider */}
          <div className="hidden lg:block w-px h-5 bg-slate-200" />

          {/* 2. Unit Dropdown */}
          <div className="w-28 sm:w-32 shrink-0">
            <select
              value={draftFilters.group}
              onChange={(e) => {
                const next = e.target.value;
                setDraftFilters((prev) => ({ ...prev, group: next, machine: '' }));
              }}
              disabled={filtersLoading}
              className="w-full h-8.5 px-2 py-1 border border-slate-200 rounded-lg bg-slate-50/60 focus:bg-white text-xs font-semibold text-slate-800 focus:outline-none focus:ring-1 focus:ring-amber-400 focus:border-amber-400 disabled:opacity-60 transition-all cursor-pointer truncate"
              title="Filter Unit"
            >
              <option value="">Semua Unit</option>
              {filterOptions.groups.map((g) => (
                <option key={g.code} value={g.code}>
                  {g.code}
                </option>
              ))}
            </select>
          </div>

          {/* 3. Machine Dropdown */}
          <div className="w-28 sm:w-32 shrink-0">
            <select
              value={draftFilters.machine}
              onChange={(e) => setDraftFilters((prev) => ({ ...prev, machine: e.target.value }))}
              disabled={filtersLoading}
              className="w-full h-8.5 px-2 py-1 border border-slate-200 rounded-lg bg-slate-50/60 focus:bg-white text-xs font-semibold text-slate-800 focus:outline-none focus:ring-1 focus:ring-amber-400 focus:border-amber-400 disabled:opacity-60 transition-all cursor-pointer truncate"
              title="Filter Mesin"
            >
              <option value="">Semua Mesin</option>
              {machinesForSelectedGroup.map((m) => (
                <option key={m.code} value={m.code}>
                  {m.code || m.name}
                </option>
              ))}
            </select>
          </div>

          {/* Divider */}
          <div className="hidden lg:block w-px h-5 bg-slate-200" />

          {/* 4. Compact Date Range */}
          <div className="flex items-center gap-1 shrink-0">
            <input
              type="date"
              value={draftFilters.start_date}
              onChange={(e) => setDraftFilters((prev) => ({ ...prev, start_date: e.target.value }))}
              disabled={filtersLoading}
              title="Tanggal Mulai"
              className="h-8.5 px-2 py-1 border border-slate-200 rounded-lg bg-slate-50/60 focus:bg-white text-xs text-slate-700 focus:outline-none focus:ring-1 focus:ring-amber-400 focus:border-amber-400 disabled:opacity-60 transition-all w-28 sm:w-32"
            />
            <span className="text-[11px] font-semibold text-slate-400 select-none">s/d</span>
            <input
              type="date"
              value={draftFilters.end_date}
              onChange={(e) => setDraftFilters((prev) => ({ ...prev, end_date: e.target.value }))}
              disabled={filtersLoading}
              title="Tanggal Selesai"
              className="h-8.5 px-2 py-1 border border-slate-200 rounded-lg bg-slate-50/60 focus:bg-white text-xs text-slate-700 focus:outline-none focus:ring-1 focus:ring-amber-400 focus:border-amber-400 disabled:opacity-60 transition-all w-28 sm:w-32"
            />
          </div>

          {/* 5. Active Filter Indicator */}
          {activeFilterCount > 0 && (
            <span className="hidden xl:inline-flex items-center text-[10px] font-bold px-2 py-1 rounded-md bg-amber-50 text-amber-800 border border-amber-200/80 shrink-0">
              {activeFilterCount} Aktif
            </span>
          )}

          {/* 6. Action Buttons */}
          <div className="flex items-center gap-1.5 ml-auto shrink-0">
            {activeFilterCount > 0 && (
              <button
                type="button"
                onClick={() => {
                  setDraftFilters(defaultDraftFilters);
                  setAppliedFilters(defaultDraftFilters);
                  setPage(1);
                }}
                className="h-8.5 px-2.5 border border-slate-200 rounded-lg text-xs font-semibold text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition-colors flex items-center gap-1 cursor-pointer"
                title="Reset semua filter"
              >
                <RotateCcw className="w-3 h-3" />
                <span className="hidden sm:inline">Reset</span>
              </button>
            )}

            <button
              type="button"
              onClick={() => {
                setAppliedFilters(draftFilters);
                setPage(1);
              }}
              disabled={filtersLoading}
              className="h-8.5 px-3 bg-amber-400 hover:bg-amber-300 text-slate-950 font-bold text-xs rounded-lg shadow-2xs hover:shadow-xs transition-all active:scale-95 flex items-center gap-1 cursor-pointer disabled:opacity-60"
            >
              <Filter className="w-3 h-3 text-slate-950" />
              <span>Terapkan</span>
            </button>
          </div>
        </div>
      </div>

      {/* Table Container with Sticky Header & Pinned Pagination */}
      <div className="bg-white shadow-xs rounded-xl overflow-hidden border border-slate-200/90 flex-1 min-h-0 flex flex-col">
        {/* Table scroll area */}
        <div className="flex-1 min-h-0 overflow-x-auto overflow-y-auto table-scrollbar">
          {/* ========================================================= */}
          {/* DESKTOP & TABLET TABLE (hidden on mobile, table on md+)   */}
          {/* ========================================================= */}
          <table className="min-w-[1360px] w-full divide-y divide-slate-200 hidden md:table">
            <thead className="bg-slate-50 sticky top-0 z-20 border-b border-slate-200 shadow-2xs">
              <tr>
                <th className="sticky left-0 z-30 bg-slate-50 px-3 py-2 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider whitespace-nowrap border-r border-slate-200/80 shadow-[2px_0_5px_-2px_rgba(0,0,0,0.06)]">Mesin</th>
                <th className="px-3 py-2 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider whitespace-nowrap">Batch</th>
                <th className="px-3 py-2 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider whitespace-nowrap">Waktu Mulai</th>
                <th className="px-3 py-2 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider whitespace-nowrap">Efisiensi</th>
                <th className="px-3 py-2 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider whitespace-nowrap">Artikel</th>
                <th className="px-3 py-2 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider whitespace-nowrap">No Order</th>
                <th className="px-3 py-2 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider whitespace-nowrap">Warna</th>
                <th className="px-3 py-2 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider whitespace-nowrap">Program</th>
                <th className="px-3 py-2 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider whitespace-nowrap">Jenis Proses</th>
                <th className="px-3 py-2 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider whitespace-nowrap">Isi</th>
                <th className="px-3 py-2 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider whitespace-nowrap">Batch Kain</th>
                <th className="px-3 py-2 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider whitespace-nowrap">Operator</th>
                <th className="px-3 py-2 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider whitespace-nowrap">Durasi (m)</th>
                <th className="px-3 py-2 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider whitespace-nowrap">Peak Temp (&deg;C)</th>
                <th className="px-3 py-2 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider whitespace-nowrap">Steam (Bar)</th>
                <th className="px-3 py-2 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider whitespace-nowrap">Status</th>
                <th className="px-3 py-2 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider whitespace-nowrap">Anomali</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-slate-100">
              {loading ? (
                <tr><td colSpan="17" className="px-3 py-8 text-center text-slate-500 text-sm">Memuat data...</td></tr>
              ) : data.length === 0 ? (
                <tr><td colSpan="17" className="px-3 py-8 text-center text-slate-500 text-sm">Tidak ada riwayat ditemukan.</td></tr>
              ) : (
                data.map((row) => (
                  <tr
                    key={row.id}
                    onClick={() => openReport(row)}
                    className="group hover:bg-blue-50/70 cursor-pointer transition-colors"
                  >
                    <td className="sticky left-0 z-10 bg-white group-hover:bg-blue-50/70 px-3 py-2 whitespace-nowrap border-r border-slate-100 shadow-[2px_0_5px_-2px_rgba(0,0,0,0.06)] transition-colors">
                      <div className="text-xs font-bold text-slate-900">{row.machine_name}</div>
                    </td>
                    <td className="px-3 py-2 whitespace-nowrap text-xs font-semibold text-slate-800">#{row.batch_number}</td>
                    <td className="px-3 py-2 whitespace-nowrap text-xs text-slate-500">
                      {new Date(row.start_time).toLocaleString('id-ID')}
                    </td>
                    <td className="px-3 py-2 whitespace-nowrap">
                      {row.efficiency ? (
                        <span className={`px-2 inline-flex text-xs leading-5 font-bold rounded-full ${row.efficiency >= 80 ? 'bg-emerald-100 text-emerald-800' : row.efficiency >= 60 ? 'bg-yellow-100 text-yellow-800' : 'bg-rose-100 text-rose-800'}`}>
                          {row.efficiency}%
                        </span>
                      ) : <span className="text-slate-400">-</span>}
                    </td>
                    <td className="px-3 py-2 whitespace-nowrap text-xs text-slate-600">{row.artikel || '-'}</td>
                    <td className="px-3 py-2 whitespace-nowrap text-xs text-slate-600">{row.no_order || '-'}</td>
                    <td className="px-3 py-2 whitespace-nowrap text-xs text-slate-600">{row.warna || '-'}</td>
                    <td className="px-3 py-2 whitespace-nowrap text-xs text-slate-600">{row.program || '-'}</td>
                    <td className="px-3 py-2 whitespace-nowrap text-xs text-slate-600">{row.process || '-'}</td>
                    <td className="px-3 py-2 whitespace-nowrap text-xs text-slate-600">{row.isi || '-'}</td>
                    <td className="px-3 py-2 whitespace-nowrap text-xs text-slate-600">{row.batch_kain || '-'}</td>
                    <td className="px-3 py-2 whitespace-nowrap text-xs text-slate-600">{row.operator || '-'}</td>
                    <td className="px-3 py-2 whitespace-nowrap text-xs text-slate-600 font-mono">
                      {row.effective_duration ? row.effective_duration : '-'}
                    </td>
                    <td className="px-3 py-2 whitespace-nowrap text-xs text-slate-900 font-bold font-mono">
                      {row.max_temp ? `${row.max_temp}°C` : '-'}
                    </td>
                    <td className="px-3 py-2 whitespace-nowrap text-xs text-slate-600 font-mono">
                      {row.avg_steam_pressure !== null ? row.avg_steam_pressure : '-'}
                    </td>
                    <td className="px-3 py-2 whitespace-nowrap">
                      <ProcessStatusBadge isComplete={row.is_complete} thermalStatus={row.thermal_status} />
                    </td>
                    <td className="px-3 py-2 whitespace-nowrap">
                      {row.anomaly_types && row.anomaly_types.length > 0 ? (
                        <span className="text-[10px] font-bold text-rose-700 bg-rose-50 border border-rose-100 px-1.5 py-0.5 rounded tracking-tight">
                          {row.anomaly_types.join(', ')}
                        </span>
                      ) : (
                        <span className="text-slate-400">-</span>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>

          {/* ========================================================= */}
          {/* MOBILE CARDS VIEW (< md): Modern, Touch-Friendly Cards   */}
          {/* ========================================================= */}
          <div className="md:hidden divide-y divide-slate-100 bg-white">
            {loading ? (
              <div className="p-6 text-center text-slate-500 text-sm">Memuat data...</div>
            ) : data.length === 0 ? (
              <div className="p-8 text-center text-slate-400 text-sm flex flex-col items-center justify-center gap-2">
                <Search className="w-8 h-8 text-slate-300" />
                <span>Tidak ada riwayat batch ditemukan.</span>
              </div>
            ) : (
              data.map((row) => {
                const startTimeFormatted = row.start_time
                  ? new Date(row.start_time).toLocaleString('id-ID', {
                      day: 'numeric',
                      month: 'short',
                      hour: '2-digit',
                      minute: '2-digit',
                    })
                  : '-';

                const effColor =
                  row.efficiency >= 80
                    ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                    : row.efficiency >= 60
                    ? 'bg-amber-50 text-amber-700 border-amber-200'
                    : 'bg-rose-50 text-rose-700 border-rose-200';

                return (
                  <div
                    key={row.id}
                    onClick={() => openReport(row)}
                    className="p-3 sm:p-3.5 hover:bg-slate-50 active:bg-blue-50/60 cursor-pointer transition-colors flex flex-col gap-2"
                  >
                    {/* Top Header: Machine, Batch, Status, Efficiency */}
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2 min-w-0">
                        <ProcessStatusIcon
                          isComplete={row.is_complete}
                          thermalStatus={row.thermal_status}
                          size="sm"
                        />
                        <span className="text-sm font-bold text-slate-900 tracking-tight truncate">
                          {row.machine_name}
                        </span>
                        <span className="text-xs font-mono font-bold px-2 py-0.5 rounded-md bg-blue-50 text-blue-700 border border-blue-200/60 shrink-0">
                          #{row.batch_number}
                        </span>
                      </div>

                      {/* Efficiency Pill */}
                      {row.efficiency ? (
                        <span className={`text-xs font-bold px-2 py-0.5 rounded-full border shrink-0 ${effColor}`}>
                          {row.efficiency}%
                        </span>
                      ) : (
                        <span className="text-xs text-slate-400 font-medium shrink-0">-</span>
                      )}
                    </div>

                    {/* Middle Info Panel: Warna, Artikel, No Order, Program, Operator */}
                    <div className="flex flex-col gap-1 text-xs text-slate-600 bg-slate-50/80 p-2 sm:p-2.5 rounded-lg border border-slate-100">
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-semibold text-slate-900 truncate">
                          {row.warna || 'Tanpa Warna'}
                        </span>
                        <span className="text-[11px] text-slate-500 font-mono shrink-0">
                          {row.artikel ? `Art. ${row.artikel}` : ''}
                          {row.no_order ? ` • ${row.no_order}` : ''}
                        </span>
                      </div>

                      <div className="flex items-center justify-between text-[11px] text-slate-500 pt-0.5">
                        <span className="truncate">
                          {row.program || '-'} • {row.process || '-'}
                        </span>
                        {row.operator && (
                          <span className="shrink-0 text-slate-600">
                            Op: <b className="font-semibold text-slate-700">{row.operator}</b>
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Bottom Row: Waktu Mulai, Durasi, Temp, Steam */}
                    <div className="flex items-center justify-between text-[11px] text-slate-500 pt-0.5">
                      <div className="flex items-center gap-1.5 truncate">
                        <span>{startTimeFormatted}</span>
                        {row.effective_duration && (
                          <>
                            <span className="text-slate-300">•</span>
                            <span className="font-medium text-slate-600">{row.effective_duration}</span>
                          </>
                        )}
                      </div>

                      <div className="flex items-center gap-2 shrink-0 font-mono text-[11px]">
                        {row.max_temp && (
                          <span className="font-bold text-slate-800">
                            {row.max_temp}°C
                          </span>
                        )}
                        {row.avg_steam_pressure !== null && (
                          <span className="text-slate-600">
                            {row.avg_steam_pressure} bar
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Anomalies Alert Banner (jika terdeteksi anomali) */}
                    {row.anomaly_types && row.anomaly_types.length > 0 && (
                      <div className="mt-0.5">
                        <span className="inline-flex items-center text-[10px] font-bold text-rose-700 bg-rose-50 border border-rose-200/80 px-2 py-0.5 rounded-md">
                          ⚠️ {row.anomaly_types.join(', ')}
                        </span>
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Pinned Bottom Pagination Controls (Responsive Mobile & Desktop) */}
        <div className="shrink-0 px-3 py-2 sm:px-5 border-t border-slate-200/90 flex items-center justify-between bg-white rounded-b-xl gap-2">
          <div className="text-[11px] sm:text-xs text-slate-500 font-medium truncate">
            {totalCount > 0 ? (
              <span>
                <span className="hidden sm:inline">Menampilkan </span>
                <b className="text-slate-800 font-semibold">{(page - 1) * 10 + 1}</b>-
                <b className="text-slate-800 font-semibold">{Math.min(page * 10, totalCount)}</b>
                <span className="hidden sm:inline"> dari <b className="text-slate-800 font-semibold">{totalCount}</b></span>
                <span className="sm:hidden"> / {totalCount}</span>
              </span>
            ) : (
              <span>Hal {page} / {totalPages || 1}</span>
            )}
          </div>
          <div className="flex items-center gap-1 sm:gap-1.5 shrink-0">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1 || loading}
              className={`p-1.5 rounded-lg flex items-center justify-center transition-all ${
                page === 1 || loading
                  ? 'text-slate-300 bg-slate-50 cursor-not-allowed'
                  : 'text-slate-700 bg-white hover:bg-slate-100 border border-slate-200 shadow-2xs cursor-pointer active:scale-95'
              }`}
              title="Halaman Sebelumnya"
            >
              <ChevronLeft size={16} />
            </button>
            <span className="text-xs font-bold text-slate-700 px-1.5 sm:px-2 min-w-[44px] text-center">
              {page} / {totalPages || 1}
            </span>
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page === totalPages || loading}
              className={`p-1.5 rounded-lg flex items-center justify-center transition-all ${
                page === totalPages || loading
                  ? 'text-slate-300 bg-slate-50 cursor-not-allowed'
                  : 'text-slate-700 bg-white hover:bg-slate-100 border border-slate-200 shadow-2xs cursor-pointer active:scale-95'
              }`}
              title="Halaman Berikutnya"
            >
              <ChevronRight size={16} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default HistoryList;
