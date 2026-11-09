import React, { useState, useEffect, useMemo, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../lib/api';
import { format } from 'date-fns';

import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip as RechartsTooltip, ResponsiveContainer, LineChart, Line, ReferenceLine,
  ComposedChart, BarChart, Bar, Cell, LabelList, PieChart, Pie, Legend,
} from 'recharts';
import {
  Calendar, Activity, X, Search, AlertTriangle, Gauge, Timer, Zap, Clock,
  ChevronLeft, ChevronRight, RefreshCw, Flame, ArrowRight, Printer, CheckCircle2,
  TrendingDown, TrendingUp, Wind, PowerOff, ShieldAlert, Sparkles, Award,
  DollarSign, Factory, Layers, Filter, Compass, AlertCircle, ArrowUpRight, BarChart3,
  UserCheck, Wrench
} from 'lucide-react';

import LossesBreakdownModal from '../components/LossesBreakdownModal';

// Helper format angka
const num = (v, d = 1) => (v == null || Number.isNaN(+v) ? null : +(+v).toFixed(d));
const formatRp = (val) => {
  if (val == null || Number.isNaN(+val)) return '-';
  return 'Rp ' + Math.round(val).toLocaleString('id-ID');
};

export default function DailyReportDeep() {
  const navigate = useNavigate();

  // Tanggal aktif (06:00 - 06:00)
  const [selectedDate, setSelectedDate] = useState(() => {
    const saved = sessionStorage.getItem('dailyReportDeepDate') || sessionStorage.getItem('dailyReport1Date');
    if (saved) return saved;
    const now = new Date();
    if (now.getHours() < 6) now.setDate(now.getDate() - 1);
    return now.toISOString().split('T')[0];
  });

  useEffect(() => {
    sessionStorage.setItem('dailyReportDeepDate', selectedDate);
    sessionStorage.setItem('dailyReport1Date', selectedDate);
  }, [selectedDate]);

  // Data fetching states
  const [reportData, setReportData] = useState(null);
  const [boilerData, setBoilerData] = useState(null);
  const [dailyAnomalies, setDailyAnomalies] = useState([]);
  const [anomalyStats, setAnomalyStats] = useState(null);

  const [loading, setLoading] = useState(false);
  const [boilerLoading, setBoilerLoading] = useState(false);
  const [error, setError] = useState(null);

  // Filters & Tabs
  const [activeBoardTab, setActiveBoardTab] = useState('operasional'); // 'operasional' | 'energi' | 'finansial' | 'anomali'
  const [selectedShiftFilter, setSelectedShiftFilter] = useState('ALL'); // 'ALL' | 'SHIFT_1' | 'SHIFT_2' | 'SHIFT_3'
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedLossCategory, setSelectedLossCategory] = useState(null);

  // Modal Process Analytics
  const [processAnalyticsDetail, setProcessAnalyticsDetail] = useState(null);
  const [isProcessModalOpen, setIsProcessModalOpen] = useState(false);

  // ── Fetch Data ──────────────────────────────────────────────────────────
  const fetchReport = async (date) => {
    setLoading(true);
    setError(null);
    try {
      const [summaryRes, anomalyRes, boilerRes] = await Promise.allSettled([
        api.get(`/report/daily-summary?date=${date}`),
        api.get(`/anomalies/?date=${date}`),
        api.get(`/report/boiler-summary?date=${date}`)
      ]);

      if (summaryRes.status === 'fulfilled') {
        if (summaryRes.value.data?.error) {
          setError(summaryRes.value.data.error);
          setReportData(null);
        } else {
          setReportData(summaryRes.value.data);
        }
      } else {
        setError('Gagal memuat daily summary.');
        setReportData(null);
      }

      if (anomalyRes.status === 'fulfilled') {
        setDailyAnomalies(anomalyRes.value.data?.data || []);
        setAnomalyStats(anomalyRes.value.data?.summary || null);
      } else {
        setDailyAnomalies([]);
        setAnomalyStats(null);
      }

      if (boilerRes.status === 'fulfilled') {
        setBoilerData(boilerRes.value.data?.error ? null : boilerRes.value.data);
      } else {
        setBoilerData(null);
      }
    } catch (err) {
      console.error('Error fetching deep report:', err);
      setError('Terjadi kendala saat memuat data analitik.');
    } finally {
      setLoading(false);
      setBoilerLoading(false);
    }
  };

  useEffect(() => {
    fetchReport(selectedDate);
  }, [selectedDate]);

  const changeDate = (days) => {
    const d = new Date(selectedDate);
    d.setDate(d.getDate() + days);
    setSelectedDate(d.toISOString().split('T')[0]);
  };

  // ── 1. DEEP SHIFT ANALYSIS ENGINE ──────────────────────────────────────
  // Shift 1: 06:00 - 14:00 (Pagi)
  // Shift 2: 14:00 - 22:00 (Sore)
  // Shift 3: 22:00 - 06:00 (Malam)
  const shiftMetrics = useMemo(() => {
    if (!reportData?.history_groups && !reportData?.efficiency_summary?.machines) return null;

    // Kumpulkan semua item proses
    const allProcesses = [];
    (reportData.efficiency_summary?.machines || []).forEach(m => {
      (m.processes || []).forEach(p => {
        allProcesses.push({
          ...p,
          machine_name: m.machine_name,
          machine_id: m.machine_id,
          group_name: m.group_name
        });
      });
    });

    const initShift = (name, hours) => ({
      name,
      hours,
      batchCount: 0,
      totalDuration: 0,
      totalDelayHeat: 0,
      totalDelayCool: 0,
      totalDelay: 0,
      sumEff: 0,
      processes: [],
      machinesActive: new Set()
    });

    const shifts = {
      SHIFT_1: initShift('Shift 1 (Pagi)', '06:00 - 14:00'),
      SHIFT_2: initShift('Shift 2 (Sore)', '14:00 - 22:00'),
      SHIFT_3: initShift('Shift 3 (Malam)', '22:00 - 06:00')
    };

    allProcesses.forEach(p => {
      const timeStr = p.start_time; // format "HH:MM"
      if (!timeStr || !timeStr.includes(':')) return;
      const [h, m] = timeStr.split(':').map(Number);
      const totalM = h * 60 + m;

      let targetKey = 'SHIFT_3';
      if (totalM >= 360 && totalM < 840) {
        targetKey = 'SHIFT_1'; // 06:00 - 13:59
      } else if (totalM >= 840 && totalM < 1320) {
        targetKey = 'SHIFT_2'; // 14:00 - 21:59
      } else {
        targetKey = 'SHIFT_3'; // 22:00 - 05:59
      }

      const s = shifts[targetKey];
      s.batchCount += 1;
      s.totalDuration += (p.total_duration || 0);
      s.totalDelayHeat += (p.delay_heat || 0);
      s.totalDelayCool += (p.delay_cool || 0);
      s.totalDelay += (p.delay_total || 0);
      s.sumEff += (p.eff_total || 0);
      s.processes.push(p);
      s.machinesActive.add(p.machine_name);
    });

    // Hitung rata-rata
    Object.keys(shifts).forEach(key => {
      const s = shifts[key];
      const count = s.batchCount || 1;
      s.avgDuration = Math.round(s.totalDuration / count);
      s.avgDelayHeat = Math.round(s.totalDelayHeat / count);
      s.avgDelayCool = Math.round(s.totalDelayCool / count);
      s.avgDelayTotal = Math.round(s.totalDelay / count);
      s.avgEff = Number((s.sumEff / count).toFixed(1));
      s.activeMachineCount = s.machinesActive.size;
    });

    // Tentukan shift terbaik berdasarkan efisiensi & delay terendah
    let bestShiftKey = 'SHIFT_1';
    let worstShiftKey = 'SHIFT_3';
    let maxEff = -1;
    let minEff = 999;

    Object.keys(shifts).forEach(k => {
      if (shifts[k].batchCount > 0) {
        if (shifts[k].avgEff > maxEff) {
          maxEff = shifts[k].avgEff;
          bestShiftKey = k;
        }
        if (shifts[k].avgEff < minEff) {
          minEff = shifts[k].avgEff;
          worstShiftKey = k;
        }
      }
    });

    return {
      shifts,
      bestShiftKey,
      worstShiftKey,
      totalBatches: allProcesses.length
    };
  }, [reportData]);

  // ── 2. FINANCIAL WATERFALL LOSS ENGINE ─────────────────────────────────
  const financialWaterfall = useMemo(() => {
    if (!reportData) return null;

    const machines = reportData.efficiency_summary?.machines || [];
    
    // Akumulasi komponen kerugian dari mesin
    let steamLossRp = 0;
    let powerLossRp = 0;
    let powerWbpRp = 0;
    let powerLwbpRp = 0;
    let totalOutputYd = 0;

    machines.forEach(m => {
      steamLossRp += (m.steam_loss_rp || 0);
      powerLossRp += (m.power_loss_rp || 0);
      powerWbpRp += (m.power_wbp_rp || 0);
      powerLwbpRp += (m.power_lwbp_rp || 0);
      totalOutputYd += (m.output_yd || 0);
    });

    // 1. Kerugian Uap (Lapis 1 - Lapis 3)
    const steamLossKg = reportData.losses_summary?.steam_loss_kg || 0;
    
    // 2. Kerugian Listrik Inefisiensi
    const powerLossKwh = reportData.losses_summary?.power_loss_kwh || 0;

    // 3. Penalti Tarif WBP (Waktu Beban Puncak 17:00 - 22:00)
    // Surcharge WBP adalah selisih tarif (misal tarif pengali 1.4x - 1.0x dasar)
    // wbp_multiplier ~ 1.4, jadi porsi surcharge adalah ~(0.4 / 1.4) dari total tagihan WBP
    const wbpSurchargeRp = Math.round(powerWbpRp * (0.4 / 1.4));

    // 4. Opportunity Cost of Delay / Idle Time
    // Overhead rate pabrik per jam nganggur = Rp 65.000 / jam
    const IDLE_OVERHEAD_RATE_PER_HOUR = 65000;
    const timeLossHours = reportData.losses_summary?.time_loss_hours || 0;
    const idleOpportunityLossRp = Math.round(timeLossHours * IDLE_OVERHEAD_RATE_PER_HOUR);

    // Total Kerugian Finansial Harian
    const totalCostOfLossRp = Math.round(steamLossRp + powerLossRp + wbpSurchargeRp + idleOpportunityLossRp);

    // Specific Energy Consumption (SEC)
    const totalSteamKg = reportData.total_steam_usage || 0;
    const totalPowerKwh = reportData.production_summary?.power_kwh || 0;
    const secSteam = totalOutputYd > 0 ? (totalSteamKg / totalOutputYd).toFixed(2) : '-';
    const secPower = totalOutputYd > 0 ? (totalPowerKwh / totalOutputYd).toFixed(3) : '-';

    // Right-First-Time (RFT) Rate & Komposisi Produksi
    // CATATAN: CREAPING BUKAN REWORK! Creaping adalah proses produksi utama (texturing/relaksasi kain).
    // Rework / Perbaikan murni berasal dari other_yd (Top Level, Topping, Cuci Ulang, dll).
    const freshYd = reportData.production_summary?.fresh_yd || 0;
    const creapingYd = reportData.production_summary?.creaping_yd || 0;
    const otherYd = reportData.production_summary?.other_yd || 0;
    const totalProdYd = freshYd + creapingYd + otherYd;

    // Produksi Reguler / Utama = Fresh + Creaping
    const regularProdYd = freshYd + creapingYd;
    const regularPercent = totalProdYd > 0 ? ((regularProdYd / totalProdYd) * 100).toFixed(1) : '-';

    // Rework murni = other_yd (Top Level, Topping, Cuci, dll)
    const reworkYd = otherYd;
    const reworkPercent = totalProdYd > 0 ? ((reworkYd / totalProdYd) * 100).toFixed(1) : '0';

    // Estimasi biaya energi yang terbuang murni untuk Rework (hanya mengalikan 11.300 yd, bukan Creaping)
    const avgEnergyCostPerYd = totalOutputYd > 0 ? (steamLossRp + powerLossRp + powerLwbpRp + powerWbpRp) / totalOutputYd : 250;
    const reworkEnergyWasteRp = Math.round(reworkYd * avgEnergyCostPerYd);

    return {
      steamLossKg,
      steamLossRp,
      powerLossKwh,
      powerLossRp,
      wbpSurchargeRp,
      idleOpportunityLossRp,
      totalCostOfLossRp,
      timeLossHours,
      totalOutputYd,
      secSteam,
      secPower,
      regularPercent,
      regularProdYd,
      freshYd,
      creapingYd,
      reworkYd,
      reworkPercent,
      reworkEnergyWasteRp
    };
  }, [reportData]);

  // ── 3. COINCIDENT STEAM DEMAND & BOILER STARVATION RADAR ──────────────
  const coincidenceRadar = useMemo(() => {
    if (!boilerData?.chart_data) return null;

    const chart = boilerData.chart_data;
    let underPressureMinutes = 0;
    let peakDemandKgH = 0;
    let peakTime = '-';
    const congestionEvents = [];

    chart.forEach(pt => {
      const pr = pt.Steam_Pr || 0;
      const steam = pt.steam_usage || 0;
      
      if (steam > peakDemandKgH) {
        peakDemandKgH = steam;
        peakTime = pt.time;
      }

      // Tekanan boiler di bawah threshold kritis 3.8 bar
      if (pr > 0 && pr < 3.8) {
        underPressureMinutes += 10; // per 10 menit
        if (steam > 6000) {
          congestionEvents.push({
            time: pt.time,
            pressure: pr,
            demand: steam,
            activeMachines: pt.active_machines
          });
        }
      }
    });

    return {
      peakDemandKgH,
      peakTime,
      underPressureMinutes,
      congestionCount: congestionEvents.length,
      sampleCongestions: congestionEvents.slice(0, 4)
    };
  }, [boilerData]);

  // ── 4. PRESCRIPTIVE MORNING BRIEFING ACTION GENERATOR ──────────────────
  const morningBriefingItems = useMemo(() => {
    if (!reportData || !shiftMetrics) return [];

    const items = [];
    const worstShift = shiftMetrics.shifts[shiftMetrics.worstShiftKey];
    const bestShift = shiftMetrics.shifts[shiftMetrics.bestShiftKey];

    // 1. Preskripsi Shift Gap
    if (worstShift && bestShift && worstShift.avgDelayTotal > bestShift.avgDelayTotal + 15) {
      items.push({
        id: 'shift_gap',
        category: 'OPERASIONAL & SHIFT',
        priority: 'HIGH',
        color: 'red',
        icon: <UserCheck className="w-5 h-5 text-red-600" />,
        title: `Kesenjangan Kinerja: ${worstShift.name} Mengalami Delay +${worstShift.avgDelayTotal - bestShift.avgDelayTotal}m/batch`,
        detail: `Rata-rata delay total ${worstShift.name} mencapai ${worstShift.avgDelayTotal} menit (vs ${bestShift.name} ${bestShift.avgDelayTotal} menit). Disiplin changeover & pemantauan malam perlu di-briefing pagi ini.`,
        targetDept: 'SPV Produksi / Shift Manager'
      });
    }

    // 2. Preskripsi Suplai Uap & Bottleneck Coincidence
    if (coincidenceRadar && coincidenceRadar.underPressureMinutes >= 20) {
      items.push({
        id: 'boiler_bottleneck',
        category: 'PPIC & ENERGI',
        priority: 'HIGH',
        color: 'orange',
        icon: <Flame className="w-5 h-5 text-orange-600" />,
        title: `Pola Benturan Pemanasan: Boiler Drop <3.8 bar Selama ${coincidenceRadar.underPressureMinutes} Menit`,
        detail: `Terjadi lonjakan coincident peak ${Math.round(coincidenceRadar.peakDemandKgH).toLocaleString()} kg/jam sekitar pk ${coincidenceRadar.peakTime}. Terapkan jeda (stagger start) minimal 20 menit antar-mesin jet berkapasitas besar (JR 11, JR 12, JD 16).`,
        targetDept: 'PPIC & Operator Jet'
      });
    }

    // 3. Preskripsi Mesin Bermasalah (Heat Exchanger / Solenoid)
    const machines = (reportData.efficiency_summary?.machines || []);
    const worstHeatingMachine = [...machines].sort((a, b) => (b.delay_heat_mins || 0) - (a.delay_heat_mins || 0))[0];
    if (worstHeatingMachine && (worstHeatingMachine.delay_heat_mins || 0) > 45) {
      items.push({
        id: 'he_degradation',
        category: 'MAINTENANCE & MEKANIK',
        priority: 'MEDIUM',
        color: 'blue',
        icon: <Wrench className="w-5 h-5 text-blue-600" />,
        title: `Indikasi Kerak Heat Exchanger: Mesin ${worstHeatingMachine.machine_name} (+${Math.round(worstHeatingMachine.delay_heat_mins)}m Delay Heating)`,
        detail: `Laju pemanasan melambat signifikan melampaui toleransi standar program. Jadwalkan inspeksi steam trap dan descaling heat exchanger pada jadwal cuci mesin berikutnya.`,
        targetDept: 'Tim Mekanik / Maintenance'
      });
    }

    // 4. Preskripsi Penghematan Listrik WBP
    if (financialWaterfall && financialWaterfall.wbpSurchargeRp > 800000) {
      items.push({
        id: 'wbp_shaving',
        category: 'EFISIENSI BIAYA LISTRIK',
        priority: 'MEDIUM',
        color: 'purple',
        icon: <Zap className="w-5 h-5 text-purple-600" />,
        title: `Beban Puncak Listrik: Tagihan WBP Menyerap ${formatRp(financialWaterfall.wbpSurchargeRp)} Ekstra`,
        detail: `Penggunaan motor sirkulasi berat pada pk 17:00–22:00 terkena pengali tarif 1.4x PLN. Geser proses scouring / pre-treatment ke sebelum jam 17:00 atau setelah jam 22:00 untuk memangkas penalti ini.`,
        targetDept: 'PPIC / Ka. Shift 2'
      });
    }

    return items;
  }, [reportData, shiftMetrics, coincidenceRadar, financialWaterfall]);

  // ── 5. FILTERED TABLE MACHINE ROWS ─────────────────────────────────────
  const machineRows = useMemo(() => {
    if (!reportData?.efficiency_summary?.machines) return [];
    let list = [...reportData.efficiency_summary.machines];

    // Filter berdasarkan shift jika dipilih
    if (selectedShiftFilter !== 'ALL' && shiftMetrics) {
      const activeSet = shiftMetrics.shifts[selectedShiftFilter]?.machinesActive || new Set();
      list = list.filter(m => activeSet.has(m.machine_name));
    }

    // Filter berdasarkan search query
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      list = list.filter(m => 
        m.machine_name.toLowerCase().includes(q) ||
        (m.group_name && m.group_name.toLowerCase().includes(q))
      );
    }

    return list;
  }, [reportData, selectedShiftFilter, searchQuery, shiftMetrics]);

  // ── Actions ────────────────────────────────────────────────────────────
  const openProcessAnalyticsModal = async (processId) => {
    setIsProcessModalOpen(true);
    setProcessAnalyticsDetail(null);
    try {
      const res = await api.get(`/report/process/${processId}/analytics`);
      setProcessAnalyticsDetail(res.data);
    } catch (err) {
      console.error('Gagal mengambil process analytics:', err);
    }
  };

  const openMachineAnalytics = (machineId) => {
    navigate(`/machine-daily-deep-analytics/${machineId}/${selectedDate}`);
  };

  return (
    <div className="h-full overflow-y-auto bg-slate-50/60 pb-16 font-sans text-slate-800">
      
      {/* 🚀 STICKY COMPACT TOPBAR 🚀 */}
      <header className="sticky top-0 z-30 bg-white/95 backdrop-blur-md border-b border-slate-200 px-3 sm:px-8 py-2.5 sm:py-3 flex flex-wrap items-center justify-between gap-3 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-indigo-600 text-white flex items-center justify-center shadow-md shadow-indigo-100">
            <Compass className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-base sm:text-lg font-extrabold text-slate-900 tracking-tight">
                Daily Report V2 <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 font-bold border border-indigo-200">Deep Analytics</span>
              </h1>
              <span className="hidden md:inline-flex text-[11px] font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                ● Live PINN + IoT Synced
              </span>
            </div>
            <p className="text-xs text-slate-500 font-medium">
              Siklus 24 Jam: {format(new Date(selectedDate), 'EEEE, dd MMMM yyyy')} (06:00 - 06:00 WIB)
            </p>
          </div>
        </div>

        {/* Action Controls & Navigation */}
        <div className="flex items-center justify-between w-full sm:w-auto gap-2 sm:gap-3 flex-wrap sm:flex-nowrap">
          {/* Switcher Button back to standard daily report */}
          <button
            onClick={() => navigate('/daily-report')}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-slate-600 bg-slate-100 hover:bg-slate-200 rounded-lg transition-colors border border-slate-200"
            title="Kembali ke format Daily Report standar"
          >
            <ArrowRight className="w-3.5 h-3.5 rotate-180" />
            <span className="hidden sm:inline">Format Standar</span>
          </button>

          {/* Date Navigator */}
          <div className="flex items-center bg-slate-100 rounded-lg p-1 border border-slate-200 shadow-inner">
            <button
              onClick={() => changeDate(-1)}
              className="p-1 sm:p-1.5 text-slate-600 hover:text-slate-900 hover:bg-white rounded-md transition-all"
              title="Hari Sebelumnya"
            >
              <ChevronLeft size={16} />
            </button>
            <input
              type="date"
              className="bg-transparent border-none text-xs sm:text-sm font-bold text-slate-700 focus:ring-0 px-2 cursor-pointer outline-none w-[120px] sm:w-[130px] text-center"
              value={selectedDate}
              onChange={(e) => setSelectedDate(e.target.value)}
              max={format(new Date(), 'yyyy-MM-dd')}
            />
            <button
              onClick={() => changeDate(1)}
              className="p-1 sm:p-1.5 text-slate-600 hover:text-slate-900 hover:bg-white rounded-md transition-all"
              title="Hari Berikutnya"
            >
              <ChevronRight size={16} />
            </button>
          </div>

          <button
            onClick={() => fetchReport(selectedDate)}
            className="p-2 text-slate-600 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors border border-slate-200 bg-white shadow-sm"
            title="Muat ulang seluruh analitik"
          >
            <RefreshCw size={16} className={loading || boilerLoading ? 'animate-spin text-indigo-600' : ''} />
          </button>
        </div>
      </header>

      {/* ── MAIN CONTENT CONTAINER ───────────────────────────────────────── */}
      <main className="max-w-7xl mx-auto px-3 sm:px-8 py-4 sm:py-6 space-y-4 sm:space-y-6 animate-fade-in">
        
        {loading && !reportData ? (
          <div className="space-y-4 sm:space-y-6">
            <div className="h-28 rounded-2xl skeleton-shimmer" />
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="h-44 rounded-2xl skeleton-shimmer" />
              <div className="h-44 rounded-2xl skeleton-shimmer" />
              <div className="h-44 rounded-2xl skeleton-shimmer" />
            </div>
            <div className="h-72 rounded-2xl skeleton-shimmer" />
          </div>
        ) : error ? (
          <div className="bg-red-50 border-l-4 border-red-500 p-5 rounded-2xl shadow-sm flex items-start gap-3">
            <AlertCircle className="w-6 h-6 text-red-600 shrink-0 mt-0.5" />
            <div>
              <h3 className="text-sm font-bold text-red-900">Kendala Memuat Laporan Analitik</h3>
              <p className="text-xs text-red-700 mt-1">{error}</p>
            </div>
          </div>
        ) : !reportData ? (
          <div className="text-center py-16 text-slate-400 font-medium">Data laporan tidak ditemukan untuk tanggal ini.</div>
        ) : (
          <>
            {/* ═══════════════════════════════════════════════════════════════ */}
            {/* 1. EXECUTIVE FINANCIAL WATERFALL & HEADLINE METRICS           */}
            {/* ═══════════════════════════════════════════════════════════════ */}
            <section className="space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <div>
                  <h2 className="text-sm font-extrabold text-slate-900 uppercase tracking-wider flex items-center gap-2">
                    <DollarSign className="w-4 h-4 text-emerald-600" />
                    Kuantifikasi Kerugian Finansial & Efisiensi Energi
                  </h2>
                  <p className="text-xs text-slate-500">
                    Dekomposisi kebocoran biaya riil dari uap PINN, inefisiensi motor listrik, dan opportunity loss
                  </p>
                </div>
              </div>

              {/* 4 Kartu KPI Eksekutif */}
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
                {/* Total Cost of Loss */}
                <div className="bg-white rounded-2xl border border-red-100 p-4 shadow-sm relative overflow-hidden flex flex-col justify-between">
                  <div className="absolute top-0 right-0 w-24 h-24 bg-red-50 rounded-full blur-2xl -mr-6 -mt-6 pointer-events-none" />
                  <div>
                    <div className="flex items-center justify-between text-xs font-bold text-slate-400 uppercase tracking-wider">
                      <span>Total Biaya Kerugian</span>
                      <TrendingDown className="w-4 h-4 text-red-500" />
                    </div>
                    <div className="text-xl sm:text-2xl font-black text-red-600 mt-2">
                      {financialWaterfall ? formatRp(financialWaterfall.totalCostOfLossRp) : '-'}
                    </div>
                  </div>
                  <div className="mt-3 pt-2 border-t border-slate-100 flex items-center justify-between text-[11px] text-slate-500 font-medium">
                    <span>Uap: {financialWaterfall ? formatRp(financialWaterfall.steamLossRp) : '-'}</span>
                    <span>Listrik: {financialWaterfall ? formatRp(financialWaterfall.powerLossRp) : '-'}</span>
                  </div>
                </div>

                {/* Plant OEE */}
                <div className="bg-white rounded-2xl border border-indigo-100 p-4 shadow-sm relative overflow-hidden flex flex-col justify-between">
                  <div className="absolute top-0 right-0 w-24 h-24 bg-indigo-50 rounded-full blur-2xl -mr-6 -mt-6 pointer-events-none" />
                  <div>
                    <div className="flex items-center justify-between text-xs font-bold text-slate-400 uppercase tracking-wider">
                      <span>Plant OEE (World-Class)</span>
                      <Gauge className="w-4 h-4 text-indigo-500" />
                    </div>
                    <div className="text-xl sm:text-2xl font-black text-slate-800 mt-2">
                      {reportData.oee_lite?.combined != null ? `${reportData.oee_lite.combined}%` : '-'}
                      <span className="text-xs font-normal text-slate-400 ml-1.5">/ Target 85%</span>
                    </div>
                  </div>
                  <div className="mt-3 pt-2 border-t border-slate-100 flex items-center justify-between text-[11px] text-slate-500 font-medium">
                    <span>Avail: {reportData.oee_lite?.availability}%</span>
                    <span>Perf: {reportData.oee_lite?.performance}%</span>
                  </div>
                </div>

                {/* Right-First-Time (RFT) / Komposisi Produksi */}
                <div className="bg-white rounded-2xl border border-emerald-100 p-4 shadow-sm relative overflow-hidden flex flex-col justify-between">
                  <div className="absolute top-0 right-0 w-24 h-24 bg-emerald-50 rounded-full blur-2xl -mr-6 -mt-6 pointer-events-none" />
                  <div>
                    <div className="flex items-center justify-between text-xs font-bold text-slate-400 uppercase tracking-wider">
                      <span>Produksi Utama (RFT)</span>
                      <Award className="w-4 h-4 text-emerald-500" />
                    </div>
                    <div className="text-xl sm:text-2xl font-black text-emerald-700 mt-2">
                      {financialWaterfall ? `${financialWaterfall.regularPercent}%` : '-'}
                      <span className="text-xs font-semibold text-slate-500 ml-1.5">
                        ({financialWaterfall ? `${(financialWaterfall.regularProdYd / 1000).toFixed(1)}k yd` : '-'})
                      </span>
                    </div>
                    <div className="text-[10px] text-slate-500 mt-1 font-medium flex flex-wrap items-center gap-x-1.5">
                      <span>Fresh: <strong className="text-slate-700">{financialWaterfall ? `${financialWaterfall.freshYd.toLocaleString('id-ID')} yd` : '-'}</strong></span>
                      <span className="text-slate-300">•</span>
                      <span>Creaping: <strong className="text-slate-700">{financialWaterfall ? `${financialWaterfall.creapingYd.toLocaleString('id-ID')} yd` : '-'}</strong></span>
                    </div>
                  </div>
                  <div className="mt-3 pt-2 border-t border-slate-100 flex flex-wrap items-center justify-between gap-1 text-[11px] text-slate-600 font-medium">
                    <span className="text-red-600 font-bold" title="Proses Perbaikan / Rework murni (Top Level, Topping, Cuci Ulang)">
                      Rework: {financialWaterfall ? `${financialWaterfall.reworkYd.toLocaleString()} yd (${financialWaterfall.reworkPercent}%)` : '-'}
                    </span>
                    <span className="text-amber-600 font-bold" title="Estimasi biaya energi terbuang untuk proses perbaikan/rework">
                      -{financialWaterfall ? formatRp(financialWaterfall.reworkEnergyWasteRp) : '-'}
                    </span>
                  </div>
                </div>

                {/* Specific Energy Consumption (SEC) */}
                <div className="bg-white rounded-2xl border border-amber-100 p-4 shadow-sm relative overflow-hidden flex flex-col justify-between">
                  <div className="absolute top-0 right-0 w-24 h-24 bg-amber-50 rounded-full blur-2xl -mr-6 -mt-6 pointer-events-none" />
                  <div>
                    <div className="flex items-center justify-between text-xs font-bold text-slate-400 uppercase tracking-wider">
                      <span>Specific Energy (SEC)</span>
                      <Zap className="w-4 h-4 text-amber-500" />
                    </div>
                    <div className="text-xl sm:text-2xl font-black text-slate-800 mt-2">
                      {financialWaterfall ? `${financialWaterfall.secSteam}` : '-'}
                      <span className="text-xs font-normal text-slate-400 ml-1">kg uap/yd</span>
                    </div>
                  </div>
                  <div className="mt-3 pt-2 border-t border-slate-100 flex items-center justify-between text-[11px] text-slate-500 font-medium">
                    <span>Listrik: {financialWaterfall ? `${financialWaterfall.secPower} kWh/yd` : '-'}</span>
                    <span>Total: {financialWaterfall ? `${financialWaterfall.totalOutputYd.toLocaleString()} yd` : '-'}</span>
                  </div>
                </div>
              </div>

              {/* Waterfall Cards Breakdown */}
              {financialWaterfall && (
                <div className="bg-white rounded-2xl border border-slate-200 p-4 sm:p-5 shadow-sm">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="text-xs font-bold text-slate-700 uppercase tracking-wider">
                      Rincian Dekomposisi Kerugian Finansial Harian
                    </h3>
                    <span className="text-[11px] text-slate-400">Total Loss: {formatRp(financialWaterfall.totalCostOfLossRp)}</span>
                  </div>
                  
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    {/* 1. Loss Uap PINN */}
                    <div 
                      onClick={() => setSelectedLossCategory('steam_loss')}
                      className="p-3 bg-red-50/70 border border-red-200 rounded-xl cursor-pointer hover:bg-red-100/70 transition-all group"
                    >
                      <div className="flex items-center justify-between text-xs font-bold text-red-900 mb-1">
                        <span className="flex items-center gap-1.5"><Flame className="w-3.5 h-3.5 text-red-600" /> Kebocoran Uap</span>
                        <ArrowUpRight className="w-3.5 h-3.5 opacity-0 group-hover:opacity-100 transition-opacity" />
                      </div>
                      <div className="text-base sm:text-lg font-black text-red-600 truncate">{formatRp(financialWaterfall.steamLossRp)}</div>
                      <div className="text-[11px] text-red-700 mt-0.5">
                        +{financialWaterfall.steamLossKg.toLocaleString()} kg uap terbuang
                      </div>
                    </div>

                    {/* 2. Loss Listrik Inefisiensi */}
                    <div 
                      onClick={() => setSelectedLossCategory('power_loss')}
                      className="p-3 bg-amber-50/70 border border-amber-200 rounded-xl cursor-pointer hover:bg-amber-100/70 transition-all group"
                    >
                      <div className="flex items-center justify-between text-xs font-bold text-amber-900 mb-1">
                        <span className="flex items-center gap-1.5"><Zap className="w-3.5 h-3.5 text-amber-600" /> Inefisiensi Motor</span>
                        <ArrowUpRight className="w-3.5 h-3.5 opacity-0 group-hover:opacity-100 transition-opacity" />
                      </div>
                      <div className="text-base sm:text-lg font-black text-amber-600 truncate">{formatRp(financialWaterfall.powerLossRp)}</div>
                      <div className="text-[11px] text-amber-700 mt-0.5">
                        +{financialWaterfall.powerLossKwh.toLocaleString()} kWh loss
                      </div>
                    </div>

                    {/* 3. WBP Surcharge */}
                    <div className="p-3 bg-purple-50/70 border border-purple-200 rounded-xl">
                      <div className="flex items-center justify-between text-xs font-bold text-purple-900 mb-1">
                        <span className="flex items-center gap-1.5"><Clock className="w-3.5 h-3.5 text-purple-600" /> Penalti Jam WBP</span>
                        <span className="text-[10px] bg-purple-200 text-purple-800 px-1.5 py-0.2 rounded font-bold">17-22</span>
                      </div>
                      <div className="text-base sm:text-lg font-black text-purple-600 truncate">{formatRp(financialWaterfall.wbpSurchargeRp)}</div>
                      <div className="text-[11px] text-purple-700 mt-0.5">
                        Beban ekstra pengali 1.4x PLN
                      </div>
                    </div>

                    {/* 4. Opportunity Cost of Delay */}
                    <div 
                      onClick={() => setSelectedLossCategory('time_loss')}
                      className="p-3 bg-slate-100 border border-slate-300 rounded-xl cursor-pointer hover:bg-slate-200 transition-all group"
                    >
                      <div className="flex items-center justify-between text-xs font-bold text-slate-800 mb-1">
                        <span className="flex items-center gap-1.5"><Timer className="w-3.5 h-3.5 text-slate-600" /> Opportunity Cost</span>
                        <ArrowUpRight className="w-3.5 h-3.5 opacity-0 group-hover:opacity-100 transition-opacity" />
                      </div>
                      <div className="text-base sm:text-lg font-black text-slate-700 truncate">{formatRp(financialWaterfall.idleOpportunityLossRp)}</div>
                      <div className="text-[11px] text-slate-600 mt-0.5">
                        {financialWaterfall.timeLossHours} jam mesin tertahan
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </section>


            {/* ═══════════════════════════════════════════════════════════════ */}
            {/* 2. SHIFT ACCOUNTABILITY MATRIX (Shift 1 vs Shift 2 vs Shift 3) */}
            {/* ═══════════════════════════════════════════════════════════════ */}
            <section className="bg-white rounded-2xl border border-slate-200 p-4 sm:p-6 shadow-sm space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div>
                  <h2 className="text-sm font-extrabold text-slate-900 uppercase tracking-wider flex items-center gap-2">
                    <Factory className="w-4 h-4 text-indigo-600" />
                    Matriks Akuntabilitas Kinerja Antar-Shift (Regu Kerja)
                  </h2>
                  <p className="text-xs text-slate-500">
                    Membandingkan kedisiplinan durasi siklus, delay pemanasan, dan efisiensi energi per 8 jam
                  </p>
                </div>

                {/* Filter Selector */}
                <div className="flex items-center gap-1.5 bg-slate-100 p-1 rounded-xl text-xs font-bold text-slate-600 overflow-x-auto max-w-full self-start sm:self-auto shrink-0">
                  {['ALL', 'SHIFT_1', 'SHIFT_2', 'SHIFT_3'].map(mode => (
                    <button
                      key={mode}
                      onClick={() => setSelectedShiftFilter(mode)}
                      className={`px-3 py-1.5 rounded-lg transition-all ${
                        selectedShiftFilter === mode
                          ? 'bg-white text-indigo-700 shadow-sm border border-slate-200'
                          : 'hover:text-slate-900'
                      }`}
                    >
                      {mode === 'ALL' ? 'Semua Shift' : mode.replace('_', ' ')}
                    </button>
                  ))}
                </div>
              </div>

              {shiftMetrics ? (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  {['SHIFT_1', 'SHIFT_2', 'SHIFT_3'].map((key) => {
                    const shift = shiftMetrics.shifts[key];
                    const isBest = shiftMetrics.bestShiftKey === key;
                    const isWorst = shiftMetrics.worstShiftKey === key && shift.batchCount > 0;

                    return (
                      <div
                        key={key}
                        className={`p-4 rounded-xl border transition-all ${
                          isBest
                            ? 'bg-emerald-50/40 border-emerald-300 ring-1 ring-emerald-200'
                            : isWorst
                            ? 'bg-red-50/40 border-red-200'
                            : 'bg-slate-50/50 border-slate-200'
                        }`}
                      >
                        <div className="flex items-center justify-between pb-2 border-b border-slate-200/80">
                          <div>
                            <span className="text-xs font-bold text-slate-500 block">{shift.hours}</span>
                            <h3 className="text-sm font-black text-slate-900">{shift.name}</h3>
                          </div>
                          {isBest && (
                            <span className="inline-flex items-center gap-1 text-[10px] font-extrabold text-emerald-800 bg-emerald-100 px-2 py-0.5 rounded-full border border-emerald-300">
                              🏆 Shift Terbaik
                            </span>
                          )}
                          {isWorst && (
                            <span className="inline-flex items-center gap-1 text-[10px] font-extrabold text-red-800 bg-red-100 px-2 py-0.5 rounded-full border border-red-300">
                              ⚠️ Perlu Evaluasi
                            </span>
                          )}
                        </div>

                        <div className="grid grid-cols-2 gap-3 mt-3">
                          <div>
                            <span className="text-[11px] text-slate-500 block">Total Proses</span>
                            <span className="text-base font-bold text-slate-800">{shift.batchCount} batch</span>
                          </div>
                          <div>
                            <span className="text-[11px] text-slate-500 block">Rata-rata Efisiensi</span>
                            <span className={`text-base font-bold ${shift.avgEff >= 75 ? 'text-emerald-700' : shift.avgEff >= 60 ? 'text-amber-600' : 'text-red-600'}`}>
                              {shift.avgEff}%
                            </span>
                          </div>
                          <div>
                            <span className="text-[11px] text-slate-500 block">Rata-rata Delay Total</span>
                            <span className={`text-sm font-bold ${shift.avgDelayTotal > 30 ? 'text-red-600' : 'text-slate-700'}`}>
                              +{shift.avgDelayTotal} menit/batch
                            </span>
                          </div>
                          <div>
                            <span className="text-[11px] text-slate-500 block">Mesin Beroperasi</span>
                            <span className="text-sm font-bold text-slate-700">{shift.activeMachineCount} mesin</span>
                          </div>
                        </div>

                        <div className="mt-3 pt-2.5 border-t border-slate-200/70 flex items-center justify-between text-[11px] text-slate-500">
                          <span>Delay Pemanasan: <b>+{shift.avgDelayHeat}m</b></span>
                          <span>Delay Pendinginan: <b>+{shift.avgDelayCool}m</b></span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="text-center py-6 text-slate-400 text-xs">Menghitung performa shift...</div>
              )}
            </section>


            {/* ═══════════════════════════════════════════════════════════════ */}
            {/* 3. SYNCHRONIZED COINCIDENCE STEAM DEMAND & BOILER RADAR       */}
            {/* ═══════════════════════════════════════════════════════════════ */}
            <section className="bg-white rounded-2xl border border-slate-200 p-4 sm:p-6 shadow-sm space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <div>
                  <h2 className="text-sm font-extrabold text-slate-900 uppercase tracking-wider flex items-center gap-2">
                    <Flame className="w-4 h-4 text-orange-600" />
                    Radar Dinamika Beban Serentak & Tekanan Boiler (24 Jam)
                  </h2>
                  <p className="text-xs text-slate-500">
                    Korelasi langsung antara lonjakan permintaan uap mesin jet dengan penurunan tekanan boiler (&lt; 3.8 bar)
                  </p>
                </div>

                {coincidenceRadar && (
                  <div className="flex flex-wrap items-center gap-2 sm:gap-3 text-xs self-start sm:self-auto bg-slate-50 px-2.5 py-1.5 rounded-xl border border-slate-200">
                    <span>Peak Demand: <b className="text-orange-600">{Math.round(coincidenceRadar.peakDemandKgH).toLocaleString()} kg/j</b></span>
                    <span className="text-slate-300">|</span>
                    <span>Drop Tekanan: <b className={coincidenceRadar.underPressureMinutes > 0 ? 'text-red-600 font-bold' : 'text-emerald-600'}>{coincidenceRadar.underPressureMinutes} menit</b></span>
                  </div>
                )}
              </div>

              {/* Chart Coincidence */}
              <div className="h-[220px] sm:h-[280px] w-full">
                {boilerData?.chart_data ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart data={boilerData.chart_data} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                      <XAxis dataKey="time" minTickGap={30} tick={{ fontSize: 11, fill: '#64748b' }} axisLine={false} tickLine={false} />
                      
                      {/* Left Axis: Steam Usage (kg/h) */}
                      <YAxis yAxisId="left" tick={{ fontSize: 11, fill: '#3b82f6' }} axisLine={false} tickLine={false} />
                      
                      {/* Right Axis: Steam Pressure (bar) */}
                      <YAxis yAxisId="right" orientation="right" domain={[0, 8]} tick={{ fontSize: 11, fill: '#f59e0b' }} axisLine={false} tickLine={false} />
                      
                      <RechartsTooltip
                        contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 10px 15px -3px rgb(0 0 0 / 0.1)', fontSize: '12px' }}
                      />

                      {/* Area 1: Total Steam Demand */}
                      <Area yAxisId="left" type="monotone" dataKey="steam_usage" stroke="#60a5fa" fill="#bfdbfe" fillOpacity={0.4} name="Beban Uap Total (kg/j)" />
                      
                      {/* Area 2: Jet Machines Demand */}
                      <Area yAxisId="left" type="monotone" dataKey="usage_jet" stroke="#3b82f6" fill="#93c5fd" fillOpacity={0.6} name="Beban Uap Mesin Jet (kg/j)" />

                      {/* Line: Boiler Pressure */}
                      <Line yAxisId="right" type="monotone" dataKey="Steam_Pr" stroke="#f59e0b" strokeWidth={2.5} dot={false} name="Tekanan Boiler (bar)" />

                      {/* Reference line threshold 3.8 bar */}
                      <ReferenceLine yAxisId="right" y={3.8} stroke="#ef4444" strokeDasharray="4 4" label={{ value: 'Ambang Kritis (3.8 bar)', fill: '#ef4444', fontSize: 10, position: 'insideTopLeft' }} />
                    </ComposedChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="h-full flex items-center justify-center text-slate-400 text-xs">Data dinamika uap belum tersedia</div>
                )}
              </div>

              {/* Botol Leher (Bottleneck) Insights */}
              {coincidenceRadar && coincidenceRadar.underPressureMinutes > 0 && (
                <div className="bg-amber-50/70 border border-amber-200 rounded-xl p-3.5 flex items-start gap-3 text-xs">
                  <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
                  <div>
                    <span className="font-bold text-amber-900 block">Deteksi Bottleneck Uap Terjadi di Jam Sibuk:</span>
                    <p className="text-amber-800 mt-0.5">
                      Terdapat akumulasi <b>{coincidenceRadar.underPressureMinutes} menit</b> di mana tekanan uap turun ke bawah 3.8 bar akibat beban pemanasan serentak mesin jet mencapai puncak ({Math.round(coincidenceRadar.peakDemandKgH).toLocaleString()} kg/j pada pk {coincidenceRadar.peakTime}). Seluruh mesin yang memulai proses di jendela waktu ini otomatis mengalami perlambatan laju pemanasan (+15 s/d +30 menit delay).
                    </p>
                  </div>
                </div>
              )}
            </section>


            {/* ═══════════════════════════════════════════════════════════════ */}
            {/* 4. PRESCRIPTIVE MORNING BRIEFING ACTION ITEMS                 */}
            {/* ═══════════════════════════════════════════════════════════════ */}
            <section className="bg-gradient-to-br from-indigo-900 via-slate-900 to-indigo-950 rounded-2xl p-4 sm:p-6 text-white shadow-xl space-y-3 sm:space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <div>
                  <div className="flex items-center gap-2">
                    <Sparkles className="w-5 h-5 text-indigo-400" />
                    <h2 className="text-sm font-extrabold uppercase tracking-wider text-indigo-200">
                      Prescriptive Action Items (Agenda Briefing Pagi Operasional)
                    </h2>
                  </div>
                  <p className="text-xs text-indigo-300 mt-0.5">
                    Rekomendasi tindakan preskriptif otomatis yang disintesis dari anomali & deviasi data harian
                  </p>
                </div>
                <span className="text-[11px] font-bold bg-indigo-800/60 text-indigo-200 px-3 py-1 rounded-full border border-indigo-700/60">
                  AI-Assisted Diagnostics
                </span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
                {morningBriefingItems.length > 0 ? (
                  morningBriefingItems.map(item => (
                    <div
                      key={item.id}
                      className="bg-white/10 backdrop-blur-md rounded-xl p-4 border border-white/15 flex flex-col justify-between hover:bg-white/15 transition-all"
                    >
                      <div>
                        <div className="flex items-center justify-between text-[11px] mb-1.5">
                          <span className="font-bold text-indigo-300 uppercase tracking-wider flex items-center gap-1.5">
                            {item.category}
                          </span>
                          <span className={`px-2 py-0.5 rounded font-extrabold text-[10px] ${
                            item.priority === 'HIGH' ? 'bg-red-500/80 text-white' : 'bg-amber-500/80 text-white'
                          }`}>
                            {item.priority}
                          </span>
                        </div>
                        <h4 className="text-sm font-bold text-white leading-snug">{item.title}</h4>
                        <p className="text-xs text-slate-300 mt-1.5 leading-relaxed">{item.detail}</p>
                      </div>

                      <div className="mt-3 pt-2.5 border-t border-white/10 flex items-center justify-between text-[11px] text-indigo-200">
                        <span>Penanggung Jawab:</span>
                        <b className="text-white">{item.targetDept}</b>
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="col-span-2 text-center py-6 text-indigo-300 text-xs">
                    Semua parameter operasi berjalan normal dalam batas toleransi standar. Tidak ada tindakan darurat yang mendesak.
                  </div>
                )}
              </div>
            </section>


            {/* ═══════════════════════════════════════════════════════════════ */}
            {/* 5. INTERACTIVE MASTER MACHINE MATRIX (MULTI-TAB BOARD)         */}
            {/* ═══════════════════════════════════════════════════════════════ */}
            <section className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden space-y-0">
              
              {/* Header Board & Search */}
              <div className="p-4 sm:p-5 border-b border-slate-200 flex flex-col md:flex-row md:items-center justify-between gap-3 bg-slate-50/50">
                <div>
                  <h2 className="text-sm font-extrabold text-slate-900 uppercase tracking-wider flex items-center gap-2">
                    <Layers className="w-4 h-4 text-indigo-600" />
                    Papan Master Analitik Seluruh Mesin ({machineRows.length} Mesin)
                  </h2>
                  <p className="text-xs text-slate-500">
                    Beralih tab untuk melihat aspek operasional, fisika PINN, kerugian finansial, atau diagnosa anomali
                  </p>
                </div>

                <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2 sm:gap-2.5 w-full md:w-auto">
                  {/* Search box */}
                  <div className="relative">
                    <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
                    <input
                      type="text"
                      placeholder="Cari mesin / grup..."
                      className="pl-8 pr-3 py-1.5 bg-white border border-slate-200 rounded-lg text-xs focus:ring-1 focus:ring-indigo-500 outline-none w-full sm:w-52"
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                    />
                  </div>

                  {/* Multi-Tab Selector */}
                  <div className="flex bg-slate-200/80 p-0.5 rounded-lg text-xs font-semibold text-slate-600 overflow-x-auto max-w-full shrink-0">
                    <button
                      onClick={() => setActiveBoardTab('operasional')}
                      className={`px-3 py-1.5 rounded-md transition-all whitespace-nowrap ${
                        activeBoardTab === 'operasional' ? 'bg-white text-indigo-700 font-bold shadow-sm' : 'hover:text-slate-900'
                      }`}
                    >
                      Operasional
                    </button>
                    <button
                      onClick={() => setActiveBoardTab('energi')}
                      className={`px-3 py-1.5 rounded-md transition-all whitespace-nowrap ${
                        activeBoardTab === 'energi' ? 'bg-white text-indigo-700 font-bold shadow-sm' : 'hover:text-slate-900'
                      }`}
                    >
                      Energi (PINN)
                    </button>
                    <button
                      onClick={() => setActiveBoardTab('finansial')}
                      className={`px-3 py-1.5 rounded-md transition-all whitespace-nowrap ${
                        activeBoardTab === 'finansial' ? 'bg-white text-indigo-700 font-bold shadow-sm' : 'hover:text-slate-900'
                      }`}
                    >
                      Finansial (Rp)
                    </button>
                    <button
                      onClick={() => setActiveBoardTab('anomali')}
                      className={`px-3 py-1.5 rounded-md transition-all whitespace-nowrap ${
                        activeBoardTab === 'anomali' ? 'bg-white text-indigo-700 font-bold shadow-sm' : 'hover:text-slate-900'
                      }`}
                    >
                      Diagnostik Masalah
                    </button>
                  </div>
                </div>
              </div>

              {/* Table Data */}
              <div className="overflow-x-auto">
                <table className="w-full text-xs text-left min-w-[720px]">
                  <thead className="bg-slate-100/80 text-slate-500 text-[11px] uppercase tracking-wider border-b border-slate-200 font-bold">
                    <tr>
                      <th className="px-4 py-3">Mesin</th>
                      <th className="px-3 py-3 text-center">Batch</th>
                      
                      {activeBoardTab === 'operasional' && (
                        <>
                          <th className="px-3 py-3 text-right">Output (yd)</th>
                          <th className="px-3 py-3 text-right">Durasi Aktual</th>
                          <th className="px-3 py-3 text-right">Durasi Ideal</th>
                          <th className="px-3 py-3 text-right">Efisiensi (%)</th>
                          <th className="px-3 py-3 text-right">Changeover</th>
                          <th className="px-3 py-3 text-right">Loss Time</th>
                        </>
                      )}

                      {activeBoardTab === 'energi' && (
                        <>
                          <th className="px-3 py-3 text-right">Steam Aktual</th>
                          <th className="px-3 py-3 text-right">Steam Ideal</th>
                          <th className="px-3 py-3 text-right">Efisiensi Uap</th>
                          <th className="px-3 py-3 text-right">Steam Loss (kg)</th>
                          <th className="px-3 py-3 text-right">Listrik Aktual</th>
                          <th className="px-3 py-3 text-right">Efisiensi Listrik</th>
                        </>
                      )}

                      {activeBoardTab === 'finansial' && (
                        <>
                          <th className="px-3 py-3 text-right">Steam Loss (Rp)</th>
                          <th className="px-3 py-3 text-right">Listrik Loss (Rp)</th>
                          <th className="px-3 py-3 text-right">Listrik WBP (Rp)</th>
                          <th className="px-3 py-3 text-right">Total Kerugian (Rp)</th>
                          <th className="px-3 py-3 text-right">Biaya/Yard</th>
                        </>
                      )}

                      {activeBoardTab === 'anomali' && (
                        <>
                          <th className="px-3 py-3 text-right">Delay Heat</th>
                          <th className="px-3 py-3 text-right">Delay Cool</th>
                          <th className="px-3 py-3 text-right">Total Delay</th>
                          <th className="px-3 py-3 text-right">Avg Tekanan</th>
                          <th className="px-3 py-3 text-center">Status Suplai</th>
                        </>
                      )}

                      <th className="px-4 py-3 text-center">Aksi</th>
                    </tr>
                  </thead>

                  <tbody className="divide-y divide-slate-100">
                    {machineRows.map((m) => {
                      const totalLossRp = (m.steam_loss_rp || 0) + (m.power_loss_rp || 0);
                      const isLowEff = m.avg_eff != null && m.avg_eff < 65;

                      return (
                        <tr key={m.machine_id} className="hover:bg-slate-50 transition-colors">
                          {/* Nama Mesin & Grup */}
                          <td className="px-4 py-3">
                            <span className="font-extrabold text-slate-800 block text-xs">{m.machine_name}</span>
                            <span className="text-[10px] text-slate-400 block">{m.group_name}</span>
                          </td>

                          {/* Batch Count */}
                          <td className="px-3 py-3 text-center font-bold text-slate-700">
                            {m.processes ? m.processes.length : '-'}
                          </td>

                          {/* TAB 1: OPERASIONAL */}
                          {activeBoardTab === 'operasional' && (
                            <>
                              <td className="px-3 py-3 text-right font-medium text-slate-700">
                                {m.output_yd != null ? m.output_yd.toLocaleString() : '-'}
                              </td>
                              <td className="px-3 py-3 text-right font-medium text-slate-600">
                                {m.actual_duration_mins != null ? `${m.actual_duration_mins}m` : '-'}
                              </td>
                              <td className="px-3 py-3 text-right font-medium text-slate-500">
                                {m.ideal_duration_mins != null ? `${m.ideal_duration_mins}m` : '-'}
                              </td>
                              <td className="px-3 py-3 text-right">
                                <span className={`px-2 py-0.5 rounded font-bold ${
                                  m.avg_eff >= 75 ? 'bg-emerald-50 text-emerald-700' :
                                  m.avg_eff >= 60 ? 'bg-amber-50 text-amber-700' :
                                  'bg-red-50 text-red-700'
                                }`}>
                                  {m.avg_eff != null ? `${m.avg_eff}%` : '-'}
                                </span>
                              </td>
                              <td className="px-3 py-3 text-right font-medium text-slate-600">
                                {m.avg_changeover_minutes != null ? `${m.avg_changeover_minutes}m` : '-'}
                              </td>
                              <td className="px-3 py-3 text-right font-semibold text-slate-700">
                                {m.total_loss_time_str || '-'}
                              </td>
                            </>
                          )}

                          {/* TAB 2: ENERGI (PINN) */}
                          {activeBoardTab === 'energi' && (
                            <>
                              <td className="px-3 py-3 text-right font-medium text-slate-700">
                                {m.steam_usage != null ? `${num(m.steam_usage)} kg` : '-'}
                              </td>
                              <td className="px-3 py-3 text-right font-medium text-slate-500">
                                {m.steam_ideal_kg != null ? `${num(m.steam_ideal_kg)} kg` : '-'}
                              </td>
                              <td className="px-3 py-3 text-right">
                                <span className={`px-2 py-0.5 rounded font-bold ${
                                  m.steam_eff >= 80 ? 'bg-emerald-50 text-emerald-700' :
                                  m.steam_eff >= 65 ? 'bg-amber-50 text-amber-700' :
                                  'bg-red-50 text-red-700'
                                }`}>
                                  {m.steam_eff != null ? `${num(m.steam_eff)}%` : '-'}
                                </span>
                              </td>
                              <td className="px-3 py-3 text-right font-bold text-red-600">
                                {m.steam_loss_kg != null ? `+${num(m.steam_loss_kg)} kg` : '-'}
                              </td>
                              <td className="px-3 py-3 text-right font-medium text-slate-700">
                                {m.power_usage != null ? `${num(m.power_usage)} kWh` : '-'}
                              </td>
                              <td className="px-3 py-3 text-right">
                                <span className={`px-2 py-0.5 rounded font-bold ${
                                  m.power_eff >= 80 ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-700'
                                }`}>
                                  {m.power_eff != null ? `${num(m.power_eff)}%` : '-'}
                                </span>
                              </td>
                            </>
                          )}

                          {/* TAB 3: FINANSIAL */}
                          {activeBoardTab === 'finansial' && (
                            <>
                              <td className="px-3 py-3 text-right font-bold text-red-600">
                                {formatRp(m.steam_loss_rp)}
                              </td>
                              <td className="px-3 py-3 text-right font-medium text-amber-600">
                                {formatRp(m.power_loss_rp)}
                              </td>
                              <td className="px-3 py-3 text-right font-medium text-purple-600">
                                {formatRp(m.power_wbp_rp)}
                              </td>
                              <td className="px-3 py-3 text-right font-black text-slate-900">
                                {formatRp(totalLossRp)}
                              </td>
                              <td className="px-3 py-3 text-right font-bold text-indigo-700">
                                {m.total_cost_per_yd ? `Rp ${num(m.total_cost_per_yd)}` : '-'}
                              </td>
                            </>
                          )}

                          {/* TAB 4: DIAGNOSTIK MASALAH */}
                          {activeBoardTab === 'anomali' && (
                            <>
                              <td className="px-3 py-3 text-right font-medium text-orange-600">
                                {m.delay_heat_mins > 0 ? `+${m.delay_heat_mins}m` : '-'}
                              </td>
                              <td className="px-3 py-3 text-right font-medium text-blue-600">
                                {m.delay_cool_mins > 0 ? `+${m.delay_cool_mins}m` : '-'}
                              </td>
                              <td className="px-3 py-3 text-right font-bold text-red-600">
                                {(m.delay_heat_mins || 0) + (m.delay_cool_mins || 0) > 0 ? `+${(m.delay_heat_mins || 0) + (m.delay_cool_mins || 0)}m` : '-'}
                              </td>
                              <td className="px-3 py-3 text-right font-medium text-slate-700">
                                {m.avg_steam_pressure ? `${m.avg_steam_pressure} bar` : '-'}
                              </td>
                              <td className="px-3 py-3 text-center">
                                {m.avg_steam_pressure && m.avg_steam_pressure < 3.8 ? (
                                  <span className="bg-red-100 text-red-700 font-bold px-2 py-0.5 rounded text-[10px]">Starved</span>
                                ) : (
                                  <span className="bg-emerald-100 text-emerald-700 font-bold px-2 py-0.5 rounded text-[10px]">Optimal</span>
                                )}
                              </td>
                            </>
                          )}

                          {/* Tombol Aksi */}
                          <td className="px-4 py-3 text-center">
                            <button
                              onClick={() => openMachineAnalytics(m.machine_id)}
                              className="px-2.5 py-1 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 font-bold rounded-lg transition-colors text-[11px]"
                            >
                              Detail Mesin
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </section>
          </>
        )}
      </main>

      {/* ── DATA LOSSES HARIAN BREAKDOWN MODAL ───────────────────────────── */}
      <LossesBreakdownModal
        isOpen={!!selectedLossCategory}
        onClose={() => setSelectedLossCategory(null)}
        categoryKey={selectedLossCategory}
        reportData={reportData}
        boilerData={boilerData}
        selectedDate={selectedDate}
      />
    </div>
  );
}
