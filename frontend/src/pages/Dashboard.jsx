import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useChartAnimation } from '../hooks/useChartAnimation';
import { useSmartPolling } from '../hooks/useSmartPolling';
import api from '../lib/api';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip,
  ResponsiveContainer, LineChart, Line, Legend, BarChart, Bar, Cell,
  ComposedChart, PieChart, Pie, ScatterChart, Scatter, ZAxis, ReferenceLine
} from 'recharts';
import {
  Activity, Droplet, Gauge, TrendingUp, TrendingDown, ArrowRight,
  Cpu, BarChart2, Clock, Zap, Flame, Thermometer, AlertCircle, RefreshCw,
  DollarSign, ChevronRight, CheckCircle2, AlertTriangle,
  Fuel, ChevronDown, ChevronUp, X, ExternalLink, Layers, Snowflake
} from 'lucide-react';
import { PHASE_COLORS } from '../lib/phaseColors';
import { getMachineTextileIcon } from '../components/TextileIcons';

// ── Helpers & Formatters ──────────────────────────────────────────────────
const formatNumber = (val, dec = 0) => {
  if (val == null || Number.isNaN(+val)) return '-';
  return Number(val).toLocaleString('id-ID', {
    minimumFractionDigits: dec,
    maximumFractionDigits: dec
  });
};

const formatCompactNumber = (val, dec = 1) => {
  if (val == null || Number.isNaN(+val)) return '-';
  const num = Number(val);
  if (num >= 1_000_000) return (num / 1_000_000).toFixed(dec) + 'M';
  if (num >= 1_000) return (num / 1_000).toFixed(dec) + 'k';
  return num.toFixed(dec);
};

const formatRp = (val) => {
  if (val == null || Number.isNaN(+val)) return 'Rp 0';
  const num = Number(val);
  if (Math.abs(num) >= 1_000_000_000) return `Rp ${(num / 1_000_000_000).toFixed(2)} M`;
  if (Math.abs(num) >= 1_000_000) return `Rp ${(num / 1_000_000).toFixed(1)} Jt`;
  if (Math.abs(num) >= 1_000) return `Rp ${Math.round(num / 1_000).toLocaleString('id-ID')} Rb`;
  return `Rp ${Math.round(num).toLocaleString('id-ID')}`;
};

const getLogicalTodayStr = () => {
  const d = new Date();
  if (d.getHours() < 6) d.setDate(d.getDate() - 1);
  return d.toISOString().split('T')[0];
};

const normalizeStatus = (status) => {
  const s = (status || 'OFF').toUpperCase();
  if (s === 'STOP' || s === 'OFFLINE') return 'OFF';
  if (s === 'NO SIGNAL' || s === 'NOSIGNAL') return 'NOSIGNAL';
  if (s === 'RUNNING') return 'RUNNING';
  return s;
};

function processBarColor(count, maxVal = 10) {
  const ratio = Math.min(1, Math.max(0, count / (maxVal || 1)));
  if (ratio >= 0.8) return '#059669'; // emerald-600
  if (ratio >= 0.6) return '#10b981'; // emerald-500
  if (ratio >= 0.4) return '#0ea5e9'; // sky-500
  if (ratio >= 0.2) return '#38bdf8'; // sky-400
  if (ratio > 0) return '#94a3b8';   // slate-400
  return '#e2e8f0';
}

const GRADE_BADGE = {
  A: 'bg-emerald-100 text-emerald-800 border-emerald-200',
  B: 'bg-sky-100 text-sky-800 border-sky-200',
  C: 'bg-amber-100 text-amber-800 border-amber-200',
  D: 'bg-rose-100 text-rose-800 border-rose-200',
};

// ── Section Card Component ────────────────────────────────────────────────
function SectionCard({ title, subtitle, icon: Icon, action, children, className = '', id, headerBorder = true }) {
  return (
    <div id={id} className={`bg-white rounded-2xl border border-slate-200/80 shadow-xs overflow-hidden transition-all duration-200 ${className}`}>
      {(title || action) && (
        <div className={`px-4 sm:px-5 py-3 sm:py-3.5 flex flex-wrap items-center justify-between gap-2.5 ${headerBorder ? 'border-b border-slate-100' : ''}`}>
          <div className="flex items-center gap-2.5">
            {Icon && (
              <div className="w-7 h-7 sm:w-8 sm:h-8 rounded-lg bg-slate-50 border border-slate-200/60 flex items-center justify-center text-slate-700 shrink-0">
                <Icon size={15} />
              </div>
            )}
            <div>
              {title && <h3 className="text-sm sm:text-base font-bold text-slate-900 leading-tight">{title}</h3>}
              {subtitle && <p className="text-xs text-slate-400 mt-0.5">{subtitle}</p>}
            </div>
          </div>
          {action && <div className="shrink-0">{action}</div>}
        </div>
      )}
      {children}
    </div>
  );
}

