import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { createPortal } from 'react-dom';

import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

import { default as api, legacyApi } from '../lib/api';

import {

  LineChart,

  Line,

  XAxis,

  YAxis,

  CartesianGrid,

  Tooltip,

  Legend,

  ResponsiveContainer

} from 'recharts';

import {

  Gauge,

  Flame,

  Clock,

  Snowflake,

  Hourglass,

  CheckCircle2,

  RotateCw,

  Search,

  X,

  Building2,

  ShieldAlert,

  Activity,

  ChevronRight,

} from 'lucide-react';

const getCurrentShiftLabel = () => {
  const h = new Date().getHours();
  if (h >= 6 && h < 14) return 'Shift 1 - Pagi';
  if (h >= 14 && h < 22) return 'Shift 2 - Siang';
  return 'Shift 3 - Malam';
};

const getCurrentDateLabel = () => {
  try {
    return new Date().toLocaleDateString('id-ID', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
    }) + ' · ' + new Date().toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' }) + ' WIB';
  } catch (e) {
    return '';
  }
};

export default function Home() {
  const navigate = useNavigate();

  const { user } = useAuth();

  // State telemetri utama

  const [data, setData] = useState(null);

  const [loading, setLoading] = useState(true);

  const [isRefreshing, setIsRefreshing] = useState(false);

  const [error, setError] = useState(null);

  const [lastSyncTime, setLastSyncTime] = useState(new Date());

  // Filter & Search

  const [searchTerm, setSearchTerm] = useState('');

  const [statusFilter, setStatusFilter] = useState('all');

  // Modal Detail SCADA

  const [selectedMachine, setSelectedMachine] = useState(null);

  const [modalHours, setModalHours] = useState(null);

  const [modalChartData, setModalChartData] = useState(null);

  const [modalChartLoading, setModalChartLoading] = useState(false);
  const [modalChartError, setModalChartError] = useState(null);

  // Kunci scroll body saat modal aktif agar popup tidak terpengaruh scroll latar
  useEffect(() => {
    if (selectedMachine) {
      const prev = document.body.style.overflow;
      document.body.style.overflow = 'hidden';
      return () => {
        document.body.style.overflow = prev;
      };
    }
  }, [selectedMachine]);

  // 1. Fetch data dari /api/home-korlap/

  // BEBAS INFINITE LOOP: dependensi kosong [] agar fungsi stabil dan tidak memicu render berulang

  const fetchHomeData = useCallback(async (isSilent = false) => {

    if (!isSilent) setIsRefreshing(true);

    try {

      const resp = await legacyApi.get('/home-korlap/', { cache: isSilent });

      if (resp.data && typeof resp.data === 'object' && resp.data.group_panels) {

        setData(resp.data);

        setLastSyncTime(new Date());

        setError(null);

      } else {

        console.warn('Format respons tidak valid:', resp.data);

        setError('Format telemetri tidak valid atau sesi login kedaluwarsa.');

      }

    } catch (err) {

      console.error('Error fetching home-korlap data:', err);

      setError('Gagal memuat telemetri lini produksi.');

    } finally {

      setLoading(false);

      setIsRefreshing(false);

    }

  }, []);

  // HANYA ambil data saat masuk ke laman ini dan saat tab browser kembali aktif

  // TIDAK ADA auto-refresh polling interval (hemat kuota total)

  useEffect(() => {

    fetchHomeData();

    const handleVisibilityChange = () => {

      if (!document.hidden) {

        fetchHomeData(true);

      }

    };

    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => document.removeEventListener('visibilitychange', handleVisibilityChange);

  }, [fetchHomeData]);

  // 2. Fetch data grafik detail SCADA (Suhu vs Pressure)

  // Default: dari awal proses jika ada batch aktif; 2 jam jika standby

  const fetchModalChart = useCallback(async (machineId, hours) => {
    if (!machineId) return;
    setModalChartLoading(true);
    setModalChartError(null);
    try {
      const url = (hours && hours > 0)
        ? `/dashboard/machine/${machineId}/detail?hours=${hours}`
        : `/dashboard/machine/${machineId}/detail`;
      const resp = await api.get(url, { cache: false });
      setModalChartData(resp.data);
    } catch (err) {
      console.error('Error fetching modal chart:', err);
      setModalChartError(err.response?.data?.message || err.message || 'Gagal memuat telemetri sensor.');
      setModalChartData(null);

    } finally {

      setModalChartLoading(false);

    }

  }, []);

  const openTelemetryModal = (machine) => {

    setSelectedMachine(machine);

    const initialRange = machine.has_active_batch ? null : 2;

    setModalHours(initialRange);

    fetchModalChart(machine.id, initialRange);

  };

  const closeTelemetryModal = () => {

    setSelectedMachine(null);

    setModalChartData(null);

  };

  const handleRangeChange = (h) => {

    setModalHours(h);

    if (selectedMachine) {

      fetchModalChart(selectedMachine.id, h);

    }

  };

  // Keyboard shortcut ESC

  useEffect(() => {

    const handleKeyDown = (e) => {

      if (e.key === 'Escape') {

        if (selectedMachine) {

          closeTelemetryModal();

        } else if (searchTerm) {

          setSearchTerm('');

        }

      }

    };

    window.addEventListener('keydown', handleKeyDown);

    return () => window.removeEventListener('keydown', handleKeyDown);

  }, [selectedMachine, searchTerm]);

  // Smooth scroll ke grup Hall

  const scrollToHall = (grpCode) => {

    const cleanId = `section-${String(grpCode || '').toLowerCase().replace(/\s+/g, '-')}`;

    const el = document.getElementById(cleanId);

    if (el) {

      el.scrollIntoView({ behavior: 'smooth', block: 'start' });

    }

  };

  // 3. Filter data berdasarkan kata kunci & chip status

  const filteredGroups = useMemo(() => {

    if (!data || !data.group_panels) return [];

    const query = searchTerm.toLowerCase().trim();

    return data.group_panels

      .map((grp) => {

        const filteredMachines = grp.machines.filter((m) => {

          // Status filter

          const status = (m.status || 'OFF').toUpperCase();

          if ((statusFilter === 'run' || statusFilter === 'running') && status !== 'RUNNING') return false;

          if (statusFilter === 'heat' && status !== 'HEAT') return false;

          if (statusFilter === 'steady' && status !== 'STEADY') return false;

          if (statusFilter === 'cool' && status !== 'COOL') return false;

          if ((statusFilter === 'off' || statusFilter === 'mati') && status !== 'OFF' && status !== 'STOP') return false;

          // Search term filter

          if (!query) return true;

          const matchCode = String(m.code || '').toLowerCase().includes(query);

          const matchName = String(m.name || '').toLowerCase().includes(query);

          const matchBatch = String(m.batch_number || '').toLowerCase().includes(query);

          const matchArtikel = String(m.artikel_kain || '').toLowerCase().includes(query);

          const matchProg = String(m.program_name || '').toLowerCase().includes(query);

          const matchOrder = String(m.nomor_order || '').toLowerCase().includes(query);

          return matchCode || matchName || matchBatch || matchArtikel || matchProg || matchOrder;

        });

                // Urutkan ascending berdasarkan kode mesin (misal: JD_01 paling atas ke JD_19 paling bawah)
        const sortedMachines = [...filteredMachines].sort((a, b) => {
          return (a.code || '').localeCompare(b.code || '', undefined, {
            numeric: true,
            sensitivity: 'base',
          });
        });

        return {
          ...grp,
          machines: sortedMachines,
        };

      })

      .filter((grp) => grp.machines.length > 0);

  }, [data, searchTerm, statusFilter]);

  const totalVisibleMachines = useMemo(() => {

    return filteredGroups.reduce((acc, g) => acc + g.machines.length, 0);

  }, [filteredGroups]);

  // Loading Skeleton (Gojek / Modern Moving Gradient Shimmer)
  if (loading && !data) {
    return (
      <div className="bg-slate-50 min-h-screen flex flex-col gap-4 pb-12">
        {/* TOP HUD SKELETON */}
        <header className="sticky top-0 z-30 bg-white/95 backdrop-blur-md border-b border-slate-200/90 shadow-2xs">
          <div className="min-h-[60px] py-2 sm:py-0 sm:h-16 px-3 sm:px-6 flex items-center justify-between gap-3">
            {/* Mobile (< md): 2 Cards (UAP & HTO) */}
            <div className="grid grid-cols-2 md:hidden gap-2 w-full py-0.5">
              <div className="bg-sky-50/70 border border-sky-100 rounded-xl px-2.5 py-2 flex flex-col justify-between gap-2 shadow-2xs">
                <div className="flex items-center justify-between">
                  <div className="w-12 h-3.5 rounded skeleton-shimmer" />
                  <div className="w-10 h-3.5 rounded skeleton-shimmer" />
                </div>
                <div className="flex items-baseline justify-between gap-1 mt-0.5">
                  <div className="w-16 h-5 rounded skeleton-shimmer" />
                  <div className="w-12 h-3 rounded skeleton-shimmer" />
                </div>
              </div>
              <div className="bg-amber-50/70 border border-amber-100 rounded-xl px-2.5 py-2 flex flex-col justify-between gap-2 shadow-2xs">
                <div className="flex items-center justify-between">
                  <div className="w-12 h-3.5 rounded skeleton-shimmer" />
                  <div className="w-10 h-3.5 rounded skeleton-shimmer" />
                </div>
                <div className="flex items-baseline justify-between gap-1 mt-0.5">
                  <div className="w-16 h-5 rounded skeleton-shimmer" />
                  <div className="w-12 h-3 rounded skeleton-shimmer" />
                </div>
              </div>
            </div>

            {/* Desktop (>= md): Shift Info & Badges */}
            <div className="hidden md:flex items-center gap-3">
              <div className="w-32 h-8 rounded-full skeleton-shimmer" />
              <div className="w-40 h-5 rounded skeleton-shimmer" />
            </div>
            <div className="hidden md:flex items-center gap-2.5">
              <div className="w-52 h-8 rounded-full skeleton-shimmer" />
              <div className="w-52 h-8 rounded-full skeleton-shimmer" />
            </div>
          </div>
        </header>

        {/* MAIN BODY SKELETON */}
        <main className="px-3.5 sm:px-6 flex flex-col gap-4 max-w-7xl mx-auto w-full">
          {/* Quick Filter Bar Skeleton */}
          <div className="flex items-center justify-between gap-2 overflow-x-auto pb-1 pt-1">
            <div className="flex items-center gap-2">
              <div className="w-20 h-7 rounded-full skeleton-shimmer" />
              <div className="w-24 h-7 rounded-full skeleton-shimmer" />
              <div className="w-24 h-7 rounded-full skeleton-shimmer" />
              <div className="w-20 h-7 rounded-full skeleton-shimmer" />
            </div>
            <div className="w-28 h-7 rounded-full skeleton-shimmer hidden sm:block" />
          </div>

          {/* Machine Group Section Banner Skeleton */}
          <div className="relative overflow-hidden rounded-xl sm:rounded-2xl px-3.5 py-2.5 sm:px-5 sm:py-3.5 flex items-center justify-between gap-3 shadow-md border border-blue-900/40 bg-gradient-to-r from-[#071329] via-[#0d244c] to-[#081630]">
            <div className="flex items-center gap-3 min-w-0 z-10">
              <div className="w-8 h-8 sm:w-9 sm:h-9 rounded-xl skeleton-shimmer-dark shrink-0" />
              <div className="flex items-center gap-2">
                <div className="w-36 sm:w-48 h-4 rounded skeleton-shimmer-dark" />
                <div className="w-14 h-4 rounded-full skeleton-shimmer-dark" />
              </div>
            </div>
            <div className="w-24 h-6 rounded-full skeleton-shimmer-dark z-10 shrink-0" />
          </div>

          {/* Machine Cards Grid Skeleton (6 Cards) */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3.5">
            {[1, 2, 3, 4, 5, 6].map((i) => (
              <div
                key={i}
                className="bg-white rounded-xl border border-slate-200/90 p-3 sm:p-3.5 shadow-xs flex flex-col justify-between gap-3 relative overflow-hidden"
              >
                {/* Left Colored Accent Bar Skeleton */}
                <div className="absolute left-0 top-0 bottom-0 w-1.5 skeleton-shimmer rounded-l-xl" />

                <div className="pl-1.5 flex flex-col gap-2.5">
                  {/* Row 1: Sparkline Left + Metrics Right */}
                  <div className="flex items-start gap-2.5">
                    {/* Micro-chart Thumbnail Box */}
                    <div className="w-28 sm:w-32 h-[68px] rounded-lg skeleton-shimmer shrink-0" />

                    {/* Metrics Skeleton */}
                    <div className="flex-1 flex flex-col justify-between h-[68px] py-0.5">
                      <div className="flex items-baseline justify-between gap-1">
                        <div className="w-14 h-3 rounded skeleton-shimmer" />
                        <div className="w-12 h-5 rounded skeleton-shimmer" />
                      </div>
                      <div className="flex items-baseline justify-between gap-1">
                        <div className="w-10 h-3 rounded skeleton-shimmer" />
                        <div className="w-10 h-4 rounded skeleton-shimmer" />
                      </div>
                      <div className="flex items-center justify-between gap-1">
                        <div className="w-16 h-3 rounded skeleton-shimmer" />
                        <div className="w-8 h-3 rounded skeleton-shimmer" />
                      </div>
                    </div>
                  </div>

                  {/* Row 2: Status Phase Banner Skeleton */}
                  <div className="h-6 rounded-lg skeleton-shimmer" />

                  {/* Row 3: Bottom Batch Info & Rounded Detail Button */}
                  <div className="pt-2 border-t border-slate-100 flex items-center justify-between gap-2">
                    <div className="flex items-center gap-1.5 min-w-0">
                      <div className="w-12 h-4 rounded skeleton-shimmer shrink-0" />
                      <div className="w-20 sm:w-28 h-4 rounded skeleton-shimmer truncate" />
                    </div>
                    {/* Rounded Detail Pill Button Skeleton */}
                    <div className="w-20 h-6 sm:h-7 rounded-full skeleton-shimmer shrink-0" />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </main>
      </div>
    );
  }

  // Error State

  if (error && !data) {

    return (

      <div className="min-h-screen bg-slate-50 flex items-center justify-center p-6">

        <div className="max-w-md w-full bg-white rounded-2xl shadow-sm border border-slate-200 p-6 text-center">

          <ShieldAlert className="w-10 h-10 text-rose-500 mx-auto mb-3" />

          <h3 className="text-base font-bold text-slate-900 mb-1">Gagal Memuat Telemetri</h3>

          <p className="text-xs text-slate-500 mb-4">{error}</p>

          <button

            onClick={() => fetchHomeData(false)}

            className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold shadow-xs"

          >

            Coba Lagi

          </button>

        </div>

      </div>

    );

  }

  const counts = data?.status_counts || { running: 0, heat: 0, steady: 0, cool: 0, off: 0, nosignal: 0 };

  const steam = data?.steam_pressure !== null && data?.steam_pressure !== undefined ? data.steam_pressure : '-';

  const steamUsage = data?.steam_usage || '0,0 ton/jam';

  const steamMcCount = data?.steam_mc_count ?? 0;

  const hto = data?.oil_temp !== null && data?.oil_temp !== undefined ? data.oil_temp : '-';

  const htoUsage = data?.hto_usage || '0,0 jt kcal';

  const htoMcCount = data?.hto_mc_count ?? 0;

  return (

    <div className="bg-slate-50 text-slate-800 min-h-screen w-full font-sans antialiased pb-16 animate-fade-in">

      {/* =========================================================================

          1. COMPACT TOP HUD (PLANT TELEMETRY CORE)

             - Indikator Uap & HTO lengkap: Tekanan/Suhu · Pemakaian · Jumlah MC

             - Tombol manual refresh dihapus (cukup refresh browser)

          ========================================================================= */}

      <header className="sticky top-0 z-30 bg-white/95 backdrop-blur-md border-b border-slate-200/90 shadow-2xs">

        <div className="min-h-[60px] py-1.5 sm:py-0 sm:h-16 px-2.5 sm:px-6 flex items-center justify-between gap-2 sm:gap-4">

          {/* TAMPILAN KHUSUS HP (< md): Indikator Uap & HTO berbentuk Card 2 Kolom (Tanpa Scroll Horizontal, Font Lebih Besar & Mudah Dibaca) */}
          <div className="grid grid-cols-2 md:hidden gap-2 w-full py-0.5">
            {/* Card Uap */}
            <div onClick={() => navigate('/boiler-steam')} className="bg-sky-50/95 border border-sky-200/90 rounded-xl px-2.5 py-1.5 flex flex-col justify-between shadow-2xs cursor-pointer hover:border-sky-300 active:scale-98 transition-all">
              <div className="flex items-center justify-between gap-1 leading-none">
                <div className="flex items-center gap-1 text-sky-900 font-bold text-xs tracking-wide">
                  <Gauge className="w-3.5 h-3.5 text-sky-600 shrink-0" />
                  <span>UAP</span>
                </div>
                <span className="text-[11px] font-bold text-sky-700 bg-sky-100/90 border border-sky-200/60 px-1.5 py-0.5 rounded leading-none">
                  {steamMcCount} MC
                </span>
              </div>
              <div className="flex items-baseline justify-between gap-1 mt-1">
                <div className="flex items-baseline gap-0.5">
                  <span className="text-base font-black text-slate-900 tabular-nums font-mono leading-none">
                    {steam}
                  </span>
                  <span className="text-[10px] font-semibold text-slate-500">bar</span>
                </div>
                <span className="text-[11px] font-bold text-sky-800 tabular-nums truncate">
                  {steamUsage}
                </span>
              </div>
            </div>

            {/* Card HTO */}
            <div onClick={() => navigate('/boiler-hto')} className="bg-amber-50/95 border border-amber-200/90 rounded-xl px-2.5 py-1.5 flex flex-col justify-between shadow-2xs cursor-pointer hover:border-amber-300 active:scale-98 transition-all">
              <div className="flex items-center justify-between gap-1 leading-none">
                <div className="flex items-center gap-1 text-amber-900 font-bold text-xs tracking-wide">
                  <Flame className="w-3.5 h-3.5 text-amber-600 shrink-0" />
                  <span>HTO</span>
                </div>
                <span className="text-[11px] font-bold text-amber-700 bg-amber-100/90 border border-amber-200/60 px-1.5 py-0.5 rounded leading-none">
                  {htoMcCount} MC
                </span>
              </div>
              <div className="flex items-baseline justify-between gap-1 mt-1">
                <div className="flex items-baseline gap-0.5">
                  <span className="text-base font-black text-slate-900 tabular-nums font-mono leading-none">
                    {hto}
                  </span>
                  <span className="text-[10px] font-semibold text-slate-500">°C</span>
                </div>
                <span className="text-[11px] font-bold text-amber-800 tabular-nums truncate">
                  {htoUsage}
                </span>
              </div>
            </div>
          </div>

          {/* TAMPILAN DESKTOP (>= md): Shift & Live Time di Kiri */}

          <div className="hidden md:flex items-center gap-3 shrink-0">

            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-slate-100 text-slate-700 text-xs font-semibold">

              <Clock className="w-3.5 h-3.5 text-slate-500" />

              <span>{data?.shift_name || getCurrentShiftLabel()}</span>

            </div>

            <div className="hidden lg:flex items-center gap-1.5 text-xs text-slate-500 font-medium">

              <span>{data?.now || getCurrentDateLabel()}</span>

            </div>

          </div>

          {/* TAMPILAN DESKTOP: Indikator Utilitas Uap & HTO lengkap dengan ton/jam, jt kcal & jumlah MC */}

          <div className="hidden md:flex items-center gap-2.5">

            <div onClick={() => navigate('/boiler-steam')} className="flex items-center gap-1.5 bg-sky-50 text-sky-900 border border-sky-200/90 px-3.5 py-1.5 rounded-full text-xs font-semibold shadow-2xs cursor-pointer hover:bg-sky-100/80 hover:border-sky-300 active:scale-98 transition-all" title="Klik untuk membuka Boiler Steam Dashboard">

              <Gauge className="w-3.5 h-3.5 text-sky-600 shrink-0" />

              <span className="text-slate-500 font-medium">Uap:</span>

              <span className="tabular-nums font-bold">{steam}</span>

              <span className="text-[10px] text-slate-500 font-normal">bar</span>

              <span className="text-slate-300 mx-0.5">·</span>

              <span className="text-[11px] font-bold text-sky-700">{steamUsage}</span>

              <span className="text-slate-300 mx-0.5">·</span>

              <span className="text-[11px] font-bold text-sky-800">{steamMcCount} MC</span>

            </div>

            <div onClick={() => navigate('/boiler-hto')} className="flex items-center gap-1.5 bg-amber-50 text-amber-900 border border-amber-200/90 px-3.5 py-1.5 rounded-full text-xs font-semibold shadow-2xs cursor-pointer hover:bg-amber-100/80 hover:border-amber-300 active:scale-98 transition-all" title="Klik untuk membuka Boiler HTO Dashboard">

              <Flame className="w-3.5 h-3.5 text-amber-600 shrink-0" />

              <span className="text-slate-500 font-medium">HTO:</span>

              <span className="tabular-nums font-bold">{hto}</span>

              <span className="text-[10px] text-slate-500 font-normal">°C</span>

              <span className="text-slate-300 mx-0.5">·</span>

              <span className="text-[11px] font-bold text-amber-700">{htoUsage}</span>

              <span className="text-slate-300 mx-0.5">·</span>

              <span className="text-[11px] font-bold text-amber-800">{htoMcCount} MC</span>

            </div>

          </div>

        </div>

      </header>

      {/* =========================================================================

          2. FILTER & STICKY CONTROLS TRAY

          ========================================================================= */}

      <section className="bg-white border-b border-slate-200/80 px-4 sm:px-6 py-2.5 shadow-2xs">

        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-2.5">

          {/* Left: Input Pencarian & Hall Jump Shortcuts */}

          <div className="flex flex-wrap items-center gap-2">

            <div className="relative w-full sm:w-64">

              <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2.5" />

              <input

                type="text"

                value={searchTerm}

                onChange={(e) => setSearchTerm(e.target.value)}

                placeholder="Cari mesin, batch, kain... (ESC)"

                className="w-full text-xs pl-8 pr-7 py-1.5 rounded-lg border border-slate-200 bg-slate-50/60 text-slate-800 placeholder-slate-400 focus:bg-white focus:outline-none focus:ring-1 focus:ring-blue-500 transition-all"

              />

              {searchTerm && (

                <button

                  onClick={() => setSearchTerm('')}

                  className="absolute right-2 top-2 text-slate-400 hover:text-slate-600"

                >

                  <X className="w-3.5 h-3.5" />

                </button>

              )}

            </div>

            <div className="flex items-center gap-1 overflow-x-auto hide-scrollbar py-0.5">

              {data?.group_panels?.map((grp) => (

                <button

                  key={grp.code}

                  onClick={() => scrollToHall(grp.code)}

                  className="text-[11px] font-semibold px-2 py-1 rounded-md bg-slate-100 hover:bg-slate-200 text-slate-700 transition-colors shrink-0"

                >

                  {grp.code}

                </button>

              ))}

            </div>

          </div>

          {/* Right: State Category Filter Chips */}

          <div className="flex items-center gap-1.5 overflow-x-auto hide-scrollbar py-0.5">
            <button
              onClick={() => setStatusFilter('all')}
              className={`px-2.5 py-1 rounded-md text-xs font-semibold transition-all shrink-0 ${
                statusFilter === 'all'
                  ? 'bg-slate-900 text-white shadow-2xs'
                  : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
              }`}
            >
              All ({data?.total_machines || 0})
            </button>

            <button
              onClick={() => setStatusFilter('run')}
              className={`px-2.5 py-1 rounded-md text-xs font-semibold transition-all shrink-0 flex items-center gap-1.5 ${
                statusFilter === 'run' || statusFilter === 'running'
                  ? 'bg-emerald-600 text-white shadow-2xs'
                  : 'bg-emerald-50 text-emerald-700 hover:bg-emerald-100'
              }`}
            >
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
              <span>Run ({counts.running})</span>
            </button>

            <button
              onClick={() => setStatusFilter('heat')}
              className={`px-2.5 py-1 rounded-md text-xs font-semibold transition-all shrink-0 flex items-center gap-1.5 ${
                statusFilter === 'heat'
                  ? 'bg-rose-600 text-white shadow-2xs'
                  : 'bg-rose-50 text-rose-700 hover:bg-rose-100'
              }`}
            >
              <span className="w-1.5 h-1.5 rounded-full bg-rose-500"></span>
              <span>Heat ({counts.heat})</span>
            </button>

            <button
              onClick={() => setStatusFilter('steady')}
              className={`px-2.5 py-1 rounded-md text-xs font-semibold transition-all shrink-0 flex items-center gap-1.5 ${
                statusFilter === 'steady'
                  ? 'bg-blue-600 text-white shadow-2xs'
                  : 'bg-blue-50 text-blue-700 hover:bg-blue-100'
              }`}
            >
              <span className="w-1.5 h-1.5 rounded-full bg-blue-500"></span>
              <span>Steady ({counts.steady})</span>
            </button>

            <button
              onClick={() => setStatusFilter('cool')}
              className={`px-2.5 py-1 rounded-md text-xs font-semibold transition-all shrink-0 flex items-center gap-1.5 ${
                statusFilter === 'cool'
                  ? 'bg-sky-600 text-white shadow-2xs'
                  : 'bg-sky-50 text-sky-700 hover:bg-sky-100'
              }`}
            >
              <span className="w-1.5 h-1.5 rounded-full bg-sky-500"></span>
              <span>Cool ({counts.cool})</span>
            </button>

            <button
              onClick={() => setStatusFilter('off')}
              className={`px-2.5 py-1 rounded-md text-xs font-semibold transition-all shrink-0 flex items-center gap-1.5 ${
                statusFilter === 'off' || statusFilter === 'mati'
                  ? 'bg-slate-700 text-white shadow-2xs'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              <span className="w-1.5 h-1.5 rounded-full bg-slate-400"></span>
              <span>Off ({counts.off})</span>
            </button>
          </div>

        </div>

      </section>

      {/* =========================================================================

          3. MAIN CONTENT: HALL SECTIONS & CARDS (PERSIS GAMBAR 1)

             CAPTION PANJANG DIHAPUS, DIGANTI "X/Y Mesin Dipantau"

          ========================================================================= */}

      <main className="p-4 sm:p-6 flex flex-col gap-6 max-w-[1600px] mx-auto">

        {totalVisibleMachines === 0 && (

          <div className="w-full p-10 text-center bg-white rounded-xl border border-dashed border-slate-300 flex flex-col items-center justify-center gap-2">

            <Search className="w-8 h-8 text-slate-400" />

            <h4 className="text-sm font-bold text-slate-800">Tidak Ada Mesin yang Cocok</h4>

            <p className="text-xs text-slate-500">

              Coba gunakan kata kunci pencarian lain atau pilih filter status "All".

            </p>

          </div>

        )}

        {filteredGroups.map((group, groupIdx) => {

          const sectionId = `section-${String(group?.code || '').toLowerCase().replace(/\s+/g, '-')}`;

          const syncedCount = group.synced_count ?? group.machines.length;

          const totalCount = group.total_count ?? group.machines.length;

          return (

            <section key={group.code} id={sectionId} className={`flex flex-col gap-3 ${groupIdx > 0 ? 'pt-6 sm:pt-8' : ''}`}>

              {/* Garis Pembatas Tegas Sebelum Machine Group (Kecuali Group Pertama) */}
              {groupIdx > 0 && (
                <div className="border-t-2 border-slate-200/90 -mb-1" />
              )}

              {/* Hall Section Header Banner: Gradasi Mewah & Elegan sebagai Pembatas Group Mesin */}
              <div className="relative overflow-hidden rounded-xl sm:rounded-2xl px-3.5 py-2.5 sm:px-5 sm:py-3.5 flex items-center justify-between gap-3 shadow-md border border-blue-900/50 bg-gradient-to-r from-[#071329] via-[#0d244c] to-[#081630]">
                {/* Glow ambient background wave effect */}
                <div className="absolute -right-8 -top-8 w-44 h-44 bg-blue-500/15 rounded-full blur-2xl pointer-events-none" />
                <div className="absolute left-1/3 -bottom-8 w-36 h-36 bg-indigo-500/10 rounded-full blur-2xl pointer-events-none" />

                <div className="flex items-center gap-2.5 sm:gap-3.5 min-w-0 z-10">
                  <div className="w-8 h-8 sm:w-9 sm:h-9 rounded-xl bg-gradient-to-br from-blue-500 to-blue-700 text-white flex items-center justify-center border border-blue-400/40 shadow-sm shrink-0">
                    <Building2 className="w-4 h-4 sm:w-5 sm:h-5 text-white" />
                  </div>

                  <div className="flex items-center gap-2 flex-wrap min-w-0">
                    <h3 className="text-sm sm:text-base font-extrabold text-white tracking-tight truncate">
                      {group.name}
                    </h3>
                    <span className="px-2.5 py-0.5 rounded-full text-[11px] font-mono font-bold bg-blue-500/20 text-blue-300 border border-blue-400/30 shrink-0 shadow-2xs">
                      {group.code}
                    </span>
                  </div>
                </div>

                {/* Badge Jumlah Mesin Dipantau */}
                <div className="shrink-0 flex items-center z-10">
                  <div className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-slate-900/80 border border-blue-500/30 text-xs font-semibold text-slate-200 shadow-sm backdrop-blur-xs">
                    <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse shadow-[0_0_8px_#34d399]"></span>
                    <span className="tabular-nums font-bold text-white">{syncedCount}</span>
                    <span className="text-slate-400 font-normal">/</span>
                    <span className="tabular-nums text-slate-300">{totalCount} Mesin</span>
                  </div>
                </div>
              </div>

              {/* 3-Column Responsive Grid (Compact on PC) */}

              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3.5">

                {group.machines.map((m) => (

                  <MachineCard key={m.id} machine={m} onOpenModal={openTelemetryModal} />

                ))}

              </div>

            </section>

          );

        })}

      </main>

      {/* =========================================================================

          4. MODAL DETAIL SCADA: SUHU VS PRESSURE (STEAM_PR) + INTERACTIVE HOVER

             DESAIN PROFESIONAL ENTERPRISE DUAL Y-AXIS

          ========================================================================= */}

      {selectedMachine && (() => {

        const isHtoMachine = Boolean(

          modalChartData?.energy_type === 'hto' ||

          modalChartData?.secondary_metric?.type === 'hto' ||

          (selectedMachine?.energy_usage && selectedMachine.energy_usage.includes('kcal')) ||

          (selectedMachine?.name && selectedMachine.name.toLowerCase().includes('hto')) ||

          (selectedMachine?.code && selectedMachine.code.toLowerCase().includes('hto'))

        );

        const secMetricName = isHtoMachine ? 'Suhu Sirkulasi HTO (Oil_Temp)' : 'Tekanan Uap (Steam_Pr)';

        const secMetricUnit = isHtoMachine ? '°C' : 'bar';

        const secMetricKey = isHtoMachine ? 'hto_temp' : 'pressure';

        const secMetricColor = isHtoMachine ? '#d97706' : '#7c3aed';

        const isManualMachine = Boolean(modalChartData?.machine?.is_manual || selectedMachine?.is_manual);

        const chartTitle = isHtoMachine

          ? (isManualMachine ? 'Status Mesin & Suhu Sirkulasi HTO' : 'Kurva Suhu Mesin vs Suhu Sirkulasi HTO (Oil_Temp)')

          : (isManualMachine ? 'Status & Uap' : 'Profil Suhu & Tekanan Uap');

        // Batch Process & Artikel Kain untuk Header Pop-up (menggantikan subjudul telemetri)
        const isBatchActive = Boolean(selectedMachine.has_active_batch && selectedMachine.batch_number);
        const batchNumClean = String(selectedMachine.batch_number || '').replace(/^#/, '').trim();
        const batchLabel = isBatchActive
          ? `Batch #${batchNumClean}`
          : selectedMachine.is_manual
          ? `Operasional Manual (${selectedMachine.status})`
          : 'Standby / Belum Ada Batch';

        const rawSubtitle = String(selectedMachine.batch_subtitle || '');
        const isWaitingFabric = rawSubtitle.toLowerCase().includes('menunggu') || rawSubtitle.toLowerCase().includes('kosong');
        let articleLabel = selectedMachine.artikel_kain
          ? (rawSubtitle && !isWaitingFabric ? rawSubtitle : selectedMachine.artikel_kain)
          : (!isWaitingFabric && rawSubtitle ? rawSubtitle : null);

        // Hilangkan artikel kain jika isinya duplikat dengan nomor batch (contoh #824)
        if (articleLabel) {
          const artClean = String(articleLabel).replace(/^#/, '').trim();
          if (artClean === batchNumClean || artClean === `Batch #${batchNumClean}`) {
            articleLabel = null;
          }
        }

        // Status singkat untuk bar ringkas di atas grafik
        const rawStatus = selectedMachine.time_badge || (selectedMachine.is_active ? 'Aktif' : 'Standby');
        const compactStatus = rawStatus
          .replace(/mnt/g, 'm')
          .replace(/Mulai /g, '')
          .replace(/Standby Off/g, 'Standby')
          .replace(/Mesin Berjalan/g, 'Aktif')
          .trim();

        return typeof document !== 'undefined' ? createPortal(
        <div
          className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-3.5 sm:p-5"
          onClick={closeTelemetryModal}
        >

          <div

            className="bg-white rounded-2xl shadow-2xl border border-slate-200 w-full max-w-4xl max-h-[86vh] flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-150"

            onClick={(e) => e.stopPropagation()}

          >

            {/* Modal Header */}

            <div className="px-3.5 py-2.5 sm:px-5 sm:py-3.5 bg-slate-50/80 border-b border-slate-200 flex items-center justify-between gap-3">

              <div className="flex items-center gap-3">

                <div className="w-8 h-8 rounded-lg bg-slate-900 text-white flex items-center justify-center font-bold text-xs shadow-xs">

                  {selectedMachine.code.substring(0, 2)}

                </div>

                <div>

                  <div className="flex items-center gap-2">

                    <h3 className="text-base font-bold text-slate-900 leading-tight">

                      {selectedMachine.name} ({selectedMachine.group_code})

                    </h3>

                    <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase border bg-slate-100 text-slate-700 border-slate-200">

                      {selectedMachine.status}

                    </span>

                  </div>

                  <div className="text-xs text-slate-600 mt-0.5 flex flex-wrap items-center gap-1.5 font-medium leading-normal">
                    <span className="font-semibold text-slate-800">{batchLabel}</span>
                    {articleLabel && (
                      <>
                        <span className="text-slate-300">•</span>
                        <span className="text-slate-600 truncate max-w-xs sm:max-w-md" title={articleLabel}>
                          {articleLabel}
                        </span>
                      </>
                    )}
                  </div>

                </div>

              </div>

              <button

                onClick={closeTelemetryModal}

                className="w-8 h-8 rounded-lg flex items-center justify-center text-slate-400 hover:text-slate-700 hover:bg-slate-200/70 transition-colors"

                title="Tutup (ESC)"

              >

                <X className="w-4 h-4" />

              </button>

            </div>

            {/* Modal Body */}

            <div className="p-2.5 sm:p-4 overflow-y-auto flex flex-col gap-2 sm:gap-3">

              {/* Compact Telemetry Stats & Range Selector (Layout Ringkas & Hemat Ruang) */}
              <div className="bg-slate-50/90 px-3 py-2 sm:px-3.5 sm:py-2.5 rounded-xl border border-slate-200/80 flex flex-col sm:flex-row sm:items-center justify-between gap-2 shadow-2xs">

                {/* Stats Metrics (Suhu, Gradien, Energi, Status Singkat) */}
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 sm:gap-x-4 text-xs">
                  {/* Suhu */}
                  <div className="flex items-baseline gap-1">
                    <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wide">Suhu</span>
                    <span className="text-base sm:text-lg font-black text-slate-900 tabular-nums leading-none">
                      {selectedMachine.temperature !== null ? `${selectedMachine.temperature} °C` : '-'}
                    </span>
                  </div>

                  <span className="text-slate-300 select-none">•</span>

                  {/* Gradien (menggantikan "Laju Perubahan") */}
                  <div className="flex items-baseline gap-1">
                    <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wide">Gradien</span>
                    <span className="text-xs font-bold text-slate-700 tabular-nums">
                      {selectedMachine.grad_display ? selectedMachine.grad_display.replace(/°\/m/g, '°C/m') : '-'}
                    </span>
                  </div>

                  {selectedMachine.energy_usage && (
                    <>
                      <span className="text-slate-300 select-none">•</span>
                      <div className="flex items-baseline gap-1">
                        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wide">Energi</span>
                        <span className="text-xs font-bold text-sky-700 tabular-nums">
                          {selectedMachine.energy_usage}
                        </span>
                      </div>
                    </>
                  )}

                  {compactStatus && (
                    <>
                      <span className="text-slate-300 hidden sm:inline select-none">•</span>
                      <div className="flex items-baseline gap-1 w-full sm:w-auto mt-0.5 sm:mt-0">
                        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wide">Status</span>
                        <span className="text-xs font-semibold text-slate-700 truncate max-w-[260px] sm:max-w-none" title={selectedMachine.time_badge}>
                          {compactStatus}
                        </span>
                      </div>
                    </>
                  )}
                </div>

                {/* Range Selector (Pills Ringkas) */}
                <div className="flex items-center gap-0.5 bg-white p-0.5 rounded-lg border border-slate-200 shadow-2xs shrink-0 self-start sm:self-auto">
                  {selectedMachine.has_active_batch && (
                    <button
                      onClick={() => handleRangeChange(null)}
                      className={`px-2.5 py-1 rounded-md text-xs font-semibold transition-all ${
                        modalHours === null
                          ? 'bg-blue-600 text-white shadow-2xs'
                          : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
                      }`}
                    >
                      Awal
                    </button>
                  )}
                  {[2, 6, 24].map((h) => (
                    <button
                      key={h}
                      onClick={() => handleRangeChange(h)}
                      className={`px-2.5 py-1 rounded-md text-xs font-semibold transition-all ${
                        modalHours === h || (!selectedMachine.has_active_batch && modalHours === null && h === 2)
                          ? 'bg-blue-600 text-white shadow-2xs'
                          : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
                      }`}
                    >
                      {h} Jam
                    </button>
                  ))}
                </div>
              </div>

              {/* Kurva Grafik SCADA: SUHU VS PRESSURE / HTO (ADAPTIF ENERGI & BEBAS TERTUTUP) */}

              {(() => {

                const isHtoMachine = Boolean(

                  modalChartData?.energy_type === 'hto' ||

                  modalChartData?.secondary_metric?.type === 'hto' ||

                  (selectedMachine?.energy_usage && selectedMachine.energy_usage.includes('kcal')) ||

                  (selectedMachine?.name && selectedMachine.name.toLowerCase().includes('hto')) ||

                  (selectedMachine?.code && selectedMachine.code.toLowerCase().includes('hto'))

                );

                const secMetricName = isHtoMachine ? 'Suhu Sirkulasi HTO (Oil_Temp)' : 'Tekanan Uap (Steam_Pr)';

                const secMetricUnit = isHtoMachine ? '°C' : 'bar';

                const secMetricKey = isHtoMachine ? 'hto_temp' : 'pressure';

                const secMetricColor = isHtoMachine ? '#d97706' : '#7c3aed';

                const isManualMachine = Boolean(modalChartData?.machine?.is_manual || selectedMachine?.is_manual);

                const chartTitle = isHtoMachine

                  ? (isManualMachine ? 'Status & HTO' : 'Profil Suhu & HTO')

                  : (isManualMachine ? 'Status & Uap' : 'Profil Suhu & Tekanan Uap');

                return (

                  <div className="bg-white p-3 sm:p-4 border border-slate-200/90 rounded-xl shadow-xs flex flex-col gap-2">

                    <div className="flex items-center justify-between pb-1 border-b border-slate-100">

                      <div className="flex items-center gap-2">

                        <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>

                        <h4 className="text-xs sm:text-sm font-bold text-slate-800">

                          {chartTitle}

                        </h4>

                      </div>

                      <div className="text-[11px] font-semibold text-slate-400">

                        {

                          modalHours === null

                            ? (selectedMachine.has_active_batch ? 'Siklus Aktif' : '2 Jam')

                            : `${modalHours} Jam`

                        }

                      </div>

                    </div>

                    <div className="h-[210px] sm:h-[290px] w-full pt-0.5 pb-0.5">

                      {modalChartLoading ? (

                        <div className="flex flex-col items-center justify-center h-full text-slate-400 gap-2">

                          <RotateCw className="w-6 h-6 animate-spin text-blue-500" />

                          <span className="text-xs font-medium">Memuat telemetri sensor...</span>

                        </div>

                      ) : modalChartData && modalChartData.chart_data && modalChartData.chart_data.length > 0 ? (

                        <ResponsiveContainer width="100%" height="100%">

                          <LineChart

                            data={modalChartData.chart_data}

                            margin={{ top: 8, right: 10, left: 6, bottom: 4 }}

                          >

                            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />

                            <XAxis

                              dataKey="time"

                              tick={{ fontSize: 10, fill: '#64748b' }}

                              minTickGap={24}

                              axisLine={{ stroke: '#cbd5e1' }}

                              tickLine={false}

                            padding={{ left: 0, right: 0 }}

                                />

                            {isManualMachine ? (

                              <>

                                <YAxis

                                  yAxisId="left"

                                  tick={{ fontSize: 10, fill: secMetricColor }}

                                  domain={['auto', 'auto']}

                                  width={38}

                                  tickMargin={4}

                                  unit={` ${secMetricUnit}`}

                                />

                                <YAxis

                                  yAxisId="right"

                                  orientation="right"

                                  tick={{ fontSize: 10, fill: '#10b981' }}

                                  domain={[0, 1]}

                                  ticks={[0, 1]}

                                  tickFormatter={(v) => (v === 1 ? 'ON' : 'OFF')}

                                  width={30}

                                  tickMargin={4}

                                />

                                <Tooltip

                                  contentStyle={{

                                    backgroundColor: '#ffffff',

                                    borderRadius: '10px',

                                    border: '1px solid #cbd5e1',

                                    boxShadow: '0 4px 12px rgba(0,0,0,0.08)',

                                    fontSize: '12px',

                                  }}

                                  labelFormatter={(label) => `Waktu: ${label} WIB`}

                                  formatter={(value, name) => {

                                    if (name === 'Status Mesin') return [value === 1 ? 'ON (Running)' : 'OFF (Stop)', name];

                                    if (name === secMetricName) return [`${value} ${secMetricUnit}`, name];

                                    if (name === 'Suhu Mesin') return [`${value} °C`, name];

                                    return [value, name];

                                  }}

                                />

                                <Legend verticalAlign="bottom" wrapperStyle={{ fontSize: '11px', paddingTop: '10px' }} />

                                <Line

                                  yAxisId="left"

                                  type="monotone"

                                  dataKey={secMetricKey}

                                  stroke={secMetricColor}

                                  strokeWidth={2}

                                  dot={false}

                                  name={secMetricName}

                                  activeDot={{ r: 4, fill: secMetricColor, stroke: '#ffffff', strokeWidth: 2 }}

                                />

                                <Line

                                  yAxisId="right"

                                  type="stepAfter"

                                  dataKey="is_on"

                                  stroke="#10b981"

                                  strokeWidth={2.5}

                                  dot={false}

                                  name="Status Mesin"

                                />

                              </>

                            ) : (

                              <>

                                <YAxis

                                  yAxisId="left"

                                  tick={{ fontSize: 10, fill: '#0284c7' }}

                                  domain={['auto', 'auto']}

                                  width={38}

                                  tickMargin={4}

                                  unit="°"

                                />

                                <YAxis

                                  yAxisId="right"

                                  orientation="right"

                                  tick={{ fontSize: 10, fill: secMetricColor }}

                                  domain={['auto', 'auto']}

                                  width={38}

                                  tickMargin={4}

                                  unit={` ${secMetricUnit}`}

                                />

                                <Tooltip

                                  contentStyle={{

                                    backgroundColor: '#ffffff',

                                    borderRadius: '10px',

                                    border: '1px solid #cbd5e1',

                                    boxShadow: '0 4px 12px rgba(0,0,0,0.08)',

                                    fontSize: '12px',

                                  }}

                                  labelFormatter={(label) => `Waktu: ${label} WIB`}

                                  formatter={(value, name) => {

                                    if (name === 'Suhu Mesin') return [`${value} °C`, name];

                                    if (name === secMetricName) return [`${value} ${secMetricUnit}`, name];

                                    return [value, name];

                                  }}

                                />

                                <Legend verticalAlign="bottom" wrapperStyle={{ fontSize: '11px', paddingTop: '10px' }} />

                                <Line

                                  yAxisId="left"

                                  type="monotone"

                                  dataKey="temp"

                                  stroke="#0284c7"

                                  strokeWidth={2.2}

                                  dot={false}

                                  name="Suhu Mesin"

                                  activeDot={{ r: 5, fill: '#0284c7', stroke: '#ffffff', strokeWidth: 2 }}

                                />

                                <Line

                                  yAxisId="right"

                                  type="monotone"

                                  dataKey={secMetricKey}

                                  stroke={secMetricColor}

                                  strokeWidth={1.8}

                                  strokeDasharray="4 3"

                                  dot={false}

                                  name={secMetricName}

                                  activeDot={{ r: 4, fill: secMetricColor, stroke: '#ffffff', strokeWidth: 2 }}

                                />

                              </>

                            )}

                          </LineChart>

                        </ResponsiveContainer>

                      ) : modalChartError ? (
                        <div className="flex flex-col items-center justify-center h-full text-slate-500 gap-2 p-6 text-center">
                          <ShieldAlert className="w-8 h-8 text-rose-500 mb-1" />
                          <span className="text-xs font-semibold text-slate-700">{modalChartError}</span>
                          <span className="text-[11px] text-slate-400">Periksa koneksi jaringan atau coba beberapa saat lagi.</span>
                          <button
                            onClick={() => selectedMachine && fetchModalChart(selectedMachine.id, modalHours)}
                            className="mt-2 px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold shadow-xs"
                          >
                            Coba Lagi
                          </button>
                        </div>
                      ) : (
                        <div className="flex flex-col items-center justify-center h-full text-slate-400">
                          <Activity className="w-8 h-8 mb-1 text-slate-300" />
                          <span className="text-xs font-medium">
                            Tidak ada log telemetri tercatat untuk rentang ini.
                          </span>
                        </div>
                      )}

                    </div>

                  </div>

                );

              })()}

            </div>

            {/* Modal Footer */}

            <div className="px-5 py-3 bg-slate-50 border-t border-slate-200 flex items-center justify-end">

              <button

                onClick={closeTelemetryModal}

                className="px-4 py-1.5 rounded-lg bg-slate-200 hover:bg-slate-300 text-slate-700 text-xs font-semibold transition-colors"

              >

                Tutup

              </button>

            </div>

          </div>

        </div>,
        document.body
        ) : null;

      })()}

    </div>

  );

}

// =========================================================================

// SUBKOMPONEN CARD MESIN (INDUSTRIAL TELEMETRY PROFILE)

// Menampilkan status aktif vs mati secara kontras dengan jam nyala terdeteksi

// =========================================================================

function MachineCard({ machine: m, onOpenModal }) {

  const status = (m.status || 'OFF').toUpperCase();

  const isHeat = status === 'HEAT';

  const isSteady = status === 'STEADY';

  const isCool = status === 'COOL';

  const isRunning = status === 'RUNNING';

  const isMati = status === 'OFF' || status === 'STOP';

  const isNoSig = status === 'NOSIGNAL';

  const isManual = Boolean(m.is_manual) || m.operation_mode === 'MANUAL';

  const isActive = Boolean(m.is_active) || isHeat || isSteady || isCool || isRunning;

  const hasActiveBatch = Boolean(m.has_active_batch) && Boolean(m.batch_number) && m.batch_number !== '---';

  // 1. Tentukan Tema Visual & Palet Warna Card Berdasarkan Status Real-time

  let cardBg = 'bg-white border-slate-200/90 hover:border-slate-300 hover:bg-slate-50/50';

  let leftAccentColor = 'bg-slate-300 w-1';

  let badgeClass = 'bg-slate-200 text-slate-600 border-slate-300 font-semibold';

  let thumbBg = 'bg-slate-100/90 border-slate-200';

  let phaseColor = 'text-slate-400 font-semibold';

  let strokeColor = '#94a3b8';

  let bannerClass = 'bg-slate-100/90 text-slate-500 border-slate-200';

  let BannerIcon = CheckCircle2;

  let phaseTitle = 'IDLE DRAIN';
  let bannerText = 'Off';
  let actionBtnClass = 'bg-[#0f172a] hover:bg-slate-800 active:bg-slate-900 text-white shadow-2xs font-bold rounded-full';

  if (isHeat) {
    cardBg = 'bg-gradient-to-br from-white to-rose-50/50 border-2 border-rose-500 hover:border-rose-600 shadow-sm ring-1 ring-rose-500/20';
    leftAccentColor = 'bg-rose-500 w-1.5';
    badgeClass = 'bg-rose-100 text-rose-800 border-rose-300 font-bold';
    thumbBg = 'bg-rose-50/80 border-rose-200';
    phaseColor = 'text-rose-800 font-bold';
    strokeColor = '#e11d48';
    bannerClass = 'bg-rose-50/90 text-rose-900 border-rose-200';
    BannerIcon = Flame;
    phaseTitle = 'HT RAMP';
    bannerText = m.time_badge || 'Heat';
    actionBtnClass = 'bg-[#e11d48] hover:bg-rose-700 active:bg-rose-800 text-white shadow-sm font-bold rounded-full';
  } else if (isSteady) {
    cardBg = 'bg-gradient-to-br from-white to-blue-50/50 border-2 border-blue-500 hover:border-blue-600 shadow-sm ring-1 ring-blue-500/20';
    leftAccentColor = 'bg-blue-600 w-1.5';
    badgeClass = 'bg-blue-100 text-blue-800 border-blue-300 font-bold';
    thumbBg = 'bg-blue-50/80 border-blue-200';
    phaseColor = 'text-blue-800 font-bold';
    strokeColor = '#2563eb';
    bannerClass = 'bg-blue-50/90 text-blue-900 border-blue-200';
    BannerIcon = Clock;
    phaseTitle = 'STEADY HOLD';
    bannerText = m.time_badge || 'Steady';
    actionBtnClass = 'bg-[#0066fe] hover:bg-blue-700 active:bg-blue-800 text-white shadow-sm font-bold rounded-full';
  } else if (isCool) {
    cardBg = 'bg-gradient-to-br from-white to-sky-50/50 border-2 border-blue-500 hover:border-blue-600 shadow-sm ring-1 ring-sky-500/20';
    leftAccentColor = 'bg-sky-500 w-1.5';
    badgeClass = 'bg-sky-100 text-sky-800 border-sky-300 font-bold';
    thumbBg = 'bg-sky-50/80 border-sky-200';
    phaseColor = 'text-sky-800 font-bold';
    strokeColor = '#0284c7';
    bannerClass = 'bg-sky-50/90 text-sky-900 border-sky-200';
    BannerIcon = Snowflake;
    phaseTitle = 'COOL DOWN';
    bannerText = m.time_badge || 'Cool';
    actionBtnClass = 'bg-[#0066fe] hover:bg-blue-700 active:bg-blue-800 text-white shadow-sm font-bold rounded-full';
  } else if (isRunning) {
    cardBg = 'bg-gradient-to-br from-white to-blue-50/50 border-2 border-blue-500 hover:border-blue-600 shadow-sm ring-1 ring-blue-500/20';
    leftAccentColor = 'bg-emerald-500 w-1.5';
    badgeClass = 'bg-emerald-100 text-emerald-800 border-emerald-300 font-bold';
    thumbBg = 'bg-emerald-50/80 border-emerald-200';
    phaseColor = 'text-emerald-800 font-bold';
    strokeColor = '#059669';
    bannerClass = 'bg-emerald-50/90 text-emerald-900 border-emerald-200';
    BannerIcon = Activity;
    phaseTitle = isManual ? 'MANUAL RUNNING' : (m.status_phase_label || 'CIRCULATION');
    bannerText = m.time_badge || (isManual ? `Nyala ${m.active_since || 'Hari ini'}` : 'Run');
    actionBtnClass = 'bg-[#0066fe] hover:bg-blue-700 active:bg-blue-800 text-white shadow-sm font-bold rounded-full';

  } else if (isNoSig) {

    cardBg = 'bg-gradient-to-br from-amber-50/35 to-white border-2 border-amber-400 hover:border-amber-500 shadow-sm ring-1 ring-amber-400/20';

    leftAccentColor = 'bg-amber-500 w-1.5';

    badgeClass = 'bg-amber-100 text-amber-800 border-amber-300 font-bold';

    thumbBg = 'bg-amber-50/80 border-amber-200';

    phaseColor = 'text-amber-800 font-bold';

    strokeColor = '#d97706';

    bannerClass = 'bg-amber-50/90 text-amber-900 border-amber-200';

    BannerIcon = ShieldAlert;

    phaseTitle = 'NO SIGNAL';

    bannerText = 'Sensor Tidak Terhubung';

    actionBtnClass = 'bg-amber-600 hover:bg-amber-700 active:bg-amber-800 text-white shadow-sm font-bold rounded-full';

  }

  // Rate gradien
  const gradDirection = m.grad_direction;
  const hasGradient = m.gradient !== null && m.gradient !== undefined && !Number.isNaN(Number(m.gradient));
  const gradValue = hasGradient
    ? `${Number(m.gradient) > 0 ? '+' : ''}${Number(m.gradient).toFixed(2)}`
    : (m.grad_display && m.grad_display !== '-' ? m.grad_display.replace(/°C?\/m/gi, '').replace(/[▲▼-]/g, '').trim() : null);

  let gradClass = 'text-slate-500';
  if (gradDirection === 'up') gradClass = 'text-rose-600 font-bold';
  else if (gradDirection === 'down') gradClass = 'text-sky-600 font-bold';

  // Label siklus di bagian bawah kotak preview

  const cycleSubtitle = isActive ? (m.cycle_label ? m.cycle_label.replace(/^Siklus\s*/i, 'Aktif ') : 'Aktif') : 'Standby Off';

  // Hanya tampilkan kurva mini jika mesin aktif & ada data

  const showSparkline = isActive && m.chart && m.chart.has_data;

  const gradId = `spark-grad-${m.id}`;

  return (

    <article

      onClick={() => onOpenModal(m)}

      className={`relative rounded-xl border transition-all duration-200 cursor-pointer overflow-hidden p-2.5 sm:p-3 flex flex-col justify-between gap-2 group shadow-sm hover:shadow-md hover:-translate-y-0.5 active:translate-y-0 active:scale-[0.99] ${cardBg}`}

    >

      {/* Left Colored Accent Bar */}

      <div className={`absolute left-0 top-0 bottom-0 ${leftAccentColor} rounded-l-xl`}></div>

      {/* Internal Content */}

      <div className="pl-1.5 flex flex-col gap-2">

        {/* ROW 1: TOP AREA (Micro-chart Left + Metrics Right) */}

        <div className="flex items-start gap-2.5">

          {/* Micro-chart Thumbnail Box (w-28 sm:w-32, h-[68px]) */}

          <div className={`w-28 sm:w-32 h-[68px] shrink-0 rounded-lg p-1.5 flex flex-col justify-between border ${thumbBg} relative overflow-hidden select-none`}>

            {/* Top phase label */}

            <div className={`text-[9px] tracking-wider uppercase text-center truncate ${phaseColor}`}>

              {phaseTitle}

            </div>

            {/* Sparkline curve atau Dotted Standby Line */}

            <div className="h-6 w-full flex items-center justify-center my-auto">

              {showSparkline ? (

                <svg className="w-full h-full overflow-visible" viewBox="0 0 95 38" preserveAspectRatio="none">

                  <defs>

                    <linearGradient id={gradId} x1="0" x2="0" y1="0" y2="1">

                      <stop offset="0%" stopColor={strokeColor} stopOpacity="0.30" />

                      <stop offset="100%" stopColor={strokeColor} stopOpacity="0.0" />

                    </linearGradient>

                  </defs>

                  <path d={m.chart.area} fill={`url(#${gradId})`} />

                  <polyline

                    fill="none"

                    stroke={strokeColor}

                    strokeLinecap="round"

                    strokeLinejoin="round"

                    strokeWidth="2.2"

                    points={m.chart.points}

                  />

                  <circle

                    className={isHeat ? 'animate-pulse' : ''}

                    cx={m.chart.last_x}

                    cy={m.chart.last_y}

                    fill={strokeColor}

                    r="2.8"

                  />

                </svg>

              ) : (

                /* Garis titik-titik standby off bersih untuk mesin mati */

                <svg className="w-full h-3" viewBox="0 0 95 12">

                  <line

                    x1="4"

                    y1="6"

                    x2="91"

                    y2="6"

                    stroke="#cbd5e1"

                    strokeWidth="2"

                    strokeDasharray="2 3"

                  />

                </svg>

              )}

            </div>

            {/* Bottom subtitle inside box */}

            <div className="text-[9px] font-medium text-slate-500 text-center truncate">

              {cycleSubtitle}

            </div>

          </div>

          {/* Right Metrics Box: Machine Name, Status Badge, Big Temp, Rate */}

          <div className="flex-1 min-w-0 flex flex-col justify-between h-[68px]">

            {/* Machine Name & Status Pill */}

            <div className="flex items-center justify-between gap-1">

              <h4 className="text-[15px] sm:text-base font-extrabold text-slate-900 tracking-tight leading-tight truncate" title={m.display_title || `${m.name} (${m.group_code})`}>

                {m.name}

              </h4>

              <span className={`px-1.5 py-0.5 rounded text-[10px] uppercase border leading-none shrink-0 ${badgeClass}`}>

                {m.status}

              </span>

            </div>

            {/* Temperature & Rate */}

            <div className="flex items-baseline justify-between gap-1">

              <div className="flex items-baseline">

                <span className="text-2xl sm:text-[26px] font-bold text-slate-900 tracking-tight leading-none tabular-nums font-sans">

                  {m.temperature !== null && m.temperature !== undefined ? m.temperature : '--.-'}

                </span>

                <span className="text-xs font-normal text-slate-400 ml-0.5">°C</span>

              </div>

              {/* Rate */}
              {gradValue && gradValue !== '-' ? (
                <div className={`text-[10px] sm:text-xs tabular-nums ${gradClass} shrink-0`}>
                  {gradDirection === 'up' && '▲ '}
                  {gradDirection === 'down' && '▼ '}
                  {gradDirection === 'flat' && '- '}
                  {gradValue} <span className="text-[9px] font-normal">°C/m</span>
                </div>
              ) : (
                <div className="text-[10px] sm:text-xs text-slate-400 shrink-0">-</div>
              )}

            </div>

          </div>

        </div>

        {/* ROW 2: MIDDLE OPERATIONAL BANNER (Waktu / Siklus + Perkiraan Energi Mesin Aktif) */}

        <div className={`px-2 py-1 rounded-md text-xs font-medium border flex items-center justify-between gap-1.5 w-full ${bannerClass}`}>

          <div className="flex items-center gap-1.5 min-w-0 truncate">

            <BannerIcon className="w-3.5 h-3.5 shrink-0" />

            <span className="truncate">{bannerText}</span>

          </div>

          {isActive && m.energy_usage && (

            <span className="text-[10px] font-bold tabular-nums shrink-0 px-1.5 py-0.5 rounded bg-white/80 shadow-2xs text-slate-800 border border-slate-200/50" title="Perkiraan Pemakaian Energi Mesin">

              {m.energy_usage}

            </span>

          )}

        </div>

        {/* ROW 3: BOTTOM ROW (Batch Info Left + Action Button Right) */}

        <div className="flex items-center justify-between gap-1 pt-0.5">

          {/* Batch & Fabric Tag */}

          <div className="flex items-center gap-1.5 min-w-0 truncate">

            {m.group_code && (

              <span className="px-1.5 py-0.5 rounded text-[10px] font-mono font-bold text-slate-600 bg-slate-100 border border-slate-200/90 shrink-0 shadow-2xs" title={`Kelompok Mesin: ${m.group_code}`}>

                {m.group_code}

              </span>

            )}

            <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold shrink-0 ${

              hasActiveBatch

                ? 'text-sky-700 bg-sky-50 border border-sky-200/80'

                : isManual && isRunning

                ? 'text-emerald-700 bg-emerald-50 border border-emerald-200/80'

                : 'text-slate-500 bg-slate-100 border border-slate-200'

            }`}>

              {hasActiveBatch ? `#${m.batch_number}` : isManual && isRunning ? 'MANUAL' : '#---'}

            </span>

            <span className="text-xs text-slate-600 truncate font-medium" title={m.batch_subtitle || (isActive ? 'Proses Berjalan' : 'Kosong (Menunggu Kain)')}>

              {m.batch_subtitle || (isActive ? 'Proses Berjalan' : 'Kosong (Menunggu Kain)')}

            </span>

          </div>

          {/* Action Button */}

          <button

            type="button"

            onClick={(e) => {

              e.stopPropagation();

              onOpenModal(m);

            }}

            className={`text-xs font-bold px-3.5 py-1 sm:py-1.5 rounded-full transition-all shrink-0 shadow-xs flex items-center gap-1 active:scale-95 group-hover:brightness-105 ${actionBtnClass}`}

          >

            <span>Detail</span>

            <ChevronRight className="w-3.5 h-3.5" />

          </button>

        </div>

      </div>

    </article>

  );

}

