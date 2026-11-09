import React, { useState, useEffect, useMemo } from 'react';
import api from '../lib/api';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip as RechartsTooltip, ResponsiveContainer, LineChart, Line, BarChart, Bar
} from 'recharts';
import { Calendar, Droplet, Clock, CheckCircle, Activity, X, Search, ChevronLeft, ChevronRight } from 'lucide-react';

const formatBackendDate = (dateStr) => {
  if (!dateStr || dateStr === '-' || dateStr === 'In Progress') return dateStr;
  const months = {'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04', 'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08', 'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'};
  try {
    const parts = dateStr.replace(',', '').split(' ');
    if (parts.length === 4) {
      return `${parts[0].padStart(2, '0')}/${months[parts[1]] || '00'}/${parts[2]} ${parts[3]}`;
    }
    return dateStr;
  } catch(e) {
    return dateStr;
  }
};

export default function MonthlyReport() {
  const [startDate, setStartDate] = useState(() => {
    const now = new Date();
    const firstDay = new Date(now.getFullYear(), now.getMonth(), 1);
    return firstDay.toISOString().split('T')[0];
  });
  
  const [endDate, setEndDate] = useState(() => {
    const now = new Date();
    return now.toISOString().split('T')[0];
  });

  const [reportData, setReportData]   = useState(null);
  const [loading, setLoading]         = useState(false);
  const [error, setError]             = useState(null);
  const [searchQuery, setSearchQuery] = useState('');

  // Pagination for History Process groups
  const [groupPages, setGroupPages] = useState({});

  // Modal state
  const [processAnalyticsDetail, setProcessAnalyticsDetail] = useState(null);
  const [isProcessModalOpen, setIsProcessModalOpen] = useState(false);

  // Machine Process History Modal state
  const [isMachineModalOpen, setIsMachineModalOpen] = useState(false);
  const [machineProcessData, setMachineProcessData] = useState(null);
  const [selectedMachineName, setSelectedMachineName] = useState("");

  const fetchReport = async (start, end) => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get(`/report/monthly-summary?start_date=${start}&end_date=${end}`);
      setReportData(res.data);
      // Reset group pages
      const newGroupPages = {};
      res.data.history_groups.forEach(g => {
        newGroupPages[g.group_name] = 1;
      });
      setGroupPages(newGroupPages);
    } catch (err) {
      console.error('Gagal mengambil monthly report:', err);
      setError('Gagal mengambil data laporan. Pastikan format tanggal benar.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { 
    if (startDate && endDate) {
      fetchReport(startDate, endDate); 
    }
  }, [startDate, endDate]);

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

  const closeProcessModal = () => { setIsProcessModalOpen(false); setProcessAnalyticsDetail(null); };

  const openMachineProcessModal = async (machineId, machineName) => {
    setIsMachineModalOpen(true);
    setMachineProcessData(null);
    setSelectedMachineName(machineName);
    try {
      const res = await api.get(`/report/machine/${machineId}/process-history?start_date=${startDate}&end_date=${endDate}`);
      setMachineProcessData(res.data);
    } catch (err) {
      console.error('Gagal mengambil history proses mesin:', err);
    }
  };
  
  const closeMachineModal = () => { setIsMachineModalOpen(false); setMachineProcessData(null); setSelectedMachineName(""); };

  const CustomMachineTooltip = ({ active, payload, label }) => {
    if (active && payload && payload.length) {
      const data = payload[0].payload;
      return (
        <div className="bg-white p-3 rounded-lg shadow-[0_4px_20px_rgb(0,0,0,0.1)] border border-gray-100 text-sm min-w-[160px]">
          <p className="font-bold text-gray-800 mb-2 border-b border-gray-50 pb-1">{label}</p>
          <div className="flex justify-between gap-4 mb-1">
            <span className="text-gray-500">Jumlah Proses:</span>
            <span className="font-bold text-blue-600">{data.count}</span>
          </div>
          <div className="flex justify-between gap-4 mb-1">
            <span className="text-gray-500">Total Durasi:</span>
            <span className="font-semibold text-gray-700">{data.duration} m</span>
          </div>
          <div className="flex justify-between gap-4">
            <span className="text-gray-500">Total Uap:</span>
            <span className="font-semibold text-gray-700">{data.steam} kg</span>
          </div>
        </div>
      );
    }
    return null;
  };

  // ── Client-side search / filter ────────────────────────────────
  const filteredHistoryGroups = useMemo(() => {
    if (!reportData) return [];
    const q = searchQuery.trim().toLowerCase();
    if (!q) return reportData.history_groups;

    return reportData.history_groups.reduce((acc, group) => {
      const filteredItems = group.items.filter(item =>
        [item.machine_name, item.machine_code, String(item.batch_number),
         item.start_time, item.end_time, String(item.max_temp),
         item.nomor_order, item.artikel_kain, item.batch_kain]
          .some(field => field && String(field).toLowerCase().includes(q))
      );
      if (filteredItems.length > 0) acc.push({ ...group, items: filteredItems });
      return acc;
    }, []);
  }, [reportData, searchQuery]);

  const totalFiltered = useMemo(
    () => filteredHistoryGroups.reduce((s, g) => s + g.items.length, 0),
    [filteredHistoryGroups]
  );

  const handlePageChange = (groupName, delta) => {
    setGroupPages(prev => {
      const current = prev[groupName] || 1;
      return { ...prev, [groupName]: current + delta };
    });
  };

  return (
    <div className="p-2 sm:p-4 md:p-6 h-full overflow-y-auto bg-gray-50 relative">
      {/* Mobile Curved Hero Background */}
      <div className="md:hidden absolute top-0 left-0 right-0 h-48 bg-gradient-to-r from-blue-700 to-indigo-800 rounded-b-[2.5rem] z-0"></div>

      {/* Header & Date Filter */}
      <div className="relative z-10 flex flex-col sm:flex-row justify-between items-start sm:items-center mb-6 space-y-4 sm:space-y-0 mt-2 md:mt-0">
        <div>
          <h1 className="text-2xl font-bold text-white md:text-gray-800">Monthly Report</h1>
          <p className="text-sm text-blue-100 md:text-gray-500">
            {reportData ? `Periode: ${reportData.date_range}` : 'Memuat rentang waktu...'}
          </p>
        </div>
        <div className="flex flex-col sm:flex-row items-center space-y-2 sm:space-y-0 sm:space-x-2 bg-white px-4 py-2 rounded-xl shadow-sm border border-gray-100 w-full sm:w-auto">
          <div className="flex items-center w-full sm:w-auto">
            <Calendar className="text-gray-500 w-5 h-5 flex-shrink-0" />
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="border-none bg-transparent focus:ring-0 text-gray-700 font-medium cursor-pointer outline-none w-full sm:w-auto ml-2"
            />
          </div>
          <span className="text-gray-400 hidden sm:inline">-</span>
          <div className="flex items-center w-full sm:w-auto">
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="border-none bg-transparent focus:ring-0 text-gray-700 font-medium cursor-pointer outline-none w-full sm:w-auto ml-2 sm:ml-0"
            />
          </div>
        </div>
      </div>

      {loading ? (
        <div className="relative z-10 flex justify-center items-center h-64 text-gray-500">
          <Activity className="animate-spin mr-2" /> Memuat data laporan...
        </div>
      ) : error ? (
        <div className="relative z-10 bg-red-50 text-red-600 p-4 rounded-lg">{error}</div>
      ) : reportData ? (
        <div className="relative z-10 grid grid-cols-1 lg:grid-cols-3 gap-4 sm:gap-6">

          {/* ── LEFT COLUMN (2/3) ─────────────────────────────── */}
          <div className="lg:col-span-2 space-y-4 sm:space-y-6">

            {/* KPI Cards (Compact 3 Grid) */}
            <div className="grid grid-cols-3 gap-2 sm:gap-4">
              <div className="bg-white p-3 rounded-2xl shadow-[0_8px_30px_rgb(0,0,0,0.04)] border border-gray-50 flex flex-col items-center justify-center text-center">
                <div className="w-8 h-8 rounded-full bg-blue-50 text-blue-600 flex items-center justify-center mb-1.5"><Droplet size={14} /></div>
                <div className="text-xs sm:text-sm text-gray-500 mb-0.5">Total Uap</div>
                <div className="text-xl sm:text-2xl font-extrabold text-gray-800">{reportData.total_steam_usage.toLocaleString()} <span className="text-xs font-normal text-gray-400">kg</span></div>
              </div>
              <div className="bg-white p-3 rounded-2xl shadow-[0_8px_30px_rgb(0,0,0,0.04)] border border-gray-50 flex flex-col items-center justify-center text-center">
                <div className="w-8 h-8 rounded-full bg-purple-50 text-purple-600 flex items-center justify-center mb-1.5"><Clock size={14} /></div>
                <div className="text-xs sm:text-sm text-gray-500 mb-0.5">Total Proses</div>
                <div className="text-xl sm:text-2xl font-extrabold text-gray-800">{reportData.total_processes}</div>
              </div>
              <div className="bg-white p-3 rounded-2xl shadow-[0_8px_30px_rgb(0,0,0,0.04)] border border-gray-50 flex flex-col items-center justify-center text-center">
                <div className="w-8 h-8 rounded-full bg-green-50 text-green-600 flex items-center justify-center mb-1.5"><CheckCircle size={14} /></div>
                <div className="text-xs sm:text-sm text-gray-500 mb-0.5">Report Type</div>
                <div className="text-xl sm:text-2xl font-extrabold text-gray-800">Monthly</div>
              </div>
            </div>

            {/* Steam Traffic Chart */}
            <div className="bg-white p-4 sm:p-6 rounded-3xl shadow-[0_8px_30px_rgb(0,0,0,0.04)] border border-gray-50">
              <h2 className="text-lg font-bold text-gray-800 mb-6">Steam Traffic (Rata-rata 24 Jam)</h2>
              <div className="h-[250px] sm:h-[300px] w-full">
                <ResponsiveContainer width="100%" height="100%" minHeight={1} minWidth={1}>
                  <AreaChart data={reportData.steam_series} margin={{ top: 10, right: 0, left: -20, bottom: 0 }}>
                    <defs>
                      <linearGradient id="colorUsageReport" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%"  stopColor="#0ea5e9" stopOpacity={0.8} />
                        <stop offset="95%" stopColor="#0ea5e9" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f0f0f0" />
                    <XAxis dataKey="time" axisLine={false} tickLine={false} tick={{ fontSize: 12, fill: '#9ca3af' }} interval="preserveStartEnd" minTickGap={30} />
                    <YAxis yAxisId="left"  axisLine={false} tickLine={false} tick={{ fontSize: 12, fill: '#9ca3af' }} />
                    <YAxis yAxisId="right" orientation="right" axisLine={false} tickLine={false} tick={{ fontSize: 12, fill: '#9ca3af' }} />
                    <RechartsTooltip contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }} />
                    <Area yAxisId="left"  type="monotone" dataKey="usage"    stroke="#0ea5e9" strokeWidth={3} fillOpacity={1} fill="url(#colorUsageReport)" name="Usage (kg)" />
                    <Area yAxisId="right" type="monotone" dataKey="pressure" stroke="#8b5cf6" strokeWidth={2} fillOpacity={0} name="Pressure (bar)" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* History Process Table */}
            <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
              {/* Header + search */}
              <div className="p-4 sm:p-6 border-b border-gray-100 space-y-3">
                <div className="flex justify-between items-start">
                  <div>
                    <h2 className="text-lg font-bold text-gray-800">History Process</h2>
                    <p className="text-sm text-gray-500">Daftar proses yang teridentifikasi pada periode ini</p>
                  </div>
                  <span className="bg-blue-50 text-blue-700 px-3 py-1 rounded-full text-sm font-semibold whitespace-nowrap">
                    {totalFiltered} proses
                  </span>
                </div>
                {/* Search */}
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 w-4 h-4" />
                  <input
                    type="text"
                    placeholder="Cari mesin, batch, artikel, nomor order, suhu, jam..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-full pl-9 pr-4 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-300 bg-gray-50"
                  />
                </div>
              </div>

              <div className="overflow-x-auto w-full">
                <table className="min-w-full divide-y divide-gray-200 hidden md:table">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Mesin</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Batch</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Waktu</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Durasi</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Max Temp</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Data Kain</th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-gray-200">
                    {filteredHistoryGroups.length === 0 ? (
                      <tr>
                        <td colSpan="6" className="px-6 py-8 text-center text-sm text-gray-400">
                          {searchQuery ? `Tidak ada hasil untuk "${searchQuery}"` : 'Tidak ada proses di periode ini.'}
                        </td>
                      </tr>
                    ) : (
                      filteredHistoryGroups.map((group, gIdx) => {
                        const page = groupPages[group.group_name] || 1;
                        const startIndex = (page - 1) * 5;
                        const endIndex = startIndex + 5;
                        const paginatedItems = group.items.slice(startIndex, endIndex);
                        const totalPages = Math.ceil(group.items.length / 5);

                        return (
                          <React.Fragment key={gIdx}>
                            <tr className="bg-gray-50">
                              <td colSpan="6" className="px-4 py-2 border-t border-gray-200">
                                <div className="flex justify-between items-center w-full">
                                  <span className="text-xs font-bold text-gray-600 uppercase tracking-wider">
                                    {group.group_name} <span className="text-gray-400 ml-2">({group.items.length} proses)</span>
                                  </span>
                                  {totalPages > 1 && (
                                    <div className="flex items-center space-x-1">
                                      <button 
                                        onClick={() => handlePageChange(group.group_name, -1)} 
                                        disabled={page === 1}
                                        className={`p-1 rounded ${page === 1 ? 'text-gray-300' : 'text-gray-600 hover:bg-gray-200'}`}
                                      >
                                        <ChevronLeft size={16} />
                                      </button>
                                      <span className="text-xs text-gray-500 font-medium">{page} / {totalPages}</span>
                                      <button 
                                        onClick={() => handlePageChange(group.group_name, 1)} 
                                        disabled={page === totalPages}
                                        className={`p-1 rounded ${page === totalPages ? 'text-gray-300' : 'text-gray-600 hover:bg-gray-200'}`}
                                      >
                                        <ChevronRight size={16} />
                                      </button>
                                    </div>
                                  )}
                                </div>
                              </td>
                            </tr>
                            {paginatedItems.map((item) => (
                              <tr
                                key={item.id}
                                className="hover:bg-blue-50 cursor-pointer transition-colors"
                                onClick={() => openProcessAnalyticsModal(item.id)}
                              >
                                <td className="px-4 py-3 whitespace-nowrap">
                                  <div className="text-sm font-medium text-gray-900">{item.machine_name}</div>
                                  <div className="text-xs text-gray-400">{item.machine_code}</div>
                                </td>
                                <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-900">#{item.batch_number}</td>
                                <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-500">{item.start_time} – {item.end_time}</td>
                                <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-900">{item.duration} m</td>
                                <td className="px-4 py-3 whitespace-nowrap text-sm font-semibold text-gray-900">{item.max_temp} °C</td>
                                <td className="px-4 py-3 whitespace-nowrap min-w-[160px]">
                                  <div className="text-xs font-medium text-gray-700">{item.nomor_order}</div>
                                  <div className="text-xs text-gray-500">{item.artikel_kain}</div>
                                  <div className="text-xs text-gray-400">Batch: {item.batch_kain}</div>
                                </td>
                              </tr>
                            ))}
                          </React.Fragment>
                        );
                      })
                    )}
                  </tbody>
                </table>

                {/* Mobile Card View (History Process) */}
                <div className="md:hidden divide-y divide-gray-100">
                  {filteredHistoryGroups.length === 0 ? (
                    <div className="p-8 text-center text-sm text-gray-400">
                      {searchQuery ? `Tidak ada hasil untuk "${searchQuery}"` : 'Tidak ada proses di periode ini.'}
                    </div>
                  ) : (
                    filteredHistoryGroups.map((group, gIdx) => {
                      const page = groupPages[group.group_name] || 1;
                      const startIndex = (page - 1) * 5;
                      const endIndex = startIndex + 5;
                      const paginatedItems = group.items.slice(startIndex, endIndex);
                      const totalPages = Math.ceil(group.items.length / 5);

                      return (
                        <React.Fragment key={gIdx}>
                          <div className="bg-gray-50 px-4 py-2 flex justify-between items-center border-t border-gray-100">
                            <span className="text-xs font-bold text-gray-500 uppercase tracking-wider">
                              {group.group_name} ({group.items.length})
                            </span>
                            {totalPages > 1 && (
                              <div className="flex items-center space-x-1">
                                <button 
                                  onClick={() => handlePageChange(group.group_name, -1)} 
                                  disabled={page === 1}
                                  className={`p-1 rounded ${page === 1 ? 'text-gray-300' : 'text-gray-600'}`}
                                >
                                  <ChevronLeft size={14} />
                                </button>
                                <span className="text-xs text-gray-500">{page}/{totalPages}</span>
                                <button 
                                  onClick={() => handlePageChange(group.group_name, 1)} 
                                  disabled={page === totalPages}
                                  className={`p-1 rounded ${page === totalPages ? 'text-gray-300' : 'text-gray-600'}`}
                                >
                                  <ChevronRight size={14} />
                                </button>
                              </div>
                            )}
                          </div>
                          <div className="divide-y divide-gray-100">
                            {paginatedItems.map((item) => (
                              <div key={item.id} className="px-4 py-3 bg-white active:bg-gray-50 cursor-pointer flex items-center justify-between" onClick={() => openProcessAnalyticsModal(item.id)}>
                                <div className="flex items-center w-[75%]">
                                  <div className="flex-shrink-0 h-10 w-10 bg-indigo-50 rounded-full flex items-center justify-center text-indigo-600 font-bold text-xs">
                                    {item.machine_name.charAt(0)}
                                  </div>
                                  <div className="ml-3 min-w-0 flex-1">
                                    <div className="text-sm font-bold text-gray-800 leading-tight truncate">{item.machine_name} <span className="text-xs font-normal text-gray-400">({item.machine_code})</span></div>
                                    <div className="text-xs text-gray-500 mt-0.5 flex items-center space-x-1 truncate">
                                      <span className="font-medium text-indigo-600">B#{item.batch_number}</span>
                                      <span>•</span>
                                      <span>{item.start_time}</span>
                                    </div>
                                    <div className="text-[9px] text-gray-400 mt-0.5 truncate">{item.artikel_kain} ({item.nomor_order})</div>
                                  </div>
                                </div>
                                <div className="text-right flex-shrink-0 pl-2">
                                  <div className="text-sm font-bold text-gray-800">{item.max_temp}°C</div>
                                  <div className="text-xs text-gray-400 mt-0.5">{item.duration}m</div>
                                </div>
                              </div>
                            ))}
                          </div>
                        </React.Fragment>
                      );
                    })
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* ── RIGHT COLUMN (1/3) ────────────────────────────── */}
          <div className="space-y-6">

            {/* Process Heatmap */}
            <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden flex flex-col max-h-[800px]">
              <div className="p-4 border-b border-gray-100 flex-shrink-0 flex justify-between items-center">
                <div>
                  <h2 className="text-base font-bold text-gray-800">Jumlah Proses Per Mesin</h2>
                  <p className="text-xs text-gray-500">Intensitas proses pada periode ini</p>
                </div>
                <div className="bg-blue-50 text-blue-700 px-3 py-1 rounded-full text-sm font-semibold whitespace-nowrap">
                  {reportData.total_processes} proses
                </div>
              </div>
              <div className="p-4 overflow-y-auto flex-1">
                {reportData.heatmap_groups.length === 0 ? (
                  <div className="text-center text-gray-500 text-sm py-4">Tidak ada data proses.</div>
                ) : (
                  <div className="space-y-5">
                    {reportData.heatmap_groups.map((group, idx) => (
                      <div key={idx} className="relative pt-8 -mt-7">
                        <div className="flex items-center justify-between mb-2">
                          <h3 className="text-xs font-semibold text-gray-700">{group.group_name}</h3>
                          <span className="text-xs text-gray-400">{group.total_group_processes} total</span>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          {group.machines.map(m => {
                            let bgClass = 'bg-gray-100 border-gray-200', textClass = 'text-gray-400';
                            if (m.process_count > 0) {
                              if (m.process_count <= 2)      { bgClass = 'bg-blue-100 border-blue-200'; textClass = 'text-blue-700'; }
                              else if (m.process_count <= 4) { bgClass = 'bg-blue-300 border-blue-400'; textClass = 'text-blue-800'; }
                              else if (m.process_count <= 6) { bgClass = 'bg-blue-500 border-blue-600'; textClass = 'text-white'; }
                              else                           { bgClass = 'bg-blue-700 border-blue-800'; textClass = 'text-white'; }
                            }
                            return (
                              <div key={m.id} className="group relative cursor-pointer" onClick={() => openMachineProcessModal(m.id, m.name)}>
                                <div
                                  className={`w-8 h-8 sm:w-10 sm:h-10 rounded-md flex items-center justify-center text-xs font-bold border transition-transform hover:scale-110 ${bgClass} ${textClass} shadow-sm`}
                                >
                                  {m.process_count > 0 ? m.process_count : '-'}
                                </div>
                                <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-2 py-1 bg-gray-800 text-white text-xs rounded opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap z-50 pointer-events-none shadow-lg">
                                  {m.name}: {m.process_count} proses
                                  <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-gray-800" />
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

          </div>
        </div>
      ) : null}

      {/* Modal Process Analytics (Compact UI) */}
      {isProcessModalOpen && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-2 sm:p-4 bg-black bg-opacity-50 backdrop-blur-sm">
          <div className="bg-gray-50 rounded-xl shadow-2xl w-full max-w-[95%] lg:max-w-5xl overflow-hidden flex flex-col max-h-[95vh] text-sm">
            
            {/* Header Modal */}
            <div className="flex justify-between items-center p-3 sm:p-4 bg-white border-b border-gray-100 shrink-0">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-full bg-blue-50 text-blue-600 flex items-center justify-center font-bold">
                  {processAnalyticsDetail ? processAnalyticsDetail.machine_name.charAt(0) : <Activity className="animate-spin w-4 h-4" />}
                </div>
                <div>
                  <h3 className="text-base sm:text-lg font-bold text-gray-800 leading-tight">
                    {processAnalyticsDetail ? processAnalyticsDetail.machine_name : 'Memuat data...'}
                  </h3>
                  {processAnalyticsDetail && (
                    <p className="text-xs text-gray-500">Batch #{processAnalyticsDetail.batch_number}</p>
                  )}
                </div>
              </div>
              <button onClick={closeProcessModal} className="text-gray-400 hover:text-gray-600 transition-colors p-1 rounded-full hover:bg-gray-100">
                <X size={20} />
              </button>
            </div>

            {/* Modal Content */}
            <div className="p-4 sm:p-6 overflow-y-auto overflow-x-hidden flex-1 space-y-4 sm:space-y-6">
              {!processAnalyticsDetail ? (
                <div className="flex justify-center items-center h-64">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
                </div>
              ) : (
                <>
                  {/* Identity & KPI (Compact 2 columns on desktop) */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    
                    {/* Identity Panel */}
                    <div className="bg-white rounded-lg border border-gray-100 p-3 sm:p-4 flex flex-col justify-center shadow-sm">
                      <div className="grid grid-cols-2 gap-x-2 gap-y-2 text-xs sm:text-sm">
                        <div><span className="text-gray-400 block mb-0.5">Order/Warna</span><span className="font-semibold text-gray-700">{processAnalyticsDetail.identity.nomor_order} / {processAnalyticsDetail.identity.nomor_warna}</span></div>
                        <div><span className="text-gray-400 block mb-0.5">Artikel</span><span className="font-semibold text-gray-700 truncate block">{processAnalyticsDetail.identity.artikel_kain}</span></div>
                        <div><span className="text-gray-400 block mb-0.5">Batch Kain</span><span className="font-semibold text-gray-700">{processAnalyticsDetail.identity.batch}</span></div>
                        <div><span className="text-gray-400 block mb-0.5">Program</span><span className="font-semibold text-indigo-600 truncate block">{processAnalyticsDetail.identity.program}</span></div>
                        <div><span className="text-gray-400 block mb-0.5">Operator</span><span className="font-semibold text-gray-700">{processAnalyticsDetail.identity.operator}</span></div>
                        <div><span className="text-gray-400 block mb-0.5 text-xs sm:text-sm uppercase tracking-wider">Waktu Proses</span><span className="font-semibold text-gray-800">{formatBackendDate(processAnalyticsDetail.identity.heat_start_time)} - {formatBackendDate(processAnalyticsDetail.identity.end_time)}</span></div>
                      </div>
                    </div>

                    {/* KPI Panel */}
                    <div className="grid grid-cols-4 gap-2">
                      <div className="bg-white rounded-lg border border-gray-100 flex flex-col items-center justify-center p-2 text-center shadow-sm">
                        <span className="text-xs sm:text-sm text-gray-500 font-medium mb-0.5">Durasi Aktual</span>
                        <span className="text-base sm:text-lg font-bold text-gray-800">{processAnalyticsDetail.kpi.duration_effective || '-'}m</span>
                      </div>
                      <div className="bg-white rounded-lg border border-gray-100 flex flex-col items-center justify-center p-2 text-center shadow-sm">
                        <span className="text-xs sm:text-sm text-gray-500 font-medium mb-0.5">Durasi Ideal</span>
                        <span className="text-base sm:text-lg font-bold text-gray-800">{processAnalyticsDetail.timing.total_ideal || '-'}m</span>
                      </div>
                      <div className={`rounded-lg border flex flex-col items-center justify-center p-2 text-center shadow-sm ${processAnalyticsDetail.kpi.efficiency >= 80 ? 'bg-green-50 border-green-100 text-green-700' : processAnalyticsDetail.kpi.efficiency >= 60 ? 'bg-yellow-50 border-yellow-100 text-yellow-700' : 'bg-red-50 border-red-100 text-red-700'}`}>
                        <span className="text-xs sm:text-sm font-medium mb-0.5 opacity-80">Efisiensi</span>
                        <span className="text-lg sm:text-xl font-extrabold">{processAnalyticsDetail.kpi.efficiency ? processAnalyticsDetail.kpi.efficiency + '%' : '-'}</span>
                      </div>
                      <div className="bg-white rounded-lg border border-gray-100 flex flex-col items-center justify-center p-2 text-center shadow-sm">
                        <span className="text-xs sm:text-sm text-gray-500 font-medium mb-0.5">Loss Time</span>
                        <span className={`text-base sm:text-lg font-bold ${(processAnalyticsDetail.kpi.loss_time || 0) > 0 ? 'text-red-600' : 'text-gray-800'}`}>
                          {processAnalyticsDetail.kpi.loss_time ? `+${processAnalyticsDetail.kpi.loss_time}m` : '-'}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Phase Breakdown Progress Bar */}
                  {Object.keys(processAnalyticsDetail.phase_breakdown).length > 0 && (
                    <div className="bg-white rounded-lg border border-gray-100 p-3">
                      <div className="flex justify-between items-end mb-1">
                        <span className="text-sm font-bold text-gray-700">Phase Breakdown</span>
                        <div className="flex gap-3 text-xs">
                          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-red-400"></span>Heat ({processAnalyticsDetail.phase_breakdown.heat || 0}%)</span>
                          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-orange-400"></span>Hold ({processAnalyticsDetail.phase_breakdown.hold || 0}%)</span>
                          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-blue-400"></span>Cool ({processAnalyticsDetail.phase_breakdown.cooling || 0}%)</span>
                        </div>
                      </div>
                      <div className="w-full h-3 flex rounded-full overflow-hidden bg-gray-100">
                        <div style={{ width: `${processAnalyticsDetail.phase_breakdown.heat || 0}%` }} className="bg-red-400 h-full" />
                        <div style={{ width: `${processAnalyticsDetail.phase_breakdown.hold || 0}%` }} className="bg-orange-400 h-full" />
                        <div style={{ width: `${processAnalyticsDetail.phase_breakdown.cooling || 0}%` }} className="bg-blue-400 h-full" />
                      </div>
                    </div>
                  )}

                  {/* Chart and Timing details row */}
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                    {/* Chart */}
                    <div className="md:col-span-2 bg-white rounded-lg border border-gray-100 p-3">
                       <h4 className="text-sm font-bold text-gray-700 mb-2">Profil Suhu & Tekanan</h4>
                       <div className="h-[200px] w-full">
                         <ResponsiveContainer width="100%" height="100%" minHeight={1} minWidth={1}>
                           <LineChart data={processAnalyticsDetail.chart_data} margin={{ top: 5, right: 0, left: -25, bottom: 0 }}>
                             <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" vertical={false} />
                             <XAxis dataKey="time" tick={{ fontSize: 12, fill: '#9ca3af' }} axisLine={false} tickLine={false} interval="preserveStartEnd" minTickGap={20} />
                             <YAxis yAxisId="left" tick={{ fontSize: 12, fill: '#9ca3af' }} axisLine={false} tickLine={false} />
                             <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 12, fill: '#9ca3af' }} axisLine={false} tickLine={false} domain={[0, 5]} />
                             <RechartsTooltip contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)', fontSize: '12px' }} formatter={(value) => parseFloat(value).toFixed(2)} />
                             <Line yAxisId="left" type="monotone" dataKey="temp" stroke="#ef4444" strokeWidth={2} dot={false} name="Suhu (°C)" />
                             <Line yAxisId="right" type="monotone" dataKey="pressure" stroke="#8b5cf6" strokeWidth={2} dot={false} name="Steam (bar)" />
                           </LineChart>
                         </ResponsiveContainer>
                       </div>
                    </div>
                    
                    {/* Timing details */}
                    <div className="bg-white rounded-lg border border-gray-100 p-3">
                       <h4 className="text-sm font-bold text-gray-700 mb-2">Detail Fase</h4>
                       <div className="space-y-2">
                         <div className="flex justify-between items-center bg-gray-50 p-2 rounded text-sm">
                           <span className="text-gray-500">Heating</span>
                           <span className="font-medium text-gray-800">{processAnalyticsDetail.timing.heat_actual || 0}m <span className="text-gray-400 text-xs ml-1">(Ideal: {processAnalyticsDetail.timing.heat_ideal || 0}m)</span></span>
                         </div>
                         <div className="flex justify-between items-center bg-gray-50 p-2 rounded text-sm">
                           <span className="text-gray-500">Holding</span>
                           <span className="font-medium text-gray-800">{processAnalyticsDetail.timing.hold_actual || 0}m <span className="text-gray-400 text-xs ml-1">(Ideal: {processAnalyticsDetail.timing.keep_ideal || 0}m)</span></span>
                         </div>
                         <div className="flex justify-between items-center bg-gray-50 p-2 rounded text-sm">
                           <span className="text-gray-500">Cooling</span>
                           <span className="font-medium text-gray-800">{processAnalyticsDetail.timing.cool_actual || 0}m <span className="text-gray-400 text-xs ml-1">(Ideal: {processAnalyticsDetail.timing.cool_ideal || 0}m)</span></span>
                         </div>
                         <div className="pt-2 border-t border-gray-100 flex justify-between items-center text-sm">
                           <span className="text-gray-500">Max Temp</span>
                           <span className="font-bold text-red-500">
                             {processAnalyticsDetail.timing.peak_temp || '-'}°C 
                             <span className="text-gray-400 text-xs ml-1 font-normal">(Ideal: {processAnalyticsDetail.timing.max_temp_prg || '-'}°C)</span>
                           </span>
                         </div>
                       </div>
                    </div>
                  </div>

                  {/* Masalah / Catatan */}
                  {processAnalyticsDetail.identity.masalah && (
                    <div className="bg-red-50 rounded-lg border border-red-100 p-3">
                      <h4 className="text-sm font-bold text-red-800 mb-1">Catatan / Masalah</h4>
                      <p className="text-sm text-red-600">{processAnalyticsDetail.identity.masalah}</p>
                    </div>
                  )}
                  {processAnalyticsDetail.identity.keterangan && (
                    <div className="bg-blue-50 rounded-lg border border-blue-100 p-3">
                      <h4 className="text-sm font-bold text-blue-800 mb-1">Keterangan</h4>
                      <p className="text-sm text-blue-600">{processAnalyticsDetail.identity.keterangan}</p>
                    </div>
                  )}

                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Modal Machine Process History */}
      {isMachineModalOpen && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black bg-opacity-50 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-3xl overflow-hidden flex flex-col max-h-[90vh]">
            {/* Header Modal */}
            <div className="flex justify-between items-center p-4 sm:p-6 border-b border-gray-100 bg-gray-50 shrink-0">
              <div>
                <h3 className="text-lg sm:text-xl font-bold text-gray-800 leading-tight">
                  Riwayat Proses Harian
                </h3>
                <p className="text-sm text-gray-500 font-medium">{selectedMachineName}</p>
              </div>
              <button onClick={closeMachineModal} className="text-gray-400 hover:text-gray-600 transition-colors p-2 rounded-full hover:bg-gray-200 bg-white shadow-sm">
                <X size={20} />
              </button>
            </div>

            {/* Modal Content */}
            <div className="p-4 sm:p-6 overflow-y-auto flex-1 bg-white">
              {!machineProcessData ? (
                <div className="flex justify-center items-center h-64">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
                </div>
              ) : (
                <div className="space-y-6">
                  {/* KPI Cards */}
                  <div className="grid grid-cols-3 gap-4">
                    <div className="bg-blue-50 border border-blue-100 p-4 rounded-xl flex flex-col items-center justify-center text-center">
                      <span className="text-sm text-blue-600 font-medium mb-1">Rata-rata / Hari</span>
                      <span className="text-2xl font-extrabold text-blue-800">{machineProcessData.avg}</span>
                    </div>
                    <div className="bg-green-50 border border-green-100 p-4 rounded-xl flex flex-col items-center justify-center text-center">
                      <span className="text-sm text-green-600 font-medium mb-1">Maksimal</span>
                      <span className="text-2xl font-extrabold text-green-800">{machineProcessData.max}</span>
                    </div>
                    <div className="bg-orange-50 border border-orange-100 p-4 rounded-xl flex flex-col items-center justify-center text-center">
                      <span className="text-sm text-orange-600 font-medium mb-1">Minimal</span>
                      <span className="text-2xl font-extrabold text-orange-800">{machineProcessData.min}</span>
                    </div>
                  </div>

                  {/* Chart */}
                  <div className="border border-gray-100 rounded-xl p-4 shadow-sm bg-gray-50">
                    <h4 className="text-sm font-bold text-gray-700 mb-4">Grafik Jumlah Proses ({startDate} - {endDate})</h4>
                    <div className="h-[300px] w-full">
                      <ResponsiveContainer width="100%" height="100%" minHeight={1} minWidth={1}>
                        <BarChart data={machineProcessData.chart_data} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e5e7eb" />
                          <XAxis dataKey="date" axisLine={false} tickLine={false} tick={{ fontSize: 12, fill: '#6b7280' }} minTickGap={20} />
                          <YAxis allowDecimals={false} axisLine={false} tickLine={false} tick={{ fontSize: 12, fill: '#6b7280' }} />
                          <RechartsTooltip content={<CustomMachineTooltip />} cursor={{ fill: 'rgba(0,0,0,0.04)' }} />
                          <Bar dataKey="count" fill="#3b82f6" radius={[4, 4, 0, 0]} maxBarSize={40} />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
