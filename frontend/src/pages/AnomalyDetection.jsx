import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../lib/api';
import { useToast } from '../context/ToastContext';
import { AlertTriangle, CheckCircle, Info, X, RefreshCw, Download, Printer, Filter } from 'lucide-react';
import * as XLSX from 'xlsx';
import { DataTable } from './anomalies/data-table';
import { columns } from './anomalies/columns';

const AnomalyDetection = () => {
  const navigate = useNavigate();
  const toast = useToast();
  const [anomalies, setAnomalies] = useState([]);
  const [loading, setLoading] = useState(true);
  const tableRef = useRef(null);
  
  // Backend Filters
  const [filterDate, setFilterDate] = useState(() => sessionStorage.getItem('anomalyFilterDate') || '');
  const [filterStatus, setFilterStatus] = useState(() => sessionStorage.getItem('anomalyFilterStatus') || 'unresolved'); // 'unresolved', 'resolved', 'all'
  
  const [visitedRowId, setVisitedRowId] = useState(null);
  
  // Modal state
  const [selectedAnomaly, setSelectedAnomaly] = useState(null);
  const [actionNotes, setActionNotes] = useState('');
  const [actionType, setActionType] = useState('');
  const [resolving, setResolving] = useState(false);

  const fetchAnomalies = async () => {
    setLoading(true);
    try {
      let isResolvedParam = '';
      if (filterStatus === 'unresolved') isResolvedParam = 'false';
      else if (filterStatus === 'resolved') isResolvedParam = 'true';
      
      const params = new URLSearchParams();
      if (isResolvedParam !== '') params.append('is_resolved', isResolvedParam);
      if (filterDate) params.append('date', filterDate);
      params.append('_t', new Date().getTime());

      const res = await api.get(`/anomalies/?${params.toString()}`);
      if (res.data.status === 'success') {
        setAnomalies(res.data.data);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  // Sync backend filters to session storage & fetch
  useEffect(() => {
    sessionStorage.setItem('anomalyFilterDate', filterDate);
    sessionStorage.setItem('anomalyFilterStatus', filterStatus);
    fetchAnomalies();
  }, [filterDate, filterStatus]);

  useEffect(() => {
    const id = sessionStorage.getItem('lastVisitedAnomaly');
    if (id) {
      setVisitedRowId(Number(id));
      sessionStorage.removeItem('lastVisitedAnomaly');
    }
  }, []);

  const handleResolve = async () => {
    if (!selectedAnomaly || !actionType || resolving) return;
    setResolving(true);
    try {
      const res = await api.post(`/anomalies/${selectedAnomaly.id}/resolve/`, {
        action: actionType,
        notes: actionNotes
      });
      if (res.data.status === 'success') {
        setSelectedAnomaly(null);
        setActionNotes('');
        setActionType('');
        fetchAnomalies();
      }
    } catch (err) {
      console.error(err);
      toast.error('Gagal menyelesaikan anomali: ' + (err.response?.data?.message || err.message));
    } finally {
      setResolving(false);
    }
  };

  const openActionModal = useCallback((anomaly, action) => {
    setSelectedAnomaly(anomaly);
    setActionType(action);
    setActionNotes('');
  }, []);

  const handleRowClick = useCallback((a) => {
    if (!a.machine_code || a.machine_code === '-' || !a.batch_number || a.batch_number === '-') {
      toast.warning('Batch ini belum terhubung dengan record proses mesin.');
      return;
    }
    sessionStorage.setItem('lastVisitedAnomaly', a.id.toString());
    navigate(`/history/report/${a.process_record_id || 0}?machine=${encodeURIComponent(a.machine_code || '')}&batch=${encodeURIComponent(a.batch_number || '')}`, {
      state: { from: '/anomalies' }
    });
  }, [navigate]);

  const tableMeta = useMemo(() => ({
    handleRowClick,
    openActionModal,
  }), [handleRowClick, openActionModal]);

  // Export Excel
  const handleExportExcel = () => {
    const wb = XLSX.utils.book_new();
    const wsData = [
      ['Waktu Start', 'Batch #ID', 'Program', 'Artikel', 'PO', 'Batch Kain', 'Proses', 'Tipe Analisis', 'Max Temp', 'Max(Idl)', 'Heat', 'Heat(Idl)', 'Hold', 'Hold(Idl)', 'Cool', 'Cool(Idl)', 'Status']
    ];
    
    // Export the currently filtered data from the table instance
    const filteredRows = tableRef.current?.getFilteredRowModel().rows;
    const dataToExport = filteredRows ? filteredRows.map(row => row.original) : anomalies;

    if (filteredRows && filteredRows.length === 0) {
      toast.info('Tidak ada data yang sesuai filter untuk diekspor.');
      return;
    }

    dataToExport.forEach(a => {
      const types = (a.anomaly_types || []).join(', ');
      wsData.push([
        a.batch_start ? new Date(a.batch_start).toLocaleString('id-ID') : '-',
        `${a.machine_code} B#${a.batch_number}`,
        a.program_name,
        a.artikel_kain,
        a.nomor_order,
        a.batch_kain,
        a.jenis_proses,
        types,
        a.details?.actuals?.suhu ?? '-',
        a.details?.ideals?.suhu ?? '-',
        a.details?.actuals?.heat ?? '-',
        a.details?.ideals?.heat ?? '-',
        a.details?.actuals?.keep ?? '-',
        a.details?.ideals?.keep ?? '-',
        a.details?.actuals?.cool ?? '-',
        a.details?.ideals?.cool ?? '-',
        a.is_resolved ? 'Selesai' : 'Belum Selesai'
      ]);
    });
    
    const ws = XLSX.utils.aoa_to_sheet(wsData);
    XLSX.utils.book_append_sheet(wb, ws, "Anomali");
    
    const dateStr = filterDate || new Date().toLocaleDateString('id-ID').replace(new RegExp('/', 'g'), '-');
    const statusStr = filterStatus === 'unresolved' ? 'BelumSelesai' : (filterStatus === 'resolved' ? 'Selesai' : 'Semua');
    XLSX.writeFile(wb, `Laporan_Anomali_${statusStr}_${dateStr}.xlsx`);
  };

  // Print A4
  const handlePrint = () => {
    document.documentElement.classList.add('printing-performance');
    const cleanup = () => {
      document.documentElement.classList.remove('printing-performance');
    };
    window.addEventListener('afterprint', cleanup, { once: true });
    
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        window.print();
      });
    });
  };

  return (
    <div id="anomaly-main-container" className="h-full bg-slate-50 flex flex-col relative overflow-hidden pb-3 snapshot-print-flow">
      {/* Compact Filters Header (No-Print) */}
      <div className="bg-white border-b border-gray-200 px-4 py-2 flex-shrink-0 z-10 shadow-sm no-print">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex items-center text-sm font-semibold text-gray-700 mr-2 bg-indigo-50 px-2 py-1 rounded text-indigo-700">
              <Filter className="w-4 h-4 mr-1" /> Filter Data
            </div>
            
            {/* Status (Backend) */}
            <select
              value={filterStatus}
              onChange={(e) => setFilterStatus(e.target.value)}
              className="text-xs border-gray-300 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 py-1 pl-2 pr-6"
            >
              <option value="unresolved">Belum Selesai</option>
              <option value="resolved">Riwayat Selesai</option>
              <option value="all">Semua Status</option>
            </select>

            {/* Tanggal (Backend) */}
            <input
              type="date"
              value={filterDate}
              onChange={(e) => setFilterDate(e.target.value)}
              className="text-xs border-gray-300 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 py-1 px-2"
              title="Filter Tanggal (Semua jika kosong)"
            />
          </div>
          
          <div className="flex items-center gap-2">
            <button
              onClick={fetchAnomalies}
              className="p-1.5 bg-white border border-gray-200 text-gray-600 rounded hover:bg-gray-50 transition-colors"
              title="Refresh Data"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </button>
            <div className="w-px h-6 bg-gray-200 mx-1"></div>
            <button
              onClick={handleExportExcel}
              className="flex items-center px-3 py-1.5 text-xs font-medium text-emerald-700 bg-emerald-50 border border-emerald-200 rounded hover:bg-emerald-100 transition-colors"
            >
              <Download className="w-3.5 h-3.5 mr-1" /> Excel
            </button>
            <button
              onClick={handlePrint}
              className="flex items-center px-3 py-1.5 text-xs font-medium text-gray-700 bg-white border border-gray-300 rounded hover:bg-gray-50 transition-colors"
            >
              <Printer className="w-3.5 h-3.5 mr-1" /> Print
            </button>
          </div>
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 overflow-hidden px-4 pt-4 pb-2 relative snapshot-print-flow">
        {/* Print-Only Header */}
        <div className="hidden print:block perf-print-header mb-4">
          <h1 className="text-xl font-bold text-gray-900">Laporan Anomaly Detection</h1>
          <div className="text-xs text-gray-600 mt-2 flex flex-wrap gap-4">
            <p><strong>Tanggal:</strong> {filterDate || 'Semua Waktu'}</p>
            <p><strong>Status:</strong> {filterStatus === 'unresolved' ? 'Belum Diselesaikan' : filterStatus === 'resolved' ? 'Riwayat Selesai' : 'Semua Status'}</p>
          </div>
        </div>
        
        <DataTable 
          tableRef={tableRef}
          columns={columns} 
          data={anomalies} 
          loading={loading}
          visitedRowId={visitedRowId}
          meta={tableMeta}
        />
      </div>

      {/* Action Modal */}
      {selectedAnomaly && (
        <div className="fixed inset-0 bg-gray-900/60 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-xl shadow-2xl max-w-sm w-full overflow-hidden flex flex-col">
            <div className="px-5 py-3 border-b border-gray-100 flex justify-between items-center bg-gray-50">
              <h3 className="text-sm font-bold text-gray-900 flex items-center">
                {actionType === 'SOLVE' && <CheckCircle className="w-4 h-4 text-emerald-500 mr-2" />}
                {actionType === 'INVALIDATE' && <Info className="w-4 h-4 text-amber-500 mr-2" />}
                {actionType === 'UNLINK' && <AlertTriangle className="w-4 h-4 text-rose-500 mr-2" />}
                Konfirmasi Tindakan
              </h3>
              <button onClick={() => !resolving && setSelectedAnomaly(null)} className="text-gray-400 hover:text-gray-600">
                <X className="w-4 h-4" />
              </button>
            </div>
            
            <div className="p-5">
              <p className="text-xs text-gray-600 mb-4">
                Anomali pada mesin <strong className="text-gray-900">{selectedAnomaly.machine_code} - B#{selectedAnomaly.batch_number}</strong>
                {actionType === 'SOLVE' && ' akan ditandai selesai.'}
                {actionType === 'INVALIDATE' && ' akan ditandai bukan masalah.'}
                {actionType === 'UNLINK' && ' akan dihapus relasinya.'}
              </p>
              
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Catatan Tambahan</label>
                <textarea
                  className="w-full border border-gray-300 rounded text-xs px-2 py-1.5 focus:ring-indigo-500 focus:border-indigo-500"
                  rows="2"
                  value={actionNotes}
                  onChange={(e) => setActionNotes(e.target.value)}
                  disabled={resolving}
                />
              </div>
            </div>
            
            <div className="px-5 py-3 border-t border-gray-100 flex justify-end space-x-2 bg-gray-50">
              <button
                onClick={() => setSelectedAnomaly(null)}
                disabled={resolving}
                className="px-3 py-1.5 text-xs font-medium text-gray-700 bg-white border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-50"
              >
                Batal
              </button>
              <button
                onClick={handleResolve}
                disabled={resolving}
                className={`px-3 py-1.5 text-xs font-medium text-white rounded disabled:opacity-50 flex items-center ${
                  actionType === 'SOLVE' ? 'bg-emerald-600 hover:bg-emerald-700' :
                  actionType === 'INVALIDATE' ? 'bg-amber-600 hover:bg-amber-700' :
                  'bg-rose-600 hover:bg-rose-700'
                }`}
              >
                {resolving && <RefreshCw className="w-3 h-3 mr-1 animate-spin" />}
                {resolving ? 'Menyimpan...' : 'Simpan'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AnomalyDetection;
