import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer, ReferenceLine
} from 'recharts';
import {
  ArrowLeft, Printer, Calendar, ChevronLeft, ChevronRight, Activity, Flame,
  Clock, Droplets, Zap, AlertTriangle, CheckCircle2, AlertCircle, X,
  FileText, Sparkles, ExternalLink, ShieldCheck, UserCheck, Award
} from 'lucide-react';
import api, { BACKEND_BASE_URL } from '../lib/api';

const CANDIDATE_TIME_TICKS = [
  '06:00',
  '09:00',
  '12:00',
  '15:00',
  '18:00',
  '21:00',
  '00:00',
  '03:00',
  '06:00 '
];

const CANDIDATE_MINOR_TIME_TICKS = [
  '07:00', '08:00',
  '10:00', '11:00',
  '13:00', '14:00',
  '16:00', '17:00',
  '19:00', '20:00',
  '22:00', '23:00',
  '01:00', '02:00',
  '04:00', '05:00'
];

const MINOR_Y_TICKS = [
  36, 42, 48, 54,
  66, 72, 78, 84,
  96, 102, 108, 114,
  126, 132, 138, 144
];

export default function MachineDailyAnalytics() {
  const { machineId, date } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showPrintPreview, setShowPrintPreview] = useState(false);

  const chartTicks = React.useMemo(() => {
    if (!data?.chart_data || data.chart_data.length === 0) return undefined;
    const timeSet = new Set(data.chart_data.map(d => d.time));
    const matched = CANDIDATE_TIME_TICKS.filter(t => timeSet.has(t));
    return matched.length >= 2 ? matched : undefined;
  }, [data]);

  const minorXTicks = React.useMemo(() => {
    if (!data?.chart_data || data.chart_data.length === 0) return [];
    const timeSet = new Set(data.chart_data.map(d => d.time));
    return CANDIDATE_MINOR_TIME_TICKS.filter(t => timeSet.has(t));
  }, [data]);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const res = await api.get(`/report/machine/${machineId}/daily-chart?date=${date}`);
        setData(res.data);
      } catch (err) {
        console.error(err);
        setError('Gagal memuat data analitik mesin.');
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [machineId, date]);

  // Handler for navigation by date
  const changeDate = (days) => {
    try {
      const cur = new Date(date);
      cur.setDate(cur.getDate() + days);
      const nextStr = cur.toISOString().split('T')[0];
      navigate(`/machine-daily-analytics/${machineId}/${nextStr}`);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    if (showPrintPreview) {
      const timer = setTimeout(() => {
        window.dispatchEvent(new Event('resize'));
      }, 60);
      return () => clearTimeout(timer);
    }
  }, [showPrintPreview]);

  const handleOpenPrintPreview = () => {
    setShowPrintPreview(true);
  };

  const handlePrint = () => {
    let style = document.getElementById('process-daily-print-page-style');
    if (!style) {
      style = document.createElement('style');
      style.id = 'process-daily-print-page-style';
      style.textContent = '@page { size: A4 landscape; margin: 5mm 5mm; }';
      document.head.appendChild(style);
    }
    document.documentElement.classList.add('printing-process-daily');
    document.body.classList.add('printing-process-daily');
    window.dispatchEvent(new Event('resize'));

    const cleanup = () => {
      document.documentElement.classList.remove('printing-process-daily');
      document.body.classList.remove('printing-process-daily');
      document.getElementById('process-daily-print-page-style')?.remove();
    };

    window.addEventListener('afterprint', cleanup, { once: true });
    setTimeout(() => {
      window.print();
    }, 160);
  };

  const num = (v, dec = 1) => {
    if (v == null || v === '-' || isNaN(v)) return '-';
    return Number(v).toLocaleString('id-ID', { minimumFractionDigits: 0, maximumFractionDigits: dec });
  };

  const formatRp = (v) => {
    if (v == null || isNaN(v)) return 'Rp 0';
    return 'Rp ' + Math.round(v).toLocaleString('id-ID');
  };

  const formatDelta = (val) => {
    if (val == null || val === '-') return <span className="text-gray-400">-</span>;
    const n = Number(val);
    if (isNaN(n)) return <span className="text-gray-400">-</span>;
    if (n === 0) return <span className="text-gray-600 font-medium">0m</span>;
    const isLate = n > 0;
    return (
      <span className={`font-semibold tabular-nums ${isLate ? 'text-red-600' : 'text-emerald-600'}`}>
        {isLate ? `+${n}` : n}m
      </span>
    );
  };

  const formatLoss = (val, unit = 'm') => {
    if (val == null || val === '-') return <span className="text-gray-400">-</span>;
    const n = Number(val);
    if (isNaN(n)) return <span className="text-gray-400">-</span>;
    if (n === 0) return <span className="text-gray-500 font-medium">0{unit}</span>;
    const isLate = n > 0;
    return (
      <span className={`font-semibold tabular-nums ${isLate ? 'text-red-600' : 'text-emerald-600'}`}>
        {isLate ? `+${n}` : n}{unit}
      </span>
    );
  };

  const formatPhaseReal = (realVal, deltaVal) => {
    if (realVal == null || realVal === '-') return <span className="text-slate-400">-</span>;
    const realStr = `${realVal}m`;
    if (deltaVal == null || deltaVal === 0) {
      return <span className="font-semibold text-slate-800 tabular-nums">{realStr}</span>;
    }
    const isLate = deltaVal > 0;
    const deltaStr = isLate ? `(+${deltaVal}m)` : `(${deltaVal}m)`;
    return (
      <span className="font-semibold text-slate-800 tabular-nums">
        {realStr}{' '}
        <span className={`text-[10px] font-bold ${isLate ? 'text-red-600' : 'text-emerald-600'}`}>
          {deltaStr}
        </span>
      </span>
    );
  };

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-gray-50">
        <div className="flex flex-col items-center gap-3">
          <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-indigo-600" />
          <span className="text-xs text-gray-500 font-medium">Memuat analitik proses mesin...</span>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="flex h-screen items-center justify-center bg-gray-50 p-6">
        <div className="bg-white rounded-2xl shadow-sm border border-red-200 p-8 max-w-md text-center">
          <AlertCircle className="w-12 h-12 text-red-500 mx-auto mb-3" />
          <h2 className="text-base font-bold text-gray-800 mb-1">Gagal Memuat Data Mesin</h2>
          <p className="text-gray-500 text-xs mb-5">{error || 'Data tidak ditemukan'}</p>
          <button
            onClick={() => { if (window.history.state && typeof window.history.state.idx === "number" && window.history.state.idx > 0) { navigate(-1); } else { navigate("/daily-report"); } }}
            className="px-4 py-2 bg-gray-100 hover:bg-gray-200 text-gray-700 text-xs font-semibold rounded-lg transition-colors"
          >
            Kembali
          </button>
        </div>
      </div>
    );
  }

  const isHto = data.energy_type === 'HTO';
  const companyLogoUrl = data.company?.logo
    ? (data.company.logo.startsWith('http') ? data.company.logo : `${BACKEND_BASE_URL}${data.company.logo}`)
    : null;

  // Check if any batch has problem or notes
  const batchesWithNotes = (data.batches || []).filter(b => (b.masalah && b.masalah !== '-') || (b.keterangan && b.keterangan !== '-'));

  return (
    <div className="h-full overflow-y-auto bg-slate-50/60 pb-16 font-sans text-slate-800">
      
      {/* 🖥️ MAIN INTERACTIVE SCREEN (HIDDEN COMPLETELY DURING PRINT) */}
      <div className="main-screen-view">
        {/* 🚀 STICKY COMPACT TOOLBAR 🚀 */}
      <header className="sticky top-0 z-30 bg-white/95 backdrop-blur-md border-b border-slate-200 px-3 sm:px-6 py-2.5 flex items-center justify-between gap-3 shadow-xs no-print">
        <div className="flex items-center gap-3 min-w-0">
          <button
            onClick={() => navigate('/daily-report')}
            className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-600 transition-colors"
            title="Kembali ke Laporan Harian"
          >
            <ArrowLeft size={18} />
          </button>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h1 className="text-base sm:text-lg font-bold text-slate-900 truncate">
                {data.machine_name}
              </h1>
              <span className="text-xs px-2 py-0.5 rounded-md bg-indigo-50 text-indigo-700 font-bold border border-indigo-200 font-mono">
                {data.machine_code || data.machine_name}
              </span>
              <span className="hidden sm:inline-flex text-[11px] font-semibold text-slate-500 bg-slate-100 px-2 py-0.5 rounded">
                Grup: {data.machine_group || '-'}
              </span>
            </div>
            <p className="text-[11px] text-slate-500 truncate flex items-center gap-1.5">
              <span>Periode: <b>{data.date_range} WIB</b></span>
              <span className="text-slate-300">&bull;</span>
              <span>Energi: <b className={isHto ? 'text-amber-600' : 'text-blue-600'}>{data.energy_type || 'STEAM'}</b></span>
            </p>
          </div>
        </div>

        {/* Date Navigator + Mode Switcher + Print Button */}
        <div className="flex items-center gap-2 shrink-0">
          {/* Quick Date Navigator */}
          <div className="hidden md:flex items-center bg-slate-100 rounded-lg p-0.5 border border-slate-200 text-xs">
            <button
              onClick={() => changeDate(-1)}
              className="p-1.5 hover:bg-white rounded-md text-slate-600 transition-colors"
              title="Hari Sebelumnya"
            >
              <ChevronLeft size={14} />
            </button>
            <span className="px-2 font-semibold text-slate-700 font-mono text-[11px]">{date}</span>
            <button
              onClick={() => changeDate(1)}
              className="p-1.5 hover:bg-white rounded-md text-slate-600 transition-colors"
              title="Hari Berikutnya"
            >
              <ChevronRight size={14} />
            </button>
          </div>

          {/* Switcher to MachineDailyAnalytics1 (Energy Deep Dossier) */}
          <button
            onClick={() => navigate(`/machine-daily-deep-analytics/${machineId}/${date}`)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 text-xs font-semibold rounded-lg border border-indigo-200 transition-colors shadow-2xs"
            title="Buka pelacakan konsumsi energi & scatter analitik 60 batch"
          >
            <Zap size={14} className="text-indigo-600" />
            <span className="hidden lg:inline">Tracking Energi (V2) &rarr;</span>
            <span className="lg:hidden">Energi &rarr;</span>
          </button>

          {/* Print Preview Button */}
          <button
            onClick={handleOpenPrintPreview}
            className="inline-flex items-center gap-1.5 px-3.5 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold rounded-lg transition-colors shadow-2xs"
            title="Buka Pratinjau Cetak Formal (A4 Landscape)"
          >
            <Printer size={15} />
            <span>Pratinjau Cetak</span>
          </button>
        </div>
      </header>

      {/* 📄 MAIN CONTENT CONTAINER 📄 */}
      <main className="p-3 sm:p-6 space-y-5 max-w-[1500px] mx-auto daily-analytics-content">

        {/* ═══════════════════════════════════════════════════════════════════ */}
        {/* BAGIAN 1: GRAFIK PROFIL SUHU AKTUAL MESIN (24 JAM, 06:00 - 06:00)   */}
        {/* ═══════════════════════════════════════════════════════════════════ */}
        <div className="bg-white rounded-2xl shadow-xs border border-slate-200 p-4 sm:p-5">
          <div className="flex flex-wrap items-center justify-between gap-3 mb-2">
            <div>
              <h2 className="text-xs sm:text-sm font-bold text-slate-900 flex items-center gap-2">
                <Activity size={16} className="text-indigo-600" />
                <span>Profil Suhu Aktual Mesin vs {isHto ? 'Temperatur HTO' : 'Tekanan Steam'} (24 Jam)</span>
              </h2>
              <p className="text-[11px] text-slate-500 mt-0.5">
                Pemantauan fluktuasi termal mesin kontinu dari jam 06:00 s/d 06:00 WIB
              </p>
            </div>

            <div className="flex items-center gap-4 text-xs font-semibold">
              <div className="flex items-center gap-1.5 text-slate-700">
                <span className="w-4 h-1 bg-red-500 rounded-full inline-block" />
                <span>Suhu Aktual (°C)</span>
              </div>
              <div className="flex items-center gap-1.5 text-slate-700">
                <span className={`w-4 h-0 border-t-2 border-dashed ${isHto ? 'border-amber-500' : 'border-blue-600'} inline-block`} />
                <span>{isHto ? 'Temperatur HTO (°C)' : 'Tekanan Steam (bar)'}</span>
              </div>
            </div>
          </div>

          <div className="h-[280px] sm:h-[340px] w-full min-w-0">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data.chart_data} margin={{ top: 12, right: 12, left: 6, bottom: 0 }}>
                {/* Kisi Mayor (Solid #9ec5e8, interval 30°C & 3 jam) */}
                <CartesianGrid syncWithTicks={true} yAxisId="left" stroke="#9ec5e8" strokeWidth={1} vertical={true} />
                
                {/* Kisi Minor Horisontal (Suhu step 6°C, dashed #b7d0e6) */}
                {MINOR_Y_TICKS.map((val) => (
                  <ReferenceLine
                    key={`screen-minor-y-${val}`}
                    yAxisId="left"
                    y={val}
                    stroke="#b7d0e6"
                    strokeWidth={0.7}
                    strokeDasharray="3 2"
                    ifOverflow="discard"
                  />
                ))}

                {/* Kisi Minor Vertikal (Jam per 1 jam: 07:00, 08:00, 10:00, 11:00, dst., dashed #b7d0e6) */}
                {minorXTicks.map((val) => (
                  <ReferenceLine
                    key={`screen-minor-x-${val}`}
                    yAxisId="left"
                    x={val}
                    stroke="#b7d0e6"
                    strokeWidth={0.85}
                    strokeDasharray="3 2"
                    ifOverflow="discard"
                  />
                ))}

                <XAxis
                  dataKey="time"
                  ticks={chartTicks}
                  tickFormatter={(v) => (typeof v === 'string' ? v.trim() : v)}
                  tick={{ fontSize: 11, fill: '#1e3a5f' }}
                  axisLine={{ stroke: '#6ba3cc', strokeWidth: 1.2 }}
                  tickLine={{ stroke: '#6ba3cc' }}
                  padding={{ left: 0, right: 0 }}
                />
                <YAxis
                  yAxisId="left"
                  width={42}
                  tick={{ fontSize: 11, fill: '#ef4444' }}
                  axisLine={{ stroke: '#6ba3cc', strokeWidth: 1.2 }}
                  tickLine={{ stroke: '#6ba3cc' }}
                  domain={[30, 150]}
                  ticks={[30, 60, 90, 120, 150]}
                />
                <YAxis
                  yAxisId="right"
                  orientation="right"
                  width={isHto ? 36 : 28}
                  domain={isHto ? [0, 300] : [0, (dataMax) => Math.max(6, Math.ceil(dataMax || 6))]}
                  tick={{ fontSize: 11, fill: isHto ? '#d97706' : '#2563eb' }}
                  axisLine={{ stroke: '#6ba3cc', strokeWidth: 1.2 }}
                  tickLine={{ stroke: '#6ba3cc' }}
                />
                <RechartsTooltip
                  labelFormatter={(v) => (typeof v === 'string' ? v.trim() : v)}
                  contentStyle={{ borderRadius: '10px', border: 'none', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)', fontSize: '12px' }}
                />
                <Line yAxisId="left" type="monotone" dataKey="temp" stroke="#ef4444" strokeWidth={2.2} dot={false} name="Suhu Mesin (°C)" />
                <Line
                  yAxisId="right"
                  type="monotone"
                  dataKey="pressure"
                  stroke={isHto ? '#d97706' : '#2563eb'}
                  strokeWidth={1.8}
                  strokeDasharray="4 4"
                  dot={false}
                  name={isHto ? 'Temp HTO (°C)' : 'Tekanan Steam (bar)'}
                />
                {!isHto && (
                  <ReferenceLine
                    yAxisId="right"
                    y={3.8}
                    stroke="#f59e0b"
                    strokeDasharray="3 3"
                    label={{ value: '3.8 bar threshold', fill: '#d97706', fontSize: 10, position: 'insideTopLeft' }}
                  />
                )}
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* ═══════════════════════════════════════════════════════════════════ */}
        {/* BAGIAN 2: DYEING PROCESS ANALYTICS (TABEL UTAMA PELACAKAN PROSES)  */}
        {/* ═══════════════════════════════════════════════════════════════════ */}
        <section className="bg-white rounded-2xl shadow-xs border border-slate-200 overflow-hidden space-y-6 p-4 sm:p-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-100">
            <div>
              <div className="flex items-center gap-2">
                <FileText className="w-5 h-5 text-indigo-600" />
                <h2 className="text-base font-bold text-slate-900 tracking-tight">
                  Dyeing Process Analytics (Pelacakan Proses Harian)
                </h2>
              </div>
              <p className="text-xs text-slate-500 mt-0.5">
                Seluruh perhitungan waktu siklus & fase dimulai dari <b>Real Heat</b> s/d <b>Selesai</b>. Data siap diekspor/cetak untuk meeting evaluasi.
              </p>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <span className="text-xs font-semibold text-slate-600 bg-slate-100 px-3 py-1 rounded-lg">
                Total: <b>{data.batches?.length || 0} Batch Selesai</b>
              </span>
            </div>
          </div>

          {/* ───────────────────────────────────────────────────────────────── */}
          {/* TABEL A: IDENTITAS KAIN & WAKTU SIKLUS                            */}
          {/* ───────────────────────────────────────────────────────────────── */}
          <div>
            <div className="flex items-center justify-between mb-2.5">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-700 flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-indigo-600" />
                Tabel 1: Identitas Kain & Waktu Siklus (Per Proses)
              </h3>
              <span className="text-[11px] text-slate-400">Dimulai dari Real Heat</span>
            </div>

            <div className="overflow-x-auto border border-slate-200 rounded-xl">
              <table className="w-full text-xs text-center border-collapse">
                <thead className="bg-slate-100/80 text-slate-700 text-[11px] font-bold border-b border-slate-200">
                  <tr className="divide-x divide-slate-200">
                    <th className="px-2 py-2.5 text-center whitespace-nowrap">No. Batch</th>
                    <th className="px-2 py-2.5 text-center whitespace-nowrap bg-indigo-50/50 text-indigo-900">Jam Mulai (Heat)</th>
                    <th className="px-2 py-2.5 text-center whitespace-nowrap bg-indigo-50/50 text-indigo-900">Jam Selesai</th>
                    <th className="px-2 py-2.5 text-center whitespace-nowrap">Batch Kain</th>
                    <th className="px-2 py-2.5 text-center whitespace-nowrap">No. Order</th>
                    <th className="px-2 py-2.5 text-center whitespace-nowrap">Buyer</th>
                    <th className="px-2 py-2.5 text-center whitespace-nowrap">Artikel Kain</th>
                    <th className="px-2 py-2.5 text-center whitespace-nowrap">Warna / Desain</th>
                    <th className="px-2 py-2.5 text-center whitespace-nowrap">Jenis Proses</th>
                    <th className="px-2 py-2.5 text-center whitespace-nowrap">Master Program</th>
                    <th className="px-2 py-2.5 text-center whitespace-nowrap">Tube</th>
                    <th className="px-2 py-2.5 text-center whitespace-nowrap">Nozzle / Main Pump</th>
                    <th className="px-2 py-2.5 text-center whitespace-nowrap">Operator</th>
                    <th className="px-2 py-2.5 text-center whitespace-nowrap bg-indigo-50/50 font-bold text-indigo-900">Durasi Aktual</th>
                    <th className="px-2 py-2.5 text-center whitespace-nowrap text-slate-600">Durasi Ideal</th>
                    <th className="px-2 py-2.5 text-center whitespace-nowrap">Loss Time</th>
                    <th className="px-2 py-2.5 text-center whitespace-nowrap">Efisiensi</th>
                    <th className="px-2 py-2.5 text-center whitespace-nowrap no-print">Aksi</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {data.batches && data.batches.length > 0 ? (
                    data.batches.map((b) => {
                      const effBadgeCls = (b.eff_total >= 80)
                        ? 'bg-emerald-100 text-emerald-800'
                        : (b.eff_total >= 60)
                        ? 'bg-amber-100 text-amber-800'
                        : 'bg-red-100 text-red-800';

                      return (
                        <tr key={b.id} className="hover:bg-slate-50 transition-colors divide-x divide-slate-100">
                          <td className="px-2 py-2 text-center font-bold text-slate-900 whitespace-nowrap">
                            #{b.batch_number}
                          </td>
                          <td className="px-2 py-2 text-center font-mono font-medium text-slate-800 bg-indigo-50/20 whitespace-nowrap">
                            {b.jam_mulai}
                          </td>
                          <td className="px-2 py-2 text-center font-mono font-medium text-slate-800 bg-indigo-50/20 whitespace-nowrap">
                            {b.jam_selesai}
                          </td>
                          <td className="px-2 py-2 text-center font-mono text-slate-800 whitespace-nowrap">{b.batch_kain}</td>
                          <td className="px-2 py-2 text-center text-slate-700 whitespace-nowrap">{b.no_order}</td>
                          <td className="px-2 py-2 text-center text-slate-700 whitespace-nowrap">{b.kode_buyer}</td>
                          <td className="px-2 py-2 text-center text-slate-800 font-medium max-w-[160px] truncate mx-auto" title={b.artikel}>
                            {b.artikel}
                          </td>
                          <td className="px-2 py-2 text-center text-slate-700 whitespace-nowrap">{b.warna_desain}</td>
                          <td className="px-2 py-2 text-center text-slate-700 whitespace-nowrap">
                            <span className="px-2 py-0.5 rounded bg-slate-100 text-slate-700 font-medium text-[11px]">
                              {b.jenis_proses}
                            </span>
                          </td>
                          <td className="px-2 py-2 text-center text-indigo-700 font-semibold max-w-[150px] truncate mx-auto" title={b.program}>
                            {b.program}
                          </td>
                          <td className="px-2 py-2 text-center text-slate-700 whitespace-nowrap">{b.isi_per_tube}</td>
                          <td className="px-2 py-2 text-center font-mono text-slate-800 whitespace-nowrap">
                            {b.nozzle_main_pump || '-'}
                          </td>
                          <td className="px-2 py-2 text-center text-slate-700 whitespace-nowrap">{b.operator}</td>
                          <td className="px-2 py-2 text-center font-bold font-mono text-slate-900 bg-indigo-50/20 whitespace-nowrap">
                            {b.total_durasi !== '-' ? `${b.total_durasi}m` : '-'}
                          </td>
                          <td className="px-2 py-2 text-center text-slate-500 font-mono whitespace-nowrap">
                            {b.durasi_ideal !== '-' ? `${b.durasi_ideal}m` : '-'}
                          </td>
                          <td className="px-2 py-2 text-center whitespace-nowrap">
                            {formatLoss(b.loss_time, 'm')}
                          </td>
                          <td className="px-2 py-2 text-center whitespace-nowrap">
                            {b.eff_total != null ? (
                              <span className={`px-2 py-0.5 rounded-full font-bold text-[10px] ${effBadgeCls}`}>
                                {b.eff_total}%
                              </span>
                            ) : (
                              <span className="text-slate-400">-</span>
                            )}
                          </td>
                          <td className="px-2 py-2 text-center whitespace-nowrap no-print">
                            <a
                              href={`/history/report/${b.id}`}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex items-center gap-1 text-blue-600 hover:text-blue-800 font-semibold px-2 py-0.5 rounded hover:bg-blue-50 transition-colors text-[11px]"
                            >
                              Detail <ExternalLink size={11} />
                            </a>
                          </td>
                        </tr>
                      );
                    })
                  ) : (
                    <tr>
                      <td colSpan="18" className="px-4 py-8 text-center text-slate-400">
                        Tidak ada proses batch yang tercatat pada hari ini.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* ───────────────────────────────────────────────────────────────── */}
          {/* TABEL B: DETAIL FASE & PARAMETER TERMAL                           */}
          {/* ───────────────────────────────────────────────────────────────── */}
          <div>
            <div className="flex items-center justify-between mb-2.5">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-700 flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-amber-500" />
                Tabel 2: Detail Fase & Parameter Termal (Per Proses)
              </h3>
              <span className="text-[11px] text-slate-400">Dekomposisi Heating, Steady, Cooling & Boiler</span>
            </div>

            <div className="overflow-x-auto border border-slate-200 rounded-xl">
              <table className="w-full text-xs text-center border-collapse">
                <thead className="bg-slate-100/80 text-slate-700 text-[11px] font-bold border-b border-slate-200">
                  <tr className="divide-x divide-slate-200">
                    <th className="px-2.5 py-2.5 text-center whitespace-nowrap">No. Batch</th>
                    <th className="px-2.5 py-2.5 text-center whitespace-nowrap bg-red-50/50 text-red-900" title="Heating Standar Ideal">Heat Idl</th>
                    <th className="px-2.5 py-2.5 text-center whitespace-nowrap bg-red-50/70 text-red-900" title="Heating Aktual & Selisih (+/-)">Heat Real</th>
                    <th className="px-2.5 py-2.5 text-center whitespace-nowrap bg-amber-50/50 text-amber-900" title="Steady (Hold) Standar Ideal">Steady Idl</th>
                    <th className="px-2.5 py-2.5 text-center whitespace-nowrap bg-amber-50/70 text-amber-900" title="Steady (Hold) Aktual & Selisih (+/-)">Steady Real</th>
                    <th className="px-2.5 py-2.5 text-center whitespace-nowrap bg-blue-50/50 text-blue-900" title="Cooling Standar Ideal">Cool Idl</th>
                    <th className="px-2.5 py-2.5 text-center whitespace-nowrap bg-blue-50/70 text-blue-900" title="Cooling Aktual & Selisih (+/-)">Cool Real</th>
                    <th className="px-2.5 py-2.5 text-center whitespace-nowrap">Suhu Awal</th>
                    <th className="px-2.5 py-2.5 text-center whitespace-nowrap font-bold text-slate-700 bg-slate-50" title="Suhu Puncak Master Program">Suhu Prog.</th>
                    <th className="px-2.5 py-2.5 text-center whitespace-nowrap font-bold text-red-700" title="Suhu Puncak Aktual Tercapai">Suhu Puncak</th>
                    <th className="px-2.5 py-2.5 text-center whitespace-nowrap" title="Laju Pemanasan (°C/menit)">Gradien Heat</th>
                    <th className="px-2.5 py-2.5 text-center whitespace-nowrap" title="Laju Pendinginan (°C/menit)">Gradien Cool</th>
                    <th className="px-2.5 py-2.5 text-center whitespace-nowrap font-semibold text-blue-700">Avg Steam Pr</th>
                    <th className="px-2.5 py-2.5 text-center whitespace-nowrap" title="Waktu tunggu bongkar kain (<70°C s/d OFF). Standar toleransi ≤45m.">Bongkar (Handling)</th>
                    <th className="px-2.5 py-2.5 text-center whitespace-nowrap" title="Waktu siklus kain pada suhu puncak">Cycle Puncak</th>
                    <th className="px-2.5 py-2.5 text-center whitespace-nowrap" title="Waktu siklus kain pada suhu 60°C">Cycle 60</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {data.batches && data.batches.length > 0 ? (
                    data.batches.map((b) => {


                      return (
                        <tr key={b.id} className="hover:bg-slate-50 transition-colors divide-x divide-slate-100">
                          <td className="px-2.5 py-2 text-center font-bold text-slate-900 whitespace-nowrap">
                            #{b.batch_number}
                          </td>

                          {/* Heating Ideal & Real */}
                          <td className="px-2.5 py-2 text-center whitespace-nowrap bg-red-50/20 font-mono text-slate-600">
                            {b.ideal_heating != null ? `${b.ideal_heating}m` : '-'}
                          </td>
                          <td className="px-2.5 py-2 text-center whitespace-nowrap bg-red-50/30 font-mono">
                            {formatPhaseReal(b.real_heating, b.delta_heating)}
                          </td>

                          {/* Steady Ideal & Real */}
                          <td className="px-2.5 py-2 text-center whitespace-nowrap bg-amber-50/20 font-mono text-slate-600">
                            {b.ideal_steady != null ? `${b.ideal_steady}m` : '-'}
                          </td>
                          <td className="px-2.5 py-2 text-center whitespace-nowrap bg-amber-50/30 font-mono">
                            {formatPhaseReal(b.real_steady, b.delta_steady)}
                          </td>

                          {/* Cooling Ideal & Real */}
                          <td className="px-2.5 py-2 text-center whitespace-nowrap bg-blue-50/20 font-mono text-slate-600">
                            {b.ideal_cooling != null ? `${b.ideal_cooling}m` : '-'}
                          </td>
                          <td className="px-2.5 py-2 text-center whitespace-nowrap bg-blue-50/30 font-mono">
                            {formatPhaseReal(b.real_cooling, b.delta_cooling)}
                          </td>

                          {/* Temperatures */}
                          <td className="px-2.5 py-2 text-center font-mono text-slate-700 whitespace-nowrap">
                            {b.start_temp !== '-' ? `${b.start_temp}°C` : '-'}
                          </td>
                          <td className="px-2.5 py-2 text-center font-mono font-semibold text-slate-800 bg-slate-50 whitespace-nowrap">
                            {b.suhu_prog !== '-' && b.suhu_prog != null ? `${b.suhu_prog}°C` : '-'}
                          </td>
                          <td className="px-2.5 py-2 text-center font-mono font-bold text-red-600 whitespace-nowrap">
                            {b.max_temp !== '-' ? `${b.max_temp}°C` : '-'}
                          </td>

                          {/* Gradients */}
                          <td className="px-2.5 py-2 text-center font-mono text-slate-700 whitespace-nowrap">
                            {b.heating_gradient !== '-' ? `${b.heating_gradient}°C/m` : '-'}
                          </td>
                          <td className="px-2.5 py-2 text-center font-mono text-slate-700 whitespace-nowrap">
                            {b.cooling_gradient !== '-' ? `${b.cooling_gradient}°C/m` : '-'}
                          </td>

                          {/* Steam Pressure */}
                          <td className="px-2.5 py-2 text-center font-mono font-semibold text-blue-700 whitespace-nowrap">
                            {b.avg_steam_pressure !== '-' ? `${b.avg_steam_pressure} bar` : '-'}
                          </td>

                          {/* Handling (Bongkar) */}
                          <td className="px-2.5 py-2 text-center font-mono whitespace-nowrap">
                            {b.late_stop_mins != null ? (
                              <span className={b.late_stop_mins > 45 ? "text-red-600 font-bold" : "text-slate-800"}>
                                {b.late_stop_mins}m
                              </span>
                            ) : (
                              <span className="text-slate-400">-</span>
                            )}
                          </td>

                          {/* Cycle Puncak */}
                          <td className="px-2.5 py-2 text-center font-mono font-medium text-slate-800 whitespace-nowrap">
                            {b.cycle_puncak || '-'}
                          </td>

                          {/* Cycle 60 */}
                          <td className="px-2.5 py-2 text-center font-mono font-medium text-slate-800 whitespace-nowrap">
                            {b.cycle_60 || '-'}
                          </td>
                        </tr>
                      );
                    })
                  ) : (
                    <tr>
                      <td colSpan="12" className="px-4 py-8 text-center text-slate-400">
                        Tidak ada rincian fase batch untuk ditampilkan.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* ───────────────────────────────────────────────────────────────── */}
          {/* SECTION C: CATATAN & MASALAH PROSES (JIKA ADA MASALAH)           */}
          {/* ───────────────────────────────────────────────────────────────── */}
          {batchesWithNotes.length > 0 && (
            <div className="bg-amber-50/70 border border-amber-200 rounded-xl p-4 space-y-2">
              <div className="flex items-center gap-2 text-amber-900 font-bold text-xs uppercase tracking-wider">
                <AlertTriangle size={15} className="text-amber-600" />
                Catatan Pengawas & Kendala Operasional (Batch Notes)
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs text-left border-collapse">
                  <thead className="text-[11px] font-bold text-amber-900 border-b border-amber-200">
                    <tr>
                      <th className="py-1.5 px-3 w-24">No. Batch</th>
                      <th className="py-1.5 px-3">Kendala / Masalah yang Dihadapi</th>
                      <th className="py-1.5 px-3">Catatan / Tindakan Operator</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-amber-100">
                    {batchesWithNotes.map((b) => (
                      <tr key={b.id}>
                        <td className="py-2 px-3 font-bold font-mono text-slate-900 align-top">#{b.batch_number}</td>
                        <td className="py-2 px-3 text-red-700 font-medium align-top">{b.masalah || '-'}</td>
                        <td className="py-2 px-3 text-slate-700 align-top">{b.keterangan || '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </section>

        {/* ═══════════════════════════════════════════════════════════════════ */}
        {/* BAGIAN 3: RINGKASAN ENERGI HARIAN & LOSSES (PINDAH KE BAWAH)        */}
        {/* ═══════════════════════════════════════════════════════════════════ */}
        {data.summary && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            
            {/* Card 1: Summary Energi Harian */}
            <div className="bg-white rounded-2xl shadow-xs border border-slate-200 p-4 sm:p-5 flex flex-col justify-between">
              <div>
                <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider flex items-center gap-2 mb-3">
                  <Zap size={16} className="text-amber-500" /> Ringkasan Pemakaian Energi Harian
                </h3>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5 text-xs">
                  
                  <div className="bg-slate-50 border border-slate-100 p-2.5 rounded-xl">
                    <span className="text-[10px] text-slate-400 font-bold uppercase block">Steam Usage</span>
                    <span className="text-base font-bold text-slate-800 tabular-nums">
                      {num(data.summary.steam_usage)} <span className="text-[10px] font-normal text-slate-400">kg</span>
                    </span>
                  </div>

                  <div className="bg-slate-50 border border-slate-100 p-2.5 rounded-xl">
                    <span className="text-[10px] text-slate-400 font-bold uppercase block">Steam Eff</span>
                    <span className={`text-base font-bold tabular-nums ${data.summary.steam_eff >= 80 ? 'text-emerald-600' : 'text-amber-600'}`}>
                      {num(data.summary.steam_eff)}%
                    </span>
                  </div>

                  <div className="bg-slate-50 border border-slate-100 p-2.5 rounded-xl">
                    <span className="text-[10px] text-slate-400 font-bold uppercase block">% Sehat Uap</span>
                    <span className="text-base font-bold text-slate-800 tabular-nums">{num(data.summary.steam_ok_pct)}%</span>
                  </div>

                  <div className="bg-slate-50 border border-slate-100 p-2.5 rounded-xl">
                    <span className="text-[10px] text-slate-400 font-bold uppercase block">Listrik WBP</span>
                    <span className="text-base font-bold text-purple-700 tabular-nums">
                      {num(data.summary.total_power_wbp_kwh)} <span className="text-[10px] font-normal text-slate-400">kWh</span>
                    </span>
                  </div>

                  <div className="bg-slate-50 border border-slate-100 p-2.5 rounded-xl">
                    <span className="text-[10px] text-slate-400 font-bold uppercase block">Listrik LWBP</span>
                    <span className="text-base font-bold text-blue-700 tabular-nums">
                      {num(data.summary.total_power_lwbp_kwh)} <span className="text-[10px] font-normal text-slate-400">kWh</span>
                    </span>
                  </div>

                  <div className="bg-slate-50 border border-slate-100 p-2.5 rounded-xl">
                    <span className="text-[10px] text-slate-400 font-bold uppercase block">Udara Tekan</span>
                    <span className="text-base font-bold text-slate-400 tabular-nums">0 <span className="text-[10px] font-normal text-slate-400">NLiter</span></span>
                  </div>

                </div>
              </div>
            </div>

            {/* Card 2: Losses & Potensi Penghematan */}
            <div className="bg-white rounded-2xl shadow-xs border border-red-100 p-4 sm:p-5 flex flex-col justify-between">
              <div>
                <h3 className="text-xs font-bold text-red-700 uppercase tracking-wider flex items-center gap-2 mb-3">
                  <AlertTriangle size={16} className="text-red-500" /> Losses & Potensi Penghematan Biaya
                </h3>
                <div className="space-y-2.5 text-xs">
                  
                  <div className="bg-slate-50 border border-slate-100 p-2.5 rounded-xl flex justify-between items-center">
                    <div>
                      <span className="text-xs font-bold text-slate-700 flex items-center gap-1.5">
                        <Clock size={13} className="text-slate-500" /> Total Loss Time
                      </span>
                      <span className="text-[10px] text-slate-400">Akumulasi deviasi waktu di luar durasi ideal</span>
                    </div>
                    <span className="text-sm font-bold text-red-600 font-mono">
                      {data.summary.total_loss_time_str || '-'}
                    </span>
                  </div>

                  <div className="bg-red-50/70 border border-red-200 p-3 rounded-xl">
                    <div className="flex justify-between items-center">
                      <span className="text-[10px] font-bold text-red-900 uppercase">Kerugian Finansial Energi</span>
                      <span className="text-[11px] text-red-600 font-semibold">Over-consumption</span>
                    </div>
                    <span className="text-xl font-bold text-red-600 block mt-0.5 tabular-nums">
                      {formatRp((data.summary.steam_loss_rp || 0) + (data.summary.power_loss_rp || 0))}
                    </span>
                    <div className="mt-2 pt-2 border-t border-red-100 flex justify-between text-[11px] text-red-700 font-medium">
                      <span>Steam Loss: <b>{formatRp(data.summary.steam_loss_rp)}</b></span>
                      <span>Power Loss: <b>{formatRp(data.summary.power_loss_rp)}</b></span>
                    </div>
                  </div>

                </div>
              </div>
            </div>

          </div>
        )}

      </main>
      </div>

      {/* ═══════════════════════════════════════════════════════════════════ */}
      {/* 🖨️ MODAL PRATINJAU CETAK RESMI (A4 LANDSCAPE: 297mm x 210mm)        */}
      {/* ═══════════════════════════════════════════════════════════════════ */}
      {showPrintPreview && (
        <>
          {/* Backdrop */}
          <div
            className="print-preview-backdrop fixed inset-0 bg-slate-900/60 backdrop-blur-xs z-50 print:hidden transition-opacity"
            onClick={() => setShowPrintPreview(false)}
            aria-hidden="true"
          />

          {/* Modal Container */}
          <div className="print-modal-container fixed inset-0 z-50 flex flex-col items-center justify-start p-2 sm:p-4 overflow-y-auto pointer-events-none print:p-0 print:static print:block">
            <div
              className="print-modal-inner bg-slate-100 rounded-2xl shadow-2xl border border-slate-300 w-full max-w-[1300px] overflow-hidden pointer-events-auto my-auto print:bg-white print:border-none print:shadow-none print:max-w-none print:m-0"
              onClick={(e) => e.stopPropagation()}
            >
              {/* Modal Top Bar (Toolbar Cetak) */}
              <div className="print-preview-toolbar bg-slate-800 text-white px-4 py-3 flex items-center justify-between print:hidden">
                <div className="flex items-center gap-2">
                  <Printer size={18} className="text-indigo-400" />
                  <div>
                    <h3 className="text-sm font-bold leading-tight">Pratinjau Cetak Formal: Laporan Proses Harian Mesin</h3>
                    <p className="text-[11px] text-slate-300">Format A4 Landscape &bull; Logo Resmi &bull; Tanda Tangan &bull; Nomor Dokumen</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setShowPrintPreview(false)}
                    className="px-3 py-1.5 text-xs font-semibold bg-slate-700 hover:bg-slate-600 rounded-lg transition-colors text-slate-200"
                  >
                    Tutup
                  </button>
                  <button
                    onClick={handlePrint}
                    className="inline-flex items-center gap-1.5 px-4 py-1.5 text-xs font-bold bg-blue-600 hover:bg-blue-500 rounded-lg transition-colors shadow-xs"
                  >
                    <Printer size={14} /> Cetak Sekarang (A4)
                  </button>
                </div>
              </div>

              {/* Scrollable Paper Simulation Area */}
              <div className="print-scroll-wrap p-3 sm:p-5 overflow-x-auto print:p-0 print:overflow-visible">
                
                {/* 📄 THE PHYSICAL A4 LANDSCAPE SHEET 📄 */}
                <div
                  id="process-daily-print-sheet"
                  className="bg-white mx-auto shadow-md border border-slate-300 p-3 sm:p-4 text-slate-800 print:shadow-none print:border-none print:p-0"
                  style={{ width: '287mm', minHeight: '198mm', boxSizing: 'border-box' }}
                >
                  
                  {/* KOP SURAT RESMI PERUSAHAAN */}
                  <header className="pb-1.5 border-b-2 border-slate-900 mb-2 flex justify-between items-center gap-3">
                    <div className="flex items-center gap-3">
                      {companyLogoUrl ? (
                        <img
                          src={companyLogoUrl}
                          alt={data.company?.name || 'Company Logo'}
                          className="h-9 w-auto max-w-[95px] object-contain"
                        />
                      ) : (
                        <div className="h-8 w-8 rounded-lg bg-indigo-900 text-white flex items-center justify-center font-bold text-xs">
                          ST
                        </div>
                      )}
                      <div>
                        <h1 className="text-sm font-bold uppercase tracking-tight text-slate-900 leading-tight">
                          {data.company?.name || 'Suritex Factory'}
                        </h1>
                        <p className="text-[9px] font-semibold text-slate-600 uppercase tracking-widest">
                          Analisis Harian Laporan Produksi
                        </p>
                        <p className="text-[8px] text-slate-400 mt-0.5">
                          Jl. Pahlawan Desa No. 131–132, Utama, Kec. Cimahi Selatan, Kota Cimahi &bull; Jawa Barat
                        </p>
                      </div>
                    </div>

                    {/* Metadata Kecil Sederhana: Mesin, Periode Celup, & Cetak */}
                    <div className="text-right text-[8.5px] text-slate-600 leading-tight shrink-0">
                      <div>Mesin: <b className="text-slate-900">{data.machine_name} ({data.machine_code})</b></div>
                      <div>Periode Celup: <b className="text-slate-800">{date} (06:00 - 06:00 WIB)</b></div>
                      <div className="text-slate-400 text-[8px]">Dicetak: {new Date().toLocaleString('id-ID')}</div>
                    </div>
                  </header>

                  {/* ═══════════════════════════════════════════════════════════ */}
                  {/* GRAFIK 24 JAM (06:00 - 06:00 WIB) SELEBAR KERTAS & TABEL   */}
                  {/* ═══════════════════════════════════════════════════════════ */}
                  <div className="mb-2 border border-slate-300 rounded-sm pt-1.5 pb-1 px-2 bg-white avoid-break">
                    <div className="flex justify-between items-center mb-1 px-1">
                      <div className="flex items-center gap-2">
                        <span className="text-[9.5px] font-bold uppercase text-slate-900 tracking-wider">
                          Grafik Profil Suhu Aktual Mesin vs {isHto ? 'Temperatur HTO' : 'Tekanan Steam'} (24 Jam: 06:00 - 06:00 WIB)
                        </span>
                      </div>
                      <div className="flex items-center gap-3 text-[8.5px] font-semibold">
                        <div className="flex items-center gap-1.5 text-slate-800">
                          <span className="w-3.5 h-0.5 bg-red-500 rounded-full inline-block" />
                          <span>Suhu Aktual (°C)</span>
                        </div>
                        <div className="flex items-center gap-1.5 text-slate-800">
                          <span className={`w-3.5 h-0 border-t-2 border-dashed ${isHto ? 'border-amber-500' : 'border-blue-600'} inline-block`} />
                          <span>{isHto ? 'Temperatur HTO (°C)' : 'Tekanan Steam (bar)'}</span>
                        </div>
                        {!isHto && (
                          <div className="flex items-center gap-1 text-amber-700">
                            <span className="w-3.5 h-0 border-t border-dashed border-amber-500 inline-block" />
                            <span>Ambang Kritis (3.8 bar)</span>
                          </div>
                        )}
                      </div>
                    </div>

                    <div className="w-full h-[230px] sm:h-[240px] print-chart-box">
                      <ResponsiveContainer width="100%" height="100%" minHeight={1} minWidth={1}>
                        <LineChart data={data.chart_data} margin={{ top: 6, right: 8, left: 4, bottom: 0 }}>
                          {/* Kisi Mayor Cetak (Solid #6ba3cc, interval 30°C & 3 jam) */}
                          <CartesianGrid syncWithTicks={true} yAxisId="left" stroke="#6ba3cc" strokeWidth={1} vertical={true} />
                          
                          {/* Kisi Minor Horisontal Cetak (Suhu step 6°C, dashed #7a9bb8) */}
                          {MINOR_Y_TICKS.map((val) => (
                            <ReferenceLine
                              key={`print-minor-y-${val}`}
                              yAxisId="left"
                              y={val}
                              stroke="#7a9bb8"
                              strokeWidth={0.75}
                              strokeDasharray="3 2"
                              ifOverflow="discard"
                            />
                          ))}

                          {/* Kisi Minor Vertikal Cetak (Jam per 1 jam: 07:00, 08:00, 10:00, 11:00, dst., dashed #7a9bb8) */}
                          {minorXTicks.map((val) => (
                            <ReferenceLine
                              key={`print-minor-x-${val}`}
                              yAxisId="left"
                              x={val}
                              stroke="#7a9bb8"
                              strokeWidth={0.85}
                              strokeDasharray="3 2"
                              ifOverflow="discard"
                            />
                          ))}

                          <XAxis
                            dataKey="time"
                            ticks={chartTicks}
                            tickFormatter={(v) => (typeof v === 'string' ? v.trim() : v)}
                            tick={{ fontSize: 8.5, fill: '#1e3a5f' }}
                            axisLine={{ stroke: '#6ba3cc', strokeWidth: 1.2 }}
                            tickLine={{ stroke: '#6ba3cc' }}
                            padding={{ left: 0, right: 0 }}
                          />
                          <YAxis
                            yAxisId="left"
                            width={38}
                            tick={{ fontSize: 8.5, fill: '#ef4444' }}
                            axisLine={{ stroke: '#6ba3cc', strokeWidth: 1.2 }}
                            tickLine={{ stroke: '#6ba3cc' }}
                            domain={[30, 150]}
                            ticks={[30, 60, 90, 120, 150]}
                          />
                          <YAxis
                            yAxisId="right"
                            width={isHto ? 32 : 24}
                            orientation="right"
                            domain={isHto ? [0, 300] : [0, (dataMax) => Math.max(6, Math.ceil(dataMax || 6))]}
                            tick={{ fontSize: 8.5, fill: isHto ? '#d97706' : '#2563eb' }}
                            axisLine={{ stroke: '#6ba3cc', strokeWidth: 1.2 }}
                            tickLine={{ stroke: '#6ba3cc' }}
                          />
                          <Line
                            yAxisId="left"
                            type="monotone"
                            dataKey="temp"
                            stroke="#ef4444"
                            strokeWidth={2}
                            dot={false}
                            isAnimationActive={false}
                            name="Suhu Mesin (°C)"
                          />
                          <Line
                            yAxisId="right"
                            type="monotone"
                            dataKey="pressure"
                            stroke={isHto ? '#d97706' : '#2563eb'}
                            strokeWidth={1.8}
                            strokeDasharray="4 3"
                            dot={false}
                            isAnimationActive={false}
                            name={isHto ? 'Temp HTO (°C)' : 'Tekanan Steam (bar)'}
                          />
                          {!isHto && (
                            <ReferenceLine
                              yAxisId="right"
                              y={3.8}
                              stroke="#f59e0b"
                              strokeDasharray="3 3"
                            />
                          )}
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                  </div>

                  {/* TABEL 1 (PRINT): IDENTITAS KAIN & WAKTU SIKLUS */}
                  <div className="mb-2">
                    <div className="flex justify-between items-center mb-0.5">
                      <h4 className="text-[10px] font-bold text-slate-900 uppercase tracking-wider">
                        1. Identitas Kain & Waktu Siklus (Dimulai Real Heat s/d Selesai)
                      </h4>
                      <span className="text-[8.5px] text-slate-500 italic">* Durasi real & loss time dihitung dari tercapainya suhu Real Heat</span>
                    </div>
                    <table className="w-full text-[8.5px] text-center border-collapse border border-slate-800 leading-tight">
                      <thead className="bg-slate-800 text-white font-bold text-[8px]">
                        <tr className="divide-x divide-slate-700">
                          <th className="p-1 text-center w-8">Batch</th>
                          <th className="p-1 text-center whitespace-nowrap">Mulai Heat</th>
                          <th className="p-1 text-center whitespace-nowrap">Selesai</th>
                          <th className="p-1 text-center">Batch Kain</th>
                          <th className="p-1 text-center">No. Order</th>
                          <th className="p-1 text-center">Buyer</th>
                          <th className="p-1 text-center">Artikel</th>
                          <th className="p-1 text-center">Warna / Desain</th>
                          <th className="p-1 text-center">Proses</th>
                          <th className="p-1 text-center">Master Program</th>
                          <th className="p-1 text-center">Tube</th>
                          <th className="p-1 text-center">Nozzle / Main Pump</th>
                          <th className="p-1 text-center">Operator</th>
                          <th className="p-1 text-center font-bold">Dur. Real</th>
                          <th className="p-1 text-center">Dur. Idl</th>
                          <th className="p-1 text-center">Loss Time</th>
                          <th className="p-1 text-center">Eff (%)</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-300">
                        {data.batches && data.batches.length > 0 ? (
                          data.batches.map((b, idx) => (
                            <tr key={b.id} className={`divide-x divide-slate-300 ${idx % 2 === 1 ? 'bg-slate-50' : 'bg-white'}`}>
                              <td className="p-1 text-center font-bold font-mono">#{b.batch_number}</td>
                              <td className="p-1 text-center font-mono">{b.jam_mulai}</td>
                              <td className="p-1 text-center font-mono">{b.jam_selesai}</td>
                              <td className="p-1 text-center font-mono">{b.batch_kain}</td>
                              <td className="p-1 text-center">{b.no_order}</td>
                              <td className="p-1 text-center">{b.kode_buyer}</td>
                              <td className="p-1 text-center font-medium truncate max-w-[120px] mx-auto">{b.artikel}</td>
                              <td className="p-1 text-center">{b.warna_desain}</td>
                              <td className="p-1 text-center">{b.jenis_proses}</td>
                              <td className="p-1 text-center font-medium truncate max-w-[110px] mx-auto">{b.program}</td>
                              <td className="p-1 text-center">{b.isi_per_tube}</td>
                              <td className="p-1 text-center font-mono">{b.nozzle_main_pump || "-"}</td>
                              <td className="p-1 text-center">{b.operator}</td>
                              <td className="p-1 text-center font-bold font-mono">{b.total_durasi !== '-' ? `${b.total_durasi}m` : '-'}</td>
                              <td className="p-1 text-center font-mono text-slate-500">{b.durasi_ideal !== '-' ? `${b.durasi_ideal}m` : '-'}</td>
                              <td className="p-1 text-center font-mono font-semibold">
                                {b.loss_time != null ? (b.loss_time > 0 ? `+${b.loss_time}m` : `${b.loss_time}m`) : '-'}
                              </td>
                              <td className="p-1 text-center font-bold">
                                {b.eff_total != null ? `${b.eff_total}%` : '-'}
                              </td>
                            </tr>
                          ))
                        ) : (
                          <tr>
                            <td colSpan="17" className="p-3 text-center text-slate-400">Tidak ada data proses batch</td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>

                  {/* TABEL 2 (PRINT): DETAIL FASE & PARAMETER TERMAL */}
                  <div className="mb-2">
                    <div className="flex justify-between items-center mb-0.5">
                      <h4 className="text-[10px] font-bold text-slate-900 uppercase tracking-wider">
                        2. Detail Fase Operasi & Parameter Termal
                      </h4>
                      <span className="text-[8.5px] text-slate-500 italic">* Standar toleransi bongkar kain: ≤45 menit</span>
                    </div>
                    <table className="w-full text-[8.5px] text-center border-collapse border border-slate-800 leading-tight">
                      <thead className="bg-slate-800 text-white font-bold text-[8px]">
                        <tr className="divide-x divide-slate-700">
                          <th className="p-1 text-center w-8">Batch</th>
                          <th className="p-1 text-center">Heat Idl</th>
                          <th className="p-1 text-center">Heat Real</th>
                          <th className="p-1 text-center">Steady Idl</th>
                          <th className="p-1 text-center">Steady Real</th>
                          <th className="p-1 text-center">Cool Idl</th>
                          <th className="p-1 text-center">Cool Real</th>
                          <th className="p-1 text-center">Suhu Awal</th>
                          <th className="p-1 text-center font-bold bg-slate-700 text-slate-100">Suhu Prog.</th>
                          <th className="p-1 text-center font-bold text-amber-300">Suhu Puncak</th>
                          <th className="p-1 text-center">Gradien Heat</th>
                          <th className="p-1 text-center">Gradien Cool</th>
                          <th className="p-1 text-center">Avg Steam Pr</th>
                          <th className="p-1 text-center">Bongkar</th>
                          <th className="p-1 text-center">Cycle Puncak</th>
                          <th className="p-1 text-center">Cycle 60</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-300">
                        {data.batches && data.batches.length > 0 ? (
                          data.batches.map((b, idx) => (
                            <tr key={b.id} className={`divide-x divide-slate-300 ${idx % 2 === 1 ? 'bg-slate-50' : 'bg-white'}`}>
                              <td className="p-1 text-center font-bold font-mono">#{b.batch_number}</td>
                              <td className="p-1 text-center font-mono text-slate-600">{b.ideal_heating != null ? `${b.ideal_heating}m` : '-'}</td>
                              <td className="p-1 text-center font-mono">
                                {b.real_heating !== '-' ? (
                                  <span>
                                    <b>{b.real_heating}m</b>
                                    {b.delta_heating != null && b.delta_heating !== 0 && (
                                      <span className={b.delta_heating > 0 ? ' text-red-600 font-bold' : ' text-emerald-600 font-bold'}>
                                        {' '}({b.delta_heating > 0 ? `+${b.delta_heating}m` : `${b.delta_heating}m`})
                                      </span>
                                    )}
                                  </span>
                                ) : '-'}
                              </td>
                              <td className="p-1 text-center font-mono text-slate-600">{b.ideal_steady != null ? `${b.ideal_steady}m` : '-'}</td>
                              <td className="p-1 text-center font-mono">
                                {b.real_steady !== '-' ? (
                                  <span>
                                    <b>{b.real_steady}m</b>
                                    {b.delta_steady != null && b.delta_steady !== 0 && (
                                      <span className={b.delta_steady > 0 ? ' text-red-600 font-bold' : ' text-emerald-600 font-bold'}>
                                        {' '}({b.delta_steady > 0 ? `+${b.delta_steady}m` : `${b.delta_steady}m`})
                                      </span>
                                    )}
                                  </span>
                                ) : '-'}
                              </td>
                              <td className="p-1 text-center font-mono text-slate-600">{b.ideal_cooling != null ? `${b.ideal_cooling}m` : '-'}</td>
                              <td className="p-1 text-center font-mono">
                                {b.real_cooling !== '-' ? (
                                  <span>
                                    <b>{b.real_cooling}m</b>
                                    {b.delta_cooling != null && b.delta_cooling !== 0 && (
                                      <span className={b.delta_cooling > 0 ? ' text-red-600 font-bold' : ' text-emerald-600 font-bold'}>
                                        {' '}({b.delta_cooling > 0 ? `+${b.delta_cooling}m` : `${b.delta_cooling}m`})
                                      </span>
                                    )}
                                  </span>
                                ) : '-'}
                              </td>
                              <td className="p-1 text-center font-mono">{b.start_temp !== '-' ? `${b.start_temp}°C` : '-'}</td>
                              <td className="p-1 text-center font-mono font-semibold text-slate-800 bg-slate-50">
                                {b.suhu_prog !== '-' && b.suhu_prog != null ? `${b.suhu_prog}°C` : '-'}
                              </td>
                              <td className="p-1 text-center font-mono font-bold text-slate-900">{b.max_temp !== '-' ? `${b.max_temp}°C` : '-'}</td>
                              <td className="p-1 text-center font-mono">{b.heating_gradient !== '-' ? `${b.heating_gradient}°C/m` : '-'}</td>
                              <td className="p-1 text-center font-mono">{b.cooling_gradient !== '-' ? `${b.cooling_gradient}°C/m` : '-'}</td>
                              <td className="p-1 text-center font-mono font-semibold">{b.avg_steam_pressure !== '-' ? `${b.avg_steam_pressure} bar` : '-'}</td>
                              <td className="p-1 text-center font-mono">{b.late_stop_mins != null ? `${b.late_stop_mins}m` : '-'}</td>
                              <td className="p-1 text-center font-mono">{b.cycle_puncak || '-'}</td>
                              <td className="p-1 text-center font-mono">{b.cycle_60 || '-'}</td>
                            </tr>
                          ))
                        ) : (
                          <tr>
                            <td colSpan="16" className="p-3 text-center text-slate-400">Tidak ada rincian termal</td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>

                  {/* SECTION 3 (PRINT): CATATAN & MASALAH BATCH (JIKA ADA) */}
                  {batchesWithNotes.length > 0 && (
                    <div className="mb-1.5">
                      <h4 className="text-[10px] font-bold text-slate-900 uppercase tracking-wider mb-0.5">
                        3. Rekap Kendala & Catatan Operasional
                      </h4>
                      <table className="w-full text-[8.5px] text-left border-collapse border border-slate-800 leading-tight">
                        <thead className="bg-slate-100 font-bold border-b border-slate-300">
                          <tr className="divide-x divide-slate-300">
                            <th className="p-1 text-center w-12">Batch</th>
                            <th className="p-1 w-1/2">Permasalahan / Kendala</th>
                            <th className="p-1">Tindakan & Catatan Khusus Operator</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-300">
                          {batchesWithNotes.map((b) => (
                            <tr key={b.id} className="divide-x divide-slate-300">
                              <td className="p-1 text-center font-bold font-mono">#{b.batch_number}</td>
                              <td className="p-1 text-red-700 font-medium">{b.masalah || '-'}</td>
                              <td className="p-1 text-slate-700">{b.keterangan || '-'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}

                </div>
              </div>
            </div>
          </div>
        </>
      )}

      {/* ═══════════════════════════════════════════════════════════════════ */}
      {/* 🎨 CSS INJECTIONS FOR EXACT 1-PAGE A4 LANDSCAPE PRINTING          */}
      {/* ═══════════════════════════════════════════════════════════════════ */}
      <style>{`
        @media print {
          @page {
            size: A4 landscape;
            margin: 5mm 5mm;
          }

          html.printing-process-daily,
          html.printing-process-daily body {
            height: auto !important;
            min-height: 0 !important;
            max-height: none !important;
            overflow: visible !important;
            margin: 0 !important;
            padding: 0 !important;
            background: #ffffff !important;
            -webkit-print-color-adjust: exact !important;
            print-color-adjust: exact !important;
          }

          /* 1. Sembunyikan TOTAL tampilan web interaktif (hilangkan 1800px ghost body) */
          body.printing-process-daily .main-screen-view,
          body.printing-process-daily .print-preview-backdrop,
          body.printing-process-daily .print-preview-toolbar,
          body.printing-process-daily .no-print,
          body.printing-process-daily aside,
          body.printing-process-daily nav,
          body.printing-process-daily header:not(#process-daily-print-sheet header) {
            display: none !important;
          }

          /* 2. Runtuhkan container modal ke aliran dokumen alami (static flow) */
          body.printing-process-daily .print-modal-container,
          body.printing-process-daily .print-modal-inner,
          body.printing-process-daily .print-scroll-wrap {
            position: static !important;
            display: block !important;
            padding: 0 !important;
            margin: 0 !important;
            width: 100% !important;
            max-width: none !important;
            height: auto !important;
            overflow: visible !important;
            border: none !important;
            box-shadow: none !important;
            background: transparent !important;
          }

          /* 3. Lembar Cetak A4: Pas 1 halaman penuh tanpa kelebihan */
          body.printing-process-daily #process-daily-print-sheet {
            display: block !important;
            position: static !important;
            width: 100% !important;
            max-width: 100% !important;
            min-height: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
            border: none !important;
            box-shadow: none !important;
            background: #ffffff !important;
            overflow: visible !important;
          }

          body.printing-process-daily .avoid-break {
            break-inside: avoid !important;
            page-break-inside: avoid !important;
          }

          body.printing-process-daily thead {
            display: table-header-group !important;
          }

          body.printing-process-daily tr {
            break-inside: avoid !important;
            page-break-inside: avoid !important;
          }

          /* 4. Tinggi grafik dibuat 230px proporsional & sinkron dengan layout web agar kurva & sumbu tampil utuh tanpa tumpang tindih */
          body.printing-process-daily .print-chart-box {
            width: 100% !important;
            height: 230px !important;
            min-height: 230px !important;
            max-height: 230px !important;
            overflow: visible !important;
          }

          body.printing-process-daily .print-chart-box .recharts-responsive-container,
          body.printing-process-daily .print-chart-box .recharts-responsive-container > div,
          body.printing-process-daily .print-chart-box .recharts-wrapper {
            width: 100% !important;
            height: 100% !important;
            position: relative !important;
          }

          body.printing-process-daily .print-chart-box .recharts-wrapper > svg.recharts-surface {
            width: 100% !important;
            height: 100% !important;
            display: block !important;
          }

          body.printing-process-daily .recharts-tooltip-wrapper,
          body.printing-process-daily .recharts-default-tooltip,
          body.printing-process-daily .recharts-tooltip-cursor {
            display: none !important;
          }
        }
      `}</style>

    </div>
  );
}
