import { useState, useEffect, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../../lib/api';
import { useSmartPolling } from '../../hooks/useSmartPolling';
import {
  ResponsiveContainer,
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
} from 'recharts';
import {
  Gauge,
  Flame,
  Clock,
  Activity,
  TrendingDown,
  RefreshCw,
  CheckCircle2,
  Cpu,
  ChevronDown,
  ArrowRight,
  Sliders,
} from 'lucide-react';

const HOURS_OPTIONS = [
  { value: 2, label: '2 Jam' },
  { value: 4, label: '4 Jam' },
  { value: 8, label: '8 Jam' },
  { value: 12, label: '12 Jam' },
  { value: 24, label: '24 Jam' },
];

/**
 * Custom Tooltip Grafik 1 (Primary vs Usage)
 */
const CustomPrimaryTooltip = ({ active, payload, label, channel }) => {
  if (!active || !payload || !payload.length) return null;

  const isSteam = channel === 'steam';
  const primaryName = isSteam ? 'Tekanan' : 'Suhu';
  const primaryUnit = isSteam ? 'bar' : '°C';
  const usageName = isSteam ? 'Pemakaian' : 'Beban';
  const usageUnit = isSteam ? 'ton/jam' : 'jt kcal';

  const primaryItem = payload.find((p) => p.dataKey === 'primary_val');
  const usageItem = payload.find((p) => p.dataKey === 'usage');

  return (
    <div className="bg-slate-900/60 backdrop-blur-md border border-white/20 p-2 sm:p-2.5 rounded-xl shadow-lg text-[11px] sm:text-xs text-slate-100 min-w-[130px] sm:min-w-[150px] pointer-events-none transition-all">
      <div className="font-mono font-semibold text-slate-300 border-b border-white/10 pb-1 mb-1.5 flex items-center justify-between text-[10px] sm:text-[11px]">
        <span className="flex items-center gap-1">
          <Clock className="w-3 h-3 text-slate-400" />
          Pukul {label}
        </span>
      </div>
      <div className="space-y-1">
        {primaryItem && primaryItem.value != null && (
          <div className="flex items-center justify-between gap-2.5">
            <span className="flex items-center gap-1 text-slate-200 font-medium text-[10px] sm:text-xs">
              <span className={`w-1.5 h-1.5 rounded-full ${isSteam ? 'bg-sky-400' : 'bg-amber-400'}`} />
              {primaryName}
            </span>
            <span className="font-mono font-bold text-white text-xs sm:text-sm">
              {Number(primaryItem.value).toFixed(2)} <span className="text-[10px] font-normal text-slate-300">{primaryUnit}</span>
            </span>
          </div>
        )}
        {usageItem && usageItem.value != null && (
          <div className="flex items-center justify-between gap-2.5">
            <span className="flex items-center gap-1 text-slate-200 font-medium text-[10px] sm:text-xs">
              <span className={`w-1.5 h-1.5 rounded-full ${isSteam ? 'bg-indigo-400' : 'bg-orange-500'}`} />
              {usageName}
            </span>
            <span className="font-mono font-bold text-white text-xs sm:text-sm">
              {Number(usageItem.value).toFixed(2)} <span className="text-[10px] font-normal text-slate-300">{usageUnit}</span>
            </span>
          </div>
        )}
      </div>
    </div>
  );
};

/**
 * Custom Tooltip Grafik 2 (Speed Batu Bara vs Temp Ruang Bakar)
 * Transparan 60% dengan backdrop blur halus agar tidak menutupi kurva grafik
 */
const CustomCombustionTooltip = ({ active, payload, label }) => {
  if (!active || !payload || !payload.length) return null;

  const speedItem = payload.find((p) => p.dataKey === 'speed_coal');
  const tempItem = payload.find((p) => p.dataKey === 'temp_chamber');

  return (
    <div className="bg-slate-900/60 backdrop-blur-md border border-white/20 p-2 sm:p-2.5 rounded-xl shadow-lg text-[11px] sm:text-xs text-slate-100 min-w-[130px] sm:min-w-[150px] pointer-events-none transition-all">
      <div className="font-mono font-semibold text-slate-300 border-b border-white/10 pb-1 mb-1.5 flex items-center justify-between text-[10px] sm:text-[11px]">
        <span className="flex items-center gap-1">
          <Clock className="w-3 h-3 text-slate-400" />
          Pukul {label}
        </span>
      </div>
      <div className="space-y-1">
        {speedItem && speedItem.value != null && (
          <div className="flex items-center justify-between gap-2.5">
            <span className="flex items-center gap-1 text-slate-200 font-medium text-[10px] sm:text-xs">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
              Speed Coal
            </span>
            <span className="font-mono font-bold text-white text-xs sm:text-sm">
              {Number(speedItem.value).toFixed(1)} <span className="text-[10px] font-normal text-slate-300">Hz</span>
            </span>
          </div>
        )}
        {tempItem && tempItem.value != null && (
          <div className="flex items-center justify-between gap-2.5">
            <span className="flex items-center gap-1 text-slate-200 font-medium text-[10px] sm:text-xs">
              <span className="w-1.5 h-1.5 rounded-full bg-rose-500" />
              Suhu R. Bakar
            </span>
            <span className="font-mono font-bold text-white text-xs sm:text-sm">
              {Number(tempItem.value).toFixed(1)} <span className="text-[10px] font-normal text-slate-300">°C</span>
            </span>
          </div>
        )}
      </div>
    </div>
  );
};

export default function BoilerUtilityView({ channel = 'steam' }) {
  const navigate = useNavigate();
  const isSteam = channel === 'steam';

  const [hours, setHours] = useState(4);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  // Fetch telemetry data from API
  const fetchData = useCallback(async (isManualRefresh = false) => {
    if (isManualRefresh) setRefreshing(true);

    try {
      const res = await api.get(`/boiler/utility-telemetry?channel=${channel}&hours=${hours}`, {
        cache: isManualRefresh ? false : undefined,
      });
      setData(res.data);
    } catch (err) {
      console.error('Error fetching boiler utility telemetry:', err);
    } finally {
      setLoading(false);
      if (isManualRefresh) setRefreshing(false);
    }
  }, [channel, hours]);

    // Polling pintar 30 detik: pause otomatis di background tab, resume seketika saat fokus
  useSmartPolling(() => fetchData(false), 30000, { immediate: true });

  const realtime = data?.realtime || {};
  const dailyKpi = data?.daily_kpi || {};
  const chartData = data?.chart_data || [];
  const historyEvents = data?.history_events || [];

  // Hitung min/max domain agar grafik tidak terpotong dan terlihat presisi
  const primaryDomain = useMemo(() => {
    if (!chartData.length) return [0, isSteam ? 8 : 300];
    const vals = chartData.map((d) => d.primary_val).filter((v) => v != null);
    if (!vals.length) return [0, isSteam ? 8 : 300];
    const min = Math.min(...vals);
    const max = Math.max(...vals);
    if (isSteam) {
      return [Math.max(0, Math.floor(min - 0.5)), Math.ceil(max + 0.5)];
    }
    return [Math.max(0, Math.floor(min - 10)), Math.ceil(max + 10)];
  }, [chartData, isSteam]);

  const usageDomain = useMemo(() => {
    if (!chartData.length) return [0, isSteam ? 15 : 10];
    const vals = chartData.map((d) => d.usage).filter((v) => v != null);
    if (!vals.length) return [0, isSteam ? 15 : 10];
    const max = Math.max(...vals);
    return [0, Math.ceil(max * 1.25) || 5];
  }, [chartData, isSteam]);

  const speedDomain = useMemo(() => {
    if (!chartData.length) return [0, 50];
    const vals = chartData.map((d) => d.speed_coal).filter((v) => v != null);
    if (!vals.length) return [0, 50];
    const max = Math.max(...vals);
    return [0, Math.max(30, Math.ceil(max * 1.2))];
  }, [chartData]);

  const tempDomain = useMemo(() => {
    if (!chartData.length) return [200, 800];
    const vals = chartData.map((d) => d.temp_chamber).filter((v) => v != null);
    if (!vals.length) return [200, 800];
    const min = Math.min(...vals);
    const max = Math.max(...vals);
    return [Math.max(0, Math.floor(min - 40)), Math.ceil(max + 40)];
  }, [chartData]);

  // Status Styling


  // Loading Skeleton (Gojek / Modern Shimmer Animation)
  if (loading && !data) {
    return (
      <div className="w-full min-h-screen bg-slate-50 text-slate-800 font-sans antialiased p-2.5 sm:p-5 md:p-6 space-y-3 sm:space-y-6">
        {/* HEADER SKELETON */}
        <div className="bg-white rounded-2xl border border-slate-200/90 shadow-2xs p-3 sm:p-4 space-y-3">
          {/* Row 1: Switch pill Left + Range Right */}
          <div className="flex items-center justify-between gap-2">
            <div className="w-36 h-8 rounded-xl skeleton-shimmer" />
            <div className="flex items-center gap-2">
              <div className="w-24 h-8 rounded-lg skeleton-shimmer" />
              <div className="w-8 h-8 rounded-lg skeleton-shimmer" />
            </div>
          </div>
          {/* Row 2: 4 KPI Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-1.5 sm:gap-2 pt-1 border-t border-slate-100">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="p-2.5 sm:p-3 rounded-xl border border-slate-200/90 bg-white flex flex-col justify-between gap-2 shadow-2xs">
                <div className="flex items-center justify-between">
                  <div className="w-16 h-3 rounded skeleton-shimmer" />
                  <div className="w-12 h-4 rounded-full skeleton-shimmer" />
                </div>
                <div className="flex items-baseline justify-between mt-1">
                  <div className="w-20 h-6 rounded skeleton-shimmer" />
                  <div className="w-12 h-3 rounded skeleton-shimmer" />
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* CHART 1 SKELETON */}
        <div className="bg-white rounded-2xl border border-slate-200/90 shadow-2xs p-3.5 sm:p-5 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg skeleton-shimmer" />
              <div className="w-36 sm:w-56 h-5 rounded skeleton-shimmer" />
            </div>
            <div className="w-20 h-5 rounded-full skeleton-shimmer" />
          </div>
          <div className="w-full h-[260px] sm:h-[320px] md:h-[360px] rounded-xl skeleton-shimmer" />
        </div>

        {/* CHART 2 SKELETON */}
        <div className="bg-white rounded-2xl border border-slate-200/90 shadow-2xs p-3.5 sm:p-5 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg skeleton-shimmer" />
              <div className="w-40 sm:w-64 h-5 rounded skeleton-shimmer" />
            </div>
            <div className="w-20 h-5 rounded-full skeleton-shimmer" />
          </div>
          <div className="w-full h-[240px] sm:h-[300px] md:h-[340px] rounded-xl skeleton-shimmer" />
        </div>

        {/* HISTORY LIST SKELETON */}
        <div className="bg-white rounded-2xl border border-slate-200/90 shadow-2xs p-3.5 sm:p-5 space-y-3">
          <div className="w-48 h-5 rounded skeleton-shimmer" />
          <div className="space-y-2">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-10 rounded-xl skeleton-shimmer" />
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="w-full min-h-screen bg-slate-50 text-slate-800 font-sans antialiased p-2 sm:p-5 md:p-6 space-y-3 sm:space-y-6 animate-fade-in">
      {/* ═══════════════════════════════════════════════════════════════════ */}
      {/* HEADER: TITLE, QUICK CHANNEL SWITCH & CONTROLS                     */}
      {/* ═══════════════════════════════════════════════════════════════════ */}
      <div className="bg-white rounded-2xl border border-slate-200/90 shadow-2xs p-2.5 sm:p-3.5 space-y-2.5">
        {/* ROW 1: SWITCH STEAM/HTO (KIRI) & CONTROLS RANGE/REFRESH (KANAN) */}
        <div className="flex items-center justify-between gap-2">
          {/* Pilihan Switch Steam / HTO di Kiri */}
          <div className="inline-flex p-0.5 bg-slate-100 rounded-xl border border-slate-200/90 text-xs font-bold shadow-2xs">
            <button
              onClick={() => navigate('/boiler-steam')}
              className={`px-2.5 sm:px-3 py-1 sm:py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5 cursor-pointer ${
                isSteam
                  ? 'bg-white text-sky-700 shadow-2xs border border-sky-100'
                  : 'text-slate-500 hover:text-slate-800'
              }`}
            >
              <Gauge className={`w-3.5 h-3.5 ${isSteam ? 'text-sky-600' : 'text-slate-400'}`} />
              Steam
            </button>
            <button
              onClick={() => navigate('/boiler-hto')}
              className={`px-2.5 sm:px-3 py-1 sm:py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5 cursor-pointer ${
                !isSteam
                  ? 'bg-white text-amber-700 shadow-2xs border border-amber-100'
                  : 'text-slate-500 hover:text-slate-800'
              }`}
            >
              <Flame className={`w-3.5 h-3.5 ${!isSteam ? 'text-amber-600' : 'text-slate-400'}`} />
              HTO
            </button>
          </div>

          {/* Action Controls di Kanan: Dropdown Range & Refresh */}
          <div className="flex items-center gap-1.5">
            {/* Range Dropdown */}
            <div className="relative inline-flex items-center">
              <select
                value={hours}
                onChange={(e) => setHours(Number(e.target.value))}
                className="appearance-none bg-slate-100 hover:bg-slate-200/80 text-slate-800 text-[11px] sm:text-xs font-bold py-1 sm:py-1.5 pl-2.5 pr-6 sm:pr-7 rounded-lg border border-slate-200 transition-all cursor-pointer focus:outline-none"
              >
                {HOURS_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
              <ChevronDown className="w-3.5 h-3.5 text-slate-500 absolute right-1.5 pointer-events-none" />
            </div>

            {/* Refresh */}
            <button
              onClick={() => fetchData(true)}
              disabled={refreshing || loading}
              className="p-1 sm:p-1.5 bg-slate-100 hover:bg-slate-200 text-slate-600 rounded-lg border border-slate-200 transition-all cursor-pointer disabled:opacity-50"
              title="Refresh Data"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin text-indigo-600' : ''}`} />
            </button>
          </div>
        </div>

        {/* ROW 2: 4 COMPACT TELEMETRY CARDS (BERKACA DARI HEADER HOME.JSX) */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-1.5 sm:gap-2 pt-1 border-t border-slate-100">
          {/* 1. Tekanan / Suhu */}
          <div className={`${isSteam ? 'bg-gradient-to-br from-white to-sky-50/80 border-2 border-sky-400' : 'bg-gradient-to-br from-white to-amber-50/80 border-2 border-amber-400'} rounded-xl px-2.5 py-1.5 flex flex-col justify-between shadow-2xs`}>
            <div className="flex items-center justify-between gap-1 leading-none">
              <div className={`flex items-center gap-1 ${isSteam ? 'text-sky-900' : 'text-amber-900'} font-bold text-xs tracking-wide`}>
                {isSteam ? <Gauge className="w-3.5 h-3.5 text-sky-600 shrink-0" /> : <Flame className="w-3.5 h-3.5 text-amber-600 shrink-0" />}
                <span>{isSteam ? 'TEKANAN' : 'SUHU'}</span>
              </div>
              {/* Badge Jumlah Mesin Aktif (misal: 12 MC) */}
              <span className={`text-[10px] font-bold ${isSteam ? 'text-sky-700 bg-sky-100/90 border-sky-200/60' : 'text-amber-700 bg-amber-100/90 border-amber-200/60'} border px-1.5 py-0.5 rounded leading-none`}>
                {realtime.active_mc ?? 0} MC
              </span>
            </div>
            <div className="flex items-baseline justify-between gap-1 mt-1">
              <div className="flex items-baseline gap-0.5">
                <span className="text-base sm:text-lg font-black text-slate-900 tabular-nums font-mono leading-none">
                  {realtime.value != null ? Number(realtime.value).toFixed(2) : '-'}
                </span>
                <span className="text-[10px] font-semibold text-slate-500">{realtime.unit}</span>
              </div>
              {/* Pemakaian Uap / Beban Panas menggantikan tulisan Live */}
              <span className={`text-[11px] font-bold ${isSteam ? 'text-sky-800' : 'text-amber-800'} tabular-nums truncate`}>
                {realtime.usage || (realtime.usage_val != null ? `${realtime.usage_val} ${isSteam ? 'ton/jam' : 'jt kcal'}` : '-')}
              </span>
            </div>
          </div>

          {/* 2. Ruang Bakar: Temperature & Speed Feeder */}
          <div className="bg-gradient-to-br from-white to-orange-50/80 border-2 border-orange-400 rounded-xl px-2.5 py-1.5 flex flex-col justify-between shadow-2xs">
            <div className="flex items-center justify-between gap-1 leading-none">
              <div className="flex items-center gap-1 text-orange-950 font-bold text-xs tracking-wide">
                <Cpu className="w-3.5 h-3.5 text-orange-600 shrink-0" />
                <span>RUANG BAKAR</span>
              </div>
              {/* Badge OK atau Regulasi (jika ada regulasi beberapa menit sebelumnya) */}
              <span
                className={`text-[10px] font-bold px-1.5 py-0.5 rounded leading-none border flex items-center gap-1 ${
                  realtime.has_recent_regulation || realtime.combustion_badge === 'Regulasi'
                    ? 'text-amber-800 bg-amber-100/95 border-amber-300'
                    : 'text-emerald-800 bg-emerald-100/90 border-emerald-300'
                }`}
              >
                <span
                  className={`w-1.5 h-1.5 rounded-full ${
                    realtime.has_recent_regulation || realtime.combustion_badge === 'Regulasi'
                      ? 'bg-amber-500 animate-pulse'
                      : 'bg-emerald-500'
                  }`}
                />
                {realtime.combustion_badge || (realtime.has_recent_regulation ? 'Regulasi' : 'OK')}
              </span>
            </div>
            <div className="flex items-baseline justify-between gap-1 mt-1">
              {/* Temperature Ruang Bakar */}
              <div className="flex items-baseline gap-0.5">
                <span className="text-base sm:text-lg font-black text-slate-900 tabular-nums font-mono leading-none">
                  {realtime.temp_chamber != null ? Number(realtime.temp_chamber).toFixed(1) : '-'}
                </span>
                <span className="text-[10px] font-semibold text-slate-500">°C</span>
              </div>
              {/* Speed Ruang Bakar / Feeder */}
              <div className="flex items-baseline gap-1">
                <span className="text-[10px] font-semibold text-orange-800/80">Speed</span>
                <span className="text-xs sm:text-sm font-bold text-slate-900 tabular-nums font-mono leading-none">
                  {realtime.speed_coal != null ? Number(realtime.speed_coal).toFixed(1) : '-'}
                </span>
                <span className="text-[10px] font-semibold text-slate-500">Hz</span>
              </div>
            </div>
          </div>

          {/* 3. Regulasi */}
          <div className="bg-gradient-to-br from-white to-amber-50/80 border-2 border-amber-300 rounded-xl px-2.5 py-1.5 flex flex-col justify-between shadow-2xs">
            <div className="flex items-center justify-between gap-1 leading-none">
              <div className="flex items-center gap-1 text-amber-900 font-bold text-xs tracking-wide">
                <Sliders className="w-3.5 h-3.5 text-amber-600 shrink-0" />
                <span>REGULASI</span>
              </div>
              <span className="text-[10px] font-bold text-amber-700 bg-amber-100/90 border border-amber-200/60 px-1.5 py-0.5 rounded leading-none">
                ≤ {dailyKpi.regulation_max_speed} Hz
              </span>
            </div>
            <div className="flex items-baseline justify-between gap-1 mt-1">
              <div className="flex items-baseline gap-0.5">
                <span className="text-base sm:text-lg font-black text-slate-900 tabular-nums font-mono leading-none">
                  {dailyKpi.regulation_count ?? 0}
                </span>
                <span className="text-[10px] font-semibold text-slate-500">kali</span>
              </div>
              <span className="text-[10px] font-semibold text-slate-400">
                Hari ini
              </span>
            </div>
          </div>

          {/* 4. Drop (Heatmap Alert: Rose jika > 0, Emerald/Slate jika 0) */}
          <div className={`border rounded-xl px-2.5 py-1.5 flex flex-col justify-between shadow-2xs ${
            dailyKpi.drop_minutes > 0
              ? 'bg-rose-50/95 border-rose-200/90'
              : 'bg-emerald-50/90 border-emerald-200/80'
          }`}>
            <div className="flex items-center justify-between gap-1 leading-none">
              <div className={`flex items-center gap-1 font-bold text-xs tracking-wide ${
                dailyKpi.drop_minutes > 0 ? 'text-rose-900' : 'text-emerald-900'
              }`}>
                <TrendingDown className={`w-3.5 h-3.5 shrink-0 ${dailyKpi.drop_minutes > 0 ? 'text-rose-600' : 'text-emerald-600'}`} />
                <span>DROP</span>
              </div>
              <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded leading-none border ${
                dailyKpi.drop_minutes > 0
                  ? 'text-rose-700 bg-rose-100/90 border-rose-200/60'
                  : 'text-emerald-700 bg-emerald-100/90 border-emerald-200/60'
              }`}>
                &lt; {dailyKpi.drop_threshold} {isSteam ? 'bar' : '°C'}
              </span>
            </div>
            <div className="flex items-baseline justify-between gap-1 mt-1">
              <div className="flex items-baseline gap-0.5">
                <span className={`text-base sm:text-lg font-black tabular-nums font-mono leading-none ${
                  dailyKpi.drop_minutes > 0 ? 'text-rose-600' : 'text-slate-900'
                }`}>
                  {dailyKpi.drop_minutes ?? 0}
                </span>
                <span className="text-[10px] font-semibold text-slate-500">menit</span>
              </div>
              <span className={`text-[10px] font-bold truncate ${
                dailyKpi.drop_minutes > 0 ? 'text-rose-600' : 'text-emerald-600'
              }`}>
                {dailyKpi.drop_minutes > 0 ? 'Drop' : 'Aman'}
              </span>
            </div>
          </div>
        </div>
      </div>

      <div className="bg-white p-2.5 sm:p-5 rounded-2xl border border-slate-200/90 shadow-xs space-y-3">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-100 pb-3">
          <div>
            <h2 className="text-sm sm:text-base font-black text-slate-900 flex items-center gap-2">
              <Activity className={`w-4 h-4 ${isSteam ? 'text-sky-600' : 'text-amber-600'}`} />
              {isSteam ? 'Profil Tekanan Uap vs Pemakaian Uap Pabrik' : 'Profil Suhu Sirkulasi HTO vs Beban Panas Pabrik'}
            </h2>

          </div>
          <div className="flex items-center gap-3 text-xs font-semibold self-end sm:self-auto">
            <div className="flex items-center gap-1.5">
              <span className={`w-3 h-1 rounded-sm ${isSteam ? 'bg-sky-500' : 'bg-amber-500'}`} />
              <span className="text-slate-700">{isSteam ? 'Tekanan (bar)' : 'Suhu (°C)'}</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className={`w-3 h-1 rounded-sm ${isSteam ? 'bg-indigo-500' : 'bg-orange-500'}`} />
              <span className="text-slate-700">{isSteam ? 'Pemakaian (ton/jam)' : 'Beban (jt kcal)'}</span>
            </div>
          </div>
        </div>

        {/* Area Chart Container */}
        <div className="w-full h-[260px] sm:h-[320px] md:h-[360px]">
          {loading ? (
            <div className="w-full h-full flex flex-col items-center justify-center text-slate-400 gap-2">
              <RefreshCw className="w-6 h-6 animate-spin text-indigo-500" />
              <span className="text-xs font-semibold">Memuat data grafik...</span>
            </div>
          ) : chartData.length === 0 ? (
            <div className="w-full h-full flex items-center justify-center text-slate-400 text-xs">
              Belum ada data rekaman pada rentang waktu ini.
            </div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={chartData} margin={{ top: 10, right: 2, left: 2, bottom: 0 }}>
                <defs>
                  <linearGradient id="usageGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={isSteam ? '#6366f1' : '#f97316'} stopOpacity={0.35} />
                    <stop offset="95%" stopColor={isSteam ? '#6366f1' : '#f97316'} stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                <XAxis
                  dataKey="time"
                  tick={{ fontSize: 10, fill: '#64748b', fontWeight: 500 }}
                  tickLine={false}
                  axisLine={{ stroke: '#e2e8f0' }}
                  minTickGap={20}
                />
                {/* Y-Axis Kiri: Primary (Pressure / Oil Temp) - tanpa disingkat */}
                <YAxis
                  yAxisId="left"
                  domain={primaryDomain}
                  width={isSteam ? 42 : 46}
                  tick={{ fontSize: 10, fill: isSteam ? '#0284c7' : '#d97706', fontWeight: 500 }}
                  tickLine={false}
                  axisLine={{ stroke: '#e2e8f0' }}
                  tickFormatter={(val) => `${val} ${isSteam ? 'bar' : '°C'}`}
                />
                {/* Y-Axis Kanan: Usage (ton/jam / jt kcal) - tanpa disingkat */}
                <YAxis
                  yAxisId="right"
                  orientation="right"
                  domain={usageDomain}
                  width={isSteam ? 40 : 48}
                  tick={{ fontSize: 10, fill: isSteam ? '#4f46e5' : '#ea580c', fontWeight: 500 }}
                  tickLine={false}
                  axisLine={{ stroke: '#e2e8f0' }}
                  tickFormatter={(val) => `${val} ${isSteam ? 'ton' : 'jt'}`}
                />
                <Tooltip
                  content={<CustomPrimaryTooltip channel={channel} />}
                  cursor={{ stroke: '#94a3b8', strokeWidth: 1, strokeDasharray: '3 3' }}
                  wrapperStyle={{ pointerEvents: 'none', zIndex: 40 }}
                />

                {/* Garis Batas Ambang Drop */}
                {dailyKpi.drop_threshold && (
                  <ReferenceLine
                    yAxisId="left"
                    y={dailyKpi.drop_threshold}
                    stroke="#ef4444"
                    strokeDasharray="4 4"
                    label={{
                      value: `Batas Drop (${dailyKpi.drop_threshold} ${isSteam ? 'bar' : '°C'})`,
                      fill: '#ef4444',
                      fontSize: 10,
                      position: 'insideBottomLeft',
                    }}
                  />
                )}

                {/* Garis Batas Regulasi */}
                {dailyKpi.regulation_min_val && (
                  <ReferenceLine
                    yAxisId="left"
                    y={dailyKpi.regulation_min_val}
                    stroke="#f59e0b"
                    strokeDasharray="4 4"
                    label={{
                      value: `Min Regulasi (${dailyKpi.regulation_min_val} ${isSteam ? 'bar' : '°C'})`,
                      fill: '#d97706',
                      fontSize: 10,
                      position: 'insideTopLeft',
                    }}
                  />
                )}

                {/* Layer Pemakaian Pabrik (Area) */}
                <Area
                  yAxisId="right"
                  type="monotone"
                  dataKey="usage"
                  name={isSteam ? 'Pemakaian Uap (ton/jam)' : 'Beban Panas HTO (jt kcal)'}
                  stroke={isSteam ? '#6366f1' : '#f97316'}
                  strokeWidth={2}
                  fillOpacity={1}
                  fill="url(#usageGradient)"
                />

                {/* Layer Utama (Tekanan / Suhu) */}
                <Line
                  yAxisId="left"
                  type="monotone"
                  dataKey="primary_val"
                  name={isSteam ? 'Tekanan Steam (bar)' : 'Suhu HTO (°C)'}
                  stroke={isSteam ? '#0284c7' : '#d97706'}
                  strokeWidth={2.5}
                  dot={false}
                  activeDot={{ r: 5, strokeWidth: 2, stroke: '#ffffff' }}
                />
              </ComposedChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* ═══════════════════════════════════════════════════════════════════ */}
      {/* GRAFIK 2 (BAWAH): SPEED BATU BARA VS SUHU RUANG BAKAR               */}
      {/* ═══════════════════════════════════════════════════════════════════ */}
      <div className="bg-white p-2.5 sm:p-5 rounded-2xl border border-slate-200/90 shadow-xs space-y-3">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-100 pb-3">
          <div>
            <h2 className="text-sm sm:text-base font-black text-slate-900 flex items-center gap-2">
              <Cpu className="w-4 h-4 text-amber-600" />
              Kestabilan Pembakaran: Speed Batu Bara vs Suhu Ruang Bakar
            </h2>

          </div>
          <div className="flex items-center gap-3 text-xs font-semibold self-end sm:self-auto">
            <div className="flex items-center gap-1.5">
              <span className="w-3 h-1 rounded-sm bg-amber-500" />
              <span className="text-slate-700">Speed Feeder (Hz)</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-3 h-1 rounded-sm bg-rose-500" />
              <span className="text-slate-700">Suhu Ruang Bakar (°C)</span>
            </div>
          </div>
        </div>

        {/* Combustion Chart Container */}
        <div className="w-full h-[240px] sm:h-[300px] md:h-[340px]">
          {loading ? (
            <div className="w-full h-full flex flex-col items-center justify-center text-slate-400 gap-2">
              <RefreshCw className="w-6 h-6 animate-spin text-amber-500" />
              <span className="text-xs font-semibold">Memuat data pembakaran...</span>
            </div>
          ) : chartData.length === 0 ? (
            <div className="w-full h-full flex items-center justify-center text-slate-400 text-xs">
              Belum ada data rekaman pada rentang waktu ini.
            </div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={chartData} margin={{ top: 10, right: 2, left: 2, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                <XAxis
                  dataKey="time"
                  tick={{ fontSize: 10, fill: '#64748b', fontWeight: 500 }}
                  tickLine={false}
                  axisLine={{ stroke: '#e2e8f0' }}
                  minTickGap={20}
                />
                {/* Y-Axis Kiri: Speed Batu Bara (Hz) */}
                <YAxis
                  yAxisId="speed"
                  domain={speedDomain}
                  width={38}
                  tick={{ fontSize: 10, fill: '#d97706', fontWeight: 500 }}
                  tickLine={false}
                  axisLine={{ stroke: '#e2e8f0' }}
                  tickFormatter={(val) => `${val} Hz`}
                />
                {/* Y-Axis Kanan: Suhu Ruang Bakar (°C) */}
                <YAxis
                  yAxisId="temp"
                  orientation="right"
                  domain={tempDomain}
                  width={44}
                  tick={{ fontSize: 10, fill: '#e11d48', fontWeight: 500 }}
                  tickLine={false}
                  axisLine={{ stroke: '#e2e8f0' }}
                  tickFormatter={(val) => `${val} °C`}
                />
                <Tooltip
                  content={<CustomCombustionTooltip />}
                  cursor={{ stroke: '#94a3b8', strokeWidth: 1, strokeDasharray: '3 3' }}
                  wrapperStyle={{ pointerEvents: 'none', zIndex: 40 }}
                />

                {/* Garis Speed Feeder Batu Bara */}
                <Line
                  yAxisId="speed"
                  type="monotone"
                  dataKey="speed_coal"
                  name="Speed Batu Bara (Hz)"
                  stroke="#f59e0b"
                  strokeWidth={2}
                  dot={false}
                  activeDot={{ r: 4, stroke: '#ffffff', strokeWidth: 2 }}
                />

                {/* Garis Suhu Ruang Bakar */}
                <Line
                  yAxisId="temp"
                  type="monotone"
                  dataKey="temp_chamber"
                  name="Suhu Ruang Bakar (°C)"
                  stroke="#f43f5e"
                  strokeWidth={2.5}
                  dot={false}
                  activeDot={{ r: 5, stroke: '#ffffff', strokeWidth: 2 }}
                />
              </ComposedChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* ═══════════════════════════════════════════════════════════════════ */}
      {/* HISTORI REGULASI & DROP PRESSURE / TEMPERATURE                     */}
      {/* ═══════════════════════════════════════════════════════════════════ */}
      <div className="bg-white p-3 sm:p-5 rounded-2xl border border-slate-200/90 shadow-xs space-y-3">
        <div className="flex items-center justify-between border-b border-slate-100 pb-2.5">
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded-lg bg-slate-100 text-slate-700">
              <Clock className="w-4 h-4 text-slate-600" />
            </div>
            <div>
              <h2 className="text-sm sm:text-base font-bold text-slate-900 tracking-tight leading-none">
                Histori Regulasi & Drop {isSteam ? 'Pressure' : 'Temperature'}
              </h2>
              <span className="text-[10px] sm:text-xs text-slate-400 font-medium">
                Hari ini sejak {dailyKpi.boiler_day_start || '06:00'} WIB
              </span>
            </div>
          </div>
          <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 border border-slate-200">
            {historyEvents.length} Catatan
          </span>
        </div>

        {/* List of Events */}
        {historyEvents.length === 0 ? (
          <div className="py-6 px-4 text-center rounded-xl bg-slate-50/60 border border-dashed border-slate-200 flex flex-col items-center justify-center gap-1.5">
            <CheckCircle2 className="w-5 h-5 text-emerald-500" />
            <p className="text-xs font-medium text-slate-600">
              Tidak ada histori regulasi atau drop hari ini. Kondisi boiler stabil & normal.
            </p>
          </div>
        ) : (
          <div className="divide-y divide-slate-100 max-h-[380px] overflow-y-auto pr-1">
            {historyEvents.map((ev, idx) => {
              const isDrop = ev.type === 'DROP';
              return (
                <div
                  key={idx}
                  className="py-2.5 px-2 sm:px-3 flex items-center justify-between gap-3 hover:bg-slate-50/80 rounded-xl transition-colors"
                >
                  <div className="flex items-center gap-2 sm:gap-3 min-w-0">
                    {/* Jam (Pukul 08:25) */}
                    <div className="flex items-center gap-1 text-xs sm:text-sm font-bold font-mono text-slate-900 bg-slate-100 px-2 py-1 rounded-lg border border-slate-200/80 shrink-0">
                      <Clock className="w-3.5 h-3.5 text-slate-400" />
                      <span>{ev.time}</span>
                    </div>

                    {/* Badge Tipe: REGULASI / DROP */}
                    <span
                      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] sm:text-xs font-bold border shrink-0 ${
                        isDrop
                          ? 'bg-rose-50 text-rose-700 border-rose-200'
                          : 'bg-amber-50 text-amber-700 border-amber-200'
                      }`}
                    >
                      {isDrop ? <TrendingDown className="w-3 h-3" /> : <Sliders className="w-3 h-3" />}
                      {ev.type}
                    </span>

                    {/* Deskripsi Apa yang Terjadi */}
                    <span className="text-xs sm:text-sm font-semibold text-slate-800 truncate">
                      {ev.label}
                    </span>
                  </div>

                  {/* Keterangan Tambahan Nilai */}
                  <div className="text-[11px] sm:text-xs font-mono font-medium shrink-0">
                    {ev.peak_value != null && (
                      <span className="text-amber-700 bg-amber-50 px-1.5 py-0.5 rounded border border-amber-200/60">
                        Peak: {ev.peak_value} {isSteam ? 'bar' : '°C'}
                      </span>
                    )}
                    {ev.min_value != null && (
                      <span className="text-rose-700 bg-rose-50 px-1.5 py-0.5 rounded border border-rose-200/60">
                        Min: {ev.min_value} {isSteam ? 'bar' : '°C'}
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* ═══════════════════════════════════════════════════════════════════ */}
      {/* FOOTER QUICK LINKS: LAPORAN BOILER & KALENDER LENGKAP              */}
      {/* ═══════════════════════════════════════════════════════════════════ */}
      <div className="flex flex-wrap items-center justify-between gap-3 bg-white p-3.5 sm:p-4 rounded-xl border border-slate-200/80 text-xs text-slate-600">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-indigo-500" />
          <span>Ingin audit efisiensi atau SFC harian lengkap?</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => navigate('/boiler-report')}
            className="px-3 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-800 font-bold flex items-center gap-1 transition-all"
          >
            Buka Boiler Report
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => navigate('/boiler-calendar')}
            className="px-3 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-800 font-bold flex items-center gap-1 transition-all"
          >
            Buka Kalender Boiler
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
}
