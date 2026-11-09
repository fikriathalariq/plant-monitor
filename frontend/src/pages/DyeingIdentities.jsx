import React, { useState, useEffect, useMemo, useRef } from 'react';
import api from '../lib/api';
import { useToast } from '../context/ToastContext';
import {
  Search, Plus, Edit2, Trash2, X, Save, ChevronLeft, ChevronRight,
  Activity, AlertCircle, CheckCircle2, Clock, Flame, Copy, Sparkles,
  RefreshCw, Layers, Check, ExternalLink, Zap,
  Calendar, ArrowRight, Info, AlertTriangle, FileSpreadsheet, ChevronDown
} from 'lucide-react';
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer
} from 'recharts';
import * as XLSX from 'xlsx';

// Helper live yard calculator
const calculateYardFromTube = (val) => {
  if (!val || typeof val !== 'string') return null;
  const clean = val.trim();

  const parsePart = (v) => {
    const s = v.trim();
    // 1. Roll: e.g. 6 Roll or 6 Roll ( 739 )
    const mRoll = s.match(/^(\d+)\s*roll/i);
    if (mRoll) return parseInt(mRoll[1], 10) * 100;

    // 2. PCS with multiplier: e.g. 6 PCS ( 2X ) or 10 pcs (2x)
    const mPcsX = s.match(/(\d+)\s*pcs\s*\(\s*(\d+)\s*x\s*\)/i);
    if (mPcsX) {
      return parseInt(mPcsX[1], 10) * parseInt(mPcsX[2], 10) * 50;
    }

    // 3. Simple PCS: e.g. 12 PCS
    const mPcs = s.match(/(\d+)\s*pcs/i);
    if (mPcs) return parseInt(mPcs[1], 10) * 50;

    // 4. Meter: e.g. 300 M
    const mM = s.match(/^(\d+)\s*m$/i);
    if (mM) return Math.round(parseInt(mM[1], 10) * 1.09361);

    return null;
  };

  if (clean.includes('/')) {
    const parts = clean.split('/');
    const sub = parts.map(parsePart);
    if (sub.every(x => x !== null)) {
      return sub.reduce((a, b) => a + b, 0);
    }
  }
  return parsePart(clean);
};

// Jenis proses badge styling
const getProcessBadge = (jenis) => {
  if (!jenis) return { label: '-', className: 'bg-slate-100 text-slate-700 border-slate-200' };
  const j = jenis.toUpperCase();
  if (j === 'FRESH') {
    return { label: 'Fresh', className: 'bg-emerald-50 text-emerald-700 border-emerald-200 font-semibold' };
  }
  if (['TOPPING', 'TOP_LEVEL', 'LEVELLING', 'MIGRASI'].includes(j)) {
    return { label: jenis.replace('_', ' '), className: 'bg-amber-50 text-amber-700 border-amber-200 font-medium' };
  }
  if (j.startsWith('CREAPING') || j.includes('ULANG')) {
    return { label: jenis.replace('_', ' '), className: 'bg-purple-50 text-purple-700 border-purple-200 font-medium' };
  }
  if (j.startsWith('CUCI')) {
    return { label: jenis.replace('_', ' '), className: 'bg-sky-50 text-sky-700 border-sky-200 font-medium' };
  }
  return { label: jenis.replace('_', ' '), className: 'bg-slate-100 text-slate-700 border-slate-200' };
};

// Tooltip for Mini Recharts Curve
const SparklineTooltip = ({ active, payload }) => {
  if (active && payload && payload.length) {
    const p = payload[0].payload;
    return (
      <div className="bg-slate-900/95 text-white px-2.5 py-1.5 rounded-lg shadow-xl text-[11px] border border-slate-700 leading-tight">
        <div className="text-slate-400 font-mono">Pukul: {p.time}</div>
        <div className="font-bold text-rose-400 text-xs mt-0.5">
          {p.temp != null ? `${Number(p.temp).toFixed(1)} °C` : '-'}
        </div>
      </div>
    );
  }
  return null;
};

const INITIAL_FORM = {
  dyeing_process_id: null,
  machine_id: '',
  nomor_order: '',
  artikel_kain: '',
  batch: '', // Nomor Batch Kain (manual)
  kode_buyer: '',
  program_id: '',
  isi_per_tube: '',
  operator: '',
  nomor_warna: '',
  nomor_desain: '',
  handling_quality: '',
  jenis_proses: 'FRESH',
  cycle_60: '',
  cycle_puncak: '',
  nozzle_main_pump: '',
  masalah: '',
  keterangan: ''
};

