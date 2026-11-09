import React, { useState, useMemo } from 'react';
import { flushSync } from 'react-dom';
import { RefreshCw, ChevronDown, ChevronRight, LayoutList, ListTree, Download, Printer } from 'lucide-react';
import * as XLSX from 'xlsx';
import { useGetPerformanceSummaryQuery } from '../store/performanceApi';
import { BACKEND_BASE_URL } from '../lib/api';
const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

const STEAM_LABELS = {
  'sehat': { label: 'Sehat (>= 3.8)', color: 'text-green-700 bg-green-50' },
  'kurang_bagus': { label: 'Kurang Bagus (< 3.8)', color: 'text-red-700 bg-red-50' },
  'tidak_lengkap': { label: 'Data Tidak Lengkap', color: 'text-gray-500 bg-gray-100' }
};

const getDeviationColor = (actual, ideal) => {
  if (!actual || !ideal) return '';
  const diffPercent = ((actual - ideal) / ideal) * 100;
  if (diffPercent > 15) return 'text-red-700 font-semibold bg-red-50';
  if (diffPercent > 5) return 'text-yellow-700 font-semibold bg-yellow-50';
  return '';
};

const calculateEfficiency = (idealTotal, avgEffective) => {
  if (!idealTotal || !avgEffective || avgEffective <= 0) return { display: '-', color: '' };
  const eff = (idealTotal / avgEffective) * 100;
  
  let color = 'text-red-700 font-semibold bg-red-50';
  if (eff >= 80) {
    color = 'text-green-700 font-semibold bg-green-50';
  } else if (eff >= 60) {
    color = 'text-orange-600 font-semibold bg-orange-50';
  }
  
  return { display: `${eff.toFixed(1)}%`, color };
};

