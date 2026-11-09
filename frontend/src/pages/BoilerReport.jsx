import React, { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import api from '../lib/api';
import { 
  ResponsiveContainer, AreaChart, Area, LineChart, Line, XAxis, YAxis, 
  CartesianGrid, Tooltip, Legend, PieChart, Pie, Cell, ScatterChart, Scatter, ZAxis, ComposedChart, BarChart, Bar
} from 'recharts';
import { Calendar, RefreshCw, ChevronLeft, ChevronRight, Zap, TrendingUp, TrendingDown, Minus, AlertTriangle, Fuel } from 'lucide-react';
import { ShareToChatButton } from '../components/chat/ShareToChatButton';

const COLORS = ['#10B981', '#3B82F6', '#F59E0B', '#EF4444', '#8B5CF6'];
const PIE_COLORS = { ideal: '#10B981', under: '#F59E0B', over: '#EF4444' };

const calcDelta = (current, baseline) => {
  if (current == null || baseline == null || baseline === 0) return null;
  return Number((((current - baseline) / baseline) * 100).toFixed(1));
};

const DeltaBadge = ({ current, baseline, invertColor = false }) => {
  const delta = calcDelta(current, baseline);
  if (delta === null) return <span className="text-xs text-gray-400">vs 7 hari: -</span>;
  const isPositive = delta > 0;
  const isNeutral = delta === 0;
  const isGood = invertColor ? !isPositive : isPositive;
  const colorClass = isNeutral ? 'text-gray-500' : isGood ? 'text-green-600' : 'text-red-600';
  const Icon = isNeutral ? Minus : isPositive ? TrendingUp : TrendingDown;
  return (
    <span className={`text-xs flex items-center gap-0.5 ${colorClass}`}>
      <Icon size={12} />
      {delta > 0 ? '+' : ''}{delta}% vs 7 hari
    </span>
  );
};

const KpiCard = ({ title, value, unit, subtitle, current, baseline, invertColor }) => (
  <div className="bg-white p-4 rounded-xl shadow-sm border border-gray-200">
    <div className="text-[10px] text-gray-500 uppercase font-bold tracking-wider mb-1">{title}</div>
    <div className="text-2xl font-bold text-gray-900">
      {value ?? '-'}
      {value != null && unit && <span className="text-sm font-medium text-gray-500 ml-1">{unit}</span>}
    </div>
    {subtitle && <div className="text-xs text-gray-400 mt-1">{subtitle}</div>}
    {current != null && baseline != null && (
      <div className="mt-2">
        <DeltaBadge current={current} baseline={baseline} invertColor={invertColor} />
      </div>
    )}
  </div>
);

const BoilerReport = () => {
  const [searchParams, setSearchParams] = useSearchParams();

  // Ambil tanggal dari query param ?date= (misal saat datang dari Boiler Calendar),
  // fallback ke hari ini jika tidak ada / tidak valid.
  const [date, setDate] = useState(() => {
    const paramDate = searchParams.get('date');
    if (paramDate && /^\d{4}-\d{2}-\d{2}$/.test(paramDate)) return paramDate;
    const today = new Date();
    return today.toISOString().split('T')[0];
  });

  const updateDate = (newDate) => {
    setDate(newDate);
    setSearchParams({ date: newDate });
  };
  
  const [loading, setLoading] = useState(true);
  const [alertFilter, setAlertFilter] = useState('Semua');
  const [baselineLoading, setBaselineLoading] = useState(false);
  const [data, setData] = useState(null);
  const [baseline, setBaseline] = useState(null);
  const [error, setError] = useState(null);

  const fetchReport = async () => {
    setLoading(true);
    setError(null);
    setData(null);
    setBaseline(null);

    try {
      const summaryRes = await api.get(`/report/boiler-summary?date=${date}`);
      if (summaryRes.data.error) {
        setError(summaryRes.data.error);
      } else {
        setData(summaryRes.data);
      }
    } catch (err) {
      setError('Gagal memuat data Boiler Report. Cek koneksi ke server.');
      console.error(err);
    } finally {
      setLoading(false);
    }

    // Baseline 7 hari dimuat terpisah agar tidak memblokir laporan utama
    setBaselineLoading(true);
    api.get(`/report/boiler-weekly-baseline?date=${date}`)
      .then((res) => {
        if (!res.data.error) setBaseline(res.data);
      })
      .catch((err) => console.warn('Baseline 7 hari gagal dimuat:', err))
      .finally(() => setBaselineLoading(false));
  };

  useEffect(() => {
    fetchReport();
  }, [date]);

  const changeDate = (days) => {
    const d = new Date(date);
    d.setDate(d.getDate() + days);
    updateDate(d.toISOString().split('T')[0]);
  };

  // Custom Tooltip component for better formatting
  const CustomTooltip = ({ active, payload, label }) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-white p-3 border border-gray-200 shadow-lg rounded-lg">
          <p className="font-bold text-gray-800 mb-2">{label}</p>
          {payload.map((entry, index) => (
            <div key={index} className="flex items-center text-sm mb-1">
              <span className="w-3 h-3 rounded-full mr-2" style={{ backgroundColor: entry.color }}></span>
              <span className="font-medium text-gray-600 mr-2">{entry.name}:</span>
              <span className="font-bold" style={{ color: entry.color }}>
                {entry.value !== null ? entry.value : '-'}
              </span>
            </div>
          ))}
        </div>
      );
    }
    return null;
  };

  // Prepare Scatter data
  let scatterData = data?.chart_data?.filter(d => d.Temp_RB_Steam > 0 && d.Speed_RB_Steam > 0).map(d => ({
    x: d.Temp_RB_Steam,
    y: d.Speed_RB_Steam,
    name: d.time
  })) || [];

  // Calculate Linear Regression & Correlation
  let correlationInsight = null;
  if (scatterData.length > 1) {
    const n = scatterData.length;
    let sumX = 0, sumY = 0, sumXY = 0, sumX2 = 0, sumY2 = 0;
    
    scatterData.forEach(d => {
      sumX += d.x;
      sumY += d.y;
      sumXY += d.x * d.y;
      sumX2 += d.x * d.x;
      sumY2 += d.y * d.y;
    });

    const denominator = (n * sumX2 - sumX * sumX);
    if (denominator !== 0) {
      const m = (n * sumXY - sumX * sumY) / denominator;
      const b = (sumY - m * sumX) / n;
      
      // Calculate correlation coefficient r
      const rNum = n * sumXY - sumX * sumY;
      const rDen = Math.sqrt((n * sumX2 - sumX * sumX) * (n * sumY2 - sumY * sumY));
      const r = rDen !== 0 ? rNum / rDen : 0;
      
      // Sort data by X for proper line rendering
      scatterData.sort((a, b) => a.x - b.x);
      
      // Add trend line data
      scatterData = scatterData.map(d => ({
        ...d,
        trendY: m * d.x + b
      }));

      // Generate Insight text
      let insightText = '';
      const rAbs = Math.abs(r);
      let strength = rAbs > 0.7 ? 'Kuat' : rAbs > 0.4 ? 'Sedang' : 'Lemah';
      let direction = r > 0 ? 'Positif (Berbanding Lurus)' : 'Negatif (Berbanding Terbalik)';
      
      if (r > 0) {
        insightText = `Korelasi ${strength} ${direction}. Semakin cepat feeder bahan bakar (Hz naik), suhu steam cenderung meningkat. Ini menunjukkan suplai energi responsif terhadap bahan bakar.`;
      } else {
        insightText = `Korelasi ${strength} ${direction}. Kecepatan feeder naik, namun suhu malah turun. Ini dapat mengindikasikan efisiensi pembakaran buruk (misal: batubara basah, terlalu banyak angin, atau laju feeding terlalu membludak sehingga menekan suhu).`;
      }
      
      if (rAbs < 0.3) {
         insightText = `Korelasi sangat Lemah. Perubahan kecepatan feeder bahan bakar (Hz) tidak berdampak signifikan pada fluktuasi Suhu Steam. Mungkin ada delay panas atau intervensi manual yang besar.`;
      }

      correlationInsight = { r: r.toFixed(2), m: m.toFixed(2), text: insightText };
    }
  }

  const totalPressure = (data?.pressure_dist?.ideal || 0) + (data?.pressure_dist?.under || 0) + (data?.pressure_dist?.over || 0);
  const getPercentage = (val) => totalPressure > 0 ? Number(((val / totalPressure) * 100).toFixed(1)) : 0;

  const pieData = [
    { name: 'Ideal (3.5-5.5 Bar)', value: getPercentage(data?.pressure_dist?.ideal || 0) },
    { name: 'Under Pressure (<3.5)', value: getPercentage(data?.pressure_dist?.under || 0) },
    { name: 'Over Pressure (>5.5)', value: getPercentage(data?.pressure_dist?.over || 0) },
  ];

  // Prepare Histogram Data for Steam Usage
  let usageHistogram = [];
  const validUsages = data?.chart_data?.map(d => d.steam_usage).filter(u => u > 0) || [];
  if (validUsages.length > 0) {
    const minU = Math.floor(Math.min(...validUsages));
    const maxU = Math.ceil(Math.max(...validUsages));
    const binCount = 15;
    const binSize = (maxU - minU) / binCount || 1;
    
    const bins = Array(binCount).fill(0).map((_, i) => ({
      rangeStart: minU + (i * binSize),
      rangeEnd: minU + ((i + 1) * binSize),
      name: `${Math.round(minU + (i * binSize))}-${Math.round(minU + ((i + 1) * binSize))}`,
      count: 0
    }));

    validUsages.forEach(u => {
      let placed = false;
      for (let i = 0; i < binCount - 1; i++) {
        if (u >= bins[i].rangeStart && u < bins[i].rangeEnd) {
          bins[i].count += 1;
          placed = true;
          break;
        }
      }
      if (!placed) {
        bins[binCount - 1].count += 1;
      }
    });
    usageHistogram = bins;
  }

  // Statistical properties for normal distribution check
  const SD_MAX = 600; // 10% of 6000 kg/h capacity
  let statsUsage = { mean: 0, sd: 0, cv: 0, skewness: 0, label: '', reasons: [], scoreValue: 0 };
  if (validUsages.length > 0) {
    const sum = validUsages.reduce((a, b) => a + b, 0);
    const mean = sum / validUsages.length;
    const squaredDiffs = validUsages.map(v => Math.pow(v - mean, 2));
    const variance = squaredDiffs.reduce((a, b) => a + b, 0) / validUsages.length;
    const sd = Math.sqrt(variance);
    const cv = mean > 0 ? (sd / mean) * 100 : 0;
    
    let skewness = 0;
    if (sd > 0) {
      const cubedDiffs = validUsages.map(v => Math.pow((v - mean) / sd, 3));
      skewness = cubedDiffs.reduce((a, b) => a + b, 0) / validUsages.length;
    }

    let points = 0;
    let reasons = [];

    // Evaluate CV (Moderate limits)
    if (cv >= 30) { points += 2; reasons.push(`CV tinggi (${cv.toFixed(1)}%)`); }
    else if (cv >= 15) { points += 1; }

    // Evaluate Skewness (Moderate limits)
    const absSkew = Math.abs(skewness);
    if (absSkew > 1.5) { points += 2; reasons.push(`Asimetris ekstrem (Skew: ${skewness.toFixed(2)})`); }
    else if (absSkew > 0.8) { points += 1; }

    // Evaluate SD Max (Moderate limits)
    if (sd > SD_MAX * 2) { points += 2; reasons.push(`SD melebihi batas 2x toleransi (${sd.toFixed(0)} kg/h)`); }
    else if (sd > SD_MAX) { points += 1; }

    // Determine final label based on total points (Max 6)
    let label = 'Sangat Stabil';
    let scoreValue = 0; 
    
    if (points >= 4) {
      label = 'Fluktuatif';
      scoreValue = 2;
    } else if (points >= 2) {
      label = 'Normal';
      scoreValue = 1;
    }

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

  const kpi = data?.kpi_summary;
  const alertHistory = data?.alert_history || [];
  const fuelCalibrated = data?.fuel_config?.steam_calibrated || data?.fuel_config?.hto_calibrated;
  const steamFuelCalibrated = data?.fuel_config?.steam_calibrated;
  const htoFuelCalibrated = data?.fuel_config?.hto_calibrated;
  const hasFuelChartData = data?.chart_data?.some(d => d.fuel_kg_steam != null || d.fuel_kg_hto != null);
  const fmt = (v) => v != null ? Number(v).toFixed(2) : '-';
  const severityLabel = { CRITICAL: 'KRITIS', WARNING: 'PERINGATAN', INFO: 'INFO' };

  const severityStyle = {
    CRITICAL: 'bg-red-100 text-red-700 border-red-200',
    WARNING: 'bg-amber-100 text-amber-700 border-amber-200',
    INFO: 'bg-blue-100 text-blue-700 border-blue-200',
  };

  return (
    <div id="dashboard-scroll-container" className="p-4 sm:p-6 bg-gray-50 min-h-full space-y-6">
      
      {/* Header & Date Picker */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <Zap className="text-amber-500" />
            Boiler Energy Report
          </h1>
          <p className="text-gray-500 text-sm">Analisis Kinerja dan Stabilitas Boiler Harian</p>
        </div>
        
        <div className="flex items-center gap-2">
          <div className="flex bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden w-full sm:w-auto">
            <button onClick={() => changeDate(-1)} className="p-2.5 text-gray-600 hover:bg-gray-100 hover:text-blue-600 transition-colors">
              <ChevronLeft size={20} />
            </button>
            <div className="px-4 py-2 flex items-center gap-2 border-x border-gray-100 font-semibold text-gray-800 bg-gray-50">
              <Calendar size={18} className="text-blue-600" />
              <input 
                type="date" 
                value={date} 
                onChange={(e) => updateDate(e.target.value)}
                className="bg-transparent border-none outline-none focus:ring-0 cursor-pointer"
              />
            </div>
            <button onClick={() => changeDate(1)} className="p-2.5 text-gray-600 hover:bg-gray-100 hover:text-blue-600 transition-colors">
              <ChevronRight size={20} />
            </button>
          </div>
          <ShareToChatButton
            reportPayload={{
              report_type: 'BOILER_REPORT',
              title: `Laporan Energi Boiler • ${date}`,
              subtitle: `Kinerja & Stabilitas Harian`,
              metrics: {
                'Tanggal': date,
                'Status': data ? 'Tersedia' : 'Memuat',
              },
              target_url: `/boiler-report?date=${date}`,
            }}
            variant="outline"
            label="Bagikan"
          />
          <button 
            onClick={fetchReport}
            className="p-2.5 bg-white rounded-xl shadow-sm border border-gray-200 text-gray-600 hover:bg-blue-50 hover:text-blue-600 transition-colors"
            title="Refresh Data"
          >
            <RefreshCw size={20} className={loading ? "animate-spin text-blue-500" : ""} />
          </button>
        </div>
      </div>

      {error ? (
        <div className="bg-red-50 text-red-600 p-4 rounded-xl border border-red-100 font-medium">
          {error}
        </div>
      ) : loading ? (
        <div className="flex flex-col items-center justify-center py-20">
          <RefreshCw size={40} className="animate-spin text-blue-500 mb-4" />
          <p className="text-gray-500 font-medium">Memuat data analisis boiler...</p>
        </div>
      ) : (
        <div className="space-y-6">

          {/* KPI SUMMARY CARDS */}
          {kpi ? (
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
              <KpiCard
                title="Total Steam Usage"
                value={kpi.total_steam_usage_kg?.toLocaleString()}
                unit="kg"
                current={kpi.total_steam_usage_kg}
                baseline={baseline?.avg_total_steam_usage_kg}
              />
              <KpiCard
                title="Rata-rata Tekanan"
                value={kpi.avg_pressure}
                unit="Bar"
                current={kpi.avg_pressure}
                baseline={baseline?.avg_pressure}
              />
              <KpiCard
                title="Konsumsi Batu Bara"
                value={fuelCalibrated ? kpi.total_fuel_kg?.toLocaleString() : null}
                unit={fuelCalibrated ? 'kg' : undefined}
                subtitle={!fuelCalibrated ? 'Kalibrasi Speed RB (Hz) di Admin > Master Global' : undefined}
                current={kpi.total_fuel_kg}
                baseline={baseline?.avg_total_fuel_kg}
                invertColor
              />

              <KpiCard
                title="Alert Hari Ini"
                value={kpi.alert_count_total}
                unit="kejadian"
                subtitle={`${kpi.alert_count_critical} kritis, ${kpi.alert_count_warning} warning`}
                current={kpi.alert_count_total}
                baseline={baseline?.avg_alert_count_total}
                invertColor
              />
              <KpiCard
                title="Kejadian Regulasi"
                value={data?.regulation_summary?.total ?? 0}
                unit="kejadian"
                subtitle={`${data?.regulation_summary?.steam_count ?? 0} Steam, ${data?.regulation_summary?.hto_count ?? 0} HTO`}
                invertColor
              />
            </div>
          ) : (
            <div className="bg-amber-50 border border-amber-200 text-amber-800 p-4 rounded-xl text-sm">
              KPI summary tidak tersedia — restart server Django (Waitress) lalu refresh halaman ini.
            </div>
          )}

          {baselineLoading && (
            <p className="text-xs text-gray-400 text-center">Memuat perbandingan 7 hari terakhir...</p>
          )}

          {/* ALERT HISTORY */}
          <div className="bg-white p-4 sm:p-5 rounded-2xl shadow-sm border border-gray-200">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between mb-4 gap-4">
              <div>
                <h2 className="text-lg font-bold text-gray-800 mb-1 flex items-center gap-2">
                  <AlertTriangle size={18} className="text-amber-500" />
                  Histori Alert & Regulasi
                </h2>
                <p className="text-sm text-gray-500">Kejadian peringatan, anomali, dan regulasi boiler</p>
              </div>
              <div className="flex bg-gray-100 p-1 rounded-lg">
                {['Semua', 'Critical', 'Warning', 'Regulasi'].map(f => (
                  <button 
                    key={f}
                    onClick={() => setAlertFilter(f)}
                    className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-colors ${
                      alertFilter === f ? 'bg-white text-gray-800 shadow-sm' : 'text-gray-500 hover:text-gray-700'
                    }`}
                  >
                    {f}
                  </button>
                ))}
              </div>
            </div>
            
            {(() => {
              const filteredAlerts = alertHistory.filter(a => {
                if (alertFilter === 'Semua') return true;
                if (alertFilter === 'Regulasi') return a.alert_type === 'REGULATION';
                return a.severity === alertFilter.toUpperCase() && a.alert_type !== 'REGULATION';
              });
              
              if (filteredAlerts.length === 0) {
                return <div className="text-center py-8 text-gray-400 text-sm">Tidak ada data untuk filter "{alertFilter}".</div>;
              }
              
              return (
                <div className="overflow-x-auto max-h-80 overflow-y-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-gray-100 text-left text-xs text-gray-500 uppercase">
                        <th className="pb-2 pr-4">Waktu</th>
                        <th className="pb-2 pr-4">Jenis</th>
                        <th className="pb-2 pr-4">Mesin</th>
                        <th className="pb-2 pr-4">Judul</th>
                        <th className="pb-2 pr-4">Nilai / Batas</th>
                        <th className="pb-2">Durasi / Tindakan</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredAlerts.map((alert, idx) => {
                        const isReg = alert.alert_type === 'REGULATION';
                        return (
                        <tr key={idx} className={`border-b border-gray-50 hover:bg-gray-50 ${isReg ? 'bg-orange-50/40' : ''}`}>
                          <td className="py-2.5 pr-4 text-gray-600 whitespace-nowrap">{alert.created_at}</td>
                          <td className="py-2.5 pr-4">
                            {isReg ? (
                              <span className="text-[10px] font-bold px-2 py-0.5 rounded-full border bg-orange-100 text-orange-700 border-orange-200 uppercase tracking-wide">
                                REGULASI
                              </span>
                            ) : (
                              <span className={`text-xs font-semibold px-2 py-0.5 rounded-full border ${severityStyle[alert.severity] || 'bg-gray-100 text-gray-600'}`}>
                                {alert.severity}
                              </span>
                            )}
                          </td>
                          <td className="py-2.5 pr-4 text-gray-700 font-medium">{alert.machine_code}</td>
                          <td className="py-2.5 pr-4 text-gray-700">{alert.title}</td>
                          <td className="py-2.5 pr-4 text-gray-600">
                            {isReg ? fmt(alert.current_value) : `${fmt(alert.current_value)} / ${fmt(alert.threshold_value)}`}
                          </td>
                          <td className="py-2.5">
                            {isReg ? (
                              <span className="text-gray-600">{alert.regulation_meta?.duration_minutes} menit</span>
                            ) : (
                              <span className={`text-xs ${alert.is_acknowledged ? 'text-green-600' : 'text-amber-600'}`}>
                                {alert.is_acknowledged ? 'Sudah diakui' : 'Belum diakui'}
                              </span>
                            )}
                          </td>
                        </tr>
                      )})}
                    </tbody>
                  </table>
                </div>
              );
            })()}
          </div>
          
          {/* SECTION 1: STEAM BOILER 4-AXIS SYNCHRONIZED CHARTS */}
          <div className="bg-white p-4 sm:p-5 rounded-2xl shadow-sm border border-gray-200">
            <h2 className="text-lg font-bold text-gray-800 mb-1">Analisis Steam Boiler</h2>
            <p className="text-sm text-gray-500 mb-6">Analisa pengaruh Feeding Bahan Bakar, Tekanan Uap, dan Penggunaan Uap</p>
            
            <div className="w-full overflow-x-auto overflow-y-hidden">
              <div className="min-w-[600px] space-y-4 pb-2">
                {/* Chart 1: Steam Usage vs Steam Pressure */}
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%" minHeight={1} minWidth={1}>
                    <AreaChart data={data.chart_data} syncId="boilerChart" margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E5E7EB" />
                      <XAxis dataKey="time" tick={{ fontSize: 10, fill: '#6B7280' }} tickMargin={10} minTickGap={35} />
                      <YAxis yAxisId="left" tick={{ fontSize: 10, fill: '#6B7280' }} stroke={COLORS[0]} domain={['auto', 'auto']} />
                      <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 10, fill: '#6B7280' }} stroke={COLORS[1]} domain={[0, 10]} />
                      <Tooltip content={<CustomTooltip />} />
                      <Legend verticalAlign="top" height={36} wrapperStyle={{ fontSize: '11px' }} />
                      <Area connectNulls={true} yAxisId="left" type="monotone" dataKey="steam_usage" name="Steam Usage" stroke={COLORS[0]} fill={COLORS[0]} fillOpacity={0.1} />
                      <Line connectNulls={true} yAxisId="right" type="monotone" dataKey="Steam_Pr" name="Pressure" stroke={COLORS[1]} strokeWidth={2} dot={false} />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>

                {/* Chart 2: Speed RB vs Temp RB Steam */}
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%" minHeight={1} minWidth={1}>
                    <LineChart data={data.chart_data} syncId="boilerChart" margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E5E7EB" />
                      <XAxis dataKey="time" tick={{ fontSize: 10, fill: '#6B7280' }} tickMargin={10} minTickGap={35} />
                      <YAxis yAxisId="left" tick={{ fontSize: 10, fill: '#6B7280' }} stroke={COLORS[2]} domain={['auto', 'auto']} />
                      <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 10, fill: '#6B7280' }} stroke={COLORS[3]} domain={['auto', 'auto']} />
                      <Tooltip content={<CustomTooltip />} />
                      <Legend verticalAlign="top" height={36} wrapperStyle={{ fontSize: '11px' }} />
                      <Line connectNulls={true} yAxisId="left" type="monotone" dataKey="Speed_RB_Steam" name="Speed RB (Hz)" stroke={COLORS[2]} strokeWidth={2} dot={false} />
                      <Line connectNulls={true} yAxisId="right" type="monotone" dataKey="Temp_RB_Steam" name="Temp RB (°C)" stroke={COLORS[3]} strokeWidth={2} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>

                {/* Chart 3: Konsumsi Fuel Batu Bara */}
                {steamFuelCalibrated ? (
                  <div className="h-64">
                    <ResponsiveContainer width="100%" height="100%" minHeight={1} minWidth={1}>
                      <AreaChart data={data.chart_data} syncId="boilerChart" margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E5E7EB" />
                        <XAxis dataKey="time" tick={{ fontSize: 10, fill: '#6B7280' }} tickMargin={10} minTickGap={35} />
                        <YAxis tick={{ fontSize: 10, fill: '#6B7280' }} stroke="#78716C" domain={[0, 'auto']} />
                        <Tooltip content={<CustomTooltip />} />
                        <Legend verticalAlign="top" height={36} wrapperStyle={{ fontSize: '11px' }} />
                        <Area connectNulls={true} type="monotone" dataKey="fuel_kg_steam" name="Fuel Batu Bara (kg)" stroke="#78716C" fill="#78716C" fillOpacity={0.15} />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                ) : (
                  <div className="h-20 flex items-center justify-center bg-amber-50 border border-amber-100 rounded-xl text-amber-700 text-sm">
                    <Fuel size={16} className="mr-2" />
                    Fuel batu bara belum dikalibrasi — set faktor Hz Speed RB di Admin &gt; Master Global
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* SECTION 2: HTO (THERMAL OIL) BOILER */}
          <div className="bg-white p-4 sm:p-5 rounded-2xl shadow-sm border border-gray-200">
            <h2 className="text-lg font-bold text-gray-800 mb-1">Analisis HTO Boiler (Thermal Oil)</h2>
            <p className="text-sm text-gray-500 mb-6">Stabilitas Suhu Oli Panas terhadap Ruang Bakar HTO</p>

            <div className="w-full overflow-x-auto overflow-y-hidden">
              <div className="min-w-[600px] space-y-4 pb-2">

                {/* Chart 1 HTO: Suhu Oli vs Speed RB */}
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%" minHeight={1} minWidth={1}>
                    <LineChart data={data.chart_data} syncId="htoChart" margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E5E7EB" />
                      <XAxis dataKey="time" tick={{ fontSize: 10, fill: '#6B7280' }} tickMargin={10} minTickGap={35} />
                      <YAxis yAxisId="left" tick={{ fontSize: 10, fill: '#6B7280' }} stroke={COLORS[4]} domain={['auto', 'auto']} />
                      <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 10, fill: '#6B7280' }} stroke={COLORS[2]} domain={['auto', 'auto']} />
                      <Tooltip content={<CustomTooltip />} />
                      <Legend verticalAlign="top" height={36} wrapperStyle={{ fontSize: '11px' }} />
                      <Line connectNulls={true} yAxisId="left" type="monotone" dataKey="Oil_Temp" name="Suhu Oli HTO (°C)" stroke={COLORS[4]} strokeWidth={3} dot={false} />
                      <Line connectNulls={true} yAxisId="right" type="monotone" dataKey="Speed_R_Bakar" name="Speed RB HTO (Hz)" stroke={COLORS[2]} strokeWidth={2} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>

                {/* Chart 2 HTO: Suhu Ruang Bakar vs Speed RB */}
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%" minHeight={1} minWidth={1}>
                    <LineChart data={data.chart_data} syncId="htoChart" margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E5E7EB" />
                      <XAxis dataKey="time" tick={{ fontSize: 10, fill: '#6B7280' }} tickMargin={10} minTickGap={35} />
                      <YAxis yAxisId="left" tick={{ fontSize: 10, fill: '#6B7280' }} stroke={COLORS[3]} domain={['auto', 'auto']} />
                      <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 10, fill: '#6B7280' }} stroke={COLORS[2]} domain={['auto', 'auto']} />
                      <Tooltip content={<CustomTooltip />} />
                      <Legend verticalAlign="top" height={36} wrapperStyle={{ fontSize: '11px' }} />
                      <Line connectNulls={true} yAxisId="left" type="monotone" dataKey="Temp_R_Bakar" name="Suhu Ruang Bakar HTO (°C)" stroke={COLORS[3]} strokeWidth={2} dot={false} strokeDasharray="5 5" />
                      <Line connectNulls={true} yAxisId="right" type="monotone" dataKey="Speed_R_Bakar" name="Speed RB HTO (Hz)" stroke={COLORS[2]} strokeWidth={2} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>

                {/* Chart 3 HTO: Konsumsi Fuel HTO */}
                {htoFuelCalibrated ? (
                  <div className="h-64">
                    <ResponsiveContainer width="100%" height="100%" minHeight={1} minWidth={1}>
                      <AreaChart data={data.chart_data} syncId="htoChart" margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E5E7EB" />
                        <XAxis dataKey="time" tick={{ fontSize: 10, fill: '#6B7280' }} tickMargin={10} minTickGap={35} />
                        <YAxis tick={{ fontSize: 10, fill: '#6B7280' }} stroke="#A8A29E" domain={[0, 'auto']} />
                        <Tooltip content={<CustomTooltip />} />
                        <Legend verticalAlign="top" height={36} wrapperStyle={{ fontSize: '11px' }} />
                        <Area connectNulls={true} type="monotone" dataKey="fuel_kg_hto" name="Fuel HTO (kg)" stroke="#A8A29E" fill="#A8A29E" fillOpacity={0.15} />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                ) : (
                  <div className="h-20 flex items-center justify-center bg-amber-50 border border-amber-100 rounded-xl text-amber-700 text-sm">
                    <Fuel size={16} className="mr-2" />
                    Fuel HTO belum dikalibrasi — set faktor Hz Speed RB HTO di Admin &gt; Master Global
                  </div>
                )}

              </div>
            </div>
          </div>

          {/* SECTION 3: WIDGETS */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            
            {/* Widget 1: Analisis Stabilitas (Tekanan & Pemakaian) */}
            <div className="bg-white p-4 sm:p-5 rounded-2xl shadow-sm border border-gray-200 flex flex-col space-y-6">
              
              {/* Part 1: Tekanan Uap */}
              <div>
                <h2 className="text-lg font-bold text-gray-800 mb-1">Distribusi Tekanan Uap</h2>
                <p className="text-sm text-gray-500 mb-2">Target: 3.5 - 5.5 Bar</p>
                <div className="h-48">
                  <ResponsiveContainer width="100%" height="100%" minHeight={1} minWidth={1}>
                    <PieChart>
                      <Pie
                        data={pieData}
                        cx="50%"
                        cy="50%"
                        innerRadius={50}
                        outerRadius={70}
                        paddingAngle={5}
                        dataKey="value"
                      >
                        <Cell fill="#10B981" /> {/* Ideal */}
                        <Cell fill="#F59E0B" /> {/* Under */}
                        <Cell fill="#EF4444" /> {/* Over */}
                      </Pie>
                      <Tooltip formatter={(val) => [`${val}%`, 'Persentase']} />
                      <Legend verticalAlign="bottom" height={36} iconType="circle" />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              </div>

              {/* Part 2: Pemakaian Uap */}
              <div className="pt-4 border-t border-gray-100">
                <h2 className="text-lg font-bold text-gray-800 mb-1">Stabilitas Pemakaian (Demand)</h2>
                <p className="text-sm text-gray-500 mb-2">Distribusi frekuensi beban pemakaian uap (kg/h)</p>
                <div className="h-48">
                  {usageHistogram.length > 0 ? (
                    <ResponsiveContainer width="100%" height="100%" minHeight={1} minWidth={1}>
                      <BarChart data={usageHistogram} margin={{ top: 10, right: 10, bottom: 20, left: -20 }}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E5E7EB" />
                        <XAxis dataKey="name" tick={{ fontSize: 9, fill: '#6B7280' }} interval={0} angle={-45} textAnchor="end" height={40} />
                        <YAxis tick={{ fontSize: 11, fill: '#6B7280' }} />
                        <Tooltip cursor={{ fill: '#F3F4F6' }} formatter={(val) => [`${val} Frekuensi`, 'Jumlah']} />
                        <Bar dataKey="count" fill="#8B5CF6" radius={[4, 4, 0, 0]} name="Frekuensi" />
                      </BarChart>
                    </ResponsiveContainer>
                  ) : (
                    <div className="flex h-full items-center justify-center text-gray-400">Tidak ada data pemakaian valid.</div>
                  )}
                </div>

                {validUsages.length > 0 && (
                  <div className="mt-4 flex flex-col space-y-3">
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-center">
                      <div className="bg-gray-50 p-2 rounded-lg border border-gray-100">
                        <div className="text-[10px] text-gray-500 uppercase font-bold">Rata-rata</div>
                        <div className="text-sm font-bold text-gray-800">{statsUsage.mean}</div>
                      </div>
                      <div className="bg-gray-50 p-2 rounded-lg border border-gray-100">
                        <div className="text-[10px] text-gray-500 uppercase font-bold">SD (Sebaran)</div>
                        <div className="text-sm font-bold text-gray-800">±{statsUsage.sd}</div>
                      </div>
                      <div className="bg-gray-50 p-2 rounded-lg border border-gray-100">
                        <div className="text-[10px] text-gray-500 uppercase font-bold">Skewness</div>
                        <div className="text-sm font-bold text-gray-800">{statsUsage.skewness}</div>
                      </div>
                      <div className={`p-2 rounded-lg border flex flex-col justify-center ${statsUsage.scoreValue === 0 ? 'bg-green-50 border-green-100 text-green-700' : statsUsage.scoreValue === 1 ? 'bg-blue-50 border-blue-100 text-blue-700' : 'bg-orange-50 border-orange-100 text-orange-700'}`}>
                        <div className="text-[10px] uppercase font-bold opacity-80">Karakteristik</div>
                        <div className="text-xs font-bold mt-0.5 leading-tight">{statsUsage.label}</div>
                      </div>
                    </div>
                    {statsUsage.reasons.length > 0 && statsUsage.scoreValue > 0 && (
                      <div className="bg-gray-50 p-3 rounded-lg border border-gray-100 text-xs text-gray-600">
                        <p className="font-semibold mb-1">Catatan Penurunan Stabilitas:</p>
                        <ul className="list-disc pl-4 space-y-0.5">
                          {statsUsage.reasons.map((reason, idx) => (
                            <li key={idx}>{reason}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                )}
              </div>

            </div>

            {/* Widget 2: Boiler Temp vs Fuel */}
            <div className="bg-white p-4 sm:p-5 rounded-2xl shadow-sm border border-gray-200">
              <h2 className="text-lg font-bold text-gray-800 mb-1">Korelasi Suhu vs Fuel</h2>
              <p className="text-sm text-gray-500 mb-4">Sebaran Temperatur Steam Boiler terhadap Speed R. Bakar (Supply)</p>
              
              <div className="h-64 mb-4">
                {scatterData.length > 0 ? (
                  <div className="w-full h-full overflow-x-auto overflow-y-hidden">
                    <div className="min-w-[500px] h-full">
                      <ResponsiveContainer width="100%" height="100%" minHeight={1} minWidth={1}>
                        <ComposedChart margin={{ top: 20, right: 20, bottom: 20, left: 10 }}>
                          <CartesianGrid strokeDasharray="3 3" />
                          <XAxis type="number" dataKey="x" name="Suhu Steam" unit=" °C" tick={{ fontSize: 10 }} domain={['auto', 'auto']} />
                          <YAxis type="number" dataKey="y" name="Speed RB" unit=" Hz" tick={{ fontSize: 10 }} domain={['auto', 'auto']} />
                          <ZAxis type="category" dataKey="name" name="Waktu" />
                          <Tooltip cursor={{ strokeDasharray: '3 3' }} />
                          <Scatter data={scatterData} name="Actual Data" fill="#3B82F6" opacity={0.6} />
                          <Line data={scatterData} dataKey="trendY" type="monotone" stroke="#EF4444" strokeWidth={2} dot={false} activeDot={false} name="Trend Line" />
                        </ComposedChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                ) : (
                  <div className="flex h-full items-center justify-center text-gray-400">
                    Tidak ada data korelasi yang valid.
                  </div>
                )}
              </div>
              
              {/* Insight Box */}
              {correlationInsight && (
                <div className="bg-blue-50 border border-blue-100 p-3 rounded-xl">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-bold text-blue-800 uppercase tracking-wider">Insight Korelasi (r: {correlationInsight.r})</span>
                  </div>
                  <p className="text-sm text-blue-900 leading-relaxed">
                    {correlationInsight.text}
                  </p>
                </div>
              )}
            </div>

          </div>

        </div>
      )}
    </div>
  );
};

export default BoilerReport;