const DyeingIdentities = () => {
  const toast = useToast();

  // Active Tab: "pending" (Antrean Belum Diisi) | "completed" (Riwayat Sudah Diisi)
  const [activeTab, setActiveTab] = useState('pending');

  // Stats / KPIs
  const [stats, setStats] = useState({
    total_identities: 0,
    fresh_count: 0,
    rework_count: 0,
    orphan_count: 0,
    pending_batches_7d: 0
  });

  // Options State (machines, programs with ideal specs, jenis_proses)
  const [options, setOptions] = useState({
    machines: [],
    programs: [],
    jenis_proses: []
  });

  // Pending Batches State
  const [pendingBatches, setPendingBatches] = useState([]);
  const [pendingLoading, setPendingLoading] = useState(true);
  const [pendingFilterDays, setPendingFilterDays] = useState(7);
  const [pendingMachineFilter, setPendingMachineFilter] = useState('');
  const [pendingSearch, setPendingSearch] = useState('');

  // Completed Identities State
  const [identities, setIdentities] = useState([]);
  const [completedLoading, setCompletedLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalCount, setTotalCount] = useState(0);

  // Filters for Completed Tab
  const [historySearch, setHistorySearch] = useState('');
  const [historyMachineFilter, setHistoryMachineFilter] = useState('');
  const [historyProcessFilter, setHistoryProcessFilter] = useState('');
  const [historyProgramFilter, setHistoryProgramFilter] = useState('');
  const [historyDateFrom, setHistoryDateFrom] = useState('');
  const [historyDateTo, setHistoryDateTo] = useState('');

  // Form State & Drawer
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [currentId, setCurrentId] = useState(null); // DyeingIdentity ID if editing
  const [activeBatchContext, setActiveBatchContext] = useState(null); // Sensor info if linked
  const [formData, setFormData] = useState(INITIAL_FORM);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [orderLookupSuggestion, setOrderLookupSuggestion] = useState(null);
  const [prefillLoading, setPrefillLoading] = useState(false);

  // Telemetry Curve & Key Timestamps State
  const [processTelemetry, setProcessTelemetry] = useState(null);
  const [telemetryLoading, setTelemetryLoading] = useState(false);

  // Searchable Program Dropdown State
  const [isProgramDropdownOpen, setIsProgramDropdownOpen] = useState(false);
  const [programSearchText, setProgramSearchText] = useState('');
  const programDropdownRef = useRef(null);

  // Close program dropdown on outside click
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (programDropdownRef.current && !programDropdownRef.current.contains(event.target)) {
        setIsProgramDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Live estimated yard calculation
  const liveYard = useMemo(() => calculateYardFromTube(formData.isi_per_tube), [formData.isi_per_tube]);

  // Fetch Options & Stats
  const fetchOptions = async () => {
    try {
      const res = await api.get('/identities/options');
      setOptions(res.data);
    } catch (err) {
      console.error('Error fetching options:', err);
    }
  };

  const fetchStats = async () => {
    try {
      const res = await api.get('/identities/stats');
      setStats(res.data);
    } catch (err) {
      console.error('Error fetching stats:', err);
    }
  };

  // Fetch Process Telemetry (Curve + Key Timestamps)
  const fetchProcessTelemetry = async (processId) => {
    if (!processId) {
      setProcessTelemetry(null);
      return;
    }
    setTelemetryLoading(true);
    try {
      const res = await api.get(`/identities/process-telemetry/${processId}`);
      setProcessTelemetry(res.data);
    } catch (err) {
      console.error('Error fetching process telemetry:', err);
      setProcessTelemetry(null);
    } finally {
      setTelemetryLoading(false);
    }
  };

  // Fetch Pending Batches
  const fetchPendingBatches = async () => {
    setPendingLoading(true);
    try {
      const params = new URLSearchParams();
      params.append('days', pendingFilterDays);
      if (pendingMachineFilter) params.append('machine_id', pendingMachineFilter);
      if (pendingSearch) params.append('search', pendingSearch);

      const res = await api.get(`/identities/pending-batches?${params.toString()}`);
      setPendingBatches(res.data.items || []);
    } catch (err) {
      console.error('Error fetching pending batches:', err);
      toast.error('Gagal memuat antrean batch mesin.');
    } finally {
      setPendingLoading(false);
    }
  };

  // Fetch Completed Identities History
  const fetchCompletedIdentities = async () => {
    setCompletedLoading(true);
    try {
      const params = new URLSearchParams();
      params.append('page', page);
      if (historySearch) params.append('search', historySearch);
      if (historyMachineFilter) params.append('machine_id', historyMachineFilter);
      if (historyProcessFilter) params.append('jenis_proses', historyProcessFilter);
      if (historyProgramFilter) params.append('program_id', historyProgramFilter);
      if (historyDateFrom) params.append('date_from', historyDateFrom);
      if (historyDateTo) params.append('date_to', historyDateTo);

      const res = await api.get(`/identities/?${params.toString()}`);
      setIdentities(res.data.items || []);
      setTotalCount(res.data.count || 0);
      setTotalPages(Math.ceil((res.data.count || 0) / 20) || 1);
    } catch (err) {
      console.error('Error fetching completed identities:', err);
    } finally {
      setCompletedLoading(false);
    }
  };

  useEffect(() => {
    fetchOptions();
    fetchStats();
  }, []);

  useEffect(() => {
    if (activeTab === 'pending') {
      fetchPendingBatches();
    } else {
      fetchCompletedIdentities();
    }
  }, [activeTab]);

  useEffect(() => {
    if (activeTab === 'pending') {
      const timer = setTimeout(() => {
        fetchPendingBatches();
      }, 400);
      return () => clearTimeout(timer);
    }
  }, [pendingFilterDays, pendingMachineFilter, pendingSearch]);

  useEffect(() => {
    if (activeTab === 'completed') {
      const timer = setTimeout(() => {
        fetchCompletedIdentities();
      }, 400);
      return () => clearTimeout(timer);
    }
  }, [page, historySearch, historyMachineFilter, historyProcessFilter, historyProgramFilter, historyDateFrom, historyDateTo]);

  // Open Form to fill a Pending Batch
  const handleOpenFillBatch = (batchItem) => {
    setActiveBatchContext(batchItem);
    setCurrentId(batchItem.identity_id || null);

    // PENTING: Nomor batch kain dan nomor batch proses (sensor) itu beda!
    // Jangan samakan batch kain dengan nomor batch sensor. Biarkan batch kain kosong untuk diisi manual.
    setFormData({
      ...INITIAL_FORM,
      dyeing_process_id: batchItem.id,
      machine_id: batchItem.machine_id,
      batch: '', // Dikosongkan agar diisi manual sesuai kartu fisik kain
      operator: ''
    });
    setOrderLookupSuggestion(null);
    setProgramSearchText('');
    setIsProgramDropdownOpen(false);
    setIsDrawerOpen(true);

    // Fetch telemetri kurva sensor
    fetchProcessTelemetry(batchItem.id);
  };

  // Open Form to Edit an Existing Identity
  const handleOpenEdit = (identity) => {
    const ctx = identity.dyeing_process_id ? {
      id: identity.dyeing_process_id,
      machine_code: identity.machine?.code || '',
      machine_name: identity.machine?.name || '',
      batch_number: identity.dyeing_process_batch,
      start_time: identity.start_time_snapshot
    } : null;

    setActiveBatchContext(ctx);
    setCurrentId(identity.id);
    setFormData({
      dyeing_process_id: identity.dyeing_process_id || null,
      machine_id: identity.machine?.id || '',
      nomor_order: identity.nomor_order || '',
      artikel_kain: identity.artikel_kain || '',
      batch: identity.batch || '', // Batch kain dari database
      kode_buyer: identity.kode_buyer || '',
      program_id: identity.program?.id || '',
      isi_per_tube: identity.isi_per_tube || '',
      operator: identity.operator || '',
      nomor_warna: identity.nomor_warna || '',
      nomor_desain: identity.nomor_desain || '',
      handling_quality: identity.handling_quality || '',
      jenis_proses: identity.jenis_proses || 'FRESH',
      cycle_60: identity.cycle_60 || '',
      cycle_puncak: identity.cycle_puncak || '',
      nozzle_main_pump: identity.nozzle_main_pump || '',
      masalah: identity.masalah || '',
      keterangan: identity.keterangan || ''
    });
    setOrderLookupSuggestion(null);
    setProgramSearchText('');
    setIsProgramDropdownOpen(false);
    setIsDrawerOpen(true);

    if (identity.dyeing_process_id) {
      fetchProcessTelemetry(identity.dyeing_process_id);
    } else {
      setProcessTelemetry(null);
    }
  };

  // Open Form for Brand New Manual Identity (Orphan / Standalone)
  const handleOpenManualAdd = () => {
    setActiveBatchContext(null);
    setProcessTelemetry(null);
    setCurrentId(null);
    setFormData(INITIAL_FORM);
    setOrderLookupSuggestion(null);
    setProgramSearchText('');
    setIsProgramDropdownOpen(false);
    setIsDrawerOpen(true);
  };

  const handleCloseDrawer = () => {
    setIsDrawerOpen(false);
    setCurrentId(null);
    setActiveBatchContext(null);
    setProcessTelemetry(null);
    setOrderLookupSuggestion(null);
    setIsProgramDropdownOpen(false);
  };

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: value
    }));
  };

  // Selected Program Object
  const selectedProgram = useMemo(() => {
    if (!formData.program_id) return null;
    return options.programs.find(p => p.id === Number(formData.program_id)) || null;
  }, [formData.program_id, options.programs]);

  // Actual Sensor Telemetry Values for Comparison
  const actualTemp = useMemo(() => {
    return processTelemetry?.max_temp ?? activeBatchContext?.peak_temp ?? null;
  }, [processTelemetry, activeBatchContext]);

  const actualHeat = useMemo(() => {
    return processTelemetry?.heating_duration ?? activeBatchContext?.heating_duration ?? null;
  }, [processTelemetry, activeBatchContext]);

  const actualSteady = useMemo(() => {
    return processTelemetry?.steady_duration ?? activeBatchContext?.steady_duration ?? null;
  }, [processTelemetry, activeBatchContext]);

  const actualTotal = useMemo(() => {
    return processTelemetry?.duration_minutes ?? activeBatchContext?.duration_minutes ?? null;
  }, [processTelemetry, activeBatchContext]);

  // Filtered Programs for Combobox
  const filteredPrograms = useMemo(() => {
    if (!programSearchText) return options.programs;
    const q = programSearchText.toLowerCase();
    return options.programs.filter(p =>
      p.nama.toLowerCase().includes(q) ||
      String(p.suhu_max || '').includes(q) ||
      String(p.durasi_heating_ideal || '').includes(q)
    );
  }, [options.programs, programSearchText]);

  // Comparison Deltas
  const deltaTemp = useMemo(() => {
    if (actualTemp == null || selectedProgram?.suhu_max == null) return null;
    return actualTemp - selectedProgram.suhu_max;
  }, [actualTemp, selectedProgram]);

  const deltaHeat = useMemo(() => {
    if (actualHeat == null || selectedProgram?.durasi_heating_ideal == null) return null;
    return actualHeat - selectedProgram.durasi_heating_ideal;
  }, [actualHeat, selectedProgram]);

  const deltaSteady = useMemo(() => {
    if (actualSteady == null || selectedProgram?.durasi_keeping_ideal == null) return null;
    return actualSteady - selectedProgram.durasi_keeping_ideal;
  }, [actualSteady, selectedProgram]);

  const deltaTotal = useMemo(() => {
    if (actualTotal == null || selectedProgram?.durasi_ideal == null) return null;
    return actualTotal - selectedProgram.durasi_ideal;
  }, [actualTotal, selectedProgram]);

  // 1-Click Copy from Last Batch on the same machine
  const handleCopyPreviousBatch = async () => {
    const targetMachineId = formData.machine_id || activeBatchContext?.machine_id;
    if (!targetMachineId) {
      toast.error('Pilih mesin terlebih dahulu.');
      return;
    }
    setPrefillLoading(true);
    try {
      const res = await api.get(`/identities/prefill?machine_id=${targetMachineId}`);
      if (res.data && res.data.machine_last) {
        const last = res.data.machine_last;
        // PENTING: Jangan menimpa batch (Nomor Batch Kain) saat menyalin
        setFormData(prev => ({
          ...prev,
          nomor_order: last.nomor_order || prev.nomor_order,
          artikel_kain: last.artikel_kain || prev.artikel_kain,
          kode_buyer: last.kode_buyer || prev.kode_buyer,
          program_id: last.program_id || prev.program_id,
          jenis_proses: last.jenis_proses || prev.jenis_proses,
          isi_per_tube: last.isi_per_tube || prev.isi_per_tube,
          operator: last.operator || prev.operator,
          nomor_warna: last.nomor_warna || prev.nomor_warna,
          nomor_desain: last.nomor_desain || prev.nomor_desain,
          cycle_60: last.cycle_60 || prev.cycle_60,
          cycle_puncak: last.cycle_puncak || prev.cycle_puncak,
          nozzle_main_pump: last.nozzle_main_pump || prev.nozzle_main_pump,
          handling_quality: last.handling_quality || prev.handling_quality,
        }));
        toast.success(`Berhasil menyalin spesifikasi dari batch terakhir mesin ini!`);
      } else {
        toast.info('Belum ada riwayat batch sebelumnya pada mesin ini.');
      }
    } catch (err) {
      console.error(err);
      toast.error('Gagal mengambil data batch sebelumnya.');
    } finally {
      setPrefillLoading(false);
    }
  };

  // Auto-Lookup when Nomor Order is blurred or searched
  const handleOrderLookup = async (orderVal) => {
    const clean = (orderVal || formData.nomor_order || '').trim();
    if (!clean || clean.length < 3) return;

    try {
      const res = await api.get(`/identities/prefill?order_no=${encodeURIComponent(clean)}`);
      if (res.data && res.data.order_match) {
        setOrderLookupSuggestion(res.data.order_match);
      } else {
        setOrderLookupSuggestion(null);
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handleApplyOrderLookup = () => {
    if (!orderLookupSuggestion) return;
    setFormData(prev => ({
      ...prev,
      artikel_kain: orderLookupSuggestion.artikel_kain || prev.artikel_kain,
      kode_buyer: orderLookupSuggestion.kode_buyer || prev.kode_buyer,
      nomor_warna: orderLookupSuggestion.nomor_warna || prev.nomor_warna,
      nomor_desain: orderLookupSuggestion.nomor_desain || prev.nomor_desain,
      program_id: orderLookupSuggestion.program_id || prev.program_id,
      jenis_proses: orderLookupSuggestion.jenis_proses || prev.jenis_proses,
    }));
    toast.success('Artikel & Buyer dari nomor order berhasil diisikan!');
    setOrderLookupSuggestion(null);
  };

  // Submit Handler
  const handleSave = async (andNext = false) => {
    if (!formData.nomor_order && !formData.artikel_kain) {
      toast.error('Mohon isi Nomor Order atau Nama Artikel Kain.');
      return;
    }

    setIsSubmitting(true);
    try {
      const payload = { ...formData };
      if (payload.machine_id === '') payload.machine_id = null;
      if (payload.program_id === '') payload.program_id = null;

      if (currentId) {
        await api.put(`/identities/${currentId}`, payload);
        toast.success('Identitas berhasil diperbarui!');
      } else {
        await api.post('/identities/', payload);
        toast.success('Identitas batch baru berhasil disimpan!');
      }

      fetchStats();

      if (andNext && activeTab === 'pending' && activeBatchContext) {
        const currentIndex = pendingBatches.findIndex(b => b.id === activeBatchContext.id);
        const updatedPending = pendingBatches.filter(b => b.id !== activeBatchContext.id);
        setPendingBatches(updatedPending);

        if (updatedPending.length > 0) {
          const nextIndex = currentIndex < updatedPending.length ? currentIndex : 0;
          const nextBatch = updatedPending[nextIndex];
          toast.info(`Membuka batch berikutnya: ${nextBatch.machine_code} #${nextBatch.batch_number}`);
          handleOpenFillBatch(nextBatch);
        } else {
          toast.success('Semua antrean batch telah terisi!');
          handleCloseDrawer();
          fetchPendingBatches();
        }
      } else {
        if (activeTab === 'pending') fetchPendingBatches();
        if (activeTab === 'completed') fetchCompletedIdentities();
        handleCloseDrawer();
      }
    } catch (err) {
      console.error('Error saving identity:', err);
      toast.error('Terjadi kesalahan saat menyimpan identitas.');
    } finally {
      setIsSubmitting(false);
    }
  };

  // Delete Handler
  const handleDelete = async (id) => {
    if (window.confirm('Apakah Anda yakin ingin menghapus identitas proses ini?')) {
      try {
        await api.delete(`/identities/${id}`);
        fetchCompletedIdentities();
        fetchStats();
        toast.success('Identitas proses berhasil dihapus');
      } catch (err) {
        console.error(err);
        toast.error('Terjadi kesalahan saat menghapus data.');
      }
    }
  };

  // Export to Excel
  const handleExportExcel = () => {
    if (!identities || identities.length === 0) {
      toast.error('Tidak ada data untuk diekspor.');
      return;
    }

    const exportRows = identities.map((row, idx) => ({
      No: idx + 1,
      Mesin: row.machine?.code || '-',
      Nama_Mesin: row.machine?.name || '-',
      Batch_Sensor_SCADA: row.dyeing_process_batch || '-',
      Nomor_Order: row.nomor_order || '-',
      Batch_Kain: row.batch || '-',
      Artikel_Kain: row.artikel_kain || '-',
      Kode_Buyer: row.kode_buyer || '-',
      Program: row.program?.nama || '-',
      Jenis_Proses: row.jenis_proses || '-',
      Isi_Per_Tube: row.isi_per_tube || '-',
      Est_Yard: row.output_yard || '-',
      Operator: row.operator || '-',
      Nomor_Warna: row.nomor_warna || '-',
      Nomor_Desain: row.nomor_desain || '-',
      Nozzle_Pump: row.nozzle_main_pump || '-',
      Cycle_60: row.cycle_60 || '-',
      Cycle_Puncak: row.cycle_puncak || '-',
      Masalah: row.masalah || '-',
      Keterangan: row.keterangan || '-',
      Waktu_Snapshot: row.start_time_snapshot ? new Date(row.start_time_snapshot).toLocaleString('id-ID') : '-'
    }));

    const ws = XLSX.utils.json_to_sheet(exportRows);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, 'Identitas Celup');
    XLSX.writeFile(wb, `Dyeing_Identities_${new Date().toISOString().slice(0, 10)}.xlsx`);
    toast.success('Data berhasil diekspor ke Excel!');
  };

  // Format date helper
  const formatDate = (isoStr) => {
    if (!isoStr) return '-';
    try {
      const d = new Date(isoStr);
      return d.toLocaleDateString('id-ID', {
        day: '2-digit',
        month: 'short',
        hour: '2-digit',
        minute: '2-digit'
      });
    } catch {
      return isoStr;
    }
  };

  return (
    <div className="p-3 sm:p-5 md:p-6 bg-slate-50 min-h-screen flex flex-col font-sans">
      
      {/* ── TOP HEADER & TITLE ─────────────────────────────────────────── */}
      <div className="flex flex-col md:flex-row md:items-center justify-between pb-4 border-b border-slate-200 gap-3">
        <div>
          <div className="flex items-center space-x-2">
            <span className="p-2 bg-indigo-600 text-white rounded-xl shadow-sm">
              <Layers className="w-5 h-5" />
            </span>
            <div>
              <h1 className="text-xl sm:text-2xl font-black text-slate-800 tracking-tight">
                Dyeing Identities & Antrean Input
              </h1>
              <p className="text-xs sm:text-sm text-slate-500 font-medium">
                Meja kerja terpadu input kartu proses celup, sinkronisasi batch sensor, & tracking identitas produksi
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center space-x-2">
          <button
            onClick={() => {
              fetchStats();
              if (activeTab === 'pending') fetchPendingBatches();
              else fetchCompletedIdentities();
            }}
            className="p-2 text-slate-600 bg-white border border-slate-200 hover:bg-slate-50 rounded-xl text-sm font-semibold shadow-sm transition-all flex items-center gap-1.5"
            title="Refresh Data"
          >
            <RefreshCw className="w-4 h-4 text-slate-500" />
            <span className="hidden sm:inline">Refresh</span>
          </button>

          <button
            onClick={handleOpenManualAdd}
            className="px-3.5 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-sm font-bold shadow-sm transition-all flex items-center gap-1.5"
          >
            <Plus className="w-4 h-4" />
            <span>Input Manual</span>
          </button>
        </div>
      </div>

      {/* ── KPI METRICS STRIP ────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 my-4">
        {/* Metric 1: Pending Batches */}
        <div 
          onClick={() => setActiveTab('pending')}
          className={`p-3.5 sm:p-4 rounded-2xl border transition-all cursor-pointer shadow-sm ${
            activeTab === 'pending'
              ? 'bg-rose-50/80 border-rose-300 ring-2 ring-rose-400/20'
              : 'bg-white border-slate-200 hover:border-rose-200'
          }`}
        >
          <div className="flex items-center justify-between text-xs font-semibold text-rose-600 mb-1">
            <span className="flex items-center gap-1.5">
              <AlertCircle className="w-4 h-4 text-rose-500" />
              Antrean Belum Diisi
            </span>
            <span className="px-2 py-0.5 rounded-full bg-rose-100 text-rose-700 text-[11px] font-bold">
              7 Hari Terakhir
            </span>
          </div>
          <div className="text-2xl sm:text-3xl font-black text-rose-700">
            {stats.pending_batches_7d}
            <span className="text-sm font-semibold text-rose-500 ml-1.5">Batch</span>
          </div>
          <div className="text-[11px] text-slate-500 mt-1 flex items-center gap-1">
            <Zap className="w-3 h-3 text-amber-500" />
            Klik untuk langsung mengisi antrean
          </div>
        </div>

        {/* Metric 2: Total Completed */}
        <div 
          onClick={() => setActiveTab('completed')}
          className={`p-3.5 sm:p-4 rounded-2xl border transition-all cursor-pointer shadow-sm ${
            activeTab === 'completed'
              ? 'bg-indigo-50/80 border-indigo-300 ring-2 ring-indigo-400/20'
              : 'bg-white border-slate-200 hover:border-indigo-200'
          }`}
        >
          <div className="flex items-center justify-between text-xs font-semibold text-indigo-600 mb-1">
            <span className="flex items-center gap-1.5">
              <CheckCircle2 className="w-4 h-4 text-indigo-500" />
              Total Batch Terdata
            </span>
            <span className="px-2 py-0.5 rounded-full bg-indigo-100 text-indigo-700 text-[11px] font-bold">
              Riwayat
            </span>
          </div>
          <div className="text-2xl sm:text-3xl font-black text-slate-800">
            {stats.total_identities.toLocaleString('id-ID')}
            <span className="text-sm font-semibold text-slate-400 ml-1.5">Record</span>
          </div>
          <div className="text-[11px] text-slate-500 mt-1">
            Identitas proses tersimpan di sistem
          </div>
        </div>

        {/* Metric 3: Fresh vs Rework Ratio */}
        <div className="p-3.5 sm:p-4 rounded-2xl border bg-white border-slate-200 shadow-sm">
          <div className="flex items-center justify-between text-xs font-semibold text-emerald-600 mb-1">
            <span className="flex items-center gap-1.5">
              <Sparkles className="w-4 h-4 text-emerald-500" />
              Rasio Celup Fresh
            </span>
            <span className="px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700 text-[11px] font-bold">
              First-Time Right
            </span>
          </div>
          <div className="text-2xl sm:text-3xl font-black text-emerald-700">
            {stats.total_identities > 0
              ? `${((stats.fresh_count / stats.total_identities) * 100).toFixed(1)}%`
              : '0%'}
          </div>
          <div className="text-[11px] text-slate-500 mt-1">
            {stats.fresh_count} Fresh vs {stats.rework_count} Topping/Cuci
          </div>
        </div>

        {/* Metric 4: Sensor Connectivity */}
        <div className="p-3.5 sm:p-4 rounded-2xl border bg-white border-slate-200 shadow-sm">
          <div className="flex items-center justify-between text-xs font-semibold text-sky-600 mb-1">
            <span className="flex items-center gap-1.5">
              <Activity className="w-4 h-4 text-sky-500" />
              Terkoneksi Sensor
            </span>
            <span className="px-2 py-0.5 rounded-full bg-sky-100 text-sky-700 text-[11px] font-bold">
              SCADA
            </span>
          </div>
          <div className="text-2xl sm:text-3xl font-black text-sky-700">
            {stats.total_identities > 0
              ? `${(((stats.total_identities - stats.orphan_count) / stats.total_identities) * 100).toFixed(1)}%`
              : '0%'}
          </div>
          <div className="text-[11px] text-slate-500 mt-1">
            {stats.orphan_count > 0 ? `${stats.orphan_count} batch manual (orphan)` : 'Semua ter-link'}
          </div>
        </div>
      </div>

      {/* ── TAB SELECTOR ─────────────────────────────────────────────────── */}
      <div className="flex items-center space-x-2 border-b border-slate-200 mb-4">
        <button
          onClick={() => setActiveTab('pending')}
          className={`flex items-center gap-2 py-2.5 px-4 font-bold text-sm border-b-2 transition-all ${
            activeTab === 'pending'
              ? 'border-rose-600 text-rose-600 bg-rose-50/50 rounded-t-lg'
              : 'border-transparent text-slate-500 hover:text-slate-800'
          }`}
        >
          <span className="relative flex h-2.5 w-2.5">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-rose-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-rose-600"></span>
          </span>
          <span>🔴 Antrean Batch Belum Diisi</span>
          <span className="px-2 py-0.5 rounded-full text-xs font-bold bg-rose-100 text-rose-700 ml-1">
            {stats.pending_batches_7d}
          </span>
        </button>

        <button
          onClick={() => setActiveTab('completed')}
          className={`flex items-center gap-2 py-2.5 px-4 font-bold text-sm border-b-2 transition-all ${
            activeTab === 'completed'
              ? 'border-indigo-600 text-indigo-600 bg-indigo-50/50 rounded-t-lg'
              : 'border-transparent text-slate-500 hover:text-slate-800'
          }`}
        >
          <CheckCircle2 className="w-4 h-4 text-indigo-500" />
          <span>🟢 Riwayat Sudah Diisi</span>
          <span className="px-2 py-0.5 rounded-full text-xs font-bold bg-slate-100 text-slate-600 ml-1">
            {totalCount || stats.total_identities}
          </span>
        </button>
      </div>

      {/* ── TAB 1 CONTENT: PENDING BATCHES QUEUE ─────────────────────────── */}
      {activeTab === 'pending' && (
        <div className="flex flex-col bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden flex-1">
          {/* Filter Bar Pending */}
          <div className="p-3.5 sm:p-4 bg-slate-50/80 border-b border-slate-200 flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center flex-wrap gap-2 text-xs font-semibold text-slate-600">
              <span className="text-slate-400 uppercase tracking-wider text-[11px]">Filter Antrean:</span>

              {/* Mesin Filter */}
              <select
                value={pendingMachineFilter}
                onChange={(e) => setPendingMachineFilter(e.target.value)}
                className="bg-white border border-slate-200 rounded-xl px-2.5 py-1.5 text-xs font-medium text-slate-700 focus:ring-2 focus:ring-rose-500 focus:outline-none"
              >
                <option value="">Semua Mesin</option>
                {options.machines.map(m => (
                  <option key={m.id} value={m.id}>{m.code} - {m.name}</option>
                ))}
              </select>

              {/* Days Range */}
              <select
                value={pendingFilterDays}
                onChange={(e) => setPendingFilterDays(Number(e.target.value))}
                className="bg-white border border-slate-200 rounded-xl px-2.5 py-1.5 text-xs font-medium text-slate-700 focus:ring-2 focus:ring-rose-500 focus:outline-none"
              >
                <option value={1}>1 Hari Terakhir (Hari Ini)</option>
                <option value={3}>3 Hari Terakhir</option>
                <option value={7}>7 Hari Terakhir</option>
                <option value={14}>14 Hari Terakhir</option>
                <option value={30}>30 Hari Terakhir</option>
              </select>
            </div>

            {/* Quick Search on Pending Table */}
            <div className="relative w-full sm:w-64">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                <Search className="h-3.5 w-3.5 text-slate-400" />
              </div>
              <input
                type="text"
                placeholder="Cari mesin / batch #..."
                value={pendingSearch}
                onChange={(e) => setPendingSearch(e.target.value)}
                className="w-full pl-9 pr-3 py-1.5 bg-white border border-slate-200 rounded-xl text-xs placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-rose-500 font-medium"
              />
            </div>
          </div>

          {/* Pending Batches Table */}
          <div className="overflow-x-auto flex-1">
            <table className="min-w-full divide-y divide-slate-100 text-left text-xs">
              <thead className="bg-slate-50 sticky top-0 z-10 font-bold text-slate-500 uppercase tracking-wider">
                <tr>
                  <th className="px-4 py-3">Mesin</th>
                  <th className="px-4 py-3">Batch Sensor</th>
                  <th className="px-4 py-3">Waktu Mulai – Selesai</th>
                  <th className="px-4 py-3">Durasi</th>
                  <th className="px-4 py-3">Suhu Puncak</th>
                  <th className="px-4 py-3">Status Sensor</th>
                  <th className="px-4 py-3">Status Kartu</th>
                  <th className="px-4 py-3 text-right">Aksi</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 bg-white">
                {pendingLoading ? (
                  <tr>
                    <td colSpan="8" className="px-6 py-12 text-center text-slate-400">
                      <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2 text-rose-500" />
                      Memuat antrean batch mesin...
                    </td>
                  </tr>
                ) : pendingBatches.length === 0 ? (
                  <tr>
                    <td colSpan="8" className="px-6 py-12 text-center text-slate-400">
                      <CheckCircle2 className="w-10 h-10 text-emerald-400 mx-auto mb-2" />
                      <div className="text-sm font-bold text-slate-700">Bagus Sekali! Semua Batch Terisi</div>
                      <div className="text-xs text-slate-400 mt-1">Tidak ada batch sensor yang belum memiliki identitas dalam rentang ini.</div>
                    </td>
                  </tr>
                ) : (
                  pendingBatches.map((batch) => (
                    <tr
                      key={batch.id}
                      onClick={() => handleOpenFillBatch(batch)}
                      className="hover:bg-rose-50/40 cursor-pointer transition-colors group"
                    >
                      <td className="px-4 py-3 font-bold text-slate-800 whitespace-nowrap">
                        <span className="px-2.5 py-1 rounded-lg bg-slate-100 text-slate-800 font-mono text-xs border border-slate-200">
                          {batch.machine_code}
                        </span>
                        <span className="text-[11px] text-slate-400 font-normal ml-2">{batch.machine_name}</span>
                      </td>

                      <td className="px-4 py-3 whitespace-nowrap">
                        <span className="font-mono font-black text-rose-700 text-sm">
                          #{batch.batch_number}
                        </span>
                      </td>

                      <td className="px-4 py-3 text-slate-600 whitespace-nowrap">
                        <div className="font-medium text-slate-800">
                          {formatDate(batch.start_time)}
                        </div>
                        <div className="text-[11px] text-slate-400">
                          {batch.end_time ? `s/d ${formatDate(batch.end_time)}` : 'Sedang berjalan'}
                        </div>
                      </td>

                      <td className="px-4 py-3 text-slate-700 font-mono font-semibold whitespace-nowrap">
                        {batch.duration_minutes ? `${batch.duration_minutes} mnt` : '-'}
                      </td>

                      <td className="px-4 py-3 whitespace-nowrap">
                        {batch.peak_temp ? (
                          <span className={`px-2 py-0.5 rounded-full font-mono font-bold text-[11px] ${
                            batch.peak_temp >= 120
                              ? 'bg-purple-100 text-purple-700'
                              : batch.peak_temp >= 95
                              ? 'bg-rose-100 text-rose-700'
                              : 'bg-emerald-100 text-emerald-700'
                          }`}>
                            <Flame className="w-3 h-3 inline mr-1 text-current" />
                            {batch.peak_temp}°C
                          </span>
                        ) : '-'}
                      </td>

                      <td className="px-4 py-3 whitespace-nowrap">
                        {batch.is_complete ? (
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-100 text-slate-600">
                            SELESAI
                          </span>
                        ) : (
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-100 text-amber-700 animate-pulse">
                            SEDANG JALAN
                          </span>
                        )}
                      </td>

                      <td className="px-4 py-3 whitespace-nowrap">
                        {batch.status === 'UNFILLED' ? (
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-100 text-rose-700 border border-rose-200">
                            ❌ Belum Diisi
                          </span>
                        ) : (
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-100 text-amber-700 border border-amber-200">
                            ⚠️ Belum Lengkap
                          </span>
                        )}
                      </td>

                      <td className="px-4 py-3 text-right whitespace-nowrap">
                        <div className="flex items-center justify-end space-x-1.5" onClick={(e) => e.stopPropagation()}>
                          {/* Link ke /history/report/{id} */}
                          <a
                            href={`/history/report/${batch.id}?machine=${encodeURIComponent(batch.machine_code || '')}&batch=${encodeURIComponent(batch.batch_number || '')}`}
                            target="_blank"
                            rel="noreferrer"
                            className="p-1.5 text-slate-500 hover:text-indigo-600 bg-slate-100 hover:bg-indigo-50 rounded-lg transition-colors flex items-center gap-1 text-xs font-semibold"
                            title="Buka Laporan SCADA"
                          >
                            <Activity className="w-4 h-4 text-indigo-500" />
                            <span className="hidden xl:inline">SCADA</span>
                          </a>

                          <button
                            onClick={() => handleOpenFillBatch(batch)}
                            className="px-2.5 py-1 bg-rose-600 hover:bg-rose-700 text-white rounded-lg font-bold text-xs flex items-center gap-1 shadow-sm transition-all"
                          >
                            <Zap className="w-3.5 h-3.5" />
                            <span>Isi Identitas</span>
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          <div className="p-3 bg-slate-50 border-t border-slate-200 text-xs text-slate-500 flex items-center justify-between">
            <span>Menampilkan <b>{pendingBatches.length}</b> batch sensor yang memerlukan kartu identitas.</span>
            <span className="text-[11px] text-slate-400">💡 Klik baris untuk langsung mengisi form</span>
          </div>
        </div>
      )}

      {/* ── TAB 2 CONTENT: COMPLETED IDENTITIES HISTORY ─────────────────── */}
      {activeTab === 'completed' && (
        <div className="flex flex-col bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden flex-1">
          {/* Smart Filter Bar Completed */}
          <div className="p-3.5 sm:p-4 bg-slate-50/80 border-b border-slate-200 flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center flex-wrap gap-2 text-xs font-semibold text-slate-600 w-full lg:w-auto">
              <span className="text-slate-400 uppercase tracking-wider text-[11px]">Filter:</span>

              {/* Mesin Filter */}
              <select
                value={historyMachineFilter}
                onChange={(e) => { setHistoryMachineFilter(e.target.value); setPage(1); }}
                className="bg-white border border-slate-200 rounded-xl px-2.5 py-1.5 text-xs font-medium text-slate-700 focus:ring-2 focus:ring-indigo-500 focus:outline-none"
              >
                <option value="">Semua Mesin</option>
                {options.machines.map(m => (
                  <option key={m.id} value={m.id}>{m.code} - {m.name}</option>
                ))}
              </select>

              {/* Jenis Proses Filter */}
              <select
                value={historyProcessFilter}
                onChange={(e) => { setHistoryProcessFilter(e.target.value); setPage(1); }}
                className="bg-white border border-slate-200 rounded-xl px-2.5 py-1.5 text-xs font-medium text-slate-700 focus:ring-2 focus:ring-indigo-500 focus:outline-none"
              >
                <option value="">Semua Proses</option>
                {options.jenis_proses.map(jp => (
                  <option key={jp.value} value={jp.value}>{jp.label}</option>
                ))}
              </select>

              {/* Program Filter */}
              <select
                value={historyProgramFilter}
                onChange={(e) => { setHistoryProgramFilter(e.target.value); setPage(1); }}
                className="bg-white border border-slate-200 rounded-xl px-2.5 py-1.5 text-xs font-medium text-slate-700 focus:ring-2 focus:ring-indigo-500 focus:outline-none max-w-[150px] truncate"
              >
                <option value="">Semua Program</option>
                {options.programs.map(p => (
                  <option key={p.id} value={p.id}>{p.nama}</option>
                ))}
              </select>

              {/* Date From */}
              <input
                type="date"
                value={historyDateFrom}
                onChange={(e) => { setHistoryDateFrom(e.target.value); setPage(1); }}
                className="bg-white border border-slate-200 rounded-xl px-2.5 py-1 text-xs font-medium text-slate-700 focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                title="Tanggal Dari"
              />

              {/* Date To */}
              <input
                type="date"
                value={historyDateTo}
                onChange={(e) => { setHistoryDateTo(e.target.value); setPage(1); }}
                className="bg-white border border-slate-200 rounded-xl px-2.5 py-1 text-xs font-medium text-slate-700 focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                title="Tanggal Sampai"
              />
            </div>

            {/* Search & Export Actions */}
            <div className="flex items-center space-x-2 w-full lg:w-auto ml-auto">
              <div className="relative w-full sm:w-64">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                  <Search className="h-3.5 w-3.5 text-slate-400" />
                </div>
                <input
                  type="text"
                  placeholder="Cari Order, Artikel, Buyer, Op..."
                  value={historySearch}
                  onChange={(e) => { setHistorySearch(e.target.value); setPage(1); }}
                  className="w-full pl-9 pr-3 py-1.5 bg-white border border-slate-200 rounded-xl text-xs placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 font-medium"
                />
              </div>

              <button
                onClick={handleExportExcel}
                className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-xs font-bold shadow-sm transition-all flex items-center gap-1.5 whitespace-nowrap"
                title="Ekspor ke Excel"
              >
                <FileSpreadsheet className="w-3.5 h-3.5" />
                <span>Excel</span>
              </button>
            </div>
          </div>

          {/* Completed Table */}
          <div className="overflow-x-auto flex-1">
            <table className="min-w-full divide-y divide-slate-100 text-left text-xs">
              <thead className="bg-slate-50 sticky top-0 z-10 font-bold text-slate-500 uppercase tracking-wider">
                <tr>
                  <th className="px-4 py-3">Mesin & Batch</th>
                  <th className="px-4 py-3">Nomor Order</th>
                  <th className="px-4 py-3">Artikel Kain & Buyer</th>
                  <th className="px-4 py-3">Program & Proses</th>
                  <th className="px-4 py-3">Isi Tube & Est. Yard</th>
                  <th className="px-4 py-3">Parameter Mesin</th>
                  <th className="px-4 py-3">Operator & Waktu</th>
                  <th className="px-4 py-3 text-right">Aksi</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 bg-white">
                {completedLoading ? (
                  <tr>
                    <td colSpan="8" className="px-6 py-12 text-center text-slate-400">
                      <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2 text-indigo-500" />
                      Memuat riwayat identitas celup...
                    </td>
                  </tr>
                ) : identities.length === 0 ? (
                  <tr>
                    <td colSpan="8" className="px-6 py-12 text-center text-slate-400">
                      <AlertCircle className="w-8 h-8 text-slate-300 mx-auto mb-2" />
                      Tidak ada riwayat identitas yang sesuai dengan filter pencarian.
                    </td>
                  </tr>
                ) : (
                  identities.map((row) => {
                    const badge = getProcessBadge(row.jenis_proses);
                    return (
                      <tr
                        key={row.id}
                        onClick={() => handleOpenEdit(row)}
                        className="hover:bg-indigo-50/50 cursor-pointer transition-colors group"
                      >
                        <td className="px-4 py-3 whitespace-nowrap">
                          <div className="flex items-center space-x-1.5">
                            <span className="px-2 py-0.5 rounded-lg bg-slate-100 text-slate-800 font-mono font-bold text-xs border border-slate-200">
                              {row.machine?.code || '-'}
                            </span>
                            {row.dyeing_process_batch ? (
                              <span className="font-mono text-indigo-600 font-bold text-xs" title="Batch Sensor SCADA">
                                #{row.dyeing_process_batch}
                              </span>
                            ) : null}
                          </div>
                          <div className="text-[11px] text-slate-400 font-mono mt-0.5">
                            Kain: <b className="text-slate-600">{row.batch || '-'}</b>
                          </div>
                        </td>

                        <td className="px-4 py-3 whitespace-nowrap">
                          <div className="font-bold text-slate-900 text-sm">
                            {row.nomor_order || '-'}
                          </div>
                          <div className="text-[11px] text-slate-400">
                            Warna: {row.nomor_warna || '-'} | Des: {row.nomor_desain || '-'}
                          </div>
                        </td>

                        <td className="px-4 py-3">
                          <div className="font-semibold text-slate-800 text-xs truncate max-w-[200px]" title={row.artikel_kain}>
                            {row.artikel_kain || '-'}
                          </div>
                          <div className="text-[11px] text-slate-500">
                            Buyer: <span className="font-medium text-slate-700">{row.kode_buyer || '-'}</span>
                          </div>
                        </td>

                        <td className="px-4 py-3">
                          <div className="font-medium text-slate-800 text-xs truncate max-w-[170px]" title={row.program?.nama}>
                            {row.program?.nama || '-'}
                          </div>
                          <span className={`inline-block px-2 py-0.5 rounded-full text-[10px] border mt-1 ${badge.className}`}>
                            {badge.label}
                          </span>
                        </td>

                        <td className="px-4 py-3 whitespace-nowrap">
                          <div className="font-medium text-slate-700 text-xs">
                            {row.isi_per_tube || '-'}
                          </div>
                          {row.output_yard ? (
                            <span className="inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200 mt-1">
                              📐 {row.output_yard.toLocaleString('id-ID')} yd
                            </span>
                          ) : null}
                        </td>

                        <td className="px-4 py-3 text-slate-600 text-[11px] whitespace-nowrap">
                          <div>Nozzle: <span className="font-mono text-slate-800">{row.nozzle_main_pump || '-'}</span></div>
                          <div>C60: <span className="font-mono text-slate-800">{row.cycle_60 || '-'}</span> | Puncak: <span className="font-mono text-slate-800">{row.cycle_puncak || '-'}</span></div>
                        </td>

                        <td className="px-4 py-3 whitespace-nowrap">
                          <div className="font-medium text-slate-700 text-xs">
                            {row.operator || '-'}
                          </div>
                          <div className="text-[11px] text-slate-400">
                            {formatDate(row.start_time_snapshot || row.created_at)}
                          </div>
                        </td>

                        <td className="px-4 py-3 text-right whitespace-nowrap">
                          <div className="flex items-center justify-end space-x-1" onClick={(e) => e.stopPropagation()}>
                            {/* Link ke /history/report/{id} */}
                            {row.dyeing_process_id ? (
                              <a
                                href={`/history/report/${row.dyeing_process_id}?machine=${encodeURIComponent(row.machine_code || '')}&batch=${encodeURIComponent(row.batch || '')}`}
                                target="_blank"
                                rel="noreferrer"
                                className="p-1.5 text-slate-500 hover:text-indigo-600 bg-slate-100 hover:bg-indigo-50 rounded-lg transition-colors flex items-center gap-1 text-xs font-semibold"
                                title="Lihat Laporan SCADA"
                              >
                                <Activity className="w-4 h-4 text-indigo-500" />
                                <span className="hidden xl:inline">SCADA</span>
                              </a>
                            ) : null}

                            <button
                              onClick={() => handleOpenEdit(row)}
                              className="p-1.5 text-indigo-600 hover:text-indigo-900 bg-indigo-50 hover:bg-indigo-100 rounded-lg transition-colors"
                              title="Edit Identitas"
                            >
                              <Edit2 className="w-3.5 h-3.5" />
                            </button>

                            <button
                              onClick={() => handleDelete(row.id)}
                              className="p-1.5 text-rose-600 hover:text-rose-900 bg-rose-50 hover:bg-rose-100 rounded-lg transition-colors"
                              title="Hapus"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>

          {/* Completed Pagination */}
          <div className="p-3 bg-slate-50 border-t border-slate-200 flex items-center justify-between text-xs">
            <div className="text-slate-500">
              Total <b>{totalCount}</b> identitas • Halaman <b>{page}</b> dari <b>{totalPages || 1}</b>
            </div>

            <div className="flex items-center space-x-2">
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page === 1}
                className={`p-1.5 rounded-lg border flex items-center justify-center transition-colors ${
                  page === 1 ? 'text-slate-300 border-slate-200 bg-slate-100' : 'text-slate-700 border-slate-300 bg-white hover:bg-slate-50'
                }`}
              >
                <ChevronLeft className="w-4 h-4" />
              </button>

              <span className="font-bold text-slate-700 px-2">
                {page} / {totalPages || 1}
              </span>

              <button
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                disabled={page === totalPages || totalPages === 0}
                className={`p-1.5 rounded-lg border flex items-center justify-center transition-colors ${
                  page === totalPages || totalPages === 0 ? 'text-slate-300 border-slate-200 bg-slate-100' : 'text-slate-700 border-slate-300 bg-white hover:bg-slate-50'
                }`}
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── WORKBENCH SLIDE-OVER DRAWER (FORM INPUT LENGKAP) ────────────── */}
      {isDrawerOpen && (
        <div className="fixed inset-0 z-50 overflow-hidden bg-slate-900/40 backdrop-blur-xs flex justify-end transition-opacity">
          <div className="w-full md:max-w-2xl bg-white h-full shadow-2xl flex flex-col transform transition-transform duration-300 ease-out border-l border-slate-200">
            
            {/* Drawer Header */}
            <div className="px-5 py-4 bg-slate-900 text-white flex items-center justify-between border-b border-slate-800">
              <div>
                <div className="flex items-center space-x-2">
                  <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-indigo-500 text-white uppercase tracking-wider">
                    {activeBatchContext ? 'Batch Celup Sensor' : currentId ? 'Edit Identitas' : 'Identitas Baru'}
                  </span>
                  {activeBatchContext && (
                    <span className="font-mono text-sm font-black text-rose-300">
                      {activeBatchContext.machine_code} (Batch Sensor #{activeBatchContext.batch_number})
                    </span>
                  )}
                </div>
                <h2 className="text-base sm:text-lg font-bold text-white mt-1">
                  {currentId ? 'Perbarui Identitas Kartu Proses' : 'Input Kartu Identitas Proses Celup'}
                </h2>
              </div>

              <button
                onClick={handleCloseDrawer}
                className="p-1.5 rounded-xl text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
                title="Tutup (ESC)"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Drawer Body Scrollable */}
            <div className="flex-1 overflow-y-auto p-5 space-y-5 bg-slate-50/50">

              {/* ── CARD TELEMETRI SENSOR DENGAN PREVIEW GRAFIK LANGSUNG ──── */}
              {activeBatchContext && (
                <div className="p-4 bg-white border border-indigo-200 rounded-2xl shadow-sm space-y-3">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="flex items-center space-x-2 text-xs font-bold text-indigo-900">
                        <Activity className="w-4 h-4 text-indigo-600 animate-pulse" />
                        <span>Telemetri Sensor Batch Terhubung</span>
                        <span className="font-mono text-indigo-600 bg-indigo-50 px-2 py-0.5 rounded-full text-[10px]">
                          {activeBatchContext.machine_code} #{activeBatchContext.batch_number}
                        </span>
                      </div>
                      <div className="text-xs text-slate-500 mt-0.5">
                        {formatDate(activeBatchContext.start_time)}
                        {activeBatchContext.end_time ? ` s/d ${formatDate(activeBatchContext.end_time)}` : ' (Sedang berjalan)'}
                        {actualTotal != null ? ` • Total Durasi: ${actualTotal} mnt` : ''}
                      </div>
                    </div>

                    {/* Tombol Buka SCADA ke 8000/history/report/{id} */}
                    <a
                      href={`/history/report/${activeBatchContext.id}?machine=${encodeURIComponent(activeBatchContext.machine_code || '')}&batch=${encodeURIComponent(activeBatchContext.batch_number || '')}`}
                      target="_blank"
                      rel="noreferrer"
                      className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-xs font-bold flex items-center gap-1.5 shadow-sm transition-colors whitespace-nowrap"
                    >
                      <span>Buka SCADA</span>
                      <ExternalLink className="w-3.5 h-3.5" />
                    </a>
                  </div>

                  {/* Preview Grafik Kurva Suhu Langsung */}
                  <div className="h-32 w-full bg-slate-50 rounded-xl p-1 relative border border-slate-100">
                    {telemetryLoading ? (
                      <div className="h-full flex items-center justify-center text-xs text-slate-400">
                        <RefreshCw className="w-4 h-4 animate-spin mr-1.5 text-indigo-600" />
                        Memuat kurva telemetri sensor...
                      </div>
                    ) : processTelemetry?.curve && processTelemetry.curve.length > 0 ? (
                      <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={processTelemetry.curve} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                          <defs>
                            <linearGradient id="colorTempIdent" x1="0" y1="0" x2="0" y2="1">
                              <stop offset="5%" stopColor="#6366f1" stopOpacity={0.4}/>
                              <stop offset="95%" stopColor="#6366f1" stopOpacity={0.0}/>
                            </linearGradient>
                          </defs>
                          <XAxis dataKey="time" tick={{ fontSize: 10, fill: '#64748b' }} tickLine={false} />
                          <YAxis domain={['auto', 'auto']} tick={{ fontSize: 10, fill: '#64748b' }} tickLine={false} unit="°" />
                          <Tooltip content={<SparklineTooltip />} />
                          <Area type="monotone" dataKey="temp" stroke="#4f46e5" strokeWidth={2} fillOpacity={1} fill="url(#colorTempIdent)" />
                        </AreaChart>
                      </ResponsiveContainer>
                    ) : (
                      <div className="h-full flex items-center justify-center text-xs text-slate-400">
                        Grafik menit telemetri tidak tersedia untuk batch ini.
                      </div>
                    )}
                  </div>

                  {/* 3 Titik Waktu Kunci dari Sensor */}
                  <div className="grid grid-cols-3 gap-2 pt-1 text-[11px]">
                    <div className="bg-slate-50 p-2 rounded-xl border border-slate-200/60 text-center">
                      <div className="text-slate-400 font-semibold text-[10px]">🔺 Mulai Naik (Heat)</div>
                      <div className="font-mono font-bold text-slate-800 text-xs mt-0.5">
                        {processTelemetry?.heating_start_time || '-'}
                      </div>
                    </div>
                    <div className="bg-slate-50 p-2 rounded-xl border border-slate-200/60 text-center">
                      <div className="text-slate-400 font-semibold text-[10px]">🔶 Puncak (Steady)</div>
                      <div className="font-mono font-bold text-rose-600 text-xs mt-0.5">
                        {processTelemetry?.steady_start_time || '-'}
                        {actualTemp != null && <span className="ml-1 text-[10px] font-normal">({actualTemp}°C)</span>}
                      </div>
                    </div>
                    <div className="bg-slate-50 p-2 rounded-xl border border-slate-200/60 text-center">
                      <div className="text-slate-400 font-semibold text-[10px]">🔻 Turun (&lt;70°C)</div>
                      <div className="font-mono font-bold text-sky-600 text-xs mt-0.5">
                        {processTelemetry?.reached_70c_time || '-'}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Fast-Action Toolbar: Copy from Previous Batch */}
              <div className="p-3 bg-amber-50/80 border border-amber-200 rounded-2xl flex items-center justify-between gap-2">
                <div className="flex items-center space-x-2 text-xs text-amber-800">
                  <Copy className="w-4 h-4 text-amber-600 flex-shrink-0" />
                  <span>Jalan artikel & program sama dengan batch sebelumnya?</span>
                </div>
                <button
                  type="button"
                  onClick={handleCopyPreviousBatch}
                  disabled={prefillLoading}
                  className="px-3 py-1.5 bg-amber-500 hover:bg-amber-600 text-white rounded-xl text-xs font-bold shadow-xs transition-all flex items-center gap-1.5 whitespace-nowrap flex-shrink-0"
                >
                  {prefillLoading ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Copy className="w-3.5 h-3.5" />}
                  <span>Salin Batch Sebelumnya</span>
                </button>
              </div>

              {/* Auto-Lookup Order Suggestion Card */}
              {orderLookupSuggestion && (
                <div className="p-3.5 bg-blue-50 border border-blue-200 rounded-2xl flex items-center justify-between gap-3 animate-in fade-in">
                  <div className="text-xs text-blue-900">
                    <div className="font-bold flex items-center gap-1">
                      <Sparkles className="w-3.5 h-3.5 text-blue-600" />
                      Ditemukan Order #{orderLookupSuggestion.nomor_order} di database:
                    </div>
                    <div className="text-[11px] text-blue-700 mt-0.5">
                      Artikel: <b>{orderLookupSuggestion.artikel_kain || '-'}</b> • Buyer: <b>{orderLookupSuggestion.kode_buyer || '-'}</b>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={handleApplyOrderLookup}
                    className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-xs font-bold whitespace-nowrap"
                  >
                    Terapkan
                  </button>
                </div>
              )}

              {/* Section 1: Alokasi & Program Celup */}
              <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-xs space-y-3">
                <div className="flex items-center space-x-2 text-xs font-bold text-slate-700 uppercase tracking-wider pb-2 border-b border-slate-100">
                  <span className="w-2 h-2 rounded-full bg-indigo-600"></span>
                  <span>1. Alokasi Mesin & Program Celup</span>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                  {/* Mesin */}
                  <div>
                    <label className="block font-bold text-slate-700 mb-1">
                      Mesin <span className="text-rose-500">*</span>
                    </label>
                    <select
                      name="machine_id"
                      value={formData.machine_id}
                      onChange={handleInputChange}
                      disabled={!!activeBatchContext} // Lock if initiated from a specific pending batch
                      className={`w-full border rounded-xl p-2 font-medium focus:ring-2 focus:ring-indigo-500 focus:outline-none ${
                        activeBatchContext ? 'bg-slate-100 border-slate-200 text-slate-500 cursor-not-allowed' : 'bg-white border-slate-300 text-slate-800'
                      }`}
                    >
                      <option value="">-- Pilih Mesin --</option>
                      {options.machines.map(m => (
                        <option key={m.id} value={m.id}>{m.code} - {m.name}</option>
                      ))}
                    </select>
                  </div>

                  {/* Jenis Proses */}
                  <div>
                    <label className="block font-bold text-slate-700 mb-1">
                      Jenis Proses <span className="text-rose-500">*</span>
                    </label>
                    <select
                      name="jenis_proses"
                      value={formData.jenis_proses}
                      onChange={handleInputChange}
                      className="w-full bg-white border border-slate-300 rounded-xl p-2 font-bold text-indigo-700 focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                    >
                      {options.jenis_proses.map(jp => (
                        <option key={jp.value} value={jp.value}>{jp.label}</option>
                      ))}
                    </select>
                  </div>

                  {/* Searchable Program Master Celup */}
                  <div className="sm:col-span-2 relative" ref={programDropdownRef}>
                    <div className="flex items-center justify-between mb-1">
                      <label className="font-bold text-slate-700">
                        Program Master Celup (Dapat Dicari)
                      </label>
                      {selectedProgram?.suhu_max != null && (
                        <span className="text-[11px] text-indigo-600 font-semibold font-mono">
                          Target: {selectedProgram.suhu_max}°C • Heat: {selectedProgram.durasi_heating_ideal || '-'}m
                        </span>
                      )}
                    </div>

                    {/* Trigger Box / Input */}
                    <div 
                      onClick={() => setIsProgramDropdownOpen(true)}
                      className="w-full bg-white border border-slate-300 hover:border-indigo-400 rounded-xl p-2 font-medium text-slate-800 flex items-center justify-between cursor-pointer focus-within:ring-2 focus-within:ring-indigo-500 focus-within:border-indigo-500"
                    >
                      <div className="flex items-center gap-2 flex-1 min-w-0">
                        <Search className="w-4 h-4 text-slate-400 shrink-0" />
                        <input
                          type="text"
                          placeholder={selectedProgram ? selectedProgram.nama : "Ketik untuk mencari program celup..."}
                          value={programSearchText}
                          onChange={(e) => {
                            setProgramSearchText(e.target.value);
                            setIsProgramDropdownOpen(true);
                          }}
                          onFocus={() => setIsProgramDropdownOpen(true)}
                          className="w-full text-xs font-semibold text-slate-800 placeholder-slate-400 bg-transparent focus:outline-none"
                        />
                      </div>

                      <div className="flex items-center gap-1 shrink-0 ml-2">
                        {formData.program_id && (
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              setFormData(prev => ({ ...prev, program_id: '' }));
                              setProgramSearchText('');
                            }}
                            className="p-1 hover:bg-slate-100 rounded-lg text-slate-400 hover:text-slate-600"
                            title="Hapus pilihan"
                          >
                            <X className="w-3.5 h-3.5" />
                          </button>
                        )}
                        <ChevronDown className="w-4 h-4 text-slate-400" />
                      </div>
                    </div>

                    {/* Dropdown Menu Popover */}
                    {isProgramDropdownOpen && (
                      <div className="absolute z-30 left-0 right-0 mt-1 bg-white border border-slate-200 rounded-2xl shadow-xl max-h-60 overflow-y-auto p-1.5 animate-in fade-in">
                        {filteredPrograms.length === 0 ? (
                          <div className="p-3 text-center text-xs text-slate-400">
                            Tidak ada program yang cocok dengan pencarian "{programSearchText}".
                          </div>
                        ) : (
                          filteredPrograms.map((prog) => {
                            const isSelected = formData.program_id === prog.id;
                            const isTempMatched = actualTemp != null && prog.suhu_max != null && Math.abs(prog.suhu_max - actualTemp) <= 5;
                            return (
                              <div
                                key={prog.id}
                                onClick={() => {
                                  setFormData(prev => ({ ...prev, program_id: prog.id }));
                                  setProgramSearchText('');
                                  setIsProgramDropdownOpen(false);
                                }}
                                className={`p-2.5 rounded-xl cursor-pointer transition-colors flex items-center justify-between text-xs ${
                                  isSelected ? 'bg-indigo-50 border border-indigo-200 text-indigo-900 font-bold' : 'hover:bg-slate-50 text-slate-700'
                                }`}
                              >
                                <div>
                                  <div className="font-bold text-slate-800 text-xs flex items-center gap-1.5">
                                    <span>{prog.nama}</span>
                                    {isTempMatched && (
                                      <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-300">
                                        🎯 Cocok Suhu ({prog.suhu_max}°C)
                                      </span>
                                    )}
                                  </div>
                                  <div className="text-[10px] text-slate-400 mt-0.5 font-mono">
                                    Suhu: <b>{prog.suhu_max || '-'}°C</b> • Heat: <b>{prog.durasi_heating_ideal || '-'}m</b> • Keep: <b>{prog.durasi_keeping_ideal || '-'}m</b> • Total: <b>{prog.durasi_ideal || '-'}m</b>
                                  </div>
                                </div>

                                {isSelected && (
                                  <Check className="w-4 h-4 text-indigo-600 shrink-0 ml-2" />
                                )}
                              </div>
                            );
                          })
                        )}
                      </div>
                    )}

                    {/* ── SHOW NOTES: KOMPARASI PROGRAM VS SENSOR AKTUAL ── */}
                    {selectedProgram && (
                      <div className="mt-3 p-3.5 bg-slate-50 border border-slate-200 rounded-2xl space-y-2.5">
                        <div className="flex items-center justify-between">
                          <div className="text-xs font-bold text-slate-800 flex items-center gap-1.5">
                            <span>⚖️ Show Notes: Komparasi Program vs Sensor Aktual</span>
                          </div>
                          <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-indigo-100 text-indigo-700">
                            {selectedProgram.nama}
                          </span>
                        </div>

                        {/* Peringatan Ketidaksesuaian Suhu (Early Warning) */}
                        {actualTemp != null && selectedProgram.suhu_max != null && Math.abs(actualTemp - selectedProgram.suhu_max) > 8 && (
                          <div className="p-2.5 bg-rose-50 border border-rose-300 rounded-xl text-xs text-rose-800 flex items-start gap-2">
                            <AlertTriangle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
                            <div>
                              <span className="font-bold">Peringatan Ketidaksesuaian Suhu:</span> Suhu Program (<b>{selectedProgram.suhu_max}°C</b>) terpaut jauh (<b>{Math.abs(actualTemp - selectedProgram.suhu_max).toFixed(1)}°C</b>) dari Suhu Puncak Aktual Mesin (<b>{actualTemp}°C</b>). Pastikan kartu proses dan program yang dipilih sudah benar!
                            </div>
                          </div>
                        )}

                        {/* Catatan Ketidaksesuaian Heating Duration */}
                        {actualHeat != null && selectedProgram.durasi_heating_ideal != null && Math.abs(actualHeat - selectedProgram.durasi_heating_ideal) > 15 && (
                          <div className="p-2 bg-amber-50 border border-amber-300 rounded-xl text-xs text-amber-800 flex items-start gap-2">
                            <Info className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
                            <div>
                              <span className="font-bold">Catatan Waktu Heating:</span> Waktu Heating aktual (<b>{actualHeat} mnt</b>) terpaut <b>{Math.abs(actualHeat - selectedProgram.durasi_heating_ideal).toFixed(1)} mnt</b> dari standar program (<b>{selectedProgram.durasi_heating_ideal} mnt</b>).
                            </div>
                          </div>
                        )}

                        {/* Tabel Komparasi Detail */}
                        <div className="overflow-x-auto">
                          <table className="w-full text-left text-xs">
                            <thead>
                              <tr className="border-b border-slate-200 text-slate-400 font-bold uppercase text-[10px]">
                                <th className="py-1">Parameter</th>
                                <th className="py-1 text-center">Standar Program</th>
                                <th className="py-1 text-center">Aktual Sensor</th>
                                <th className="py-1 text-right">Selisih (Δ)</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100">
                              <tr>
                                <td className="py-1.5 font-semibold text-slate-700">🌡️ Suhu Puncak</td>
                                <td className="py-1.5 text-center font-mono">{selectedProgram.suhu_max != null ? `${selectedProgram.suhu_max}°C` : '-'}</td>
                                <td className="py-1.5 text-center font-mono font-bold text-slate-900">{actualTemp != null ? `${actualTemp}°C` : '-'}</td>
                                <td className="py-1.5 text-right font-mono font-bold">
                                  {deltaTemp != null ? (
                                    <span className={`px-1.5 py-0.5 rounded text-[11px] ${
                                      Math.abs(deltaTemp) <= 3 ? 'bg-emerald-100 text-emerald-800' :
                                      Math.abs(deltaTemp) <= 8 ? 'bg-amber-100 text-amber-800' : 'bg-rose-100 text-rose-800'
                                    }`}>
                                      {deltaTemp > 0 ? `+${deltaTemp.toFixed(1)}` : deltaTemp.toFixed(1)}°C
                                    </span>
                                  ) : '-'}
                                </td>
                              </tr>
                              <tr>
                                <td className="py-1.5 font-semibold text-slate-700">🔥 Waktu Heating</td>
                                <td className="py-1.5 text-center font-mono">{selectedProgram.durasi_heating_ideal != null ? `${selectedProgram.durasi_heating_ideal} mnt` : '-'}</td>
                                <td className="py-1.5 text-center font-mono font-bold text-slate-900">{actualHeat != null ? `${actualHeat} mnt` : '-'}</td>
                                <td className="py-1.5 text-right font-mono font-bold">
                                  {deltaHeat != null ? (
                                    <span className={`px-1.5 py-0.5 rounded text-[11px] ${
                                      Math.abs(deltaHeat) <= 5 ? 'bg-emerald-100 text-emerald-800' :
                                      Math.abs(deltaHeat) <= 15 ? 'bg-amber-100 text-amber-800' : 'bg-rose-100 text-rose-800'
                                    }`}>
                                      {deltaHeat > 0 ? `+${deltaHeat.toFixed(1)}` : deltaHeat.toFixed(1)} mnt
                                    </span>
                                  ) : '-'}
                                </td>
                              </tr>
                              <tr>
                                <td className="py-1.5 font-semibold text-slate-700">⏱️ Waktu Keeping</td>
                                <td className="py-1.5 text-center font-mono">{selectedProgram.durasi_keeping_ideal != null ? `${selectedProgram.durasi_keeping_ideal} mnt` : '-'}</td>
                                <td className="py-1.5 text-center font-mono text-slate-800">{actualSteady != null ? `${actualSteady} mnt` : '-'}</td>
                                <td className="py-1.5 text-right font-mono">
                                  {deltaSteady != null ? (
                                    <span className="text-slate-600">{deltaSteady > 0 ? `+${deltaSteady.toFixed(1)}` : deltaSteady.toFixed(1)} mnt</span>
                                  ) : '-'}
                                </td>
                              </tr>
                              <tr>
                                <td className="py-1.5 font-semibold text-slate-700">⏳ Total Durasi</td>
                                <td className="py-1.5 text-center font-mono">{selectedProgram.durasi_ideal != null ? `${selectedProgram.durasi_ideal} mnt` : '-'}</td>
                                <td className="py-1.5 text-center font-mono text-slate-800">{actualTotal != null ? `${actualTotal} mnt` : '-'}</td>
                                <td className="py-1.5 text-right font-mono">
                                  {deltaTotal != null ? (
                                    <span className="text-slate-600">{deltaTotal > 0 ? `+${deltaTotal.toFixed(1)}` : deltaTotal.toFixed(1)} mnt</span>
                                  ) : '-'}
                                </td>
                              </tr>
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Operator */}
                  <div className="sm:col-span-2">
                    <label className="block font-bold text-slate-700 mb-1">
                      Operator Bertugas
                    </label>
                    <input
                      type="text"
                      name="operator"
                      value={formData.operator}
                      onChange={handleInputChange}
                      placeholder="Nama operator pelaksana..."
                      className="w-full bg-white border border-slate-300 rounded-xl p-2 text-slate-800 focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                    />
                  </div>
                </div>
              </div>

              {/* Section 2: Identitas Pesanan & Kain */}
              <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-xs space-y-3">
                <div className="flex items-center space-x-2 text-xs font-bold text-slate-700 uppercase tracking-wider pb-2 border-b border-slate-100">
                  <span className="w-2 h-2 rounded-full bg-emerald-600"></span>
                  <span>2. Identitas Pesanan & Kain</span>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                  {/* Nomor Order */}
                  <div>
                    <label className="block font-bold text-slate-700 mb-1">
                      Nomor Order (PO) <span className="text-rose-500">*</span>
                    </label>
                    <div className="relative">
                      <input
                        type="text"
                        name="nomor_order"
                        value={formData.nomor_order}
                        onChange={handleInputChange}
                        onBlur={(e) => handleOrderLookup(e.target.value)}
                        placeholder="Misal: 61016-14..."
                        className="w-full bg-white border border-slate-300 rounded-xl p-2 text-slate-900 font-bold focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                      />
                      <button
                        type="button"
                        onClick={() => handleOrderLookup(formData.nomor_order)}
                        className="absolute right-2 top-2 text-slate-400 hover:text-indigo-600"
                        title="Cari riwayat order"
                      >
                        <Search className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>

                  {/* Nomor Batch Kain (Terpisah dari No. Batch Sensor) */}
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <label className="font-bold text-slate-700">
                        Nomor Batch Kain <span className="text-rose-500">*</span>
                      </label>
                      {activeBatchContext && (
                        <span className="text-[10px] text-slate-400 font-mono">
                          (Sensor: #{activeBatchContext.batch_number})
                        </span>
                      )}
                    </div>
                    <input
                      type="text"
                      name="batch"
                      value={formData.batch}
                      onChange={handleInputChange}
                      placeholder="Misal: B-01, 1A, atau nomor lot..."
                      className="w-full bg-white border border-slate-300 rounded-xl p-2 font-mono text-slate-900 font-semibold focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                    />
                    <p className="text-[10px] text-slate-400 mt-0.5">
                      Diisi nomor batch fisik kain (bukan nomor urut proses sensor)
                    </p>
                  </div>

                  {/* Artikel Kain */}
                  <div className="sm:col-span-2">
                    <label className="block font-bold text-slate-700 mb-1">
                      Nama Artikel Kain <span className="text-rose-500">*</span>
                    </label>
                    <input
                      type="text"
                      name="artikel_kain"
                      value={formData.artikel_kain}
                      onChange={handleInputChange}
                      placeholder="Misal: Hokaido, Rayon Twill, GE 0001..."
                      className="w-full bg-white border border-slate-300 rounded-xl p-2 text-slate-900 font-semibold focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                    />
                  </div>

                  {/* Kode Buyer */}
                  <div>
                    <label className="block font-bold text-slate-700 mb-1">
                      Kode Buyer
                    </label>
                    <input
                      type="text"
                      name="kode_buyer"
                      value={formData.kode_buyer}
                      onChange={handleInputChange}
                      placeholder="Misal: M&S, ZARA, UNQLO..."
                      className="w-full bg-white border border-slate-300 rounded-xl p-2 text-slate-800 focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                    />
                  </div>

                  {/* Nomor Warna */}
                  <div>
                    <label className="block font-bold text-slate-700 mb-1">
                      Nomor Warna
                    </label>
                    <input
                      type="text"
                      name="nomor_warna"
                      value={formData.nomor_warna}
                      onChange={handleInputChange}
                      placeholder="Misal: Navy 04, Black..."
                      className="w-full bg-white border border-slate-300 rounded-xl p-2 text-slate-800 focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                    />
                  </div>

                  {/* Nomor Desain */}
                  <div className="sm:col-span-2">
                    <label className="block font-bold text-slate-700 mb-1">
                      Nomor Desain
                    </label>
                    <input
                      type="text"
                      name="nomor_desain"
                      value={formData.nomor_desain}
                      onChange={handleInputChange}
                      placeholder="Misal: DSN-4820..."
                      className="w-full bg-white border border-slate-300 rounded-xl p-2 text-slate-800 focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                    />
                  </div>
                </div>
              </div>

              {/* Section 3: Setting Parameter Mesin & Kapasitas */}
              <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-xs space-y-3">
                <div className="flex items-center space-x-2 text-xs font-bold text-slate-700 uppercase tracking-wider pb-2 border-b border-slate-100">
                  <span className="w-2 h-2 rounded-full bg-amber-500"></span>
                  <span>3. Setting Parameter Mesin & Kapasitas</span>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                  {/* Isi per Tube with Live Yard Badge */}
                  <div className="sm:col-span-2">
                    <div className="flex items-center justify-between mb-1">
                      <label className="font-bold text-slate-700">
                        Isi per Tube
                      </label>
                      {liveYard !== null ? (
                        <span className="px-2 py-0.5 rounded-lg font-bold text-[11px] bg-emerald-100 text-emerald-800 border border-emerald-300 flex items-center gap-1 animate-in fade-in">
                          <Check className="w-3 h-3 text-emerald-600" />
                          Estimasi Output: {liveYard.toLocaleString('id-ID')} Yard
                        </span>
                      ) : (
                        <span className="text-[11px] text-slate-400">
                          Contoh: <b>6 Roll</b>, <b>10 PCS (2X)</b>, <b>300 M</b>
                        </span>
                      )}
                    </div>
                    <input
                      type="text"
                      name="isi_per_tube"
                      value={formData.isi_per_tube}
                      onChange={handleInputChange}
                      placeholder="Misal: 6 Roll atau 10 PCS (2X) / 8 PCS (2X)..."
                      className="w-full bg-white border border-slate-300 rounded-xl p-2 text-slate-800 focus:ring-2 focus:ring-indigo-500 focus:outline-none font-mono font-medium"
                    />
                  </div>

                  {/* Nozzle / Main Pump */}
                  <div>
                    <label className="block font-bold text-slate-700 mb-1">
                      Nozzle / Main Pump
                    </label>
                    <input
                      type="text"
                      name="nozzle_main_pump"
                      value={formData.nozzle_main_pump}
                      onChange={handleInputChange}
                      placeholder="Misal: 65 / 1.2 bar..."
                      className="w-full bg-white border border-slate-300 rounded-xl p-2 text-slate-800 focus:ring-2 focus:ring-indigo-500 focus:outline-none font-mono"
                    />
                  </div>

                  {/* Cycle 60 */}
                  <div>
                    <label className="block font-bold text-slate-700 mb-1">
                      Cycle 60°C
                    </label>
                    <input
                      type="text"
                      name="cycle_60"
                      value={formData.cycle_60}
                      onChange={handleInputChange}
                      placeholder="Misal: 90s..."
                      className="w-full bg-white border border-slate-300 rounded-xl p-2 text-slate-800 focus:ring-2 focus:ring-indigo-500 focus:outline-none font-mono"
                    />
                  </div>

                  {/* Cycle Puncak */}
                  <div className="sm:col-span-2">
                    <label className="block font-bold text-slate-700 mb-1">
                      Cycle Puncak
                    </label>
                    <input
                      type="text"
                      name="cycle_puncak"
                      value={formData.cycle_puncak}
                      onChange={handleInputChange}
                      placeholder="Misal: 85s..."
                      className="w-full bg-white border border-slate-300 rounded-xl p-2 text-slate-800 focus:ring-2 focus:ring-indigo-500 focus:outline-none font-mono"
                    />
                  </div>
                </div>
              </div>

              {/* Section 4: Kualitas & Catatan Operasional */}
              <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-xs space-y-3">
                <div className="flex items-center space-x-2 text-xs font-bold text-slate-700 uppercase tracking-wider pb-2 border-b border-slate-100">
                  <span className="w-2 h-2 rounded-full bg-sky-500"></span>
                  <span>4. Kontrol Kualitas & Catatan Masalah</span>
                </div>

                <div className="space-y-3 text-xs">
                  {/* Handling Quality */}
                  <div>
                    <label className="block font-bold text-slate-700 mb-1">
                      Handling Quality
                    </label>
                    <textarea
                      name="handling_quality"
                      value={formData.handling_quality}
                      onChange={handleInputChange}
                      rows="2"
                      placeholder="Catatan penanganan kain, kelembutan, dsb..."
                      className="w-full bg-white border border-slate-300 rounded-xl p-2 text-slate-800 focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                    ></textarea>
                  </div>

                  {/* Masalah / Kendala */}
                  <div>
                    <label className="block font-bold text-slate-700 mb-1 text-rose-700">
                      Masalah / Kendala Celup (Opsional)
                    </label>
                    <textarea
                      name="masalah"
                      value={formData.masalah}
                      onChange={handleInputChange}
                      rows="2"
                      placeholder="Catatan kendala teknis, belang, flek, stop mesin, dll..."
                      className="w-full bg-rose-50/40 border border-rose-200 rounded-xl p-2 text-slate-800 focus:ring-2 focus:ring-rose-500 focus:outline-none"
                    ></textarea>
                  </div>

                  {/* Keterangan */}
                  <div>
                    <label className="block font-bold text-slate-700 mb-1">
                      Keterangan Tambahan (Opsional)
                    </label>
                    <textarea
                      name="keterangan"
                      value={formData.keterangan}
                      onChange={handleInputChange}
                      rows="2"
                      placeholder="Catatan umum bebas..."
                      className="w-full bg-white border border-slate-300 rounded-xl p-2 text-slate-800 focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                    ></textarea>
                  </div>
                </div>
              </div>

            </div>

            {/* Drawer Footer Actions */}
            <div className="p-4 bg-white border-t border-slate-200 flex items-center justify-between gap-3">
              <button
                type="button"
                onClick={handleCloseDrawer}
                className="px-4 py-2 border border-slate-300 text-slate-700 hover:bg-slate-50 rounded-xl text-xs font-bold transition-colors"
              >
                Batal
              </button>

              <div className="flex items-center space-x-2">
                {activeTab === 'pending' && activeBatchContext && (
                  <button
                    type="button"
                    onClick={() => handleSave(true)}
                    disabled={isSubmitting}
                    className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-xs font-bold shadow-sm transition-all flex items-center gap-1.5"
                    title="Simpan kartu ini dan langsung buka kartu batch berikutnya di antrean"
                  >
                    {isSubmitting ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <ArrowRight className="w-3.5 h-3.5" />}
                    <span>Simpan & Buka Berikutnya</span>
                  </button>
                )}

                <button
                  type="button"
                  onClick={() => handleSave(false)}
                  disabled={isSubmitting}
                  className="px-5 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-xs font-bold shadow-sm transition-all flex items-center gap-1.5"
                >
                  {isSubmitting ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                  <span>Simpan</span>
                </button>
              </div>
            </div>

          </div>
        </div>
      )}

    </div>
  );
};

export default DyeingIdentities;
