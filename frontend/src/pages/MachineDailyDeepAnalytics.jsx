import React, { useState, useEffect, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer,
  ReferenceLine, ScatterChart, Scatter, ZAxis, Cell, Legend
} from 'recharts';
import {
  ExternalLink, ArrowLeft, Wind, Zap, Droplets, Clock, Activity, AlertTriangle, Printer,
  Compass, Flame, Wrench, ShieldCheck, CheckCircle2, ChevronLeft, ChevronRight,
  TrendingDown, TrendingUp, Layers, RefreshCw, AlertCircle, Timer, Award, Filter
} from 'lucide-react';
import api from '../lib/api';

const num = (v, d = 1) => (v == null || Number.isNaN(+v) ? '-' : +(+v).toFixed(d));
const formatRp = (val) => {
  if (val == null || Number.isNaN(+val)) return '-';
  return 'Rp ' + Math.round(val).toLocaleString('id-ID');
};

const getTone = (eff) => {
  if (eff == null || eff === '-') return 'gray';
  if (eff >= 80) return 'green';
  if (eff >= 60) return 'yellow';
  return 'red';
};

const colorMap = {
  'green': 'bg-green-50 text-green-700',
  'yellow': 'bg-yellow-50 text-yellow-700',
  'red': 'bg-red-50 text-red-700',
  'gray': 'bg-gray-50 text-gray-700'
};

const formatLoss = (val) => {
  if (val == null || val === '-') return <span className="text-gray-400">-</span>;
  const numVal = Number(val);
  if (isNaN(numVal)) return <span className="text-gray-400">-</span>;
  const sign = numVal > 0 ? '+' : '';
  const cls = numVal > 0 ? 'text-red-600 font-semibold' : 'text-emerald-600 font-semibold';
  return <span className={cls}>{sign}{numVal}</span>;
};

