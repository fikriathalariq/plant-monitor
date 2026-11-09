import React, { useState, useEffect, useMemo } from 'react';

import { useNavigate } from 'react-router-dom';

import api from '../lib/api';

import { CalendarDays, ChevronLeft, ChevronRight, RefreshCw, Star, AlertTriangle, Fuel, ArrowRight } from 'lucide-react';

const MONTH_NAMES = [

  'Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni',

  'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember',

];

const WEEKDAY_NAMES = ['Min', 'Sen', 'Sel', 'Rab', 'Kam', 'Jum', 'Sab'];

// Skor gabungan hari: specific fuel consumption (efisiensi) + pressure ideal% + sedikit alert kritis.

// Setiap komponen dinormalisasi 0-1 lalu dijumlahkan berbobot, supaya hari terbaik

// bukan hanya "paling irit bahan bakar" tapi juga stabil tekanannya dan minim gangguan.

function computeDayScore(day, monthStats) {

  if (!day || day.specific_fuel_consumption == null) return null;

  const sfcScore = monthStats.maxSfc > monthStats.minSfc

    ? (day.specific_fuel_consumption - monthStats.minSfc) / (monthStats.maxSfc - monthStats.minSfc)

    : 1;

  const pressureScore = (day.pressure_ideal_percent ?? 0) / 100;

  const alertPenalty = Math.min((day.alert_count_critical ?? 0) / 10, 1);

  return sfcScore * 0.5 + pressureScore * 0.4 - alertPenalty * 0.1;

}

function getFuelColor(value, minSfc, maxSfc) {

  if (value == null) return 'bg-gray-50 border-gray-200';

  if (maxSfc === minSfc) return 'bg-emerald-100 border-emerald-300';

  const ratio = (value - minSfc) / (maxSfc - minSfc);

  if (ratio >= 0.75) return 'bg-emerald-100 border-emerald-300';

  if (ratio >= 0.5) return 'bg-lime-100 border-lime-300';

  if (ratio >= 0.25) return 'bg-amber-100 border-amber-300';

  return 'bg-red-100 border-red-300';

}

const formatSelectedDateIndo = (dateStr) => {

  if (!dateStr) return '';

  try {

    const [y, m, d] = dateStr.split('-').map(Number);

    const dateObj = new Date(y, m - 1, d);

    return dateObj.toLocaleDateString('id-ID', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });

  } catch {

    return dateStr;

  }

};