// ── Ultra-Compact Running Machine Summary HUD ──────────────────────────────
function RunningMachineSummaryCompact({ data }) {
  if (!data) return null;
  const { steam, hto } = data;
  const totalRunning = (steam?.continuous?.running || 0) + (steam?.jd_jr?.running || 0) +
                       (hto?.processing?.running || 0) + (hto?.printing?.running || 0);
  const totalMachines = (steam?.continuous?.total || 0) + (steam?.jd_jr?.total || 0) +
                        (hto?.processing?.total || 0) + (hto?.printing?.total || 0);

  return (
    <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs px-3.5 py-2.5 sm:px-4 sm:py-3">
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
        <div className="flex items-center gap-2 shrink-0">
          <span className="relative flex h-2.5 w-2.5">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500" />
          </span>
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold text-slate-900">Mesin Berjalan:</span>
            <span className="text-xs font-black text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200/60 tabular-nums">
              {totalRunning} / {totalMachines} Aktif
            </span>
          </div>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 flex-1 max-w-4xl">
          <div className="bg-sky-50/60 border border-sky-100/80 rounded-xl px-2.5 py-1.5 flex items-center justify-between">
            <span className="text-[10px] font-bold text-sky-700 uppercase tracking-tight truncate">Uap Cont</span>
            <span className="text-xs font-black text-sky-900 tabular-nums ml-1">
              {steam?.continuous?.running ?? 0}<span className="text-sky-400 font-normal">/{steam?.continuous?.total ?? 0}</span>
            </span>
          </div>

          <div className="bg-sky-50/60 border border-sky-100/80 rounded-xl px-2.5 py-1.5 flex items-center justify-between">
            <span className="text-[10px] font-bold text-sky-700 uppercase tracking-tight truncate">Uap JD+JR</span>
            <span className="text-xs font-black text-sky-900 tabular-nums ml-1">
              {steam?.jd_jr?.running ?? 0}<span className="text-sky-400 font-normal">/{steam?.jd_jr?.total ?? 0}</span>
            </span>
          </div>

          <div className="bg-amber-50/60 border border-amber-100/80 rounded-xl px-2.5 py-1.5 flex items-center justify-between">
            <span className="text-[10px] font-bold text-amber-700 uppercase tracking-tight truncate">HTO Proc</span>
            <span className="text-xs font-black text-amber-900 tabular-nums ml-1">
              {hto?.processing?.running ?? 0}<span className="text-amber-400 font-normal">/{hto?.processing?.total ?? 0}</span>
            </span>
          </div>

          <div className="bg-amber-50/60 border border-amber-100/80 rounded-xl px-2.5 py-1.5 flex items-center justify-between">
            <span className="text-[10px] font-bold text-amber-700 uppercase tracking-tight truncate">HTO Print</span>
            <span className="text-xs font-black text-amber-900 tabular-nums ml-1">
              {hto?.printing?.running ?? 0}<span className="text-amber-400 font-normal">/{hto?.printing?.total ?? 0}</span>
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Phase Duration Bar & Breakdown Pill Component ─────────────────────────
function PhaseDurationBreakdown({ machine, highlightMode = 'steam' }) {
  const heatAct = machine.avg_heat_actual || 0;
  const heatIdl = machine.avg_heat_ideal || 0;
  const keepAct = machine.avg_keep_actual || 0;
  const keepIdl = machine.avg_keep_ideal || 0;
  const coolAct = machine.avg_cool_actual || 0;
  const coolIdl = machine.avg_cool_ideal || 0;

  const dHeat = machine.avg_delta_heat || 0;
  const dKeep = machine.avg_delta_steady || 0;
  const dCool = machine.avg_delta_cool || 0;

  const totalAct = Math.max(1, heatAct + keepAct + coolAct);
  const heatPct = Math.round((heatAct / totalAct) * 100);
  const keepPct = Math.round((keepAct / totalAct) * 100);
  const coolPct = Math.max(0, 100 - heatPct - keepPct);

  return (
    <div className="mt-2.5 pt-2.5 border-t border-slate-100 space-y-2">
      {/* Stacked Visual Phase Bar */}
      <div>
        <div className="flex justify-between items-center text-[10px] text-slate-500 mb-1">
          <span className="font-semibold text-slate-600">
            Proporsi Durasi Siklus Rata-rata ({Math.round(heatAct + keepAct + coolAct)}m aktual vs {Math.round(heatIdl + keepIdl + coolIdl)}m ideal)
          </span>
          <span className="font-mono text-[10px] text-slate-400">
            {machine.evaluated_batches_count} batch
          </span>
        </div>
        <div className="h-2.5 w-full rounded-full bg-slate-100 overflow-hidden flex p-0.5 gap-0.5">
          <div
            style={{ width: `${heatPct}%` }}
            className="h-full bg-rose-500 rounded-l-full transition-all"
            title={`Heating: ${heatAct}m (Ideal ${heatIdl}m)`}
          />
          <div
            style={{ width: `${keepPct}%` }}
            className="h-full bg-amber-500 transition-all"
            title={`Keep/Holding: ${keepAct}m (Ideal ${keepIdl}m)`}
          />
          <div
            style={{ width: `${coolPct}%` }}
            className="h-full bg-sky-500 rounded-r-full transition-all"
            title={`Cooling: ${coolAct}m (Ideal ${coolIdl}m)`}
          />
        </div>
      </div>

      {/* 3 Phase Pills: Heating, Keep, Cooling */}
      <div className="grid grid-cols-3 gap-1.5 text-[10px]">
        {/* Heating */}
        <div className={`px-2 py-1.5 rounded-lg border ${
          dHeat > 10
            ? 'bg-rose-50/80 border-rose-200/80 text-rose-900'
            : 'bg-slate-50 border-slate-100 text-slate-700'
        }`}>
          <div className="flex items-center justify-between">
            <span className="font-bold flex items-center gap-1 text-rose-600">
              <span className="w-1.5 h-1.5 rounded-full bg-rose-500" /> Heating
            </span>
            <span className={`font-black tabular-nums ${dHeat > 5 ? 'text-rose-600' : 'text-emerald-600'}`}>
              {dHeat > 0 ? `+${dHeat}m` : `${dHeat}m`}
            </span>
          </div>
          <div className="text-[10px] text-slate-500 mt-0.5 tabular-nums">
            <strong className="text-slate-800">{heatAct}m</strong> <span className="text-slate-400">/ idl {heatIdl}m</span>
          </div>
        </div>

        {/* Keep / Steady */}
        <div className={`px-2 py-1.5 rounded-lg border ${
          dKeep > 10
            ? 'bg-amber-50/80 border-amber-200/80 text-amber-900'
            : 'bg-slate-50 border-slate-100 text-slate-700'
        }`}>
          <div className="flex items-center justify-between">
            <span className="font-bold flex items-center gap-1 text-amber-600">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-500" /> Keep
            </span>
            <span className={`font-black tabular-nums ${dKeep > 5 ? 'text-amber-600' : 'text-emerald-600'}`}>
              {dKeep > 0 ? `+${dKeep}m` : `${dKeep}m`}
            </span>
          </div>
          <div className="text-[10px] text-slate-500 mt-0.5 tabular-nums">
            <strong className="text-slate-800">{keepAct}m</strong> <span className="text-slate-400">/ idl {keepIdl}m</span>
          </div>
        </div>

        {/* Cooling */}
        <div className={`px-2 py-1.5 rounded-lg border ${
          dCool > 10 && highlightMode === 'power'
            ? 'bg-sky-50/90 border-sky-200 text-sky-900'
            : dCool > 10
            ? 'bg-amber-50/60 border-amber-200/60 text-slate-800'
            : 'bg-slate-50 border-slate-100 text-slate-700'
        }`}>
          <div className="flex items-center justify-between">
            <span className="font-bold flex items-center gap-1 text-sky-600">
              <span className="w-1.5 h-1.5 rounded-full bg-sky-500" /> Cooling
            </span>
            <span className={`font-black tabular-nums ${dCool > 5 ? 'text-rose-600' : 'text-emerald-600'}`}>
              {dCool > 0 ? `+${dCool}m` : `${dCool}m`}
            </span>
          </div>
          <div className="text-[10px] text-slate-500 mt-0.5 tabular-nums">
            <strong className="text-slate-800">{coolAct}m</strong> <span className="text-slate-400">/ idl {coolIdl}m</span>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Custom Tooltip for Boiler Report ──────────────────────────────────────
const BoilerTooltip = ({ active, payload, label }) => {
  if (active && payload && payload.length) {
    return (
      <div className="bg-white/95 backdrop-blur-sm p-3 border border-slate-200 shadow-lg rounded-xl text-xs z-30">
        <p className="font-bold text-slate-800 mb-1.5 pb-1 border-b border-slate-100">{label}</p>
        <div className="space-y-1">
          {payload.map((entry, index) => (
            <div key={index} className="flex items-center justify-between gap-3 text-[11px]">
              <div className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full" style={{ backgroundColor: entry.color }} />
                <span className="text-slate-600">{entry.name}:</span>
              </div>
              <span className="font-bold tabular-nums" style={{ color: entry.color }}>
                {entry.value !== null && entry.value !== undefined ? formatNumber(entry.value, 1) : '-'}
              </span>
            </div>
          ))}
        </div>
      </div>
    );
  }
  return null;
};

export default function Dashboard() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const isAnimActive = useChartAnimation();

  // Responsive state
  const [isMobile, setIsMobile] = useState(window.innerWidth < 768);
  useEffect(() => {
    const handleResize = () => setIsMobile(window.innerWidth < 768);
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // Main Dashboard states
  const [trafficData, setTrafficData] = useState(null);
  const [machinesData, setMachinesData] = useState(null);
  const [energyCondition, setEnergyCondition] = useState([]);
  const [runningSummary, setRunningSummary] = useState(null);
  const [initialLoadError, setInitialLoadError] = useState(null);

  // Time-range switches
  const [steamDays, setSteamDays] = useState(30);
  const [processDays, setProcessDays] = useState(30);

  // Historical & Context states
  const [steamSalesData, setSteamSalesData] = useState(null);
  const [processesData, setProcessesData] = useState({ groups: [] });
  const [processSummary30d, setProcessSummary30d] = useState(null);

  // Boiler Report Data (Steam Analysis, HTO Analysis, Distributions, Alert History)
  const [boilerReport, setBoilerReport] = useState(null);
  const [alertFilter, setAlertFilter] = useState('Semua');
  const [boilerAnalysisTab, setBoilerAnalysisTab] = useState('steam'); // 'steam' | 'hto'

  // Machine Health & Energy Waste Analytics State
  const [fleetWindow, setFleetWindow] = useState('7D'); // '1D' | '7D' | '30D'
  const [fleetHealthData, setFleetHealthData] = useState(null);
  const [fleetHealthLoading, setFleetHealthLoading] = useState(false);
  const [expandedSteamMachineId, setExpandedSteamMachineId] = useState(null);
  const [expandedPowerMachineId, setExpandedPowerMachineId] = useState(null);

  // Compact Active Machines view state
  const [compactMachineFilter, setCompactMachineFilter] = useState('all'); // 'all' | 'steam' | 'hto'
  const [compactMachinesExpanded, setCompactMachinesExpanded] = useState(false);

  // Modals States
  const [selectedMachineId, setSelectedMachineId] = useState(null);
  const [machineDetail, setMachineDetail] = useState(null);
  const [machineDetailLoading, setMachineDetailLoading] = useState(false);
  const [machineDetailError, setMachineDetailError] = useState(null);
  const [isModalOpen, setIsModalOpen] = useState(false);

  // ── Data Fetching ────────────────────────────────────────────────────────
  const fetchFastData = useCallback(async (isManualRetry = false) => {
    try {
      if (isManualRetry) setInitialLoadError(null);
      const [traffic, machines, energyRes, runningSummaryRes] = await Promise.all([
        api.get('/dashboard/steam-traffic'),
        api.get('/dashboard/active-machines'),
        api.get('/dashboard/energy-condition').catch((err) => {
          console.warn('Gagal memuat energy condition:', err);
          return { data: { data: [] } };
        }),
        api.get('/dashboard/running-summary').catch((err) => {
          console.warn('Gagal memuat running summary:', err);
          return { data: null };
        }),
      ]);
      setTrafficData(traffic.data);
      setMachinesData(machines.data);
      setEnergyCondition(energyRes.data?.data || []);
      setRunningSummary(runningSummaryRes.data);
      setInitialLoadError(null);
    } catch (err) {
      console.error('Gagal mengambil fast data dashboard:', err);
      if (!trafficData || !machinesData) {
        setInitialLoadError(err?.message || 'Gagal mengambil data dashboard dari server.');
      }
    }
  }, [trafficData, machinesData]);

  const fetchSlowData = useCallback(async () => {
    try {
      const todayStr = getLogicalTodayStr();
      const [salesRes, processesRes, summary30dRes, boilerRes, fleetRes] = await Promise.all([
        api.get(`/dashboard/steam-sales?days=${steamDays}`).catch(() => ({ data: null })),
        api.get(`/dashboard/daily-processes?days=${processDays}`).catch(() => ({ data: null })),
        api.get('/dashboard/process-summary-30d').catch(() => ({ data: null })),
        api.get(`/report/boiler-summary?date=${todayStr}`).catch(() => ({ data: null })),
        api.get(`/dashboard/fleet-health-waste?window=${fleetWindow}`).catch(() => ({ data: null })),
      ]);

      if (salesRes?.data) setSteamSalesData(salesRes.data);
      if (processesRes?.data) setProcessesData(processesRes.data);
      if (summary30dRes?.data) setProcessSummary30d(summary30dRes.data);
      if (boilerRes?.data && !boilerRes.data.error) setBoilerReport(boilerRes.data);
      if (fleetRes?.data) setFleetHealthData(fleetRes.data);
    } catch (err) {
      console.error('Gagal mengambil slow data dashboard:', err);
    }
  }, [steamDays, processDays, fleetWindow]);

  // Re-fetch on days or window change
  useEffect(() => {
    api.get(`/dashboard/steam-sales?days=${steamDays}`)
      .then((res) => res.data && setSteamSalesData(res.data))
      .catch((err) => console.warn(err));
  }, [steamDays]);

  useEffect(() => {
    api.get(`/dashboard/daily-processes?days=${processDays}`)
      .then((res) => res.data && setProcessesData(res.data))
      .catch((err) => console.warn(err));
  }, [processDays]);

  useEffect(() => {
    setFleetHealthLoading(true);
    api.get(`/dashboard/fleet-health-waste?window=${fleetWindow}`)
      .then((res) => {
        if (res.data) setFleetHealthData(res.data);
      })
      .catch((err) => console.warn(err))
      .finally(() => setFleetHealthLoading(false));
  }, [fleetWindow]);

  useSmartPolling(fetchFastData, 30000);
  useSmartPolling(fetchSlowData, 300000);

  // Machine Detail Modal Action (with Real-Time Telemetry Chart)
  const openMachineDetail = async (id) => {
    setSelectedMachineId(id);
    setIsModalOpen(true);
    setMachineDetail(null);
    setMachineDetailError(null);
    setMachineDetailLoading(true);
    try {
      const res = await api.get(`/dashboard/machine/${id}/detail`, { cache: false });
      setMachineDetail(res.data);
    } catch (err) {
      setMachineDetailError('Gagal memuat detail telemetri mesin.');
    } finally {
      setMachineDetailLoading(false);
    }
  };

  // Navigate to Machine Daily Analytics page
  const goToMachineAnalytics = (machineId) => {
    if (!machineId) return;
    navigate(`/machine-daily-analytics/${machineId}/${getLogicalTodayStr()}`);
  };

  // Navigate to Machine Daily Report page (directly focused on target machine with drawer opened)
  const goToMachineReport = (machineId, tab = 'programs') => {
    if (!machineId) return;
    navigate(`/machine-daily-report?machineId=${machineId}&window=${fleetWindow}&tab=${tab}`);
  };

  const scrollToSection = (id) => {
    const el = document.getElementById(id);
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  // ── Memoized Fleet Health & Waste Rankings ───────────────────────────────
  const fleetMachines = fleetHealthData?.machines || [];
  const fleetKpi = fleetHealthData?.fleet_kpi || null;

  const healthMatrixData = useMemo(() => {
    return fleetMachines.map((m) => ({
      x: m.health_score,
      y: Math.round((m.avg_waste_rp_batch || 0) / 1000),
      z: m.evaluated_batches_count || 1,
      name: m.machine_name,
      grade: m.health_grade,
      id: m.machine_id,
      waste_rp: m.avg_waste_rp_batch || 0,
      waste_30d: m.projected_30d_rp || 0,
    }));
  }, [fleetMachines]);

  const topWasteMachines = useMemo(() => {
    return [...fleetMachines]
      .sort((a, b) => (b.projected_30d_rp || 0) - (a.projected_30d_rp || 0))
      .slice(0, 10)
      .map((m) => ({
        name: m.machine_name,
        id: m.machine_id,
        grade: m.health_grade,
        waste_jt: Math.round(((m.projected_30d_rp || 0) / 1_000_000) * 10) / 10,
        steam_ton: Math.round(((m.projected_30d_steam_kg || 0) / 1000) * 10) / 10,
        power_kwh: Math.round(m.projected_30d_power_kwh || 0),
      }));
  }, [fleetMachines]);

  // Top Steam Wasteful Machines (sorted by actual + projected steam waste)
  const topSteamWasteList = useMemo(() => {
    return [...fleetMachines]
      .filter((m) => (m.evaluated_batches_count || 0) > 0)
      .sort((a, b) => (b.waste_steam_kg || 0) - (a.waste_steam_kg || 0))
      .slice(0, 6);
  }, [fleetMachines]);

  // Top Electricity Wasteful Machines (sorted by actual + projected power waste kWh)
  const topPowerWasteList = useMemo(() => {
    return [...fleetMachines]
      .filter((m) => (m.evaluated_batches_count || 0) > 0)
      .sort((a, b) => (b.waste_power_kwh || 0) - (a.waste_power_kwh || 0))
      .slice(0, 6);
  }, [fleetMachines]);

  // ── Render Fallbacks ──────────────────────────────────────────────────────
  if (initialLoadError && (!trafficData || !machinesData)) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] p-8 text-center max-w-md mx-auto">
        <div className="w-12 h-12 rounded-full bg-rose-50 flex items-center justify-center text-rose-500 mb-4 border border-rose-200">
          <AlertCircle className="w-6 h-6" />
        </div>
        <h3 className="text-base font-semibold text-slate-800 mb-1">Gagal Menghubungkan ke Server</h3>
        <p className="text-xs text-slate-500 mb-5 leading-relaxed">
          Koneksi ke server terputus atau sesi telah berakhir. Silakan coba muat ulang.
        </p>
        <button
          onClick={() => {
            fetchFastData(true);
            fetchSlowData();
          }}
          className="inline-flex items-center gap-2 px-4 py-2 bg-sky-600 hover:bg-sky-700 text-white text-xs font-semibold rounded-xl shadow-xs transition-colors"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          Muat Ulang Sekarang
        </button>
      </div>
    );
  }

  if (!trafficData || !machinesData) {
    return (
      <div className="flex flex-col items-center justify-center h-full p-8 text-slate-500 gap-3">
        <div className="w-10 h-10 border-2 border-sky-500 border-t-transparent rounded-full animate-spin" />
        <p className="text-sm font-medium">Memuat Dashboard Real-time...</p>
      </div>
    );
  }

  // Active machines calculations
  const rawActiveMachines = machinesData.table_data || [];
  const coolingMachines = rawActiveMachines.filter((m) => normalizeStatus(m.status) === 'COOL');
  const energyActive = machinesData.energy_active || { total: 0, steam: 0, hto: 0 };
  const energyCoolingOff = machinesData.energy_cooling_off || { total: 0, steam: 0, hto: 0, cooling: 0, off: 0 };
  const coolingCount = energyCoolingOff.cooling ?? coolingMachines.length;

  const filteredActiveMachines = rawActiveMachines.filter((m) => {
    const statusKey = normalizeStatus(m.status);
    if (compactMachineFilter === 'cooling') return statusKey === 'COOL';
    if (compactMachineFilter === 'steam') return (m.steam || 0) > 0 && statusKey !== 'COOL';
    if (compactMachineFilter === 'hto') return (m.hto || 0) > 0 && statusKey !== 'COOL';
    return true;
  });

  // Max value for process bar color scale
  const maxProcessCount = Math.max(
    10,
    ...processesData.groups.flatMap((g) => g.machines.map((m) => m.process_count || 0))
  );

  // ── Boiler Report Calculations ───────────────────────────────────────────
  const boilerChartData = boilerReport?.chart_data || [];
  const alertHistory = boilerReport?.alert_history || [];
  const fuelConfig = boilerReport?.fuel_config || {};

  // 1. Distribusi Tekanan Uap
  const totalPressure = (boilerReport?.pressure_dist?.ideal || 0) +
                        (boilerReport?.pressure_dist?.under || 0) +
                        (boilerReport?.pressure_dist?.over || 0);
  const getPressurePct = (val) => totalPressure > 0 ? Number(((val / totalPressure) * 100).toFixed(1)) : 0;
  const pressurePieData = [
    { name: 'Ideal (3.5-5.5 Bar)', value: getPressurePct(boilerReport?.pressure_dist?.ideal || 0), count: boilerReport?.pressure_dist?.ideal || 0, color: '#10b981' },
    { name: 'Under (<3.5 Bar)', value: getPressurePct(boilerReport?.pressure_dist?.under || 0), count: boilerReport?.pressure_dist?.under || 0, color: '#f59e0b' },
    { name: 'Over (>5.5 Bar)', value: getPressurePct(boilerReport?.pressure_dist?.over || 0), count: boilerReport?.pressure_dist?.over || 0, color: '#ef4444' },
  ];

  // 2. Distribusi Suhu HTO (Target Operasional: 240 - 275 °C)
  const validHtoTemps = boilerChartData.map((d) => d.Oil_Temp).filter((t) => t != null && t > 0);
  let htoDist = { ideal: 0, under: 0, over: 0 };
  validHtoTemps.forEach((t) => {
    if (t < 240) htoDist.under += 1;
    else if (t > 275) htoDist.over += 1;
    else htoDist.ideal += 1;
  });
  const totalHtoTemps = validHtoTemps.length || 1;
  const htoPieData = [
    { name: 'Ideal (240-275°C)', value: Number(((htoDist.ideal / totalHtoTemps) * 100).toFixed(1)), count: htoDist.ideal, color: '#10b981' },
    { name: 'Under (<240°C)', value: Number(((htoDist.under / totalHtoTemps) * 100).toFixed(1)), count: htoDist.under, color: '#f59e0b' },
    { name: 'Over (>275°C)', value: Number(((htoDist.over / totalHtoTemps) * 100).toFixed(1)), count: htoDist.over, color: '#ef4444' },
  ];

  // 3. Stabilitas Pemakaian (Demand) Harian Histogram & Stats
  let usageHistogram = [];
  const validUsages = boilerChartData.map((d) => d.steam_usage).filter((u) => u > 0);
  let statsUsage = { mean: '0', sd: '0', cv: '0', skewness: '0', label: 'Normal', scoreValue: 0, reasons: [] };

  if (validUsages.length > 0) {
    const minU = Math.floor(Math.min(...validUsages));
    const maxU = Math.ceil(Math.max(...validUsages));
    const binCount = 10;
    const binSize = (maxU - minU) / binCount || 1;

    const bins = Array(binCount).fill(0).map((_, i) => ({
      rangeStart: minU + (i * binSize),
      rangeEnd: minU + ((i + 1) * binSize),
      name: `${Math.round(minU + (i * binSize))}-${Math.round(minU + ((i + 1) * binSize))}`,
      count: 0
    }));

    validUsages.forEach((u) => {
      let placed = false;
      for (let i = 0; i < binCount - 1; i++) {
        if (u >= bins[i].rangeStart && u < bins[i].rangeEnd) {
          bins[i].count += 1;
          placed = true;
          break;
        }
      }
      if (!placed) bins[binCount - 1].count += 1;
    });
    usageHistogram = bins;

    const sum = validUsages.reduce((a, b) => a + b, 0);
    const mean = sum / validUsages.length;
    const squaredDiffs = validUsages.map((v) => Math.pow(v - mean, 2));
    const variance = squaredDiffs.reduce((a, b) => a + b, 0) / validUsages.length;
    const sd = Math.sqrt(variance);
    const cv = mean > 0 ? (sd / mean) * 100 : 0;

    let skewness = 0;
    if (sd > 0) {
      const cubedDiffs = validUsages.map((v) => Math.pow((v - mean) / sd, 3));
      skewness = cubedDiffs.reduce((a, b) => a + b, 0) / validUsages.length;
    }

    let points = 0;
    let reasons = [];
    if (cv >= 30) { points += 2; reasons.push(`CV tinggi (${cv.toFixed(1)}%)`); }
    else if (cv >= 15) { points += 1; }

    const absSkew = Math.abs(skewness);
    if (absSkew > 1.5) { points += 2; reasons.push(`Asimetris ekstrem (Skew: ${skewness.toFixed(2)})`); }
    else if (absSkew > 0.8) { points += 1; }

    const SD_MAX = 600;
    if (sd > SD_MAX * 2) { points += 2; reasons.push(`SD melebihi batas 2x toleransi (${sd.toFixed(0)} kg/h)`); }
    else if (sd > SD_MAX) { points += 1; }

    let label = 'Sangat Stabil';
    let scoreValue = 0;
    if (points >= 4) { label = 'Fluktuatif'; scoreValue = 2; }
    else if (points >= 2) { label = 'Normal'; scoreValue = 1; }

    if (reasons.length === 0) {
      if (points > 0) reasons.push('Beberapa parameter berada di batas moderat');
      else reasons.push('Semua parameter dalam batas ideal');
    }

    statsUsage = {
      mean: mean.toFixed(1),
      sd: sd.toFixed(1),
      cv: cv.toFixed(1),
      skewness: skewness.toFixed(2),
      label,
      reasons,
      scoreValue
    };
  }

  // 4. Filtered Alerts
  const filteredAlerts = alertHistory.filter((a) => {
    if (alertFilter === 'Semua') return true;
    if (alertFilter === 'Regulasi') return a.alert_type === 'REGULATION';
    return a.severity === alertFilter.toUpperCase() && a.alert_type !== 'REGULATION';
  });

  return (
    <div id="dashboard-scroll-container" className="h-full overflow-y-auto bg-slate-50/80 pb-24 md:pb-8">
      <div className="max-w-[1720px] mx-auto p-3 sm:p-4 md:p-6 space-y-6">

        {/* ═══════════════════════════════════════════════════════════════════════════ */}
        {/* BAGIAN ATAS: 3-SECTION GRID (Section Tengah 2/3 | Section Kanan 1/3)        */}
        {/* ═══════════════════════════════════════════════════════════════════════════ */}
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-6 items-start">

          {/* ========================================================================= */}
          {/* SECTION TENGAH / UTAMA (2/3 Width on Desktop xl:col-span-2)               */}
          {/* ========================================================================= */}
          <div className="xl:col-span-2 space-y-5 sm:space-y-6">

            {/* 1. HEADER SECTION UTAMA: HANYA 4 KPI CARD REAL-TIME */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
              {/* CARD 1: PEMAKAIAN UAP */}
              <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs p-3.5 sm:p-4 flex items-center gap-3 transition-all hover:shadow-sm">
                <div className="w-10 h-10 sm:w-11 sm:h-11 rounded-xl bg-sky-50 text-sky-600 border border-sky-100 flex items-center justify-center shrink-0">
                  <Droplet size={20} />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-[10px] sm:text-[11px] font-bold text-slate-500 uppercase tracking-wider truncate">
                    PEMAKAIAN UAP
                  </p>
                  <div className="mt-0.5 flex items-baseline gap-1 leading-tight">
                    <span className="text-xl sm:text-2xl font-black text-slate-900 tabular-nums">
                      {formatNumber(trafficData.current_usage)}
                    </span>
                    <span className="text-xs font-semibold text-slate-400">kg/h</span>
                  </div>
                </div>
              </div>

              {/* CARD 2: PEMAKAIAN HTO */}
              <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs p-3.5 sm:p-4 flex items-center gap-3 transition-all hover:shadow-sm">
                <div className="w-10 h-10 sm:w-11 sm:h-11 rounded-xl bg-rose-50 text-rose-600 border border-rose-100 flex items-center justify-center shrink-0">
                  <Flame size={20} />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-[10px] sm:text-[11px] font-bold text-slate-500 uppercase tracking-wider truncate">
                    PEMAKAIAN HTO
                  </p>
                  <div className="mt-0.5 flex items-baseline gap-1 leading-tight">
                    <span className="text-xl sm:text-2xl font-black text-slate-900 tabular-nums">
                      {formatCompactNumber(trafficData.current_hto ?? 0, 1)}
                    </span>
                    <span className="text-xs font-semibold text-slate-400">kCal/h</span>
                  </div>
                </div>
              </div>

              {/* CARD 3: SUHU HTO */}
              <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs p-3.5 sm:p-4 flex items-center gap-3 transition-all hover:shadow-sm">
                <div className="w-10 h-10 sm:w-11 sm:h-11 rounded-xl bg-amber-50 text-amber-600 border border-amber-100 flex items-center justify-center shrink-0">
                  <Thermometer size={20} />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-[10px] sm:text-[11px] font-bold text-slate-500 uppercase tracking-wider truncate">
                    SUHU HTO
                  </p>
                  <div className="mt-0.5 flex items-baseline gap-1 leading-tight">
                    <span className="text-xl sm:text-2xl font-black text-slate-900 tabular-nums">
                      {formatNumber(trafficData.current_oil_temp ?? 0, 1)}
                    </span>
                    <span className="text-xs font-semibold text-slate-400">°C</span>
                  </div>
                </div>
              </div>

              {/* CARD 4: TEKANAN UAP */}
              <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs p-3.5 sm:p-4 flex items-center gap-3 transition-all hover:shadow-sm">
                <div className="w-10 h-10 sm:w-11 sm:h-11 rounded-xl bg-violet-50 text-violet-600 border border-violet-100 flex items-center justify-center shrink-0">
                  <Gauge size={20} />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-[10px] sm:text-[11px] font-bold text-slate-500 uppercase tracking-wider truncate">
                    TEKANAN UAP
                  </p>
                  <div className="mt-0.5 flex items-baseline gap-1 leading-tight">
                    <span className="text-xl sm:text-2xl font-black text-slate-900 tabular-nums">
                      {formatNumber(trafficData.current_pressure, 2)}
                    </span>
                    <span className="text-xs font-semibold text-slate-400">bar</span>
                  </div>
                </div>
              </div>
            </div>

            {/* 2. FEATURE QUICK-NAV (Mobile only < md) */}
            <div className="md:hidden flex overflow-x-auto gap-3 py-1 px-1 hide-scrollbar snap-x">
              <div className="flex flex-col items-center min-w-[72px] snap-start cursor-pointer group" onClick={() => scrollToSection('section-active-machines')}>
                <div className="w-11 h-11 rounded-xl bg-sky-50 text-sky-600 flex items-center justify-center mb-1.5 group-active:scale-95 transition-transform border border-sky-100">
                  <Cpu size={18} />
                </div>
                <div className="text-[10px] font-medium text-slate-600 text-center leading-tight">Mesin Aktif</div>
              </div>
              <div className="flex flex-col items-center min-w-[72px] snap-start cursor-pointer group" onClick={() => scrollToSection('section-boiler-analysis')}>
                <div className="w-11 h-11 rounded-xl bg-amber-50 text-amber-600 flex items-center justify-center mb-1.5 group-active:scale-95 transition-transform border border-amber-100">
                  <Flame size={18} />
                </div>
                <div className="text-[10px] font-medium text-slate-600 text-center leading-tight">Analisis Boiler</div>
              </div>
              <div className="flex flex-col items-center min-w-[72px] snap-start cursor-pointer group" onClick={() => scrollToSection('section-fleet-health')}>
                <div className="w-11 h-11 rounded-xl bg-rose-50 text-rose-600 flex items-center justify-center mb-1.5 group-active:scale-95 transition-transform border border-rose-100">
                  <Zap size={18} />
                </div>
                <div className="text-[10px] font-medium text-slate-600 text-center leading-tight">Audit Energi</div>
              </div>
              <div className="flex flex-col items-center min-w-[72px] snap-start cursor-pointer group" onClick={() => scrollToSection('section-process-count')}>
                <div className="w-11 h-11 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center mb-1.5 group-active:scale-95 transition-transform border border-indigo-100">
                  <TrendingUp size={18} />
                </div>
                <div className="text-[10px] font-medium text-slate-600 text-center leading-tight">Proses 30h</div>
              </div>
            </div>

            {/* 3. RINGKASAN MESIN BERJALAN (Ultra Compact HUD Strip) */}
            <RunningMachineSummaryCompact data={runningSummary} />

            {/* 4. MESIN AKTIF & DISTRIBUSI ENERGI (Compact Modern UI-UX) */}
            <SectionCard
              id="section-active-machines"
              title="Mesin Aktif & Distribusi Energi"
              subtitle={`${machinesData.total_active} mesin aktif memproses kain · Klik mesin untuk grafik telemetri real-time`}
              action={
                <div className="flex items-center gap-2">
                  <div className="flex bg-slate-100 p-0.5 rounded-lg text-xs font-semibold">
                    <button
                      onClick={() => setCompactMachineFilter('all')}
                      className={`px-2 py-1 rounded-md transition-all ${compactMachineFilter === 'all' ? 'bg-white text-slate-900 shadow-2xs' : 'text-slate-500 hover:text-slate-700'}`}
                    >
                      Semua ({rawActiveMachines.length})
                    </button>
                    <button
                      onClick={() => setCompactMachineFilter('steam')}
                      className={`px-2 py-1 rounded-md transition-all ${compactMachineFilter === 'steam' ? 'bg-white text-sky-700 shadow-2xs' : 'text-slate-500 hover:text-slate-700'}`}
                    >
                      Uap ({energyActive.steam})
                    </button>
                    <button
                      onClick={() => setCompactMachineFilter('hto')}
                      className={`px-2 py-1 rounded-md transition-all ${compactMachineFilter === 'hto' ? 'bg-white text-amber-700 shadow-2xs' : 'text-slate-500 hover:text-slate-700'}`}
                    >
                      HTO ({energyActive.hto})
                    </button>
                    <button
                      onClick={() => setCompactMachineFilter('cooling')}
                      className={`px-2 py-1 rounded-md transition-all ${compactMachineFilter === 'cooling' ? 'bg-white text-cyan-700 shadow-2xs' : 'text-slate-500 hover:text-slate-700'}`}
                    >
                      Cooling ({coolingCount})
                    </button>
                  </div>
                  <Link to="/mesin-aktif" className="text-xs text-sky-600 hover:text-sky-700 font-semibold flex items-center gap-0.5 ml-1">
                    Manual <ChevronRight size={13} />
                  </Link>
                </div>
              }
            >
              <div className="p-3 sm:p-4 space-y-3">
                {/* Compact KPI Indicator Row */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
                  <div
                    onClick={() => setCompactMachineFilter('all')}
                    className={`rounded-xl p-2.5 border cursor-pointer transition-all ${
                      compactMachineFilter === 'all'
                        ? 'bg-slate-100/90 border-slate-300 ring-1 ring-slate-200'
                        : 'bg-slate-50 border-slate-100 hover:bg-slate-100/60'
                    }`}
                  >
                    <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider block">Energi Aktif</span>
                    <span className="text-base font-black text-slate-900 tabular-nums">{energyActive.total} Mesin</span>
                  </div>
                  <div
                    onClick={() => setCompactMachineFilter('steam')}
                    className={`rounded-xl p-2.5 border cursor-pointer transition-all ${
                      compactMachineFilter === 'steam'
                        ? 'bg-sky-100/70 border-sky-300 ring-1 ring-sky-200'
                        : 'bg-sky-50/60 border-sky-100/60 hover:bg-sky-100/40'
                    }`}
                  >
                    <span className="text-[10px] font-bold text-sky-600 uppercase tracking-wider block">Konsumsi Uap</span>
                    <span className="text-base font-black text-sky-900 tabular-nums">{energyActive.steam} Mesin</span>
                  </div>
                  <div
                    onClick={() => setCompactMachineFilter('hto')}
                    className={`rounded-xl p-2.5 border cursor-pointer transition-all ${
                      compactMachineFilter === 'hto'
                        ? 'bg-amber-100/70 border-amber-300 ring-1 ring-amber-200'
                        : 'bg-amber-50/60 border-amber-100/60 hover:bg-amber-100/40'
                    }`}
                  >
                    <span className="text-[10px] font-bold text-amber-600 uppercase tracking-wider block">Konsumsi HTO</span>
                    <span className="text-base font-black text-amber-900 tabular-nums">{energyActive.hto} Mesin</span>
                  </div>
                  <div
                    onClick={() => setCompactMachineFilter('cooling')}
                    className={`rounded-xl p-2.5 border cursor-pointer transition-all ${
                      compactMachineFilter === 'cooling'
                        ? 'bg-cyan-100/70 border-cyan-300 ring-1 ring-cyan-200'
                        : 'bg-cyan-50/60 border-cyan-100/60 hover:bg-cyan-100/40'
                    }`}
                  >
                    <span className="text-[10px] font-bold text-cyan-700 uppercase tracking-wider block">Cooling</span>
                    <span className="text-base font-black text-cyan-950 tabular-nums">{coolingCount} Mesin</span>
                  </div>
                </div>

                {/* Compact Active Machines Grid */}
                {filteredActiveMachines.length === 0 ? (
                  <div className="py-6 text-center text-xs text-slate-400 bg-slate-50/50 rounded-xl border border-dashed border-slate-200">
                    {compactMachineFilter === 'cooling'
                      ? 'Tidak ada mesin yang sedang berada pada fase Cooling saat ini.'
                      : 'Tidak ada mesin yang cocok dengan filter energi ini.'}
                  </div>
                ) : (
                  <div className={`grid grid-cols-1 md:grid-cols-2 gap-2 overflow-y-auto custom-scrollbar transition-all ${
                    compactMachinesExpanded ? 'max-h-[500px]' : 'max-h-[220px]'
                  }`}>
                    {filteredActiveMachines.map((m) => {
                      const statusKey = normalizeStatus(m.status);
                      const hasSteam = (m.steam || 0) > 0;
                      const hasHto = (m.hto || 0) > 0;
                      const MachineIcon = getMachineTextileIcon(m.name, m.group_name);

                      const iconBadgeStyle =
                        statusKey === 'HEAT'
                          ? 'bg-rose-50 text-rose-600 border-rose-200/80'
                          : statusKey === 'STEADY'
                          ? 'bg-amber-50 text-amber-600 border-amber-200/80'
                          : statusKey === 'COOL'
                          ? 'bg-cyan-50 text-cyan-600 border-cyan-200/80'
                          : 'bg-emerald-50 text-emerald-600 border-emerald-200/80';

                      return (
                        <div
                          key={m.id}
                          onClick={() => openMachineDetail(m.id)}
                          className="px-3 py-2 bg-slate-50/60 hover:bg-sky-50/50 rounded-xl border border-slate-100 hover:border-sky-200/60 cursor-pointer flex items-center justify-between transition-all group"
                        >
                          <div className="flex items-center gap-2.5 min-w-0">
                            <div
                              className={`w-8 h-8 rounded-lg border flex items-center justify-center shrink-0 transition-transform group-hover:scale-105 ${iconBadgeStyle}`}
                              title={`Status: ${statusKey}`}
                            >
                              <MachineIcon size={18} />
                            </div>
                            <div className="min-w-0">
                              <div className="flex items-center gap-1.5">
                                <p className="text-xs font-bold text-slate-900 group-hover:text-sky-600 transition-colors truncate">
                                  {m.name}
                                </p>
                                {statusKey === 'COOL' && (
                                  <span className="text-[9px] font-bold px-1.5 py-0.2 rounded-full bg-cyan-100 text-cyan-700 border border-cyan-200 shrink-0">
                                    Cooling
                                  </span>
                                )}
                              </div>
                              <div className="text-[10px] text-slate-500 flex items-center gap-1.5 truncate">
                                <span>{m.group_name || 'Lainnya'}</span>
                                {m.start_time && <span>• Mulai {m.start_time}</span>}
                              </div>
                            </div>
                          </div>

                          <div className="flex items-center gap-3 shrink-0 text-right">
                            <div className="text-right">
                              <p className={`text-xs font-black tabular-nums ${m.temperature > 100 ? 'text-rose-600' : 'text-slate-800'}`}>
                                {m.temperature ? `${Number(m.temperature).toFixed(1)}°C` : '-'}
                              </p>
                              <div className="text-[10px] text-slate-500">
                                {statusKey === 'COOL' ? (
                                  <span className="text-cyan-600 font-semibold">Pendinginan</span>
                                ) : (
                                  <>
                                    {hasSteam && <span className="text-sky-600 font-semibold">{m.steam} kg/h</span>}
                                    {hasSteam && hasHto && <span className="mx-1">•</span>}
                                    {hasHto && <span className="text-amber-600 font-semibold">{formatNumber(m.hto, 0)} kCal</span>}
                                    {!hasSteam && !hasHto && <span className="text-slate-400">Standby</span>}
                                  </>
                                )}
                              </div>
                            </div>
                            <ChevronRight size={13} className="text-slate-300 group-hover:text-sky-600 transition-colors" />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}

                {filteredActiveMachines.length > 6 && (
                  <div className="pt-1 text-center">
                    <button
                      onClick={() => setCompactMachinesExpanded(!compactMachinesExpanded)}
                      className="inline-flex items-center gap-1 text-[11px] font-bold text-sky-600 hover:text-sky-700 bg-sky-50 px-3 py-1 rounded-full border border-sky-100 transition-colors"
                    >
                      {compactMachinesExpanded ? (
                        <>Perkecil Tampilan <ChevronUp size={12} /></>
                      ) : (
                        <>Tampilkan Semua ({filteredActiveMachines.length} Mesin) <ChevronDown size={12} /></>
                      )}
                    </button>
                  </div>
                )}
              </div>
            </SectionCard>

            {/* 5. ANALISIS STEAM BOILER & ANALISIS HTO BOILER */}
            <SectionCard
              id="section-boiler-analysis"
              title="Analisis Kinerja Boiler"
              subtitle="Korelasi Laju Pemakaian, Tekanan, Kecepatan Ruang Bakar & Temperatur Harian"
              action={
                <div className="flex bg-slate-100 p-0.5 rounded-lg text-xs font-semibold">
                  <button
                    onClick={() => setBoilerAnalysisTab('steam')}
                    className={`px-3 py-1 rounded-md transition-all flex items-center gap-1.5 ${
                      boilerAnalysisTab === 'steam' ? 'bg-white text-sky-700 shadow-2xs font-bold' : 'text-slate-500 hover:text-slate-700'
                    }`}
                  >
                    <Droplet size={13} className="text-sky-500" />
                    Steam Boiler
                  </button>
                  <button
                    onClick={() => setBoilerAnalysisTab('hto')}
                    className={`px-3 py-1 rounded-md transition-all flex items-center gap-1.5 ${
                      boilerAnalysisTab === 'hto' ? 'bg-white text-amber-700 shadow-2xs font-bold' : 'text-slate-500 hover:text-slate-700'
                    }`}
                  >
                    <Flame size={13} className="text-amber-500" />
                    HTO Boiler
                  </button>
                </div>
              }
            >
              <div className="p-3 sm:p-5">
                {boilerChartData.length === 0 ? (
                  <div className="py-12 text-center text-xs text-slate-400 bg-slate-50/50 rounded-xl border border-dashed border-slate-200">
                    Memuat data analisis boiler hari ini...
                  </div>
                ) : (
                  <>
                    {/* TAB 1: ANALISIS STEAM BOILER */}
                    {boilerAnalysisTab === 'steam' && (
                      <div className="space-y-4">
                        <div className="flex flex-wrap items-center justify-between gap-2 pb-2 border-b border-slate-100">
                          <div>
                            <h4 className="text-xs font-bold text-slate-800 uppercase tracking-wide flex items-center gap-1.5">
                              <Droplet size={14} className="text-sky-500" />
                              Analisis Steam Boiler
                            </h4>
                            <p className="text-[11px] text-slate-400 mt-0.5">Pengaruh Feeding Bahan Bakar, Tekanan Uap, dan Penggunaan Uap</p>
                          </div>
                          <div className="flex items-center gap-3 text-[11px] text-slate-500 font-medium">
                            <span className="flex items-center gap-1"><span className="w-2.5 h-1 bg-sky-500 rounded" /> Steam Usage (kg/h)</span>
                            <span className="flex items-center gap-1"><span className="w-2.5 h-1 bg-violet-500 rounded" /> Pressure (bar)</span>
                          </div>
                        </div>

                        <div className="h-[200px] w-full">
                          <ResponsiveContainer width="100%" height="100%">
                            <AreaChart data={boilerChartData} syncId="boilerSync" margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
                              <defs>
                                <linearGradient id="gradSteamAnalysis" x1="0" y1="0" x2="0" y2="1">
                                  <stop offset="5%" stopColor="#0ea5e9" stopOpacity={0.25} />
                                  <stop offset="95%" stopColor="#0ea5e9" stopOpacity={0.0} />
                                </linearGradient>
                              </defs>
                              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                              <XAxis dataKey="time" tick={{ fontSize: 10, fill: '#94a3b8' }} minTickGap={35} />
                              <YAxis yAxisId="left" tick={{ fontSize: 10, fill: '#94a3b8' }} width={48} label={{ value: 'kg/h', angle: -90, position: 'insideLeft', fill: '#94a3b8', fontSize: 10 }} />
                              <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 10, fill: '#94a3b8' }} domain={[0, 10]} width={36} label={{ value: 'bar', angle: 90, position: 'insideRight', fill: '#94a3b8', fontSize: 10 }} />
                              <RechartsTooltip content={<BoilerTooltip />} />
                              <Area connectNulls yAxisId="left" type="monotone" dataKey="steam_usage" name="Steam Usage" stroke="#0ea5e9" strokeWidth={2} fill="url(#gradSteamAnalysis)" />
                              <Line connectNulls yAxisId="right" type="monotone" dataKey="Steam_Pr" name="Pressure" stroke="#8b5cf6" strokeWidth={2} dot={false} />
                            </AreaChart>
                          </ResponsiveContainer>
                        </div>

                        <div className="pt-2 border-t border-slate-100">
                          <div className="flex items-center justify-between text-[11px] text-slate-500 font-medium mb-1.5">
                            <span className="font-bold text-slate-700">Feeding Bahan Bakar vs Suhu Ruang Bakar</span>
                            <div className="flex items-center gap-3">
                              <span className="flex items-center gap-1"><span className="w-2.5 h-1 bg-amber-500 rounded" /> Speed RB (Hz)</span>
                              <span className="flex items-center gap-1"><span className="w-2.5 h-1 bg-rose-500 rounded" /> Temp RB (°C)</span>
                            </div>
                          </div>
                          <div className="h-[175px] w-full">
                            <ResponsiveContainer width="100%" height="100%">
                              <LineChart data={boilerChartData} syncId="boilerSync" margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
                                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                                <XAxis dataKey="time" tick={{ fontSize: 10, fill: '#94a3b8' }} minTickGap={35} />
                                <YAxis yAxisId="left" tick={{ fontSize: 10, fill: '#94a3b8' }} stroke="#f59e0b" width={42} />
                                <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 10, fill: '#94a3b8' }} stroke="#f43f5e" width={38} />
                                <RechartsTooltip content={<BoilerTooltip />} />
                                <Line connectNulls yAxisId="left" type="monotone" dataKey="Speed_RB_Steam" name="Speed RB (Hz)" stroke="#f59e0b" strokeWidth={2} dot={false} />
                                <Line connectNulls yAxisId="right" type="monotone" dataKey="Temp_RB_Steam" name="Temp RB (°C)" stroke="#f43f5e" strokeWidth={2} dot={false} />
                              </LineChart>
                            </ResponsiveContainer>
                          </div>
                        </div>

                        {fuelConfig.steam_calibrated && (
                          <div className="pt-2 border-t border-slate-100">
                            <div className="flex items-center justify-between text-[11px] text-slate-500 font-medium mb-1">
                              <span className="font-bold text-slate-700 flex items-center gap-1"><Fuel size={12} /> Konsumsi Fuel Batu Bara (kg/jam)</span>
                            </div>
                            <div className="h-[135px] w-full">
                              <ResponsiveContainer width="100%" height="100%">
                                <AreaChart data={boilerChartData} syncId="boilerSync" margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
                                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                                  <XAxis dataKey="time" tick={{ fontSize: 10, fill: '#94a3b8' }} minTickGap={35} />
                                  <YAxis tick={{ fontSize: 10, fill: '#94a3b8' }} width={42} />
                                  <RechartsTooltip content={<BoilerTooltip />} />
                                  <Area connectNulls type="monotone" dataKey="fuel_kg_steam" name="Fuel Batu Bara (kg)" stroke="#78716c" fill="#78716c" fillOpacity={0.15} />
                                </AreaChart>
                              </ResponsiveContainer>
                            </div>
                          </div>
                        )}
                      </div>
                    )}

                    {/* TAB 2: ANALISIS HTO BOILER */}
                    {boilerAnalysisTab === 'hto' && (
                      <div className="space-y-4">
                        <div className="flex flex-wrap items-center justify-between gap-2 pb-2 border-b border-slate-100">
                          <div>
                            <h4 className="text-xs font-bold text-slate-800 uppercase tracking-wide flex items-center gap-1.5">
                              <Flame size={14} className="text-amber-500" />
                              Analisis HTO Boiler (Thermal Oil)
                            </h4>
                            <p className="text-[11px] text-slate-400 mt-0.5">Stabilitas Suhu Oli Panas terhadap Ruang Bakar HTO</p>
                          </div>
                          <div className="flex items-center gap-3 text-[11px] text-slate-500 font-medium">
                            <span className="flex items-center gap-1"><span className="w-2.5 h-1 bg-amber-500 rounded" /> Suhu Oli (°C)</span>
                            <span className="flex items-center gap-1"><span className="w-2.5 h-1 bg-sky-500 rounded" /> Speed RB (Hz)</span>
                          </div>
                        </div>

                        <div className="h-[200px] w-full">
                          <ResponsiveContainer width="100%" height="100%">
                            <LineChart data={boilerChartData} syncId="htoBoilerSync" margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
                              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                              <XAxis dataKey="time" tick={{ fontSize: 10, fill: '#94a3b8' }} minTickGap={35} />
                              <YAxis yAxisId="left" tick={{ fontSize: 10, fill: '#94a3b8' }} stroke="#f59e0b" width={48} label={{ value: '°C', angle: -90, position: 'insideLeft', fill: '#94a3b8', fontSize: 10 }} />
                              <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 10, fill: '#94a3b8' }} stroke="#0ea5e9" width={38} label={{ value: 'Hz', angle: 90, position: 'insideRight', fill: '#94a3b8', fontSize: 10 }} />
                              <RechartsTooltip content={<BoilerTooltip />} />
                              <Line connectNulls yAxisId="left" type="monotone" dataKey="Oil_Temp" name="Suhu Oli HTO (°C)" stroke="#f59e0b" strokeWidth={2.5} dot={false} />
                              <Line connectNulls yAxisId="right" type="monotone" dataKey="Speed_R_Bakar" name="Speed RB HTO (Hz)" stroke="#0ea5e9" strokeWidth={2} dot={false} />
                            </LineChart>
                          </ResponsiveContainer>
                        </div>

                        <div className="pt-2 border-t border-slate-100">
                          <div className="flex items-center justify-between text-[11px] text-slate-500 font-medium mb-1.5">
                            <span className="font-bold text-slate-700">Suhu Ruang Bakar HTO vs Speed Feeder</span>
                            <div className="flex items-center gap-3">
                              <span className="flex items-center gap-1"><span className="w-2.5 h-1 bg-rose-500 rounded" /> Temp RB (°C)</span>
                              <span className="flex items-center gap-1"><span className="w-2.5 h-1 bg-sky-500 rounded" /> Speed RB (Hz)</span>
                            </div>
                          </div>
                          <div className="h-[175px] w-full">
                            <ResponsiveContainer width="100%" height="100%">
                              <LineChart data={boilerChartData} syncId="htoBoilerSync" margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
                                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                                <XAxis dataKey="time" tick={{ fontSize: 10, fill: '#94a3b8' }} minTickGap={35} />
                                <YAxis yAxisId="left" tick={{ fontSize: 10, fill: '#94a3b8' }} stroke="#f43f5e" width={48} />
                                <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 10, fill: '#94a3b8' }} stroke="#0ea5e9" width={38} />
                                <RechartsTooltip content={<BoilerTooltip />} />
                                <Line connectNulls yAxisId="left" type="monotone" dataKey="Temp_R_Bakar" name="Temp Ruang Bakar (°C)" stroke="#f43f5e" strokeWidth={2} strokeDasharray="4 4" dot={false} />
                                <Line connectNulls yAxisId="right" type="monotone" dataKey="Speed_R_Bakar" name="Speed RB HTO (Hz)" stroke="#0ea5e9" strokeWidth={2} dot={false} />
                              </LineChart>
                            </ResponsiveContainer>
                          </div>
                        </div>

                        {fuelConfig.hto_calibrated && (
                          <div className="pt-2 border-t border-slate-100">
                            <div className="flex items-center justify-between text-[11px] text-slate-500 font-medium mb-1">
                              <span className="font-bold text-slate-700 flex items-center gap-1"><Fuel size={12} /> Konsumsi Fuel HTO (kg/jam)</span>
                            </div>
                            <div className="h-[135px] w-full">
                              <ResponsiveContainer width="100%" height="100%">
                                <AreaChart data={boilerChartData} syncId="htoBoilerSync" margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
                                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                                  <XAxis dataKey="time" tick={{ fontSize: 10, fill: '#94a3b8' }} minTickGap={35} />
                                  <YAxis tick={{ fontSize: 10, fill: '#94a3b8' }} width={42} />
                                  <RechartsTooltip content={<BoilerTooltip />} />
                                  <Area connectNulls type="monotone" dataKey="fuel_kg_hto" name="Fuel HTO (kg)" stroke="#a8a29e" fill="#a8a29e" fillOpacity={0.15} />
                                </AreaChart>
                              </ResponsiveContainer>
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </>
                )}
              </div>
            </SectionCard>

            {/* 6. GRID 2 KOLOM DI PC: DISTRIBUSI & STABILITAS (KIRI) vs HISTORI ALERT & REGULASI (KANAN) */}
            <div id="section-stability-alerts" className="grid grid-cols-1 lg:grid-cols-2 gap-5 sm:gap-6">

              {/* ── KOLOM KIRI: DISTRIBUSI TEKANAN & SUHU + STABILITAS DEMAND ── */}
              <div className="space-y-5">
                <SectionCard
                  title="Distribusi Tekanan Uap & Suhu HTO"
                  subtitle="Kepatuhan parameter operasional terhadap batas standar ideal"
                >
                  <div className="p-3 sm:p-4 space-y-4">
                    <div className="grid grid-cols-2 gap-3 divide-x divide-slate-100">
                      {/* Tekanan Uap Donut */}
                      <div className="flex flex-col items-center">
                        <span className="text-[11px] font-bold text-slate-700 uppercase tracking-tight mb-0.5">Tekanan Uap</span>
                        <span className="text-[10px] text-slate-400 mb-1">Target 3.5 - 5.5 Bar</span>
                        <div className="h-28 w-28 relative">
                          <ResponsiveContainer width="100%" height="100%">
                            <PieChart>
                              <Pie
                                data={pressurePieData}
                                cx="50%"
                                cy="50%"
                                innerRadius={30}
                                outerRadius={46}
                                paddingAngle={3}
                                dataKey="value"
                              >
                                {pressurePieData.map((entry, index) => (
                                  <Cell key={`cell-${index}`} fill={entry.color} />
                                ))}
                              </Pie>
                              <RechartsTooltip formatter={(val) => [`${val}%`, 'Persentase']} />
                            </PieChart>
                          </ResponsiveContainer>
                          <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                            <span className="text-xs font-black text-emerald-600 tabular-nums">
                              {pressurePieData[0]?.value || 0}%
                            </span>
                            <span className="text-[9px] text-slate-400 leading-none">Ideal</span>
                          </div>
                        </div>
                        <div className="mt-2 w-full space-y-1 text-[10px]">
                          <div className="flex justify-between items-center text-slate-600">
                            <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-emerald-500" /> Ideal</span>
                            <span className="font-bold tabular-nums">{pressurePieData[0]?.value}%</span>
                          </div>
                          <div className="flex justify-between items-center text-slate-600">
                            <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-amber-500" /> Under</span>
                            <span className="font-bold tabular-nums">{pressurePieData[1]?.value}%</span>
                          </div>
                          <div className="flex justify-between items-center text-slate-600">
                            <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-rose-500" /> Over</span>
                            <span className="font-bold tabular-nums">{pressurePieData[2]?.value}%</span>
                          </div>
                        </div>
                      </div>

                      {/* Suhu HTO Donut */}
                      <div className="flex flex-col items-center pl-3">
                        <span className="text-[11px] font-bold text-slate-700 uppercase tracking-tight mb-0.5">Suhu Oli HTO</span>
                        <span className="text-[10px] text-slate-400 mb-1">Target 240 - 275 °C</span>
                        <div className="h-28 w-28 relative">
                          <ResponsiveContainer width="100%" height="100%">
                            <PieChart>
                              <Pie
                                data={htoPieData}
                                cx="50%"
                                cy="50%"
                                innerRadius={30}
                                outerRadius={46}
                                paddingAngle={3}
                                dataKey="value"
                              >
                                {htoPieData.map((entry, index) => (
                                  <Cell key={`cell-${index}`} fill={entry.color} />
                                ))}
                              </Pie>
                              <RechartsTooltip formatter={(val) => [`${val}%`, 'Persentase']} />
                            </PieChart>
                          </ResponsiveContainer>
                          <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                            <span className="text-xs font-black text-emerald-600 tabular-nums">
                              {htoPieData[0]?.value || 0}%
                            </span>
                            <span className="text-[9px] text-slate-400 leading-none">Ideal</span>
                          </div>
                        </div>
                        <div className="mt-2 w-full space-y-1 text-[10px]">
                          <div className="flex justify-between items-center text-slate-600">
                            <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-emerald-500" /> Ideal</span>
                            <span className="font-bold tabular-nums">{htoPieData[0]?.value}%</span>
                          </div>
                          <div className="flex justify-between items-center text-slate-600">
                            <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-amber-500" /> Under</span>
                            <span className="font-bold tabular-nums">{htoPieData[1]?.value}%</span>
                          </div>
                          <div className="flex justify-between items-center text-slate-600">
                            <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-rose-500" /> Over</span>
                            <span className="font-bold tabular-nums">{htoPieData[2]?.value}%</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </SectionCard>

                {/* Stabilitas Pemakaian (Demand) Harian */}
                <SectionCard
                  title="Stabilitas Pemakaian (Demand)"
                  subtitle="Distribusi frekuensi beban pemakaian uap harian (kg/h)"
                >
                  <div className="p-3 sm:p-4 space-y-3">
                    <div className="h-40 w-full">
                      {usageHistogram.length > 0 ? (
                        <ResponsiveContainer width="100%" height="100%">
                          <BarChart data={usageHistogram} margin={{ top: 8, right: 8, bottom: 20, left: -20 }}>
                            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                            <XAxis dataKey="name" tick={{ fontSize: 9, fill: '#94a3b8' }} interval={0} angle={-35} textAnchor="end" height={36} />
                            <YAxis tick={{ fontSize: 10, fill: '#94a3b8' }} width={36} />
                            <RechartsTooltip cursor={{ fill: '#f8fafc' }} formatter={(val) => [`${val} Frekuensi`, 'Jumlah']} />
                            <Bar dataKey="count" fill="#8b5cf6" radius={[4, 4, 0, 0]} name="Frekuensi" />
                          </BarChart>
                        </ResponsiveContainer>
                      ) : (
                        <div className="flex h-full items-center justify-center text-slate-400 text-xs">
                          Belum ada data pemakaian valid hari ini.
                        </div>
                      )}
                    </div>

                    {validUsages.length > 0 && (
                      <div className="space-y-2 pt-2 border-t border-slate-100">
                        <div className="grid grid-cols-4 gap-2 text-center">
                          <div className="bg-slate-50 p-1.5 rounded-lg border border-slate-100">
                            <div className="text-[9px] text-slate-400 uppercase font-bold">Rata-rata</div>
                            <div className="text-xs font-bold text-slate-800 tabular-nums">{statsUsage.mean}</div>
                          </div>
                          <div className="bg-slate-50 p-1.5 rounded-lg border border-slate-100">
                            <div className="text-[9px] text-slate-400 uppercase font-bold">SD (Sebaran)</div>
                            <div className="text-xs font-bold text-slate-800 tabular-nums">±{statsUsage.sd}</div>
                          </div>
                          <div className="bg-slate-50 p-1.5 rounded-lg border border-slate-100">
                            <div className="text-[9px] text-slate-400 uppercase font-bold">Skewness</div>
                            <div className="text-xs font-bold text-slate-800 tabular-nums">{statsUsage.skewness}</div>
                          </div>
                          <div className={`p-1.5 rounded-lg border flex flex-col justify-center ${
                            statsUsage.scoreValue === 0
                              ? 'bg-emerald-50 border-emerald-200/60 text-emerald-700'
                              : statsUsage.scoreValue === 1
                              ? 'bg-sky-50 border-sky-200/60 text-sky-700'
                              : 'bg-amber-50 border-amber-200/60 text-amber-700'
                          }`}>
                            <div className="text-[9px] uppercase font-bold opacity-80">Karakteristik</div>
                            <div className="text-[11px] font-black leading-tight truncate">{statsUsage.label}</div>
                          </div>
                        </div>

                        {statsUsage.reasons.length > 0 && statsUsage.scoreValue > 0 && (
                          <div className="bg-slate-50 p-2.5 rounded-lg border border-slate-100 text-[11px] text-slate-600">
                            <p className="font-semibold mb-0.5 text-slate-800">Catatan Penurunan Stabilitas:</p>
                            <ul className="list-disc pl-4 space-y-0.5 text-slate-500">
                              {statsUsage.reasons.map((reason, idx) => (
                                <li key={idx}>{reason}</li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </SectionCard>
              </div>

              {/* ── KOLOM KANAN: HISTORI ALERT & REGULASI ── */}
              <div>
                <SectionCard
                  title="Histori Alert & Regulasi"
                  subtitle="Kejadian peringatan, anomali sensor, dan regulasi boiler"
                  icon={AlertTriangle}
                  action={
                    <div className="flex bg-slate-100 p-0.5 rounded-lg text-xs font-semibold">
                      {['Semua', 'Critical', 'Warning', 'Regulasi'].map((f) => (
                        <button
                          key={f}
                          onClick={() => setAlertFilter(f)}
                          className={`px-2 py-1 rounded-md transition-all text-[11px] ${
                            alertFilter === f ? 'bg-white text-slate-900 shadow-2xs font-bold' : 'text-slate-500 hover:text-slate-700'
                          }`}
                        >
                          {f}
                        </button>
                      ))}
                    </div>
                  }
                  className="h-full flex flex-col"
                >
                  <div className="p-3 sm:p-4 flex-1 flex flex-col">
                    {filteredAlerts.length === 0 ? (
                      <div className="my-auto py-12 text-center text-xs text-slate-400 bg-slate-50/50 rounded-xl border border-dashed border-slate-200 flex flex-col items-center justify-center">
                        <CheckCircle2 size={24} className="text-emerald-500 mb-2" />
                        <span className="font-semibold text-slate-700">Tidak ada alert untuk filter "{alertFilter}".</span>
                        <span className="text-[11px] text-slate-400 mt-0.5">Sistem pembakaran boiler dan sensor beroperasi stabil.</span>
                      </div>
                    ) : (
                      <div className="overflow-x-auto overflow-y-auto max-h-[460px] custom-scrollbar">
                        <table className="w-full text-left text-xs">
                          <thead>
                            <tr className="border-b border-slate-100 text-[10px] text-slate-400 uppercase tracking-wider font-bold">
                              <th className="pb-2 pr-3">Waktu</th>
                              <th className="pb-2 pr-3">Jenis</th>
                              <th className="pb-2 pr-3">Mesin</th>
                              <th className="pb-2 pr-3">Keterangan</th>
                              <th className="pb-2 pr-3">Nilai / Batas</th>
                              <th className="pb-2">Status</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-100">
                            {filteredAlerts.map((alert, idx) => {
                              const isReg = alert.alert_type === 'REGULATION';
                              return (
                                <tr key={idx} className={`hover:bg-slate-50/80 transition-colors ${isReg ? 'bg-amber-50/30' : ''}`}>
                                  <td className="py-2.5 pr-3 text-slate-600 whitespace-nowrap font-mono text-[11px]">
                                    {alert.created_at || '-'}
                                  </td>
                                  <td className="py-2.5 pr-3 whitespace-nowrap">
                                    {isReg ? (
                                      <span className="text-[9px] font-black px-1.5 py-0.5 rounded-full border bg-amber-100 text-amber-800 border-amber-200 uppercase tracking-wide">
                                        REGULASI
                                      </span>
                                    ) : (
                                      <span className={`text-[9px] font-black px-1.5 py-0.5 rounded-full border ${
                                        alert.severity === 'CRITICAL'
                                          ? 'bg-rose-100 text-rose-700 border-rose-200'
                                          : 'bg-amber-100 text-amber-700 border-amber-200'
                                      }`}>
                                        {alert.severity}
                                      </span>
                                    )}
                                  </td>
                                  <td className="py-2.5 pr-3 text-slate-800 font-bold whitespace-nowrap">
                                    {alert.machine_code || '-'}
                                  </td>
                                  <td className="py-2.5 pr-3 text-slate-600 min-w-[120px]">
                                    {alert.title || alert.message || '-'}
                                  </td>
                                  <td className="py-2.5 pr-3 text-slate-600 whitespace-nowrap tabular-nums">
                                    {isReg
                                      ? (alert.current_value != null ? Number(alert.current_value).toFixed(1) : '-')
                                      : `${alert.current_value != null ? Number(alert.current_value).toFixed(1) : '-'} / ${alert.threshold_value != null ? Number(alert.threshold_value).toFixed(1) : '-'}`}
                                  </td>
                                  <td className="py-2.5 whitespace-nowrap">
                                    {isReg ? (
                                      <span className="text-slate-500 text-[10px]">
                                        {alert.regulation_meta?.duration_minutes ? `${alert.regulation_meta.duration_minutes}m` : 'Aktif'}
                                      </span>
                                    ) : (
                                      <span className={`text-[10px] font-semibold ${alert.is_acknowledged ? 'text-emerald-600' : 'text-amber-600'}`}>
                                        {alert.is_acknowledged ? 'Diakui' : 'Terbuka'}
                                      </span>
                                    )}
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                </SectionCard>
              </div>

            </div>

          </div>

          {/* ========================================================================= */}
          {/* SECTION KANAN (1/3 Width on Desktop xl:col-span-1 — Contextual Analytics) */}
          {/* ========================================================================= */}
          <div className="xl:col-span-1 space-y-5 sm:space-y-6">

            {/* WIDGET 1: KONDISI ENERGI BOILER (1 JAM TERAKHIR) */}
            <SectionCard
              id="section-energy-condition"
              title="Kondisi Energi Boiler"
              subtitle="Parameter sensor aktual vs rata-rata 1 jam terakhir"
            >
              <div className="p-3 sm:p-4">
                <div className="overflow-x-auto max-h-[300px] custom-scrollbar">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-slate-100 text-[10px] text-slate-400 uppercase tracking-wider font-bold">
                        <th className="pb-2 pr-2">Mesin / Parameter</th>
                        <th className="pb-2 pr-2 text-right">Aktual</th>
                        <th className="pb-2 text-right">Rata-rata 1 Jam</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {(energyCondition || []).map((row) => (
                        <tr key={row.id || row.name} className="hover:bg-slate-50 transition-colors">
                          <td className="py-2 pr-2">
                            <div className="flex items-center gap-2">
                              <div className="w-6 h-6 bg-amber-50 rounded-md flex items-center justify-center text-amber-600 shrink-0">
                                <Activity size={13} />
                              </div>
                              <span className="font-semibold text-slate-800">{row.name}</span>
                            </div>
                          </td>
                          <td className="py-2 pr-2 text-right font-bold text-slate-900 tabular-nums whitespace-nowrap">
                            {row.value} <span className="text-[10px] text-slate-400 font-medium">{row.unit}</span>
                          </td>
                          <td className="py-2 text-right text-slate-600 tabular-nums whitespace-nowrap">
                            {row.average_1h !== undefined && row.average_1h !== null ? (
                              <>
                                {row.average_1h} <span className="text-[10px] text-slate-400">{row.unit}</span>
                              </>
                            ) : (
                              '-'
                            )}
                          </td>
                        </tr>
                      ))}
                      {(!energyCondition || energyCondition.length === 0) && (
                        <tr>
                          <td colSpan="3" className="py-6 text-center text-xs text-slate-400">
                            Data kondisi energi belum tersedia
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </SectionCard>


            {/* WIDGET 2: TOTAL PEMAKAIAN UAP (30 Hari / 7 Hari) */}
            <SectionCard
              id="section-steam-sales"
              title={`Total Pemakaian Uap (${steamDays} Hari)`}
              subtitle={`Total: ${steamSalesData ? formatNumber((steamSalesData.total || 0) / 1000, 1) + ' Ton' : 'Memuat...'}`}
              action={
                <div className="flex bg-slate-100 p-0.5 rounded-lg text-xs font-semibold">
                  <button
                    onClick={() => setSteamDays(30)}
                    className={`px-2 py-0.5 rounded-md transition-all ${steamDays === 30 ? 'bg-white text-sky-600 shadow-2xs font-bold' : 'text-slate-500 hover:text-slate-700'}`}
                  >
                    30 Hari
                  </button>
                  <button
                    onClick={() => setSteamDays(7)}
                    className={`px-2 py-0.5 rounded-md transition-all ${steamDays === 7 ? 'bg-white text-sky-600 shadow-2xs font-bold' : 'text-slate-500 hover:text-slate-700'}`}
                  >
                    7 Hari
                  </button>
                </div>
              }
            >
              <div className="p-3 sm:p-4">
                <div className="h-[175px] w-full">
                  <ResponsiveContainer debounce={50} width="100%" height="100%">
                    <BarChart
                      data={steamSalesData?.series?.map((d) => ({
                        ...d,
                        formattedDate: d.day || (d.date ? String(d.date).slice(5) : '-'),
                        pemakaian: d.pemakaian ?? d.usage ?? 0,
                      })) || []}
                      margin={{ top: 8, right: 8, left: -16, bottom: 0 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                      <XAxis dataKey="formattedDate" tick={{ fontSize: 9, fill: '#94a3b8' }} interval={isMobile || steamDays === 30 ? 4 : 0} />
                      <YAxis tick={{ fontSize: 10, fill: '#94a3b8' }} tickFormatter={(val) => `${(val / 1000).toFixed(0)}t`} width={36} />
                      <RechartsTooltip
                        formatter={(val) => [`${formatNumber(val, 0)} kg (${(val / 1000).toFixed(1)} ton)`, 'Pemakaian']}
                        labelFormatter={(lbl) => `Hari: ${lbl}`}
                      />
                      <Bar isAnimationActive={isAnimActive} dataKey="pemakaian" radius={[3, 3, 0, 0]}>
                        {steamSalesData?.series?.map((entry, index) => (
                          <Cell
                            key={`cell-${index}`}
                            fill={index === (steamSalesData.series.length - 1) ? '#0284c7' : '#38bdf8'}
                          />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </SectionCard>

            {/* WIDGET 3: AVAILABILITY & EFISIENSI (2 Mini Cards) */}
            <div className="grid grid-cols-2 gap-3">
              <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs p-3.5 flex flex-col justify-between">
                <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Availability ({steamDays}h)</span>
                <div className="mt-2 flex items-baseline gap-1">
                  <span className="text-2xl font-black text-slate-900 tabular-nums">
                    {formatNumber(steamSalesData?.avg_availability ?? steamSalesData?.yesterday_availability ?? 0, 1)}
                  </span>
                  <span className="text-xs font-semibold text-slate-400">%</span>
                </div>
                <span className="text-[10px] text-slate-400 mt-1">Rata-rata kesiapan mesin</span>
              </div>

              <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs p-3.5 flex flex-col justify-between">
                <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Rata-rata Efisiensi ({steamDays}h)</span>
                <div className="mt-2 flex items-baseline gap-1">
                  <span className="text-2xl font-black text-slate-900 tabular-nums">
                    {formatNumber(steamSalesData?.avg_efficiency ?? steamSalesData?.avg_productivity ?? 0, 1)}
                  </span>
                  <span className="text-xs font-semibold text-slate-400">%</span>
                </div>
                <span className="text-[10px] text-slate-400 mt-1">Rata-rata hari aktif efisiensi</span>
              </div>
            </div>

            {/* WIDGET 4: JUMLAH PROSES PER MESIN (30 Hari / Hari Ini -> Klik ke /machine-daily-analytics) */}
            <SectionCard
              id="section-process-count"
              title={`Jumlah Proses Per Mesin (${processDays} Hari)`}
              subtitle={
                processDays === 30
                  ? "Rata-rata harian (~/hr) dihitung dari hari aktif produksi mesin (hari tanpa batch diabaikan)"
                  : "Klik baris mesin untuk membuka halaman Machine Daily Analytics"
              }
              action={
                <div className="flex bg-slate-100 p-0.5 rounded-lg text-xs font-semibold">
                  <button
                    onClick={() => setProcessDays(30)}
                    className={`px-2 py-0.5 rounded-md transition-all ${processDays === 30 ? 'bg-white text-sky-600 shadow-2xs font-bold' : 'text-slate-500 hover:text-slate-700'}`}
                  >
                    30 Hari
                  </button>
                  <button
                    onClick={() => setProcessDays(1)}
                    className={`px-2 py-0.5 rounded-md transition-all ${processDays === 1 ? 'bg-white text-sky-600 shadow-2xs font-bold' : 'text-slate-500 hover:text-slate-700'}`}
                  >
                    Hari Ini
                  </button>
                </div>
              }
            >
              <div className="p-3 sm:p-4 space-y-4 max-h-[380px] overflow-y-auto custom-scrollbar">
                {processesData.groups.map((grp) => (
                  <div key={grp.group_name} className="space-y-2">
                    <div className="flex justify-between items-center text-xs font-bold text-slate-700 border-b border-slate-100 pb-1">
                      <span>{grp.group_name}</span>
                      <span className="text-[10px] font-semibold text-slate-400 tabular-nums">
                        {grp.machines.reduce((sum, m) => sum + (m.process_count || 0), 0)} batch total
                      </span>
                    </div>

                    <div className="space-y-1.5">
                      {grp.machines.map((m) => {
                        const mId = m.id ?? m.machine_id;
                        const mName = m.name || m.machine_name || '-';
                        const count = m.process_count || 0;
                        const pct = Math.min(100, Math.round((count / maxProcessCount) * 100));

                        return (
                          <div
                            key={mId}
                            onClick={() => goToMachineAnalytics(mId)}
                            title={`Buka Analitik Harian Mesin ${mName}`}
                            className="group flex items-center justify-between text-xs py-1 px-1.5 rounded-lg hover:bg-sky-50/70 cursor-pointer transition-colors"
                          >
                            <span className="w-24 sm:w-28 font-semibold text-slate-700 group-hover:text-sky-600 transition-colors truncate flex items-center gap-1">
                              {mName}
                              <ExternalLink size={10} className="opacity-0 group-hover:opacity-100 text-sky-500 transition-opacity shrink-0" />
                            </span>

                            <div className="flex-1 mx-2.5 h-2 bg-slate-100 rounded-full overflow-hidden">
                              <div
                                className="h-full rounded-full transition-all duration-500"
                                style={{
                                  width: `${pct}%`,
                                  backgroundColor: processBarColor(count, maxProcessCount),
                                }}
                              />
                            </div>

                            <div className="w-16 text-right tabular-nums shrink-0">
                              <span className="font-bold text-slate-900">{count}</span>
                              {processDays === 30 && m.avg_per_day != null && (
                                <span
                                  className="text-[10px] text-slate-400 block leading-none"
                                  title={`${count} batch dalam ${m.active_days || 0} hari kerja aktif (rata-rata ~${m.avg_per_day} batch/hari)`}
                                >
                                  ~{m.avg_per_day}/hr
                                </span>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </SectionCard>

            {/* WIDGET 5: REKAP PROSES 30 HARI & ANOMALI */}
            <SectionCard
              title="Rekap Proses & Anomali (30 Hari)"
              subtitle="Statistik siklus proses dan anomali produksi"
            >
              <div className="p-3 sm:p-4 space-y-3">
                {processSummary30d ? (
                  <div className="space-y-3">
                    <div className="grid grid-cols-2 gap-2 text-center">
                      <div className="bg-slate-50 p-2.5 rounded-xl border border-slate-100">
                        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wide block">Total Batch (30h)</span>
                        <span className="text-xl font-black text-slate-900 tabular-nums">
                          {formatNumber(processSummary30d.total_processes)}
                        </span>
                      </div>
                      <div className="bg-slate-50 p-2.5 rounded-xl border border-slate-100">
                        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wide block">Rata-rata Durasi</span>
                        <span className="text-xl font-black text-slate-900 tabular-nums">
                          {processSummary30d.avg_duration_minutes ? `${Math.round(processSummary30d.avg_duration_minutes)}m` : '-'}
                        </span>
                      </div>
                    </div>

                    <div className="bg-rose-50/50 border border-rose-100 rounded-xl p-3 space-y-2">
                      <div className="flex justify-between items-center">
                        <span className="text-xs font-bold text-rose-800 flex items-center gap-1.5">
                          <AlertTriangle size={14} className="text-rose-500" /> Anomali Terdeteksi (30h)
                        </span>
                        <span className="text-xs font-black text-rose-700 tabular-nums">
                          {formatNumber(processSummary30d.total_anomalies || 0)} Insiden
                        </span>
                      </div>

                      {processSummary30d.top_anomalies?.length > 0 && (
                        <div className="flex flex-wrap gap-1.5 pt-1">
                          {processSummary30d.top_anomalies.slice(0, 4).map((anom, i) => (
                            <span
                              key={i}
                              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-white border border-rose-200/70 text-[10px] font-semibold text-rose-700"
                            >
                              <span>{anom.flag}:</span>
                              <strong className="tabular-nums">{anom.count}</strong>
                            </span>
                          ))}
                        </div>
                      )}
                    </div>

                    {processSummary30d.top_machines?.length > 0 && (
                      <div className="pt-2 border-t border-slate-100">
                        <span className="text-[11px] font-bold text-slate-600 block mb-2 uppercase tracking-wide">
                          Top Mesin Paling Produktif (30h):
                        </span>
                        <div className="space-y-1.5">
                          {(processSummary30d?.top_machines || []).slice(0, 5).map((tm, idx) => {
                            const tmName = tm.name || tm.machine_name || '-';
                            const tmBatches = tm.batches ?? tm.count ?? 0;
                            return (
                              <div
                                key={idx}
                                onClick={() => tm.id && goToMachineAnalytics(tm.id)}
                                className="flex justify-between items-center text-xs py-1 px-2 rounded-lg bg-slate-50/70 hover:bg-sky-50/60 border border-slate-100 cursor-pointer transition-colors"
                              >
                                <div className="flex items-center gap-2 min-w-0">
                                  <span className="w-5 h-5 rounded-full bg-sky-100 text-sky-700 font-black text-[10px] flex items-center justify-center shrink-0">
                                    {idx + 1}
                                  </span>
                                  <span className="text-slate-800 font-bold truncate">{tmName}</span>
                                  {tm.group && (
                                    <span className="text-[9px] font-semibold px-1.5 py-0.5 rounded bg-slate-200/70 text-slate-600 shrink-0">
                                      {tm.group}
                                    </span>
                                  )}
                                </div>
                                <div className="text-right shrink-0 ml-2 tabular-nums">
                                  <span className="font-bold text-slate-900">{tmBatches} batch</span>
                                  {tm.avg_per_day != null && (
                                    <span
                                      className="text-[10px] text-slate-400 ml-1"
                                      title={`${tmBatches} batch dalam ${tm.active_days || 0} hari kerja aktif`}
                                    >
                                      (~{tm.avg_per_day}/hr)
                                    </span>
                                  )}
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="py-6 text-center text-xs text-slate-400">
                    Memuat ringkasan proses 30 hari...
                  </div>
                )}
              </div>
            </SectionCard>


          </div>

        </div>

        {/* ═══════════════════════════════════════════════════════════════════════════ */}
        {/* BAGIAN BAWAH: MACHINE HEALTH & ENERGY WASTE ANALYTICS                       */}
        {/* + RIWAYAT DURASI HEATING, KEEP, COOLING (DIPISAH UAP vs LISTRIK)           */}
        {/* ═══════════════════════════════════════════════════════════════════════════ */}
        <div id="section-fleet-health" className="space-y-6 pt-2">

          {/* 1. HEADER BAR & RENTANG EVALUASI */}
          <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs p-4 sm:p-5 flex flex-col lg:flex-row lg:items-center justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 mb-1">
                <span className="px-2 py-0.5 rounded-md text-[10px] font-black bg-indigo-100 text-indigo-700 uppercase tracking-wider">
                  Fleet Intelligence & Waste Audit
                </span>
                {fleetHealthData?.date_range_label && (
                  <span className="text-xs text-slate-400 font-mono">
                    • {fleetHealthData.date_range_label}
                  </span>
                )}
              </div>
              <h2 className="text-lg sm:text-xl font-black text-slate-900 tracking-tight">
                Machine Health & Energy Waste Analytics
              </h2>
              <p className="text-xs text-slate-500 mt-0.5">
                Evaluasi Indeks Kesehatan Mesin (MHI), Riwayat Durasi Fase (Heating · Keep · Cooling), serta Audit Pemborosan Uap & Listrik
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-2.5">
              <div className="inline-flex rounded-xl bg-slate-100 p-1 text-xs font-semibold">
                {[
                  { key: '1D', label: '1 Hari (24J)' },
                  { key: '7D', label: '7 Hari' },
                  { key: '30D', label: '30 Hari' },
                ].map((opt) => (
                  <button
                    key={opt.key}
                    type="button"
                    onClick={() => setFleetWindow(opt.key)}
                    className={`px-3 py-1.5 rounded-lg transition-all ${
                      fleetWindow === opt.key
                        ? 'bg-white text-indigo-700 shadow-2xs font-bold'
                        : 'text-slate-600 hover:text-slate-900'
                    }`}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>

              <Link
                to="/machine-daily-report"
                className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold shadow-2xs transition-colors"
              >
                <span>Buka Laporan Penuh</span>
                <ArrowRight size={13} />
              </Link>
            </div>
          </div>

          {fleetHealthLoading && !fleetHealthData ? (
            <div className="bg-white rounded-2xl border border-slate-200/80 p-10 text-center space-y-2">
              <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin mx-auto" />
              <p className="text-xs font-semibold text-slate-600">Menghitung Machine Health Index (MHI) & Audit Energi...</p>
            </div>
          ) : fleetKpi ? (
            <>
              {/* 2. EXECUTIVE FLEET KPI STRIP (6 CARDS) */}
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
                {/* MHI Score */}
                <div className="bg-white p-3.5 sm:p-4 rounded-2xl border border-slate-200/80 shadow-xs">
                  <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wide flex items-center gap-1">
                    <Cpu size={13} className="text-indigo-500" /> Fleet Health (MHI)
                  </span>
                  <div className="flex items-baseline gap-1 mt-1.5">
                    <span className="text-2xl font-black text-slate-900 tabular-nums">{fleetKpi.avg_health_score ?? '-'}</span>
                    <span className="text-xs font-semibold text-slate-400">/ 100</span>
                  </div>
                  <div className="flex items-center gap-1 mt-2 text-[10px] font-bold">
                    <span className="px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-800">{fleetKpi.healthy_count} Sehat</span>
                    <span className="px-1.5 py-0.5 rounded bg-amber-100 text-amber-800">{fleetKpi.warning_count} C</span>
                    <span className="px-1.5 py-0.5 rounded bg-rose-100 text-rose-800">{fleetKpi.critical_count} D</span>
                  </div>
                </div>

                {/* Lost Cycle Hours */}
                <div className="bg-white p-3.5 sm:p-4 rounded-2xl border border-slate-200/80 shadow-xs">
                  <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wide flex items-center gap-1">
                    <Clock size={13} className="text-amber-500" /> Jam Siklus Hilang
                  </span>
                  <div className="flex items-baseline gap-1 mt-1.5">
                    <span className="text-2xl font-black text-amber-600 tabular-nums">{formatNumber(fleetKpi.total_loss_hours, 0)}</span>
                    <span className="text-xs font-semibold text-slate-400">Jam</span>
                  </div>
                  <p className="text-[10px] text-slate-400 mt-2 truncate">Molor Heating + Keep + Cooling</p>
                </div>

                {/* Steam Waste */}
                <div className="bg-white p-3.5 sm:p-4 rounded-2xl border border-slate-200/80 shadow-xs">
                  <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wide flex items-center gap-1">
                    <Droplet size={13} className="text-sky-500" /> Uap Terbuang
                  </span>
                  <div className="flex items-baseline gap-1 mt-1.5">
                    <span className="text-2xl font-black text-slate-900 tabular-nums">
                      {fleetKpi.total_steam_waste_kg >= 1000
                        ? formatNumber(fleetKpi.total_steam_waste_kg / 1000, 1)
                        : formatNumber(fleetKpi.total_steam_waste_kg, 0)}
                    </span>
                    <span className="text-xs font-semibold text-slate-400">
                      {fleetKpi.total_steam_waste_kg >= 1000 ? 'Ton' : 'kg'}
                    </span>
                  </div>
                  <p className="text-[10px] text-sky-600 font-semibold mt-2">
                    {formatRp((fleetKpi.total_steam_waste_kg || 0) * (fleetHealthData?.tariffs?.steam_cost_per_kg || 350))}
                  </p>
                </div>

                {/* Power Waste */}
                <div className="bg-white p-3.5 sm:p-4 rounded-2xl border border-slate-200/80 shadow-xs">
                  <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wide flex items-center gap-1">
                    <Zap size={13} className="text-amber-500" /> Listrik Terbuang
                  </span>
                  <div className="flex items-baseline gap-1 mt-1.5">
                    <span className="text-2xl font-black text-slate-900 tabular-nums">{formatNumber(fleetKpi.total_power_waste_kwh, 0)}</span>
                    <span className="text-xs font-semibold text-slate-400">kWh</span>
                  </div>
                  <p className="text-[10px] text-amber-600 font-semibold mt-2">
                    {formatRp((fleetKpi.total_power_waste_kwh || 0) * (fleetHealthData?.tariffs?.electricity_base_rate || 1035.8))}
                  </p>
                </div>

                {/* Total Financial Loss */}
                <div className="bg-white p-3.5 sm:p-4 rounded-2xl border border-slate-200/80 shadow-xs">
                  <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wide flex items-center gap-1">
                    <DollarSign size={13} className="text-emerald-500" /> Total Pemborosan
                  </span>
                  <div className="flex items-baseline gap-1 mt-1.5">
                    <span className="text-xl sm:text-2xl font-black text-rose-600 tabular-nums">
                      {formatRp(fleetKpi.total_financial_loss_rp)}
                    </span>
                  </div>
                  <p className="text-[10px] text-slate-400 mt-2">Akumulasi Uap + Listrik</p>
                </div>

                {/* 30D Projection */}
                <div className="bg-gradient-to-br from-rose-500 to-rose-600 text-white p-3.5 sm:p-4 rounded-2xl shadow-xs">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-rose-100 flex items-center gap-1">
                      <Flame size={13} /> Proyeksi 30 Hari
                    </span>
                    <span className="text-[9px] bg-white/20 px-1.5 py-0.5 rounded font-bold">Run-Rate</span>
                  </div>
                  <div className="mt-1.5">
                    <span className="text-lg sm:text-xl font-black tracking-tight tabular-nums">
                      {formatRp(fleetKpi.projected_30d_loss_rp)}
                    </span>
                  </div>
                  <p className="text-[10px] text-rose-100 mt-2 truncate">
                    Mesin Kritis (C&D): <b>{formatRp(fleetKpi.projected_30d_critical_loss_rp)}</b>
                  </p>
                </div>
              </div>

              {/* 3. VISUAL FLEET CHARTS: QUADRANT MATRIX & TOP 10 WASTEFUL MACHINES */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Chart 1: Health Matrix (Scatter Quadrant) */}
                <SectionCard
                  title="Peta Kuadran: Kesehatan Mesin (MHI) vs Pemborosan"
                  subtitle="Sumbu X: Skor MHI (0–100) · Sumbu Y: Pemborosan Energi (Ribu Rp/Batch)"
                  icon={Activity}
                  action={
                    <span className="text-[10px] font-bold px-2 py-0.5 rounded-md bg-slate-100 text-slate-600">
                      {healthMatrixData.length} Mesin Dievaluasi
                    </span>
                  }
                >
                  <div className="p-4">
                    <div className="h-60 sm:h-64 w-full">
                      <ResponsiveContainer width="100%" height="100%">
                        <ScatterChart margin={{ top: 10, right: 15, bottom: 20, left: 5 }}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                          <XAxis
                            type="number"
                            dataKey="x"
                            name="MHI Score"
                            domain={[40, 100]}
                            tick={{ fontSize: 10, fill: '#64748b' }}
                            label={{ value: 'Machine Health Index (MHI)', position: 'insideBottom', offset: -10, fontSize: 10, fill: '#64748b' }}
                          />
                          <YAxis
                            type="number"
                            dataKey="y"
                            name="Waste (Ribu Rp)"
                            tick={{ fontSize: 10, fill: '#64748b' }}
                            label={{ value: 'Ribu Rp / Batch', angle: -90, position: 'insideLeft', fontSize: 10, fill: '#64748b' }}
                          />
                          <ZAxis type="number" dataKey="z" range={[60, 200]} />
                          <ReferenceLine x={70} stroke="#f59e0b" strokeDasharray="4 4" label={{ value: 'Batas MHI 70', position: 'insideTopLeft', fontSize: 9, fill: '#d97706' }} />
                          <ReferenceLine y={100} stroke="#ef4444" strokeDasharray="4 4" label={{ value: 'Rp 100rb/batch', position: 'insideBottomRight', fontSize: 9, fill: '#dc2626' }} />
                          <RechartsTooltip
                            cursor={{ strokeDasharray: '3 3' }}
                            content={({ active, payload }) => {
                              if (active && payload && payload.length) {
                                const p = payload[0].payload;
                                return (
                                  <div className="bg-slate-900 text-white p-2.5 rounded-xl shadow-xl text-xs space-y-1 border border-slate-700">
                                    <div className="font-bold flex items-center justify-between gap-3 border-b border-slate-700 pb-1">
                                      <span>{p.name}</span>
                                      <span className="px-1.5 py-0.5 rounded bg-indigo-500 font-bold text-[10px]">Grade {p.grade}</span>
                                    </div>
                                    <div>Skor Kesehatan: <b>{p.x} / 100</b></div>
                                    <div>Pemborosan: <b>{formatRp(p.waste_rp)} / batch</b></div>
                                    <div>Proyeksi 30 Hari: <b>{formatRp(p.waste_30d)}</b></div>
                                  </div>
                                );
                              }
                              return null;
                            }}
                          />
                          <Scatter
                            data={healthMatrixData}
                            onClick={(node) => node?.id && goToMachineReport(node.id)}
                            className="cursor-pointer"
                          >
                            {healthMatrixData.map((entry, index) => {
                              let col = '#10b981';
                              if (entry.grade === 'D') col = '#f43f5e';
                              else if (entry.grade === 'C') col = '#f59e0b';
                              else if (entry.grade === 'B') col = '#3b82f6';
                              return <Cell key={`cell-${index}`} fill={col} fillOpacity={0.85} stroke="#ffffff" strokeWidth={1.5} />;
                            })}
                          </Scatter>
                        </ScatterChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                </SectionCard>

                {/* Chart 2: Top 10 Wasteful Machines */}
                <SectionCard
                  title="Top 10 Mesin Potensi Pemborosan Terbesar"
                  subtitle="Proyeksi Biaya Energi Terbuang (Juta Rp / 30 Hari) bila tidak ditangani"
                  icon={BarChart2}
                  action={
                    <span className="text-[10px] font-bold px-2 py-0.5 rounded-md bg-rose-50 text-rose-700 border border-rose-200/60">
                      Prioritas Perbaikan
                    </span>
                  }
                >
                  <div className="p-4">
                    <div className="h-60 sm:h-64 w-full">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={topWasteMachines} margin={{ top: 10, right: 15, bottom: 20, left: 0 }}>
                          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                          <XAxis dataKey="name" tick={{ fontSize: 10, fill: '#64748b' }} interval={0} />
                          <YAxis tick={{ fontSize: 10, fill: '#64748b' }} label={{ value: 'Juta Rp / 30h', angle: -90, position: 'insideLeft', fontSize: 10, fill: '#64748b' }} />
                          <RechartsTooltip
                            content={({ active, payload }) => {
                              if (active && payload && payload.length) {
                                const p = payload[0].payload;
                                return (
                                  <div className="bg-slate-900 text-white p-2.5 rounded-xl shadow-xl text-xs space-y-1 border border-slate-700">
                                    <div className="font-bold border-b border-slate-700 pb-1">{p.name} (Grade {p.grade})</div>
                                    <div>Proyeksi Rugi 30h: <b>Rp {p.waste_jt} Juta</b></div>
                                    <div>Uap Terbuang: <b>{p.steam_ton} Ton</b></div>
                                    <div>Listrik Terbuang: <b>{formatNumber(p.power_kwh)} kWh</b></div>
                                  </div>
                                );
                              }
                              return null;
                            }}
                          />
                          <Bar
                            dataKey="waste_jt"
                            radius={[6, 6, 0, 0]}
                            onClick={(bar) => bar?.id && goToMachineReport(bar.id)}
                            className="cursor-pointer"
                          >
                            {topWasteMachines.map((entry, idx) => (
                              <Cell
                                key={`bar-${idx}`}
                                fill={entry.grade === 'D' ? '#f43f5e' : entry.grade === 'C' ? '#f59e0b' : '#3b82f6'}
                              />
                            ))}
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                </SectionCard>
              </div>

              {/* ═══════════════════════════════════════════════════════════════════════════ */}
              {/* 4. RIWAYAT DURASI HEATING, KEEP, COOLING — DIPISAH UAP vs LISTRIK           */}
              {/* ═══════════════════════════════════════════════════════════════════════════ */}
              <div className="grid grid-cols-1 xl:grid-cols-2 gap-6 items-start">

                {/* ── SECTION A: POTENSI PEMBOROSAN PEMAKAIAN UAP (STEAM WASTE) ── */}
                <SectionCard
                  title="Potensi Pemborosan Pemakaian Uap & Riwayat Durasi Fase"
                  subtitle="Dipicu oleh molornya durasi Heating (pemanasan lambat) & Keep/Holding (katup uap bocor/terbuka lama)"
                  icon={Droplet}
                  action={
                    <span className="px-2.5 py-1 rounded-full text-[11px] font-black bg-sky-50 text-sky-700 border border-sky-200/80 tabular-nums">
                      Total: {fleetKpi.total_steam_waste_kg >= 1000 ? `${formatNumber(fleetKpi.total_steam_waste_kg / 1000, 1)} Ton` : `${formatNumber(fleetKpi.total_steam_waste_kg, 0)} kg`}
                    </span>
                  }
                >
                  <div className="p-3.5 sm:p-4 space-y-3">
                    {/* Explain Banner */}
                    <div className="bg-sky-50/70 border border-sky-100 rounded-xl p-3 flex flex-wrap items-center justify-between gap-2 text-xs">
                      <div className="flex items-center gap-2 text-sky-900">
                        <Flame size={15} className="text-rose-500 shrink-0" />
                        <span>
                          Fokus Fase Uap: <strong className="text-rose-600">Heating</strong> & <strong className="text-amber-600">Keep (Holding)</strong>
                        </span>
                      </div>
                      <span className="text-[11px] font-bold text-sky-800">
                        Proyeksi 30h: {formatNumber((fleetKpi.projected_30d_steam_waste_kg || 0) / 1000, 1)} Ton Uap
                      </span>
                    </div>

                    {/* Machine Cards List for Steam Waste */}
                    <div className="space-y-3">
                      {topSteamWasteList.map((m, idx) => {
                        const isExpanded = expandedSteamMachineId === m.machine_id;
                        const gradeCls = GRADE_BADGE[m.health_grade] || GRADE_BADGE.B;

                        return (
                          <div
                            key={m.machine_id}
                            className="rounded-xl border border-slate-200/80 bg-white hover:border-sky-300/80 transition-all p-3 shadow-2xs"
                          >
                            {/* Top Row: Rank, Name, MHI Grade, Steam Waste Kg & Rp */}
                            <div className="flex items-start justify-between gap-2">
                              <div className="flex items-center gap-2.5 min-w-0">
                                <span className="w-6 h-6 rounded-lg bg-sky-600 text-white font-black text-xs flex items-center justify-center shrink-0">
                                  #{idx + 1}
                                </span>
                                <div className="min-w-0">
                                  <div className="flex items-center gap-2 flex-wrap">
                                    <button
                                      type="button"
                                      onClick={() => goToMachineReport(m.machine_id)}
                                      className="text-sm font-black text-slate-900 hover:text-sky-600 flex items-center gap-1 transition-colors cursor-pointer"
                                    >
                                      {m.machine_name}
                                      <ExternalLink size={11} className="text-slate-400" />
                                    </button>
                                    <span className="text-[10px] font-semibold text-slate-400">{m.group_name}</span>
                                    <span className={`text-[10px] font-black px-1.5 py-0.2 rounded border ${gradeCls}`}>
                                      Grade {m.health_grade} ({m.health_score})
                                    </span>
                                  </div>
                                  {m.primary_diagnosis?.title && (
                                    <p className="text-[11px] text-slate-500 mt-0.5 truncate">
                                      Diagnosa: <strong className="text-slate-700">{m.primary_diagnosis.title}</strong>
                                    </p>
                                  )}
                                </div>
                              </div>

                              <div className="text-right shrink-0">
                                <div className="text-sm font-black text-sky-700 tabular-nums">
                                  {m.waste_steam_kg >= 1000
                                    ? `${formatNumber(m.waste_steam_kg / 1000, 2)} Ton`
                                    : `${formatNumber(m.waste_steam_kg, 0)} kg`}{' '}
                                  <span className="text-[10px] font-bold text-rose-600">Terbuang</span>
                                </div>
                                <div className="text-[11px] font-bold text-slate-600 tabular-nums">
                                  {formatRp(m.waste_steam_rp)} <span className="text-slate-400 font-normal">• 30h: {formatRp(m.projected_30d_steam_rp)}</span>
                                </div>
                              </div>
                            </div>

                            {/* Phase Duration Bar & 3 Phase Breakdown (Heating, Keep, Cooling) */}
                            <PhaseDurationBreakdown machine={m} highlightMode="steam" />

                            {/* Toggle Button for Batch History */}
                            <div className="mt-2 pt-2 border-t border-slate-100 flex items-center justify-between">
                              <button
                                type="button"
                                onClick={() => setExpandedSteamMachineId(isExpanded ? null : m.machine_id)}
                                className="text-[11px] font-bold text-sky-600 hover:text-sky-700 flex items-center gap-1 cursor-pointer"
                              >
                                {isExpanded ? (
                                  <>Sembunyikan Riwayat Batch <ChevronUp size={13} /></>
                                ) : (
                                  <>Lihat Riwayat Durasi per Batch ({m.recent_batches?.length || 0} Batch Terakhir) <ChevronDown size={13} /></>
                                )}
                              </button>
                              <button
                                type="button"
                                onClick={() => goToMachineReport(m.machine_id)}
                                className="text-[11px] font-semibold text-slate-500 hover:text-sky-600 flex items-center gap-0.5 cursor-pointer"
                              >
                                Detail Analitik <ChevronRight size={12} />
                              </button>
                            </div>

                            {/* Expanded Batch-by-Batch Duration History Table */}
                            {isExpanded && m.recent_batches?.length > 0 && (
                              <div className="mt-2.5 overflow-x-auto bg-slate-50/80 rounded-xl border border-slate-200/70 p-2">
                                <table className="w-full text-left text-[11px]">
                                  <thead>
                                    <tr className="border-b border-slate-200/70 text-[10px] text-slate-400 uppercase font-bold">
                                      <th className="pb-1.5 pr-2">Batch / Waktu</th>
                                      <th className="pb-1.5 pr-2">Prog</th>
                                      <th className="pb-1.5 pr-2 text-right">Heating</th>
                                      <th className="pb-1.5 pr-2 text-right">Keep</th>
                                      <th className="pb-1.5 pr-2 text-right">Cooling</th>
                                      <th className="pb-1.5 text-right">Uap Boros</th>
                                    </tr>
                                  </thead>
                                  <tbody className="divide-y divide-slate-200/50 tabular-nums">
                                    {m.recent_batches.map((b, bi) => (
                                      <tr key={b.id || bi} className="hover:bg-white transition-colors">
                                        <td className="py-1.5 pr-2 font-semibold text-slate-700 whitespace-nowrap">
                                          #{b.batch_number} <span className="text-[10px] text-slate-400 font-normal">({b.date_str} {b.time_str})</span>
                                        </td>
                                        <td className="py-1.5 pr-2 text-slate-600 whitespace-nowrap">{b.program_name}</td>
                                        <td className="py-1.5 pr-2 text-right whitespace-nowrap">
                                          <span className="font-bold text-slate-800">{b.heat_mins}m</span>
                                          {b.delta_heat != null && (
                                            <span className={`ml-1 text-[10px] font-bold ${b.delta_heat > 5 ? 'text-rose-600' : 'text-emerald-600'}`}>
                                              ({b.delta_heat > 0 ? `+${b.delta_heat}` : b.delta_heat}m)
                                            </span>
                                          )}
                                        </td>
                                        <td className="py-1.5 pr-2 text-right whitespace-nowrap">
                                          <span className="font-bold text-slate-800">{b.steady_mins}m</span>
                                          {b.delta_steady != null && (
                                            <span className={`ml-1 text-[10px] font-bold ${b.delta_steady > 5 ? 'text-amber-600' : 'text-emerald-600'}`}>
                                              ({b.delta_steady > 0 ? `+${b.delta_steady}` : b.delta_steady}m)
                                            </span>
                                          )}
                                        </td>
                                        <td className="py-1.5 pr-2 text-right whitespace-nowrap">
                                          <span className="font-bold text-slate-800">{b.cool_mins}m</span>
                                          {b.delta_cool != null && (
                                            <span className={`ml-1 text-[10px] font-bold ${b.delta_cool > 5 ? 'text-sky-600' : 'text-emerald-600'}`}>
                                              ({b.delta_cool > 0 ? `+${b.delta_cool}` : b.delta_cool}m)
                                            </span>
                                          )}
                                        </td>
                                        <td className="py-1.5 text-right font-bold text-rose-600 whitespace-nowrap">
                                          {b.waste_steam_kg > 0 ? `${b.waste_steam_kg} kg` : 'Normal'}
                                        </td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </SectionCard>

                {/* ── SECTION B: POTENSI PEMBOROSAN PEMAKAIAN LISTRIK (POWER WASTE) ── */}
                <SectionCard
                  title="Potensi Pemborosan Pemakaian Listrik & Riwayat Durasi Fase"
                  subtitle="Pompa sirkulasi & motor winch menyedot listrik ekstra selama waktu molor di fase Heating, Keep, maupun Cooling"
                  icon={Zap}
                  action={
                    <span className="px-2.5 py-1 rounded-full text-[11px] font-black bg-amber-50 text-amber-800 border border-amber-200/80 tabular-nums">
                      Total: {formatNumber(fleetKpi.total_power_waste_kwh, 0)} kWh
                    </span>
                  }
                >
                  <div className="p-3.5 sm:p-4 space-y-3">
                    {/* Explain Banner */}
                    <div className="bg-amber-50/70 border border-amber-100 rounded-xl p-3 flex flex-wrap items-center justify-between gap-2 text-xs">
                      <div className="flex items-center gap-2 text-amber-900">
                        <Zap size={15} className="text-amber-600 shrink-0" />
                        <span>
                          Fokus Fase Listrik: <strong className="text-rose-600">Heating</strong> + <strong className="text-amber-600">Keep</strong> + <strong className="text-sky-600">Cooling Molor</strong>
                        </span>
                      </div>
                      <span className="text-[11px] font-bold text-amber-800">
                        Proyeksi 30h: {formatNumber(fleetKpi.projected_30d_power_waste_kwh || 0, 0)} kWh
                      </span>
                    </div>

                    {/* Machine Cards List for Power/Electricity Waste */}
                    <div className="space-y-3">
                      {topPowerWasteList.map((m, idx) => {
                        const isExpanded = expandedPowerMachineId === m.machine_id;
                        const gradeCls = GRADE_BADGE[m.health_grade] || GRADE_BADGE.B;

                        return (
                          <div
                            key={m.machine_id}
                            className="rounded-xl border border-slate-200/80 bg-white hover:border-amber-300/80 transition-all p-3 shadow-2xs"
                          >
                            {/* Top Row: Rank, Name, Motor kW, Power Waste kWh & Rp */}
                            <div className="flex items-start justify-between gap-2">
                              <div className="flex items-center gap-2.5 min-w-0">
                                <span className="w-6 h-6 rounded-lg bg-amber-500 text-white font-black text-xs flex items-center justify-center shrink-0">
                                  #{idx + 1}
                                </span>
                                <div className="min-w-0">
                                  <div className="flex items-center gap-2 flex-wrap">
                                    <button
                                      type="button"
                                      onClick={() => goToMachineReport(m.machine_id)}
                                      className="text-sm font-black text-slate-900 hover:text-amber-600 flex items-center gap-1 transition-colors cursor-pointer"
                                    >
                                      {m.machine_name}
                                      <ExternalLink size={11} className="text-slate-400" />
                                    </button>
                                    <span className="text-[10px] font-bold px-1.5 py-0.2 rounded bg-slate-100 text-slate-600">
                                      Motor {m.nominal_power_kw} kW
                                    </span>
                                    <span className={`text-[10px] font-black px-1.5 py-0.2 rounded border ${gradeCls}`}>
                                      Grade {m.health_grade}
                                    </span>
                                  </div>
                                  <p className="text-[11px] text-slate-500 mt-0.5 truncate">
                                    Jam Molor Pompa: <strong className="text-amber-700">{m.waste_pump_hours} Jam</strong> (Cooling +{m.avg_delta_cool}m · Heating +{m.avg_delta_heat}m)
                                  </p>
                                </div>
                              </div>

                              <div className="text-right shrink-0">
                                <div className="text-sm font-black text-amber-700 tabular-nums">
                                  {formatNumber(m.waste_power_kwh, 1)} kWh{' '}
                                  <span className="text-[10px] font-bold text-rose-600">Terbuang</span>
                                </div>
                                <div className="text-[11px] font-bold text-slate-600 tabular-nums">
                                  {formatRp(m.waste_power_rp)} <span className="text-slate-400 font-normal">• 30h: {formatRp(m.projected_30d_power_rp)}</span>
                                </div>
                              </div>
                            </div>

                            {/* Phase Duration Bar & 3 Phase Breakdown (Heating, Keep, Cooling) */}
                            <PhaseDurationBreakdown machine={m} highlightMode="power" />

                            {/* Toggle Button for Batch History */}
                            <div className="mt-2 pt-2 border-t border-slate-100 flex items-center justify-between">
                              <button
                                type="button"
                                onClick={() => setExpandedPowerMachineId(isExpanded ? null : m.machine_id)}
                                className="text-[11px] font-bold text-amber-600 hover:text-amber-700 flex items-center gap-1 cursor-pointer"
                              >
                                {isExpanded ? (
                                  <>Sembunyikan Riwayat Batch <ChevronUp size={13} /></>
                                ) : (
                                  <>Lihat Riwayat Durasi & Listrik per Batch ({m.recent_batches?.length || 0} Batch) <ChevronDown size={13} /></>
                                )}
                              </button>
                              <button
                                type="button"
                                onClick={() => goToMachineReport(m.machine_id)}
                                className="text-[11px] font-semibold text-slate-500 hover:text-amber-600 flex items-center gap-0.5 cursor-pointer"
                              >
                                Detail Analitik <ChevronRight size={12} />
                              </button>
                            </div>

                            {/* Expanded Batch-by-Batch Duration & Power History Table */}
                            {isExpanded && m.recent_batches?.length > 0 && (
                              <div className="mt-2.5 overflow-x-auto bg-slate-50/80 rounded-xl border border-slate-200/70 p-2">
                                <table className="w-full text-left text-[11px]">
                                  <thead>
                                    <tr className="border-b border-slate-200/70 text-[10px] text-slate-400 uppercase font-bold">
                                      <th className="pb-1.5 pr-2">Batch / Waktu</th>
                                      <th className="pb-1.5 pr-2">Prog</th>
                                      <th className="pb-1.5 pr-2 text-right">Heating</th>
                                      <th className="pb-1.5 pr-2 text-right">Keep</th>
                                      <th className="pb-1.5 pr-2 text-right">Cooling</th>
                                      <th className="pb-1.5 text-right">Listrik Boros</th>
                                    </tr>
                                  </thead>
                                  <tbody className="divide-y divide-slate-200/50 tabular-nums">
                                    {m.recent_batches.map((b, bi) => (
                                      <tr key={b.id || bi} className="hover:bg-white transition-colors">
                                        <td className="py-1.5 pr-2 font-semibold text-slate-700 whitespace-nowrap">
                                          #{b.batch_number} <span className="text-[10px] text-slate-400 font-normal">({b.date_str} {b.time_str})</span>
                                        </td>
                                        <td className="py-1.5 pr-2 text-slate-600 whitespace-nowrap">{b.program_name}</td>
                                        <td className="py-1.5 pr-2 text-right whitespace-nowrap">
                                          <span className="font-bold text-slate-800">{b.heat_mins}m</span>
                                          {b.delta_heat != null && (
                                            <span className={`ml-1 text-[10px] font-bold ${b.delta_heat > 5 ? 'text-rose-600' : 'text-emerald-600'}`}>
                                              ({b.delta_heat > 0 ? `+${b.delta_heat}` : b.delta_heat}m)
                                            </span>
                                          )}
                                        </td>
                                        <td className="py-1.5 pr-2 text-right whitespace-nowrap">
                                          <span className="font-bold text-slate-800">{b.steady_mins}m</span>
                                          {b.delta_steady != null && (
                                            <span className={`ml-1 text-[10px] font-bold ${b.delta_steady > 5 ? 'text-amber-600' : 'text-emerald-600'}`}>
                                              ({b.delta_steady > 0 ? `+${b.delta_steady}` : b.delta_steady}m)
                                            </span>
                                          )}
                                        </td>
                                        <td className="py-1.5 pr-2 text-right whitespace-nowrap">
                                          <span className="font-bold text-slate-800">{b.cool_mins}m</span>
                                          {b.delta_cool != null && (
                                            <span className={`ml-1 text-[10px] font-bold ${b.delta_cool > 5 ? 'text-sky-600' : 'text-emerald-600'}`}>
                                              ({b.delta_cool > 0 ? `+${b.delta_cool}` : b.delta_cool}m)
                                            </span>
                                          )}
                                        </td>
                                        <td className="py-1.5 text-right font-bold text-amber-700 whitespace-nowrap">
                                          {b.waste_power_kwh > 0 ? `${b.waste_power_kwh} kWh` : 'Normal'}
                                        </td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </SectionCard>

              </div>
            </>
          ) : null}

        </div>

      </div>

      {/* ═══════════════════════════════════════════════════════════════════════════ */}
      {/* MODAL: SCADA TELEMETRI REAL-TIME MESIN (LENGKAP DENGAN GRAFIK)             */}
      {/* ═══════════════════════════════════════════════════════════════════════════ */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex flex-col sm:items-center sm:justify-center sm:p-4 bg-slate-900/50 backdrop-blur-xs">
          <div className="bg-white w-full h-full sm:h-auto sm:max-h-[92vh] sm:rounded-2xl shadow-2xl sm:max-w-4xl flex flex-col overflow-hidden border border-slate-100">
            {/* Modal Header */}
            <div className="p-4 border-b border-slate-100 flex justify-between items-start gap-3 bg-slate-50 shrink-0">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <h2 className="text-base sm:text-xl font-bold text-slate-900 truncate">
                    {machineDetail ? machineDetail.machine.name : 'Memuat Telemetri...'}
                  </h2>
                  {machineDetail?.machine?.is_manual && (
                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-100 text-amber-700">MANUAL</span>
                  )}
                </div>
                {machineDetail && (
                  <p className="text-xs text-slate-500 mt-0.5">
                    {machineDetail.machine.group} • Telemetri Real-time & Grafik Siklus
                  </p>
                )}
              </div>

              <div className="flex items-center gap-2 shrink-0">
                {selectedMachineId && (
                  <button
                    type="button"
                    onClick={() => {
                      setIsModalOpen(false);
                      goToMachineAnalytics(selectedMachineId);
                    }}
                    className="inline-flex items-center gap-1 px-3 py-1.5 rounded-xl bg-sky-50 hover:bg-sky-100 text-sky-700 text-xs font-bold border border-sky-200/70 transition-colors cursor-pointer"
                  >
                    <span>Analitik Harian</span>
                    <ExternalLink size={12} />
                  </button>
                )}
                <button
                  onClick={() => setIsModalOpen(false)}
                  className="text-slate-400 hover:text-slate-600 bg-slate-200/80 hover:bg-slate-300 rounded-full p-2 transition-colors cursor-pointer"
                >
                  <X size={16} />
                </button>
              </div>
            </div>

            {/* Modal Body */}
            <div className="p-4 overflow-y-auto flex-1 custom-scrollbar">
              {machineDetailError ? (
                <div className="flex flex-col items-center justify-center p-8 text-center">
                  <div className="w-12 h-12 rounded-full bg-rose-50 text-rose-500 flex items-center justify-center mb-3">
                    <AlertCircle size={24} />
                  </div>
                  <p className="text-sm font-semibold text-slate-800 mb-1">{machineDetailError}</p>
                  <button
                    onClick={() => openMachineDetail(selectedMachineId)}
                    className="mt-3 px-4 py-2 bg-sky-600 hover:bg-sky-700 text-white rounded-xl text-xs font-semibold shadow-xs transition-colors"
                  >
                    Coba Lagi
                  </button>
                </div>
              ) : !machineDetail || machineDetailLoading ? (
                <div className="flex flex-col justify-center items-center h-56 gap-2">
                  <div className="animate-spin rounded-full h-9 w-9 border-2 border-sky-500 border-t-transparent" />
                  <span className="text-xs text-slate-400">Memuat grafik telemetri mesin...</span>
                </div>
              ) : (
                <div className="space-y-4">
                  {(() => {
                    const isHtoMachine = Boolean(
                      machineDetail?.energy_type === 'hto' ||
                      machineDetail?.secondary_metric?.type === 'hto' ||
                      (machineDetail?.machine?.energy_usage && String(machineDetail.machine.energy_usage).includes('kcal')) ||
                      (machineDetail?.machine?.name && machineDetail.machine.name.toLowerCase().includes('hto')) ||
                      (machineDetail?.machine?.code && machineDetail.machine.code.toLowerCase().includes('hto')) ||
                      (machineDetail?.machine?.group && (machineDetail.machine.group.includes('PRT') || machineDetail.machine.group.includes('HTO')))
                    );

                    const secMetricName = isHtoMachine ? 'Suhu Sirkulasi HTO (Oil_Temp)' : 'Tekanan Uap (Steam_Pr)';
                    const secMetricUnit = isHtoMachine ? '°C' : 'bar';
                    const secMetricKey = isHtoMachine ? 'hto_temp' : 'pressure';
                    const secMetricColor = isHtoMachine ? '#d97706' : '#7c3aed';

                    const chartTitle = isHtoMachine
                      ? (machineDetail.machine.is_manual
                          ? `Suhu HTO & Status ON/OFF ${machineDetail.batch?.is_active ? '(Sejak Batch Mulai)' : '(2 Jam Terakhir)'}`
                          : `Profil Suhu Mesin & HTO ${machineDetail.batch?.is_active ? '(Sejak Batch Mulai)' : '(2 Jam Terakhir)'}`)
                      : (machineDetail.machine.is_manual
                          ? `Tekanan Uap & Status ON/OFF ${machineDetail.batch?.is_active ? '(Sejak Batch Mulai)' : '(2 Jam Terakhir)'}`
                          : `Profil Suhu Mesin & Tekanan Uap ${machineDetail.batch?.is_active ? '(Sejak Batch Mulai)' : '(2 Jam Terakhir)'}`);

                    const lastDataPoint = (machineDetail.chart_data || []).slice(-1)[0];
                    const currentSecMetricVal = lastDataPoint
                      ? (isHtoMachine ? lastDataPoint.hto_temp : lastDataPoint.pressure)
                      : null;

                    return (
                      <>
                        {/* Top KPI Stats */}
                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
                          <div className="bg-slate-50 p-3 rounded-xl border border-slate-100">
                            <div className="text-[11px] text-slate-500 mb-0.5">Status Saat Ini</div>
                            <div className="text-sm font-bold text-slate-800">{machineDetail.machine.status}</div>
                            {(machineDetail.machine.status_since_display || machineDetail.machine.active_since) && (
                              <div className="text-[10px] text-emerald-600 mt-0.5">
                                {machineDetail.machine.status_since_display || `sejak ${machineDetail.machine.active_since}`}
                              </div>
                            )}
                          </div>

                          {!machineDetail.machine.is_manual ? (
                            <div className="bg-slate-50 p-3 rounded-xl border border-slate-100">
                              <div className="text-[11px] text-slate-500 mb-0.5">Suhu Aktual Mesin</div>
                              <div className="text-sm font-bold text-sky-700">
                                {machineDetail.machine.current_temp ?? machineDetail.machine.temperature ?? '-'} °C
                              </div>
                            </div>
                          ) : (
                            <div className="bg-slate-50 p-3 rounded-xl border border-slate-100">
                              <div className="text-[11px] text-slate-500 mb-0.5">Mode Mesin</div>
                              <div className="text-sm font-bold text-amber-700">Manual (Digital Input)</div>
                            </div>
                          )}

                          {isHtoMachine ? (
                            <div className="bg-slate-50 p-3 rounded-xl border border-slate-100">
                              <div className="text-[11px] text-slate-500 mb-0.5">Beban Energi HTO</div>
                              <div className="text-sm font-bold text-amber-600">
                                {formatNumber(machineDetail.machine.hto_usage ?? machineDetail.machine.hto, 0)} kCal/h
                              </div>
                            </div>
                          ) : (
                            <div className="bg-slate-50 p-3 rounded-xl border border-slate-100">
                              <div className="text-[11px] text-slate-500 mb-0.5">Pemakaian Uap</div>
                              <div className="text-sm font-bold text-sky-600">
                                {formatNumber(machineDetail.machine.steam_usage ?? machineDetail.machine.steam ?? 0, 1)} kg/h
                              </div>
                            </div>
                          )}

                          <div className="bg-slate-50 p-3 rounded-xl border border-slate-100">
                            <div className="text-[11px] text-slate-500 mb-0.5">
                              {isHtoMachine ? 'Suhu HTO (Oil_Temp)' : 'Tekanan Uap (Steam_Pr)'}
                            </div>
                            <div className={`text-sm font-bold ${isHtoMachine ? 'text-amber-700' : 'text-purple-700'}`}>
                              {currentSecMetricVal !== null && currentSecMetricVal !== undefined
                                ? `${formatNumber(currentSecMetricVal, isHtoMachine ? 1 : 2)} ${secMetricUnit}`
                                : '-'}
                            </div>
                            {machineDetail.batch?.is_active && (
                              <div className="text-[10px] text-slate-400 mt-0.5 truncate">
                                Batch #{machineDetail.batch.batch_number}
                              </div>
                            )}
                          </div>
                        </div>

                        {/* Main Telemetry Chart */}
                        <div className="bg-white p-3.5 border border-slate-200/80 rounded-xl shadow-2xs">
                          <div className="flex items-center justify-between mb-3">
                            <h3 className="text-xs sm:text-sm font-bold text-slate-800">
                              {chartTitle}
                            </h3>
                            <span className="text-[11px] font-semibold text-slate-400">
                              {machineDetail.batch?.is_active ? 'Siklus Aktif' : '2 Jam Terakhir'}
                            </span>
                          </div>
                          <div className="h-[240px] sm:h-[280px] w-full">
                            <ResponsiveContainer debounce={50} width="100%" height="100%">
                              <LineChart data={machineDetail.chart_data || []} margin={{ top: 8, right: 12, left: 6, bottom: 4 }}>
                                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                                <XAxis dataKey="time" tick={{ fontSize: 10, fill: '#64748b' }} minTickGap={30} axisLine={{ stroke: '#cbd5e1' }} tickLine={false} />
                                {machineDetail.machine.is_manual ? (
                                  <>
                                    <YAxis yAxisId="left" tick={{ fontSize: 10, fill: secMetricColor }} domain={['auto', 'auto']} width={38} tickMargin={4} unit={` ${secMetricUnit}`} />
                                    <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 10, fill: '#10b981' }} domain={[0, 1]} ticks={[0, 1]} tickFormatter={(v) => (v === 1 ? 'ON' : 'OFF')} width={30} tickMargin={4} />
                                    <RechartsTooltip
                                      contentStyle={{ borderRadius: '10px', border: '1px solid #cbd5e1', fontSize: '12px', boxShadow: '0 4px 12px rgba(0,0,0,0.08)' }}
                                      formatter={(value, name) => {
                                        if (name === 'Status Mesin') return [value === 1 ? 'ON (Running)' : 'OFF (Stop)', name];
                                        if (name === secMetricName) return [`${formatNumber(value, isHtoMachine ? 1 : 2)} ${secMetricUnit}`, name];
                                        return [value, name];
                                      }}
                                    />
                                    <Legend verticalAlign="bottom" wrapperStyle={{ fontSize: '11px', paddingTop: '8px' }} />
                                    <Line isAnimationActive={isAnimActive} yAxisId="left" type="monotone" dataKey={secMetricKey} stroke={secMetricColor} strokeWidth={2} dot={false} name={secMetricName} />
                                    <Line isAnimationActive={isAnimActive} yAxisId="right" type="stepAfter" dataKey="is_on" stroke="#10b981" strokeWidth={2.5} dot={false} name="Status Mesin" />
                                  </>
                                ) : (
                                  <>
                                    <YAxis yAxisId="left" tick={{ fontSize: 10, fill: '#0284c7' }} domain={['auto', 'auto']} width={38} tickMargin={4} unit="°" />
                                    <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 10, fill: secMetricColor }} domain={['auto', 'auto']} width={38} tickMargin={4} unit={` ${secMetricUnit}`} />
                                    <RechartsTooltip
                                      contentStyle={{ borderRadius: '10px', border: '1px solid #cbd5e1', fontSize: '12px', boxShadow: '0 4px 12px rgba(0,0,0,0.08)' }}
                                      formatter={(value, name) => {
                                        if (name === 'Suhu Mesin') return [`${formatNumber(value, 1)} °C`, name];
                                        if (name === secMetricName) return [`${formatNumber(value, isHtoMachine ? 1 : 2)} ${secMetricUnit}`, name];
                                        return [value, name];
                                      }}
                                    />
                                    <Legend verticalAlign="bottom" wrapperStyle={{ fontSize: '11px', paddingTop: '8px' }} />
                                    <Line isAnimationActive={isAnimActive} yAxisId="left" type="monotone" dataKey="temp" stroke="#0284c7" strokeWidth={2.2} dot={false} name="Suhu Mesin" activeDot={{ r: 4, fill: '#0284c7' }} />
                                    <Line isAnimationActive={isAnimActive} yAxisId="right" type="monotone" dataKey={secMetricKey} stroke={secMetricColor} strokeWidth={2} dot={false} name={secMetricName} activeDot={{ r: 4, fill: secMetricColor }} />
                                  </>
                                )}
                              </LineChart>
                            </ResponsiveContainer>
                          </div>
                        </div>

                        {/* Secondary Chart: Plant Active Machines Concurrent Load (Khusus Mesin Uap) */}
                        {!machineDetail.machine.is_manual && !isHtoMachine && (machineDetail.chart_data?.length > 0) && (
                          <div className="bg-white p-3.5 border border-slate-200/80 rounded-xl shadow-2xs">
                            <h3 className="text-xs sm:text-sm font-bold text-slate-800 mb-2">
                              Beban Konkuren: Jumlah Mesin Aktif (Plant)
                            </h3>
                            <div className="h-[110px] sm:h-[130px] w-full">
                              <ResponsiveContainer debounce={50} width="100%" height="100%">
                                <AreaChart data={machineDetail.chart_data || []} margin={{ top: 5, right: 10, left: -18, bottom: 5 }}>
                                  <defs>
                                    <linearGradient id="colorConcurrentCount" x1="0" y1="0" x2="0" y2="1">
                                      <stop offset="5%" stopColor="#f59e0b" stopOpacity={0.7} />
                                      <stop offset="95%" stopColor="#f59e0b" stopOpacity={0} />
                                    </linearGradient>
                                  </defs>
                                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                                  <XAxis dataKey="time" tick={{ fontSize: 10, fill: '#94a3b8' }} minTickGap={40} />
                                  <YAxis tick={{ fontSize: 10, fill: '#94a3b8' }} domain={[0, 'dataMax + 4']} width={32} />
                                  <RechartsTooltip contentStyle={{ borderRadius: '10px', border: '1px solid #e2e8f0', fontSize: '12px' }} />
                                  <Area isAnimationActive={isAnimActive} type="step" dataKey="active_count" stroke="#f59e0b" fillOpacity={1} fill="url(#colorConcurrentCount)" name="Mesin Aktif Bersamaan" />
                                </AreaChart>
                              </ResponsiveContainer>
                            </div>
                          </div>
                        )}
                      </>
                    );
                  })()}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