export default function MachineDailyDeepAnalytics() {
  const { machineId, date } = useParams();
  const navigate = useNavigate();

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Filters & State
  const [selectedProgramFilter, setSelectedProgramFilter] = useState('ALL');
  const [scatterPhaseMode, setScatterPhaseMode] = useState('heating'); // 'heating' | 'cooling'

  const fetchData = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await api.get(`/report/machine/${machineId}/daily-chart-deep?date=${date}`);
      setData(res.data);
    } catch (err) {
      console.error(err);
      setError('Gagal memuat data analitik mendalam mesin.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [machineId, date]);

  const changeDate = (days) => {
    const d = new Date(date);
    d.setDate(d.getDate() + days);
    const nextDate = d.toISOString().split('T')[0];
    navigate(`/machine-daily-deep-analytics/${machineId}/${nextDate}`);
  };

  // ── Print Handling ──────────────────────────────────────────────────────
  const handlePrint = () => {
    let style = document.getElementById('dynamic-print-style');
    if (!style) {
      style = document.createElement('style');
      style.id = 'dynamic-print-style';
      style.innerHTML = '@page { size: A4 landscape; margin: 6mm 6mm; }';
      document.head.appendChild(style);
    }
    document.documentElement.classList.add('printing-daily');
    document.body.classList.add('printing-daily');
    window.dispatchEvent(new Event('resize'));
    requestAnimationFrame(() => {
      setTimeout(() => {
        window.print();
      }, 150);
    });
  };

  // ── 1. Historical Scatter Filtering (60 Batches) ────────────────────────
  const filteredScatterData = useMemo(() => {
    if (!data?.historical_scatter) return [];
    let list = data.historical_scatter;
    if (selectedProgramFilter !== 'ALL') {
      list = list.filter(item => item.program_name === selectedProgramFilter);
    }
    return list;
  }, [data, selectedProgramFilter]);

  // Quadrant Summary Statistics for the 60 batches
  const quadrantStats = useMemo(() => {
    if (!data?.historical_scatter) return { optimal: 0, boilerDrop: 0, mechDegradation: 0, anomalous: 0, total: 0 };
    const list = data.historical_scatter;
    let optimal = 0;
    let boilerDrop = 0;
    let mechDegradation = 0;
    let anomalous = 0;

    list.forEach(b => {
      if (b.quadrant === 'OPTIMAL') optimal++;
      else if (b.quadrant === 'BOILER_DROP') boilerDrop++;
      else if (b.quadrant === 'MECHANICAL_DEGRADATION') mechDegradation++;
      else anomalous++;
    });

    return {
      optimal,
      boilerDrop,
      mechDegradation,
      anomalous,
      total: list.length
    };
  }, [data]);

  // Available unique programs from historical scatter
  const availablePrograms = useMemo(() => {
    if (!data?.program_benchmarks) return [];
    return data.program_benchmarks.map(p => p.program_name);
  }, [data]);

  // Ideal target duration for currently selected program
  const currentProgramIdeal = useMemo(() => {
    if (!data?.program_benchmarks || selectedProgramFilter === 'ALL') return null;
    return data.program_benchmarks.find(p => p.program_name === selectedProgramFilter) || null;
  }, [data, selectedProgramFilter]);

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-slate-50">
        <div className="flex flex-col items-center gap-3">
          <RefreshCw className="w-10 h-10 text-indigo-600 animate-spin" />
          <p className="text-slate-600 font-bold text-sm">Menghitung 60-Batch Historical Performance & Audit Fisik...</p>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="flex h-screen items-center justify-center bg-slate-50 p-6">
        <div className="bg-white rounded-2xl shadow-sm border border-red-200 p-8 max-w-md text-center">
          <AlertCircle className="w-12 h-12 text-red-500 mx-auto mb-4" />
          <h2 className="text-lg font-bold text-slate-800 mb-2">Gagal Memuat Analitik Mesin</h2>
          <p className="text-slate-500 text-xs mb-6">{error}</p>
          <button
            onClick={() => { if (window.history.state && typeof window.history.state.idx === "number" && window.history.state.idx > 0) { navigate(-1); } else { navigate("/daily-report-deep"); } }}
            className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-bold rounded-lg transition-colors"
          >
            Kembali
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto bg-slate-50/70 pb-16 font-sans text-slate-800 print-area">
      
      {/* 🚀 STICKY COMPACT TOOLBAR 🚀 */}
      <header className="sticky top-0 z-30 bg-white/95 backdrop-blur-md border-b border-slate-200 px-3 sm:px-6 py-2.5 flex items-center justify-between gap-3 shadow-sm no-print">
        <div className="flex items-center gap-3 min-w-0">
          <button 
            onClick={() => navigate(`/daily-report-deep`)}
            className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-600 transition-colors"
            title="Kembali ke Daily Report V2"
          >
            <ArrowLeft size={18} />
          </button>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h1 className="text-base sm:text-lg font-bold text-slate-800 truncate">
                {data.machine_name} <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 font-bold border border-indigo-200">Depth Analytics Dossier</span>
              </h1>
              <span className="hidden md:inline-flex text-[11px] font-semibold text-slate-500 bg-slate-100 px-2 py-0.5 rounded">
                Grup: {data.machine_group}
              </span>
            </div>
            <p className="text-[11px] text-slate-500 truncate">
              Periode 24 Jam: {data.date_range} WIB
            </p>
          </div>
        </div>

        {/* Toolbar Action Controls */}
        <div className="flex items-center gap-2 flex-shrink-0">
          {/* Switcher back to standard machine view */}
          <button
            onClick={() => navigate(`/machine-daily-analytics/${machineId}/${date}`)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-slate-600 bg-slate-100 hover:bg-slate-200 rounded-lg transition-colors border border-slate-200"
            title="Buka format tampilan standar"
          >
            <span className="hidden sm:inline">Format Standar</span>
          </button>

          {/* Date Navigator */}
          <div className="flex items-center bg-slate-100 rounded-lg p-0.5 border border-slate-200">
            <button
              onClick={() => changeDate(-1)}
              className="p-1.5 text-slate-600 hover:text-slate-900 hover:bg-white rounded-md transition-all"
              title="Hari Sebelumnya"
            >
              <ChevronLeft size={16} />
            </button>
            <input
              type="date"
              className="bg-transparent border-none text-xs font-bold text-slate-700 focus:ring-0 px-1 cursor-pointer outline-none w-[115px] text-center"
              value={date}
              onChange={(e) => navigate(`/machine-daily-deep-analytics/${machineId}/${e.target.value}`)}
            />
            <button
              onClick={() => changeDate(1)}
              className="p-1.5 text-slate-600 hover:text-slate-900 hover:bg-white rounded-md transition-all"
              title="Hari Berikutnya"
            >
              <ChevronRight size={16} />
            </button>
          </div>

          <button
            onClick={fetchData}
            className="p-2 text-slate-600 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors border border-slate-200 bg-white shadow-xs"
            title="Muat ulang analitik"
          >
            <RefreshCw size={15} />
          </button>

          <button
            onClick={handlePrint}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold rounded-lg transition-colors shadow-xs"
          >
            <Printer size={15} /> <span className="hidden sm:inline">Print Dossier</span>
          </button>
        </div>
      </header>

      {/* ── CONTENT BODY ─────────────────────────────────────────────────── */}
      <main className="p-3 sm:p-6 space-y-6 max-w-7xl mx-auto">
        
        {/* Print Header */}
        <div className="hidden print:block mb-3 pb-2 border-b-2 border-slate-800">
          <div className="flex justify-between items-end">
            <div>
              <h1 className="text-xl font-bold text-slate-900">
                LAPORAN AUDIT & DIAGNOSTIK KINERJA MESIN: {data.machine_name}
              </h1>
              <p className="text-xs text-slate-600 mt-0.5">
                Tanggal: <b>{date}</b> &bull; Periode: <b>{data.date_range}</b> &bull; Grup: <b>{data.machine_group}</b>
              </p>
            </div>
            <div className="text-[10px] text-slate-500 text-right">
              Dicetak pada: {new Date().toLocaleString('id-ID')}
            </div>
          </div>
        </div>

        {/* ═══════════════════════════════════════════════════════════════════ */}
        {/* UPPER SECTION: 24-HR CHART & SUMMARY (ASLI DENGAN DESAIN POLISHED)  */}
        {/* ═══════════════════════════════════════════════════════════════════ */}
        <div className="flex flex-col lg:flex-row gap-4">
          
          {/* Main 24-Hour Temp vs Steam Pressure Chart */}
          <div className="flex-1 bg-white rounded-2xl shadow-xs border border-slate-200 p-4 sm:p-5 flex flex-col justify-between">
            <div className="flex flex-wrap items-center justify-between gap-3 mb-2">
              <h2 className="text-xs sm:text-sm font-semibold text-slate-900 uppercase tracking-wider flex items-center gap-2">
                <Activity size={16} className="text-indigo-600" /> Profil Suhu Aktual Mesin vs Tekanan Uap (24 Jam)
              </h2>
              <div className="flex items-center gap-4 text-xs font-semibold">
                <div className="flex items-center gap-1.5 text-slate-700">
                  <span className="w-4 h-1 bg-red-500 rounded-full inline-block" />
                  <span>Suhu (°C)</span>
                </div>
                <div className="flex items-center gap-1.5 text-slate-700">
                  <span className="w-4 h-0 border-t-2 border-dashed border-blue-600 inline-block" />
                  <span>Tekanan Steam (bar)</span>
                </div>
              </div>
            </div>

            <div className="h-[320px] sm:h-[360px] w-full min-w-0">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={data.chart_data} margin={{ top: 12, right: 10, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
                  <XAxis dataKey="time" tick={{ fontSize: 11, fill: '#64748b' }} axisLine={false} tickLine={false} minTickGap={30} />
                  <YAxis yAxisId="left" tick={{ fontSize: 11, fill: '#ef4444' }} axisLine={false} tickLine={false} />
                  <YAxis yAxisId="right" orientation="right" domain={[0, 7]} tick={{ fontSize: 11, fill: '#2563eb' }} axisLine={false} tickLine={false} />
                  <RechartsTooltip contentStyle={{ borderRadius: '10px', border: 'none', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)', fontSize: '12px' }} />
                  <Line yAxisId="left" type="monotone" dataKey="temp" stroke="#ef4444" strokeWidth={2.2} dot={false} name="Suhu (°C)" />
                  <Line yAxisId="right" type="monotone" dataKey="pressure" stroke="#2563eb" strokeWidth={1.8} strokeDasharray="4 4" dot={false} name="Tekanan (bar)" />
                  <ReferenceLine yAxisId="right" y={3.8} stroke="#f59e0b" strokeDasharray="3 3" label={{ value: '3.8 bar threshold', fill: '#d97706', fontSize: 10, position: 'insideTopLeft' }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Side Summary Cards */}
          {data.summary && (
            <div className="w-full lg:w-[320px] shrink-0 space-y-3">
              
              {/* Summary Energi */}
              <div className="bg-white rounded-2xl border border-slate-200 p-4 shadow-xs">
                <h3 className="text-xs font-bold text-slate-700 uppercase tracking-wider flex items-center gap-1.5 mb-3">
                  <Zap size={14} className="text-amber-500" /> Ringkasan Energi Harian
                </h3>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div className="bg-slate-50 border border-slate-100 p-2.5 rounded-xl">
                    <span className="text-[10px] text-slate-400 font-bold uppercase block">Steam Usage</span>
                    <span className="text-base font-semibold text-slate-800">{num(data.summary.steam_usage)} <span className="text-[10px] font-normal text-slate-400">kg</span></span>
                  </div>
                  <div className="bg-slate-50 border border-slate-100 p-2.5 rounded-xl">
                    <span className="text-[10px] text-slate-400 font-bold uppercase block">Steam Eff</span>
                    <span className={`text-base font-semibold ${data.summary.steam_eff >= 80 ? 'text-emerald-600' : 'text-amber-600'}`}>
                      {num(data.summary.steam_eff)}%
                    </span>
                  </div>
                  <div className="bg-slate-50 border border-slate-100 p-2.5 rounded-xl">
                    <span className="text-[10px] text-slate-400 font-bold uppercase block">Listrik WBP</span>
                    <span className="text-base font-semibold text-purple-700">{num(data.summary.total_power_wbp_kwh)} <span className="text-[10px] font-normal text-slate-400">kWh</span></span>
                  </div>
                  <div className="bg-slate-50 border border-slate-100 p-2.5 rounded-xl">
                    <span className="text-[10px] text-slate-400 font-bold uppercase block">Listrik LWBP</span>
                    <span className="text-base font-semibold text-blue-700">{num(data.summary.total_power_lwbp_kwh)} <span className="text-[10px] font-normal text-slate-400">kWh</span></span>
                  </div>
                  <div className="bg-slate-50 border border-slate-100 p-2.5 rounded-xl col-span-2 flex justify-between items-center">
                    <div>
                      <span className="text-[10px] text-slate-400 font-bold uppercase block">% Sehat Uap (&gt;3.8 bar)</span>
                      <span className="text-sm font-semibold text-slate-800">{num(data.summary.steam_ok_pct)}%</span>
                    </div>
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${data.summary.steam_ok_pct >= 80 ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'}`}>
                      {data.summary.steam_ok_pct >= 80 ? 'Optimal' : 'Sering Drop'}
                    </span>
                  </div>
                </div>
              </div>

              {/* Losses & Potensi Penghematan */}
              <div className="bg-white rounded-2xl border border-red-100 p-4 shadow-xs">
                <h3 className="text-xs font-bold text-red-700 uppercase tracking-wider flex items-center gap-1.5 mb-2.5">
                  <AlertTriangle size={14} className="text-red-500" /> Losses & Potensi Saving
                </h3>
                <div className="space-y-2 text-xs">
                  <div className="bg-slate-50 border border-slate-100 p-2.5 rounded-xl flex justify-between items-center">
                    <div>
                      <span className="text-[11px] font-bold text-slate-700 flex items-center gap-1"><Clock size={12} /> Total Loss Time</span>
                      <span className="text-[10px] text-slate-400">Waktu di luar standar ideal</span>
                    </div>
                    <span className="text-sm font-semibold text-red-600">{data.summary.total_loss_time_str || '-'}</span>
                  </div>

                  <div className="bg-red-50/70 border border-red-200 p-2.5 rounded-xl">
                    <span className="text-[10px] font-bold text-red-900 block uppercase">Kerugian Finansial Energi</span>
                    <span className="text-lg font-bold text-red-600 block mt-0.5">
                      {formatRp((data.summary.steam_loss_rp || 0) + (data.summary.power_loss_rp || 0))}
                    </span>
                    <div className="mt-1 pt-1 border-t border-red-100 flex justify-between text-[10px] text-red-700 font-medium">
                      <span>Steam Loss: {formatRp(data.summary.steam_loss_rp)}</span>
                      <span>Power Loss: {formatRp(data.summary.power_loss_rp)}</span>
                    </div>
                  </div>
                </div>
              </div>

            </div>
          )}
        </div>

        {/* ═══════════════════════════════════════════════════════════════════ */}
        {/* DYEING ANALYTICS BATCHES TABLE (SESUAI FORMAT STANDAR)              */}
        {/* ═══════════════════════════════════════════════════════════════════ */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden daily-analytics-card daily-analytics-table-card">
          <div className="px-4 py-2 border-b border-gray-100 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Layers size={16} className="text-indigo-600" />
              <h2 className="text-sm sm:text-base font-bold text-gray-800">
                Dyeing Analytics <span className="text-xs font-normal text-gray-500">(Batch Berjalan Hari Ini)</span>
              </h2>
            </div>
            <span className="text-[11px] text-gray-400">Durasi dihitung dari Real Heat s/d Selesai</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs border-collapse daily-analytics-table">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr className="divide-x divide-gray-200/70">
                  <th className="px-2 py-1.5 text-left font-semibold text-gray-600 leading-tight">Batch #<br/>Process</th>
                  <th className="px-2 py-1.5 text-left font-semibold text-gray-600 leading-tight">Batch<br/>Kain</th>
                  <th className="px-2 py-1.5 text-left font-semibold text-gray-600 leading-tight">Jenis<br/>Proses</th>
                  <th className="px-2 py-1.5 text-left font-semibold text-gray-600 leading-tight">Program</th>
                  <th className="px-2 py-1.5 text-right font-semibold text-gray-600 leading-tight">Output<br/>(yd)</th>
                  <th className="px-2 py-1.5 text-left font-semibold text-gray-600 leading-tight">Artikel</th>
                  <th className="px-2 py-1.5 text-left font-semibold text-gray-600 leading-tight">No Order</th>
                  <th className="px-2 py-1.5 text-center font-semibold text-gray-600 leading-tight">Jam<br/>Mulai</th>
                  <th className="px-2 py-1.5 text-right font-semibold text-gray-600 leading-tight">Durasi<br/>Total</th>
                  <th className="px-2 py-1.5 text-right font-semibold text-gray-600 leading-tight">Dur<br/>Ideal</th>
                  <th className="px-2 py-1.5 text-right font-semibold text-gray-600 leading-tight" title="Durasi Bongkar Kain / Keluar-Masuk Kain (<70°C s/d Mesin OFF). Standar toleransi pabrik ≤45 menit.">Bongkar Kain<br/>(Handling)</th>
                  <th className="px-2 py-1.5 text-right font-semibold text-gray-600 leading-tight">Listrik<br/>(kWh)</th>
                  <th className="px-2 py-1.5 text-right font-semibold text-gray-600 leading-tight">Listrik Loss<br/>(kWh)</th>
                  <th className="px-2 py-1.5 text-right font-semibold text-gray-600 leading-tight">Steam Usage<br/>(kg)</th>
                  <th className="px-2 py-1.5 text-right font-semibold text-gray-600 leading-tight">Steam Loss<br/>(kg)</th>
                  <th className="px-2 py-1.5 text-center font-semibold text-gray-600 leading-tight">Eff<br/>Total</th>
                  <th className="px-2 py-1.5 text-center font-semibold text-gray-600 leading-tight no-print">Aksi</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {data.batches && data.batches.length > 0 ? (
                  data.batches.map((b) => (
                    <tr key={b.id} className="hover:bg-gray-50 transition-colors divide-x divide-gray-100">
                      <td className="px-2 py-1.5 font-bold text-gray-900 whitespace-nowrap">#{b.batch_number}</td>
                      <td className="px-2 py-1.5 text-gray-700 whitespace-nowrap">{b.batch_kain}</td>
                      <td className="px-2 py-1.5 text-gray-700 whitespace-nowrap">{b.jenis_proses}</td>
                      <td className="px-2 py-1.5 text-gray-700 font-medium">{b.program || '-'}</td>
                      <td className="px-2 py-1.5 text-right text-gray-700 whitespace-nowrap">{b.output_yd}</td>
                      <td className="px-2 py-1.5 text-gray-700 max-w-[160px] truncate" title={b.artikel}>{b.artikel}</td>
                      <td className="px-2 py-1.5 text-gray-700 whitespace-nowrap">{b.no_order}</td>
                      <td className="px-2 py-1.5 text-center text-gray-700 whitespace-nowrap">{b.jam_mulai}</td>
                      <td className="px-2 py-1.5 text-right text-gray-800 font-medium whitespace-nowrap">{b.total_durasi}</td>
                      <td className="px-2 py-1.5 text-right text-gray-600 whitespace-nowrap">{b.durasi_ideal}</td>
                      <td className="px-2 py-1.5 text-right whitespace-nowrap">
                        {b.late_stop_mins != null ? (
                          <span 
                            className={b.late_stop_mins > 45 ? "text-red-600 font-bold" : "text-gray-800 font-medium"}
                            title={`Bongkar (<70°C s/d OFF): ${b.late_stop_mins}m ${b.late_stop_mins > 45 ? '(Over >45m)' : '(Normal ≤45m)'}${b.pre_heat_mins != null ? ` | Muat Awal: ${b.pre_heat_mins}m` : ''}`}
                          >
                            {b.late_stop_mins}m
                          </span>
                        ) : (
                          <span className="text-gray-400">-</span>
                        )}
                      </td>
                      <td className="px-2 py-1.5 text-right text-gray-800 whitespace-nowrap">{b.power_usage}</td>
                      <td className="px-2 py-1.5 text-right whitespace-nowrap">{formatLoss(b.power_loss_kwh)}</td>
                      <td className="px-2 py-1.5 text-right text-gray-800 whitespace-nowrap">{b.steam_usage}</td>
                      <td className="px-2 py-1.5 text-right whitespace-nowrap">{formatLoss(b.steam_loss_kg)}</td>
                      <td className="px-2 py-1.5 text-center whitespace-nowrap">
                        <span className={`inline-flex px-1.5 py-0.5 rounded font-bold text-[11px] ${colorMap[getTone(b.eff_total)]}`}>
                          {b.eff_total != null ? `${b.eff_total}%` : '-'}
                        </span>
                      </td>
                      <td className="px-2 py-1.5 text-center whitespace-nowrap no-print">
                        <a 
                          href={`/history/report/${b.id}`} 
                          target="_blank" 
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 text-blue-600 hover:text-blue-800 font-semibold px-1.5 py-0.5 rounded hover:bg-blue-50 transition-colors text-[11px]"
                        >
                          Detail <ExternalLink size={11} />
                        </a>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan="17" className="px-4 py-6 text-center text-gray-500">
                      Tidak ada data batch pada hari ini.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>


        {/* ═══════════════════════════════════════════════════════════════════ */}
        {/* NEW SECTION A: GRAFIK KORELASI RIWAYAT HEATING & COOLING (60 BATCH) */}
        {/* ═══════════════════════════════════════════════════════════════════ */}
        <section className="bg-white rounded-2xl shadow-xs border border-slate-200 p-4 sm:p-6 space-y-4">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 pb-3 border-b border-slate-100">
            <div>
              <div className="flex items-center gap-2">
                <Compass className="w-5 h-5 text-indigo-600" />
                <h2 className="text-sm sm:text-base font-bold text-slate-900 tracking-tight">
                  Korelasi Riwayat Durasi vs Tekanan Uap (60 Batch Terakhir)
                </h2>
              </div>
              <p className="text-xs text-slate-500 mt-0.5">
                Membedah apakah perlambatan pemanasan/pendinginan akibat boiler drop (&lt;3.8 bar) atau degradasi mekanik mesin
              </p>
            </div>

            {/* Filter Program & Phase Switcher */}
            <div className="flex items-center gap-2 flex-wrap">
              {/* Program Selector */}
              <div className="flex items-center gap-1.5 text-xs bg-slate-100 px-2.5 py-1.5 rounded-xl border border-slate-200">
                <Filter size={13} className="text-slate-400" />
                <span className="font-bold text-slate-600">Program:</span>
                <select
                  value={selectedProgramFilter}
                  onChange={(e) => setSelectedProgramFilter(e.target.value)}
                  className="bg-transparent font-bold text-indigo-700 outline-none cursor-pointer text-xs"
                >
                  <option value="ALL">Semua Program ({data.historical_scatter?.length || 60} Batch)</option>
                  {availablePrograms.map(p => (
                    <option key={p} value={p}>{p}</option>
                  ))}
                </select>
              </div>

              {/* Mode Heating vs Cooling */}
              <div className="flex bg-slate-200/80 p-0.5 rounded-lg text-xs font-bold text-slate-600">
                <button
                  onClick={() => setScatterPhaseMode('heating')}
                  className={`px-3 py-1 rounded-md transition-all ${
                    scatterPhaseMode === 'heating' ? 'bg-white text-indigo-700 shadow-xs' : 'hover:text-slate-900'
                  }`}
                >
                  Fase Heating
                </button>
                <button
                  onClick={() => setScatterPhaseMode('cooling')}
                  className={`px-3 py-1 rounded-md transition-all ${
                    scatterPhaseMode === 'cooling' ? 'bg-white text-indigo-700 shadow-xs' : 'hover:text-slate-900'
                  }`}
                >
                  Fase Cooling
                </button>
              </div>
            </div>
          </div>

          {/* Scatter Chart & Diagnostic Breakdown */}
          <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
            
            {/* Scatter Chart (3 cols) */}
            <div className="lg:col-span-3 h-[380px] w-full min-w-0 bg-slate-50/50 rounded-xl p-3 border border-slate-100">
              <ResponsiveContainer width="100%" height="100%">
                <ScatterChart margin={{ top: 15, right: 20, bottom: 20, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  
                  {/* X Axis: Avg Steam Pressure (bar) */}
                  <XAxis 
                    type="number" 
                    dataKey="avg_steam_pressure" 
                    name="Tekanan Uap Rata-rata" 
                    unit=" bar" 
                    domain={[1.5, 6.5]} 
                    tick={{ fontSize: 11, fill: '#64748b' }}
                    label={{ value: 'Tekanan Uap Rata-rata (bar)', position: 'insideBottom', offset: -10, fontSize: 11, fill: '#475569' }}
                  />

                  {/* Y Axis: Duration in minutes */}
                  <YAxis 
                    type="number" 
                    dataKey={scatterPhaseMode === 'heating' ? 'real_heat' : 'real_cool'} 
                    name={scatterPhaseMode === 'heating' ? 'Durasi Heating' : 'Durasi Cooling'} 
                    unit=" mnt" 
                    tick={{ fontSize: 11, fill: '#64748b' }}
                    label={{ value: scatterPhaseMode === 'heating' ? 'Durasi Heating (Menit)' : 'Durasi Cooling (Menit)', angle: -90, position: 'insideLeft', offset: 15, fontSize: 11, fill: '#475569' }}
                  />
                  
                  <ZAxis range={[50, 180]} />
                  <RechartsTooltip 
                    cursor={{ strokeDasharray: '3 3' }} 
                    contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 8px 16px -4px rgb(0 0 0 / 0.1)', fontSize: '12px' }}
                    content={({ payload }) => {
                      if (!payload || !payload.length) return null;
                      const d = payload[0].payload;
                      return (
                        <div className="bg-white p-3 rounded-xl shadow-lg border border-slate-200 text-xs space-y-1">
                          <div className="flex items-center justify-between font-semibold text-slate-800 pb-1 border-b border-slate-100">
                            <span>Batch #{d.batch_number} {d.is_today && <b className="text-amber-500 font-bold ml-1">(HARI INI)</b>}</span>
                            <span className="text-[10px] text-slate-400">{d.date} {d.jam}</span>
                          </div>
                          <div>Program: <b className="text-indigo-600">{d.program_name}</b></div>
                          <div>Tekanan Boiler: <b>{d.avg_steam_pressure} bar</b></div>
                          {d.real_total != null && (
                            <div>Durasi Total: <b>{d.real_total} mnt</b> {d.ideal_total != null && <span className="text-slate-400 font-normal">(Ideal: {d.ideal_total} mnt)</span>}</div>
                          )}
                          <div>Durasi {scatterPhaseMode === 'heating' ? 'Heating' : 'Cooling'}: <b>{scatterPhaseMode === 'heating' ? d.real_heat : d.real_cool} mnt</b> (Ideal: {scatterPhaseMode === 'heating' ? d.ideal_heat : d.ideal_cool} mnt)</div>
                          <div>Deviasi: <b className={(scatterPhaseMode === 'heating' ? d.delta_heat : d.delta_cool) > 10 ? 'text-red-600' : 'text-emerald-600'}>
                            {(scatterPhaseMode === 'heating' ? d.delta_heat : d.delta_cool) > 0 ? `+${(scatterPhaseMode === 'heating' ? d.delta_heat : d.delta_cool)}` : (scatterPhaseMode === 'heating' ? d.delta_heat : d.delta_cool)} mnt
                          </b></div>
                          <div className="pt-1 border-t border-slate-100 text-[11px] font-bold text-slate-700">
                            Diagnostik: <span className="text-indigo-700">{d.diag_label}</span>
                          </div>
                        </div>
                      );
                    }}
                  />

                  {/* Ambang Batas Kritis Boiler: 3.8 bar */}
                  <ReferenceLine x={3.8} stroke="#ef4444" strokeDasharray="4 4" label={{ value: 'Ambang Kritis 3.8 bar', fill: '#ef4444', fontSize: 10, position: 'insideTopLeft' }} />

                  {/* Durasi Ideal Program jika dipilih */}
                  {currentProgramIdeal && (
                    <ReferenceLine 
                      y={scatterPhaseMode === 'heating' ? currentProgramIdeal.ideal_heat : currentProgramIdeal.ideal_cool} 
                      stroke="#10b981" 
                      strokeDasharray="4 4" 
                      label={{ value: `Ideal: ${scatterPhaseMode === 'heating' ? currentProgramIdeal.ideal_heat : currentProgramIdeal.ideal_cool}m`, fill: '#059669', fontSize: 10, position: 'insideTopRight' }} 
                    />
                  )}

                  {/* Scatter Data Points */}
                  <Scatter 
                    name="Batch Riwayat" 
                    data={filteredScatterData}
                  >
                    {filteredScatterData.map((entry, index) => {
                      let color = '#3b82f6';
                      if (entry.is_today) color = '#f59e0b'; // Gold for today
                      else if (entry.quadrant === 'MECHANICAL_DEGRADATION') color = '#ef4444'; // Red for mechanical
                      else if (entry.quadrant === 'BOILER_DROP') color = '#f97316'; // Orange for boiler drop
                      else if (entry.quadrant === 'OPTIMAL') color = '#10b981'; // Green for optimal

                      return (
                        <Cell 
                          key={`cell-${index}`} 
                          fill={color} 
                          stroke={entry.is_today ? '#000000' : color} 
                          strokeWidth={entry.is_today ? 2 : 1}
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
                <h4 className="text-xs font-bold text-slate-800 uppercase tracking-wider mb-2">
                  Distribusi 4 Kuadran Masalah (60 Batch)
                </h4>
                
                <div className="space-y-2 text-xs">
                  {/* Optimal */}
                  <div className="p-2.5 bg-emerald-50/70 border border-emerald-200 rounded-xl">
                    <div className="flex justify-between items-center font-bold text-emerald-900">
                      <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-emerald-500" /> Optimal</span>
                      <span>{quadrantStats.optimal} batch ({Math.round(quadrantStats.optimal / quadrantStats.total * 100)}%)</span>
                    </div>
                    <p className="text-[10px] text-emerald-700 mt-1">Tekanan uap &gt;3.8 bar & durasi heating sesuai standar ideal.</p>
                  </div>

                  {/* Mechanical Degradation */}
                  <div className="p-2.5 bg-red-50/70 border border-red-200 rounded-xl">
                    <div className="flex justify-between items-center font-bold text-red-900">
                      <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-red-500" /> Kerak HE / Katup</span>
                      <span>{quadrantStats.mechDegradation} batch ({Math.round(quadrantStats.mechDegradation / quadrantStats.total * 100)}%)</span>
                    </div>
                    <p className="text-[10px] text-red-700 mt-1">Heating molor padahal uap cukup (&gt;4.0 bar). Murni masalah mesin internal.</p>
                  </div>

                  {/* Boiler Drop */}
                  <div className="p-2.5 bg-orange-50/70 border border-orange-200 rounded-xl">
                    <div className="flex justify-between items-center font-bold text-orange-900">
                      <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-orange-500" /> Pasokan Boiler Drop</span>
                      <span>{quadrantStats.boilerDrop} batch ({Math.round(quadrantStats.boilerDrop / quadrantStats.total * 100)}%)</span>
                    </div>
                    <p className="text-[10px] text-orange-700 mt-1">Heating molor karena uap drop &lt;3.8 bar. Masalah suplai pusat.</p>
                  </div>
                </div>
              </div>

              {/* Legend Indicator */}
              <div className="p-3 bg-slate-100 rounded-xl text-[11px] space-y-1 text-slate-600">
                <div className="font-bold text-slate-800 mb-1">Keterangan Marker:</div>
                <div className="flex items-center gap-2"><span className="w-3 h-3 rounded-full bg-amber-400 border border-black inline-block" /> <b>Bintang / Titik Emas:</b> Batch Hari Ini</div>
                <div className="flex items-center gap-2"><span className="w-2.5 h-2.5 rounded-full bg-red-500 inline-block" /> <b>Merah:</b> Kerusakan/Kerak Mesin</div>
                <div className="flex items-center gap-2"><span className="w-2.5 h-2.5 rounded-full bg-orange-500 inline-block" /> <b>Oranye:</b> Suplai Boiler Drop</div>
                <div className="flex items-center gap-2"><span className="w-2.5 h-2.5 rounded-full bg-emerald-500 inline-block" /> <b>Hijau:</b> Performa Optimal</div>
              </div>
            </div>

          </div>
        </section>


        {/* ═══════════════════════════════════════════════════════════════════ */}
        {/* NEW SECTION B: EVALUASI KESESUAIAN 3 FASE BATCH HARI INI           */}
        {/* ═══════════════════════════════════════════════════════════════════ */}
        <section className="bg-white rounded-2xl shadow-xs border border-slate-200 p-4 sm:p-6 space-y-4">
          <div>
            <h2 className="text-sm sm:text-base font-bold text-slate-900 tracking-tight flex items-center gap-2">
              <ShieldCheck className="w-5 h-5 text-emerald-600" />
              Audit Kesesuaian 3 Fase Operasi (Heating, Keeping, Cooling Hari Ini)
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Evaluasi kepatuhan laju termodinamika per batch terhadap standar Master Program
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {data.batches && data.batches.map(b => {
              const hDelay = (b.real_heating || 0) - (b.durasi_ideal ? 100 : 0);
              
              return (
                <div key={b.id} className="bg-slate-50 border border-slate-200 rounded-xl p-4 flex flex-col justify-between">
                  <div>
                    <div className="flex items-center justify-between pb-2 border-b border-slate-200">
                      <div>
                        <h4 className="text-sm font-bold text-slate-800">Batch #{b.batch_number}</h4>
                        <span className="text-[10px] text-indigo-700 font-bold block">{b.program} &bull; {b.jam_mulai}</span>
                      </div>
                      <span className={`px-2 py-0.5 rounded text-xs font-bold ${
                        b.eff_total >= 80 ? 'bg-emerald-100 text-emerald-800' : 'bg-red-100 text-red-800'
                      }`}>
                        {b.eff_total}% Eff
                      </span>
                    </div>

                    <div className="space-y-2 mt-3 text-xs">
                      {/* Fase Heating */}
                      <div className="bg-white p-2.5 rounded-lg border border-slate-200">
                        <div className="flex justify-between items-center mb-1">
                          <span className="font-bold text-slate-700 flex items-center gap-1">
                            <Flame size={12} className="text-red-500" /> Heating:
                          </span>
                          <div className="flex items-center gap-1.5">
                            <span className="font-semibold text-slate-800">
                              {b.real_heating !== '-' && b.real_heating != null ? `${b.real_heating}m` : '-'}
                            </span>
                            {b.ideal_heating != null && (
                              <span className="text-[10px] text-slate-500 font-medium">
                                (Idl: {b.ideal_heating}m)
                              </span>
                            )}
                            {b.delta_heating != null && (
                              <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${
                                b.delta_heating > 10 ? 'bg-red-100 text-red-700' :
                                b.delta_heating > 0 ? 'bg-amber-100 text-amber-800' :
                                'bg-emerald-100 text-emerald-800'
                              }`}>
                                {b.delta_heating > 0 ? `+${b.delta_heating}m` : `${b.delta_heating}m`}
                              </span>
                            )}
                          </div>
                        </div>
                        <div className="text-[10px] text-slate-500 flex justify-between pt-1 border-t border-slate-100">
                          <span>Avg Steam: <b>{b.avg_steam_pressure} bar</b></span>
                          <span className={b.avg_steam_pressure && b.avg_steam_pressure < 3.8 ? 'text-orange-600 font-bold' : 'text-emerald-600 font-bold'}>
                            {b.avg_steam_pressure && b.avg_steam_pressure < 3.8 ? 'Boiler Drop' : 'Uap Cukup'}
                          </span>
                        </div>
                      </div>

                      {/* Fase Keeping / Holding */}
                      <div className="bg-white p-2.5 rounded-lg border border-slate-200">
                        <div className="flex justify-between items-center mb-1">
                          <span className="font-bold text-slate-700 flex items-center gap-1">
                            <Clock size={12} className="text-amber-500" /> Keeping (Hold):
                          </span>
                          <div className="flex items-center gap-1.5">
                            <span className="font-semibold text-slate-800">
                              {b.real_steady !== '-' && b.real_steady != null ? `${b.real_steady}m` : '-'}
                            </span>
                            {b.ideal_steady != null && (
                              <span className="text-[10px] text-slate-500 font-medium">
                                (Idl: {b.ideal_steady}m)
                              </span>
                            )}
                            {b.delta_steady != null && (
                              <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${
                                b.delta_steady > 10 ? 'bg-red-100 text-red-700' :
                                b.delta_steady > 0 ? 'bg-amber-100 text-amber-800' :
                                'bg-emerald-100 text-emerald-800'
                              }`}>
                                {b.delta_steady > 0 ? `+${b.delta_steady}m` : `${b.delta_steady}m`}
                              </span>
                            )}
                          </div>
                        </div>
                        <div className="text-[10px] text-slate-500 flex justify-between pt-1 border-t border-slate-100">
                          <span>Suhu Puncak: <b>130°C+</b></span>
                          <span className={b.delta_steady && b.delta_steady > 10 ? 'text-amber-600 font-bold' : 'text-emerald-600 font-bold'}>
                            {b.delta_steady && b.delta_steady > 10 ? 'Overholding' : 'Stabil Sesuai Resep'}
                          </span>
                        </div>
                      </div>

                      {/* Fase Cooling */}
                      <div className="bg-white p-2.5 rounded-lg border border-slate-200">
                        <div className="flex justify-between items-center mb-1">
                          <span className="font-bold text-slate-700 flex items-center gap-1">
                            <Droplets size={12} className="text-blue-500" /> Cooling:
                          </span>
                          <div className="flex items-center gap-1.5">
                            <span className="font-semibold text-slate-800">
                              {b.real_cooling !== '-' && b.real_cooling != null ? `${b.real_cooling}m` : '-'}
                            </span>
                            {b.ideal_cooling != null && (
                              <span className="text-[10px] text-slate-500 font-medium">
                                (Idl: {b.ideal_cooling}m)
                              </span>
                            )}
                            {b.delta_cooling != null && (
                              <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${
                                b.delta_cooling > 10 ? 'bg-red-100 text-red-700' :
                                b.delta_cooling > 0 ? 'bg-amber-100 text-amber-800' :
                                'bg-emerald-100 text-emerald-800'
                              }`}>
                                {b.delta_cooling > 0 ? `+${b.delta_cooling}m` : `${b.delta_cooling}m`}
                              </span>
                            )}
                          </div>
                        </div>
                        <div className="text-[10px] text-slate-500 flex justify-between pt-1 border-t border-slate-100">
                          <span>Air Pendingin:</span>
                          <span className={b.delta_cooling && b.delta_cooling > 10 ? 'text-red-600 font-bold' : 'text-emerald-600 font-bold'}>
                            {b.delta_cooling && b.delta_cooling > 10 ? `Lambat (+${b.delta_cooling}m)` : 'Sesuai Standar'}
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="mt-3 pt-2 border-t border-slate-200 flex justify-between items-center text-[11px]">
                    <span className="text-slate-500">
                      Total: <b>{b.total_durasi}m</b> {b.durasi_ideal && b.durasi_ideal !== '-' ? <span className="text-slate-400 font-normal">(Idl: {b.durasi_ideal}m)</span> : null}
                    </span>
                    <a
                      href={`/history/report/${b.id}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-indigo-600 hover:text-indigo-800 font-bold flex items-center gap-1"
                    >
                      Buka Audit &rarr;
                    </a>
                  </div>
                </div>
              );
            })}
          </div>
        </section>


        {/* ═══════════════════════════════════════════════════════════════════ */}
        {/* NEW SECTION C: PROGRAM BENCHMARK SUMMARY TABLE                     */}
        {/* ═══════════════════════════════════════════════════════════════════ */}
        <section className="bg-white rounded-2xl shadow-xs border border-slate-200 overflow-hidden">
          <div className="p-4 sm:p-5 border-b border-slate-100 bg-slate-50/50 flex justify-between items-center">
            <div>
              <h3 className="text-xs sm:text-sm font-semibold text-slate-900 uppercase tracking-wider flex items-center gap-2">
                <Award size={15} className="text-indigo-600" /> Benchmark Program Historis Mesin Ini (60 Batch)
              </h3>
              <p className="text-[11px] text-slate-500">Membandingkan durasi rata-rata aktual dengan master program standar</p>
            </div>
            <span className="text-xs font-bold text-slate-600">{data.program_benchmarks?.length || 0} Program Terdeteksi</span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left">
              <thead className="bg-slate-100/70 text-slate-600 text-[11px] uppercase tracking-wider border-b border-slate-200 font-bold">
                <tr>
                  <th className="px-4 py-3">Nama Program</th>
                  <th className="px-3 py-3 text-center">Batch Teruji</th>
                  <th className="px-3 py-3 text-right bg-slate-200/50 text-slate-700" title="Durasi Total Ideal Program">Durasi Ideal</th>
                  <th className="px-3 py-3 text-right bg-slate-200/50 text-slate-800" title="Rata-rata Durasi Total Aktual">Avg Total</th>
                  <th className="px-3 py-3 text-right bg-slate-200/50 text-indigo-700" title="Selisih Durasi Total terhadap Ideal">Δ Total</th>
                  <th className="px-3 py-3 text-right">Ideal Heat</th>
                  <th className="px-3 py-3 text-right">Avg Heat</th>
                  <th className="px-3 py-3 text-right">Δ Heat</th>
                  <th className="px-3 py-3 text-right">Ideal Cool</th>
                  <th className="px-3 py-3 text-right">Avg Cool</th>
                  <th className="px-3 py-3 text-right">Δ Cool</th>
                  <th className="px-3 py-3 text-right">Avg Tekanan Uap</th>
                  <th className="px-3 py-3 text-center whitespace-nowrap">Performa</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data.program_benchmarks && data.program_benchmarks.map(p => {
                  const heatDelayed = (p.delta_heat_avg || 0) > 15;
                  const coolDelayed = (p.delta_cool_avg || 0) > 10;
                  const totalDelayed = (p.delta_total_avg || 0) > 20;

                  return (
                    <tr key={p.program_name} className="hover:bg-slate-50 transition-colors">
                      <td className="px-4 py-3 font-semibold text-slate-800">{p.program_name}</td>
                      <td className="px-3 py-3 text-center font-bold text-slate-700">{p.batch_count}</td>
                      
                      {/* Total Duration Benchmark */}
                      <td className="px-3 py-3 text-right text-slate-500 bg-slate-50/50">{p.ideal_total != null ? `${p.ideal_total}m` : '-'}</td>
                      <td className="px-3 py-3 text-right font-bold text-slate-800 bg-slate-50/50">{p.avg_total != null ? `${p.avg_total}m` : '-'}</td>
                      <td className="px-3 py-3 text-right font-bold bg-slate-50/50">
                        {p.delta_total_avg != null ? (
                          <span className={totalDelayed ? 'text-red-600' : (p.delta_total_avg > 0 ? 'text-amber-600' : 'text-emerald-600')}>
                            {p.delta_total_avg > 0 ? `+${p.delta_total_avg}` : p.delta_total_avg}m
                          </span>
                        ) : '-'}
                      </td>

                      {/* Heating Benchmark */}
                      <td className="px-3 py-3 text-right text-slate-500">{p.ideal_heat != null ? `${p.ideal_heat}m` : '-'}</td>
                      <td className="px-3 py-3 text-right font-bold text-slate-800">{p.avg_heat != null ? `${p.avg_heat}m` : '-'}</td>
                      <td className="px-3 py-3 text-right font-bold">
                        {p.delta_heat_avg != null ? (
                          <span className={heatDelayed ? 'text-red-600' : 'text-emerald-600'}>
                            {p.delta_heat_avg > 0 ? `+${p.delta_heat_avg}` : p.delta_heat_avg}m
                          </span>
                        ) : '-'}
                      </td>

                      {/* Cooling Benchmark */}
                      <td className="px-3 py-3 text-right text-slate-500">{p.ideal_cool != null ? `${p.ideal_cool}m` : '-'}</td>
                      <td className="px-3 py-3 text-right font-bold text-slate-800">{p.avg_cool != null ? `${p.avg_cool}m` : '-'}</td>
                      <td className="px-3 py-3 text-right font-bold">
                        {p.delta_cool_avg != null ? (
                          <span className={coolDelayed ? 'text-red-600' : 'text-emerald-600'}>
                            {p.delta_cool_avg > 0 ? `+${p.delta_cool_avg}` : p.delta_cool_avg}m
                          </span>
                        ) : '-'}
                      </td>

                      {/* Steam Pressure & Status */}
                      <td className="px-3 py-3 text-right font-medium text-slate-700">{p.avg_pressure != null ? `${p.avg_pressure} bar` : '-'}</td>
                      <td className="px-3 py-3 text-center whitespace-nowrap">
                        <span className={`inline-block px-2.5 py-0.5 rounded-full font-semibold text-[10px] whitespace-nowrap ${
                          !heatDelayed && !coolDelayed && !totalDelayed ? 'bg-emerald-50 text-emerald-800 border border-emerald-200' :
                          heatDelayed && coolDelayed ? 'bg-red-50 text-red-800 border border-red-200' :
                          'bg-amber-50 text-amber-800 border border-amber-200'
                        }`}>
                          {!heatDelayed && !coolDelayed && !totalDelayed ? 'Optimal' :
                           heatDelayed && coolDelayed ? 'Heat & Cool Lag' :
                           heatDelayed ? 'Heat Lag' :
                           coolDelayed ? 'Cooling Lag' : 'Total Lag'}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>


        {/* ═══════════════════════════════════════════════════════════════════ */}
        {/* NEW SECTION D: TIMELINE TURNAROUND 24 JAM & CHANGEOVER GAP         */}
        {/* ═══════════════════════════════════════════════════════════════════ */}
        {data.turnaround_summary && (
          <section className="bg-white rounded-2xl shadow-xs border border-slate-200 p-4 sm:p-6 space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-100">
              <div>
                <h3 className="text-xs sm:text-sm font-semibold text-slate-900 uppercase tracking-wider flex items-center gap-2">
                  <Timer size={16} className="text-indigo-600" /> Peta Turnaround & Waktu Jeda Antar-Batch (24 Jam)
                </h3>
                <p className="text-xs text-slate-500">Mendeteksi kebocoran waktu saat mesin menganggur tanpa kain (*Idle Overhead Loss*)</p>
              </div>

              <div className="flex items-center gap-3 text-xs">
                <span>Operasi: <b className="text-indigo-700">{data.turnaround_summary.run_hours} Jam</b> ({data.turnaround_summary.uptime_percent}% Uptime)</span>
                <span className="text-slate-300">|</span>
                <span>Changeover: <b className="text-emerald-700">{data.turnaround_summary.changeover_hours} Jam</b></span>
                <span className="text-slate-300">|</span>
                <span>Idle Terbuang: <b className="text-red-600">{data.turnaround_summary.idle_hours} Jam</b></span>
              </div>
            </div>

            {/* Gantt Bar Visualization */}
            <div className="space-y-1.5">
              <div className="w-full h-8 bg-slate-100 rounded-xl overflow-hidden flex shadow-inner">
                {data.turnaround_summary.events.map((ev, i) => {
                  const widthPct = Math.max(2, (ev.duration_mins / (24 * 60)) * 100);
                  const isRun = ev.type === 'PROCESS';
                  const isChange = ev.type === 'CHANGEOVER';

                  return (
                    <div
                      key={i}
                      style={{ width: `${widthPct}%` }}
                      className={`h-full flex items-center justify-center text-[10px] font-bold text-white transition-opacity hover:opacity-80 cursor-pointer ${
                        isRun ? 'bg-indigo-600' : isChange ? 'bg-emerald-500' : 'bg-red-400'
                      }`}
                      title={`${ev.label} (${ev.start} - ${ev.end}, ${ev.duration_mins}m)`}
                    >
                      {widthPct > 6 ? (isRun ? `B#${ev.batch_number}` : `${ev.duration_mins}m`) : ''}
                    </div>
                  );
                })}
              </div>

              <div className="flex items-center justify-between text-[11px] text-slate-400 px-1">
                <span>06:00 WIB</span>
                <span>12:00 WIB</span>
                <span>18:00 WIB (WBP)</span>
                <span>00:00 WIB</span>
                <span>06:00 WIB</span>
              </div>
            </div>

            {/* Financial Impact of Idle */}
            {data.turnaround_summary.idle_hours > 0 && (
              <div className="bg-amber-50/70 border border-amber-200 rounded-xl p-3.5 flex items-center justify-between text-xs">
                <div>
                  <span className="font-bold text-amber-900 block">Kompensasi Biaya Menganggur (Opportunity Overhead Loss):</span>
                  <p className="text-amber-800 text-[11px] mt-0.5">
                    Mesin menganggur tanpa proses selama <b>{data.turnaround_summary.idle_hours} jam</b>. Berdasarkan standar overhead pabrik (Rp 65.000/jam), kerugian waktu kapasitas yang tidak terserap setara <b>{formatRp(data.turnaround_summary.idle_cost_rp)}</b>.
                  </p>
                </div>
                <div className="text-right shrink-0 ml-4 font-bold text-amber-700 text-sm">
                  {formatRp(data.turnaround_summary.idle_cost_rp)}
                </div>
              </div>
            )}
          </section>
        )}


        {/* ═══════════════════════════════════════════════════════════════════ */}
        {/* NEW SECTION E: PRESCRIPTIVE MAINTENANCE WORK ORDER (CHECKLIST)     */}
        {/* ═══════════════════════════════════════════════════════════════════ */}
        {data.maintenance_tickets && (
          <section className="bg-gradient-to-br from-slate-900 via-indigo-950 to-slate-900 rounded-2xl p-5 sm:p-6 text-white shadow-xl space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm sm:text-base font-bold uppercase tracking-wider text-indigo-200 flex items-center gap-2">
                  <Wrench className="w-5 h-5 text-indigo-400" /> Checklist Pemeliharaan & Tindakan Mekanik Mesin
                </h3>
                <p className="text-xs text-indigo-300 mt-0.5">
                  Perintah kerja mekanik (*Work Order*) otomatis yang dirumuskan dari deviasi fisik 60 batch
                </p>
              </div>
              <span className="text-[11px] font-bold bg-indigo-800/80 text-indigo-200 px-3 py-1 rounded-full border border-indigo-700">
                {data.maintenance_tickets.length} Tiket Tindakan
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
              {data.maintenance_tickets.length > 0 ? (
                data.maintenance_tickets.map((t, i) => (
                  <div key={i} className="bg-white/10 backdrop-blur-md rounded-xl p-4 border border-white/15 flex flex-col justify-between">
                    <div>
                      <div className="flex items-center justify-between text-[11px] mb-1.5">
                        <span className="font-bold text-indigo-300 uppercase tracking-wider">{t.component}</span>
                        <span className={`px-2 py-0.5 rounded font-semibold text-[10px] ${
                          t.priority === 'HIGH' ? 'bg-red-500 text-white' : 'bg-amber-500 text-white'
                        }`}>
                          {t.priority}
                        </span>
                      </div>
                      <h4 className="text-sm font-bold text-white leading-snug">{t.title}</h4>
                      <p className="text-xs text-slate-300 mt-1.5 leading-relaxed">{t.description}</p>
                    </div>

                    <div className="mt-3 pt-2.5 border-t border-white/10 flex items-start gap-2 text-[11px]">
                      <span className="text-indigo-300 font-bold shrink-0">Tindakan:</span>
                      <span className="text-white font-medium">{t.action}</span>
                    </div>
                  </div>
                ))
              ) : (
                <div className="col-span-2 text-center py-6 text-indigo-300 text-xs">
                  Semua indikator termal dan mekanik mesin dalam batas normal. Tidak ada tindakan pemeliharaan mendesak.
                </div>
              )}
            </div>
          </section>
        )}

      </main>
    </div>
  );
}
