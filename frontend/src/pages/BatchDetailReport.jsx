import React, { useState, useEffect } from 'react';
import { useToast } from '../context/ToastContext';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import api, { BACKEND_BASE_URL } from '../lib/api';
import { ArrowLeft, Clock, Activity, Thermometer, Box, Hash, User, RefreshCw, AlertCircle, ExternalLink, Save, Unlink, Printer } from 'lucide-react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, Legend, ResponsiveContainer, ReferenceLine
} from 'recharts';

const BatchDetailReport = () => {
  const toast = useToast();
  const { machine_code, batch_number } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [notes, setNotes] = useState('');
  const [actionLoading, setActionLoading] = useState(false);

  const handleBack = () => {
    if (location.state?.from) {
      navigate(location.state.from);
    } else {
      navigate('/anomalies');
    }
  };

  useEffect(() => {
    let isCancelled = false;
    const fetchBatchData = async () => {
      setLoading(true);
      setError(null);
      setData(null);
      try {
        const res = await api.get(`/batch-detail/${machine_code}/${batch_number}/`);
        if (isCancelled) return;
        if (res.data.status === 'success') {
          setData(res.data.data);
          if (res.data.data.identity?.keterangan) {
            setNotes(res.data.data.identity.keterangan);
          } else {
            setNotes('');
          }
        } else {
          setError(res.data.message || 'Gagal memuat data batch.');
        }
      } catch (err) {
        if (isCancelled) return;
        console.error(err);
        const errMsg = err.response?.data?.message || (err.response?.status === 403 ? 'Anda tidak memiliki izin (history_report) untuk melihat laporan batch ini.' : 'Terjadi kesalahan saat memuat data laporan.');
        setError(errMsg);
      } finally {
        if (!isCancelled) {
          setLoading(false);
        }
      }
    };
    fetchBatchData();

    return () => {
      isCancelled = true;
    };
  }, [machine_code, batch_number]);

  if (loading) {
    return (
      <div className="flex h-full w-full items-center justify-center bg-gray-50">
        <div className="flex flex-col items-center">
          <RefreshCw className="w-10 h-10 text-indigo-500 animate-spin mb-4" />
          <p className="text-gray-500 font-medium">Memuat Analisis Fisika & Data Sensor...</p>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="flex h-full w-full items-center justify-center bg-gray-50 p-6">
        <div className="bg-white rounded-xl shadow-sm border border-red-100 p-8 max-w-md text-center">
          <AlertCircle className="w-12 h-12 text-red-500 mx-auto mb-4" />
          <h2 className="text-xl font-bold text-gray-900 mb-2">Data Tidak Ditemukan</h2>
          <p className="text-gray-500 text-sm mb-6">{error}</p>
          <button 
            onClick={handleBack}
            className="px-4 py-2 bg-gray-100 text-gray-800 rounded-md hover:bg-gray-200 font-medium transition-colors"
          >
            Kembali
          </button>
        </div>
      </div>
    );
  }

  const { identity, analysis, chart_data } = data;

  const handleSaveNotes = async () => {
    setActionLoading(true);
    try {
      await api.post(`/batch-detail/${machine_code}/${batch_number}/action/`, { action: 'SAVE_NOTES', notes });
      toast.success('Catatan batch berhasil disimpan');
    } catch (err) {
      toast.error('Gagal menyimpan catatan batch');
    } finally {
      setActionLoading(false);
    }
  };

  const handleUnlink = async () => {
    if (!window.confirm('Yakin ingin melakukan UNLINK identitas dari batch ini?')) return;
    setActionLoading(true);
    try {
      await api.post(`/batch-detail/${machine_code}/${batch_number}/action/`, { action: 'UNLINK', notes });
      toast.success('Identitas berhasil di-unlink dari batch');
      // Refresh data
      window.location.reload();
    } catch (err) {
      toast.error('Gagal melakukan unlink identitas');
    } finally {
      setActionLoading(false);
    }
  };
  
  // Custom tooltip for chart showing hover details
  const CustomTooltip = ({ active, payload, label }) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-white p-3 border border-gray-200 shadow-lg rounded-lg text-xs font-mono min-w-[200px]">
          <div className="font-bold border-b pb-1 mb-2 text-gray-700">Jam: {label}</div>
          {payload.map((entry, index) => {
            const isSteam = entry.dataKey === 'steam';
            const unit = isSteam ? 'Bar' : '°C';
            return (
              <div key={index} className="flex justify-between items-center py-0.5" style={{ color: entry.color }}>
                <span className="font-semibold">{entry.name}</span>
                <span>{entry.value !== null ? entry.value : '-'} {unit}</span>
              </div>
            );
          })}
          {payload[0]?.payload?.state && (
            <div className="mt-2 pt-2 border-t border-gray-100 flex justify-between text-gray-600">
              <span>Status:</span>
              <span className="font-bold">{payload[0].payload.state}</span>
            </div>
          )}
          {payload[0]?.payload?.gradient !== null && (
            <div className="flex justify-between text-gray-600">
              <span>Gradient:</span>
              <span>{payload[0].payload.gradient > 0 ? '+' : ''}{payload[0].payload.gradient} °C/m</span>
            </div>
          )}
          {payload[0]?.payload?.efficiency !== null && (
            <div className="flex justify-between text-gray-600 font-bold">
              <span>Eff:</span>
              <span className={payload[0].payload.efficiency > 0.6 ? 'text-green-600' : 'text-amber-600'}>
                {Math.round(payload[0].payload.efficiency * 100)}%
              </span>
            </div>
          )}
        </div>
      );
    }
    return null;
  };

  return (
    <div className="p-4 sm:p-6 bg-gray-50 min-h-full pb-20 md:pb-6 print-area">
      {/* Header */}
      <div className="flex items-center mb-6">
        <button 
          onClick={handleBack}
          className="mr-4 p-2 rounded-full hover:bg-gray-200 transition-colors text-gray-600 no-print"
        >
          <ArrowLeft size={20} />
        </button>
        <div className="flex-1">
          <h1 className="text-xl sm:text-2xl font-bold text-gray-900 tracking-tight flex items-center">
            {data.machine_name} <span className="mx-2 text-gray-300">|</span> Batch #{data.batch_number}
          </h1>
          <div className="text-sm text-gray-500 mt-1 flex items-center space-x-2">
            <span>{new Date(data.start_time).toLocaleString('id-ID')}</span>
            <span>&rarr;</span>
            <span>{data.end_time ? new Date(data.end_time).toLocaleString('id-ID') : 'Masih Berjalan'}</span>
            {!data.is_valid && (
              <span className="ml-2 px-2 py-0.5 bg-red-100 text-red-800 text-[10px] font-bold rounded uppercase">Invalid</span>
            )}
          </div>
        </div>
        <div className="no-print flex items-center gap-2">
          <a
            href={`/history/report/${data.process_id || 0}?machine=${encodeURIComponent(machine_code || '')}&batch=${encodeURIComponent(batch_number || '')}`}
            target="_blank"
            rel="noreferrer"
            className="flex items-center px-3 py-2 bg-indigo-600 text-white text-sm font-medium rounded-md hover:bg-indigo-700 shadow-xs transition-colors"
          >
            <ExternalLink className="w-4 h-4 mr-1.5" /> Buka SCADA Report
          </a>
          <button
            onClick={() => window.print()}
            className="flex items-center px-3 py-2 bg-gray-800 text-white text-sm font-medium rounded-md hover:bg-gray-900 shadow-xs transition-colors"
          >
            <Printer className="w-4 h-4 mr-1.5" /> Cetak A4
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 print:grid-cols-3">
        
        {/* Left Column: Identity & Metrik */}
        <div className="lg:col-span-1 space-y-6">
          
          {/* Identity Card */}
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
            <div className="bg-indigo-50 px-4 py-3 border-b border-indigo-100">
              <h3 className="font-semibold text-indigo-900 flex items-center text-sm">
                <Box className="w-4 h-4 mr-2" /> Identitas Kain & Program
              </h3>
            </div>
            <div className="p-4">
              {identity ? (
                <div className="space-y-4">
                  <div>
                    <p className="text-xs text-gray-500 mb-1 font-medium">Program Master</p>
                    <div className="text-sm font-bold text-gray-900 flex justify-between items-end border-b border-gray-100 pb-2">
                      <span>{identity.program_name}</span>
                      <span className="text-xs font-normal bg-indigo-100 text-indigo-800 px-2 py-0.5 rounded">Target: {identity.target_suhu_max}°C</span>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <p className="text-xs text-gray-500 mb-1 flex items-center"><Hash className="w-3 h-3 mr-1"/> No. Order</p>
                      <p className="text-sm font-semibold text-gray-800">{identity.nomor_order || '-'}</p>
                    </div>
                    <div>
                      <p className="text-xs text-gray-500 mb-1 flex items-center"><User className="w-3 h-3 mr-1"/> Operator</p>
                      <p className="text-sm font-semibold text-gray-800">{identity.operator || '-'}</p>
                    </div>
                    <div className="col-span-2">
                      <p className="text-xs text-gray-500 mb-1">Artikel Kain</p>
                      <p className="text-sm font-semibold text-gray-800">{identity.artikel_kain || '-'}</p>
                    </div>
                    <div className="col-span-2 text-xs">
                      <div className="flex justify-between py-1 border-t border-gray-50 mt-1">
                        <span className="text-gray-500">Isi / Tube</span>
                        <span className="font-medium">{identity.isi_per_tube || '-'} kg</span>
                      </div>
                      <div className="flex justify-between py-1 border-t border-gray-50">
                        <span className="text-gray-500">Proses</span>
                        <span className="font-medium">{identity.jenis_proses || '-'}</span>
                      </div>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="text-center py-6 text-gray-400 text-sm">
                  Belum ada data identitas (Unlinked/Orphan)
                </div>
              )}
            </div>
            
            {/* Actions for Identity */}
            {identity && (
              <div className="px-4 py-3 bg-gray-50 border-t border-gray-200 no-print">
                <div className="mb-3">
                  <label className="block text-xs font-medium text-gray-700 mb-1">Catatan (Notes)</label>
                  <textarea 
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    className="w-full border border-gray-300 rounded-md text-sm p-2 focus:ring-indigo-500 focus:border-indigo-500"
                    rows="2"
                    placeholder="Tulis catatan jika ada keanehan..."
                  ></textarea>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button 
                    onClick={handleSaveNotes}
                    disabled={actionLoading}
                    className="flex-1 bg-indigo-600 text-white text-xs font-medium px-3 py-1.5 rounded-md hover:bg-indigo-700 flex items-center justify-center"
                  >
                    <Save className="w-3 h-3 mr-1" /> Simpan
                  </button>
                  <button 
                    onClick={handleUnlink}
                    disabled={actionLoading}
                    className="flex-1 bg-red-600 text-white text-xs font-medium px-3 py-1.5 rounded-md hover:bg-red-700 flex items-center justify-center"
                  >
                    <Unlink className="w-3 h-3 mr-1" /> Unlink
                  </button>
                  <a 
                    href={`${BACKEND_BASE_URL}/admin/monitoring/dyeingidentity/${identity.id}/change/`}
                    target="_blank" rel="noopener noreferrer"
                    className="flex-1 bg-gray-600 text-white text-xs font-medium px-3 py-1.5 rounded-md hover:bg-gray-700 flex items-center justify-center"
                  >
                    <ExternalLink className="w-3 h-3 mr-1" /> Admin Form
                  </a>
                </div>
              </div>
            )}
          </div>

          {/* Physics Analysis Card */}
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
            <div className="bg-teal-50 px-4 py-3 border-b border-teal-100">
              <h3 className="font-semibold text-teal-900 flex items-center text-sm">
                <Activity className="w-4 h-4 mr-2" /> Analisis Fisika (Performa)
              </h3>
            </div>
            <div className="p-4 space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center text-sm text-gray-600">
                  <Thermometer className="w-4 h-4 mr-2 text-red-500" /> Suhu Puncak (Peak)
                </div>
                <div className="font-bold text-gray-900">
                  {analysis?.peak_temp || '-'} <span className="text-xs text-gray-500 font-normal">°C</span>
                </div>
              </div>
              
              <div className="flex items-center justify-between">
                <div className="flex items-center text-sm text-gray-600">
                  <Activity className="w-4 h-4 mr-2 text-green-500" /> Heating Efficiency
                </div>
                <div className={`font-bold ${analysis?.heating_efficiency >= 80 ? 'text-green-600' : analysis?.heating_efficiency >= 60 ? 'text-amber-600' : 'text-red-600'}`}>
                  {analysis?.heating_efficiency || '-'} <span className="text-xs font-normal">%</span>
                </div>
              </div>

              <div className="flex items-center justify-between">
                <div className="flex items-center text-sm text-gray-600">
                  <Clock className="w-4 h-4 mr-2 text-blue-500" /> Avg Steam Temp
                </div>
                <div className="font-bold text-gray-900">
                  {analysis?.avg_steam_temp || '-'} <span className="text-xs text-gray-500 font-normal">°C</span>
                </div>
              </div>

              <div className="pt-3 border-t border-gray-100">
                <p className="text-xs text-gray-500 mb-2 font-medium">Durasi Aktual vs Ideal (Target)</p>
                
                <div className="space-y-3">
                  {/* Heating */}
                  <div>
                    <div className="flex justify-between text-xs mb-1">
                      <span className="text-red-600 font-medium">Heating</span>
                      <span className="font-bold text-gray-700">
                        {data.actual_heating || 0}m <span className="text-gray-400 font-normal">/ {identity?.target_heating || '?'}m</span>
                      </span>
                    </div>
                    <div className="w-full bg-gray-100 rounded-full h-1.5">
                      <div className={`h-1.5 rounded-full ${data.actual_heating > (identity?.target_heating || 0) ? 'bg-red-500' : 'bg-green-500'}`} 
                           style={{ width: `${Math.min(100, ((data.actual_heating || 0) / (identity?.target_heating || 1)) * 100)}%` }}></div>
                    </div>
                  </div>

                  {/* Keeping */}
                  <div>
                    <div className="flex justify-between text-xs mb-1">
                      <span className="text-amber-500 font-medium">Keeping / Steady</span>
                      <span className="font-bold text-gray-700">
                        {data.actual_keeping || 0}m <span className="text-gray-400 font-normal">/ {identity?.target_keeping || '?'}m</span>
                      </span>
                    </div>
                    <div className="w-full bg-gray-100 rounded-full h-1.5">
                      <div className={`h-1.5 rounded-full ${Math.abs((data.actual_keeping || 0) - (identity?.target_keeping || 0)) > 5 ? 'bg-amber-500' : 'bg-green-500'}`} 
                           style={{ width: `${Math.min(100, ((data.actual_keeping || 0) / (identity?.target_keeping || 1)) * 100)}%` }}></div>
                    </div>
                  </div>

                  {/* Cooling */}
                  <div>
                    <div className="flex justify-between text-xs mb-1">
                      <span className="text-blue-500 font-medium">Cooling</span>
                      <span className="font-bold text-gray-700">
                        {data.actual_cooling || 0}m <span className="text-gray-400 font-normal">/ {identity?.target_cooling || '?'}m</span>
                      </span>
                    </div>
                    <div className="w-full bg-gray-100 rounded-full h-1.5">
                      <div className={`h-1.5 rounded-full ${data.actual_cooling > (identity?.target_cooling || 0) ? 'bg-blue-500' : 'bg-green-500'}`} 
                           style={{ width: `${Math.min(100, ((data.actual_cooling || 0) / (identity?.target_cooling || 1)) * 100)}%` }}></div>
                    </div>
                  </div>
                </div>
              </div>

            </div>
          </div>
        </div>

        {/* Right Column: Interactive Chart */}
        <div className="lg:col-span-2">
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-4 sm:p-6 h-[500px] flex flex-col relative">
            <div className="flex justify-between items-center mb-6">
              <div>
                <h2 className="text-lg font-bold text-gray-900">Kurva Suhu Proses</h2>
                <p className="text-xs text-gray-500 mt-1">Arahkan kursor (hover) pada grafik untuk melihat detail log per menit.</p>
              </div>
            </div>
            
            <div className="flex-1 w-full min-h-0 relative">
              <ResponsiveContainer width="100%" height="100%" minHeight={1} minWidth={1}>
                <LineChart
                  data={chart_data}
                  margin={{ top: 10, right: 10, left: -20, bottom: 0 }}
                >
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f3f4f6" />
                  <XAxis 
                    dataKey="time" 
                    tick={{ fontSize: 11, fill: '#6b7280' }} 
                    tickMargin={10} 
                    minTickGap={30}
                    axisLine={false} 
                    tickLine={false} 
                  />
                  <YAxis 
                    yAxisId="left"
                    domain={[0, 150]} 
                    tick={{ fontSize: 11, fill: '#6b7280' }} 
                    axisLine={false} 
                    tickLine={false} 
                  />
                  <YAxis 
                    yAxisId="right"
                    orientation="right"
                    domain={[0, 'auto']} 
                    tick={{ fontSize: 11, fill: '#6b7280' }} 
                    axisLine={false} 
                    tickLine={false}
                    tickFormatter={(val) => `${val} Bar`}
                  />
                  <RechartsTooltip content={<CustomTooltip />} />
                  <Legend wrapperStyle={{ fontSize: '12px', paddingTop: '20px' }} />
                  
                  {identity?.target_suhu_max && (
                    <ReferenceLine yAxisId="left" y={identity.target_suhu_max} stroke="#818cf8" strokeDasharray="3 3" label={{ position: 'insideTopLeft', value: 'Target Suhu', fill: '#818cf8', fontSize: 10 }} />
                  )}

                  <Line 
                    yAxisId="left"
                    type="monotone" 
                    dataKey="temp" 
                    name="Suhu Mesin" 
                    stroke="#ef4444" 
                    strokeWidth={2.5}
                    dot={false} 
                    activeDot={{ r: 6, fill: '#ef4444', stroke: '#fff', strokeWidth: 2 }}
                    isAnimationActive={true}
                  />
                  <Line 
                    yAxisId="right"
                    type="monotone" 
                    dataKey="steam" 
                    name="Tekanan Steam" 
                    stroke="#f59e0b" 
                    strokeWidth={1.5}
                    dot={false}
                    opacity={0.6}
                  />
                  <Line 
                    yAxisId="left"
                    type="monotone" 
                    dataKey="hto" 
                    name="Suhu Oil (HTO)" 
                    stroke="#10b981" 
                    strokeWidth={1.5}
                    dot={false}
                    opacity={0.6}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>

      </div>
    </div>
  );
};

export default BatchDetailReport;
