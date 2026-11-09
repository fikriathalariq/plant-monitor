import React, { useState, useEffect } from 'react';
import { driver } from 'driver.js';
import 'driver.js/dist/driver.css';
import { useParams, useNavigate } from 'react-router-dom';
import api, { BACKEND_BASE_URL } from '../lib/api';
import {
  ArrowLeft, Printer, RefreshCw, AlertCircle, Flame, PauseCircle, Snowflake,
  Clock, Target, TrendingUp, Timer, Zap, DollarSign, Activity, CheckCircle2,
  AlertTriangle, Wrench, Gauge, BarChart3, UserCheck, ExternalLink, Layers, X, Calendar, FileText,
  HelpCircle, Compass, Droplets, ChevronRight, SlidersHorizontal, Eye, ChevronDown, Check, Info
} from 'lucide-react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip,
  ResponsiveContainer, Legend, ComposedChart, Bar, Area, ReferenceLine, Cell
} from 'recharts';
import { ProcessStatusIcon, ProcessStatusBadge } from '../components/ProcessStatusIcon';
import { ShareToChatButton } from '../components/chat/ShareToChatButton';

const formatBackendDate = (dateStr) => {
  if (!dateStr || dateStr === '-' || dateStr === 'In Progress') return dateStr;
  const months = {
    Jan: '01', Feb: '02', Mar: '03', Apr: '04', May: '05', Jun: '06',
    Jul: '07', Aug: '08', Sep: '09', Oct: '10', Nov: '11', Dec: '12',
  };
  try {
    const parts = dateStr.replace(',', '').split(' ');
    if (parts.length === 4) {
      return `${parts[0].padStart(2, '0')}/${months[parts[1]] || '00'}/${parts[2]} ${parts[3]}`;
    }
    return dateStr;
  } catch {
    return dateStr;
  }
};

const rp = (val) => (val != null && !isNaN(val) ? `Rp ${Math.round(Number(val)).toLocaleString('id-ID')}` : '-');
const numFmt = (val, dec = 1) => (val != null && !isNaN(val) ? Number(val).toLocaleString('id-ID', { maximumFractionDigits: dec }) : '-');

const TONE_BOX = {
  emerald: 'bg-emerald-50/90 border-emerald-200 text-emerald-900',
  amber: 'bg-amber-50/90 border-amber-200 text-amber-900',
  red: 'bg-rose-50/90 border-rose-200 text-rose-900',
};

const TONE_BADGE = {
  emerald: 'bg-emerald-600 text-white',
  amber: 'bg-amber-500 text-white',
  red: 'bg-rose-600 text-white',
};

const SEVERITY_STYLE = {
  CRITICAL: {
    box: 'bg-rose-50/80 border-rose-200',
    badge: 'bg-rose-600 text-white',
    title: 'text-rose-900',
  },
  WARNING: {
    box: 'bg-amber-50/80 border-amber-200',
    badge: 'bg-amber-500 text-white',
    title: 'text-amber-900',
  },
  MEDIUM: {
    box: 'bg-amber-50/80 border-amber-200',
    badge: 'bg-amber-500 text-white',
    title: 'text-amber-900',
  },
  LOW: {
    box: 'bg-sky-50/80 border-sky-200',
    badge: 'bg-sky-600 text-white',
    title: 'text-sky-900',
  },
  INFO: {
    box: 'bg-slate-50 border-slate-200',
    badge: 'bg-slate-600 text-white',
    title: 'text-slate-800',
  },
  OK: {
    box: 'bg-emerald-50/80 border-emerald-200',
    badge: 'bg-emerald-600 text-white',
    title: 'text-emerald-900',
  },
};

const TOUR_STORAGE_KEY = 'plant_monitor_tour_process_report_v1';

