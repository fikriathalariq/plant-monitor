import React, { useState, useEffect, useMemo, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import api from '../lib/api';
import {
  PieChart, Pie, Cell, ResponsiveContainer, Tooltip as RechartsTooltip,
  ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, ZAxis, ComposedChart, Line, BarChart, Bar, Legend, ReferenceLine
} from 'recharts';
import {
  Calendar, Activity, Search, Cpu, CheckCircle, CheckCircle2, Clock, AlertTriangle,
  AlertCircle, Settings, ChevronDown, ChevronUp, ArrowRight, ArrowUpRight, TrendingUp,
  TrendingDown, Minus, Flame, Snowflake, Gauge, Zap, DollarSign, Wrench, ExternalLink,
  Filter, HelpCircle, Layers, BarChart3, RefreshCw, ShieldCheck, Printer
} from 'lucide-react';

import { ShareToChatButton } from '../components/chat/ShareToChatButton';

const GRADE_STYLES = {
  A: {
    badge: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    dot: 'bg-emerald-500',
    text: 'text-emerald-700',
    label: 'Grade A (Prima)'
  },
  B: {
    badge: 'bg-blue-50 text-blue-700 border-blue-200',
    dot: 'bg-blue-500',
    text: 'text-blue-700',
    label: 'Grade B (Baik)'
  },
  C: {
    badge: 'bg-amber-50 text-amber-700 border-amber-200',
    dot: 'bg-amber-500',
    text: 'text-amber-700',
    label: 'Grade C (Pantau)'
  },
  D: {
    badge: 'bg-rose-50 text-rose-700 border-rose-200',
    dot: 'bg-rose-500',
    text: 'text-rose-700',
    label: 'Grade D (Kritis)'
  }
};

const DIAGNOSIS_TONES = {
  rose: {
    box: 'bg-rose-50/80 border-rose-200 text-rose-900',
    badge: 'bg-rose-600 text-white',
    icon: Wrench
  },
  amber: {
    box: 'bg-amber-50/80 border-amber-200 text-amber-900',
    badge: 'bg-amber-600 text-white',
    icon: AlertTriangle
  },
  blue: {
    box: 'bg-sky-50/80 border-sky-200 text-sky-900',
    badge: 'bg-sky-600 text-white',
    icon: Snowflake
  },
  emerald: {
    box: 'bg-emerald-50/80 border-emerald-200 text-emerald-900',
    badge: 'bg-emerald-600 text-white',
    icon: ShieldCheck
  },
  slate: {
    box: 'bg-slate-50 border-slate-200 text-slate-800',
    badge: 'bg-slate-600 text-white',
    icon: Gauge
  }
};

const formatRp = (val) => {
  if (val == null || isNaN(val)) return 'Rp 0';
  return `Rp ${Math.round(val).toLocaleString('id-ID')}`;
};

const formatMachineCaption = (m) => {
  const gName = (m.group_name || '').toLowerCase();
  const mName = (m.machine_name || '').toUpperCase();

  let code = 'MC';
  if (mName.startsWith('JR') || gName.includes('relax')) {
    code = 'JR';
  } else if (mName.startsWith('JD') || gName.includes('dyeing')) {
    code = 'JD';
  } else if (mName.startsWith('ZET') || gName.includes('print')) {
    code = 'ZET';
  } else if (m.machine_code) {
    code = m.machine_code.split(' ')[0] || 'MC';
  }

  let bldg = 'PRC';
  if (gName.includes('print')) {
    bldg = 'PRT';
  } else if (gName.includes('finish')) {
    bldg = 'FIN';
  }

  return `${code} ${bldg} . Batch hari ini ${m.total_processes_day || 0}/${m.evaluated_batches_count || 0}`;
};

const numFmt = (val, dec = 1) => {
  if (val == null || isNaN(val)) return '-';
  return Number(val).toLocaleString('id-ID', { minimumFractionDigits: dec, maximumFractionDigits: dec });
};

export default function MachineDailyReport() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const targetMachineIdParam = searchParams.get('machineId') || searchParams.get('machine_id') || searchParams.get('machine');
  const targetWindowParam = searchParams.get('window');
  const targetDateParam = searchParams.get('date');
  const targetSubTabParam = searchParams.get('tab');

  const [selectedDate, setSelectedDate] = useState(() => {
    if (targetDateParam && /^\d{4}-\d{2}-\d{2}$/.test(targetDateParam)) {
      return targetDateParam;
    }
    const now = new Date();
    if (now.getHours() < 6) now.setDate(now.getDate() - 1);
    return now.toISOString().split('T')[0];
  });

  const [windowRange, setWindowRange] = useState(() => {
    const win = (targetWindowParam || '').toUpperCase();
    return ['1D', '7D', '30D'].includes(win) ? win : '1D';
  });

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Filters
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('ALL'); // 'ALL' | 'CRITICAL' | 'WARNING' | 'HEALTHY'
  const [groupFilter, setGroupFilter] = useState('ALL'); // 'ALL' | 'JD' | 'JR' | 'ZET'
  const [sortBy, setSortBy] = useState('critical'); // 'critical' | 'waste' | 'health_desc' | 'name'

  // Expanded Drawer State
  const [expandedMachineId, setExpandedMachineId] = useState(null);
  const [drawerSubTab, setDrawerSubTab] = useState(() => {
    const tab = targetSubTabParam || 'programs';
    return ['programs', 'charts', 'projection', 'prescription'].includes(tab) ? tab : 'programs';
  }); // 'programs' | 'charts' | 'projection' | 'prescription'
  const [activeChartMode, setActiveChartMode] = useState('durations'); // 'durations' | 'correlation' | 'spc'
  const [selectedChartProgram, setSelectedChartProgram] = useState({});
  const [selectedChartBatch, setSelectedChartBatch] = useState({}); // { [machineId]: batchId }
  const [expandedProgramRow, setExpandedProgramRow] = useState({}); // { [machineId]: programName }
  const [programAnomalyFilter, setProgramAnomalyFilter] = useState({}); // { [machineId]: boolean }
  const [scatterPhaseMode, setScatterPhaseMode] = useState('heating'); // 'heating' | 'cooling'

  const fetchReport = async (date, win) => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get(`/report/machine-daily-summary?date=${date}&window=${win}`);
      setData(res.data);
    } catch (err) {
      console.error('Failed to fetch machine daily summary', err);
      const msg = err.response?.data?.detail || err.response?.data?.message || 'Gagal mengambil data laporan mesin.';
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchReport(selectedDate, windowRange);
  }, [selectedDate, windowRange]);

  // Auto-expand and scroll to target machine if passed via URL params
  const lastTargetIdRef = useRef(null);
  useEffect(() => {
    if (!targetMachineIdParam || !data?.machines) return;
    if (lastTargetIdRef.current === targetMachineIdParam && expandedMachineId != null) return;

    const targetMachine = data.machines.find(
      (m) =>
        String(m.machine_id) === String(targetMachineIdParam) ||
        String(m.machine_name).toLowerCase() === String(targetMachineIdParam).toLowerCase()
    );

    if (targetMachine) {
      const mId = targetMachine.machine_id;
      setExpandedMachineId(mId);
      setStatusFilter('ALL');
      setGroupFilter('ALL');
      lastTargetIdRef.current = targetMachineIdParam;

      const timer = setTimeout(() => {
        const el =
          document.getElementById(`machine-row-${mId}`) ||
          document.getElementById(`machine-card-${mId}`);
        if (el) {
          el.scrollIntoView({ behavior: 'smooth', block: 'center' });
          el.classList.add('ring-2', 'ring-sky-500', 'bg-sky-50/70');
          setTimeout(() => {
            el.classList.remove('ring-2', 'ring-sky-500');
          }, 3500);
        }
      }, 400);

      return () => clearTimeout(timer);
    }
  }, [targetMachineIdParam, data]);

  // Filtering & Sorting
  const filteredMachines = useMemo(() => {
    if (!data?.machines) return [];
    let list = [...data.machines];

    // Search query
    const q = searchQuery.trim().toLowerCase();
    if (q) {
      list = list.filter(m =>
        m.machine_name.toLowerCase().includes(q) ||
        (m.machine_code && m.machine_code.toLowerCase().includes(q)) ||
        m.group_name.toLowerCase().includes(q)
      );
    }

    // Status filter
    if (statusFilter === 'CRITICAL') {
      list = list.filter(m => m.health_grade === 'D');
    } else if (statusFilter === 'WARNING') {
      list = list.filter(m => m.health_grade === 'C');
    } else if (statusFilter === 'HEALTHY') {
      list = list.filter(m => m.health_grade === 'A' || m.health_grade === 'B');
    }

    // Group filter
    if (groupFilter === 'JD') {
      list = list.filter(m => m.machine_name.startsWith('JD ') || m.machine_name.startsWith('JD_'));
    } else if (groupFilter === 'JR') {
      list = list.filter(m => m.machine_name.startsWith('JR ') || m.machine_name.startsWith('JR_'));
    } else if (groupFilter === 'ZET') {
      list = list.filter(m => m.machine_name.startsWith('ZET ') || m.machine_name.startsWith('ZET_'));
    }

    // Sorting
    if (sortBy === 'critical') {
      list.sort((a, b) => a.health_score - b.health_score);
    } else if (sortBy === 'waste') {
      list.sort((a, b) => b.projected_30d_rp - a.projected_30d_rp);
    } else if (sortBy === 'health_desc') {
      list.sort((a, b) => b.health_score - a.health_score);
    }

    return list;
  }, [data, searchQuery, statusFilter, groupFilter, sortBy]);

  // Scatter plot data for Health Matrix: Health Score vs 30D Waste Rp
  const healthMatrixData = useMemo(() => {
    if (!data?.machines) return [];
    return data.machines.map(m => ({
      x: m.health_score,
      y: Math.round(m.avg_waste_rp_batch / 1000), // in ribuan Rp / batch
      z: m.total_processes_day || m.evaluated_batches_count || 1,
      name: m.machine_name,
      grade: m.health_grade,
      id: m.machine_id,
      waste_rp: m.avg_waste_rp_batch,
      waste_30d: m.projected_30d_rp,
      dh: m.avg_delta_heat,
      dc: m.avg_delta_cool
    }));
  }, [data]);

  // Top 10 Wasteful Machines for Bar Chart
  const topWasteMachines = useMemo(() => {
    if (!data?.machines) return [];
    const sorted = [...data.machines].sort((a, b) => b.projected_30d_rp - a.projected_30d_rp);
    return sorted.slice(0, 10).map(m => ({
      name: m.machine_name,
      id: m.machine_id,
      grade: m.health_grade,
      waste_jt: Math.round((m.projected_30d_rp / 1000000) * 10) / 10,
      steam_ton: Math.round((m.projected_30d_steam_kg / 1000) * 10) / 10,
      power_kwh: m.projected_30d_power_kwh
    }));
  }, [data]);

  const toggleExpand = (id) => {
    setExpandedMachineId(expandedMachineId === id ? null : id);
  };

  const expandedMachine = useMemo(() => {
    if (!expandedMachineId || !data?.machines) return null;
    return data.machines.find(m => m.machine_id === expandedMachineId) || null;
  }, [expandedMachineId, data]);

  const kpi = data?.fleet_kpi;

  const renderMachineDrawer = (m) => {
    const gStyle = GRADE_STYLES[m.health_grade] || GRADE_STYLES.B;
    const diagTone = DIAGNOSIS_TONES[m.primary_diagnosis.tone] || DIAGNOSIS_TONES.slate;
    const DiagIcon = diagTone.icon;

    return (
      <div className="p-3 sm:p-5 space-y-4 max-w-full overflow-hidden">

                                  {/* Drawer Header Banner */}

                                  <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 bg-white p-4 rounded-2xl border border-slate-200 shadow-2xs">

                                    <div className="flex items-center gap-3">

                                      <div className="w-12 h-12 rounded-xl bg-indigo-600 text-white flex items-center justify-center font-black text-sm shadow-xs">

                                        {m.machine_name}

                                      </div>

                                      <div>

                                        <div className="flex items-center gap-2">

                                          <h4 className="text-base font-black text-slate-900">{m.machine_name} ({m.group_name})</h4>

                                          <span className={`px-2.5 py-0.5 rounded-full text-xs font-bold border ${gStyle.badge}`}>

                                            Skor MHI: {m.health_score} / 100 ({gStyle.label})

                                          </span>

                                        </div>

                                        <p className="text-xs text-slate-500 mt-0.5">

                                          Daya Nominal: {m.nominal_power_kw} kW • Tekanan Uap Rata-rata: {m.avg_steam_pressure || '-'} bar • Sampel Evaluasi: {m.evaluated_batches_count} Batch

                                        </p>

                                      </div>

                                    </div>

                                    {/* Action Shortcuts */}

                                    <div className="flex items-center gap-2">

                                      <a

                                        href={`/machine-report/${m.machine_id}/${selectedDate}/`}

                                        target="_blank"

                                        rel="noreferrer"

                                        onClick={(e) => e.stopPropagation()}

                                        className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold transition-colors shadow-2xs cursor-pointer"

                                        title="Buka laporan bulanan komprehensif siap print (A4)"

                                      >

                                        <Printer size={13} />

                                        <span>Lihat Report Lengkap</span>

                                        <ExternalLink size={12} />

                                      </a>

                                    </div>

                                  </div>

                                  {/* Sub-Tab Navigation inside Drawer */}

                                  <div className="flex space-x-1.5 bg-slate-200/70 p-1 rounded-xl max-w-full overflow-x-auto no-scrollbar text-xs font-bold whitespace-nowrap">

                                    <button

                                      type="button"

                                      onClick={() => setDrawerSubTab('programs')}

                                      className={`px-3 py-1.5 rounded-lg transition-all cursor-pointer ${

                                        drawerSubTab === 'programs' ? 'bg-white text-slate-900 shadow-2xs' : 'text-slate-600 hover:text-slate-900'

                                      }`}

                                    >

                                      1. Matriks Kepatuhan per Program ({m.programs.length})

                                    </button>

                                    <button

                                      type="button"

                                      onClick={() => setDrawerSubTab('charts')}

                                      className={`px-3 py-1.5 rounded-lg transition-all cursor-pointer ${

                                        drawerSubTab === 'charts' ? 'bg-white text-slate-900 shadow-2xs' : 'text-slate-600 hover:text-slate-900'

                                      }`}

                                    >

                                      2. Grafik Diagnostik Multi-Mode

                                    </button>

                                    <button

                                      type="button"

                                      onClick={() => setDrawerSubTab('batches')}

                                      className={`px-3 py-1.5 rounded-lg transition-all cursor-pointer ${

                                        drawerSubTab === 'batches' ? 'bg-white text-slate-900 shadow-2xs' : 'text-slate-600 hover:text-slate-900'

                                      }`}

                                    >

                                      3. Riwayat Batch Terbaru ({m.recent_batches.length})

                                    </button>

                                    <button

                                      type="button"

                                      onClick={() => setDrawerSubTab('prescription')}

                                      className={`px-3 py-1.5 rounded-lg transition-all cursor-pointer ${

                                        drawerSubTab === 'prescription' ? 'bg-white text-slate-900 shadow-2xs' : 'text-slate-600 hover:text-slate-900'

                                      }`}

                                    >

                                      4. Rekomendasi Preskriptif & Finansial

                                    </button>

                                  </div>

                                  {/* ── Sub-Panel 1: Program Compliance Matrix & Drill-down Anomali ── */}

                                  {drawerSubTab === 'programs' && (() => {

                                    // Pemetaan label anomali resmi sistem (AnomalyThresholdMaster & DataAnomaly)

                                    const ANOMALY_FLAG_MAP = {

                                      SUHU: { label: 'Suhu Melenceng', color: 'bg-amber-100 text-amber-800 border-amber-300' },

                                      SUHU_HARD: { label: 'Suhu Ekstrem (>25°C)', color: 'bg-rose-100 text-rose-800 border-rose-300' },

                                      HEAT: { label: 'Heating Melenceng', color: 'bg-rose-100 text-rose-800 border-rose-300' },

                                      KEEP: { label: 'Hold Melenceng', color: 'bg-amber-100 text-amber-800 border-amber-300' },

                                      COOL: { label: 'Cooling Melenceng', color: 'bg-sky-100 text-sky-800 border-sky-300' },

                                      SLOW_COOL: { label: 'Cooling Lambat', color: 'bg-sky-100 text-sky-800 border-sky-300' },

                                      OVER_HOLD: { label: 'Over-Hold (>8m)', color: 'bg-amber-100 text-amber-800 border-amber-300' },

                                      LATE_STOP: { label: 'Pasca-Cooling (>45m)', color: 'bg-indigo-100 text-indigo-800 border-indigo-300' },

                                      COOL_STAGNATION: { label: 'Stagnasi Cooling', color: 'bg-blue-100 text-blue-800 border-blue-300' },

                                      REHEATING: { label: 'Re-Heating (≥2x)', color: 'bg-red-100 text-red-800 border-red-300' },

                                      MID_HEAT_PAUSE: { label: 'Jeda Heating', color: 'bg-orange-100 text-orange-800 border-orange-300' },

                                      START_TEMP_HIGH: { label: 'Suhu Awal Tinggi (>60°C)', color: 'bg-amber-100 text-amber-800 border-amber-300' },

                                    };

                                    return (

                                      <div className="bg-white p-4 sm:p-5 rounded-2xl border border-slate-200 shadow-2xs space-y-3">

                                        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1">

                                          <div>

                                            <h5 className="font-bold text-slate-900 text-xs sm:text-sm flex items-center gap-1.5">

                                              <Layers size={14} className="text-indigo-600" />

                                              Audit Kesesuaian Kinerja per Master Program (Resep)

                                            </h5>

                                            <p className="text-[11px] text-slate-500">

                                              💡 <b>Klik salah satu baris program</b> untuk membuka rincian batch individual &amp; deteksi anomali resmi sistem (Anomaly Threshold Master).

                                            </p>

                                          </div>

                                          <span className="text-[10px] text-slate-400 font-medium">

                                            Evaluasi 1 Bulan Terakhir • {m.programs?.length || 0} Resep

                                          </span>

                                        </div>

                                        <div className="overflow-x-auto">

                                          <table className="w-full text-left text-xs whitespace-nowrap">

                                            <thead className="bg-slate-50 text-slate-500 font-bold border-b border-slate-200 text-[10px]">

                                              <tr>

                                                <th className="py-2.5 px-3">Nama Program</th>

                                                <th className="py-2.5 px-2 text-center">Batch</th>

                                                <th className="py-2.5 px-2 text-center">Suhu Max</th>

                                                <th className="py-2.5 px-3 text-center">Heating (Akt vs Idl)</th>

                                                <th className="py-2.5 px-3 text-center">Holding (Akt vs Idl)</th>

                                                <th className="py-2.5 px-3 text-center">Cooling (Akt vs Idl)</th>

                                                <th className="py-2.5 px-3 text-center">Total Durasi</th>

                                                <th className="py-2.5 px-3 text-center">Deviasi Suhu Puncak</th>

                                                <th className="py-2.5 px-3 text-center">Tekanan Uap</th>

                                              </tr>

                                            </thead>

                                            <tbody className="divide-y divide-slate-100">

                                              {(m.programs || []).map((prog, pidx) => {

                                                const isExpanded = expandedProgramRow[m.machine_id] === prog.program_name;

                                                const programBatches = (m.recent_batches || []).filter(

                                                  (b) => b.program_name === prog.program_name

                                                );

                                                // Gunakan jumlah anomali resmi dari DataAnomaly backend

                                                const criticalCount = prog.critical_anomaly_count ?? programBatches.filter((b) => b.is_critical_anomaly).length;

                                                const minorCount = prog.minor_anomaly_count ?? Math.max(0, (prog.anomaly_count || 0) - criticalCount);

                                                const totalAnomalies = prog.anomaly_count ?? programBatches.filter((b) => b.has_anomaly).length;

                                                const todayCount = prog.today_count ?? programBatches.filter((b) => b.is_today).length;

                                                const todayCriticalCount = prog.today_critical_count ?? programBatches.filter((b) => b.is_today && b.is_critical_anomaly).length;

                                                const currentFilter = programAnomalyFilter[m.machine_id] || 'ALL'; // 'ALL' | 'TODAY' | 'CRITICAL' | 'ANOMALIES'

                                                const displayedBatches = programBatches.filter((b) => {

                                                  if (currentFilter === 'TODAY') return b.is_today;

                                                  if (currentFilter === 'CRITICAL') return b.is_critical_anomaly;

                                                  if (currentFilter === 'ANOMALIES') return b.has_anomaly;

                                                  return true;

                                                });

                                                return (

                                                  <React.Fragment key={pidx}>

                                                    <tr

                                                      onClick={() =>

                                                        setExpandedProgramRow((prev) => ({

                                                          ...prev,

                                                          [m.machine_id]: prev[m.machine_id] === prog.program_name ? null : prog.program_name

                                                        }))

                                                      }

                                                      className={`cursor-pointer transition-colors ${

                                                        isExpanded

                                                          ? 'bg-indigo-50/70 font-semibold'

                                                          : 'hover:bg-slate-50/70'

                                                      }`}

                                                    >

                                                      <td className="py-2.5 px-3 font-bold text-slate-800">

                                                        <div className="flex items-center gap-1.5">

                                                          <span

                                                            className={`p-0.5 rounded text-slate-400 transition-transform ${

                                                              isExpanded ? 'rotate-180 text-indigo-600' : ''

                                                            }`}

                                                          >

                                                            <ChevronDown size={14} />

                                                          </span>

                                                          <span className="text-slate-900">{prog.program_name}</span>

                                                          {criticalCount > 0 ? (

                                                            <span className="px-1.5 py-0.2 rounded-full text-[9px] bg-rose-100 text-rose-700 border border-rose-300 font-bold shrink-0">

                                                              {criticalCount} Kritis

                                                            </span>

                                                          ) : minorCount > 0 ? (

                                                            <span className="px-1.5 py-0.2 rounded-full text-[9px] bg-amber-50 text-amber-700 border border-amber-200 font-medium shrink-0">

                                                              {minorCount} Catatan Deviasi

                                                            </span>

                                                          ) : (

                                                            <span className="px-1.5 py-0.2 rounded-full text-[9px] bg-emerald-50 text-emerald-700 border border-emerald-200 font-medium shrink-0">

                                                              Normal

                                                            </span>

                                                          )}

                                                          {todayCount > 0 && (

                                                            <span className="px-1.5 py-0.2 rounded text-[8.5px] bg-indigo-50 text-indigo-700 border border-indigo-200 font-bold shrink-0">

                                                              Hari Ini: {todayCount}x

                                                            </span>

                                                          )}

                                                        </div>

                                                      </td>

                                                      <td className="py-2.5 px-2 text-center font-bold text-indigo-600">

                                                        {prog.batch_count}x

                                                      </td>

                                                      <td className="py-2.5 px-2 text-center text-slate-600">

                                                        {prog.suhu_max ? `${prog.suhu_max}°C` : '-'}

                                                      </td>

                                                      <td className="py-2.5 px-3 text-center">

                                                        <span className="font-semibold text-slate-800">{prog.avg_heat || '-'}m</span>

                                                        {prog.ideal_heat && (

                                                          <span className="text-[10px] text-slate-400"> (Idl: {prog.ideal_heat}m)</span>

                                                        )}

                                                        {prog.delta_heat != null && (

                                                          <span className={`block text-[10px] font-bold ${prog.delta_heat > 10 ? 'text-rose-600' : 'text-emerald-600'}`}>

                                                            {prog.delta_heat > 0 ? `+${prog.delta_heat}m` : `${prog.delta_heat}m`}

                                                          </span>

                                                        )}

                                                      </td>

                                                      <td className="py-2.5 px-3 text-center">

                                                        <span className="font-semibold text-slate-800">{prog.avg_steady || '-'}m</span>

                                                        {prog.ideal_steady && (

                                                          <span className="text-[10px] text-slate-400"> (Idl: {prog.ideal_steady}m)</span>

                                                        )}

                                                      </td>

                                                      <td className="py-2.5 px-3 text-center">

                                                        <span className="font-semibold text-slate-800">{prog.avg_cool || '-'}m</span>

                                                        {prog.ideal_cool && (

                                                          <span className="text-[10px] text-slate-400"> (Idl: {prog.ideal_cool}m)</span>

                                                        )}

                                                        {prog.delta_cool != null && (

                                                          <span className={`block text-[10px] font-bold ${prog.delta_cool > 10 ? 'text-rose-600' : 'text-emerald-600'}`}>

                                                            {prog.delta_cool > 0 ? `+${prog.delta_cool}m` : `${prog.delta_cool}m`}

                                                          </span>

                                                        )}

                                                      </td>

                                                      <td className="py-2.5 px-3 text-center">

                                                        <span className="font-bold text-slate-900">{prog.avg_total || '-'}m</span>

                                                        {prog.ideal_total && (

                                                          <span className="text-[10px] text-slate-400"> (Idl: {prog.ideal_total}m)</span>

                                                        )}

                                                      </td>

                                                      <td className="py-2.5 px-3 text-center">

                                                        <span className="font-bold text-slate-800">{prog.avg_temp ? `${prog.avg_temp}°C` : '-'}</span>

                                                        {prog.stddev_temp != null && (

                                                          <span className="block text-[10px] text-slate-400">σ = ±{prog.stddev_temp}°C</span>

                                                        )}

                                                      </td>

                                                      <td className="py-2.5 px-3 text-center font-mono text-slate-700">

                                                        {prog.avg_pressure ? `${prog.avg_pressure} bar` : '-'}

                                                      </td>

                                                    </tr>

                                                    {/* ── Sub-Row: Drill-Down Rincian Batch Program ── */}

                                                    {isExpanded && (

                                                      <tr className="bg-slate-50/70 border-b border-indigo-100">

                                                        <td colSpan={9} className="p-2 sm:p-3">

                                                          <div className="bg-white rounded-xl border border-indigo-200/80 shadow-xs p-3 space-y-2.5">

                                                            {/* Sub-header Toolbar */}

                                                            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-2 border-b border-slate-100">

                                                              <div className="flex items-center gap-2 flex-wrap">

                                                                <span className="w-2 h-2 rounded-full bg-indigo-600 animate-pulse shrink-0" />

                                                                <h6 className="font-bold text-slate-800 text-xs sm:text-sm">

                                                                  Rincian Batch Program: <span className="text-indigo-600">{prog.program_name}</span>

                                                                </h6>

                                                                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-100 text-slate-600 font-bold">

                                                                  {programBatches.length} Batch (1 Bulan)

                                                                </span>

                                                                {todayCount > 0 && (

                                                                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-indigo-50 text-indigo-700 font-bold">

                                                                    {todayCount} Batch Hari Ini ({todayCriticalCount > 0 ? `${todayCriticalCount} Kritis` : 'Semua Normal'})

                                                                  </span>

                                                                )}

                                                                <span className="text-[10.5px]">

                                                                  {criticalCount > 0 ? (

                                                                    <span className="text-rose-600 font-bold">

                                                                      ⚠️ {criticalCount} batch kritis ({minorCount} catatan deviasi wajar)

                                                                    </span>

                                                                  ) : minorCount > 0 ? (

                                                                    <span className="text-amber-600 font-medium">

                                                                      ℹ️ {minorCount} batch memiliki catatan deviasi operasional wajar (cooling lambat/suhu tipis)

                                                                    </span>

                                                                  ) : (

                                                                    <span className="text-emerald-600 font-semibold">

                                                                      ✓ Seluruh batch berjalan presisi sesuai standar resep

                                                                    </span>

                                                                  )}

                                                                </span>

                                                              </div>

                                                              {/* Toggle Filter Anomali */}

                                                              <div className="flex items-center gap-1.5 text-xs flex-wrap">

                                                                <button

                                                                  type="button"

                                                                  onClick={(e) => {

                                                                    e.stopPropagation();

                                                                    setProgramAnomalyFilter((prev) => ({ ...prev, [m.machine_id]: 'ALL' }));

                                                                  }}

                                                                  className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition-all cursor-pointer ${

                                                                    currentFilter === 'ALL'

                                                                      ? 'bg-slate-800 text-white shadow-2xs'

                                                                      : 'bg-slate-100 text-slate-600 hover:bg-slate-200'

                                                                  }`}

                                                                >

                                                                  Semua ({programBatches.length})

                                                                </button>

                                                                {todayCount > 0 && (

                                                                  <button

                                                                    type="button"

                                                                    onClick={(e) => {

                                                                      e.stopPropagation();

                                                                      setProgramAnomalyFilter((prev) => ({ ...prev, [m.machine_id]: 'TODAY' }));

                                                                    }}

                                                                    className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition-all cursor-pointer ${

                                                                      currentFilter === 'TODAY'

                                                                        ? 'bg-indigo-600 text-white shadow-2xs'

                                                                        : 'bg-indigo-50 text-indigo-700 hover:bg-indigo-100 border border-indigo-200'

                                                                    }`}

                                                                  >

                                                                    Hari Ini ({todayCount})

                                                                  </button>

                                                                )}

                                                                {criticalCount > 0 && (

                                                                  <button

                                                                    type="button"

                                                                    onClick={(e) => {

                                                                      e.stopPropagation();

                                                                      setProgramAnomalyFilter((prev) => ({ ...prev, [m.machine_id]: 'CRITICAL' }));

                                                                    }}

                                                                    className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition-all cursor-pointer flex items-center gap-1 ${

                                                                      currentFilter === 'CRITICAL'

                                                                        ? 'bg-rose-600 text-white shadow-2xs'

                                                                        : 'bg-rose-50 text-rose-700 hover:bg-rose-100 border border-rose-200'

                                                                    }`}

                                                                  >

                                                                    <AlertTriangle size={12} />

                                                                    <span>Hanya Kritis ({criticalCount})</span>

                                                                  </button>

                                                                )}

                                                                {totalAnomalies > 0 && (

                                                                  <button

                                                                    type="button"

                                                                    onClick={(e) => {

                                                                      e.stopPropagation();

                                                                      setProgramAnomalyFilter((prev) => ({ ...prev, [m.machine_id]: 'ANOMALIES' }));

                                                                    }}

                                                                    className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition-all cursor-pointer ${

                                                                      currentFilter === 'ANOMALIES'

                                                                        ? 'bg-amber-600 text-white shadow-2xs'

                                                                        : 'bg-amber-50 text-amber-700 hover:bg-amber-100 border border-amber-200'

                                                                    }`}

                                                                  >

                                                                    <span>Semua Catatan ({totalAnomalies})</span>

                                                                  </button>

                                                                )}

                                                              </div>

                                                            </div>

                                                            {/* Tabel Batch */}

                                                            {displayedBatches.length === 0 ? (

                                                              <div className="py-6 text-center text-xs text-slate-500">

                                                                {currentFilter === 'CRITICAL'

                                                                  ? 'Tidak ada batch anomali kritis pada program ini!'

                                                                  : currentFilter === 'TODAY'

                                                                  ? 'Tidak ada batch untuk program ini pada hari acuan.'

                                                                  : currentFilter === 'ANOMALIES'

                                                                  ? 'Tidak ada catatan anomali terdaftar pada program ini.'

                                                                  : 'Tidak ada data batch untuk program ini pada rentang evaluasi.'}

                                                              </div>

                                                            ) : (

                                                              <div className="overflow-x-auto max-h-[340px] overflow-y-auto rounded-lg border border-slate-200/80">

                                                                <table className="w-full text-left text-[11px] whitespace-nowrap">

                                                                  <thead className="bg-slate-100 text-slate-600 font-bold sticky top-0 z-10 border-b border-slate-200 text-[10px]">

                                                                    <tr>

                                                                      <th className="py-2 px-2.5">No. Batch</th>

                                                                      <th className="py-2 px-2">Tanggal &amp; Waktu</th>

                                                                      <th className="py-2 px-2">No. Order</th>

                                                                      <th className="py-2 px-2.5 text-center">Suhu Max (°C)</th>

                                                                      <th className="py-2 px-2.5 text-center">Heating</th>

                                                                      <th className="py-2 px-2 text-center">Keep</th>

                                                                      <th className="py-2 px-2.5 text-center">Cooling</th>

                                                                      <th className="py-2 px-2 text-center">Total Durasi</th>

                                                                      <th className="py-2 px-2.5 text-center">Tekanan Uap</th>

                                                                      <th className="py-2 px-3 text-center">Diagnosa Anomali</th>

                                                                      <th className="py-2 px-2 text-center">Aksi</th>

                                                                    </tr>

                                                                  </thead>

                                                                  <tbody className="divide-y divide-slate-100 font-mono">

                                                                    {displayedBatches.map((b) => {

                                                                      const hasAnomaly = Boolean(b.has_anomaly && b.anomaly);

                                                                      const anomFlags = hasAnomaly ? (b.anomaly.flags || []) : [];

                                                                      const hasSuhuAnom = anomFlags.includes('SUHU') || anomFlags.includes('SUHU_HARD');

                                                                      const hasHeatAnom = anomFlags.includes('HEAT') || anomFlags.includes('REHEATING') || anomFlags.includes('MID_HEAT_PAUSE');

                                                                      const hasKeepAnom = anomFlags.includes('KEEP') || anomFlags.includes('OVER_HOLD');

                                                                      const hasCoolAnom = anomFlags.includes('COOL') || anomFlags.includes('SLOW_COOL') || anomFlags.includes('COOL_STAGNATION');

                                                                      const hasLateStop = anomFlags.includes('LATE_STOP');

                                                                      const targetTemp = b.target_temp || prog.suhu_max;

                                                                      const tempDiff = (targetTemp && b.max_temp) ? Math.round((b.max_temp - targetTemp) * 10) / 10 : null;

                                                                      const iHeat = b.ideal_heat || prog.ideal_heat;

                                                                      const dHeat = b.delta_heat != null ? b.delta_heat : (iHeat && b.heat_mins ? b.heat_mins - iHeat : null);

                                                                      const iCool = b.ideal_cool || prog.ideal_cool;

                                                                      const dCool = b.delta_cool != null ? b.delta_cool : (iCool && b.cool_mins ? b.cool_mins - iCool : null);

                                                                      const isSteamDrop = b.avg_pressure != null && b.avg_pressure < 3.8;

                                                                      return (

                                                                        <tr

                                                                          key={b.id}

                                                                          className={`hover:bg-slate-50 transition-colors ${

                                                                            b.is_critical_anomaly

                                                                              ? 'bg-rose-50/25'

                                                                              : b.is_minor_anomaly

                                                                              ? 'bg-amber-50/15'

                                                                              : ''

                                                                          }`}

                                                                        >

                                                                          {/* No. Batch */}

                                                                          <td className="py-2 px-2.5 font-bold text-slate-800">

                                                                            <span className="font-mono">#{b.batch_number}</span>

                                                                            {b.is_today && (

                                                                              <span className="ml-1.5 px-1 py-0.2 rounded text-[8px] bg-indigo-100 text-indigo-700 font-bold uppercase tracking-wider">

                                                                                Hari Ini

                                                                              </span>

                                                                            )}

                                                                          </td>

                                                                          {/* Tanggal & Jam */}

                                                                          <td className="py-2 px-2 text-slate-500 font-sans text-[10.5px]">

                                                                            {b.date_str} {b.time_str && <span className="text-slate-400">({b.time_str})</span>}

                                                                          </td>

                                                                          {/* No. Order */}

                                                                          <td className="py-2 px-2 text-slate-600 font-sans text-[10.5px]">

                                                                            {b.order_no || '-'}

                                                                          </td>

                                                                          {/* Suhu Max */}

                                                                          <td className="py-2 px-2.5 text-center">

                                                                            <span className={`font-bold ${hasSuhuAnom ? 'text-rose-700 bg-rose-50 px-1.5 py-0.5 rounded font-bold' : 'text-slate-800'}`}>

                                                                              {b.max_temp != null ? `${b.max_temp}°C` : '-'}

                                                                            </span>

                                                                            {tempDiff != null && (

                                                                              <span className={`block text-[9.5px] font-semibold ${hasSuhuAnom ? 'text-rose-600 font-bold' : 'text-slate-400'}`}>

                                                                                {tempDiff > 0 ? `+${tempDiff}°C` : `${tempDiff}°C`} vs resep

                                                                              </span>

                                                                            )}

                                                                          </td>

                                                                          {/* Heating */}

                                                                          <td className="py-2 px-2.5 text-center">

                                                                            <span className={`font-bold ${hasHeatAnom ? 'text-rose-700 bg-rose-50 px-1.5 py-0.5 rounded' : 'text-slate-800'}`}>

                                                                              {b.heat_mins != null ? `${b.heat_mins}m` : '-'}

                                                                            </span>

                                                                            {dHeat != null && (

                                                                              <span className={`block text-[9.5px] font-semibold ${hasHeatAnom ? 'text-rose-600 font-bold' : 'text-slate-400'}`}>

                                                                                {dHeat > 0 ? `+${Math.round(dHeat)}m` : `${Math.round(dHeat)}m`}

                                                                              </span>

                                                                            )}

                                                                          </td>

                                                                          {/* Keep */}

                                                                          <td className="py-2 px-2 text-center text-slate-600">

                                                                            <span className={hasKeepAnom ? 'text-amber-700 font-bold bg-amber-50 px-1 rounded' : ''}>

                                                                              {b.steady_mins != null ? `${b.steady_mins}m` : '-'}

                                                                            </span>

                                                                          </td>

                                                                          {/* Cooling */}

                                                                          <td className="py-2 px-2.5 text-center">

                                                                            <span className={`font-bold ${hasCoolAnom ? 'text-sky-700 bg-sky-50 px-1.5 py-0.5 rounded' : 'text-slate-800'}`}>

                                                                              {b.cool_mins != null ? `${b.cool_mins}m` : '-'}

                                                                            </span>

                                                                            {dCool != null && (

                                                                              <span className={`block text-[9.5px] font-semibold ${hasCoolAnom ? 'text-sky-600 font-bold' : 'text-slate-400'}`}>

                                                                                {dCool > 0 ? `+${Math.round(dCool)}m` : `${Math.round(dCool)}m`}

                                                                              </span>

                                                                            )}

                                                                          </td>

                                                                          {/* Total Durasi */}

                                                                          <td className="py-2 px-2 text-center font-bold text-slate-900">

                                                                            <span className={hasLateStop ? 'text-indigo-700 bg-indigo-50 px-1 rounded' : ''}>

                                                                              {b.total_mins != null ? `${b.total_mins}m` : '-'}

                                                                            </span>

                                                                          </td>

                                                                          {/* Tekanan Uap */}

                                                                          <td className="py-2 px-2.5 text-center">

                                                                            <span className={`font-bold ${isSteamDrop ? 'text-purple-700 bg-purple-50 px-1.5 py-0.5 rounded' : 'text-slate-700'}`}>

                                                                              {b.avg_pressure != null ? `${b.avg_pressure} bar` : '-'}

                                                                            </span>

                                                                            {isSteamDrop && (

                                                                              <span className="block text-[9px] text-purple-600 font-bold">&lt; 3.8 bar</span>

                                                                            )}

                                                                          </td>

                                                                          {/* Diagnosa Anomali Resmi Sistem */}

                                                                          <td className="py-2 px-3 text-center font-sans">

                                                                            {b.is_critical_anomaly ? (

                                                                              <div className="flex flex-wrap items-center justify-center gap-1">

                                                                                <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-rose-600 text-white shrink-0">

                                                                                  KRITIS

                                                                                </span>

                                                                                {anomFlags.map((flag, fidx) => {

                                                                                  const meta = ANOMALY_FLAG_MAP[flag] || { label: flag, color: 'bg-slate-100 text-slate-800 border-slate-300' };

                                                                                  return (

                                                                                    <span

                                                                                      key={fidx}

                                                                                      className={`px-1.5 py-0.5 rounded text-[9.5px] font-bold border ${meta.color}`}

                                                                                    >

                                                                                      {meta.label}

                                                                                    </span>

                                                                                  );

                                                                                })}

                                                                              </div>

                                                                            ) : b.is_minor_anomaly ? (

                                                                              <div className="flex flex-wrap items-center justify-center gap-1">

                                                                                <span className="px-1.5 py-0.5 rounded text-[9px] font-semibold bg-amber-100 text-amber-800 border border-amber-200 shrink-0">

                                                                                  DEV. OPERASIONAL

                                                                                </span>

                                                                                {anomFlags.map((flag, fidx) => {

                                                                                  const meta = ANOMALY_FLAG_MAP[flag] || { label: flag, color: 'bg-slate-100 text-slate-800 border-slate-300' };

                                                                                  return (

                                                                                    <span

                                                                                      key={fidx}

                                                                                      className="px-1.5 py-0.5 rounded text-[9.5px] font-medium bg-slate-100 text-slate-600 border border-slate-200"

                                                                                    >

                                                                                      {meta.label}

                                                                                    </span>

                                                                                  );

                                                                                })}

                                                                              </div>

                                                                            ) : (

                                                                              <span className="inline-flex items-center gap-1 text-[10px] text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full font-semibold border border-emerald-200">

                                                                                <CheckCircle2 size={10} />

                                                                                <span>Sesuai Standar</span>

                                                                              </span>

                                                                            )}

                                                                          </td>

                                                                          {/* Aksi Audit */}

                                                                          <td className="py-2 px-2 text-center font-sans">

                                                                            <a

                                                                              href={`/history/report/${b.id}`}

                                                                              target="_blank"

                                                                              rel="noreferrer"

                                                                              className="inline-flex items-center gap-0.5 px-2 py-1 rounded bg-indigo-50 text-indigo-700 hover:bg-indigo-100 hover:text-indigo-900 font-bold text-[10px] transition-colors"

                                                                              title="Buka laporan batch lengkap di tab baru"

                                                                            >

                                                                              <span>Audit</span>

                                                                              <ExternalLink size={10} />

                                                                            </a>

                                                                          </td>

                                                                        </tr>

                                                                      );

                                                                    })}

                                                                  </tbody>

                                                                </table>

                                                              </div>

                                                            )}

                                                          </div>

                                                        </td>

                                                      </tr>

                                                    )}

                                                  </React.Fragment>

                                                );

                                              })}

                                            </tbody>

                                          </table>

                                        </div>

                                      </div>

                                    );

                                  })()}

                                  {/* ── Sub-Panel 2: Diagnostic Charts ── */}

                                  {drawerSubTab === 'charts' && (() => {

                                    // Hanya program yang valid (memiliki master program dari dyeingidentities)

                                    const validPrograms = (m.programs || []).filter(

                                      (p) => p.program_name && p.program_name !== 'Tanpa Master Program' && p.program_name !== 'Tanpa Program'

                                    );

                                    if (validPrograms.length === 0) {

                                      return (

                                        <div className="bg-white p-8 rounded-2xl border border-slate-200 shadow-2xs text-center space-y-3">

                                          <div className="w-12 h-12 rounded-2xl bg-amber-50 text-amber-600 border border-amber-200 flex items-center justify-center mx-auto">

                                            <AlertTriangle size={24} />

                                          </div>

                                          <h5 className="font-bold text-slate-800 text-sm">Grafik Diagnostik Kinerja Termal Tidak Ditampilkan</h5>

                                          <p className="text-xs text-slate-500 max-w-md mx-auto">

                                            Mesin <b>{m.machine_name}</b> belum memiliki batch dengan master resep (Dyeing Identities) terdaftar pada 1 bulan terakhir. Grafik komparasi historis hanya dievaluasi pada proses dengan master resep standar.

                                          </p>

                                        </div>

                                      );

                                    }

                                    const activeProgName = selectedChartProgram[m.machine_id] || validPrograms[0].program_name;

                                    const activeProgInfo = validPrograms.find((p) => p.program_name === activeProgName) || validPrograms[0];

                                    // Batch yang difilter khusus untuk program ini dalam 1 bulan terakhir (semuanya), urutan kronologis

                                    const progBatches = (m.recent_batches || [])

                                      .filter((b) => activeProgName === 'ALL' || b.program_name === activeProgName)

                                      .slice()

                                      .reverse();

                                    // Hitung rata-rata histori untuk garis putus-putus

                                    const validHeats = progBatches.map(b => b.heat_mins).filter(v => v > 0);

                                    const validKeeps = progBatches.map(b => b.steady_mins).filter(v => v > 0);

                                    const validCools = progBatches.map(b => b.cool_mins).filter(v => v > 0);

                                    const histAvgHeat = activeProgInfo?.avg_heat ?? (validHeats.length ? (validHeats.reduce((s, b) => s + b, 0) / validHeats.length).toFixed(1) : null);

                                    const histAvgKeep = activeProgInfo?.avg_steady ?? (validKeeps.length ? (validKeeps.reduce((s, b) => s + b, 0) / validKeeps.length).toFixed(1) : null);

                                    const histAvgCool = activeProgInfo?.avg_cool ?? (validCools.length ? (validCools.reduce((s, b) => s + b, 0) / validCools.length).toFixed(1) : null);

                                    // Batch terpilih atau batch hari ini / batch terbaru untuk komparasi tabel

                                    const targetBatchId = selectedChartBatch[m.machine_id];

                                    let activeBatch = null;

                                    if (targetBatchId) {

                                      activeBatch = progBatches.find((b) => b.id === targetBatchId);

                                    }

                                    if (!activeBatch) {

                                      const selDayMonth = selectedDate ? selectedDate.split('-').slice(1).reverse().join('/') : null;

                                      const todayBatch = selDayMonth ? progBatches.slice().reverse().find((b) => b.date_str === selDayMonth) : null;

                                      activeBatch = todayBatch || (progBatches.length > 0 ? progBatches[progBatches.length - 1] : null);

                                    }

                                    const progChartSeries = progBatches.map((b) => ({

                                      id: b.id,

                                      label: `#${b.batch_number}`,

                                      date: b.date_str,

                                      heat_mins: b.heat_mins || 0,

                                      steady_mins: b.steady_mins || 0,

                                      cool_mins: b.cool_mins || 0,

                                      avg_pressure: b.avg_pressure

                                    }));

                                    const handleOpenBatch = (batchId) => {

                                      if (!batchId) return;

                                      setSelectedChartBatch((prev) => ({ ...prev, [m.machine_id]: batchId }));

                                      window.open(`/history/report/${batchId}`, '_blank');

                                    };

                                    // Data untuk scatter korelasi

                                    const rawCorr = m.correlation_points || [];

                                    const filteredCorr = rawCorr.filter((p) => activeProgName === 'ALL' || p.program_name === activeProgName);

                                    // Hitung kuadran distribusi untuk scatter

                                    const qStats = {

                                      optimal: filteredCorr.filter((p) => p.quadrant === 'OPTIMAL').length,

                                      mech: filteredCorr.filter((p) => p.quadrant === 'MECHANICAL_DEGRADATION').length,

                                      boiler: filteredCorr.filter((p) => p.quadrant === 'BOILER_DROP').length,

                                      total: Math.max(1, filteredCorr.length)

                                    };

                                    return (

                                      <div className="bg-white p-4 sm:p-5 rounded-2xl border border-slate-200 shadow-2xs space-y-4">

                                        {/* ── Toolbar Kontrol Atas: Mode Visualisasi & Dropdown Program ── */}

                                        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3 pb-3 border-b border-slate-100">

                                          <div className="flex items-center gap-2">

                                            {/* Mode Switcher */}

                                            <div className="inline-flex rounded-xl bg-slate-100 p-1 text-xs font-bold">

                                              <button

                                                type="button"

                                                onClick={() => setActiveChartMode('durations')}

                                                className={`px-3 py-1.5 rounded-lg transition-all cursor-pointer ${

                                                  activeChartMode === 'durations'

                                                    ? 'bg-white text-indigo-700 shadow-2xs'

                                                    : 'text-slate-600 hover:text-slate-900'

                                                }`}

                                              >

                                                1. Riwayat Durasi (Heating, Keep, Cooling) vs Uap

                                              </button>

                                              <button

                                                type="button"

                                                onClick={() => setActiveChartMode('correlation')}

                                                className={`px-3 py-1.5 rounded-lg transition-all cursor-pointer ${

                                                  activeChartMode === 'correlation'

                                                    ? 'bg-white text-indigo-700 shadow-2xs'

                                                    : 'text-slate-600 hover:text-slate-900'

                                                }`}

                                              >

                                                2. Korelasi Regresi vs Tekanan Uap

                                              </button>

                                            </div>

                                          </div>

                                          {/* Dropdown Pemilih Program Resep */}

                                          <div className="flex items-center gap-2 flex-wrap">

                                            <div className="flex items-center gap-1.5 text-xs bg-slate-50 px-3 py-1.5 rounded-xl border border-slate-200">

                                              <Filter size={13} className="text-slate-400" />

                                              <span className="font-bold text-slate-500">Pilih Program:</span>

                                              <select

                                                value={activeProgName}

                                                onChange={(e) => {

                                                  setSelectedChartProgram((prev) => ({ ...prev, [m.machine_id]: e.target.value }));

                                                  setSelectedChartBatch((prev) => ({ ...prev, [m.machine_id]: null }));

                                                }}

                                                className="bg-transparent font-bold text-indigo-700 outline-none cursor-pointer text-xs"

                                              >

                                                {activeChartMode === 'correlation' && (

                                                  <option value="ALL">Semua Program ({m.recent_batches.length} Batch 1 Bln)</option>

                                                )}

                                                {validPrograms.map((prog) => (

                                                  <option key={prog.program_name} value={prog.program_name}>

                                                    {prog.program_name} ({prog.batch_count} Batch)

                                                  </option>

                                                ))}

                                              </select>

                                            </div>

                                            {/* Toggle Fase Heating vs Cooling khusus untuk Korelasi Regresi */}

                                            {activeChartMode === 'correlation' && (

                                              <div className="flex bg-slate-200/80 p-0.5 rounded-xl text-xs font-bold text-slate-600">

                                                <button

                                                  type="button"

                                                  onClick={() => setScatterPhaseMode('heating')}

                                                  className={`px-3 py-1 rounded-lg transition-all cursor-pointer ${

                                                    scatterPhaseMode === 'heating'

                                                      ? 'bg-white text-rose-600 shadow-2xs'

                                                      : 'hover:text-slate-900'

                                                  }`}

                                                >

                                                  Fase Heating

                                                </button>

                                                <button

                                                  type="button"

                                                  onClick={() => setScatterPhaseMode('cooling')}

                                                  className={`px-3 py-1 rounded-lg transition-all cursor-pointer ${

                                                    scatterPhaseMode === 'cooling'

                                                      ? 'bg-white text-sky-600 shadow-2xs'

                                                      : 'hover:text-slate-900'

                                                  }`}

                                                >

                                                  Fase Cooling

                                                </button>

                                              </div>

                                            )}

                                          </div>

                                        </div>

                                        {/* ── MODE 1: RIWAYAT DURASI HEATING, KEEP, COOLING SLIM BARS + PRESSURE ── */}

                                        {activeChartMode === 'durations' && (

                                          <div className="space-y-3">

                                            {/* Header Info */}

                                            <div className="flex flex-wrap items-center justify-between gap-2">

                                              <div>

                                                <h3 className="text-xs sm:text-sm font-bold text-slate-900">

                                                  Grafik Riwayat Durasi Heating &amp; Cooling vs Avg Pressure (Program: {activeProgName})

                                                </h3>

                                                <p className="text-[11px] text-slate-500">

                                                  Menampilkan {progChartSeries.length} batch terakhir di mesin <b>{m.machine_name}</b> dalam 1 bulan terakhir &mdash; garis putus-putus menunjukkan rata-rata histori

                                                </p>

                                              </div>

                                              <div className="flex flex-wrap items-center gap-1.5 text-[10.5px]">

                                                <span className="px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-200 font-bold flex items-center gap-1">

                                                  <span>💡 Klik titik / bar untuk buka Laporan Batch</span>

                                                </span>

                                                {histAvgHeat != null && (

                                                  <span className="px-2 py-0.5 rounded bg-rose-50 text-rose-800 border border-rose-200 font-semibold">

                                                    Avg Heat: <b>{histAvgHeat} mnt</b>

                                                  </span>

                                                )}

                                                {histAvgKeep != null && (

                                                  <span className="px-2 py-0.5 rounded bg-amber-50 text-amber-800 border border-amber-200 font-semibold">

                                                    Avg Keep: <b>{histAvgKeep} mnt</b>

                                                  </span>

                                                )}

                                                {histAvgCool != null && (

                                                  <span className="px-2 py-0.5 rounded bg-sky-50 text-sky-800 border border-sky-200 font-semibold">

                                                    Avg Cool: <b>{histAvgCool} mnt</b>

                                                  </span>

                                                )}

                                              </div>

                                            </div>

                                            {/* Container Berdampingan: Tabel Komparasi Resep (Kiri) & Grafik Composed (Kanan) */}

                                            <div className="flex flex-col lg:flex-row items-stretch gap-3 mt-2">

                                              {/* ── SISI KIRI: TABEL PARAMETER (Batch Ini vs Avg Histori vs Standar Resep) ── */}

                                              <div className="w-full lg:w-[325px] xl:w-[345px] shrink-0 bg-slate-50/90 rounded-xl border border-slate-200/90 p-2.5 sm:p-3 flex flex-col justify-between">

                                                <div>

                                                  {/* Header Tabel Komparasi */}

                                                  <div className="flex items-center justify-between pb-1.5 border-b border-slate-200 mb-2">

                                                    <div className="flex items-center gap-1.5 min-w-0">

                                                      <span className="w-2 h-2 rounded-full bg-indigo-600 animate-pulse shrink-0" />

                                                      <span className="text-[11px] font-bold text-slate-800 truncate">

                                                        {activeBatch ? `Batch #${activeBatch.batch_number}` : 'Batch Ini'}

                                                      </span>

                                                      {activeBatch?.date_str && (

                                                        <span className="text-[10px] text-slate-400 font-mono">({activeBatch.date_str})</span>

                                                      )}

                                                    </div>

                                                    {activeBatch?.id && (

                                                      <a

                                                        href={`/history/report/${activeBatch.id}`}

                                                        target="_blank"

                                                        rel="noreferrer"

                                                        className="inline-flex items-center gap-1 text-[10px] text-indigo-700 bg-indigo-50 hover:bg-indigo-100 border border-indigo-200 font-bold px-2 py-0.5 rounded shadow-2xs transition-colors shrink-0"

                                                        title="Buka laporan batch lengkap di tab baru"

                                                      >

                                                        <span>Laporan Batch</span>

                                                        <ExternalLink size={10} />

                                                      </a>

                                                    )}

                                                  </div>

                                                  {/* Tabel Parameter vs Batch Ini vs Rata-rata Histori vs Standar Resep */}

                                                  <div className="overflow-x-auto">

                                                    <table className="w-full text-left text-[10.5px]">

                                                      <thead>

                                                        <tr className="border-b border-slate-200 text-[9px] text-slate-400 uppercase font-semibold">

                                                          <th className="py-1 px-1">Parameter</th>

                                                          <th className="py-1 px-1 text-center bg-indigo-50/70 text-indigo-900 rounded font-bold">Batch Ini</th>

                                                          <th className="py-1 px-1 text-center text-slate-600 font-medium">Rata-rata Histori</th>

                                                          <th className="py-1 px-1 text-center text-emerald-700 font-medium">Standar Resep</th>

                                                        </tr>

                                                      </thead>

                                                      <tbody className="divide-y divide-slate-100 font-mono">

                                                        {/* 1. Heating */}

                                                        <tr>

                                                          <td className="py-1.5 px-1 font-sans font-semibold text-rose-700 flex items-center gap-1">

                                                            <span className="w-1.5 h-1.5 rounded-full bg-rose-500 shrink-0" />

                                                            Heating

                                                          </td>

                                                          <td className="py-1.5 px-1 text-center font-bold text-slate-800 bg-indigo-50/30">

                                                            {activeBatch?.heat_mins != null ? `${activeBatch.heat_mins} m` : '-'}

                                                          </td>

                                                          <td className="py-1.5 px-1 text-center text-slate-600">

                                                            {histAvgHeat != null ? `${histAvgHeat} m` : '-'}

                                                          </td>

                                                          <td className="py-1.5 px-1 text-center text-emerald-700 font-semibold">

                                                            {activeProgInfo?.ideal_heat != null ? `${activeProgInfo.ideal_heat} m` : '-'}

                                                          </td>

                                                        </tr>

                                                        {/* 2. Keep */}

                                                        <tr>

                                                          <td className="py-1.5 px-1 font-sans font-semibold text-amber-700 flex items-center gap-1">

                                                            <span className="w-1.5 h-1.5 rounded-full bg-amber-500 shrink-0" />

                                                            Keep

                                                          </td>

                                                          <td className="py-1.5 px-1 text-center font-bold text-slate-800 bg-indigo-50/30">

                                                            {activeBatch?.steady_mins != null ? `${activeBatch.steady_mins} m` : '-'}

                                                          </td>

                                                          <td className="py-1.5 px-1 text-center text-slate-600">

                                                            {histAvgKeep != null ? `${histAvgKeep} m` : '-'}

                                                          </td>

                                                          <td className="py-1.5 px-1 text-center text-emerald-700 font-semibold">

                                                            {activeProgInfo?.ideal_steady != null ? `${activeProgInfo.ideal_steady} m` : '-'}

                                                          </td>

                                                        </tr>

                                                        {/* 3. Cooling */}

                                                        <tr>

                                                          <td className="py-1.5 px-1 font-sans font-semibold text-sky-700 flex items-center gap-1">

                                                            <span className="w-1.5 h-1.5 rounded-full bg-sky-500 shrink-0" />

                                                            Cooling

                                                          </td>

                                                          <td className="py-1.5 px-1 text-center font-bold text-slate-800 bg-indigo-50/30">

                                                            {activeBatch?.cool_mins != null ? `${activeBatch.cool_mins} m` : '-'}

                                                          </td>

                                                          <td className="py-1.5 px-1 text-center text-slate-600">

                                                            {histAvgCool != null ? `${histAvgCool} m` : '-'}

                                                          </td>

                                                          <td className="py-1.5 px-1 text-center text-emerald-700 font-semibold">

                                                            {activeProgInfo?.ideal_cool != null ? `${activeProgInfo.ideal_cool} m` : '-'}

                                                          </td>

                                                        </tr>

                                                        {/* 4. Total Proses */}

                                                        <tr className="bg-slate-100/50">

                                                          <td className="py-1.5 px-1 font-sans font-bold text-slate-800">Total Proses</td>

                                                          <td className="py-1.5 px-1 text-center font-bold text-slate-900 bg-indigo-50/60">

                                                            {activeBatch?.total_mins != null

                                                              ? `${activeBatch.total_mins} m`

                                                              : (activeBatch ? `${(activeBatch.heat_mins || 0) + (activeBatch.steady_mins || 0) + (activeBatch.cool_mins || 0)} m` : '-')}

                                                          </td>

                                                          <td className="py-1.5 px-1 text-center text-slate-700 font-medium">

                                                            {activeProgInfo?.avg_total != null ? `${activeProgInfo.avg_total} m` : '-'}

                                                          </td>

                                                          <td className="py-1.5 px-1 text-center text-emerald-700 font-bold">

                                                            {activeProgInfo?.ideal_total != null ? `${activeProgInfo.ideal_total} m` : '-'}

                                                          </td>

                                                        </tr>

                                                        {/* 5. Tekanan Uap */}

                                                        <tr>

                                                          <td className="py-1.5 px-1 font-sans font-semibold text-purple-700 flex items-center gap-1">

                                                            <span className="w-1.5 h-1.5 rounded-full bg-purple-500 shrink-0" />

                                                            Tekanan Uap

                                                          </td>

                                                          <td className="py-1.5 px-1 text-center font-bold text-purple-900 bg-indigo-50/30">

                                                            {activeBatch?.avg_pressure != null ? `${activeBatch.avg_pressure} bar` : '-'}

                                                          </td>

                                                          <td className="py-1.5 px-1 text-center text-slate-600">

                                                            {activeProgInfo?.avg_pressure != null ? `${activeProgInfo.avg_pressure} bar` : '-'}

                                                          </td>

                                                          <td className="py-1.5 px-1 text-center text-slate-500 text-[9.5px]">

                                                            &ge; 3.8 bar

                                                          </td>

                                                        </tr>

                                                        {/* 6. Suhu Maksimal */}

                                                        <tr>

                                                          <td className="py-1.5 px-1 font-sans font-medium text-slate-600">Suhu Maks</td>

                                                          <td className="py-1.5 px-1 text-center font-bold text-slate-800 bg-indigo-50/30">

                                                            {activeBatch?.max_temp != null ? `${activeBatch.max_temp}°C` : '-'}

                                                          </td>

                                                          <td className="py-1.5 px-1 text-center text-slate-600">

                                                            {activeProgInfo?.avg_temp != null ? `${activeProgInfo.avg_temp}°C` : '-'}

                                                          </td>

                                                          <td className="py-1.5 px-1 text-center text-slate-500">

                                                            {activeProgInfo?.suhu_max != null ? `${activeProgInfo.suhu_max}°C` : '-'}

                                                          </td>

                                                        </tr>

                                                      </tbody>

                                                    </table>

                                                  </div>

                                                </div>

                                                {/* Petunjuk Interaktif di Footer Tabel */}

                                                <div className="pt-2 border-t border-slate-200 text-[9.5px] text-slate-400 flex items-center gap-1 mt-1">

                                                  <span>💡</span>

                                                  <span>Klik titik / bar di grafik untuk membuka Laporan Batch & komparasi detail.</span>

                                                </div>

                                              </div>

                                              {/* ── SISI KANAN: GRAFIK COMPOSED ── */}

                                              <div className="flex-1 min-w-0 h-[280px] sm:h-[320px] w-full">

                                                <ResponsiveContainer width="100%" height="100%">

                                                  <ComposedChart

                                                    data={progChartSeries}

                                                    margin={{ top: 18, right: 12, left: -15, bottom: 5 }}

                                                    onClick={(e) => {

                                                      if (e && e.activePayload && e.activePayload.length > 0) {

                                                        const payload = e.activePayload[0].payload;

                                                        if (payload && payload.id) {

                                                          handleOpenBatch(payload.id);

                                                        }

                                                      }

                                                    }}

                                                  >

                                                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />

                                                    <XAxis

                                                      dataKey="label"

                                                      interval="preserveStartEnd"

                                                      tick={{ fontSize: 9.5, fill: '#475569' }}

                                                      axisLine={false}

                                                      tickLine={false}

                                                    />

                                                    <YAxis

                                                      yAxisId="left"

                                                      tick={{ fontSize: 10, fill: '#475569' }}

                                                      axisLine={false}

                                                      tickLine={false}

                                                      label={{ value: 'Menit', angle: -90, position: 'insideLeft', offset: 8, style: { fontSize: 10, fill: '#64748b' } }}

                                                    />

                                                    <YAxis

                                                      yAxisId="right"

                                                      orientation="right"

                                                      domain={[0, 6]}

                                                      tick={{ fontSize: 10, fill: '#7c3aed' }}

                                                      axisLine={false}

                                                      tickLine={false}

                                                      label={{ value: 'Bar', angle: 90, position: 'insideRight', offset: 0, style: { fontSize: 10, fill: '#7c3aed' } }}

                                                    />

                                                    <RechartsTooltip

                                                      contentStyle={{ borderRadius: '6px', fontSize: '11px', boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1)' }}

                                                      formatter={(val, name) => {

                                                        const suffix = name.includes('Pressure') ? ' bar' : ' mnt';

                                                        return [`${val}${suffix}`, name];

                                                      }}

                                                      labelFormatter={(lbl, payload) => {

                                                        const item = payload?.[0]?.payload;

                                                        return item ? `${lbl} (${item.date}) • Klik untuk buka laporan batch` : lbl;

                                                      }}

                                                    />

                                                    <Legend wrapperStyle={{ fontSize: '11px', paddingTop: '6px' }} iconType="rect" iconSize={12} />

                                                    {/* Garis Putus-Putus Rata-rata Histori */}

                                                    {histAvgHeat != null && (

                                                      <ReferenceLine

                                                        yAxisId="left"

                                                        y={Number(histAvgHeat)}

                                                        stroke="#e11d48"

                                                        strokeDasharray="4 3"

                                                        strokeWidth={1.5}

                                                      />

                                                    )}

                                                    {histAvgKeep != null && (

                                                      <ReferenceLine

                                                        yAxisId="left"

                                                        y={Number(histAvgKeep)}

                                                        stroke="#d97706"

                                                        strokeDasharray="4 3"

                                                        strokeWidth={1.5}

                                                      />

                                                    )}

                                                    {histAvgCool != null && (

                                                      <ReferenceLine

                                                        yAxisId="left"

                                                        y={Number(histAvgCool)}

                                                        stroke="#0284c7"

                                                        strokeDasharray="4 3"

                                                        strokeWidth={1.5}

                                                      />

                                                    )}

                                                    <ReferenceLine yAxisId="right" y={3.8} stroke="#10b981" strokeDasharray="4 4" />

                                                    {/* 1. Slim Bar Heating (Merah / Pink) */}

                                                    <Bar

                                                      yAxisId="left"

                                                      dataKey="heat_mins"

                                                      name="Durasi Heating (mnt)"

                                                      fill="#f43f5e"

                                                      radius={[3, 3, 0, 0]}

                                                      maxBarSize={12}

                                                      isAnimationActive={false}

                                                    >

                                                      {progChartSeries.map((entry, index) => {

                                                        const isSelected = activeBatch && activeBatch.id === entry.id;

                                                        return (

                                                          <Cell

                                                            key={`heat-${index}`}

                                                            fill={isSelected ? '#f43f5e' : '#fb7185'}

                                                            stroke={isSelected ? '#be123c' : 'none'}

                                                            strokeWidth={isSelected ? 1.5 : 0}

                                                            className="cursor-pointer hover:opacity-80 transition-opacity"

                                                            onClick={(e) => {

                                                              e?.stopPropagation?.();

                                                              if (entry.id) handleOpenBatch(entry.id);

                                                            }}

                                                          />

                                                        );

                                                      })}

                                                    </Bar>

                                                    {/* 2. Slim Bar Keep / Steady (Kuning / Amber) */}

                                                    <Bar

                                                      yAxisId="left"

                                                      dataKey="steady_mins"

                                                      name="Durasi Keep (mnt)"

                                                      fill="#f59e0b"

                                                      radius={[3, 3, 0, 0]}

                                                      maxBarSize={12}

                                                      isAnimationActive={false}

                                                    >

                                                      {progChartSeries.map((entry, index) => {

                                                        const isSelected = activeBatch && activeBatch.id === entry.id;

                                                        return (

                                                          <Cell

                                                            key={`keep-${index}`}

                                                            fill={isSelected ? '#f59e0b' : '#fbbf24'}

                                                            stroke={isSelected ? '#b45309' : 'none'}

                                                            strokeWidth={isSelected ? 1.5 : 0}

                                                            className="cursor-pointer hover:opacity-80 transition-opacity"

                                                            onClick={(e) => {

                                                              e?.stopPropagation?.();

                                                              if (entry.id) handleOpenBatch(entry.id);

                                                            }}

                                                          />

                                                        );

                                                      })}

                                                    </Bar>

                                                    {/* 3. Slim Bar Cooling (Biru Cyan) */}

                                                    <Bar

                                                      yAxisId="left"

                                                      dataKey="cool_mins"

                                                      name="Durasi Cooling (mnt)"

                                                      fill="#0ea5e9"

                                                      radius={[3, 3, 0, 0]}

                                                      maxBarSize={12}

                                                      isAnimationActive={false}

                                                    >

                                                      {progChartSeries.map((entry, index) => {

                                                        const isSelected = activeBatch && activeBatch.id === entry.id;

                                                        return (

                                                          <Cell

                                                            key={`cool-${index}`}

                                                            fill={isSelected ? '#0284c7' : '#38bdf8'}

                                                            stroke={isSelected ? '#0369a1' : 'none'}

                                                            strokeWidth={isSelected ? 1.5 : 0}

                                                            className="cursor-pointer hover:opacity-80 transition-opacity"

                                                            onClick={(e) => {

                                                              e?.stopPropagation?.();

                                                              if (entry.id) handleOpenBatch(entry.id);

                                                            }}

                                                          />

                                                        );

                                                      })}

                                                    </Bar>

                                                    {/* Line Tekanan Uap (Ungu) */}

                                                    <Line

                                                      yAxisId="right"

                                                      type="monotone"

                                                      dataKey="avg_pressure"

                                                      name="Avg Pressure (bar)"

                                                      stroke="#7c3aed"

                                                      strokeWidth={2.5}

                                                      dot={(dotProps) => {

                                                        const { cx, cy, payload } = dotProps;

                                                        if (cx == null || cy == null) return null;

                                                        const isSelected = activeBatch && activeBatch.id === payload?.id;

                                                        return (

                                                          <circle

                                                            key={`dot-${payload?.id || cx}`}

                                                            cx={cx}

                                                            cy={cy}

                                                            r={isSelected ? 5.5 : 3.5}

                                                            fill={isSelected ? '#6d28d9' : '#7c3aed'}

                                                            stroke={isSelected ? '#ffffff' : 'none'}

                                                            strokeWidth={isSelected ? 2 : 0}

                                                            className="cursor-pointer hover:scale-125 transition-transform"

                                                            onClick={(e) => {

                                                              e?.stopPropagation?.();

                                                              if (payload?.id) handleOpenBatch(payload.id);

                                                            }}

                                                          />

                                                        );

                                                      }}

                                                      activeDot={{

                                                        r: 6.5,

                                                        fill: '#6d28d9',

                                                        stroke: '#ffffff',

                                                        strokeWidth: 2,

                                                        cursor: 'pointer',

                                                        onClick: (e, eventPayload) => {

                                                          e?.stopPropagation?.();

                                                          const bId = eventPayload?.payload?.id || eventPayload?.id;

                                                          if (bId) handleOpenBatch(bId);

                                                        }

                                                      }}

                                                      isAnimationActive={false}

                                                    />

                                                  </ComposedChart>

                                                </ResponsiveContainer>

                                              </div>

                                            </div>

                                          </div>

                                        )}

                                        {/* ── MODE 2: KORELASI REGRESI VS TEKANAN UAP DENGAN GARIS PROGRAM ── */}

                                        {activeChartMode === 'correlation' && (

                                          <div className="space-y-4">

                                            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">

                                              <div>

                                                <h4 className="text-xs sm:text-sm font-bold text-slate-900">

                                                  Plot Korelasi Durasi {scatterPhaseMode === 'heating' ? 'Heating' : 'Cooling'} vs Tekanan Uap

                                                  {activeProgName !== 'ALL' && ` (Program: ${activeProgName})`}

                                                </h4>

                                                <p className="text-[11px] text-slate-500">

                                                  Membedah apakah perlambatan termal akibat drop suplai boiler (&lt;3.8 bar) atau degradasi mekanik mesin

                                                </p>

                                              </div>

                                              <div className="text-xs text-slate-500">

                                                Total Sampel: <b className="text-slate-800">{filteredCorr.length} batch</b>

                                              </div>

                                            </div>

                                            <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">

                                              {/* Scatter Chart (3 cols) */}

                                              <div className="lg:col-span-3 h-[320px] sm:h-[350px] w-full min-w-0 bg-slate-50/50 rounded-xl p-3 border border-slate-100">

                                                <ResponsiveContainer width="100%" height="100%">

                                                  <ScatterChart margin={{ top: 15, right: 20, bottom: 20, left: 0 }}>

                                                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />

                                                    {/* Sumbu X: Tekanan Uap */}

                                                    <XAxis

                                                      type="number"

                                                      dataKey="avg_steam_pressure"

                                                      name="Tekanan Uap"

                                                      unit=" bar"

                                                      domain={[1.5, 6.5]}

                                                      tick={{ fontSize: 10, fill: '#64748b' }}

                                                      label={{ value: 'Tekanan Uap Rata-rata (bar)', position: 'insideBottom', offset: -10, fontSize: 11, fill: '#475569' }}

                                                    />

                                                    {/* Sumbu Y: Durasi Heating atau Cooling */}

                                                    <YAxis

                                                      type="number"

                                                      dataKey={scatterPhaseMode === 'heating' ? 'real_heat' : 'real_cool'}

                                                      name={scatterPhaseMode === 'heating' ? 'Durasi Heating' : 'Durasi Cooling'}

                                                      unit=" mnt"

                                                      tick={{ fontSize: 10, fill: '#64748b' }}

                                                      label={{

                                                        value: scatterPhaseMode === 'heating' ? 'Durasi Heating (Menit)' : 'Durasi Cooling (Menit)',

                                                        angle: -90,

                                                        position: 'insideLeft',

                                                        offset: 15,

                                                        fontSize: 11,

                                                        fill: '#475569'

                                                      }}

                                                    />

                                                    <ZAxis range={[50, 160]} />

                                                    {/* Ambang Batas Kritis Boiler: 3.8 bar */}

                                                    <ReferenceLine

                                                      x={3.8}

                                                      stroke="#ef4444"

                                                      strokeDasharray="4 4"

                                                      label={{ value: 'Ambang Kritis 3.8 bar', fill: '#ef4444', fontSize: 10, position: 'insideTopLeft' }}

                                                    />

                                                    {/* GARIS PROGRAM: Durasi Ideal Master Resep */}

                                                    {activeProgInfo && (scatterPhaseMode === 'heating' ? activeProgInfo.ideal_heat : activeProgInfo.ideal_cool) && (

                                                      <ReferenceLine

                                                        y={scatterPhaseMode === 'heating' ? activeProgInfo.ideal_heat : activeProgInfo.ideal_cool}

                                                        stroke="#10b981"

                                                        strokeDasharray="4 4"

                                                        strokeWidth={2}

                                                        label={{

                                                          value: `Target Resep: ${scatterPhaseMode === 'heating' ? activeProgInfo.ideal_heat : activeProgInfo.ideal_cool} mnt`,

                                                          fill: '#059669',

                                                          fontSize: 10,

                                                          position: 'insideTopRight'

                                                        }}

                                                      />

                                                    )}

                                                    <RechartsTooltip

                                                      cursor={{ strokeDasharray: '3 3' }}

                                                      contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 8px 16px -4px rgb(0 0 0 / 0.1)', fontSize: '12px' }}

                                                      content={({ payload }) => {

                                                        if (!payload || !payload.length) return null;

                                                        const d = payload[0].payload;

                                                        const val = scatterPhaseMode === 'heating' ? d.real_heat : d.real_cool;

                                                        const idl = scatterPhaseMode === 'heating' ? d.ideal_heat : d.ideal_cool;

                                                        const delta = scatterPhaseMode === 'heating' ? d.delta_heat : d.delta_cool;

                                                        return (

                                                          <div className="bg-white p-3 rounded-xl shadow-lg border border-slate-200 text-xs space-y-1">

                                                            <div className="flex items-center justify-between font-semibold text-slate-800 pb-1 border-b border-slate-100">

                                                              <span>Batch #{d.batch_number}</span>

                                                              <span className="text-[10px] text-slate-400">{d.date} {d.time}</span>

                                                            </div>

                                                            <div>Program: <b className="text-indigo-600">{d.program_name}</b></div>

                                                            <div>Tekanan Boiler: <b>{d.avg_steam_pressure} bar</b></div>

                                                            <div>Durasi {scatterPhaseMode === 'heating' ? 'Heating' : 'Cooling'}: <b>{val} mnt</b> {idl != null && <span className="text-slate-400 font-normal">(Target: {idl} mnt)</span>}</div>

                                                            {delta != null && (

                                                              <div>Deviasi: <b className={delta > 10 ? 'text-rose-600' : 'text-emerald-600'}>{delta > 0 ? `+${delta}` : delta} mnt</b></div>

                                                            )}

                                                          </div>

                                                        );

                                                      }}

                                                    />

                                                    {/* Scatter Data Points */}

                                                    <Scatter data={filteredCorr}>

                                                      {filteredCorr.map((entry, index) => {

                                                        let col = '#10b981';

                                                        if (entry.quadrant === 'MECHANICAL_DEGRADATION') col = '#ef4444';

                                                        else if (entry.quadrant === 'BOILER_DROP') col = '#f97316';

                                                        else if (entry.quadrant === 'SEVERE_LAG') col = '#e11d48';

                                                        return (

                                                          <Cell

                                                            key={`scat-${index}`}

                                                            fill={col}

                                                            stroke="#ffffff"

                                                            strokeWidth={1}

                                                            className="cursor-pointer hover:opacity-80 transition-opacity"

                                                            onClick={() => {

                                                              if (entry.id) window.open(`/history/report/${entry.id}`, '_blank');

                                                            }}

                                                          />

                                                        );

                                                      })}

                                                    </Scatter>

                                                  </ScatterChart>

                                                </ResponsiveContainer>

                                              </div>

                                              {/* Diagnostic Kuadran Card (1 col) */}

                                              <div className="space-y-2.5 flex flex-col justify-between">

                                                <div>

                                                  <h5 className="text-xs font-bold text-slate-800 uppercase tracking-wider mb-2">

                                                    Distribusi Diagnostik ({filteredCorr.length} Batch)

                                                  </h5>

                                                  <div className="space-y-2 text-xs">

                                                    {/* Optimal */}

                                                    <div className="p-2.5 bg-emerald-50/70 border border-emerald-200 rounded-xl">

                                                      <div className="flex justify-between items-center font-bold text-emerald-900">

                                                        <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-emerald-500" /> Optimal</span>

                                                        <span>{qStats.optimal} batch ({Math.round((qStats.optimal / qStats.total) * 100)}%)</span>

                                                      </div>

                                                      <p className="text-[10px] text-emerald-700 mt-1">Tekanan uap &ge;3.8 bar &amp; durasi sesuai resep.</p>

                                                    </div>

                                                    {/* Kerak HE / Katup */}

                                                    <div className="p-2.5 bg-red-50/70 border border-red-200 rounded-xl">

                                                      <div className="flex justify-between items-center font-bold text-red-900">

                                                        <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-red-500" /> Kerak HE / Katup</span>

                                                        <span>{qStats.mech} batch ({Math.round((qStats.mech / qStats.total) * 100)}%)</span>

                                                      </div>

                                                      <p className="text-[10px] text-red-700 mt-1">Molor padahal uap cukup (&ge;3.8 bar). Indikasi masalah internal mesin.</p>

                                                    </div>

                                                    {/* Drop Boiler */}

                                                    <div className="p-2.5 bg-amber-50/70 border border-amber-200 rounded-xl">

                                                      <div className="flex justify-between items-center font-bold text-amber-900">

                                                        <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-amber-500" /> Drop Boiler</span>

                                                        <span>{qStats.boiler} batch ({Math.round((qStats.boiler / qStats.total) * 100)}%)</span>

                                                      </div>

                                                      <p className="text-[10px] text-amber-700 mt-1">Melambat karena tekanan uap pabrik drop (&lt;3.8 bar).</p>

                                                    </div>

                                                  </div>

                                                </div>

                                              </div>

                                            </div>

                                          </div>

                                        )}

                                      </div>

                                    );

                                  })()}

                                  {/* ── Sub-Panel 3: Recent Batches Table ── */}

                                  {drawerSubTab === 'batches' && (

                                    <div className="bg-white p-4 sm:p-5 rounded-2xl border border-slate-200 shadow-2xs space-y-3">

                                      <div className="flex items-center justify-between">

                                        <h5 className="font-bold text-slate-900 text-xs sm:text-sm">

                                          Daftar 20 Batch Terbaru Mesin Ini

                                        </h5>

                                        <span className="text-[11px] text-slate-400">Klik Detail untuk membuka audit mendalam proses</span>

                                      </div>

                                      <div className="hidden sm:block overflow-x-auto">

                                        <table className="w-full text-left text-xs whitespace-nowrap">

                                          <thead className="bg-slate-50 text-slate-500 font-bold border-b border-slate-200 text-[10px]">

                                            <tr>

                                              <th className="py-2.5 px-3">Batch & Order</th>

                                              <th className="py-2.5 px-3">Program</th>

                                              <th className="py-2.5 px-2 text-center">Waktu</th>

                                              <th className="py-2.5 px-2 text-center">Heating</th>

                                              <th className="py-2.5 px-2 text-center">Cooling</th>

                                              <th className="py-2.5 px-2 text-center">Efisiensi</th>

                                              <th className="py-2.5 px-2 text-center">Suhu Max</th>

                                              <th className="py-2.5 px-3 text-right">Uap Boros</th>

                                              <th className="py-2.5 px-3 text-center">Laporan</th>

                                            </tr>

                                          </thead>

                                          <tbody className="divide-y divide-slate-100">

                                            {m.recent_batches.map((b) => (

                                              <tr key={b.id} className="hover:bg-slate-50/60">

                                                <td className="py-2.5 px-3 font-bold text-slate-800">

                                                  #{b.batch_number} <span className="text-slate-400 font-normal">({b.order_no})</span>

                                                </td>

                                                <td className="py-2.5 px-3 font-medium text-slate-700">

                                                  {b.program_name}

                                                </td>

                                                <td className="py-2.5 px-2 text-center text-slate-500 text-[11px]">

                                                  {b.date_str} {b.time_str}

                                                </td>

                                                <td className="py-2.5 px-2 text-center">

                                                  <span>{b.heat_mins}m</span>

                                                  {b.delta_heat != null && (

                                                    <span className={`block text-[10px] font-bold ${b.delta_heat > 10 ? 'text-rose-600' : 'text-emerald-600'}`}>

                                                      {b.delta_heat > 0 ? `+${b.delta_heat}m` : `${b.delta_heat}m`}

                                                    </span>

                                                  )}

                                                </td>

                                                <td className="py-2.5 px-2 text-center">

                                                  <span>{b.cool_mins}m</span>

                                                  {b.delta_cool != null && (

                                                    <span className={`block text-[10px] font-bold ${b.delta_cool > 10 ? 'text-rose-600' : 'text-emerald-600'}`}>

                                                      {b.delta_cool > 0 ? `+${b.delta_cool}m` : `${b.delta_cool}m`}

                                                    </span>

                                                  )}

                                                </td>

                                                <td className="py-2.5 px-2 text-center font-bold">

                                                  {b.eff != null ? (

                                                    <span className={b.eff >= 85 ? 'text-emerald-600' : b.eff >= 70 ? 'text-blue-600' : 'text-rose-600'}>

                                                      {b.eff}%

                                                    </span>

                                                  ) : '-'}

                                                </td>

                                                <td className="py-2.5 px-2 text-center text-slate-700">

                                                  {b.max_temp ? `${b.max_temp}°C` : '-'}

                                                </td>

                                                <td className="py-2.5 px-3 text-right font-medium text-slate-800">

                                                  {b.waste_steam_kg ? `${b.waste_steam_kg} kg` : '-'}

                                                </td>

                                                <td className="py-2.5 px-3 text-center">

                                                  <button

                                                    type="button"

                                                    onClick={(e) => {

                                                      e.stopPropagation();

                                                      window.open(`/history/report/${b.id}`, '_blank');

                                                    }}

                                                    className="inline-flex items-center gap-1 text-indigo-600 hover:text-indigo-800 font-bold text-[11px] hover:underline"

                                                  >

                                                    <span>Buka</span>

                                                    <ExternalLink size={11} />

                                                  </button>

                                                </td>

                                              </tr>

                                            ))}

                                          </tbody>

                                        </table>

                                      </div>

                                      {/* Mobile Cards View for Batches */}

                                      <div className="block sm:hidden space-y-2 mt-2">

                                        {m.recent_batches.map((b) => (

                                          <div key={b.id} className="p-2.5 rounded-xl bg-slate-50 border border-slate-200/80 space-y-2">

                                            <div className="flex items-center justify-between">

                                              <div>

                                                <span className="font-extrabold text-slate-800 text-xs">#{b.batch_number}</span>

                                                <span className="text-[10px] text-slate-400 font-normal ml-1">({b.order_no})</span>

                                                <div className="text-[11px] font-semibold text-slate-700">{b.program_name}</div>

                                              </div>

                                              <button

                                                type="button"

                                                onClick={(e) => {

                                                  e.stopPropagation();

                                                  window.open(`/history/report/${b.id}`, '_blank');

                                                }}

                                                className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-indigo-50 hover:bg-indigo-100 text-indigo-700 border border-indigo-200 font-bold text-[11px] shadow-2xs"

                                              >

                                                <span>Buka</span>

                                                <ExternalLink size={10} />

                                              </button>

                                            </div>

                                            <div className="grid grid-cols-4 gap-1 text-center text-[10px]">

                                              <div className="bg-white p-1 rounded-lg border border-slate-100">

                                                <span className="text-slate-400 block text-[9px]">Heating</span>

                                                <span className="font-bold">{b.heat_mins}m</span>

                                                {b.delta_heat != null && (

                                                  <span className={`block text-[9px] font-extrabold ${b.delta_heat > 10 ? 'text-rose-600' : 'text-emerald-600'}`}>

                                                    {b.delta_heat > 0 ? `+${b.delta_heat}m` : `${b.delta_heat}m`}

                                                  </span>

                                                )}

                                              </div>

                                              <div className="bg-white p-1 rounded-lg border border-slate-100">

                                                <span className="text-slate-400 block text-[9px]">Cooling</span>

                                                <span className="font-bold">{b.cool_mins}m</span>

                                                {b.delta_cool != null && (

                                                  <span className={`block text-[9px] font-extrabold ${b.delta_cool > 10 ? 'text-rose-600' : 'text-emerald-600'}`}>

                                                    {b.delta_cool > 0 ? `+${b.delta_cool}m` : `${b.delta_cool}m`}

                                                  </span>

                                                )}

                                              </div>

                                              <div className="bg-white p-1 rounded-lg border border-slate-100">

                                                <span className="text-slate-400 block text-[9px]">Efisiensi</span>

                                                <span className={`font-extrabold ${b.eff >= 85 ? 'text-emerald-600' : b.eff >= 70 ? 'text-blue-600' : 'text-rose-600'}`}>

                                                  {b.eff != null ? `${b.eff}%` : '-'}

                                                </span>

                                              </div>

                                              <div className="bg-white p-1 rounded-lg border border-slate-100">

                                                <span className="text-slate-400 block text-[9px]">Suhu Max</span>

                                                <span className="font-bold">{b.max_temp ? `${b.max_temp}°C` : '-'}</span>

                                              </div>

                                            </div>

                                            <div className="flex items-center justify-between text-[10px] text-slate-500 pt-1 border-t border-slate-200/60">

                                              <span>{b.date_str} {b.time_str}</span>

                                              {b.waste_steam_kg ? (

                                                <span className="font-bold text-rose-600">Uap Boros: {b.waste_steam_kg} kg</span>

                                              ) : (

                                                <span className="text-slate-400">Normal</span>

                                              )}

                                            </div>

                                          </div>

                                        ))}

                                      </div>

                                    </div>

                                  )}

                                  {/* ── Sub-Panel 4: Prescription & Projections ── */}

                                  {drawerSubTab === 'prescription' && (

                                    <div className="space-y-4">

                                      {/* Technical Diagnosis Banner */}

                                      <div className={`p-4 sm:p-5 rounded-2xl border ${diagTone.box}`}>

                                        <div className="flex items-start gap-3">

                                          <div className={`p-2 rounded-xl ${diagTone.badge} shrink-0`}>

                                            <DiagIcon size={20} />

                                          </div>

                                          <div className="flex-1">

                                            <div className="flex items-center gap-2">

                                              <span className={`px-2 py-0.5 rounded text-[10px] font-black uppercase tracking-wider ${diagTone.badge}`}>

                                                {m.primary_diagnosis.tag}

                                              </span>

                                              <h5 className="font-black text-sm">{m.primary_diagnosis.title}</h5>

                                            </div>

                                            <p className="text-xs mt-1.5 leading-relaxed">

                                              {m.primary_diagnosis.summary}

                                            </p>

                                            <div className="mt-3 pt-3 border-t border-slate-200/60 text-xs">

                                              <span className="font-bold">Rekomendasi Tindakan Teknis: </span>

                                              <span>{m.primary_diagnosis.prescription}</span>

                                            </div>

                                          </div>

                                        </div>

                                      </div>

                                      {/* Financial Projection Cards */}

                                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">

                                        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-2xs">

                                          <span className="text-[11px] font-bold text-slate-500 uppercase">Rata-rata Terbuang / Batch</span>

                                          <div className="text-xl font-black text-slate-900 mt-1">

                                            {formatRp(m.avg_waste_rp_batch)}

                                          </div>

                                          <p className="text-[10px] text-slate-400 mt-1">

                                            Dari {m.evaluated_batches_count} batch yang dievaluasi

                                          </p>

                                        </div>

                                        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-2xs">

                                          <span className="text-[11px] font-bold text-slate-500 uppercase">Proyeksi 7 Hari ke Depan</span>

                                          <div className="text-xl font-black text-amber-600 mt-1">

                                            {formatRp(m.projected_7d_rp)}

                                          </div>

                                          <p className="text-[10px] text-slate-400 mt-1">

                                            Jika kondisi mesin tetap seperti sekarang

                                          </p>

                                        </div>

                                        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-2xs">

                                          <span className="text-[11px] font-bold text-slate-500 uppercase">Proyeksi 30 Hari (1 Bulan)</span>

                                          <div className="text-xl font-black text-rose-600 mt-1">

                                            {formatRp(m.projected_30d_rp)}

                                          </div>

                                          <p className="text-[10px] text-slate-400 mt-1">

                                            Setara {numFmt(m.projected_30d_steam_kg / 1000, 1)} Ton Uap & {numFmt(m.projected_30d_power_kwh, 0)} kWh

                                          </p>

                                        </div>

                                      </div>

                                    </div>

                                  )}

                                </div>
    );
  };

  return (
    <div className="p-2 sm:p-4 md:p-6 min-h-screen bg-slate-50 text-slate-800">
      {/* ══════════════════════════════════════════════════════════════════════
          1. HEADER & GLOBAL CONTROLS
         ══════════════════════════════════════════════════════════════════════ */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 mb-6">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-indigo-100 text-indigo-700 tracking-wide uppercase">
              Fleet Intelligence Hub
            </span>
            <span className="text-xs text-slate-400 font-mono">
              SPC & Energy Waste Audit
            </span>
          </div>
          <h1 className="text-xl sm:text-2xl font-black text-slate-900 tracking-tight">
            Machine Health & Energy Waste Analytics
          </h1>
          <p className="text-xs sm:text-sm text-slate-500">
            {data ? `Periode Analisis: ${data.date_range_label}` : 'Memuat data analitik armada...'}
          </p>
        </div>

        {/* Controls: Date Picker & Window Selector */}
        <div className="flex flex-wrap items-center gap-2.5">
          {/* Window Range Toggle */}
          <div className="inline-flex rounded-xl bg-white p-1 shadow-2xs border border-slate-200 text-xs font-semibold">
            <button
              type="button"
              onClick={() => setWindowRange('1D')}
              className={`px-3 py-1.5 rounded-lg transition-all ${
                windowRange === '1D'
                  ? 'bg-indigo-600 text-white shadow-2xs'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              1 Hari (24J)
            </button>
            <button
              type="button"
              onClick={() => setWindowRange('7D')}
              className={`px-3 py-1.5 rounded-lg transition-all ${
                windowRange === '7D'
                  ? 'bg-indigo-600 text-white shadow-2xs'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              7 Hari Terakhir
            </button>
            <button
              type="button"
              onClick={() => setWindowRange('30D')}
              className={`px-3 py-1.5 rounded-lg transition-all ${
                windowRange === '30D'
                  ? 'bg-indigo-600 text-white shadow-2xs'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              30 Hari Terakhir
            </button>
          </div>

          {/* Date Picker */}
          <div className="flex items-center gap-2 bg-white px-3 py-2 rounded-xl shadow-2xs border border-slate-200">
            <Calendar size={15} className="text-slate-500" />
            <input
              type="date"
              value={selectedDate}
              onChange={(e) => setSelectedDate(e.target.value)}
              className="text-xs font-semibold text-slate-700 outline-none cursor-pointer bg-transparent"
            />
          </div>

          <button
            type="button"
            onClick={() => fetchReport(selectedDate, windowRange)}
            className="p-2 bg-white hover:bg-slate-100 rounded-xl border border-slate-200 shadow-2xs text-slate-600 transition-colors"
            title="Muat Ulang"
          >
            <RefreshCw size={15} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {loading ? (
        <div className="flex flex-col items-center justify-center min-h-[400px] bg-white rounded-2xl border border-slate-200 shadow-xs p-8">
          <Activity className="w-10 h-10 text-indigo-500 animate-spin mb-3" />
          <h3 className="font-bold text-slate-800 text-sm">Menghitung Machine Health Index (MHI) & Proyeksi Energi...</h3>
          <p className="text-xs text-slate-400 mt-1">Mengagregasikan 37+ mesin, evaluasi 3 fase, dan prediksi 3-lapis PINN...</p>
        </div>
      ) : error ? (
        <div className="bg-rose-50 border border-rose-200 p-6 rounded-2xl text-center">
          <AlertCircle className="w-10 h-10 text-rose-500 mx-auto mb-2" />
          <h3 className="text-base font-bold text-rose-900 mb-1">Gagal Memuat Laporan Mesin</h3>
          <p className="text-xs text-rose-700 mb-4">{error}</p>
          <button
            type="button"
            onClick={() => fetchReport(selectedDate, windowRange)}
            className="px-4 py-2 bg-rose-600 hover:bg-rose-700 text-white rounded-xl text-xs font-bold transition-colors cursor-pointer"
          >
            Coba Lagi
          </button>
        </div>
      ) : data ? (
        <div className="space-y-6">
          {/* ══════════════════════════════════════════════════════════════════════
              2. EXECUTIVE FLEET KPIS (6 CARDS)
             ══════════════════════════════════════════════════════════════════════ */}
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
            {/* Card 1: Health Index */}
            <div className="bg-white p-3.5 sm:p-4 rounded-2xl border border-slate-200 shadow-2xs">
              <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wide flex items-center gap-1">
                <Cpu size={13} className="text-indigo-500" />
                Fleet Health (MHI)
              </span>
              <div className="flex items-baseline gap-1.5 mt-1.5">
                <span className="text-2xl font-black text-slate-900">{kpi?.avg_health_score || '-'}</span>
                <span className="text-xs font-semibold text-slate-400">/ 100</span>
              </div>
              <div className="flex items-center gap-1 mt-2 text-[10px] font-bold">
                <span className="px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-800">{kpi?.healthy_count} Sehat</span>
                <span className="px-1.5 py-0.5 rounded bg-amber-100 text-amber-800">{kpi?.warning_count} C</span>
                <span className="px-1.5 py-0.5 rounded bg-rose-100 text-rose-800">{kpi?.critical_count} D</span>
              </div>
            </div>

            {/* Card 2: Lost Production Hours */}
            <div className="bg-white p-3.5 sm:p-4 rounded-2xl border border-slate-200 shadow-2xs">
              <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wide flex items-center gap-1">
                <Clock size={13} className="text-amber-500" />
                Jam Siklus Hilang
              </span>
              <div className="flex items-baseline gap-1 mt-1.5">
                <span className="text-2xl font-black text-amber-600">{numFmt(kpi?.total_loss_hours, 0)}</span>
                <span className="text-xs font-semibold text-slate-500">Jam</span>
              </div>
              <p className="text-[10px] text-slate-400 mt-2 truncate">
                Slow heating + cooling + over-hold
              </p>
            </div>

            {/* Card 3: Steam Waste */}
            <div className="bg-white p-3.5 sm:p-4 rounded-2xl border border-slate-200 shadow-2xs">
              <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wide flex items-center gap-1">
                <Flame size={13} className="text-rose-500" />
                Uap Terbuang (Aktual)
              </span>
              <div className="flex items-baseline gap-1 mt-1.5">
                <span className="text-2xl font-black text-slate-900">
                  {kpi?.total_steam_waste_kg >= 1000
                    ? `${numFmt(kpi.total_steam_waste_kg / 1000, 1)}`
                    : numFmt(kpi?.total_steam_waste_kg, 0)}
                </span>
                <span className="text-xs font-semibold text-slate-500">
                  {kpi?.total_steam_waste_kg >= 1000 ? 'Ton' : 'kg'}
                </span>
              </div>
              <p className="text-[10px] text-slate-400 mt-2">
                Tarif Rp {data.tariffs?.steam_cost_per_kg}/kg
              </p>
            </div>

            {/* Card 4: Power Waste */}
            <div className="bg-white p-3.5 sm:p-4 rounded-2xl border border-slate-200 shadow-2xs">
              <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wide flex items-center gap-1">
                <Zap size={13} className="text-yellow-500" />
                Listrik Pompa Terbuang
              </span>
              <div className="flex items-baseline gap-1 mt-1.5">
                <span className="text-2xl font-black text-slate-900">{numFmt(kpi?.total_power_waste_kwh, 0)}</span>
                <span className="text-xs font-semibold text-slate-500">kWh</span>
              </div>
              <p className="text-[10px] text-slate-400 mt-2">
                Motor berputar saat siklus molor
              </p>
            </div>

            {/* Card 5: Actual Total Loss Rp */}
            <div className="bg-white p-3.5 sm:p-4 rounded-2xl border border-slate-200 shadow-2xs">
              <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wide flex items-center gap-1">
                <DollarSign size={13} className="text-emerald-500" />
                Total Kerugian Energi
              </span>
              <div className="flex items-baseline gap-1 mt-1.5">
                <span className="text-xl sm:text-2xl font-black text-rose-600">
                  {formatRp(kpi?.total_financial_loss_rp)}
                </span>
              </div>
              <p className="text-[10px] text-slate-400 mt-2">
                Total Uap + Listrik terbuang
              </p>
            </div>

            {/* Card 6: 30-Day Run-Rate Projection */}
            <div className="bg-gradient-to-br from-rose-500 to-rose-600 text-white p-3.5 sm:p-4 rounded-2xl shadow-xs relative overflow-hidden">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-bold uppercase tracking-wider text-rose-100 flex items-center gap-1">
                  <Flame size={13} className="text-rose-200" />
                  Proyeksi 30 Hari
                </span>
                <span className="text-[9px] bg-white/20 px-1.5 py-0.5 rounded font-bold">
                  Bila Dibiarkan
                </span>
              </div>
              <div className="mt-1.5">
                <span className="text-lg sm:text-xl font-black tracking-tight">
                  {formatRp(kpi?.projected_30d_loss_rp)}
                </span>
              </div>
              <p className="text-[10px] text-rose-100/90 mt-2 leading-tight">
                Khusus Mesin Kritis (C&D): <b>{formatRp(kpi?.projected_30d_critical_loss_rp)}</b>
              </p>
            </div>
          </div>

          {/* ══════════════════════════════════════════════════════════════════════
              3. VISUAL FLEET CHARTS (QUADRANT MATRIX & TOP WASTEFUL MACHINES)
             ══════════════════════════════════════════════════════════════════════ */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Chart 1: Health Matrix (Scatter Quadrant) */}
            <div className="bg-white p-4 sm:p-5 rounded-2xl border border-slate-200 shadow-2xs">
              <div className="flex items-center justify-between mb-2">
                <div>
                  <h3 className="text-sm font-bold text-slate-900 flex items-center gap-1.5">
                    <Activity size={16} className="text-indigo-600" />
                    Peta Kuadran: Kesehatan Mesin vs Pemborosan Biaya
                  </h3>
                  <p className="text-xs text-slate-500">
                    Sumbu X: Skor Kesehatan MHI (0–100) | Sumbu Y: Pemborosan Energi (Ribu Rp / Batch)
                  </p>
                </div>
                <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-slate-100 text-slate-600">
                  {healthMatrixData.length} Mesin
                </span>
              </div>

              <div className="h-64 sm:h-72 w-full mt-3">
                <ResponsiveContainer width="100%" height="100%">
                  <ScatterChart margin={{ top: 15, right: 15, bottom: 20, left: 10 }}>
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
                    <ZAxis type="number" dataKey="z" range={[60, 220]} />
                    <ReferenceLine x={70} stroke="#f59e0b" strokeDasharray="4 4" label={{ value: 'Batas Kritis 70', position: 'insideTopLeft', fontSize: 9, fill: '#d97706' }} />
                    <ReferenceLine y={100} stroke="#ef4444" strokeDasharray="4 4" label={{ value: 'Rp 100k/batch', position: 'insideBottomRight', fontSize: 9, fill: '#dc2626' }} />
                    <RechartsTooltip
                      cursor={{ strokeDasharray: '3 3' }}
                      content={({ active, payload }) => {
                        if (active && payload && payload.length) {
                          const p = payload[0].payload;
                          return (
                            <div className="bg-slate-900 text-white p-2.5 rounded-xl shadow-xl text-xs space-y-1 border border-slate-700">
                              <div className="font-bold flex items-center justify-between gap-2 border-b border-slate-700 pb-1">
                                <span>{p.name}</span>
                                <span className="px-1.5 py-0.2 rounded bg-indigo-500 font-bold text-[10px]">Grade {p.grade}</span>
                              </div>
                              <div>Skor Kesehatan: <b>{p.x} / 100</b></div>
                              <div>Pemborosan: <b>Rp {Math.round(p.waste_rp).toLocaleString('id-ID')} / batch</b></div>
                              <div>Proyeksi 30 Hari: <b>Rp {Math.round(p.waste_30d).toLocaleString('id-ID')}</b></div>
                              <div className="text-slate-400 text-[10px]">Klik titik untuk bedah mendalam mesin ini</div>
                            </div>
                          );
                        }
                        return null;
                      }}
                    />
                    <Scatter
                      data={healthMatrixData}
                      onClick={(node) => {
                        if (node && node.id) toggleExpand(node.id);
                      }}
                      className="cursor-pointer"
                    >
                      {healthMatrixData.map((entry, index) => {
                        let col = '#10b981'; // Green
                        if (entry.grade === 'D') col = '#f43f5e';
                        else if (entry.grade === 'C') col = '#f59e0b';
                        else if (entry.grade === 'B') col = '#3b82f6';
                        return <Cell key={`cell-${index}`} fill={col} fillOpacity={0.85} stroke="#ffffff" strokeWidth={1.5} />;
                      })}
                    </Scatter>
                  </ScatterChart>
                </ResponsiveContainer>
              </div>

              {/* Legend Kuadran */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-2 border-t border-slate-100 text-[10px] text-slate-500">
                <div className="flex items-center gap-1.5">
                  <span className="w-2.5 h-2.5 rounded-full bg-rose-500"></span>
                  <span>Kiri-Atas: Prioritas Perbaikan</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="w-2.5 h-2.5 rounded-full bg-amber-500"></span>
                  <span>Kiri-Bawah: Degradasi Teknis</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="w-2.5 h-2.5 rounded-full bg-sky-500"></span>
                  <span>Kanan-Atas: Inefisiensi Eksternal</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="w-2.5 h-2.5 rounded-full bg-emerald-500"></span>
                  <span>Kanan-Bawah: Benchmark Prima</span>
                </div>
              </div>
            </div>

            {/* Chart 2: Top 10 Wasteful Machines (Bar Chart) */}
            <div className="bg-white p-4 sm:p-5 rounded-2xl border border-slate-200 shadow-2xs">
              <div className="flex items-center justify-between mb-2">
                <div>
                  <h3 className="text-sm font-bold text-slate-900 flex items-center gap-1.5">
                    <BarChart3 size={16} className="text-rose-600" />
                    Top 10 Mesin dengan Potensi Pemborosan Terbesar
                  </h3>
                  <p className="text-xs text-slate-500">
                    Proyeksi Biaya Energi Terbuang (Juta Rp / 30 Hari) Jika Tidak Diperbaiki
                  </p>
                </div>
                <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-rose-50 text-rose-700">
                  Ranking Prioritas
                </span>
              </div>

              <div className="hidden sm:block h-64 sm:h-72 w-full mt-3">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={topWasteMachines} margin={{ top: 15, right: 15, bottom: 20, left: 10 }}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                    <XAxis
                      dataKey="name"
                      tick={{ fontSize: 10, fill: '#64748b' }}
                      interval={0}
                    />
                    <YAxis
                      tick={{ fontSize: 10, fill: '#64748b' }}
                      label={{ value: 'Juta Rp / 30 Hari', angle: -90, position: 'insideLeft', fontSize: 10, fill: '#64748b' }}
                    />
                    <RechartsTooltip
                      content={({ active, payload }) => {
                        if (active && payload && payload.length) {
                          const m = payload[0].payload;
                          return (
                            <div className="bg-slate-900 text-white p-2.5 rounded-xl text-xs space-y-1 shadow-xl border border-slate-700">
                              <div className="font-bold border-b border-slate-700 pb-1">{m.name}</div>
                              <div>Proyeksi Kerugian: <b className="text-rose-400">Rp {m.waste_jt} Juta / bln</b></div>
                              <div>Uap Ekstra: <b>{m.steam_ton} Ton</b></div>
                              <div>Listrik Ekstra: <b>{m.power_kwh} kWh</b></div>
                            </div>
                          );
                        }
                        return null;
                      }}
                    />
                    <Bar
                      dataKey="waste_jt"
                      name="Kerugian (Juta Rp)"
                      fill="#f43f5e"
                      radius={[4, 4, 0, 0]}
                      onClick={(node) => {
                        if (node && node.id) toggleExpand(node.id);
                      }}
                      className="cursor-pointer"
                    >
                      {topWasteMachines.map((entry, index) => {
                        let fill = '#f43f5e';
                        if (entry.grade === 'B') fill = '#3b82f6';
                        else if (entry.grade === 'C') fill = '#f59e0b';
                        return <Cell key={`bar-${index}`} fill={fill} />;
                      })}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>

              {/* Mobile Horizontal Ranking View */}
              <div className="block sm:hidden space-y-2 mt-3">
                {topWasteMachines.map((m, idx) => {
                  const maxVal = topWasteMachines[0]?.waste_jt || 1;
                  const pct = Math.min(100, Math.max(8, (m.waste_jt / maxVal) * 100));
                  const gradeStyle = GRADE_STYLES[m.grade] || GRADE_STYLES.B;
                  return (
                    <div
                      key={m.id || idx}
                      onClick={() => toggleExpand(m.id)}
                      className="p-2.5 rounded-xl bg-slate-50 border border-slate-200/80 active:bg-indigo-50/50 transition-colors cursor-pointer"
                    >
                      <div className="flex items-center justify-between text-xs mb-1.5">
                        <div className="flex items-center gap-1.5 font-bold text-slate-800">
                          <span className="w-5 h-5 rounded-full bg-slate-200 text-slate-700 flex items-center justify-center text-[10px] font-black">
                            {idx + 1}
                          </span>
                          <span className="text-xs">{m.name}</span>
                          <span className={`px-1.5 py-0.2 rounded text-[9.5px] font-bold border ${gradeStyle.badge}`}>
                            Grade {m.grade}
                          </span>
                        </div>
                        <span className="font-extrabold text-rose-600 text-xs">
                          Rp {m.waste_jt} Jt
                        </span>
                      </div>
                      <div className="w-full bg-slate-200/80 h-2 rounded-full overflow-hidden">
                        <div
                          className="h-full rounded-full transition-all duration-500 bg-rose-500"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                      <div className="flex items-center justify-between text-[10px] text-slate-400 mt-1 font-medium">
                        <span>Uap Ekstra: <b>{m.steam_ton} Ton</b></span>
                        <span>Listrik: <b>{m.power_kwh} kWh</b></span>
                      </div>
                    </div>
                  );
                })}
              </div>

              <div className="flex items-center justify-between pt-2 border-t border-slate-100 text-[10px] text-slate-500">
                <span>Diurutkan berdasarkan total nominal kerugian uap & listrik</span>
                <span className="font-semibold text-rose-600">Klik batang untuk melihat detail perbaikan</span>
              </div>
            </div>
          </div>

          {/* ══════════════════════════════════════════════════════════════════════
              4. CONTROLS, SEARCH, AND FILTERS
             ══════════════════════════════════════════════════════════════════════ */}
          <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-2xs space-y-3">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
              {/* Search Bar */}
              <div className="relative flex-1 max-w-md">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 w-4 h-4" />
                <input
                  type="text"
                  placeholder="Cari nama mesin (misal: JD 12, JR 8, ZET 6)..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full pl-9 pr-4 py-2 text-xs font-medium border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-400 bg-slate-50"
                />
              </div>

              {/* Sort By Dropdown */}
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-500 font-medium">Urutkan:</span>
                <select
                  value={sortBy}
                  onChange={(e) => setSortBy(e.target.value)}
                  className="text-xs font-semibold bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 outline-none cursor-pointer focus:ring-2 focus:ring-indigo-400"
                >
                  <option value="critical">Prioritas: Paling Kritis Dulu (MHI Terendah)</option>
                  <option value="waste">Finansial: Paling Boros Dulu (Rp Terbesar)</option>
                  <option value="health_desc">Kondisi: Paling Prima Dulu (MHI Tertinggi)</option>
                  <option value="name">Alfabet Nama Mesin</option>
                </select>
              </div>
            </div>

            {/* Quick Filter Pills */}
            <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-slate-100">
              <div className="flex items-center gap-1.5 overflow-x-auto no-scrollbar pb-1 sm:pb-0">
                <span className="text-[11px] font-semibold text-slate-400 mr-1">Status:</span>
                <button
                  type="button"
                  onClick={() => setStatusFilter('ALL')}
                  className={`px-2.5 py-1 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                    statusFilter === 'ALL' ? 'bg-slate-900 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                  }`}
                >
                  Semua ({data.machines.length})
                </button>
                <button
                  type="button"
                  onClick={() => setStatusFilter('CRITICAL')}
                  className={`px-2.5 py-1 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                    statusFilter === 'CRITICAL' ? 'bg-rose-600 text-white' : 'bg-rose-50 text-rose-700 hover:bg-rose-100'
                  }`}
                >
                  🔴 Kritis ({data.machines.filter(m => m.health_grade === 'D').length})
                </button>
                <button
                  type="button"
                  onClick={() => setStatusFilter('WARNING')}
                  className={`px-2.5 py-1 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                    statusFilter === 'WARNING' ? 'bg-amber-600 text-white' : 'bg-amber-50 text-amber-700 hover:bg-amber-100'
                  }`}
                >
                  🟡 Pantau ({data.machines.filter(m => m.health_grade === 'C').length})
                </button>
                <button
                  type="button"
                  onClick={() => setStatusFilter('HEALTHY')}
                  className={`px-2.5 py-1 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                    statusFilter === 'HEALTHY' ? 'bg-emerald-600 text-white' : 'bg-emerald-50 text-emerald-700 hover:bg-emerald-100'
                  }`}
                >
                  🟢 Prima ({data.machines.filter(m => m.health_grade === 'A' || m.health_grade === 'B').length})
                </button>
              </div>

              {/* Group Pills */}
              <div className="flex items-center gap-1.5 overflow-x-auto no-scrollbar pb-1 sm:pb-0">
                <span className="text-[11px] font-semibold text-slate-400 mr-1">Grup:</span>
                <button
                  type="button"
                  onClick={() => setGroupFilter('ALL')}
                  className={`px-2 py-0.5 rounded text-[11px] font-bold ${
                    groupFilter === 'ALL' ? 'bg-indigo-600 text-white' : 'bg-slate-100 text-slate-600'
                  }`}
                >
                  Semua
                </button>
                <button
                  type="button"
                  onClick={() => setGroupFilter('JD')}
                  className={`px-2 py-0.5 rounded text-[11px] font-bold ${
                    groupFilter === 'JD' ? 'bg-indigo-600 text-white' : 'bg-slate-100 text-slate-600'
                  }`}
                >
                  Jet Dyeing (JD)
                </button>
                <button
                  type="button"
                  onClick={() => setGroupFilter('JR')}
                  className={`px-2 py-0.5 rounded text-[11px] font-bold ${
                    groupFilter === 'JR' ? 'bg-indigo-600 text-white' : 'bg-slate-100 text-slate-600'
                  }`}
                >
                  Jet Relax (JR)
                </button>
                <button
                  type="button"
                  onClick={() => setGroupFilter('ZET')}
                  className={`px-2 py-0.5 rounded text-[11px] font-bold ${
                    groupFilter === 'ZET' ? 'bg-indigo-600 text-white' : 'bg-slate-100 text-slate-600'
                  }`}
                >
                  Jet Print (ZET)
                </button>
              </div>
            </div>
          </div>

          {/* ══════════════════════════════════════════════════════════════════════
              5. MASTER FLEET TABLE & EXPANDED DRAWER
             ══════════════════════════════════════════════════════════════════════ */}
          <div className="bg-white rounded-2xl border border-slate-200 shadow-2xs overflow-hidden">
            {/* Desktop Table View */}
            <div className="hidden md:block overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead className="bg-slate-50 border-b border-slate-200 text-slate-600 uppercase tracking-wider text-[10px] font-bold select-none">
                  <tr>
                    <th className="py-2.5 px-3 sticky left-0 bg-slate-50 z-20 shadow-[2px_0_5px_-2px_rgba(0,0,0,0.06)] min-w-[150px] max-w-[170px]">
                      Mesin & Grup
                    </th>
                    <th className="py-2.5 px-2 text-center min-w-[76px]">
                      MHI
                    </th>
                    <th className="py-2.5 px-2 text-center min-w-[70px]">
                      Heating
                    </th>
                    <th className="py-2.5 px-2 text-center min-w-[70px]">
                      Cooling
                    </th>
                    <th className="py-2.5 px-2 text-center min-w-[75px]">
                      Presisi Suhu
                    </th>
                    <th className="py-2.5 px-2.5 text-right min-w-[125px]">
                      Energi Terbuang
                    </th>
                    <th className="py-2.5 px-2.5 text-right min-w-[115px]">
                      Proyeksi 30H
                    </th>
                    <th className="py-2.5 px-2 text-center min-w-[65px]">
                      Aksi
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {filteredMachines.length === 0 ? (
                    <tr>
                      <td colSpan={8} className="py-8 text-center text-slate-400">
                        Tidak ada mesin yang sesuai dengan filter pencarian.
                      </td>
                    </tr>
                  ) : (
                    filteredMachines.map((m) => {
                      const isExpanded = expandedMachineId === m.machine_id;
                      const gStyle = GRADE_STYLES[m.health_grade] || GRADE_STYLES.B;
                      const diagTone = DIAGNOSIS_TONES[m.primary_diagnosis.tone] || DIAGNOSIS_TONES.slate;
                      const DiagIcon = diagTone.icon;

                      return (
                        <React.Fragment key={m.machine_id}>
                          <tr
                            id={`machine-row-${m.machine_id}`}
                            onClick={() => toggleExpand(m.machine_id)}
                            className={`group cursor-pointer transition-colors ${
                              isExpanded ? 'bg-indigo-50/50' : 'hover:bg-slate-50/80'
                            }`}
                          >
                            {/* Mesin & Grup - Sticky Column */}
                            <td className={`py-2.5 px-3 sticky left-0 z-10 shadow-[2px_0_5px_-2px_rgba(0,0,0,0.06)] transition-colors min-w-[150px] max-w-[170px] ${
                              isExpanded ? 'bg-indigo-50' : 'bg-white group-hover:bg-slate-50'
                            }`}>
                              <div className="flex items-center gap-2">
                                <div className="w-7 h-7 rounded-lg bg-indigo-50 text-indigo-700 border border-indigo-200 flex items-center justify-center font-bold text-[11px] shrink-0">
                                  {m.machine_name.substring(0, 3)}
                                </div>
                                <div className="min-w-0 flex-1">
                                  <div className="font-bold text-slate-900 text-xs flex items-center gap-1">
                                    <span className="truncate">{m.machine_name}</span>
                                    {m.health_trend === 'declining' && (
                                      <TrendingDown size={12} className="text-rose-500 shrink-0" title="Kinerja sedang menurun" />
                                    )}
                                    {m.health_trend === 'improving' && (
                                      <TrendingUp size={12} className="text-emerald-500 shrink-0" title="Kinerja membaik" />
                                    )}
                                  </div>
                                  <div className="text-[10px] text-slate-400 truncate" title={`${m.group_name} • ${m.total_processes_day} batch`}>
                                    {formatMachineCaption(m)}
                                  </div>
                                </div>
                              </div>
                            </td>

                            {/* Skor Kesehatan MHI */}
                            <td className="py-2.5 px-2 text-center min-w-[76px]">
                              <div className="inline-flex flex-col items-center">
                                <span className={`px-2 py-0.5 rounded-full font-black text-xs border ${gStyle.badge}`}>
                                  {m.health_score} • {m.health_grade}
                                </span>
                                <span className="text-[9px] text-slate-400 mt-0.5">
                                  Avail: {m.availability_pct}%
                                </span>
                              </div>
                            </td>

                            {/* Heating */}
                            <td className="py-2.5 px-2 text-center min-w-[70px]">
                              <div className="font-semibold text-slate-800 text-xs">
                                {m.avg_delta_heat != null ? (
                                  <span className={m.avg_delta_heat > 15 ? 'text-rose-600 font-bold' : m.avg_delta_heat > 5 ? 'text-amber-600 font-semibold' : 'text-emerald-600 font-semibold'}>
                                    {m.avg_delta_heat > 0 ? `+${m.avg_delta_heat}m` : `${m.avg_delta_heat}m`}
                                  </span>
                                ) : '-'}
                              </div>
                              <div className="text-[10px] text-slate-400">
                                {m.avg_heating_grad ? `${m.avg_heating_grad}°C/m` : '-'}
                              </div>
                            </td>

                            {/* Cooling */}
                            <td className="py-2.5 px-2 text-center min-w-[70px]">
                              <div className="font-semibold text-slate-800 text-xs">
                                {m.avg_delta_cool != null ? (
                                  <span className={m.avg_delta_cool > 15 ? 'text-rose-600 font-bold' : m.avg_delta_cool > 5 ? 'text-amber-600 font-semibold' : 'text-emerald-600 font-semibold'}>
                                    {m.avg_delta_cool > 0 ? `+${m.avg_delta_cool}m` : `${m.avg_delta_cool}m`}
                                  </span>
                                ) : '-'}
                              </div>
                              <div className="text-[10px] text-slate-400">
                                {m.avg_cooling_grad ? `${m.avg_cooling_grad}°C/m` : '-'}
                              </div>
                            </td>

                            {/* Presisi Suhu */}
                            <td className="py-2.5 px-2 text-center min-w-[75px]">
                              <div className="font-semibold text-slate-800 text-xs">
                                {m.avg_delta_temp != null ? (
                                  <span className={Math.abs(m.avg_delta_temp) > 2.5 ? 'text-rose-600 font-bold' : 'text-slate-700'}>
                                    {m.avg_delta_temp > 0 ? `+${m.avg_delta_temp}°C` : `${m.avg_delta_temp}°C`}
                                  </span>
                                ) : '-'}
                              </div>
                              <div className="text-[10px] text-slate-400">
                                {m.temp_overshoot_count > 0 ? (
                                  <span className="text-rose-500 font-bold">{m.temp_overshoot_count}x Over</span>
                                ) : (
                                  <span className="text-emerald-600">Presisi</span>
                                )}
                              </div>
                            </td>

                            {/* Energi Terbuang Aktual */}
                            <td className="py-2.5 px-2.5 text-right min-w-[125px]">
                              <div className="font-bold text-slate-900 text-xs">
                                {formatRp(m.waste_cost_rp)}
                              </div>
                              <div className="text-[10px] text-slate-400 whitespace-nowrap">
                                {numFmt(m.waste_steam_kg, 0)} kg • {numFmt(m.waste_power_kwh, 0)} kWh
                              </div>
                            </td>

                            {/* Proyeksi 30 Hari */}
                            <td className="py-2.5 px-2.5 text-right min-w-[115px]">
                              <div className="font-black text-rose-600 text-xs">
                                {formatRp(m.projected_30d_rp)}
                              </div>
                              <div className="text-[10px] text-slate-400 whitespace-nowrap">
                                {numFmt(m.projected_30d_steam_kg / 1000, 1)} Ton uap/bln
                              </div>
                            </td>

                            {/* Aksi */}
                            <td className="py-2.5 px-2 text-center min-w-[65px]">
                              <button
                                type="button"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  toggleExpand(m.machine_id);
                                }}
                                className={`inline-flex items-center gap-1 px-2 py-1 rounded-lg font-bold text-[11px] transition-colors cursor-pointer ${
                                  isExpanded
                                    ? 'bg-indigo-600 text-white shadow-2xs'
                                    : 'text-indigo-600 hover:text-indigo-800 hover:bg-indigo-50'
                                }`}
                              >
                                <span>{isExpanded ? 'Tutup' : 'Detail'}</span>
                                {isExpanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                              </button>
                            </td>
                          </tr>

                          {/* ══════════════════════════════════════════════════════
                              EXPANDED DRAWER PANEL (BEDAH MENDALAM PER MESIN)
                             ══════════════════════════════════════════════════════ */}
                          {isExpanded && (
                            <tr>
                              <td colSpan={8} className="p-0 bg-slate-50 border-y-2 border-indigo-100 max-w-full">
                                {renderMachineDrawer(m)}
                              </td>
                            </tr>
                          )}
                        </React.Fragment>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>

            {/* Mobile Touch-Optimized Cards View (Phone Viewport) */}
            <div className="block md:hidden divide-y divide-slate-100">
              {filteredMachines.length === 0 ? (
                <div className="py-8 text-center text-slate-400 text-xs">
                  Tidak ada mesin yang sesuai dengan filter pencarian.
                </div>
              ) : (
                filteredMachines.map((m) => {
                  const isExpanded = expandedMachineId === m.machine_id;
                  const gStyle = GRADE_STYLES[m.health_grade] || GRADE_STYLES.B;
                  const diagTone = DIAGNOSIS_TONES[m.primary_diagnosis.tone] || DIAGNOSIS_TONES.slate;
                  const DiagIcon = diagTone.icon;

                  return (
                    <div
                      id={`machine-card-${m.machine_id}`}
                      key={m.machine_id}
                      className={`transition-all ${isExpanded ? 'bg-indigo-50/40' : 'bg-white'}`}
                    >
                      <div
                        onClick={() => toggleExpand(m.machine_id)}
                        className="p-3.5 space-y-2.5 cursor-pointer active:bg-slate-50 transition-colors"
                      >
                        {/* Header: Avatar, Nama Mesin, Trend, Grade & Score */}
                        <div className="flex items-center justify-between gap-2">
                          <div className="flex items-center gap-2.5 min-w-0">
                            <div className="w-9 h-9 rounded-xl bg-indigo-50 text-indigo-700 border border-indigo-200 flex items-center justify-center font-black text-xs shrink-0 shadow-2xs">
                              {m.machine_name.substring(0, 3)}
                            </div>
                            <div className="min-w-0">
                              <div className="font-extrabold text-slate-900 text-xs sm:text-sm flex items-center gap-1.5">
                                <span className="truncate">{m.machine_name}</span>
                                {m.health_trend === 'declining' && (
                                  <TrendingDown size={13} className="text-rose-500 shrink-0" title="Kinerja sedang menurun" />
                                )}
                                {m.health_trend === 'improving' && (
                                  <TrendingUp size={13} className="text-emerald-500 shrink-0" title="Kinerja membaik" />
                                )}
                              </div>
                              <div className="text-[10px] text-slate-400 truncate">
                                {formatMachineCaption(m)}
                              </div>
                            </div>
                          </div>

                          <div className="flex flex-col items-end shrink-0">
                            <span className={`px-2 py-0.5 rounded-full font-black text-xs border ${gStyle.badge}`}>
                              {m.health_score} • {m.health_grade}
                            </span>
                            <span className="text-[9.5px] text-slate-400 mt-0.5 font-medium">
                              Avail: {m.availability_pct}%
                            </span>
                          </div>
                        </div>

                        {/* Phase Chips: Heating, Cooling, Presisi Suhu */}
                        <div className="grid grid-cols-3 gap-1.5 text-center">
                          <div className="bg-slate-50 border border-slate-200/80 rounded-xl p-1.5">
                            <span className="text-[9px] font-bold text-slate-400 uppercase tracking-wider block">Heating</span>
                            <div className="font-bold text-xs mt-0.5">
                              {m.avg_delta_heat != null ? (
                                <span className={m.avg_delta_heat > 15 ? 'text-rose-600 font-extrabold' : m.avg_delta_heat > 5 ? 'text-amber-600 font-bold' : 'text-emerald-600 font-bold'}>
                                  {m.avg_delta_heat > 0 ? `+${m.avg_delta_heat}m` : `${m.avg_delta_heat}m`}
                                </span>
                              ) : '-'}
                            </div>
                            <span className="text-[9px] text-slate-400 block truncate">
                              {m.avg_heat_mins ? `${m.avg_heat_mins}m` : '-'} (Idl {m.ideal_heat_mins || '-'}m)
                            </span>
                          </div>

                          <div className="bg-slate-50 border border-slate-200/80 rounded-xl p-1.5">
                            <span className="text-[9px] font-bold text-slate-400 uppercase tracking-wider block">Cooling</span>
                            <div className="font-bold text-xs mt-0.5">
                              {m.avg_delta_cool != null ? (
                                <span className={m.avg_delta_cool > 10 ? 'text-rose-600 font-extrabold' : m.avg_delta_cool > 5 ? 'text-amber-600 font-bold' : 'text-emerald-600 font-bold'}>
                                  {m.avg_delta_cool > 0 ? `+${m.avg_delta_cool}m` : `${m.avg_delta_cool}m`}
                                </span>
                              ) : '-'}
                            </div>
                            <span className="text-[9px] text-slate-400 block truncate">
                              {m.avg_cool_mins ? `${m.avg_cool_mins}m` : '-'} (Idl {m.ideal_cool_mins || '-'}m)
                            </span>
                          </div>

                          <div className="bg-slate-50 border border-slate-200/80 rounded-xl p-1.5">
                            <span className="text-[9px] font-bold text-slate-400 uppercase tracking-wider block">Presisi Suhu</span>
                            <div className="font-bold text-xs mt-0.5">
                              {m.avg_temp_dev != null ? (
                                <span className={m.avg_temp_dev > 3.0 ? 'text-rose-600 font-extrabold' : m.avg_temp_dev > 1.5 ? 'text-amber-600 font-bold' : 'text-emerald-600 font-bold'}>
                                  ±{m.avg_temp_dev}°C
                                </span>
                              ) : '-'}
                            </div>
                            <span className="text-[9px] text-slate-400 block truncate">
                              Hold Deviasi
                            </span>
                          </div>
                        </div>

                        {/* Financial Metrics Row */}
                        <div className="flex items-center justify-between pt-1 border-t border-slate-100 text-xs">
                          <div>
                            <span className="text-[9.5px] text-slate-400 block">Pemborosan / Batch:</span>
                            <span className="font-extrabold text-rose-600 text-xs">
                              {formatRp(m.avg_waste_rp_batch)}
                            </span>
                          </div>
                          <div className="text-right">
                            <span className="text-[9.5px] text-slate-400 block">Proyeksi 30H:</span>
                            <span className="font-extrabold text-slate-900 text-xs">
                              {formatRp(m.projected_30d_rp)}
                            </span>
                          </div>
                        </div>

                        {/* Diagnosis & Expand Toggle Button */}
                        <div className="flex items-center justify-between pt-1">
                          <div className="flex items-center gap-1.5 text-[11px] text-slate-600 truncate max-w-[75%]">
                            <span className={`p-1 rounded-md ${diagTone.badge} text-[10px] shrink-0`}>
                              <DiagIcon size={12} />
                            </span>
                            <span className="font-semibold truncate">{m.primary_diagnosis.title}</span>
                          </div>
                          <div className="flex items-center gap-1 text-xs font-bold text-indigo-600 shrink-0">
                            <span>{isExpanded ? 'Tutup' : 'Detail'}</span>
                            <span className={`transition-transform duration-200 ${isExpanded ? 'rotate-180' : ''}`}>
                              <ChevronDown size={13} />
                            </span>
                          </div>
                        </div>
                      </div>

                      {/* Expanded Drawer on Mobile */}
                      {isExpanded && (
                        <div className="border-t border-indigo-100 bg-slate-50/80">
                          {renderMachineDrawer(m)}
                        </div>
                      )}
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