const PerformanceSummary = () => {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [isFlatView, setIsFlatView] = useState(false);
  const [filterDate, setFilterDate] = useState('');
  const [filterMachine, setFilterMachine] = useState('');
  const [filterProgram, setFilterProgram] = useState('');

  const { data, isLoading, isFetching, refetch } = useGetPerformanceSummaryQuery({ year, month });

  const years = data?.years || [now.getFullYear()];
  const flatData = data?.data || [];
  const rawData = data?.raw_data || [];
  const unidentifiedRawData = data?.unidentified_raw_data || [];

  const machineOptions = useMemo(() => {
    const seen = new Map();
    rawData.forEach(r => { if (!seen.has(r.machine__code)) seen.set(r.machine__code, r.machine__name); });
    return [...seen.entries()].sort((a, b) => a[0].localeCompare(b[0], undefined, { numeric: true }));
  }, [rawData]);

  const programOptions = useMemo(() => {
    const seen = new Map();
    rawData.forEach(r => {
      if (!seen.has(r.identity__program_id)) seen.set(r.identity__program_id, r.identity__program__nama);
    });
    return [...seen.entries()].sort((a, b) => (a[1] || '').localeCompare(b[1] || ''));
  }, [rawData]);

  const filteredRawData = useMemo(() => {
    return rawData.filter(row => {
      if (filterDate) {
        const rowDate = new Date(row.start_time).toLocaleDateString('en-CA', { timeZone: 'Asia/Jakarta' });
        if (rowDate !== filterDate) return false;
      }
      if (filterMachine && row.machine__code !== filterMachine) return false;
      if (filterProgram && String(row.identity__program_id) !== filterProgram) return false;
      return true;
    });
  }, [rawData, filterDate, filterMachine, filterProgram]);

  const dynamicStats = useMemo(() => {
    let total_ideal = 0;
    let total_effective = 0;
    let total_sehat = 0;
    let total_identified = filteredRawData.length;

    filteredRawData.forEach(row => {
      total_ideal += (row.identity__program__durasi_ideal || 0);
      total_effective += (row.avg_duration_effective || 0);
      if (row.steam_category === 'sehat') total_sehat += 1;
    });

    const avg_eff = total_effective > 0 ? (total_ideal / total_effective) * 100 : 0;
    const health_percent = total_identified > 0 ? (total_sehat / total_identified) * 100 : 0;

    let total_unidentified = unidentifiedRawData.length;
    if (filterDate || filterMachine) {
      const filteredUnidentified = unidentifiedRawData.filter(row => {
        if (filterDate) {
          const rowDate = new Date(row.start_time).toLocaleDateString('en-CA', { timeZone: 'Asia/Jakarta' });
          if (rowDate !== filterDate) return false;
        }
        if (filterMachine && row.machine__code !== filterMachine) return false;
        return true;
      });
      total_unidentified = filterProgram ? 0 : filteredUnidentified.length;
    } else if (filterProgram) {
      total_unidentified = 0;
    }

    return {
      avg_eff,
      health_percent,
      total_identified,
      total_unidentified
    };
  }, [filteredRawData, unidentifiedRawData, filterDate, filterMachine, filterProgram]);

  const filteredFlatData = useMemo(() => {
    const hasAnyFilter = filterDate || filterMachine || filterProgram;

    if (!hasAnyFilter) {
      return [...flatData].sort((a, b) => {
        const mc = (a.machine__code || '').localeCompare(b.machine__code || '', undefined, { numeric: true });
        if (mc !== 0) return mc;
        return (a.identity__program__nama || '').localeCompare(b.identity__program__nama || '');
      });
    }

    const groups = {};
    filteredRawData.forEach(row => {
      const key = `${row.machine__code}::${row.identity__program_id}::${row.steam_category}`;
      if (!groups[key]) {
        groups[key] = {
          machine__code: row.machine__code,
          machine__name: row.machine__name,
          identity__program_id: row.identity__program_id,
          identity__program__nama: row.identity__program__nama,
          identity__program__durasi_ideal: row.identity__program__durasi_ideal,
          identity__program__durasi_heating_ideal: row.identity__program__durasi_heating_ideal,
          identity__program__durasi_keeping_ideal: row.identity__program__durasi_keeping_ideal,
          identity__program__durasi_cooling_ideal: row.identity__program__durasi_cooling_ideal,
          steam_category: row.steam_category,
          total_batches: 0,
          _sum_heating: 0,   _n_heating: 0,
          _sum_steady: 0,    _n_steady: 0,
          _sum_cooling: 0,   _n_cooling: 0,
          _sum_effective: 0, _n_effective: 0,
          _sum_max_temp: 0,  _n_max_temp: 0,
          _sum_pressure: 0,  _n_pressure: 0,
        };
      }
      const g = groups[key];
      g.total_batches += 1;

      if (row.avg_heating_duration   != null) { g._sum_heating   += row.avg_heating_duration;   g._n_heating   += 1; }
      if (row.avg_steady_duration    != null) { g._sum_steady    += row.avg_steady_duration;    g._n_steady    += 1; }
      if (row.avg_cooling_duration   != null) { g._sum_cooling   += row.avg_cooling_duration;   g._n_cooling   += 1; }
      if (row.avg_duration_effective != null) { g._sum_effective += row.avg_duration_effective; g._n_effective += 1; }
      if (row.avg_max_temp           != null) { g._sum_max_temp  += row.avg_max_temp;           g._n_max_temp  += 1; }
      if (row.avg_avg_steam_pressure != null) { g._sum_pressure  += row.avg_avg_steam_pressure; g._n_pressure  += 1; }
    });

    return Object.values(groups).map(g => ({
      ...g,
      avg_heating_duration:   g._n_heating   > 0 ? g._sum_heating   / g._n_heating   : null,
      avg_steady_duration:    g._n_steady    > 0 ? g._sum_steady    / g._n_steady    : null,
      avg_cooling_duration:   g._n_cooling   > 0 ? g._sum_cooling   / g._n_cooling   : null,
      avg_duration_effective: g._n_effective > 0 ? g._sum_effective / g._n_effective : null,
      avg_max_temp:           g._n_max_temp  > 0 ? g._sum_max_temp  / g._n_max_temp  : null,
      avg_avg_steam_pressure: g._n_pressure  > 0 ? g._sum_pressure  / g._n_pressure  : null,
    })).sort((a, b) => {
      const mc = (a.machine__code || '').localeCompare(b.machine__code || '', undefined, { numeric: true });
      if (mc !== 0) return mc;
      return (a.identity__program__nama || '').localeCompare(b.identity__program__nama || '');
    });
  }, [flatData, filteredRawData, filterDate, filterMachine, filterProgram]);

  const [expandedDates, setExpandedDates] = useState({});
  const [expandedMachines, setExpandedMachines] = useState({});
  const [expandedPrograms, setExpandedPrograms] = useState({});

  const toggleDate = (dateStr) => setExpandedDates(p => ({ ...p, [dateStr]: !p[dateStr] }));
  const toggleMachine = (key) => setExpandedMachines(p => ({ ...p, [key]: !p[key] }));
  const toggleProgram = (key) => setExpandedPrograms(p => ({ ...p, [key]: !p[key] }));

  const nestedData = useMemo(() => {
    if (!filteredRawData.length) return {};
    const dates = {};
    
    filteredRawData.forEach(row => {
      const dateObj = new Date(row.start_time);
      const dateStr = dateObj.toLocaleDateString('en-CA', { timeZone: 'Asia/Jakarta' }); 
      
      if (!dates[dateStr]) {
        dates[dateStr] = {
          date: dateStr,
          total_batches: 0,
          total_ideal_heat: 0, total_real_heat: 0,
          total_ideal_hold: 0, total_real_hold: 0,
          total_ideal_cool: 0, total_real_cool: 0,
          total_ideal_total: 0, total_real_effective: 0,
          total_sehat_batches: 0,
          unique_machines: new Set(),
          machines: {}
        };
      }
      
      const d = dates[dateStr];
      const mCode = row.machine__code;
      
      if (!d.machines[mCode]) {
        d.machines[mCode] = {
          code: mCode,
          name: row.machine__name || mCode,
          total_batches: 0,
          total_ideal_heat: 0, total_real_heat: 0,
          total_ideal_hold: 0, total_real_hold: 0,
          total_ideal_cool: 0, total_real_cool: 0,
          total_ideal_total: 0, total_real_effective: 0,
          total_sehat_batches: 0,
          unique_programs: new Set(),
          programs: {}
        };
      }
      
      const m = d.machines[mCode];
      const pId = row.identity__program_id;
      
      if (!m.programs[pId]) {
        m.programs[pId] = {
          id: pId,
          name: row.identity__program__nama,
          ideal_total: row.identity__program__durasi_ideal,
          ideal_heat: row.identity__program__durasi_heating_ideal,
          ideal_hold: row.identity__program__durasi_keeping_ideal,
          ideal_cool: row.identity__program__durasi_cooling_ideal,
          total_batches: 0,
          total_real_heat: 0, total_real_hold: 0, total_real_cool: 0,
          total_real_effective: 0, total_max_temp: 0, total_pressure: 0,
          total_sehat_batches: 0,
          batches: []
        };
      }
      
      const p = m.programs[pId];
      const batchCount = 1;

      // Accumulate for Date
      d.total_batches += batchCount;
      d.total_ideal_heat += (row.identity__program__durasi_heating_ideal || 0);
      d.total_real_heat += (row.avg_heating_duration || 0);
      d.total_ideal_hold += (row.identity__program__durasi_keeping_ideal || 0);
      d.total_real_hold += (row.avg_steady_duration || 0);
      d.total_ideal_cool += (row.identity__program__durasi_cooling_ideal || 0);
      d.total_real_cool += (row.avg_cooling_duration || 0);
      d.total_ideal_total += (row.identity__program__durasi_ideal || 0);
      d.total_real_effective += (row.avg_duration_effective || 0);
      if (row.steam_category === 'sehat') d.total_sehat_batches += batchCount;
      d.unique_machines.add(mCode);

      // Accumulate for Machine
      m.total_batches += batchCount;
      m.total_ideal_heat += (row.identity__program__durasi_heating_ideal || 0);
      m.total_real_heat += (row.avg_heating_duration || 0);
      m.total_ideal_hold += (row.identity__program__durasi_keeping_ideal || 0);
      m.total_real_hold += (row.avg_steady_duration || 0);
      m.total_ideal_cool += (row.identity__program__durasi_cooling_ideal || 0);
      m.total_real_cool += (row.avg_cooling_duration || 0);
      m.total_ideal_total += (row.identity__program__durasi_ideal || 0);
      m.total_real_effective += (row.avg_duration_effective || 0);
      if (row.steam_category === 'sehat') m.total_sehat_batches += batchCount;
      m.unique_programs.add(pId);

      // Accumulate for Program
      p.total_batches += batchCount;
      p.total_real_heat += (row.avg_heating_duration || 0);
      p.total_real_hold += (row.avg_steady_duration || 0);
      p.total_real_cool += (row.avg_cooling_duration || 0);
      p.total_real_effective += (row.avg_duration_effective || 0);
      p.total_max_temp += (row.avg_max_temp || 0);
      p.total_pressure += (row.avg_avg_steam_pressure || 0);
      if (row.steam_category === 'sehat') p.total_sehat_batches += batchCount;
      
      p.batches.push(row);
    });

    return Object.values(dates).sort((a, b) => b.date.localeCompare(a.date));
  }, [filteredRawData]);

  const renderDataRow = (row, isFlat, prog = null) => {
    const idealTotal = isFlat ? row.identity__program__durasi_ideal : prog.ideal_total;
    const idealHeat = isFlat ? row.identity__program__durasi_heating_ideal : prog.ideal_heat;
    const idealHold = isFlat ? row.identity__program__durasi_keeping_ideal : prog.ideal_hold;
    const idealCool = isFlat ? row.identity__program__durasi_cooling_ideal : prog.ideal_cool;
    
    const eff = calculateEfficiency(idealTotal, row.avg_duration_effective);

    return (
      <>
        {/* Heat */}
        <td className="px-3 py-2 text-gray-500 whitespace-nowrap">{idealHeat || '-'}</td>
        <td className={`px-3 py-2 whitespace-nowrap ${getDeviationColor(row.avg_heating_duration, idealHeat)}`}>
          {row.avg_heating_duration?.toFixed(1) || '-'}
        </td>
        {/* Hold */}
        <td className="px-3 py-2 text-gray-500 whitespace-nowrap">{idealHold || '-'}</td>
        <td className={`px-3 py-2 whitespace-nowrap ${getDeviationColor(row.avg_steady_duration, idealHold)}`}>
          {row.avg_steady_duration?.toFixed(1) || '-'}
        </td>
        {/* Cool */}
        <td className="px-3 py-2 text-gray-500 whitespace-nowrap">{idealCool || '-'}</td>
        <td className={`px-3 py-2 whitespace-nowrap ${getDeviationColor(row.avg_cooling_duration, idealCool)}`}>
          {row.avg_cooling_duration?.toFixed(1) || '-'}
        </td>
        
        {/* Eff */}
        <td className={`px-3 py-2 whitespace-nowrap ${eff.color}`}>{eff.display}</td>
        
        {/* Max Temp & Pressure */}
        <td className="px-3 py-2 whitespace-nowrap">{row.avg_max_temp?.toFixed(1) || '-'}</td>
        <td className="px-3 py-2 whitespace-nowrap">{row.avg_avg_steam_pressure?.toFixed(2) || '-'}</td>
      </>
    );
  };

  const tableHeaders = (
    <tr>
      <th className="px-3 py-2.5 font-semibold">{isFlatView ? 'Mesin' : 'Tanggal / Mesin'}</th>
      <th className="px-3 py-2.5 font-semibold">Program</th>
      <th className="px-3 py-2.5 font-semibold">Kondisi Steam</th>
      <th className="px-3 py-2.5 font-semibold">Batch</th>
      <th className="px-3 py-2.5 font-semibold text-gray-400">Heat (Idl)</th>
      <th className="px-3 py-2.5 font-semibold">Heat (Rl)</th>
      <th className="px-3 py-2.5 font-semibold text-gray-400">Hold (Idl)</th>
      <th className="px-3 py-2.5 font-semibold">Hold (Rl)</th>
      <th className="px-3 py-2.5 font-semibold text-gray-400">Cool (Idl)</th>
      <th className="px-3 py-2.5 font-semibold">Cool (Rl)</th>
      <th className="px-3 py-2.5 font-semibold">Eff (%)</th>
      <th className="px-3 py-2.5 font-semibold">Max Temp</th>
      <th className="px-3 py-2.5 font-semibold">Pressure</th>
    </tr>
  );
  const handleExportExcel = () => {
    const wb = XLSX.utils.book_new();

    // --- Sheet 1: Flatten View ---
    const s1Header = [
      ['=== RINGKASAN KPI ==='],
      [`Avg Efficiency: ${dynamicStats.avg_eff.toFixed(1)}%`,
       `Health Batch: ${dynamicStats.health_percent.toFixed(1)}%`,
       `Total Identified: ${dynamicStats.total_identified}`,
       `Total Unidentified: ${dynamicStats.total_unidentified}`],
      [],
      ['Mesin', 'Program', 'Kondisi Steam', 'Jml Batch',
       'Heat Ideal (m)', 'Heat Real (m)',
       'Hold Ideal (m)', 'Hold Real (m)',
       'Cool Ideal (m)', 'Cool Real (m)',
       'Eff (%)', 'Max Temp (°C)', 'Pressure (Bar)']
    ];

    const s1Rows = filteredFlatData.map(row => {
      const idealTotal = row.identity__program__durasi_ideal;
      const eff = row.avg_duration_effective > 0
        ? ((idealTotal / row.avg_duration_effective) * 100).toFixed(1)
        : '-';
      return [
        row.machine__name || row.machine__code,
        row.identity__program__nama,
        STEAM_LABELS[row.steam_category]?.label || row.steam_category,
        row.total_batches,
        row.identity__program__durasi_heating_ideal ?? '-',
        row.avg_heating_duration?.toFixed(1) ?? '-',
        row.identity__program__durasi_keeping_ideal ?? '-',
        row.avg_steady_duration?.toFixed(1) ?? '-',
        row.identity__program__durasi_cooling_ideal ?? '-',
        row.avg_cooling_duration?.toFixed(1) ?? '-',
        eff,
        row.avg_max_temp?.toFixed(1) ?? '-',
        row.avg_avg_steam_pressure?.toFixed(2) ?? '-',
      ];
    });

    const ws1 = XLSX.utils.aoa_to_sheet([...s1Header, ...s1Rows]);
    XLSX.utils.book_append_sheet(wb, ws1, 'Flatten View');

    // --- Sheet 2: Raw Batches ---
    const s2Header = [
      ['Tanggal', 'Waktu Mulai', 'Mesin', 'Batch', 'Program', 'Kondisi Steam',
       'Heat Ideal (m)', 'Heat Real (m)',
       'Hold Ideal (m)', 'Hold Real (m)',
       'Cool Ideal (m)', 'Cool Real (m)',
       'Eff (%)', 'Max Temp (°C)', 'Pressure (Bar)']
    ];

    const sortedRaw = [...filteredRawData].sort((a, b) =>
      new Date(a.start_time) - new Date(b.start_time)
    );

    const s2Rows = sortedRaw.map(row => {
      const dt = new Date(row.start_time);
      const dateStr = dt.toLocaleDateString('en-CA', { timeZone: 'Asia/Jakarta' });
      const timeStr = dt.toLocaleTimeString('id-ID', { timeZone: 'Asia/Jakarta', hour: '2-digit', minute: '2-digit' });
      const idealTotal = row.identity__program__durasi_ideal;
      const eff = row.avg_duration_effective > 0
        ? ((idealTotal / row.avg_duration_effective) * 100).toFixed(1)
        : '-';
      return [
        dateStr,
        timeStr,
        row.machine__name || row.machine__code,
        row.identity__batch,
        row.identity__program__nama,
        STEAM_LABELS[row.steam_category]?.label || row.steam_category,
        row.identity__program__durasi_heating_ideal ?? '-',
        row.avg_heating_duration?.toFixed(1) ?? '-',
        row.identity__program__durasi_keeping_ideal ?? '-',
        row.avg_steady_duration?.toFixed(1) ?? '-',
        row.identity__program__durasi_cooling_ideal ?? '-',
        row.avg_cooling_duration?.toFixed(1) ?? '-',
        eff,
        row.avg_max_temp?.toFixed(1) ?? '-',
        row.avg_avg_steam_pressure?.toFixed(2) ?? '-',
      ];
    });

    const ws2 = XLSX.utils.aoa_to_sheet([...s2Header, ...s2Rows]);
    XLSX.utils.book_append_sheet(wb, ws2, 'Raw Batches');

    // Nama file dinamis
    const monthName = MONTHS[month - 1];
    const machineLabel = filterMachine || 'Semua';
    XLSX.writeFile(wb, `Performance_${machineLabel}_${monthName}-${year}.xlsx`);
  };

  const handlePrint = () => {
    const allDates = {};
    const allMachines = {};
    const allPrograms = {};

    nestedData.forEach(dateObj => {
      allDates[dateObj.date] = true;
      Object.values(dateObj.machines).forEach(machine => {
        const mKey = `${dateObj.date}-${machine.code}`;
        allMachines[mKey] = true;
        Object.keys(machine.programs).forEach(pId => {
          const pKey = `${dateObj.date}-${machine.code}-${pId}`;
          allPrograms[pKey] = true;
        });
      });
    });

    flushSync(() => {
      setExpandedDates(allDates);
      setExpandedMachines(allMachines);
      setExpandedPrograms(allPrograms);
    });

    const style = document.createElement('style');
    style.id = 'perf-print-page-style';
    style.textContent = '@page { size: A4 landscape; margin: 8mm 6mm; }';
    document.head.appendChild(style);

    document.documentElement.classList.add('printing-performance');

    const cleanup = () => {
      document.documentElement.classList.remove('printing-performance');
      document.getElementById('perf-print-page-style')?.remove();
    };
    window.addEventListener('afterprint', cleanup, { once: true });

    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        window.print();
      });
    });
  };

  return (
    <div className="p-4 sm:p-6 bg-gray-50 min-h-full pb-20 md:pb-6">
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-4 mb-4 flex flex-wrap gap-3 items-end justify-between no-print">
        <div className="flex flex-wrap gap-3 items-end">
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">Bulan</label>
            <select value={month} onChange={(e) => setMonth(Number(e.target.value))} className="border border-gray-300 rounded-md text-sm px-2 py-1.5 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500">
              {MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">Tahun</label>
            <select value={year} onChange={(e) => setYear(Number(e.target.value))} className="border border-gray-300 rounded-md text-sm px-2 py-1.5 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500">
              {years.map((y) => <option key={y} value={y}>{y}</option>)}
            </select>
          </div>
          <div className="border-l border-gray-300 mx-1 h-8 self-center"></div>
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">Tanggal (Filter)</label>
            <div className="flex items-center gap-1">
              <input type="date" value={filterDate} onChange={e => setFilterDate(e.target.value)}
                className="border border-gray-300 rounded-md text-sm px-2 py-1.5 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500" />
              {filterDate && (
                <button onClick={() => setFilterDate('')} className="text-xs text-gray-400 hover:text-red-500 px-1">✕</button>
              )}
            </div>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">Mesin (Filter)</label>
            <select value={filterMachine} onChange={e => setFilterMachine(e.target.value)} className="border border-gray-300 rounded-md text-sm px-2 py-1.5 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500">
              <option value="">Semua Mesin</option>
              {machineOptions.map(([code, name]) => <option key={code} value={code}>{name || code}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">Program (Filter)</label>
            <select value={filterProgram} onChange={e => setFilterProgram(e.target.value)} className="border border-gray-300 rounded-md text-sm px-2 py-1.5 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 max-w-[150px] truncate">
              <option value="">Semua Program</option>
              {programOptions.map(([id, name]) => <option key={id} value={String(id)}>{name}</option>)}
            </select>
          </div>
          <button onClick={refetch} className="p-2 ml-1 rounded-md border border-gray-300 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500" title="Refresh">
            <RefreshCw className={`w-4 h-4 text-gray-600 ${isFetching ? 'animate-spin' : ''}`} />
          </button>
        </div>
        
        <div className="flex items-center gap-2">
          <button
            onClick={handleExportExcel}
            disabled={filteredRawData.length === 0}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium bg-green-50 border border-green-300 rounded-md hover:bg-green-100 text-green-700 disabled:opacity-40"
          >
            <Download className="w-4 h-4" />
            Export Excel
          </button>

          <button
            onClick={handlePrint}
            disabled={filteredRawData.length === 0}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium bg-blue-50 border border-blue-300 rounded-md hover:bg-blue-100 text-blue-700 disabled:opacity-40"
          >
            <Printer className="w-4 h-4" />
            Print A4
          </button>

          <button 
            onClick={() => setIsFlatView(!isFlatView)}
            className="flex items-center gap-2 px-3 py-1.5 text-sm font-medium bg-white border border-gray-300 rounded-md hover:bg-gray-50 text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            {isFlatView ? <ListTree className="w-4 h-4" /> : <LayoutList className="w-4 h-4" />}
            {isFlatView ? 'Nested View' : 'Flatten View'}
          </button>
        </div>
      </div>

      {dynamicStats && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4 no-print">
          {/* Kartu 1: Avg Efficiency */}
          <div className="bg-white rounded-xl border border-gray-200 p-3 shadow-sm">
            <p className="text-xs text-gray-500 font-medium">Avg Machine Efficiency</p>
            <p className="text-xl font-bold text-gray-900">
              {dynamicStats.avg_eff?.toFixed(1) || '0.0'}%
            </p>
          </div>

          {/* Kartu 2: Health Batch */}
          <div className="bg-white rounded-xl border border-gray-200 p-3 shadow-sm">
            <p className="text-xs text-gray-500 font-medium">Health Batch (Sehat)</p>
            <p className="text-xl font-bold text-green-600">
              {dynamicStats.health_percent?.toFixed(1) || '0.0'}%
            </p>
          </div>

          {/* Kartu 3: Identified */}
          <div className="bg-white rounded-xl border border-gray-200 p-3 shadow-sm">
            <p className="text-xs text-gray-500 font-medium">Total Batch (Identified)</p>
            <p className="text-xl font-bold text-blue-600">
              {dynamicStats.total_identified || 0}
            </p>
          </div>

          {/* Kartu 4: Unidentified */}
          <div className="bg-white rounded-xl border border-gray-200 p-3 shadow-sm">
            <p className="text-xs text-gray-500 font-medium">Total Batch (Unidentified)</p>
            <p className="text-xl font-bold text-red-500">
              {dynamicStats.total_unidentified || 0}
            </p>
          </div>
        </div>
      )}

      <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-x-auto print-area">
        {dynamicStats && (
          <div className="hidden print:block perf-print-header text-sm p-4 border-b border-gray-200">
            <h2 className="text-lg font-bold">Laporan Performa Mesin Dyeing</h2>
            <p className="text-gray-600 mt-1">
              Periode: {MONTHS[month-1]} {year} 
              {filterDate ? ` | Tanggal: ${filterDate}` : ''} 
              {filterMachine ? ` | Mesin: ${filterMachine}` : ''}
              {filterProgram ? ` | Program ID: ${filterProgram}` : ''}
            </p>
            <p className="text-gray-600 text-xs mt-1">Dicetak: {new Date().toLocaleString('id-ID')}</p>
            <div className="grid grid-cols-4 gap-4 mt-3 pt-3 border-t border-gray-100 text-xs">
              <div>
                <span className="text-gray-500 block">Avg Efficiency</span>
                <span className="font-bold">{dynamicStats.avg_eff.toFixed(1)}%</span>
              </div>
              <div>
                <span className="text-gray-500 block">Health Batch</span>
                <span className="font-bold">{dynamicStats.health_percent.toFixed(1)}%</span>
              </div>
              <div>
                <span className="text-gray-500 block">Identified</span>
                <span className="font-bold">{dynamicStats.total_identified}</span>
              </div>
              <div>
                <span className="text-gray-500 block">Unidentified</span>
                <span className="font-bold">{dynamicStats.total_unidentified}</span>
              </div>
            </div>
          </div>
        )}

        {isLoading ? (
          <div className="p-12 text-center text-gray-400 text-sm">Memuat data performa...</div>
        ) : (isFlatView ? filteredFlatData.length === 0 : filteredRawData.length === 0) ? (
          <div className="p-12 text-center text-gray-400 text-sm">Tidak ada data untuk periode ini dengan filter yang dipilih.</div>
        ) : isFlatView ? (
          <table className="min-w-full text-xs text-left">
            <thead className="bg-gray-50 border-b border-gray-200 text-gray-500 uppercase">
              {tableHeaders}
            </thead>
            <tbody className="divide-y divide-gray-100">
              {filteredFlatData.map((row, idx) => (
                <tr key={idx} className="hover:bg-blue-50">
                  <td className="px-3 py-2 font-medium text-gray-800 whitespace-nowrap">{row.machine__name || row.machine__code}</td>
                  <td className="px-3 py-2 text-gray-700 max-w-[200px] truncate" title={row.identity__program__nama}>{row.identity__program__nama}</td>
                  <td className="px-3 py-2 whitespace-nowrap">
                      <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium ${STEAM_LABELS[row.steam_category]?.color || 'bg-gray-100'}`}>
                        {STEAM_LABELS[row.steam_category]?.label || row.steam_category}
                      </span>
                  </td>
                  <td className="px-3 py-2 font-semibold text-gray-800">{row.total_batches}</td>
                  {renderDataRow(row, true)}
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <table className="min-w-full text-xs text-left">
            <thead className="bg-gray-50 border-b border-gray-200 text-gray-500 uppercase">
              {tableHeaders}
            </thead>
            <tbody className="divide-y divide-gray-100">
              {nestedData.map(dateObj => {
                const dateHealthPercent = dateObj.total_batches > 0
                  ? ((dateObj.total_sehat_batches / dateObj.total_batches) * 100).toFixed(1) + '%'
                  : '-';
                const dateEff = calculateEfficiency(dateObj.total_ideal_total, dateObj.total_real_effective);
                const isDateExp = expandedDates[dateObj.date];
                
                return (
                  <React.Fragment key={dateObj.date}>
                    <tr className="bg-gray-100 hover:bg-gray-200 cursor-pointer border-t border-gray-300" onClick={() => toggleDate(dateObj.date)}>
                      <td className="px-3 py-2 font-bold text-gray-900 text-sm whitespace-nowrap flex items-center gap-1">
                        {isDateExp ? <ChevronDown className="w-4 h-4 text-gray-500" /> : <ChevronRight className="w-4 h-4 text-gray-500" />}
                        {dateObj.date}
                      </td>
                      <td className="px-3 py-2 text-gray-500 text-xs font-semibold">{dateObj.unique_machines.size} Mesin</td>
                      <td className="px-3 py-2 text-green-700 font-bold">{dateHealthPercent}</td>
                      <td className="px-3 py-2 font-bold text-blue-600">{dateObj.total_batches}</td>
                      
                      <td className="px-3 py-2 text-gray-500 font-medium">{dateObj.total_ideal_heat.toFixed(1)}</td>
                      <td className="px-3 py-2 font-medium text-gray-800">{dateObj.total_real_heat.toFixed(1)}</td>
                      
                      <td className="px-3 py-2 text-gray-500 font-medium">{dateObj.total_ideal_hold.toFixed(1)}</td>
                      <td className="px-3 py-2 font-medium text-gray-800">{dateObj.total_real_hold.toFixed(1)}</td>
                      
                      <td className="px-3 py-2 text-gray-500 font-medium">{dateObj.total_ideal_cool.toFixed(1)}</td>
                      <td className="px-3 py-2 font-medium text-gray-800">{dateObj.total_real_cool.toFixed(1)}</td>
                      
                      <td className={`px-3 py-2 ${dateEff.color}`}>{dateEff.display}</td>
                      <td className="px-3 py-2"></td>
                      <td className="px-3 py-2"></td>
                    </tr>
                    
                    {isDateExp && Object.values(dateObj.machines).sort((a,b) => a.code.localeCompare(b.code, undefined, {numeric: true})).map(machine => {
                      const mKey = `${dateObj.date}-${machine.code}`;
                      const isMachExp = expandedMachines[mKey];
                      const mHealthPercent = machine.total_batches > 0 
                        ? ((machine.total_sehat_batches / machine.total_batches) * 100).toFixed(1) + '%' 
                        : '-';
                      const mEff = calculateEfficiency(machine.total_ideal_total, machine.total_real_effective);
                      
                      return (
                        <React.Fragment key={mKey}>
                          <tr className="bg-white hover:bg-gray-50 cursor-pointer border-t border-gray-200" onClick={() => toggleMachine(mKey)}>
                            <td className="px-3 py-2 font-bold text-gray-900 text-sm whitespace-nowrap flex items-center gap-1 pl-6">
                              {isMachExp ? <ChevronDown className="w-4 h-4 text-gray-400" /> : <ChevronRight className="w-4 h-4 text-gray-400" />}
                              {machine.name}
                            </td>
                            <td className="px-3 py-2 text-gray-500 text-xs font-semibold">{machine.unique_programs.size} Prog</td>
                            <td className="px-3 py-2 text-green-700 font-bold">{mHealthPercent}</td>
                            <td className="px-3 py-2 font-bold text-blue-600">{machine.total_batches}</td>
                            
                            <td className="px-3 py-2 text-gray-500 font-medium">{machine.total_ideal_heat.toFixed(1)}</td>
                            <td className="px-3 py-2 font-medium text-gray-800">{machine.total_real_heat.toFixed(1)}</td>
                            
                            <td className="px-3 py-2 text-gray-500 font-medium">{machine.total_ideal_hold.toFixed(1)}</td>
                            <td className="px-3 py-2 font-medium text-gray-800">{machine.total_real_hold.toFixed(1)}</td>
                            
                            <td className="px-3 py-2 text-gray-500 font-medium">{machine.total_ideal_cool.toFixed(1)}</td>
                            <td className="px-3 py-2 font-medium text-gray-800">{machine.total_real_cool.toFixed(1)}</td>
                            
                            <td className={`px-3 py-2 ${mEff.color}`}>{mEff.display}</td>
                            <td className="px-3 py-2"></td>
                            <td className="px-3 py-2"></td>
                          </tr>
                          
                          {isMachExp && Object.values(machine.programs).map(prog => {
                            const pKey = `${mKey}-${prog.id}`;
                            const isProgExp = expandedPrograms[pKey];
                            const progHealthPercent = prog.total_batches > 0 
                              ? ((prog.total_sehat_batches / prog.total_batches) * 100).toFixed(1) + '%' 
                              : '-';
                            const progAvgHeat = prog.total_batches > 0 ? (prog.total_real_heat / prog.total_batches) : null;
                            const progAvgHold = prog.total_batches > 0 ? (prog.total_real_hold / prog.total_batches) : null;
                            const progAvgCool = prog.total_batches > 0 ? (prog.total_real_cool / prog.total_batches) : null;
                            const progAvgMaxTemp = prog.total_batches > 0 ? (prog.total_max_temp / prog.total_batches) : null;
                            const progAvgPressure = prog.total_batches > 0 ? (prog.total_pressure / prog.total_batches) : null;
                            const progAvgEffective = prog.total_batches > 0 ? (prog.total_real_effective / prog.total_batches) : 0;
                            const progEff = calculateEfficiency(prog.ideal_total, progAvgEffective);
                            
                            return (
                              <React.Fragment key={pKey}>
                                <tr className="bg-blue-50/30 hover:bg-blue-50 cursor-pointer" onClick={() => toggleProgram(pKey)}>
                                  <td className="px-3 py-2"></td>
                                  <td className="px-3 py-2 font-medium text-gray-800 pl-4 flex items-center gap-1">
                                    {isProgExp ? <ChevronDown className="w-3 h-3 text-gray-400" /> : <ChevronRight className="w-3 h-3 text-gray-400" />}
                                    {prog.name}
                                  </td>
                                  <td className="px-3 py-2 text-green-700 font-bold">{progHealthPercent}</td>
                                  <td className="px-3 py-2 font-semibold text-gray-700">{prog.total_batches}</td>
                                  
                                  <td className="px-3 py-2 text-gray-500 font-medium">{prog.ideal_heat || '-'}</td>
                                  <td className={`px-3 py-2 font-medium text-gray-800 ${getDeviationColor(progAvgHeat, prog.ideal_heat)}`}>{progAvgHeat !== null ? progAvgHeat.toFixed(1) : '-'}</td>
                                  
                                  <td className="px-3 py-2 text-gray-500 font-medium">{prog.ideal_hold || '-'}</td>
                                  <td className={`px-3 py-2 font-medium text-gray-800 ${getDeviationColor(progAvgHold, prog.ideal_hold)}`}>{progAvgHold !== null ? progAvgHold.toFixed(1) : '-'}</td>
                                  
                                  <td className="px-3 py-2 text-gray-500 font-medium">{prog.ideal_cool || '-'}</td>
                                  <td className={`px-3 py-2 font-medium text-gray-800 ${getDeviationColor(progAvgCool, prog.ideal_cool)}`}>{progAvgCool !== null ? progAvgCool.toFixed(1) : '-'}</td>
                                  
                                  <td className={`px-3 py-2 ${progEff.color}`}>{progEff.display}</td>
                                  
                                  <td className="px-3 py-2 font-medium text-gray-800">{progAvgMaxTemp !== null ? progAvgMaxTemp.toFixed(1) : '-'}</td>
                                  <td className="px-3 py-2 font-medium text-gray-800">{progAvgPressure !== null ? progAvgPressure.toFixed(2) : '-'}</td>
                                </tr>
                                
                                {isProgExp && prog.batches.sort((a, b) => new Date(b.start_time) - new Date(a.start_time)).map(batch => (
                                  <tr 
                                    key={batch.id} 
                                    className="bg-white hover:bg-gray-50 cursor-pointer"
                                    onClick={() => window.open(`${BACKEND_BASE_URL}/dyeing-report/${batch.identity__id}/`, '_blank')}
                                  >
                                    <td colSpan={2} className="px-3 py-2 pl-12 text-gray-600 font-mono">
                                      {new Date(batch.start_time).toLocaleTimeString('id-ID', { timeZone: 'Asia/Jakarta', hour: '2-digit', minute: '2-digit' })} - Batch {batch.identity__batch}
                                    </td>
                                    <td className="px-3 py-2 whitespace-nowrap">
                                      <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium border ${STEAM_LABELS[batch.steam_category]?.color || 'bg-gray-100'}`}>
                                        {STEAM_LABELS[batch.steam_category]?.label || batch.steam_category}
                                      </span>
                                    </td>
                                    <td className="px-3 py-2 text-gray-400 text-xs font-semibold">1</td>
                                    
                                    <td className="px-3 py-2 text-gray-400 font-medium">{prog.ideal_heat || '-'}</td>
                                    <td className={`px-3 py-2 font-medium text-gray-800 ${getDeviationColor(batch.avg_heating_duration, prog.ideal_heat)}`}>{batch.avg_heating_duration?.toFixed(1) || '-'}</td>
                                    
                                    <td className="px-3 py-2 text-gray-400 font-medium">{prog.ideal_hold || '-'}</td>
                                    <td className={`px-3 py-2 font-medium text-gray-800 ${getDeviationColor(batch.avg_steady_duration, prog.ideal_hold)}`}>{batch.avg_steady_duration?.toFixed(1) || '-'}</td>
                                    
                                    <td className="px-3 py-2 text-gray-400 font-medium">{prog.ideal_cool || '-'}</td>
                                    <td className={`px-3 py-2 font-medium text-gray-800 ${getDeviationColor(batch.avg_cooling_duration, prog.ideal_cool)}`}>{batch.avg_cooling_duration?.toFixed(1) || '-'}</td>
                                    
                                    <td className={`px-3 py-2 ${calculateEfficiency(prog.ideal_total, batch.avg_duration_effective).color}`}>
                                      {calculateEfficiency(prog.ideal_total, batch.avg_duration_effective).display}
                                    </td>
                                    
                                    <td className="px-3 py-2 font-medium text-gray-800">{batch.avg_max_temp?.toFixed(1) || '-'}</td>
                                    <td className="px-3 py-2 font-medium text-gray-800">{batch.avg_avg_steam_pressure?.toFixed(2) || '-'}</td>
                                  </tr>
                                ))}
                              </React.Fragment>
                            );
                          })}
                        </React.Fragment>
                      );
                    })}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};

export default PerformanceSummary;