const ProcessReport = () => {
  const { process_id } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [inspectorBatch, setInspectorBatch] = useState(null);
  const [showWelcomeTourBanner, setShowWelcomeTourBanner] = useState(false);
  const [activeMobileTab, setActiveMobileTab] = useState('summary');

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        setInspectorBatch(null);
      }
    };
    if (inspectorBatch) {
      window.addEventListener('keydown', handleKeyDown);
    }
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [inspectorBatch]);

  const getAdminAddUrl = () => {
    if (!data?.id) return `${BACKEND_BASE_URL}/admin/monitoring/dyeingidentity/add/`;
    const params = new URLSearchParams();
    params.set('dyeing_process', String(data.id));
    if (data.machine_id) params.set('machine', String(data.machine_id));
    if (data.start_time_iso) params.set('start_time_snapshot', data.start_time_iso);
    return `${BACKEND_BASE_URL}/admin/monitoring/dyeingidentity/add/?${params.toString()}`;
  };

  const handleBack = () => {
    if (window.history.state && typeof window.history.state.idx === 'number' && window.history.state.idx > 0) {
      navigate(-1);
    } else {
      navigate('/history');
    }
  };

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const searchParams = new URLSearchParams(window.location.search);
      const machineParam = searchParams.get('machine');
      const batchParam = searchParams.get('batch');

      let url = `/report/process/${process_id}/analytics`;
      const queryParts = [];
      if (machineParam) queryParts.push(`machine=${encodeURIComponent(machineParam)}`);
      if (batchParam) queryParts.push(`batch=${encodeURIComponent(batchParam)}`);
      if (queryParts.length > 0) {
        url += `?${queryParts.join('&')}`;
      }

      const res = await api.get(url);
      setData(res.data);

      // Sinkronkan URL address bar ke ID dan query param kanonikal (tahan reprocess)
      if (res.data?.id) {
        const canonicalBatch = res.data.identity?.batch_number || res.data.batch_number || '';
        const canonicalMachine = res.data.machine_code || '';
        const newSearch = canonicalBatch || canonicalMachine
          ? `?machine=${encodeURIComponent(canonicalMachine)}&batch=${encodeURIComponent(canonicalBatch)}`
          : window.location.search;
        if (String(res.data.id) !== String(process_id) || !window.location.search) {
          window.history.replaceState(null, '', `/history/report/${res.data.id}${newSearch}`);
        }
      }
    } catch (err) {
      console.error(err);
      const serverMsg = err.response?.data?.detail || err.response?.data?.message;
      setError(serverMsg || 'Gagal memuat laporan audit proses.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [process_id]);

  useEffect(() => {
    const setupPrint = () => {
      if (!document.getElementById('process-report-print-page')) {
        const pageStyle = document.createElement('style');
        pageStyle.id = 'process-report-print-page';
        pageStyle.textContent = '@page { size: A4 landscape; margin: 6mm; }';
        document.head.appendChild(pageStyle);
      }
      document.documentElement.classList.add('printing-process-report');
      document.body.classList.add('printing-process-report');
    };

    const cleanupPrint = () => {
      document.documentElement.classList.remove('printing-process-report');
      document.body.classList.remove('printing-process-report');
      document.getElementById('process-report-print-page')?.remove();
    };

    window.addEventListener('beforeprint', setupPrint);
    window.addEventListener('afterprint', cleanupPrint);

    return () => {
      window.removeEventListener('beforeprint', setupPrint);
      window.removeEventListener('afterprint', cleanupPrint);
      cleanupPrint();
    };
  }, []);

  // ── ONBOARDING PRODUCT TOUR LOGIC ──────────────────────────────────────
  useEffect(() => {
    if (!loading && data && !error) {
      const hasSeenTour = localStorage.getItem(TOUR_STORAGE_KEY);
      if (!hasSeenTour) {
        // Tampilkan tawaran tur halus setelah render halaman stabil
        const timer = setTimeout(() => {
          setShowWelcomeTourBanner(true);
        }, 800);
        return () => clearTimeout(timer);
      }
    }
  }, [loading, data, error]);

  const handleStartTour = () => {
    setActiveMobileTab('all');
    setShowWelcomeTourBanner(false);
    const isMobile = window.innerWidth < 768;

    // Tambahkan class agar ada padding bawah 60vh sehingga bagian paling bawah dapat di-scroll ke tengah layar
    document.body.classList.add('driver-tour-active');

    // Fungsi centering elemen aktif ke tengah viewport secara mulus
    const scrollToCenterElement = (element) => {
      if (!element) return;
      const rect = element.getBoundingClientRect();
      const windowHeight = window.innerHeight;
      const elemHeight = rect.height;
      const currentScrollY = window.scrollY || document.documentElement.scrollTop;

      let targetScrollY;
      if (elemHeight <= windowHeight * 0.65) {
        // Elemen tidak terlalu tinggi: tempatkan pusat vertikalnya sedikit di atas tengah layar (42%)
        // agar ada ruang leluasa untuk popover di bawahnya
        const elementCenter = rect.top + elemHeight / 2;
        const targetCenter = windowHeight * 0.42;
        targetScrollY = currentScrollY + (elementCenter - targetCenter);
      } else {
        // Elemen tinggi (seperti multi-card grid di mobile): sejajarkan bagian atasnya dengan margin yang nyaman
        const targetTop = isMobile ? 55 : 80;
        targetScrollY = currentScrollY + (rect.top - targetTop);
      }

      const maxScrollY = document.documentElement.scrollHeight - windowHeight;
      targetScrollY = Math.max(0, Math.min(targetScrollY, maxScrollY));

      if (Math.abs(targetScrollY - currentScrollY) > 8) {
        window.scrollTo({
          top: targetScrollY,
          behavior: 'smooth',
        });
      }
    };

    // Fungsi memastikan popover tidak terpotong tepi atas atau bawah
    const ensurePopoverVisible = () => {
      setTimeout(() => {
        const popover = document.querySelector('.driver-popover');
        if (!popover) return;
        const popRect = popover.getBoundingClientRect();
        const windowHeight = window.innerHeight;

        let deltaY = 0;
        if (popRect.top < 16) {
          deltaY = popRect.top - 24;
        } else if (popRect.bottom > windowHeight - 16) {
          deltaY = popRect.bottom - (windowHeight - 24);
        }

        if (Math.abs(deltaY) > 6) {
          window.scrollBy({
            top: deltaY,
            behavior: 'smooth',
          });
        }
      }, 120);
    };

    const cleanupTour = () => {
      document.body.classList.remove('driver-tour-active');
      localStorage.setItem(TOUR_STORAGE_KEY, 'true');
    };

    // Daftar kandidat seluruh bagian fitur potensial yang bisa disorot
    const candidateSteps = [
      {
        element: '.print-report-header',
        icon: '🧭',
        title: 'Navigasi & Aksi Laporan',
        description: 'Di bagian atas ini tertera identitas mesin, nomor batch, dan status akhir proses. Gunakan tombol "Koreksi di Admin" jika ingin mengoreksi data kain di Django Admin, "Grafik Mesin (24 Jam)" untuk melihat rekap 24 jam mesin ini, atau "Cetak Laporan" untuk mengunduh laporan PDF resmi siap rapat.',
        side: 'bottom',
        align: isMobile ? 'center' : 'start',
      },
      {
        element: '.print-kpi-grid',
        icon: '📊',
        title: 'Enam Kartu Indikator Kunci (KPI)',
        description: 'Ringkasan instan performa batch: memantau durasi efektif aktual vs resep ideal, persentase tekanan uap sehat (≥ 3.8 bar), nominal total kerugian energi rupiah, dan potensi penghematan bulanan/tahunan jika mesin dioptimasi.',
        side: 'bottom',
        align: 'center',
      },
      {
        element: '.print-3col-grid',
        icon: '💰',
        title: 'Audit Biaya & Akar Sumber Kerugian (PINN)',
        description: 'Sistem membedah kerugian menjadi 4 akar penyebab: degradasi fisik mesin (kerak HE), penurunan pasokan tekanan boiler, over-holding operator, dan penalti tarif listrik WBP (17:00–22:00 WIB). Dilengkapi audit 3-lapis uap & listrik.',
        side: 'bottom',
        align: 'center',
      },
      {
        element: '.print-bench-left',
        icon: '🎯',
        title: 'Audit Normalitas vs Resep Standar',
        description: 'Tabel komparasi otomatis yang membandingkan durasi heating, holding, dan cooling batch ini terhadap rata-rata historis mesin ini dan standar resep ideal program. Evaluasi di atas tabel langsung menyimpulkan performa sistem termal mesin.',
        side: isMobile ? 'bottom' : 'right',
        align: isMobile ? 'center' : 'start',
      },
      {
        element: '.print-bench-right',
        icon: '💡',
        title: 'Grafik Riwayat & Quick Audit Inspector (Bisa Diklik!)',
        description: 'Memplot tren durasi heating (merah) dan cooling (biru) terhadap tekanan uap (garis ungu). FITUR KHUSUS: Klik pada batang atau titik ungu mana pun pada grafik ini untuk membuka jendela audit dan melompat ke laporan batch tersebut!',
        side: isMobile ? 'bottom' : 'left',
        align: isMobile ? 'center' : 'start',
      },
      {
        element: '.print-bench-empty-card',
        icon: '🎯',
        title: 'Komparasi Historis Program Resep',
        description: 'Area komparasi performa historis mesin vs resep ideal. Pada batch ini, kartu proses belum ditautkan ke Master Resep sehingga data komparasi heating/cooling akan muncul otomatis setelah resep dilengkapi.',
        side: 'bottom',
        align: 'center',
      },
      {
        element: '.print-boiler-section',
        icon: '🏭',
        title: 'Korelasi Beban Pabrik vs Respons Boiler',
        description: 'Menjawab pertanyaan krusial saat uap drop: apakah karena boiler lambat merespons batu bara, atau karena lonjakan pemakaian uap serentak di pabrik? Terdiri dari grafik beban uap (kg/jam) dan speed batu bara (Hz).',
        side: 'top',
        align: 'center',
      },
      {
        element: '.print-cooling-section',
        icon: '❄️',
        title: 'Diagnostik Laju Cooling vs Mesin Cooling Bersamaan',
        description: 'Menganalisis anomali pendinginan: apakah mesin lambat dingin karena kendala fisik penukar panas (kerak HE / katup), atau karena lonjakan mesin lain yang cooling bersamaan sehingga debit air pendingin pabrik terbagi.',
        side: 'top',
        align: 'center',
      },
      {
        element: '.print-forensics-section',
        icon: '🕵️',
        title: 'Forensik Anomali & Kedisiplinan Operator',
        description: 'Mendeteksi otomatis waktu tunggu bongkar kain melebihi standar toleransi (≤ 45 menit), penahanan kain berlebih, atau anomali kurva. Dilengkapi nama operator, taksiran kerugian rupiah, dan rekomendasi tindak lanjut.',
        side: 'top',
        align: 'center',
      },
      {
        element: '.process-report-grid',
        icon: '📈',
        title: 'Kurva Suhu Aktual (°C) vs Tekanan & Identitas Kain',
        description: 'Identitas lengkap kain (Order, Buyer, Artikel, Output Yard) berdampingan dengan kurva dinamis suhu aktual mesin (°C) vs tekanan uap (bar). Anda dapat mengarahkan kursor (hover) pada grafik untuk melihat pembacaan per menit.',
        side: 'top',
        align: 'center',
      },
    ];

    // Filter dinamis: hanya sertakan langkah yang elemen fisiknya BENAR-BENAR ADA di halaman saat ini
    const activeSteps = candidateSteps
      .filter((step) => {
        const el = document.querySelector(step.element);
        return el !== null;
      })
      .map((step, idx) => ({
        element: step.element,
        popover: {
          title: `${step.icon} ${idx + 1}. ${step.title}`,
          description: step.description,
          side: step.side,
          align: step.align,
        },
      }));

    if (activeSteps.length === 0) return;

    const driverObj = driver({
      showProgress: true,
      animate: true,
      allowClose: true,
      overlayColor: 'rgb(15, 23, 42)',
      overlayOpacity: 0.75,
      stagePadding: isMobile ? 4 : 8,
      stageRadius: 10,
      popoverClass: 'pm-tour-popover',
      nextBtnText: 'Lanjut →',
      prevBtnText: '← Kembali',
      doneBtnText: 'Selesai & Mengerti 🎉',
      progressText: 'Langkah {{current}} dari {{total}}',
      onHighlightStarted: (element) => {
        scrollToCenterElement(element);
      },
      onHighlighted: () => {
        ensurePopoverVisible();
      },
      onDestroyStarted: () => {
        cleanupTour();
        driverObj.destroy();
      },
      onDestroyed: () => {
        cleanupTour();
      },
      steps: activeSteps,
    });

    driverObj.drive();
  };


  const handlePrint = () => {
    if (!document.getElementById('process-report-print-page')) {
      const pageStyle = document.createElement('style');
      pageStyle.id = 'process-report-print-page';
      pageStyle.textContent = '@page { size: A4 landscape; margin: 6mm; }';
      document.head.appendChild(pageStyle);
    }
    document.documentElement.classList.add('printing-process-report');
    document.body.classList.add('printing-process-report');
    window.dispatchEvent(new Event('resize'));

    requestAnimationFrame(() => {
      setTimeout(() => {
        window.dispatchEvent(new Event('resize'));
        setTimeout(() => {
          window.print();
        }, 120);
      }, 80);
    });
  };

  if (loading) {
    return (
      <div className="flex h-full w-full items-center justify-center bg-gray-50">
        <div className="flex flex-col items-center">
          <RefreshCw className="w-10 h-10 text-indigo-500 animate-spin mb-4" />
          <p className="text-gray-500 font-medium">Memuat laporan audit energi & diagnostik mesin...</p>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="flex min-h-screen w-full items-center justify-center bg-slate-50 p-4 sm:p-6">
        <div className="bg-white rounded-2xl shadow-sm border border-red-100 p-6 sm:p-8 max-w-md w-full text-center">
          <div className="w-14 h-14 bg-rose-50 border border-rose-200 rounded-full flex items-center justify-center mx-auto mb-4">
            <AlertCircle className="w-8 h-8 text-rose-500" />
          </div>
          <span className="inline-block px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-rose-50 text-rose-700 border border-rose-200 mb-2">
            ID #{process_id}
          </span>
          <h2 className="text-xl font-bold text-gray-900 mb-2">Data Tidak Ditemukan</h2>
          <p className="text-slate-600 text-xs sm:text-sm mb-2 leading-relaxed">
            {error || 'Data laporan audit untuk proses ini tidak ditemukan di database.'}
          </p>
          <p className="text-slate-400 text-[11px] mb-6">
            Kemungkinan nomor ID proses salah, proses telah dihapus, atau belum disinkronisasi.
          </p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-2.5 w-full">
            <button
              type="button"
              onClick={handleBack}
              className="w-full sm:w-auto inline-flex items-center justify-center gap-1.5 px-4 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl font-semibold text-xs transition-colors cursor-pointer"
            >
              <ArrowLeft size={14} />
              <span>Kembali</span>
            </button>
            <button
              type="button"
              onClick={() => navigate('/history')}
              className="w-full sm:w-auto inline-flex items-center justify-center gap-1.5 px-4 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl font-semibold text-xs transition-colors shadow-xs cursor-pointer"
            >
              <span>Daftar Riwayat</span>
            </button>
            <button
              type="button"
              onClick={() => fetchData()}
              className="w-full sm:w-auto inline-flex items-center justify-center gap-1.5 px-3 py-2.5 text-slate-500 hover:text-slate-800 hover:bg-slate-100 rounded-xl font-semibold text-xs transition-colors cursor-pointer"
              title="Coba Muat Ulang"
            >
              <RefreshCw size={14} />
              <span className="sm:hidden">Muat Ulang</span>
            </button>
          </div>
        </div>
      </div>
    );
  }

  const {
    identity,
    kpi,
    timing,
    phase_breakdown: phases,
    chart_data,
    energy_financials: fin,
    program_benchmark: bench,
    operator_forensics: forensics,
    plant_boiler_context: boilerCtx,
    cooling_context: coolingCtx,
  } = data;

  const eff = kpi?.efficiency;
  const effValueClass =
    eff == null
      ? 'text-slate-900'
      : eff >= 80
        ? 'text-emerald-700'
        : eff >= 60
          ? 'text-amber-700'
          : 'text-rose-700';

  const thresholdBar = boilerCtx?.threshold_bar ?? 3.8;

  const MOBILE_TABS = [
    { id: 'summary', label: 'Ringkasan & Biaya', icon: Layers, count: null },
    { id: 'curve', label: 'Kurva Suhu', icon: Activity, count: null },
    ...(coolingCtx ? [{ id: 'cooling', label: 'Cooling', icon: Droplets, count: coolingCtx.overrun_mins > 0 ? `+${coolingCtx.overrun_mins}m` : null }] : []),
    ...(boilerCtx ? [{ id: 'boiler', label: 'Tekanan Uap', icon: Gauge, count: boilerCtx.low_pressure_pct > 0 ? `${boilerCtx.low_pressure_pct}%` : null }] : []),
    ...((bench || (forensics && forensics.length > 0)) ? [{ id: 'bench', label: 'Benchmark & Forensik', icon: BarChart3, count: forensics?.length ? `${forensics.length}` : null }] : []),
    { id: 'all', label: 'Semua Bagian', icon: FileText, count: null },
  ];

  return (
    <div
      className="process-report min-h-full bg-slate-50 px-2.5 py-2.5 sm:px-5 lg:px-6 pb-12 print-area"
      style={{ WebkitPrintColorAdjust: 'exact', printColorAdjust: 'exact' }}
    >
      <div className="mx-auto w-full max-w-[1440px] space-y-4 process-report-content">
        {/* ══════════════════════════════════════════════════════════════════════
            HEADER LAPORAN AUDIT ENERGI & DIAGNOSTIK PROSES
           ══════════════════════════════════════════════════════════════════════ */}
        <div className="print-report-header bg-white rounded-2xl border border-slate-200/90 p-4 sm:p-5 shadow-xs space-y-3">
          {/* Desktop Layout (hidden sm:block) */}
          <div className="hidden sm:block space-y-3">
            {/* Top Row: Title & Machine (Left) + Action Buttons (Right) */}
            <div className="flex items-center justify-between gap-4">
              <div className="flex items-center gap-3 min-w-0">
                <button
                  onClick={handleBack}
                  aria-label="Kembali"
                  className="no-print flex-shrink-0 rounded-xl p-2.5 text-slate-600 bg-slate-100 hover:bg-slate-200 hover:text-slate-900 transition-all shadow-2xs hover:-translate-y-0.5 cursor-pointer"
                  title="Kembali ke halaman sebelumnya"
                >
                  <ArrowLeft size={18} />
                </button>
                <ProcessStatusIcon
                  isComplete={data.is_complete}
                  thermalStatus={data.thermal_status}
                  size="md"
                  className="shrink-0"
                />
                <div className="flex items-center gap-3 min-w-0">
                  <h1 className="text-2xl font-black tracking-tight text-slate-900 font-sans whitespace-nowrap">
                    {data.machine_name}
                  </h1>
                  <span className="px-3 py-1 rounded-lg bg-indigo-50 border border-indigo-200/80 text-indigo-700 text-sm font-mono font-bold shrink-0">
                    Batch #{data.batch_number}
                  </span>
                  <ProcessStatusBadge isComplete={data.is_complete} thermalStatus={data.thermal_status} />
                  {data.machine_group && data.machine_group !== '-' && (
                    <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-slate-100 text-slate-600 border border-slate-200/60 truncate max-w-xs">
                      {data.machine_group}
                    </span>
                  )}
                </div>
              </div>

              {/* Action Buttons Right: Unified clean theme */}
              <div className="no-print flex items-center gap-2 shrink-0">
                {/* Koreksi di Admin */}
                {data.identity_id ? (
                  <a
                    href={`${BACKEND_BASE_URL}/admin/monitoring/dyeingidentity/${data.identity_id}/change/`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center justify-center gap-1.5 rounded-xl border border-slate-200 bg-white hover:bg-amber-50/70 hover:border-amber-300 text-slate-700 hover:text-amber-950 px-3.5 py-2 text-xs font-semibold transition-all text-center shadow-2xs hover:-translate-y-0.5 cursor-pointer group"
                    title={`Koreksi Data Batch #${data.batch_number} di Django Admin (ID: ${data.identity_id}) - Buka tab baru`}
                  >
                    <Wrench size={13} className="text-amber-600 group-hover:rotate-12 transition-transform shrink-0" />
                    <span>Koreksi di Admin</span>
                    <ExternalLink size={11} className="text-slate-400 group-hover:text-amber-600 opacity-70 shrink-0" />
                  </a>
                ) : (
                  <a
                    href={getAdminAddUrl()}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center justify-center gap-1.5 rounded-xl border border-slate-200 bg-white hover:bg-amber-50/70 hover:border-amber-300 text-slate-700 hover:text-amber-950 px-3.5 py-2 text-xs font-semibold transition-all text-center shadow-2xs hover:-translate-y-0.5 cursor-pointer group"
                    title="Input identitas batch baru di Django Admin - Buka tab baru"
                  >
                    <Wrench size={13} className="text-amber-600 group-hover:rotate-12 transition-transform shrink-0" />
                    <span>Input di Admin</span>
                    <ExternalLink size={11} className="text-slate-400 group-hover:text-amber-600 opacity-70 shrink-0" />
                  </a>
                )}

                {/* Laporan Lengkap Formal */}
                <a
                  href={`${BACKEND_BASE_URL}/dyeing-report/${data.identity_id || data.id || process_id}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center justify-center gap-1.5 rounded-xl border border-slate-200 bg-white hover:bg-emerald-50/70 hover:border-emerald-300 text-slate-700 hover:text-emerald-950 px-3.5 py-2 text-xs font-semibold transition-all text-center shadow-2xs hover:-translate-y-0.5 cursor-pointer group"
                  title="Buka Laporan Celup Lengkap Formal (8000/dyeing-report)"
                >
                  <FileText size={13} className="text-emerald-600 shrink-0" />
                  <span>Laporan Lengkap</span>
                  <ExternalLink size={11} className="text-slate-400 group-hover:text-emerald-600 opacity-70 shrink-0" />
                </a>

                {/* Bagikan */}
                <ShareToChatButton
                  reportPayload={{
                    report_type: 'PROCESS_REPORT',
                    title: `Batch #${identity.batch_number || data.batch_number || process_id} • ${identity.machine_name || data.machine_name || 'Mesin'}`,
                    subtitle: `Program: ${identity.program || '-'} • Proses: ${identity.jenis_proses || '-'}`,
                    metrics: {
                      'Durasi': `${data.duration_effective || '-'} mnt`,
                      'Suhu Maks': `${data.max_temperature || data.max_temp || '-'} °C`,
                      'Steam': `${data.steam_total_kg || '-'} kg`,
                      'Status': data.is_complete ? 'Selesai' : 'Berjalan',
                    },
                    target_url: `/history/report/${data.id || process_id}?machine=${encodeURIComponent(data.machine_code || '')}&batch=${encodeURIComponent(identity.batch_number || data.batch_number || '')}`,
                    machine_code: data.machine_code || '',
                    batch_number: identity.batch_number || data.batch_number || '',
                  }}
                  variant="default"
                  label="Bagikan"
                />

                {/* Cetak Laporan - Primary Action */}
                <button
                  onClick={handlePrint}
                  className="inline-flex items-center justify-center gap-1.5 rounded-xl bg-slate-900 hover:bg-slate-800 text-white px-4 py-2 text-xs font-bold shadow-xs hover:shadow-sm transition-all hover:-translate-y-0.5 cursor-pointer text-center shrink-0"
                >
                  <Printer size={14} className="shrink-0" />
                  <span>Cetak Laporan</span>
                </button>
              </div>
            </div>

            {/* Bottom Row: Metadata Strip (Program, Proses, Real Heat -> Selesai) + Secondary Links */}
            <div className="pt-2.5 border-t border-slate-100 flex flex-wrap items-center justify-between gap-y-2 text-xs">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-slate-600 font-medium">
                <span className="inline-flex items-center gap-1.5">
                  <span className="text-slate-400 font-normal">Program:</span>
                  <strong className="text-slate-900 font-mono font-bold bg-slate-100 px-2 py-0.5 rounded border border-slate-200/60">
                    {identity.program}
                  </strong>
                </span>
                <span className="text-slate-300">•</span>
                <span className="inline-flex items-center gap-1.5">
                  <span className="text-slate-400 font-normal">Proses:</span>
                  <strong className="text-indigo-700 font-bold bg-indigo-50 px-2 py-0.5 rounded border border-indigo-200/60">
                    {identity.jenis_proses}
                  </strong>
                </span>
                <span className="text-slate-300">•</span>
                <span className="inline-flex items-center gap-1">
                  <span className="text-slate-400 font-normal">Real Heat:</span>
                  <strong className="text-slate-800 font-mono font-semibold">
                    {formatBackendDate(identity.heat_start_time)}
                  </strong>
                  <span className="text-slate-400 mx-1">&rarr;</span>
                  <span className="text-slate-400 font-normal">Selesai:</span>
                  <strong className="text-slate-800 font-mono font-semibold">
                    {formatBackendDate(identity.end_time)}
                  </strong>
                </span>
              </div>

              {/* Secondary Navigation Links */}
              <div className="no-print flex items-center gap-1.5 shrink-0">
                {data.machine_id && data.report_date && (
                  <a
                    href={`/machine-daily-analytics/${data.machine_id}/${data.report_date}`}
                    className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg border border-slate-200 bg-slate-50 hover:bg-indigo-50 hover:border-indigo-200 text-slate-700 hover:text-indigo-800 text-xs font-medium transition-all shadow-2xs hover:-translate-y-0.5 shrink-0"
                    title="Buka pelacakan proses mesin harian &amp; grafik profil suhu 24 jam kontinu"
                  >
                    <Activity size={12} className="text-indigo-600 shrink-0" />
                    <span>Grafik Mesin (24 Jam)</span>
                  </a>
                )}
                <a
                  href="/daily-report"
                  className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg border border-slate-200 bg-slate-50 hover:bg-slate-100 text-slate-700 hover:text-slate-900 text-xs font-medium transition-all shadow-2xs hover:-translate-y-0.5 shrink-0"
                  title="Kembali ke Dashboard Laporan Harian Pabrik"
                >
                  <Calendar size={12} className="text-slate-500 shrink-0" />
                  <span>Harian</span>
                </a>
                <button
                  type="button"
                  onClick={handleStartTour}
                  className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg border border-indigo-200/80 bg-indigo-50/70 hover:bg-indigo-100 text-indigo-700 text-xs font-semibold transition-all shadow-2xs hover:-translate-y-0.5 shrink-0 cursor-pointer group"
                  title="Buka panduan tur interaktif laporan ini"
                >
                  <Compass size={12} className="text-indigo-600 group-hover:rotate-45 transition-transform shrink-0" />
                  <span>Panduan Fitur</span>
                </button>
              </div>
            </div>
          </div>

          {/* Mobile Layout (sm:hidden) */}
          <div className="sm:hidden space-y-2.5">
            {/* Top row: Back button, Machine & Batch info, Status badge, Quick Share & Print */}
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 min-w-0">
                <button
                  onClick={handleBack}
                  aria-label="Kembali"
                  className="no-print flex-shrink-0 rounded-xl p-2 text-slate-700 bg-slate-100 hover:bg-slate-200 transition-colors shadow-2xs cursor-pointer"
                >
                  <ArrowLeft size={18} />
                </button>
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className="font-extrabold text-base tracking-tight text-slate-900 truncate">
                      {data.machine_name}
                    </span>
                    <span className="px-1.5 py-0.5 rounded-md bg-indigo-50 border border-indigo-200 text-indigo-700 text-[11px] font-bold shrink-0">
                      #{data.batch_number}
                    </span>
                    <ProcessStatusBadge isComplete={data.is_complete} thermalStatus={data.thermal_status} />
                  </div>
                  {data.machine_group && data.machine_group !== '-' && (
                    <div className="text-[10px] text-slate-500 truncate">
                      {data.machine_group}
                    </div>
                  )}
                </div>
              </div>

              {/* Action buttons (Share & Print) */}
              <div className="no-print flex items-center gap-1.5 shrink-0">
                <ShareToChatButton
                  reportPayload={{
                    report_type: 'PROCESS_REPORT',
                    title: `Batch #${identity.batch_number || data.batch_number || process_id} • ${identity.machine_name || data.machine_name || 'Mesin'}`,
                    subtitle: `Program: ${identity.program || '-'} • Proses: ${identity.jenis_proses || '-'}`,
                    metrics: {
                      'Durasi': `${data.duration_effective || '-'} mnt`,
                      'Suhu Maks': `${data.max_temperature || data.max_temp || '-'} °C`,
                      'Steam': `${data.steam_total_kg || '-'} kg`,
                      'Status': data.is_complete ? 'Selesai' : 'Berjalan',
                    },
                    target_url: `/history/report/${data.id || process_id}?machine=${encodeURIComponent(data.machine_code || '')}&batch=${encodeURIComponent(identity.batch_number || data.batch_number || '')}`,
                    machine_code: data.machine_code || '',
                    batch_number: identity.batch_number || data.batch_number || '',
                  }}
                  variant="default"
                  label=""
                />
                <button
                  type="button"
                  onClick={handlePrint}
                  aria-label="Cetak"
                  className="p-2 rounded-xl bg-slate-900 text-white hover:bg-slate-800 transition-colors shadow-2xs cursor-pointer"
                  title="Cetak Laporan"
                >
                  <Printer size={15} />
                </button>
              </div>
            </div>

            {/* Middle row: Program & Process chips */}
            <div className="bg-slate-50/90 rounded-xl p-2 border border-slate-200/70 text-[11px] space-y-1">
              <div className="flex items-center justify-between gap-2">
                <span className="font-semibold text-slate-800 truncate">
                  <span className="text-slate-500 font-normal">Program: </span>
                  {identity.program}
                </span>
                <span className="px-2 py-0.5 rounded-full bg-white border border-slate-200 text-slate-700 font-bold text-[10px] shrink-0">
                  {identity.jenis_proses}
                </span>
              </div>
              <div className="text-[10.5px] text-slate-500 truncate pt-1 border-t border-slate-200/50">
                <span>Real Heat: <b className="text-slate-700">{formatBackendDate(identity.heat_start_time)}</b></span>
                <span className="mx-1">&rarr;</span>
                <span>Selesai: <b className="text-slate-700">{formatBackendDate(identity.end_time)}</b></span>
              </div>
            </div>

            {/* Bottom row: Horizontal quick-link pills */}
            <div className="no-print overflow-x-auto scrollbar-none flex items-center gap-1.5 pt-1">
              {data.identity_id ? (
                <a
                  href={`${BACKEND_BASE_URL}/admin/monitoring/dyeingidentity/${data.identity_id}/change/`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-xl border border-amber-300 bg-amber-50/90 text-amber-900 text-[11px] font-bold whitespace-nowrap shadow-2xs shrink-0 hover:bg-amber-100 active:scale-95 transition-all"
                  title="Koreksi di Admin Django (Tab Baru)"
                >
                  <Wrench size={12} className="text-amber-700" />
                  <span>Koreksi di Admin</span>
                  <ExternalLink size={10} className="text-amber-600 opacity-70" />
                </a>
              ) : (
                <a
                  href={getAdminAddUrl()}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-xl border border-amber-300 bg-amber-50/90 text-amber-900 text-[11px] font-bold whitespace-nowrap shadow-2xs shrink-0 hover:bg-amber-100 active:scale-95 transition-all"
                  title="Input di Admin Django (Tab Baru)"
                >
                  <Wrench size={12} className="text-amber-700" />
                  <span>Input di Admin</span>
                  <ExternalLink size={10} className="text-amber-600 opacity-70" />
                </a>
              )}
              {data.machine_id && data.report_date && (
                <a
                  href={`/machine-daily-analytics/${data.machine_id}/${data.report_date}`}
                  className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-xl border border-indigo-200 bg-indigo-50/90 text-indigo-700 text-[11px] font-bold whitespace-nowrap shadow-2xs shrink-0"
                >
                  <Activity size={12} className="text-indigo-600" />
                  <span>Grafik 24 Jam</span>
                </a>
              )}
              <a
                href={`${BACKEND_BASE_URL}/dyeing-report/${data.identity_id || data.id || process_id}`}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-xl border border-emerald-200 bg-emerald-50/90 text-emerald-700 text-[11px] font-bold whitespace-nowrap shadow-2xs shrink-0"
              >
                <FileText size={12} className="text-emerald-600" />
                <span>Laporan Celup</span>
                <ExternalLink size={10} className="text-emerald-500 opacity-70" />
              </a>
              <a
                href="/daily-report"
                className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-xl border border-slate-200 bg-white text-slate-700 text-[11px] font-bold whitespace-nowrap shadow-2xs shrink-0"
              >
                <Calendar size={12} className="text-slate-500" />
                <span>Harian</span>
              </a>
              <button
                type="button"
                onClick={handleStartTour}
                className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-xl border border-indigo-200 bg-white text-indigo-700 text-[11px] font-bold whitespace-nowrap shadow-2xs shrink-0 cursor-pointer"
              >
                <Compass size={12} className="text-indigo-600" />
                <span>Panduan</span>
              </button>
              <button
                type="button"
                onClick={fetchData}
                className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-xl border border-slate-200 bg-white text-slate-600 text-[11px] font-bold whitespace-nowrap shadow-2xs shrink-0 cursor-pointer"
                title="Muat Ulang"
              >
                <RefreshCw size={12} />
                <span>Refresh</span>
              </button>
            </div>
          </div>
        </div>

        {/* ══════════════════════════════════════════════════════════════════════
            MOBILE SEGMENTED NAVIGATION TABS (STICKY)
           ══════════════════════════════════════════════════════════════════════ */}
        <div className="no-print lg:hidden sticky top-0 z-30 -mx-2.5 px-2.5 py-2 bg-slate-50/95 backdrop-blur-md border-b border-slate-200/80 mb-2 shadow-2xs">
          <div className="flex items-center gap-1.5 overflow-x-auto scrollbar-none py-0.5">
            {MOBILE_TABS.map((tab) => {
              const Icon = tab.icon;
              const isActive = activeMobileTab === tab.id;
              return (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setActiveMobileTab(tab.id)}
                  className={`px-3 py-1.5 rounded-xl text-xs font-bold whitespace-nowrap transition-all flex items-center gap-1.5 cursor-pointer shrink-0 ${
                    isActive
                      ? 'bg-slate-900 text-white shadow-xs'
                      : 'bg-white text-slate-600 hover:bg-slate-100 border border-slate-200/80'
                  }`}
                >
                  <Icon size={13} className={isActive ? 'text-indigo-300' : 'text-slate-400'} />
                  <span>{tab.label}</span>
                  {tab.count && (
                    <span className={`px-1.5 py-0.2 rounded-full text-[9.5px] font-black ${
                      isActive ? 'bg-indigo-500/30 text-indigo-100' : 'bg-rose-100 text-rose-700'
                    }`}>
                      {tab.count}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </div>

        {/* ══════════════════════════════════════════════════════════════════════
            1. RINGKASAN EKSEKUTIF KPI & FINANSIAL (6 KARTU)
           ══════════════════════════════════════════════════════════════════════ */}
        <div className="print-kpi-grid grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2.5 sm:gap-3">
          {/* Card 1: Durasi Efektif */}
          <div className="report-card p-3.5 flex flex-col justify-between bg-gradient-to-b from-white via-white to-slate-50/60 hover:shadow-md hover:-translate-y-0.5 transition-all">
            <div className="flex items-center justify-between">
              <span className="report-label">Durasi Efektif</span>
              <div className="w-7 h-7 rounded-lg bg-blue-50 text-blue-600 ring-1 ring-blue-500/15 flex items-center justify-center shrink-0">
                <Clock size={15} />
              </div>
            </div>
            <div className="report-data text-xl font-extrabold text-slate-950 mt-1.5 tracking-tight">
              {kpi.duration_effective ?? '-'}
              <span className="text-xs font-normal text-slate-500 ml-1">mnt</span>
            </div>
            <div className="text-[11px] text-slate-500 mt-1.5 flex items-center justify-between pt-1 border-t border-slate-100">
              <span>Ideal: <b className="text-slate-700">{timing.total_ideal ?? '-'}m</b></span>
              <span className={`px-1.5 py-0.5 rounded-full text-[10.5px] font-bold ${
                (kpi.loss_time || 0) > 0 ? 'bg-rose-50 text-rose-600 border border-rose-200' : 'bg-emerald-50 text-emerald-600 border border-emerald-200'
              }`}>
                {kpi.loss_time != null ? `${kpi.loss_time > 0 ? '+' : ''}${kpi.loss_time}m` : ''}
              </span>
            </div>
          </div>

          {/* Card 2: Efisiensi Durasi */}
          <div className="report-card p-3.5 flex flex-col justify-between bg-gradient-to-b from-white via-white to-slate-50/60 hover:shadow-md hover:-translate-y-0.5 transition-all">
            <div className="flex items-center justify-between">
              <span className="report-label">Efisiensi Total</span>
              <div className="w-7 h-7 rounded-lg bg-amber-50 text-amber-600 ring-1 ring-amber-500/15 flex items-center justify-center shrink-0">
                <TrendingUp size={15} />
              </div>
            </div>
            <div className={`report-data text-xl font-extrabold mt-1.5 tracking-tight flex items-center ${effValueClass}`}>
              {eff != null ? `${eff}%` : '-'}
              {kpi.grade && kpi.grade !== '-' && (
                <span className="ml-2 rounded-full bg-slate-100 border border-slate-200/80 px-2 py-0.5 text-[10px] font-bold text-slate-700">
                  Grade {kpi.grade}
                </span>
              )}
            </div>
            <div className="text-[11px] text-slate-500 mt-1.5 pt-1 border-t border-slate-100">
              Target Standar: <b className="text-slate-700">&ge; 85%</b>
            </div>
          </div>

          {/* Card 3: Tekanan & % Sehat Uap */}
          <div className="report-card p-3.5 flex flex-col justify-between bg-gradient-to-b from-white via-white to-slate-50/60 hover:shadow-md hover:-translate-y-0.5 transition-all">
            <div className="flex items-center justify-between">
              <span className="report-label">Tekanan Uap</span>
              <div className="w-7 h-7 rounded-lg bg-emerald-50 text-emerald-600 ring-1 ring-emerald-500/15 flex items-center justify-center shrink-0">
                <Gauge size={15} />
              </div>
            </div>
            <div className={`report-data text-xl font-extrabold mt-1.5 tracking-tight ${(timing.avg_steam || 0) < thresholdBar ? 'text-rose-600' : 'text-emerald-700'}`}>
              {timing.avg_steam ?? '-'}
              <span className="text-xs font-normal text-slate-500 ml-1">bar</span>
            </div>
            <div className="text-[11px] text-slate-500 mt-1.5 flex items-center justify-between pt-1 border-t border-slate-100">
              <span>% Sehat:</span>
              <b className={`px-1.5 py-0.5 rounded-full text-[10.5px] font-bold ${
                (boilerCtx?.steam_healthy_pct ?? 100) < 80 ? 'bg-rose-50 text-rose-600 border border-rose-200' : 'bg-emerald-50 text-emerald-700 border border-emerald-200'
              }`}>
                {boilerCtx?.steam_healthy_pct != null ? `${boilerCtx.steam_healthy_pct}%` : '-'}
              </b>
            </div>
          </div>

          {/* Card 4: Total Biaya Energi Aktual */}
          <div className="report-card p-3.5 flex flex-col justify-between bg-gradient-to-b from-white via-white to-slate-50/60 hover:shadow-md hover:-translate-y-0.5 transition-all">
            <div className="flex items-center justify-between">
              <span className="report-label">Biaya Energi Aktual</span>
              <div className="w-7 h-7 rounded-lg bg-violet-50 text-violet-600 ring-1 ring-violet-500/15 flex items-center justify-center shrink-0">
                <DollarSign size={15} />
              </div>
            </div>
            <div className="report-data text-lg font-extrabold text-slate-950 mt-1.5 truncate tracking-tight">
              {rp(fin?.totals?.total_actual_rp)}
            </div>
            <div className="text-[11px] text-slate-500 mt-1.5 flex items-center justify-between pt-1 border-t border-slate-100">
              <span>Ideal: <b className="text-slate-700">{rp(fin?.totals?.total_ideal_rp)}</b></span>
            </div>
          </div>

          {/* Card 5: Total Kerugian (Loss Batch Ini) */}
          <div className="report-card p-3.5 flex flex-col justify-between bg-white hover:shadow-md hover:-translate-y-0.5 transition-all border border-slate-200/90">
            <div className="flex items-center justify-between">
              <span className="report-label text-rose-700 font-bold">Total Loss Energi</span>
              <div className="w-7 h-7 rounded-lg bg-rose-50 text-rose-600 ring-1 ring-rose-500/20 flex items-center justify-center shrink-0">
                <AlertTriangle size={15} />
              </div>
            </div>
            <div className="report-data text-xl font-black text-rose-600 mt-1.5 truncate tracking-tight">
              {rp(fin?.totals?.total_loss_rp)}
            </div>
            <div className="text-[11px] text-rose-600 font-medium mt-1.5 truncate pt-1 border-t border-slate-100">
              {fin?.totals?.loss_per_yard_rp != null
                ? `Loss/Yard: +Rp ${fin.totals.loss_per_yard_rp}/yd`
                : `Uap + Listrik Loss`}
            </div>
          </div>

          {/* Card 6: Potensi Keuntungan Bulanan/Tahunan */}
          <div className="report-card p-3.5 flex flex-col justify-between bg-white hover:shadow-md hover:-translate-y-0.5 transition-all border border-slate-200/90">
            <div className="flex items-center justify-between">
              <span className="report-label text-emerald-700 font-bold">Potensi Saving Mesin</span>
              <div className="w-7 h-7 rounded-lg bg-emerald-50 text-emerald-600 ring-1 ring-emerald-500/20 flex items-center justify-center shrink-0">
                <TrendingUp size={15} />
              </div>
            </div>
            <div className="report-data text-xl font-black text-emerald-700 mt-1.5 truncate tracking-tight" title="Proyeksi penghematan per bulan pada mesin ini jika loss dieliminasi">
              {rp(fin?.totals?.projected_monthly_saving_rp)}
              <span className="text-xs font-semibold text-emerald-600 ml-1">/bln</span>
            </div>
            <div className="text-[11px] text-slate-500 mt-1.5 truncate pt-1 border-t border-slate-100">
              Tahunan: <strong className="text-slate-800 font-mono font-bold">{rp(fin?.totals?.projected_annual_saving_rp)}/thn</strong>
            </div>
          </div>
        </div>

        {/* ══════════════════════════════════════════════════════════════════════
            2. EXECUTIVE SUMMARY ANALIS ENERGI: DEKOMPOSISI 4 FAKTOR KERUGIAN & AUDIT HARGA
           ══════════════════════════════════════════════════════════════════════ */}
        {fin && (
          <div className={`print-3col-grid grid grid-cols-1 lg:grid-cols-12 gap-3 ${(activeMobileTab === "all" || activeMobileTab === "summary") ? "grid" : "hidden lg:grid print:grid"}`}>

            {/* 4-Factor Attribution Waterfall (4 cols) */}
            <div className="lg:col-span-4 report-card p-4 flex flex-col justify-between bg-gradient-to-b from-white via-white to-slate-50/30">
              <div>
                <div className="flex items-center justify-between border-b border-slate-200 pb-2 mb-3">
                  <div>
                    <h2 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                      <div className="w-6 h-6 rounded-md bg-indigo-50 text-indigo-600 flex items-center justify-center shrink-0"><Layers size={14} /></div> Attribution Sumber Kerugian (Rp)
                    </h2>
                    <p className="text-[11px] text-slate-500">
                      Porsi kerugian energi berdasarkan akar penyebabnya
                    </p>
                  </div>
                  <span className="text-xs font-bold text-rose-600 bg-rose-50 px-2 py-0.5 rounded border border-rose-200">
                    {rp(fin.totals.total_loss_rp)}
                  </span>
                </div>

                <div className="space-y-2.5">
                  {(fin.loss_attribution || []).map((b, i) => (
                    <div key={b.key} className="bg-slate-50/90 rounded-xl p-3 border border-slate-200/70 hover:bg-slate-100/70 transition-colors">
                      <div className="flex items-center justify-between text-xs font-bold text-slate-800 mb-1">
                        <span>{i + 1}. {b.label}</span>
                        <span className={b.amount_rp > 0 ? 'text-rose-600' : 'text-emerald-600'}>
                          {rp(b.amount_rp)} ({b.share_pct}%)
                        </span>
                      </div>
                      <div className="w-full h-2 bg-slate-200/80 rounded-full overflow-hidden mb-1.5">
                        <div
                          className={`h-full rounded-full ${i === 0 && b.amount_rp > 0 ? 'bg-rose-500' : 'bg-amber-500'}`}
                          style={{ width: `${Math.max(b.amount_rp > 0 ? 4 : 0, b.share_pct)}%` }}
                        />
                      </div>
                      <p className="text-[10.5px] text-slate-600 leading-snug">{b.desc}</p>
                    </div>
                  ))}
                </div>
              </div>

              <div className="mt-3.5 pt-2.5 border-t border-slate-200/80 flex flex-col sm:flex-row sm:items-center justify-between gap-1.5 text-xs bg-emerald-50/80 px-3.5 py-2.5 rounded-xl border border-emerald-200/80 shadow-2xs">
                <div>
                  <div className="font-bold text-emerald-900">Unit Cost Energi per Yard</div>
                  <div className="text-[10.5px] text-emerald-700">
                    Output Kain: <b>{fin.totals.output_yard ? `${numFmt(fin.totals.output_yard, 0)} yd` : '-'}</b> ({identity.isi_per_tube})
                  </div>
                </div>
                <div className="text-right">
                  <div className="font-bold text-slate-900">
                    Aktual: {fin.totals.cost_per_yard_actual_rp != null ? `Rp ${numFmt(fin.totals.cost_per_yard_actual_rp, 0)}/yd` : '-'}
                  </div>
                  <div className="text-[11px] font-semibold text-emerald-700">
                    Target Ideal: {fin.totals.cost_per_yard_ideal_rp != null ? `Rp ${numFmt(fin.totals.cost_per_yard_ideal_rp, 0)}/yd` : '-'}
                  </div>
                </div>
              </div>
            </div>

            {/* Audit Harga & Pemakaian Steam 3-Lapis PINN (4 cols) */}
            <div className="lg:col-span-4 report-card p-4 flex flex-col justify-between bg-gradient-to-b from-white via-white to-slate-50/30">
              <div>
                <div className="flex items-center justify-between border-b border-slate-200 pb-2 mb-3">
                  <div>
                    <h2 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                      <div className="w-6 h-6 rounded-md bg-orange-50 text-orange-600 flex items-center justify-center shrink-0"><Flame size={14} /></div> Audit Biaya & Loss Steam (3-Lapis PINN)
                    </h2>
                    <p className="text-[11px] text-slate-500">
                      Harga Satuan Uap: <b>Rp {numFmt(fin.tariffs.steam_rp_per_kg, 0)} / kg</b>
                    </p>
                  </div>
                  <span className="text-xs font-bold px-2 py-0.5 rounded bg-orange-50 text-orange-700 border border-orange-200">
                    Eff Uap: {fin.steam.eff_pct != null ? `${fin.steam.eff_pct}%` : '-'}
                  </span>
                </div>

                <div className="space-y-2 text-xs">
                  <div className="flex items-center justify-between p-2.5 rounded-r-xl rounded-l-md bg-slate-50/90 border-y border-r border-slate-200/70 border-l-4 border-l-blue-500">
                    <div>
                      <div className="font-bold text-slate-800">Lapis 1: Pemakaian Aktual Mesin Ini</div>
                      <div className="text-[10.5px] text-slate-500">Prediksi berbasis DNA termodinamika mesin ini</div>
                    </div>
                    <div className="text-right font-bold text-slate-900">
                      <div>{numFmt(fin.steam.actual_kg)} kg</div>
                      <div className="text-[11px] text-slate-600">{rp(fin.steam.cost_actual_rp)}</div>
                    </div>
                  </div>

                  <div className="flex items-center justify-between p-2.5 rounded-r-xl rounded-l-md bg-slate-50/90 border-y border-r border-slate-200/70 border-l-4 border-l-amber-500">
                    <div>
                      <div className="font-bold text-slate-800">Lapis 2: Benchmark Mesin Terbaik Sejenis</div>
                      <div className="text-[10.5px] text-slate-500">Jika dijalankan pada mesin kondisi fisik terbaik</div>
                    </div>
                    <div className="text-right font-semibold text-blue-700">
                      <div>{numFmt(fin.steam.best_machine_kg)} kg</div>
                      <div className="text-[10.5px] text-rose-600">
                        Loss Fisik Mesin: +{numFmt(fin.steam.loss_machine_cond_kg)} kg ({rp(fin.steam.loss_machine_cond_rp)})
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center justify-between p-2.5 rounded-r-xl rounded-l-md bg-emerald-50/60 border-y border-r border-emerald-200/70 border-l-4 border-l-emerald-500">
                    <div>
                      <div className="font-bold text-emerald-900">Lapis 3: Target Ideal Best-of-Best</div>
                      <div className="text-[10.5px] text-emerald-700">Kondisi mesin terbaik + tekanan uap kering ideal</div>
                    </div>
                    <div className="text-right font-bold text-emerald-800">
                      <div>{numFmt(fin.steam.ideal_kg)} kg</div>
                      <div className="text-[11px]">{rp(fin.steam.cost_ideal_rp)}</div>
                    </div>
                  </div>
                </div>
              </div>

              <div className="mt-3.5 pt-2.5 border-t border-slate-200/80 bg-gradient-to-br from-rose-50/90 via-rose-50/50 to-white rounded-xl p-3 border border-rose-200/80 shadow-2xs">
                <div className="flex items-center justify-between text-xs font-bold text-rose-900">
                  <span>Total Loss Steam (Lapis 1 &minus; Lapis 3):</span>
                  <span className="text-sm font-black text-rose-600">
                    +{numFmt(fin.steam.loss_total_kg)} kg ({rp(fin.steam.loss_total_rp)})
                  </span>
                </div>
                <div className="mt-1 flex justify-between text-[10.5px] text-rose-800">
                  <span>• Faktor Fisik Mesin: <b>{rp(fin.steam.loss_machine_cond_rp)}</b></span>
                  <span>• Faktor Drop Tekanan Uap: <b>{rp(fin.steam.loss_supply_press_rp)}</b></span>
                </div>
              </div>
            </div>

            {/* Audit Harga & Pemakaian Listrik WBP vs LWBP (4 cols) */}
            <div className="lg:col-span-4 report-card p-4 flex flex-col justify-between bg-gradient-to-b from-white via-white to-slate-50/30">
              <div>
                <div className="flex items-center justify-between border-b border-slate-200 pb-2 mb-3">
                  <div>
                    <h2 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                      <div className="w-6 h-6 rounded-md bg-amber-50 text-amber-500 flex items-center justify-center shrink-0"><Zap size={14} /></div> Audit Biaya & Loss Listrik (LWBP / WBP)
                    </h2>
                    <p className="text-[11px] text-slate-500">
                      Daya Mesin: <b>{fin.tariffs.nominal_power_kw} kW</b> &bull; LWBP: <b>Rp {numFmt(fin.tariffs.lwbp_rp_per_kwh)}</b> | WBP: <b>Rp {numFmt(fin.tariffs.wbp_rp_per_kwh)}</b>
                    </p>
                  </div>
                  <span className="text-xs font-bold px-2 py-0.5 rounded bg-amber-50 text-amber-800 border border-amber-200">
                    Eff Listrik: {fin.power.eff_pct != null ? `${fin.power.eff_pct}%` : '-'}
                  </span>
                </div>

                <div className="space-y-2 text-xs">
                  <div className="grid grid-cols-2 gap-2">
                    <div className="p-2.5 rounded-xl bg-slate-50/80 border border-slate-200/80 shadow-2xs min-w-0">
                      <div className="text-[10px] font-bold text-sky-800 uppercase tracking-tight truncate">Pemakaian LWBP</div>
                      <div className="text-sm font-bold text-slate-900 mt-0.5 font-mono truncate">{numFmt(fin.power.lwbp_kwh, 2)} kWh</div>
                      <div className="text-[11px] font-semibold text-sky-700 truncate">{rp(fin.power.cost_lwbp_rp)}</div>
                    </div>
                    <div className="p-2.5 rounded-xl bg-slate-50/80 border border-slate-200/80 shadow-2xs min-w-0">
                      <div className="text-[10px] font-bold text-amber-800 uppercase tracking-tight truncate">Pemakaian WBP (17–22)</div>
                      <div className="text-sm font-bold text-slate-900 mt-0.5 font-mono truncate">{numFmt(fin.power.wbp_kwh, 2)} kWh</div>
                      <div className="text-[11px] font-semibold text-amber-700 truncate">{rp(fin.power.cost_wbp_rp)}</div>
                    </div>
                  </div>

                  <div className="flex items-center justify-between p-2.5 rounded-xl bg-slate-50/90 border border-slate-200/70">
                    <div>
                      <div className="font-bold text-slate-800">Total Listrik Aktual vs Ideal</div>
                      <div className="text-[10.5px] text-slate-500">
                        Aktual: <b>{numFmt(fin.power.actual_kwh, 2)} kWh</b> vs Ideal: <b>{numFmt(fin.power.ideal_kwh, 2)} kWh</b>
                      </div>
                      {fin.power.elec_ideal_duration_mins > 0 && (
                        <div className="text-[10px] text-emerald-700 mt-0.5">
                          Durasi Ideal Listrik: <b>{fin.power.elec_ideal_duration_mins}m</b> (Resep {fin.power.recipe_ideal_mins}m + Keluar-Masuk Kain {fin.power.fabric_allowance_mins}m)
                        </div>
                      )}
                    </div>
                    <div className="text-right">
                      <div className="font-bold text-slate-900">{rp(fin.power.cost_actual_rp)}</div>
                      <div className="text-[10.5px] text-emerald-700 font-semibold">Ideal: {rp(fin.power.cost_ideal_rp)}</div>
                    </div>
                  </div>
                </div>
              </div>

              <div className="mt-3.5 pt-2.5 border-t border-slate-200/80 bg-gradient-to-br from-rose-50/90 via-rose-50/50 to-white rounded-xl p-3 border border-rose-200/80 shadow-2xs">
                <div className="flex items-center justify-between text-xs font-bold text-rose-900">
                  <span>Total Loss Listrik (+{numFmt(fin.power.loss_kwh, 2)} kWh):</span>
                  <span className="text-sm font-black text-rose-600">{rp(fin.power.loss_total_rp)}</span>
                </div>
                <div className="mt-1 flex justify-between text-[10.5px] text-rose-800">
                  <span>• Molor Durasi: <b>{rp(fin.power.loss_overrun_rp)}</b></span>
                  <span>• Penalti Tarif WBP: <b>{rp(fin.power.loss_wbp_surcharge_rp)}</b></span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ══════════════════════════════════════════════════════════════════════
            3. DIAGNOSTIK NORMALITAS MESIN: KOMPARASI HISTORIS PROGRAM YANG SAMA
           ══════════════════════════════════════════════════════════════════════ */}
        {bench ? (
          <div className={`report-card overflow-hidden rounded-2xl print-page-1-bottom shadow-xs ${(activeMobileTab === "all" || activeMobileTab === "bench") ? "block" : "hidden lg:block print:block"}`}>

            <div className="px-4 py-3.5 border-b border-slate-200/80 bg-gradient-to-r from-slate-50/90 via-white to-slate-50/90 flex flex-wrap items-center justify-between gap-2.5">
              <div>
                <h2 className="text-sm sm:text-base font-bold text-slate-900 flex items-center gap-2">
                  <BarChart3 size={17} className="text-blue-600" />
                  Analisis Normalitas Mesin &mdash; Komparasi Historis Program <span className="underline decoration-blue-400">{bench.program_name}</span>
                </h2>
                <p className="text-xs text-slate-600">
                  Membandingkan riwayat durasi Heating &amp; Cooling terhadap Pressure khusus pada mesin <strong className="text-slate-900">{data.machine_name}</strong> di program <strong className="text-slate-900">{bench.program_name}</strong> ({bench.sample_count_same_machine} histori batch di mesin ini)
                </p>
              </div>
              <span className={`px-3.5 py-1 rounded-full text-xs font-bold shadow-2xs ${TONE_BADGE[bench.overall_tone] || TONE_BADGE.emerald}`}>
                {bench.overall_machine_status}
              </span>
            </div>

            <div className="print-bench-grid p-3 sm:p-4 grid grid-cols-1 lg:grid-cols-12 gap-3 sm:gap-4">
              {/* Left 5 cols: Verdict Cards + Comparison Table */}
              <div className="print-bench-left lg:col-span-5 space-y-3">
                {/* Heating & Cooling Diagnosis Cards */}
                <div className={`rounded-lg border p-3 ${TONE_BOX[bench.heating_diagnosis.tone]}`}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-bold flex items-center gap-1.5">
                      <Flame size={14} /> Evaluasi Sistem Pemanas (Heating):
                    </span>
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded ${TONE_BADGE[bench.heating_diagnosis.tone]}`}>
                      {bench.heating_diagnosis.status}
                    </span>
                  </div>
                  <p className="text-xs leading-relaxed opacity-90">{bench.heating_diagnosis.detail}</p>
                </div>

                <div className={`rounded-lg border p-3 ${TONE_BOX[bench.cooling_diagnosis.tone]}`}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-bold flex items-center gap-1.5">
                      <Snowflake size={14} /> Evaluasi Sistem Pendingin (Cooling / HE):
                    </span>
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded ${TONE_BADGE[bench.cooling_diagnosis.tone]}`}>
                      {bench.cooling_diagnosis.status}
                    </span>
                  </div>
                  <p className="text-xs leading-relaxed opacity-90">{bench.cooling_diagnosis.detail}</p>
                </div>

                {/* Comparison Table */}
                <div className="overflow-x-auto border border-slate-200/80 rounded-xl shadow-2xs">
                  <table className="w-full text-xs border-collapse min-w-[340px]">
                    <thead className="bg-slate-100 border-b border-slate-200 text-slate-700">
                      <tr className="divide-x divide-slate-200">
                        <th className="px-2.5 py-2 text-left font-bold">Parameter</th>
                        <th className="px-2.5 py-2 text-right font-bold bg-blue-50/60 text-blue-900">Batch Ini</th>
                        <th className="px-2.5 py-2 text-right font-bold">Rata-rata Histori</th>
                        <th className="px-2.5 py-2 text-right font-bold text-emerald-800">Standar Resep</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-200">
                      <tr className="divide-x divide-slate-100">
                        <td className="px-2.5 py-1.5 font-semibold text-slate-700">Durasi Heating</td>
                        <td className="px-2.5 py-1.5 text-right font-bold bg-blue-50/30">{bench.comparison.current.heat_mins ?? '-'} mnt</td>
                        <td className="px-2.5 py-1.5 text-right text-slate-600">{bench.comparison.historical_avg.heat_mins ?? '-'} mnt</td>
                        <td className="px-2.5 py-1.5 text-right font-semibold text-emerald-700">{bench.comparison.recipe_ideal.heat_mins ?? '-'} mnt</td>
                      </tr>
                      <tr className="divide-x divide-slate-100">
                        <td className="px-2.5 py-1.5 font-semibold text-slate-700">Durasi Holding</td>
                        <td className="px-2.5 py-1.5 text-right font-bold bg-blue-50/30">{bench.comparison.current.hold_mins ?? '-'} mnt</td>
                        <td className="px-2.5 py-1.5 text-right text-slate-600">{bench.comparison.historical_avg.hold_mins ?? '-'} mnt</td>
                        <td className="px-2.5 py-1.5 text-right font-semibold text-emerald-700">{bench.comparison.recipe_ideal.hold_mins ?? '-'} mnt</td>
                      </tr>
                      <tr className="divide-x divide-slate-100">
                        <td className="px-2.5 py-1.5 font-semibold text-slate-700">Durasi Cooling</td>
                        <td className="px-2.5 py-1.5 text-right font-bold bg-blue-50/30">{bench.comparison.current.cool_mins ?? '-'} mnt</td>
                        <td className="px-2.5 py-1.5 text-right text-slate-600">{bench.comparison.historical_avg.cool_mins ?? '-'} mnt</td>
                        <td className="px-2.5 py-1.5 text-right font-semibold text-emerald-700">{bench.comparison.recipe_ideal.cool_mins ?? '-'} mnt</td>
                      </tr>
                      <tr className="divide-x divide-slate-100">
                        <td className="px-2.5 py-1.5 font-semibold text-slate-700">Avg Pressure Uap</td>
                        <td className="px-2.5 py-1.5 text-right font-bold bg-blue-50/30">{bench.comparison.current.avg_pressure ?? '-'} bar</td>
                        <td className="px-2.5 py-1.5 text-right text-slate-600">{bench.comparison.historical_avg.avg_pressure ?? '-'} bar</td>
                        <td className="px-2.5 py-1.5 text-right font-semibold text-emerald-700">&ge; {bench.comparison.recipe_ideal.avg_pressure} bar</td>
                      </tr>
                      <tr className="divide-x divide-slate-100 bg-slate-50/60">
                        <td className="px-2.5 py-1.5 font-bold text-slate-800">Pemakaian Steam</td>
                        <td className="px-2.5 py-1.5 text-right font-bold bg-blue-50/30">{numFmt(bench.comparison.current.steam_kg)} kg</td>
                        <td className="px-2.5 py-1.5 text-right text-slate-600">{numFmt(bench.comparison.historical_avg.steam_kg)} kg</td>
                        <td className="px-2.5 py-1.5 text-right font-bold text-emerald-700">{numFmt(bench.comparison.recipe_ideal.steam_kg)} kg</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Right 7 cols: Historical Chart (Heating & Cooling vs Pressure on same Program) */}
              <div className="print-bench-right lg:col-span-7 flex flex-col border border-slate-200/80 rounded-xl p-3.5 bg-gradient-to-b from-white to-slate-50/30 shadow-2xs">
                <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                  <div>
                    <h3 className="text-xs sm:text-sm font-bold text-slate-900">
                      Grafik Riwayat Durasi Heating &amp; Cooling vs Avg Pressure (Program: {bench.program_name})
                    </h3>
                    <p className="text-[11px] text-slate-500">
                      Menampilkan {bench.history_series.length} batch terakhir di mesin <b>{data.machine_name}</b> &mdash; garis putus-putus menunjukkan rata-rata histori
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-1.5 text-[10.5px]">
                    <span className="px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-200 font-bold flex items-center gap-1" title="Klik titik atau bar pada grafik untuk membuka Quick Audit Inspector">
                      <span>💡 Klik titik / bar untuk audit</span>
                    </span>
                    {bench.comparison.historical_avg.heat_mins != null && (
                      <span className="px-2 py-0.5 rounded bg-rose-50 text-rose-800 border border-rose-200 font-semibold">
                        Avg Heat: <b>{bench.comparison.historical_avg.heat_mins} mnt</b>
                      </span>
                    )}
                    {bench.comparison.historical_avg.cool_mins != null && (
                      <span className="px-2 py-0.5 rounded bg-sky-50 text-sky-800 border border-sky-200 font-semibold">
                        Avg Cool: <b>{bench.comparison.historical_avg.cool_mins} mnt</b>
                      </span>
                    )}
                  </div>
                </div>
                <div className="print-chart-box print-bench-chart-box h-[230px] sm:h-[270px] w-full flex-1 min-h-[220px]">
                  <ResponsiveContainer width="100%" height="100%" minHeight={1} minWidth={1}>
                    <ComposedChart
                      data={bench.history_series}
                      margin={{ top: 18, right: 12, left: -15, bottom: 5 }}
                      onClick={(e) => {
                        if (e && e.activePayload && e.activePayload.length > 0) {
                          const payload = e.activePayload[0].payload;
                          if (payload && payload.id) {
                            setInspectorBatch(payload);
                          }
                        }
                      }}
                    >
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                      <XAxis
                        dataKey="label"
                        interval="preserveStartEnd"
                        tick={{ fontSize: 9.5, fill: '#475569' }}
                        axisLine={false}
                        tickLine={false}
                      />
                      <YAxis
                        yAxisId="left"
                        tick={{ fontSize: 10, fill: '#475569' }}
                        axisLine={false}
                        tickLine={false}
                        label={{ value: 'Menit', angle: -90, position: 'insideLeft', offset: 8, style: { fontSize: 10, fill: '#64748b' } }}
                      />
                      <YAxis
                        yAxisId="right"
                        orientation="right"
                        domain={[0, 6]}
                        tick={{ fontSize: 10, fill: '#7c3aed' }}
                        axisLine={false}
                        tickLine={false}
                        label={{ value: 'Bar', angle: 90, position: 'insideRight', offset: 0, style: { fontSize: 10, fill: '#7c3aed' } }}
                      />
                      <RechartsTooltip
                        contentStyle={{ borderRadius: '6px', fontSize: '11px' }}
                        formatter={(val, name, props) => {
                          const suffix = name.includes('Pressure') ? ' bar' : ' mnt';
                          return [`${val}${suffix}`, name];
                        }}
                        labelFormatter={(lbl, payload) => {
                          const item = payload?.[0]?.payload;
                          return item ? `${lbl} (${item.date})${item.is_current ? ' — BATCH SAAT INI' : ''} • Klik untuk audit` : lbl;
                        }}
                      />
                      <Legend wrapperStyle={{ fontSize: '11px', paddingTop: '6px' }} iconType="rect" iconSize={12} />
                      {bench.comparison.historical_avg.heat_mins != null && (
                        <ReferenceLine
                          yAxisId="left"
                          y={bench.comparison.historical_avg.heat_mins}
                          stroke="#e11d48"
                          strokeDasharray="4 3"
                          strokeWidth={1.5}
                        />
                      )}
                      {bench.comparison.historical_avg.cool_mins != null && (
                        <ReferenceLine
                          yAxisId="left"
                          y={bench.comparison.historical_avg.cool_mins}
                          stroke="#0284c7"
                          strokeDasharray="4 3"
                          strokeWidth={1.5}
                        />
                      )}
                      <ReferenceLine yAxisId="right" y={thresholdBar} stroke="#10b981" strokeDasharray="4 4" />
                      <Bar yAxisId="left" dataKey="heat_mins" name="Durasi Heating (mnt)" fill="#f43f5e" radius={[3, 3, 0, 0]} maxBarSize={20} isAnimationActive={false}>
                        {bench.history_series.map((entry, index) => (
                          <Cell
                            key={`heat-${index}`}
                            fill={entry.is_current ? '#be123c' : '#fb7185'}
                            stroke={entry.is_current ? '#1e293b' : 'none'}
                            strokeWidth={entry.is_current ? 1.5 : 0}
                            className="cursor-pointer hover:opacity-80 transition-opacity"
                            onClick={() => setInspectorBatch(entry)}
                          />
                        ))}
                      </Bar>
                      <Bar yAxisId="left" dataKey="cool_mins" name="Durasi Cooling (mnt)" fill="#0ea5e9" radius={[3, 3, 0, 0]} maxBarSize={20} isAnimationActive={false}>
                        {bench.history_series.map((entry, index) => (
                          <Cell
                            key={`cool-${index}`}
                            fill={entry.is_current ? '#0369a1' : '#38bdf8'}
                            stroke={entry.is_current ? '#1e293b' : 'none'}
                            strokeWidth={entry.is_current ? 1.5 : 0}
                            className="cursor-pointer hover:opacity-80 transition-opacity"
                            onClick={() => setInspectorBatch(entry)}
                          />
                        ))}
                      </Bar>
                      <Line
                        yAxisId="right"
                        type="monotone"
                        dataKey="avg_pressure"
                        name="Avg Pressure (bar)"
                        stroke="#7c3aed"
                        strokeWidth={2.5}
                        dot={{ r: 4, fill: '#7c3aed', cursor: 'pointer' }}
                        activeDot={{
                          r: 6.5,
                          fill: '#6d28d9',
                          stroke: '#ffffff',
                          strokeWidth: 2,
                          cursor: 'pointer',
                          onClick: (_, eventPayload) => {
                            if (eventPayload && eventPayload.payload) {
                              setInspectorBatch(eventPayload.payload);
                            }
                          }
                        }}
                        isAnimationActive={false}
                      />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>
          </div>
        ) : (
          <div className={`print-bench-empty-card report-card p-4 sm:p-5 bg-white border border-slate-200/90 rounded-xl shadow-2xs space-y-2 no-print ${(activeMobileTab === "all" || activeMobileTab === "bench") ? "block" : "hidden lg:block print:block"}`}>
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-2.5">
              <div className="flex items-center gap-2">
                <div className="w-7 h-7 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center">
                  <BarChart3 size={15} />
                </div>
                <h3 className="text-xs sm:text-sm font-bold text-slate-800">
                  Analisis Normalitas Mesin &mdash; Komparasi Historis Program
                </h3>
              </div>
              <span className="text-[10.5px] font-bold px-2.5 py-0.5 rounded-full bg-slate-100 text-slate-600 border border-slate-200">
                Data Resep Belum Tersedia
              </span>
            </div>
            <p className="text-xs text-slate-500 leading-relaxed max-w-2xl">
              {identity?.program?.nama
                ? `Belum cukup sampel historis pada mesin ${data.machine_name} di program "${identity.program.nama}" untuk menghitung kurva deviasi normalitas durasi heating & cooling.`
                : `Batch ini belum memiliki tautan Master Program Resep (kartu proses). Komparasi normalitas mesin (durasi heating & cooling vs benchmark program) akan otomatis aktif setelah resep kain ditautkan.`}
            </p>
          </div>
        )}

        {/* ══════════════════════════════════════════════════════════════════════
            4. PENYEBAB TURUNNYA PRESSURE: DEMAND PABRIK vs SPEED BATU BARA BOILER
           ══════════════════════════════════════════════════════════════════════ */}
        {boilerCtx && (
          <div className={`report-card overflow-hidden rounded-2xl print-boiler-section shadow-xs ${(activeMobileTab === "all" || activeMobileTab === "boiler") ? "block" : "hidden lg:block print:block"}`}>

            <div className="px-4 py-3.5 border-b border-slate-200/80 bg-gradient-to-r from-slate-50/90 via-white to-slate-50/90 flex flex-wrap items-center justify-between gap-2.5">
              <div>
                <h2 className="text-sm sm:text-base font-bold text-slate-900 flex items-center gap-2">
                  <Gauge size={17} className="text-purple-600" />
                  Diagnostik Penyebab Fluktuasi / Turunnya Pressure Uap Saat Proses Berlangsung
                </h2>
                <p className="text-xs text-slate-600">
                  Korelasi Tekanan Uap (<code className="text-[11px]">Steam_Pr</code>) terhadap Total Pemakaian Uap Pabrik Saat Itu &amp; Speed Batu Bara Boiler (<code className="text-[11px]">Speed_RB_Steam</code>)
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <span className="px-2.5 py-1 rounded bg-white border border-slate-200 font-semibold text-slate-700">
                  Min Press: <b className={(boilerCtx.min_pressure_bar ?? 5) < thresholdBar ? 'text-rose-600' : 'text-emerald-700'}>{boilerCtx.min_pressure_bar ?? '-'} bar</b> ({boilerCtx.min_pressure_time})
                </span>
                <span className="px-2.5 py-1 rounded bg-white border border-slate-200 font-semibold text-slate-700">
                  Puncak Beban Pabrik: <b>{numFmt(boilerCtx.peak_plant_demand_kg_h, 0)} kg/jam</b> ({boilerCtx.peak_active_machines} mesin)
                </span>
              </div>
            </div>

            <div className="p-3 sm:p-4 space-y-3 sm:space-y-4">
              {/* Diagnosis Banner */}
              <div className={`rounded-xl border p-3.5 ${TONE_BOX[boilerCtx.diagnosis.tone] || TONE_BOX.emerald}`}>
                <div className="flex flex-wrap items-center justify-between gap-2 mb-1.5">
                  <div className="font-bold text-xs sm:text-sm flex items-center gap-2">
                    <AlertTriangle size={15} />
                    Kesimpulan Penyebab Tekanan Uap: {boilerCtx.diagnosis.title}
                  </div>
                  <span className={`text-[10px] font-bold px-2 py-0.5 rounded uppercase ${TONE_BADGE[boilerCtx.diagnosis.tone] || TONE_BADGE.emerald}`}>
                    {boilerCtx.low_pressure_pct > 0 ? `${boilerCtx.low_pressure_pct}% Durasi < ${thresholdBar} Bar` : '100% Sehat'}
                  </span>
                </div>
                <p className="text-xs leading-relaxed mb-2">{boilerCtx.diagnosis.detail}</p>
                <div className="bg-white/80 rounded-lg px-3 py-2 border border-black/10 text-xs">
                  <strong className="font-bold">Rekomendasi Keputusan: </strong>
                  {boilerCtx.diagnosis.action}
                </div>
              </div>

              {/* 2 Charts Side-by-Side */}
              <div className="print-2col-grid grid grid-cols-1 lg:grid-cols-2 gap-4">
                {/* Chart A: Pressure vs Plant Steam Demand */}
                <div className="border border-slate-200/80 rounded-xl p-3.5 bg-white flex flex-col shadow-2xs">
                  <div className="mb-2">
                    <h3 className="text-xs sm:text-sm font-bold text-slate-900">
                      1. Grafik Tekanan Uap (bar) vs Total Beban Uap Pabrik Saat Itu (kg/jam)
                    </h3>
                    <p className="text-[11px] text-slate-500">
                      Menunjukkan apakah turunnya pressure disebabkan oleh lonjakan pemakaian uap serentak di pabrik
                    </p>
                  </div>
                  <div className="print-chart-box print-boiler-chart-box h-[200px] sm:h-[240px] w-full">
                    <ResponsiveContainer width="100%" height="100%" minHeight={1} minWidth={1}>
                      <ComposedChart data={chart_data} margin={{ top: 16, right: 10, left: -10, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                        <XAxis dataKey="time" tick={{ fontSize: 10, fill: '#64748b' }} axisLine={false} tickLine={false} minTickGap={25} />
                        <YAxis
                          yAxisId="left"
                          tick={{ fontSize: 10, fill: '#0284c7' }}
                          axisLine={false}
                          tickLine={false}
                          label={{ value: 'kg/jam', angle: -90, position: 'insideLeft', offset: 8, style: { fontSize: 10, fill: '#0284c7' } }}
                        />
                        <YAxis
                          yAxisId="right"
                          orientation="right"
                          domain={[0, 6]}
                          tick={{ fontSize: 10, fill: '#7c3aed' }}
                          axisLine={false}
                          tickLine={false}
                          label={{ value: 'Bar', angle: 90, position: 'insideRight', offset: 0, style: { fontSize: 10, fill: '#7c3aed' } }}
                        />
                        <RechartsTooltip
                          contentStyle={{ borderRadius: '6px', fontSize: '11px' }}
                          formatter={(val, name, props) => {
                            if (name.includes('Beban')) {
                              const mc = props?.payload?.active_steam_machines;
                              return [`${numFmt(val, 0)} kg/jam (${mc || 0} mesin aktif)`, name];
                            }
                            return [`${val} bar`, name];
                          }}
                        />
                        <Legend wrapperStyle={{ fontSize: '11px', paddingTop: '4px' }} iconType="rect" iconSize={12} />
                        <ReferenceLine yAxisId="right" y={thresholdBar} stroke="#ef4444" strokeDasharray="4 4" />
                        <Area
                          yAxisId="left"
                          type="monotone"
                          dataKey="plant_steam_kg_h"
                          name="Beban Uap Pabrik (kg/jam)"
                          fill="#bae6fd"
                          stroke="#0284c7"
                          strokeWidth={1.75}
                          fillOpacity={0.45}
                          isAnimationActive={false}
                        />
                        <Line
                          yAxisId="right"
                          type="monotone"
                          dataKey="pressure"
                          name="Tekanan Uap (bar)"
                          stroke="#7c3aed"
                          strokeWidth={2.2}
                          dot={false}
                          isAnimationActive={false}
                        />
                      </ComposedChart>
                    </ResponsiveContainer>
                  </div>
                </div>

                {/* Chart B: Pressure vs Boiler Coal Speed */}
                <div className="border border-slate-200/80 rounded-xl p-3.5 bg-white flex flex-col shadow-2xs">
                  <div className="mb-2">
                    <h3 className="text-xs sm:text-sm font-bold text-slate-900">
                      2. Grafik Tekanan Uap (bar) vs Speed Batu Bara Boiler Steam (Hz)
                    </h3>
                    <p className="text-[11px] text-slate-500">
                      Menunjukkan respons umpan batu bara boiler (<code className="text-[10px]">Speed_RB_Steam</code>) saat tekanan berfluktuasi
                    </p>
                  </div>
                  <div className="print-chart-box print-boiler-chart-box h-[200px] sm:h-[240px] w-full">
                    <ResponsiveContainer width="100%" height="100%" minHeight={1} minWidth={1}>
                      <ComposedChart data={chart_data} margin={{ top: 16, right: 10, left: -10, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                        <XAxis dataKey="time" tick={{ fontSize: 10, fill: '#64748b' }} axisLine={false} tickLine={false} minTickGap={25} />
                        <YAxis
                          yAxisId="left"
                          tick={{ fontSize: 10, fill: '#d97706' }}
                          axisLine={false}
                          tickLine={false}
                          label={{ value: 'Speed (Hz)', angle: -90, position: 'insideLeft', offset: 8, style: { fontSize: 10, fill: '#d97706' } }}
                        />
                        <YAxis
                          yAxisId="right"
                          orientation="right"
                          domain={[0, 6]}
                          tick={{ fontSize: 10, fill: '#7c3aed' }}
                          axisLine={false}
                          tickLine={false}
                          label={{ value: 'Bar', angle: 90, position: 'insideRight', offset: 0, style: { fontSize: 10, fill: '#7c3aed' } }}
                        />
                        <RechartsTooltip
                          contentStyle={{ borderRadius: '6px', fontSize: '11px' }}
                          formatter={(val, name, props) => {
                            if (name.includes('Speed')) {
                              const kgH = props?.payload?.coal_feed_kg_h;
                              return [
                                `${val ?? '-'} Hz${kgH != null ? ` (${kgH} kg/jam batu bara)` : ''}`,
                                name,
                              ];
                            }
                            return [`${val} bar`, name];
                          }}
                        />
                        <Legend wrapperStyle={{ fontSize: '11px', paddingTop: '4px' }} iconType="rect" iconSize={12} />
                        <ReferenceLine yAxisId="right" y={thresholdBar} stroke="#ef4444" strokeDasharray="4 4" />
                        <Area
                          yAxisId="left"
                          type="monotone"
                          dataKey="coal_speed_hz"
                          name="Speed Batu Bara (Hz)"
                          fill="#fde68a"
                          stroke="#d97706"
                          strokeWidth={1.75}
                          fillOpacity={0.45}
                          isAnimationActive={false}
                        />
                        <Line
                          yAxisId="right"
                          type="monotone"
                          dataKey="pressure"
                          name="Tekanan Uap (bar)"
                          stroke="#7c3aed"
                          strokeWidth={2.2}
                          dot={false}
                          isAnimationActive={false}
                        />
                      </ComposedChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ══════════════════════════════════════════════════════════════════════
            4.B DIAGNOSTIK ANOMALI PROSES COOLING: KORELASI GRADIEN vs BEBAN MESIN COOLING BERSAMAAN
           ══════════════════════════════════════════════════════════════════════ */}
        {coolingCtx && (
          <div className={`report-card overflow-hidden print-boiler-section print-cooling-section ${(activeMobileTab === "all" || activeMobileTab === "cooling") ? "block" : "hidden lg:block print:block"}`}>

            <div className="px-4 py-3.5 border-b border-slate-200/80 bg-gradient-to-r from-cyan-50/80 via-white to-cyan-50/40 flex flex-wrap items-center justify-between gap-2.5">
              <div>
                <h2 className="text-sm sm:text-base font-bold text-slate-900 flex items-center gap-2">
                  <Droplets size={17} className="text-cyan-600" />
                  Diagnostik Anomali Proses Cooling: Korelasi Gradien Suhu vs Beban Mesin Cooling Bersamaan
                </h2>
                <p className="text-xs text-slate-600">
                  Korelasi Laju Penurunan Suhu (<code className="text-[11px]">|dT/dt| °C/menit</code>) terhadap Jumlah Mesin Pencelupan yang Cooling Serentak (Penggunaan Air Pendingin)
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <span className="px-2.5 py-1 rounded bg-white border border-slate-200 font-semibold text-slate-700">
                  Laju Rata-rata: <b className={(coolingCtx.avg_cooling_gradient ?? 1.5) < 1.0 ? 'text-rose-600' : 'text-cyan-700'}>{coolingCtx.avg_cooling_gradient ?? '-'} °C/mnt</b>
                </span>
                <span className="px-2.5 py-1 rounded bg-white border border-slate-200 font-semibold text-slate-700">
                  Puncak Cooling Pabrik: <b>{coolingCtx.peak_concurrent_machines} mesin</b> ({coolingCtx.peak_concurrent_time})
                </span>
                <span className="px-2.5 py-1 rounded bg-white border border-slate-200 font-semibold text-slate-700">
                  Durasi Cooling: <b>{coolingCtx.cooling_duration_mins} mnt</b>
                  {coolingCtx.cooling_ideal_mins ? (
                    <span className="text-slate-500 font-normal"> (target: {coolingCtx.cooling_ideal_mins}m)</span>
                  ) : null}
                </span>
              </div>
            </div>

            <div className="p-3 sm:p-4 space-y-3 sm:space-y-4">
              {/* Diagnosis Banner */}
              <div className={`rounded-xl border p-3.5 ${TONE_BOX[coolingCtx.diagnosis?.tone] || TONE_BOX.emerald}`}>
                <div className="flex flex-wrap items-center justify-between gap-2 mb-1.5">
                  <div className="font-bold text-xs sm:text-sm flex items-center gap-2">
                    <AlertTriangle size={15} />
                    Kesimpulan Diagnostik Cooling: {coolingCtx.diagnosis?.title}
                  </div>
                  <span className={`text-[10px] font-bold px-2 py-0.5 rounded uppercase ${TONE_BADGE[coolingCtx.diagnosis?.tone] || TONE_BADGE.emerald}`}>
                    {coolingCtx.diagnosis?.tone === 'emerald'
                      ? '100% Sehat'
                      : coolingCtx.overrun_mins > 0
                        ? `Molor +${coolingCtx.overrun_mins} Menit`
                        : 'Perlu Perhatian'}
                  </span>
                </div>
                <p className="text-xs leading-relaxed mb-2">{coolingCtx.diagnosis?.detail}</p>
                <div className="bg-white/80 rounded-lg px-3 py-2 border border-black/10 text-xs">
                  <strong className="font-bold">Rekomendasi Keputusan: </strong>
                  {coolingCtx.diagnosis?.action}
                </div>
              </div>

              {/* 2 Charts Side-by-Side */}
              <div className="print-2col-grid grid grid-cols-1 lg:grid-cols-2 gap-4">
                {/* Chart 1: Cooling Rate (|dT/dt|) vs Concurrent Cooling Machines */}
                <div className="border border-slate-200/80 rounded-xl p-3.5 bg-white flex flex-col shadow-2xs">
                  <div className="mb-2">
                    <h3 className="text-xs sm:text-sm font-bold text-slate-900">
                      1. Grafik Laju Cooling (°C/menit) vs Beban Mesin Cooling Bersamaan
                    </h3>
                    <p className="text-[11px] text-slate-500">
                      Menunjukkan apakah drop laju pendinginan bertepatan dengan lonjakan mesin lain yang membuka katup air pendingin
                    </p>
                  </div>
                  <div className="print-chart-box print-boiler-chart-box h-[200px] sm:h-[240px] w-full">
                    <ResponsiveContainer width="100%" height="100%" minHeight={1} minWidth={1}>
                      <ComposedChart
                        data={coolingCtx.cooling_chart_data || []}
                        margin={{ top: 16, right: 10, left: -10, bottom: 0 }}
                      >
                        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                        <XAxis
                          dataKey="time"
                          tick={{ fontSize: 10, fill: '#64748b' }}
                          axisLine={false}
                          tickLine={false}
                          minTickGap={20}
                        />
                        <YAxis
                          yAxisId="left"
                          tick={{ fontSize: 10, fill: '#0891b2' }}
                          axisLine={false}
                          tickLine={false}
                          label={{
                            value: '°C/menit',
                            angle: -90,
                            position: 'insideLeft',
                            offset: 8,
                            style: { fontSize: 10, fill: '#0891b2' },
                          }}
                        />
                        <YAxis
                          yAxisId="right"
                          orientation="right"
                          allowDecimals={false}
                          tick={{ fontSize: 10, fill: '#0284c7' }}
                          axisLine={false}
                          tickLine={false}
                          label={{
                            value: 'Mesin',
                            angle: 90,
                            position: 'insideRight',
                            offset: 0,
                            style: { fontSize: 10, fill: '#0284c7' },
                          }}
                        />
                        <RechartsTooltip
                          contentStyle={{ borderRadius: '6px', fontSize: '11px' }}
                          formatter={(val, name) => {
                            if (name && name.includes('Mesin')) {
                              return [`${val} mesin`, name];
                            }
                            return [`${val} °C/menit`, name];
                          }}
                        />
                        <Legend wrapperStyle={{ fontSize: '11px', paddingTop: '4px' }} iconType="rect" iconSize={12} />
                        {coolingCtx.ideal_cooling_gradient ? (
                          <ReferenceLine
                            yAxisId="left"
                            y={coolingCtx.ideal_cooling_gradient}
                            stroke="#ef4444"
                            strokeDasharray="4 4"
                            label={{
                              value: `Target: ${coolingCtx.ideal_cooling_gradient}°C/m`,
                              position: 'insideTopLeft',
                              fontSize: 9,
                              fill: '#ef4444',
                            }}
                          />
                        ) : null}
                        <Area
                          yAxisId="right"
                          type="monotone"
                          dataKey="active_cooling_machines"
                          name="Mesin Cooling Serentak (unit)"
                          fill="#cffafe"
                          stroke="#06b6d4"
                          strokeWidth={1.75}
                          fillOpacity={0.45}
                          isAnimationActive={false}
                        />
                        <Line
                          yAxisId="left"
                          type="monotone"
                          dataKey="cooling_rate"
                          name="Laju Cooling Aktual (°C/mnt)"
                          stroke="#0891b2"
                          strokeWidth={2.2}
                          dot={false}
                          isAnimationActive={false}
                        />
                      </ComposedChart>
                    </ResponsiveContainer>
                  </div>
                </div>

                {/* Chart 2: Machine Temp vs Concurrent Cooling Machines */}
                <div className="border border-slate-200/80 rounded-xl p-3.5 bg-white flex flex-col shadow-2xs">
                  <div className="mb-2">
                    <h3 className="text-xs sm:text-sm font-bold text-slate-900">
                      2. Grafik Penurunan Suhu Mesin (°C) vs Beban Mesin Cooling Bersamaan
                    </h3>
                    <p className="text-[11px] text-slate-500">
                      Menunjukkan apakah kurva penurunan suhu melandai/stagnan saat jumlah mesin cooling di pabrik tinggi
                    </p>
                  </div>
                  <div className="print-chart-box print-boiler-chart-box h-[200px] sm:h-[240px] w-full">
                    <ResponsiveContainer width="100%" height="100%" minHeight={1} minWidth={1}>
                      <ComposedChart
                        data={coolingCtx.cooling_chart_data || []}
                        margin={{ top: 16, right: 10, left: -10, bottom: 0 }}
                      >
                        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                        <XAxis
                          dataKey="time"
                          tick={{ fontSize: 10, fill: '#64748b' }}
                          axisLine={false}
                          tickLine={false}
                          minTickGap={20}
                        />
                        <YAxis
                          yAxisId="left"
                          domain={[30, 'auto']}
                          tick={{ fontSize: 10, fill: '#6366f1' }}
                          axisLine={false}
                          tickLine={false}
                          label={{
                            value: 'Suhu (°C)',
                            angle: -90,
                            position: 'insideLeft',
                            offset: 8,
                            style: { fontSize: 10, fill: '#6366f1' },
                          }}
                        />
                        <YAxis
                          yAxisId="right"
                          orientation="right"
                          allowDecimals={false}
                          tick={{ fontSize: 10, fill: '#0284c7' }}
                          axisLine={false}
                          tickLine={false}
                          label={{
                            value: 'Mesin',
                            angle: 90,
                            position: 'insideRight',
                            offset: 0,
                            style: { fontSize: 10, fill: '#0284c7' },
                          }}
                        />
                        <RechartsTooltip
                          contentStyle={{ borderRadius: '6px', fontSize: '11px' }}
                          formatter={(val, name) => {
                            if (name && name.includes('Mesin')) {
                              return [`${val} mesin`, name];
                            }
                            return [`${val} °C`, name];
                          }}
                        />
                        <Legend wrapperStyle={{ fontSize: '11px', paddingTop: '4px' }} iconType="rect" iconSize={12} />
                        <ReferenceLine
                          yAxisId="left"
                          y={70}
                          stroke="#f59e0b"
                          strokeDasharray="4 4"
                          label={{
                            value: 'Batas 70°C',
                            position: 'insideBottomRight',
                            fontSize: 9,
                            fill: '#d97706',
                          }}
                        />
                        <Area
                          yAxisId="right"
                          type="monotone"
                          dataKey="active_cooling_machines"
                          name="Mesin Cooling Serentak (unit)"
                          fill="#cffafe"
                          stroke="#06b6d4"
                          strokeWidth={1.75}
                          fillOpacity={0.45}
                          isAnimationActive={false}
                        />
                        <Line
                          yAxisId="left"
                          type="monotone"
                          dataKey="temp"
                          name="Suhu Aktual (°C)"
                          stroke="#6366f1"
                          strokeWidth={2.2}
                          dot={false}
                          isAnimationActive={false}
                        />
                      </ComposedChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ══════════════════════════════════════════════════════════════════════
            5. FORENSIK ANOMALI PROSES & INDIKASI PERILAKU OPERATOR
           ══════════════════════════════════════════════════════════════════════ */}
        {forensics && forensics.length > 0 && (
          <div className={`report-card overflow-hidden print-forensics-section ${(activeMobileTab === "all" || activeMobileTab === "bench") ? "block" : "hidden lg:block print:block"}`}>

            <div className="px-4 py-3.5 border-b border-slate-200/80 bg-gradient-to-r from-rose-50/60 via-white to-slate-50/80 flex flex-wrap items-center justify-between gap-2.5">
              <div>
                <h2 className="text-sm sm:text-base font-bold text-slate-900 flex items-center gap-2">
                  <UserCheck size={17} className="text-rose-600" />
                  Forensik Anomali Proses &amp; Evaluasi Kedisiplinan Operator
                </h2>
                <p className="text-xs text-slate-600">
                  Operator Bertugas: <strong className="text-slate-900">{identity.operator}</strong> &bull; Evaluasi terhadap over-holding, durasi pasca-cooling &gt;45 menit, dan anomali kurva
                </p>
              </div>
            </div>

            <div className="print-2col-grid p-4 grid grid-cols-1 md:grid-cols-2 gap-3">
              {forensics.map((f, idx) => {
                const st = SEVERITY_STYLE[f.severity] || SEVERITY_STYLE.INFO;
                return (
                  <div key={`${f.code}-${idx}`} className={`rounded-xl border p-3.5 flex flex-col justify-between ${st.box}`}>
                    <div>
                      <div className="flex items-center justify-between gap-2 mb-1.5">
                        <span className={`text-[10px] font-bold px-2 py-0.5 rounded uppercase ${st.badge}`}>
                          {f.severity} &bull; {f.category}
                        </span>
                      </div>
                      <h3 className={`text-xs sm:text-sm font-bold mb-1 ${st.title}`}>{f.title}</h3>
                      <p className="text-xs text-slate-700 leading-relaxed mb-2">{f.detail}</p>
                    </div>
                    <div className="space-y-1.5 pt-2 border-t border-black/10 text-[11px]">
                      <div className="text-rose-800">
                        <strong className="font-bold">Dampak Kerugian: </strong>
                        {f.impact}
                      </div>
                      <div className="bg-white/85 rounded px-2.5 py-1.5 border border-black/10 text-emerald-900">
                        <strong className="font-bold">Tindak Lanjut / Perbaikan: </strong>
                        {f.recommendation}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* ══════════════════════════════════════════════════════════════════════
            6. PROFIL KURVA SUHU & TEKANAN BATCH + IDENTITAS & DETAIL FASE
           ══════════════════════════════════════════════════════════════════════ */}
        <div className={`process-report-grid grid grid-cols-1 lg:grid-cols-12 items-stretch gap-3 ${(activeMobileTab === "all" || activeMobileTab === "curve") ? "grid" : "hidden lg:grid print:grid"}`}>

          {/* Left: Identity & Timing */}
          <div className="lg:col-span-5 space-y-3">
            <div className="report-card overflow-hidden">
              <div className="border-b border-indigo-100/90 bg-gradient-to-r from-indigo-50/80 via-white to-indigo-50/40 px-3.5 py-2.5 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="w-6 h-6 rounded-md bg-indigo-100/80 text-indigo-700 flex items-center justify-center shrink-0">
                    <FileText size={14} />
                  </div>
                  <div>
                    <h3 className="text-xs sm:text-sm font-bold text-slate-900 leading-tight">
                      Identitas Kain &amp; Waktu Siklus
                    </h3>
                    {data.identity_id && (
                      <span className="text-[10px] text-slate-500 font-mono">
                        Admin ID: #{data.identity_id}
                      </span>
                    )}
                  </div>
                </div>

                {data.identity_id ? (
                  <a
                    href={`${BACKEND_BASE_URL}/admin/monitoring/dyeingidentity/${data.identity_id}/change/`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="no-print inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-white hover:bg-amber-50 text-amber-900 border border-amber-300/80 text-[11px] font-bold shadow-2xs hover:shadow-xs hover:border-amber-400 transition-all cursor-pointer group"
                    title={`Koreksi Data Batch #${data.batch_number} di Django Admin (ID: ${data.identity_id}) - Buka tab baru`}
                  >
                    <Wrench size={12} className="text-amber-700 group-hover:rotate-12 transition-transform" />
                    <span>Koreksi di Admin</span>
                    <ExternalLink size={10} className="text-amber-600 opacity-70 group-hover:opacity-100 transition-opacity" />
                  </a>
                ) : (
                  <a
                    href={getAdminAddUrl()}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="no-print inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-white hover:bg-amber-50 text-amber-900 border border-amber-300/80 text-[11px] font-bold shadow-2xs hover:shadow-xs hover:border-amber-400 transition-all cursor-pointer group"
                    title="Input identitas batch baru di Django Admin - Buka tab baru"
                  >
                    <Wrench size={12} className="text-amber-700 group-hover:rotate-12 transition-transform" />
                    <span>Input di Admin</span>
                    <ExternalLink size={10} className="text-amber-600 opacity-70 group-hover:opacity-100 transition-opacity" />
                  </a>
                )}
              </div>

              <div className="grid grid-cols-2 gap-2.5 p-3 text-xs bg-slate-50/30">
                <div className="bg-white p-2.5 rounded-xl border border-slate-200/70 shadow-2xs">
                  <span className="report-label mb-0.5 block text-[10px] uppercase tracking-wider text-slate-400 font-bold">Order / Warna</span>
                  <span className="font-semibold text-slate-900">{identity.nomor_order} / {identity.nomor_warna}</span>
                </div>
                <div className="bg-white p-2.5 rounded-xl border border-slate-200/70 shadow-2xs">
                  <span className="report-label mb-0.5 block text-[10px] uppercase tracking-wider text-slate-400 font-bold">Batch Kain</span>
                  <span className="font-semibold text-slate-900 font-mono">{identity.batch}</span>
                </div>
                <div className="bg-white p-2.5 rounded-xl border border-slate-200/70 shadow-2xs">
                  <span className="report-label mb-0.5 block text-[10px] uppercase tracking-wider text-slate-400 font-bold">Operator</span>
                  <span className="font-semibold text-slate-900">{identity.operator}</span>
                </div>
                <div className="bg-white p-2.5 rounded-xl border border-slate-200/70 shadow-2xs">
                  <span className="report-label mb-0.5 block text-[10px] uppercase tracking-wider text-slate-400 font-bold">Buyer</span>
                  <span className="font-semibold text-slate-900">{identity.kode_buyer}</span>
                </div>
                <div className="col-span-2 bg-white p-2.5 rounded-xl border border-slate-200/70 shadow-2xs">
                  <span className="report-label mb-0.5 block text-[10px] uppercase tracking-wider text-slate-400 font-bold">Artikel Kain</span>
                  <span className="font-semibold text-slate-900">{identity.artikel_kain}</span>
                </div>
                <div className="bg-white p-2.5 rounded-xl border border-slate-200/70 shadow-2xs">
                  <span className="report-label mb-0.5 block text-[10px] uppercase tracking-wider text-slate-400 font-bold">Isi / Tube (Output)</span>
                  <span className="font-semibold text-slate-900">
                    {identity.isi_per_tube} {identity.output_yard !== '-' ? `(${identity.output_yard} yd)` : ''}
                  </span>
                </div>
                <div className="bg-white p-2.5 rounded-xl border border-slate-200/70 shadow-2xs">
                  <span className="report-label mb-0.5 block text-[10px] uppercase tracking-wider text-slate-400 font-bold">Nozzle / Main Pump</span>
                  <span className="font-semibold text-slate-900 font-mono">{identity.nozzle_main_pump || '-'}</span>
                </div>
                <div className="bg-white p-2.5 rounded-xl border border-slate-200/70 shadow-2xs">
                  <span className="report-label mb-0.5 block text-[10px] uppercase tracking-wider text-slate-400 font-bold">Cycle 60</span>
                  <span className="font-semibold text-slate-900 font-mono">{identity.cycle_60 || '-'}</span>
                </div>
                <div className="bg-white p-2.5 rounded-xl border border-slate-200/70 shadow-2xs">
                  <span className="report-label mb-0.5 block text-[10px] uppercase tracking-wider text-slate-400 font-bold">Cycle Puncak</span>
                  <span className="font-semibold text-slate-900 font-mono">{identity.cycle_puncak || '-'}</span>
                </div>
                <div className="col-span-2 bg-white p-2.5 rounded-xl border border-slate-200/70 shadow-2xs">
                  <span className="report-label mb-0.5 block text-[10px] uppercase tracking-wider text-slate-400 font-bold">Tercapai &lt;70°C (Cool End)</span>
                  <span className="font-semibold text-slate-900 font-mono text-[11px]">{formatBackendDate(identity.reached_70c_time)}</span>
                </div>
              </div>
            </div>

            <div className="report-card overflow-hidden">
              <div className="border-b border-indigo-100/90 bg-gradient-to-r from-indigo-50/80 via-white to-indigo-50/40 px-3.5 py-2.5 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="w-6 h-6 rounded-md bg-indigo-100/80 text-indigo-700 flex items-center justify-center shrink-0">
                    <Activity size={14} />
                  </div>
                  <h3 className="text-xs sm:text-sm font-bold text-slate-900">Detail Fase &amp; Parameter Termal</h3>
                </div>
              </div>
              <div className="p-3 space-y-2 text-xs">
                {[
                  { label: 'Heating (Rise Time)', actual: timing.heat_actual, ideal: timing.heat_ideal, grad: timing.heat_gradient ? `+${timing.heat_gradient}°C/m` : null },
                  { label: 'Holding / Keeping', actual: timing.hold_actual, ideal: timing.keep_ideal, grad: timing.over_hold_mins > 0 ? `Over +${timing.over_hold_mins}m` : null },
                  { label: 'Cooling', actual: timing.cool_actual, ideal: timing.cool_ideal, grad: timing.cool_gradient ? `${timing.cool_gradient}°C/m` : null },
                ].map(({ label, actual, ideal, grad }) => {
                  const delta = actual != null && ideal != null ? actual - ideal : null;
                  return (
                    <div
                      key={label}
                      className="flex items-center justify-between rounded border border-slate-200/80 bg-slate-50 px-2.5 py-2"
                    >
                      <div>
                        <span className="font-bold text-slate-800">{label}</span>
                        {grad && <span className="ml-2 text-[10px] font-semibold text-slate-500">({grad})</span>}
                      </div>
                      <span className="report-data font-bold text-slate-900">
                        {actual ?? 0}m
                        <span className="ml-1.5 text-[11px] font-normal text-slate-500">
                          (Ideal: {ideal ?? 0}m)
                        </span>
                        {delta != null && delta !== 0 && (
                          <span className={`ml-1.5 text-[11px] font-bold ${delta > 0 ? 'text-rose-600' : 'text-emerald-600'}`}>
                            {delta > 0 ? `+${delta}m` : `${delta}m`}
                          </span>
                        )}
                      </span>
                    </div>
                  );
                })}

                <div className="grid grid-cols-3 gap-2 pt-1">
                  <div className="rounded border border-slate-200 bg-white p-2">
                    <span className="report-label block">Suhu Awal</span>
                    <div className="report-data mt-0.5 text-sm font-bold text-slate-900">
                      {timing.start_temp != null ? `${timing.start_temp}°C` : '-'}
                    </div>
                  </div>
                  <div className="rounded border border-slate-200 bg-white p-2">
                    <span className="report-label block">Peak Temp</span>
                    <div className="report-data mt-0.5 text-sm font-bold text-rose-600">
                      {timing.peak_temp ?? '-'}°C
                      <span className="block text-[9.5px] font-normal text-slate-500">
                        Prg: {timing.max_temp_prg ?? '-'}°C
                      </span>
                    </div>
                  </div>
                  <div className="rounded border border-slate-200 bg-white p-2">
                    <span className="report-label block">Keluar-Masuk Kain</span>
                    <div className={`report-data mt-0.5 text-sm font-bold ${(timing.late_stop_mins || 0) > 45 ? 'text-rose-600' : 'text-emerald-700'}`}>
                      {timing.late_stop_mins != null ? `${timing.late_stop_mins} mnt` : '-'}
                      <span className="block text-[9.5px] font-normal text-slate-500">
                        &lt;70°C s/d OFF (&le;45m)
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {(identity.masalah || identity.keterangan) && (
              <div className="space-y-2">
                {identity.masalah && (
                  <div className="report-card !border-rose-200 !bg-rose-50 p-3">
                    <h4 className="mb-1 text-xs font-bold uppercase tracking-wider text-rose-800">Catatan Masalah Operator</h4>
                    <p className="text-xs text-rose-900">{identity.masalah}</p>
                  </div>
                )}
                {identity.keterangan && (
                  <div className="report-card !border-blue-200 !bg-blue-50 p-3">
                    <h4 className="mb-1 text-xs font-bold uppercase tracking-wider text-blue-800">Keterangan</h4>
                    <p className="text-xs text-blue-900">{identity.keterangan}</p>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Right: Main Temperature & Pressure Profile Chart */}
          <div className="lg:col-span-7 flex flex-col">
            <div className="process-report-chart-container report-card flex flex-col overflow-hidden flex-1 min-h-[340px] sm:min-h-[380px]">
              <div className="border-b border-slate-200 px-3.5 py-2.5 flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h2 className="text-sm sm:text-base font-bold text-slate-900">
                    Kurva Suhu Aktual Mesin (°C) vs Tekanan Uap (bar)
                  </h2>
                  <p className="text-[11px] text-slate-500">
                    Garis putus-putus hijau menandakan batas minimum tekanan uap sehat ({thresholdBar} bar)
                  </p>
                </div>
                {phases && Object.keys(phases).length > 0 && (
                  <div className="report-data flex flex-wrap gap-2.5 text-[10.5px] font-semibold">
                    <span className="inline-flex items-center gap-1 text-rose-600">
                      <Flame size={12} /> Heat ({phases.heat || 0}%)
                    </span>
                    <span className="inline-flex items-center gap-1 text-orange-600">
                      <PauseCircle size={12} /> Hold ({phases.hold || 0}%)
                    </span>
                    <span className="inline-flex items-center gap-1 text-sky-600">
                      <Snowflake size={12} /> Cool ({phases.cooling || 0}%)
                    </span>
                  </div>
                )}
              </div>

              <div className="print-chart-box print-main-chart-box min-h-[260px] sm:min-h-[320px] h-[280px] sm:h-full w-full flex-1 p-1 sm:p-2.5">
                <ResponsiveContainer width="100%" height="100%" minHeight={1} minWidth={1}>
                  <LineChart data={chart_data} margin={{ top: 16, right: 10, left: -15, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="5 5" vertical={false} stroke="#e2e8f0" />
                    <XAxis
                      dataKey="time"
                      tick={{ fontSize: 10, fill: '#64748b' }}
                      axisLine={false}
                      tickLine={false}
                      interval="preserveStartEnd"
                      minTickGap={28}
                    />
                    <YAxis
                      yAxisId="left"
                      domain={[0, 'auto']}
                      tick={{ fontSize: 10, fill: '#64748b' }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <YAxis
                      yAxisId="right"
                      orientation="right"
                      domain={[0, 6]}
                      tick={{ fontSize: 10, fill: '#64748b' }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <RechartsTooltip
                      contentStyle={{
                        borderRadius: '6px',
                        border: 'none',
                        background: '#1e293b',
                        color: '#fff',
                        fontSize: '11.5px',
                      }}
                      labelStyle={{ color: '#fff', fontWeight: 'bold' }}
                      itemStyle={{ color: '#fff' }}
                    />
                    <Legend wrapperStyle={{ fontSize: '11px', paddingTop: '6px' }} iconType="rect" iconSize={12} />
                    <ReferenceLine yAxisId="right" y={thresholdBar} stroke="#10b981" strokeDasharray="4 4" />
                    <Line
                      yAxisId="left"
                      type="monotone"
                      dataKey="temp"
                      name="Suhu Mesin (°C)"
                      stroke="#e11d48"
                      strokeWidth={2.3}
                      dot={false}
                      isAnimationActive={false}
                    />
                    <Line
                      yAxisId="right"
                      type="monotone"
                      dataKey="pressure"
                      name="Tekanan Steam (bar)"
                      stroke="#7c3aed"
                      strokeWidth={1.9}
                      strokeDasharray="5 4"
                      dot={false}
                      isAnimationActive={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ══════════════════════════════════════════════════════════════════════
          QUICK AUDIT INSPECTOR MODAL (CLICK-TO-INVESTIGATE BATCH HISTORIS)
         ══════════════════════════════════════════════════════════════════════ */}
      {inspectorBatch && (() => {
        const avgHeat = bench?.comparison?.historical_avg?.heat_mins;
        const avgCool = bench?.comparison?.historical_avg?.cool_mins;
        const heatDiff = avgHeat != null && inspectorBatch?.heat_mins != null ? Math.round(inspectorBatch.heat_mins - avgHeat) : null;
        const coolDiff = avgCool != null && inspectorBatch?.cool_mins != null ? Math.round(inspectorBatch.cool_mins - avgCool) : null;

        let statusPill = { label: 'OPTIMAL / SESUAI BASELINE', bg: 'bg-emerald-50 text-emerald-800 border-emerald-200', dot: 'bg-emerald-500' };
        let diagnosticSummary = 'Durasi pemanasan dan pendinginan berada dalam batas toleransi normal histori program.';

        if (heatDiff != null && heatDiff > 25) {
          if (inspectorBatch.avg_pressure != null && inspectorBatch.avg_pressure < thresholdBar) {
            statusPill = { label: 'CRITICAL: BOILER STEAM SAG', bg: 'bg-rose-50 text-rose-800 border-rose-200', dot: 'bg-rose-500' };
            diagnosticSummary = `Pemanasan molor ekstrem (+${heatDiff} mnt vs baseline) teridentifikasi akibat pasokan uap boiler drop (${inspectorBatch.avg_pressure} bar < ${thresholdBar} bar).`;
          } else {
            statusPill = { label: 'WARNING: DEGRADASI MEKANIK / KERAK HE', bg: 'bg-amber-50 text-amber-800 border-amber-200', dot: 'bg-amber-500' };
            diagnosticSummary = `Pemanasan molor (+${heatDiff} mnt) padahal tekanan uap stabil (${inspectorBatch.avg_pressure ?? '-'} bar). Indikasi kerak pada penukar panas atau katup uap internal.`;
          }
        } else if (coolDiff != null && coolDiff > 15) {
          statusPill = { label: 'WARNING: COOLING OVERRUN', bg: 'bg-sky-50 text-sky-800 border-sky-200', dot: 'bg-sky-500' };
          diagnosticSummary = `Proses pendinginan molor (+${coolDiff} mnt). Terindikasi debit air pendingin kurang lancar atau suhu pasokan air pendingin tinggi.`;
        }

        return (
          <div
            className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4 bg-slate-900/60 backdrop-blur-xs no-print animate-in fade-in duration-150"
            onClick={() => setInspectorBatch(null)}
          >
            <div
              className="bg-white rounded-t-2xl sm:rounded-2xl shadow-2xl border border-slate-200 w-full max-w-lg overflow-hidden animate-in zoom-in-95 duration-150 max-h-[92vh] flex flex-col"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="w-12 h-1.5 bg-slate-300 rounded-full mx-auto my-2 sm:hidden shrink-0" />
              {/* Header */}
              <div className="px-5 py-4 bg-gradient-to-r from-slate-900 via-indigo-950 to-slate-900 text-white flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-indigo-500/30 text-indigo-200 border border-indigo-400/30 uppercase tracking-wider">
                      Quick Audit Inspector
                    </span>
                    {inspectorBatch.is_current && (
                      <span className="text-[10px] font-black px-2 py-0.5 rounded bg-emerald-500 text-white">
                        Batch Aktif Saat Ini
                      </span>
                    )}
                  </div>
                  <h3 className="text-base sm:text-lg font-black tracking-tight">
                    Mesin {inspectorBatch.machine_name} &bull; Batch {inspectorBatch.label}
                  </h3>
                  <p className="text-xs text-indigo-200 mt-0.5">
                    Program: <b className="text-white">{bench?.program_name || '-'}</b> &bull; Tanggal Celup: <b className="text-white">{inspectorBatch.date}</b>
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setInspectorBatch(null)}
                  className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-colors"
                  title="Tutup (ESC)"
                >
                  <X size={18} />
                </button>
              </div>

              {/* Body Content */}
              <div className="p-4 sm:p-5 space-y-3 sm:space-y-4 overflow-y-auto">
                {/* Status Pill & Root-Cause Summary */}
                <div className={`p-3 rounded-xl border text-xs ${statusPill.bg}`}>
                  <div className="flex items-center gap-2 font-bold mb-1 uppercase tracking-wider text-[11px]">
                    <span className={`w-2 h-2 rounded-full ${statusPill.dot}`} />
                    {statusPill.label}
                  </div>
                  <p className="text-slate-800 leading-relaxed font-medium">
                    {diagnosticSummary}
                  </p>
                </div>

                {/* Comparison Metrics Grid */}
                <div className="grid grid-cols-3 gap-2.5 text-center">
                  {/* Heating */}
                  <div className="p-2.5 bg-slate-50 border border-slate-200 rounded-xl">
                    <span className="text-[10px] text-slate-400 font-bold uppercase block flex items-center justify-center gap-1">
                      <Flame size={11} className="text-rose-500" /> Heating
                    </span>
                    <span className="text-base font-black text-slate-800 block mt-0.5">
                      {inspectorBatch.heat_mins} <span className="text-[10px] font-normal text-slate-400">mnt</span>
                    </span>
                    <span className={`text-[10px] font-bold block ${heatDiff > 15 ? 'text-rose-600' : heatDiff < 0 ? 'text-emerald-600' : 'text-slate-500'}`}>
                      {heatDiff != null ? (heatDiff > 0 ? `+${heatDiff}m vs avg` : `${heatDiff}m vs avg`) : '-'}
                    </span>
                  </div>

                  {/* Cooling */}
                  <div className="p-2.5 bg-slate-50 border border-slate-200 rounded-xl">
                    <span className="text-[10px] text-slate-400 font-bold uppercase block flex items-center justify-center gap-1">
                      <Snowflake size={11} className="text-sky-500" /> Cooling
                    </span>
                    <span className="text-base font-black text-slate-800 block mt-0.5">
                      {inspectorBatch.cool_mins} <span className="text-[10px] font-normal text-slate-400">mnt</span>
                    </span>
                    <span className={`text-[10px] font-bold block ${coolDiff > 10 ? 'text-rose-600' : coolDiff < 0 ? 'text-emerald-600' : 'text-slate-500'}`}>
                      {coolDiff != null ? (coolDiff > 0 ? `+${coolDiff}m vs avg` : `${coolDiff}m vs avg`) : '-'}
                    </span>
                  </div>

                  {/* Avg Pressure */}
                  <div className="p-2.5 bg-slate-50 border border-slate-200 rounded-xl">
                    <span className="text-[10px] text-slate-400 font-bold uppercase block flex items-center justify-center gap-1">
                      <Gauge size={11} className="text-purple-500" /> Avg Steam
                    </span>
                    <span className="text-base font-black text-purple-700 block mt-0.5">
                      {inspectorBatch.avg_pressure ?? '-'} <span className="text-[10px] font-normal text-slate-400">bar</span>
                    </span>
                    <span className={`text-[10px] font-bold block ${inspectorBatch.avg_pressure < thresholdBar ? 'text-amber-600' : 'text-emerald-600'}`}>
                      {inspectorBatch.avg_pressure < thresholdBar ? 'Drop <3.8' : 'Uap Aman'}
                    </span>
                  </div>
                </div>

                {/* Secondary Info Bar */}
                <div className="bg-slate-50 p-2.5 rounded-xl border border-slate-200 text-xs text-slate-600 flex justify-between items-center">
                  <span>Durasi Efektif: <b>{inspectorBatch.total_mins} mnt</b></span>
                  <span>Steam Uap: <b>{inspectorBatch.steam_kg?.toLocaleString('id-ID')} kg</b></span>
                </div>

                {/* Clarification prompt */}
                <p className="text-[11px] text-slate-500 text-center">
                  Ingin meneliti kurva suhu proses, thermocouple, dan log audit mendalam untuk batch ini?
                </p>
              </div>

              {/* Footer Actions */}
              <div className="px-4 sm:px-5 py-3 sm:py-3.5 bg-slate-100/70 border-t border-slate-200 flex flex-col-reverse sm:flex-row sm:items-center justify-end gap-2 sm:gap-2.5">
                <button
                  type="button"
                  onClick={() => setInspectorBatch(null)}
                  className="px-3.5 py-2 text-xs font-semibold text-slate-600 hover:text-slate-800 hover:bg-slate-200/60 rounded-xl transition-colors text-center w-full sm:w-auto"
                >
                  Batal
                </button>

                <button
                  type="button"
                  onClick={() => {
                    window.open(`/history/report/${inspectorBatch.id}`, '_blank', 'noopener,noreferrer');
                    setInspectorBatch(null);
                  }}
                  className="inline-flex items-center justify-center gap-1.5 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold rounded-xl transition-colors shadow-xs w-full sm:w-auto"
                >
                  <span>Buka Laporan Audit di Tab Baru</span>
                  <ExternalLink size={13} />
                </button>
              </div>
            </div>
          </div>
        );
      })()}

      {/* ══════════════════════════════════════════════════════════════════════
          WELCOME ONBOARDING PROMPT BANNER (OPT-IN FOR FIRST-TIME USERS)
         ══════════════════════════════════════════════════════════════════════ */}
      {showWelcomeTourBanner && (
        <div className="fixed bottom-3 left-3 right-3 sm:left-auto sm:right-4 z-40 max-w-sm bg-slate-900/95 backdrop-blur-md text-white rounded-2xl p-3.5 sm:p-4 shadow-2xl border border-slate-700/80 no-print animate-in slide-in-from-bottom-5 duration-300">
          <div className="flex items-start justify-between gap-3">
            <div className="w-10 h-10 rounded-xl bg-indigo-600/30 text-indigo-400 border border-indigo-500/30 flex items-center justify-center shrink-0">
              <Compass className="w-5 h-5 animate-pulse" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-1.5 mb-1">
                <span className="text-[10px] font-extrabold uppercase tracking-wider px-1.5 py-0.5 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-400/20">
                  Panduan Fitur Laporan
                </span>
              </div>
              <h4 className="text-xs sm:text-sm font-bold text-white">
                Baru pertama kali membuka laporan ini?
              </h4>
              <p className="text-[11px] text-slate-300 mt-1 leading-relaxed">
                Ikuti tur panduan interaktif 90 detik untuk memahami grafik, audit kerugian finansial PINN, dan fitur klik investigasi batch.
              </p>
              <div className="flex items-center gap-2 mt-3 pt-2 border-t border-slate-800">
                <button
                  type="button"
                  onClick={handleStartTour}
                  className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold rounded-lg transition-colors shadow-xs cursor-pointer flex items-center gap-1.5"
                >
                  <span>Mulai Tur (90 Detik)</span>
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setShowWelcomeTourBanner(false);
                    localStorage.setItem(TOUR_STORAGE_KEY, 'true');
                  }}
                  className="px-2.5 py-1.5 text-xs font-medium text-slate-400 hover:text-slate-200 transition-colors cursor-pointer"
                >
                  Nanti Saja
                </button>
              </div>
            </div>
            <button
              type="button"
              onClick={() => {
                setShowWelcomeTourBanner(false);
                localStorage.setItem(TOUR_STORAGE_KEY, 'true');
              }}
              className="text-slate-500 hover:text-slate-300 transition-colors p-1 cursor-pointer"
              title="Tutup"
            >
              <X size={15} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default ProcessReport;