const BoilerCalendar = () => {

  const navigate = useNavigate();

  const today = new Date();

  const [year, setYear] = useState(today.getFullYear());

  const [month, setMonth] = useState(today.getMonth() + 1); // 1-12

  const [loading, setLoading] = useState(true);

  const [error, setError] = useState(null);

  const [monthData, setMonthData] = useState(null);

  // Tanggal yang sedang aktif di-inspect pada tampilan mobile

  const [selectedDate, setSelectedDate] = useState(() => {

    return `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;

  });

  const fetchMonth = async () => {

    setLoading(true);

    setError(null);

    try {

      const res = await api.get(`/report/boiler-monthly-calendar?year=${year}&month=${month}`);

      if (res.data.error) {

        setError(res.data.error);

        setMonthData(null);

      } else {

        setMonthData(res.data);

      }

    } catch (err) {

      setError('Gagal memuat data kalender boiler. Cek koneksi ke server.');

      console.error(err);

      setMonthData(null);

    } finally {

      setLoading(false);

    }

  };

  useEffect(() => {

    fetchMonth();

    // eslint-disable-next-line react-hooks/exhaustive-deps

  }, [year, month]);

  const changeMonth = (delta) => {

    let newMonth = month + delta;

    let newYear = year;

    if (newMonth > 12) { newMonth = 1; newYear += 1; }

    if (newMonth < 1) { newMonth = 12; newYear -= 1; }

    setMonth(newMonth);

    setYear(newYear);

  };

  const daysByDate = useMemo(() => {

    const map = {};

    (monthData?.days || []).forEach((d) => { map[d.date] = d; });

    return map;

  }, [monthData]);

  const monthStats = useMemo(() => {

    const sfcValues = (monthData?.days || [])

      .map((d) => d.specific_fuel_consumption)

      .filter((v) => v != null);

    if (sfcValues.length === 0) return { minSfc: 0, maxSfc: 0 };

    return { minSfc: Math.min(...sfcValues), maxSfc: Math.max(...sfcValues) };

  }, [monthData]);

  const { bestDate, worstDate } = useMemo(() => {

    const days = monthData?.days || [];

    let best = null, worst = null, bestScore = -Infinity, worstScore = Infinity;

    days.forEach((d) => {

      const score = computeDayScore(d, monthStats);

      if (score == null) return;

      if (score > bestScore) { bestScore = score; best = d.date; }

      if (score < worstScore) { worstScore = score; worst = d.date; }

    });

    return { bestDate: best, worstDate: worst };

  }, [monthData, monthStats]);

  // Update selectedDate saat data bulan berganti ke hari terbaik atau hari pertama yang memiliki data

  useEffect(() => {

    if (bestDate && bestDate.startsWith(`${year}-${String(month).padStart(2, '0')}`)) {

      setSelectedDate(bestDate);

    } else {

      const firstValidDay = (monthData?.days || []).find((d) => (d.total_steam_usage_kg || 0) > 0)?.date;

      if (firstValidDay) {

        setSelectedDate(firstValidDay);

      } else {

        setSelectedDate(`${year}-${String(month).padStart(2, '0')}-01`);

      }

    }

  }, [year, month, bestDate, monthData]);

  // Ringkasan cepat bulan untuk visualisasi ringkas mobile

  const monthlySummary = useMemo(() => {

    const days = monthData?.days || [];

    let totalSteam = 0;

    let totalFuel = 0;

    let validSfcDays = 0;

    let sumSfc = 0;

    days.forEach((d) => {

      if (d.total_steam_usage_kg) totalSteam += d.total_steam_usage_kg;

      if (d.total_fuel_kg) totalFuel += d.total_fuel_kg;

      if (d.specific_fuel_consumption != null) {

        sumSfc += d.specific_fuel_consumption;

        validSfcDays++;

      }

    });

    const avgSfc = validSfcDays > 0 ? (sumSfc / validSfcDays).toFixed(2) : null;

    return {

      totalSteamTon: (totalSteam / 1000).toFixed(1),

      totalFuelTon: (totalFuel / 1000).toFixed(1),

      avgSfc,

      activeDays: days.filter((d) => (d.total_steam_usage_kg || 0) > 0).length,

    };

  }, [monthData]);

  const fuelCalibrated = monthData?.fuel_config?.steam_calibrated || monthData?.fuel_config?.hto_calibrated;

  // Bangun grid kalender (Minggu-Sabtu), termasuk sel kosong padding di awal/akhir bulan

  const calendarCells = useMemo(() => {

    const firstDay = new Date(year, month - 1, 1);

    const startWeekday = firstDay.getDay(); // 0 = Minggu

    const daysInMonth = new Date(year, month, 0).getDate();

    const cells = [];

    for (let i = 0; i < startWeekday; i++) cells.push(null);

    for (let d = 1; d <= daysInMonth; d++) {

      const dateStr = `${year}-${String(month).padStart(2, '0')}-${String(d).padStart(2, '0')}`;

      cells.push(dateStr);

    }

    while (cells.length % 7 !== 0) cells.push(null);

    return cells;

  }, [year, month]);

  const goToDay = (dateStr) => {

    if (!dateStr) return;

    navigate(`/boiler-report?date=${dateStr}`);

  };

  const selectedDay = daysByDate[selectedDate];

  const isSelectedBest = selectedDate === bestDate;

  const isSelectedWorst = selectedDate === worstDate && bestDate !== worstDate;

  return (

    <div id="dashboard-scroll-container" className="p-4 sm:p-6 bg-gray-50 min-h-full space-y-4 sm:space-y-6">

      {/* Header & Month Navigator */}

      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 sm:gap-4">

        <div>

          <h1 className="text-xl sm:text-2xl font-bold text-gray-900 flex items-center gap-2">

            <CalendarDays className="text-amber-500 shrink-0" />

            <span>Boiler Calendar</span>

          </h1>

          <p className="text-gray-500 text-xs sm:text-sm mt-0.5">

            Pola Harian Steam Usage, Batu Bara & Tekanan — Temukan Hari Paling Efisien

          </p>

        </div>

        <div className="flex items-center gap-2 justify-between sm:justify-start">

          <div className="flex bg-white rounded-xl shadow-xs border border-gray-200 overflow-hidden">

            <button

              onClick={() => changeMonth(-1)}

              className="p-2 sm:p-2.5 text-gray-600 hover:bg-gray-100 hover:text-blue-600 transition-colors"

              aria-label="Bulan Sebelumnya"

            >

              <ChevronLeft size={18} className="sm:w-5 sm:h-5" />

            </button>

            <div className="px-3 sm:px-4 py-1.5 sm:py-2 flex items-center gap-2 border-x border-gray-100 font-semibold text-gray-800 bg-gray-50 min-w-[130px] sm:min-w-[160px] justify-center text-xs sm:text-sm">

              {MONTH_NAMES[month - 1]} {year}

            </div>

            <button

              onClick={() => changeMonth(1)}

              className="p-2 sm:p-2.5 text-gray-600 hover:bg-gray-100 hover:text-blue-600 transition-colors"

              aria-label="Bulan Berikutnya"

            >

              <ChevronRight size={18} className="sm:w-5 sm:h-5" />

            </button>

          </div>

          <button

            onClick={fetchMonth}

            className="p-2 sm:p-2.5 bg-white rounded-xl shadow-xs border border-gray-200 text-gray-600 hover:bg-blue-50 hover:text-blue-600 transition-colors"

            title="Refresh Data"

            aria-label="Refresh Data"

          >

            <RefreshCw size={18} className={`sm:w-5 sm:h-5 ${loading ? 'animate-spin text-blue-500' : ''}`} />

          </button>

        </div>

      </div>

      {/* 📱 MOBILE QUICK MONTHLY STATS PILLS (< md) */}

      {!loading && !error && monthData && (

        <div className="grid grid-cols-2 gap-2 md:hidden">

          <div className="bg-white p-3 rounded-xl border border-gray-200 shadow-xs">

            <span className="text-[10px] font-medium text-gray-500 block uppercase tracking-wider">Total Steam Bulan Ini</span>

            <span className="text-base font-bold text-blue-600 block mt-0.5">

              {monthlySummary.totalSteamTon} <span className="text-xs font-normal text-gray-500">Ton</span>

            </span>

          </div>

          <div className="bg-white p-3 rounded-xl border border-gray-200 shadow-xs">

            <span className="text-[10px] font-medium text-gray-500 block uppercase tracking-wider">Rata-rata SFC</span>

            <span className="text-base font-bold text-emerald-600 block mt-0.5">

              {monthlySummary.avgSfc ?? '-'} <span className="text-xs font-normal text-gray-500">kg/kg</span>

            </span>

          </div>

        </div>

      )}

      {!fuelCalibrated && !loading && !error && (

        <div className="bg-amber-50 border border-amber-200 text-amber-800 p-3 rounded-xl text-xs sm:text-sm flex items-center gap-2">

          <Fuel size={16} className="shrink-0" />

          <span>Faktor konversi Speed RB (Hz) ke kg batu bara belum dikalibrasi — warna kalender akan netral. Isi di Admin &gt; Master Global.</span>

        </div>

      )}

      {error ? (

        <div className="bg-red-50 text-red-600 p-4 rounded-xl border border-red-100 font-medium text-sm">

          {error}

        </div>

      ) : loading ? (

        <div className="flex flex-col items-center justify-center py-20">

          <RefreshCw size={36} className="animate-spin text-blue-500 mb-3" />

          <p className="text-gray-500 font-medium text-sm">Memuat data kalender boiler...</p>

        </div>

      ) : (

        <div className="bg-white p-3.5 sm:p-5 rounded-2xl shadow-xs border border-gray-200">

          {/* ═══════════════════════════════════════════════════════════════ */}

          {/* 📱 1. MOBILE VIEW ONLY (< md: 768px): HEATMAP + DAY INSPECTOR  */}

          {/* ═══════════════════════════════════════════════════════════════ */}

          <div className="block md:hidden">

            {/* Weekday header (Mobile) */}

            <div className="grid grid-cols-7 gap-1.5 mb-1.5">

              {WEEKDAY_NAMES.map((wd) => (

                <div key={`mob-wd-${wd}`} className="text-center text-[10px] font-bold text-gray-400 uppercase py-0.5">

                  {wd}

                </div>

              ))}

            </div>

            {/* Compact Heatmap Grid (Mobile) */}

            <div className="grid grid-cols-7 gap-1.5 mb-4">

              {calendarCells.map((dateStr, idx) => {

                if (!dateStr) return <div key={`empty-mob-${idx}`} className="h-11 rounded-lg" />;

                const day = daysByDate[dateStr];

                const dayNum = parseInt(dateStr.split('-')[2], 10);

                const isBest = dateStr === bestDate;

                const isWorst = dateStr === worstDate && bestDate !== worstDate;

                const isSelected = dateStr === selectedDate;

                const colorClass = day ? getFuelColor(day.specific_fuel_consumption, monthStats.minSfc, monthStats.maxSfc) : 'bg-gray-50 border-gray-100 text-gray-400';

                return (

                  <button

                    key={`mob-${dateStr}`}

                    type="button"

                    onClick={() => setSelectedDate(dateStr)}

                    className={`relative h-11 w-full flex flex-col items-center justify-center rounded-xl border transition-all ${colorClass} ${

                      isSelected

                        ? 'ring-2 ring-blue-600 ring-offset-1 border-blue-500 shadow-md font-bold scale-[1.03] z-10'

                        : 'hover:border-gray-400'

                    }`}

                  >

                    <span className={`text-xs ${isSelected ? 'font-black text-blue-900' : 'font-bold text-gray-800'}`}>

                      {dayNum}

                    </span>

                    {/* Micro Indicator Badges */}

                    <div className="flex items-center gap-0.5 mt-0.5 h-2.5">

                      {isBest && (

                        <Star size={9} className="text-amber-600 fill-amber-500" />

                      )}

                      {isWorst && (

                        <span className="w-1.5 h-1.5 rounded-full bg-red-500" title="Perlu Cek" />

                      )}

                      {day?.alert_count_critical > 0 && !isWorst && (

                        <span className="w-1.5 h-1.5 rounded-full bg-red-600 animate-pulse" />

                      )}

                    </div>

                  </button>

                );

              })}

            </div>

            {/* Selected Day Inspector Card (Mobile) */}

            <div className="bg-slate-50/80 rounded-2xl border border-slate-200 p-3.5 shadow-xs">

              <div className="flex items-start justify-between pb-2.5 border-b border-slate-200/80 gap-2">

                <div>

                  <span className="text-[10px] font-bold uppercase tracking-wider text-blue-600 block">

                    Detail Hari Terpilih

                  </span>

                  <h3 className="text-sm font-bold text-gray-900 leading-tight mt-0.5">

                    {formatSelectedDateIndo(selectedDate)}

                  </h3>

                </div>

                <div className="shrink-0">

                  {isSelectedBest && (

                    <span className="inline-flex items-center gap-1 text-[10px] font-bold text-amber-700 bg-amber-100 px-2 py-0.5 rounded-full border border-amber-300">

                      <Star size={11} fill="currentColor" /> Terbaik Bulan Ini

                    </span>

                  )}

                  {isSelectedWorst && (

                    <span className="inline-flex items-center gap-1 text-[10px] font-bold text-red-700 bg-red-100 px-2 py-0.5 rounded-full border border-red-300">

                      <AlertTriangle size={11} /> Perlu Cek

                    </span>

                  )}

                </div>

              </div>

              {selectedDay ? (

                <div className="mt-3 space-y-3">

                  {/* KPI Grid 2x2 */}

                  <div className="grid grid-cols-2 gap-2">

                    <div className="p-2.5 bg-white rounded-xl border border-slate-200/70 shadow-2xs">

                      <span className="text-[10px] text-gray-500 block">Produksi Steam</span>

                      <span className="text-sm font-bold text-gray-900 block mt-0.5">

                        {selectedDay.total_steam_usage_kg?.toLocaleString() ?? '-'} <span className="text-[10px] font-normal text-gray-500">kg</span>

                      </span>

                    </div>

                    <div className="p-2.5 bg-white rounded-xl border border-slate-200/70 shadow-2xs">

                      <span className="text-[10px] text-gray-500 block">Tekanan Rata-rata</span>

                      <span className="text-sm font-bold text-gray-900 block mt-0.5">

                        {selectedDay.avg_pressure ?? '-'} <span className="text-[10px] font-normal text-gray-500">Bar</span>

                      </span>

                      {selectedDay.pressure_ideal_percent != null && (

                        <span className="text-[9.5px] text-emerald-600 font-semibold block mt-0.5">

                          {selectedDay.pressure_ideal_percent}% Ideal

                        </span>

                      )}

                    </div>

                    <div className="p-2.5 bg-white rounded-xl border border-slate-200/70 shadow-2xs">

                      <span className="text-[10px] text-gray-500 block">Batu Bara</span>

                      <span className="text-sm font-bold text-gray-900 block mt-0.5">

                        {selectedDay.total_fuel_kg != null ? `${selectedDay.total_fuel_kg.toLocaleString()}` : '-'} <span className="text-[10px] font-normal text-gray-500">kg</span>

                      </span>

                    </div>

                    <div className="p-2.5 bg-white rounded-xl border border-slate-200/70 shadow-2xs">

                      <span className="text-[10px] text-gray-500 block">SFC (Steam / Fuel)</span>

                      <span className="text-sm font-bold text-gray-900 block mt-0.5">

                        {selectedDay.specific_fuel_consumption ?? '-'}

                      </span>

                      {selectedDay.steam_efficiency_percent != null && (

                        <span className="text-[9.5px] text-gray-500 block mt-0.5">

                          Eff: {selectedDay.steam_efficiency_percent}%

                        </span>

                      )}

                    </div>

                  </div>

                  {selectedDay.alert_count_critical > 0 && (

                    <div className="flex items-center gap-2 p-2 bg-red-50 border border-red-200 rounded-xl text-red-700 text-xs font-semibold">

                      <AlertTriangle size={14} className="shrink-0 text-red-500" />

                      <span>Terdeteksi {selectedDay.alert_count_critical} kondisi kritis pada tanggal ini.</span>

                    </div>

                  )}

                  {/* CTA Button to Full 24h Report */}

                  <button

                    type="button"

                    onClick={() => goToDay(selectedDate)}

                    className="w-full py-2.5 px-4 bg-blue-600 hover:bg-blue-700 active:scale-[0.98] text-white font-bold text-xs rounded-xl flex items-center justify-center gap-2 shadow-xs transition-all"

                  >

                    <span>Buka Laporan 24 Jam ({selectedDate})</span>

                    <ArrowRight size={14} />

                  </button>

                </div>

              ) : (

                <div className="py-6 text-center text-xs text-gray-400">

                  Belum ada data rekaman operasional untuk tanggal ini.

                </div>

              )}

            </div>

          </div>

          {/* ═══════════════════════════════════════════════════════════════ */}

          {/* 🖥️ 2. DESKTOP VIEW ONLY (≥ md: 768px): 100% UNCHANGED ORIGINAL */}

          {/* ═══════════════════════════════════════════════════════════════ */}

          <div className="hidden md:block">

            {/* Weekday header */}

            <div className="grid grid-cols-7 gap-2 mb-2">

              {WEEKDAY_NAMES.map((wd) => (

                <div key={wd} className="text-center text-xs font-bold text-gray-400 uppercase py-1">{wd}</div>

              ))}

            </div>

            {/* Calendar grid */}

            <div className="grid grid-cols-7 gap-2">

              {calendarCells.map((dateStr, idx) => {

                if (!dateStr) return <div key={`empty-${idx}`} className="min-h-[110px] sm:min-h-[130px]" />;

                const day = daysByDate[dateStr];

                const dayNum = parseInt(dateStr.split('-')[2], 10);

                const isBest = dateStr === bestDate;

                const isWorst = dateStr === worstDate && bestDate !== worstDate;

                const colorClass = day ? getFuelColor(day.specific_fuel_consumption, monthStats.minSfc, monthStats.maxSfc) : 'bg-gray-50 border-gray-100';

                return (

                  <button

                    key={dateStr}

                    onClick={() => goToDay(dateStr)}

                    className={`relative min-h-[110px] sm:min-h-[130px] text-left p-2 rounded-xl border transition-all hover:shadow-md hover:-translate-y-0.5 ${colorClass}`}

                  >

                    <div className="flex items-center justify-between mb-1">

                      <span className="text-sm font-bold text-gray-700">{dayNum}</span>

                      {isBest && (

                        <span title="Hari paling efisien bulan ini" className="flex items-center gap-0.5 text-[10px] font-bold text-amber-600 bg-amber-100 px-1.5 py-0.5 rounded-full border border-amber-300">

                          <Star size={10} fill="currentColor" /> Terbaik

                        </span>

                      )}

                      {isWorst && (

                        <span title="Hari paling boros / tidak stabil" className="text-[10px] font-bold text-red-600 bg-red-100 px-1.5 py-0.5 rounded-full border border-red-300">

                          Perlu Cek

                        </span>

                      )}

                    </div>

                    {day ? (

                      <div className="space-y-0.5 text-[10px] leading-tight text-gray-600">

                        <div className="flex justify-between">

                          <span>Steam</span>

                          <span className="font-semibold text-gray-800">{day.total_steam_usage_kg?.toLocaleString() ?? '-'} kg</span>

                        </div>

                        <div className="flex justify-between">

                          <span>Tekanan</span>

                          <span className="font-semibold text-gray-800">{day.avg_pressure ?? '-'} Bar</span>

                        </div>

                        <div className="flex justify-between">

                          <span>Batu Bara</span>

                          <span className="font-semibold text-gray-800">{day.total_fuel_kg != null ? `${day.total_fuel_kg.toLocaleString()} kg` : '-'}</span>

                        </div>

                        <div className="flex justify-between">

                          <span>SFC</span>

                          <span className="font-semibold text-gray-800">{day.specific_fuel_consumption ?? '-'}</span>

                        </div>

                        <div className="flex justify-between">

                          <span>Ideal%</span>

                          <span className="font-semibold text-gray-800">{day.pressure_ideal_percent != null ? `${day.pressure_ideal_percent}%` : '-'}</span>

                        </div>

                        <div className="flex justify-between">

                          <span>Steam Eff%</span>

                          <span className="font-semibold text-gray-800">{day.steam_efficiency_percent != null ? `${day.steam_efficiency_percent}%` : '-'}</span>

                        </div>

                        {day.alert_count_critical > 0 && (

                          <div className="flex items-center gap-1 text-red-600 font-semibold pt-0.5">

                            <AlertTriangle size={10} /> {day.alert_count_critical} kritis

                          </div>

                        )}

                      </div>

                    ) : (

                      <div className="text-[10px] text-gray-300">Tidak ada data</div>

                    )}

                  </button>

                );

              })}

            </div>

          </div>

          {/* Legend (Shared) */}

          <div className="flex flex-wrap items-center gap-2 sm:gap-4 mt-5 pt-4 border-t border-gray-100 text-[11px] sm:text-xs text-gray-500">

            <span className="font-semibold text-gray-600 w-full sm:w-auto">Warna = Specific Fuel Consumption (kg steam/kg fuel):</span>

            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-emerald-100 border border-emerald-300 inline-block shrink-0" /> Paling efisien</span>

            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-lime-100 border border-lime-300 inline-block shrink-0" /> Efisien</span>

            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-amber-100 border border-amber-300 inline-block shrink-0" /> Cukup</span>

            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-red-100 border border-red-300 inline-block shrink-0" /> Boros</span>

            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-gray-50 border border-gray-200 inline-block shrink-0" /> Belum ada data</span>

          </div>

          <p className="text-[10.5px] sm:text-xs text-gray-400 mt-2">

            Klik tanggal untuk melihat detail lengkap hari itu di Boiler Report. &quot;Hari Terbaik&quot; dipilih dari gabungan efisiensi bahan bakar, persentase tekanan ideal, dan jumlah alert kritis.

          </p>

        </div>

      )}

    </div>

  );

};

export default BoilerCalendar;

