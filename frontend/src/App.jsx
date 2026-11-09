import React, { lazy, Suspense } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, useParams } from 'react-router-dom';
import { Provider } from 'react-redux';
import { store } from './store/store';
import { AuthProvider } from './context/AuthContext';
import { LayoutProvider } from './context/LayoutContext';
import { ToastProvider } from './context/ToastContext';
import { ChatProvider } from './context/ChatContext';
import ProtectedRoute from './components/ProtectedRoute';
import ErrorBoundary from './components/ErrorBoundary';
import Layout from './components/Layout';
import PageLoadingFallback from './components/PageLoadingFallback';

// Helper pembungkus dynamic import dengan 1x retry jika koneksi terputus sesaat,
// dan 1x auto-reload jika build baru di server memperbarui hash chunk file
function lazyWithRetry(componentImport, componentName = '') {
  return lazy(async () => {
    const reloadKey = `chunk_reload_${componentName || 'generic'}`;
    const pageHasBeenForceRefreshed = sessionStorage.getItem(reloadKey);

    try {
      const module = await componentImport();
      // Bersihkan flag reload jika import berhasil
      sessionStorage.removeItem(reloadKey);
      return module;
    } catch (error) {
      // 1. Coba retry 1x setelah 400ms jika terjadi network drop sesaat
      try {
        await new Promise((resolve) => setTimeout(resolve, 400));
        const module = await componentImport();
        sessionStorage.removeItem(reloadKey);
        return module;
      } catch (secondError) {
        // 2. Jika masih gagal (karena chunk lama terhapus oleh build baru di server),
        // lakukan auto-reload 1x agar browser mengambil index.html & chunk terbaru
        if (!pageHasBeenForceRefreshed) {
          sessionStorage.setItem(reloadKey, 'true');
          window.location.reload();
          return new Promise(() => {}); // tahan render hingga reload selesai
        }
        sessionStorage.removeItem(reloadKey);
        throw secondError;
      }
    }
  });
}

// Lazy-loaded pages dengan auto-retry & auto-recovery (Code-Splitting Profesional)
const Login = lazyWithRetry(() => import('./pages/Login'), 'Login');
const NotFound = lazyWithRetry(() => import('./pages/NotFound'), 'NotFound');
const Home = lazyWithRetry(() => import('./pages/Home'), 'Home');
const Dashboard = lazyWithRetry(() => import('./pages/Dashboard'), 'Dashboard');
const DailyReport = lazyWithRetry(() => import('./pages/DailyReport'), 'DailyReport');
const DailyReportDeep = lazyWithRetry(() => import('./pages/DailyReportDeep'), 'DailyReportDeep');
const MonthlyReport = lazyWithRetry(() => import('./pages/MonthlyReport'), 'MonthlyReport');
const BoilerReport = lazyWithRetry(() => import('./pages/BoilerReport'), 'BoilerReport');
const BoilerCalendar = lazyWithRetry(() => import('./pages/BoilerCalendar'), 'BoilerCalendar');
const BoilerSteam = lazyWithRetry(() => import('./pages/BoilerSteam'), 'BoilerSteam');
const BoilerHto = lazyWithRetry(() => import('./pages/BoilerHto'), 'BoilerHto');
const MachineDailyReport = lazyWithRetry(() => import('./pages/MachineDailyReport'), 'MachineDailyReport');
const MachineDailyAnalytics = lazyWithRetry(() => import('./pages/MachineDailyAnalytics'), 'MachineDailyAnalytics');
const MachineDailyDeepAnalytics = lazyWithRetry(() => import('./pages/MachineDailyDeepAnalytics'), 'MachineDailyDeepAnalytics');
const AnomalyDetection = lazyWithRetry(() => import('./pages/AnomalyDetection'), 'AnomalyDetection');
const BatchDetailReport = lazyWithRetry(() => import('./pages/BatchDetailReport'), 'BatchDetailReport');
const DyeingIdentities = lazyWithRetry(() => import('./pages/DyeingIdentities'), 'DyeingIdentities');
const HistoryList = lazyWithRetry(() => import('./pages/HistoryList'), 'HistoryList');
const ProcessReport = lazyWithRetry(() => import('./pages/ProcessReport'), 'ProcessReport');
const ManualMachineUsage = lazyWithRetry(() => import('./pages/ManualMachineUsage'), 'ManualMachineUsage');
const SnapshotHistoryPivot = lazyWithRetry(() => import('./pages/SnapshotHistoryPivot'), 'SnapshotHistoryPivot');
const ProductionPlanning = lazyWithRetry(() => import('./pages/ProductionPlanning'), 'ProductionPlanning');
const PerformanceSummary = lazyWithRetry(() => import('./pages/PerformanceSummary'), 'PerformanceSummary');
const AnalyticsGrafik = lazyWithRetry(() => import('./pages/AnalyticsGrafik'), 'AnalyticsGrafik');
const DailyBatchOverview = lazyWithRetry(() => import('./pages/DailyBatchOverview'), 'DailyBatchOverview');
const JumoLiveMonitor = lazyWithRetry(() => import('./pages/JumoLiveMonitor'), 'JumoLiveMonitor');

// Engineer Workspace Lazy Pages
import EngineerLayout from './components/engineer/EngineerLayout';
const CommandCenter = lazyWithRetry(() => import('./pages/engineer/CommandCenter'), 'CommandCenter');
const IssueTriage = lazyWithRetry(() => import('./pages/engineer/IssueTriage'), 'IssueTriage');
const MachineList = lazyWithRetry(() => import('./pages/engineer/MachineList'), 'MachineList');
const MachineDossier = lazyWithRetry(() => import('./pages/engineer/MachineDossier'), 'MachineDossier');
const FieldInspection = lazyWithRetry(() => import('./pages/engineer/FieldInspection'), 'FieldInspection');
const SpareParts = lazyWithRetry(() => import('./pages/engineer/SpareParts'), 'SpareParts');
const CalculationWorkbench = lazyWithRetry(() => import('./pages/engineer/CalculationWorkbench'), 'CalculationWorkbench');
const Meetings = lazyWithRetry(() => import('./pages/engineer/Meetings'), 'Meetings');

// Helper pengalihan rute lama /history/{machine}/{batch} ke format kanonikal /history/report/0?machine=&batch=
function LegacyHistoryRedirect() {
  const { machine_code, batch_number } = useParams();
  const machine = encodeURIComponent(machine_code || '');
  const batch = encodeURIComponent(batch_number || '');
  return <Navigate to={`/history/report/0?machine=${machine}&batch=${batch}`} replace />;
}

// Helper pengalihan rute lama /machine-daily-analytics-1/:machineId/:date ke /machine-daily-deep-analytics/:machineId/:date
function LegacyMachineDailyDeepRedirect() {
  const { machineId, date } = useParams();
  return <Navigate to={`/machine-daily-deep-analytics/${machineId}/${date}`} replace />;
}

// pageCode: dipetakan 1:1 dengan kode PagePermission Django (lihat monitoring/decorators.py
// dan monitoring/views.py position_required(...)) agar frontend & backend konsisten.
const ROUTES = [
  { path: '/home', element: <Home />, pageCode: 'dashboard' },
  { path: '/dashboard', element: <Dashboard />, pageCode: 'dashboard' },
  { path: '/dashboard-1', element: <Navigate to="/dashboard" replace /> },
  { path: '/mesin-aktif', element: <ManualMachineUsage />, pageCode: 'manual_input' },
  { path: '/history', element: <HistoryList />, pageCode: 'history' },
  { path: '/history/:machine_code/:batch_number', element: <LegacyHistoryRedirect />, pageCode: 'history' },
  { path: '/history/:machine_code/:batch_number/*', element: <LegacyHistoryRedirect />, pageCode: 'history' },
  { path: '/history/report/:process_id', element: <ProcessReport />, pageCode: 'history' },
  { path: '/snapshot-history', element: <SnapshotHistoryPivot />, pageCode: 'snapshot_history' },
  { path: '/production-planning', element: <ProductionPlanning />, pageCode: 'production_planning' },
  { path: '/grafik', element: <AnalyticsGrafik />, pageCode: 'analytics' },
  { path: '/performance-summary', element: <PerformanceSummary />, pageCode: 'performance_summary' },
  { path: '/daily-batch-overview', element: <DailyBatchOverview />, pageCode: 'daily_batch_overview' },
  { path: '/daily-report', element: <DailyReport />, pageCode: 'daily_report' },
  { path: '/daily-report-deep', element: <DailyReportDeep />, pageCode: 'daily_report' },
  { path: '/daily-report-1', element: <Navigate to="/daily-report-deep" replace />, pageCode: 'daily_report' },
  { path: '/machine-daily-report', element: <MachineDailyReport />, pageCode: 'machine_daily_report' },
  { path: '/machine-daily-analytics/:machineId/:date', element: <MachineDailyAnalytics />, pageCode: 'daily_report' },
  { path: '/machine-daily-deep-analytics/:machineId/:date', element: <MachineDailyDeepAnalytics />, pageCode: 'daily_report' },
  { path: '/machine-daily-analytics-1/:machineId/:date', element: <LegacyMachineDailyDeepRedirect />, pageCode: 'daily_report' },
  { path: '/monthly-report', element: <MonthlyReport />, pageCode: 'monthly_report' },
  { path: '/boiler-report', element: <BoilerReport />, pageCode: 'boiler_report' },
  { path: '/boiler-calendar', element: <BoilerCalendar />, pageCode: 'boiler_calendar' },
  { path: '/boiler-steam', element: <BoilerSteam />, pageCode: 'boiler_report' },
  { path: '/boiler-hto', element: <BoilerHto />, pageCode: 'boiler_report' },
  { path: '/anomalies', element: <AnomalyDetection />, pageCode: 'anomaly_detection' },
  { path: '/jumo-live', element: <JumoLiveMonitor />, pageCode: 'jumo_live_monitor' },
  { path: '/batch-report/:machine_code/:batch_number', element: <BatchDetailReport />, pageCode: 'history_report' },
  { path: '/dyeing-identities', element: <DyeingIdentities />, pageCode: 'dyeing_identities' },
];

function App() {
  return (
    <Provider store={store}>
      <AuthProvider>
        <LayoutProvider>
          <ToastProvider>
            <ChatProvider>
              <Router>
              <ErrorBoundary>
                <Routes>
                  <Route
                    path="/login"
                    element={(
                      <Suspense fallback={<PageLoadingFallback />}>
                        <Login />
                      </Suspense>
                    )}
                  />
                  <Route
                    path="/login/:urlUsername/*"
                    element={(
                      <Suspense fallback={<PageLoadingFallback />}>
                        <Login />
                      </Suspense>
                    )}
                  />
                  <Route
                    path="/login/:urlUsername"
                    element={(
                      <Suspense fallback={<PageLoadingFallback />}>
                        <Login />
                      </Suspense>
                    )}
                  />
                  <Route
                    path="/engineer"
                    element={(
                      <ProtectedRoute pageCode="engineer_workspace">
                        <EngineerLayout />
                      </ProtectedRoute>
                    )}
                  >
                    <Route index element={<CommandCenter />} />
                    <Route path="issues" element={<IssueTriage />} />
                    <Route path="inspection" element={<FieldInspection />} />
                    <Route path="spare-parts" element={<SpareParts />} />
                    <Route path="calculations" element={<CalculationWorkbench />} />
                    <Route path="meetings" element={<Meetings />} />
                    <Route path="machines" element={<MachineList />} />
                    <Route path="machines/:machineId" element={<MachineDossier />} />
                  </Route>
                  <Route path="/" element={<Navigate to="/home" replace />} />
                  {ROUTES.map(({ path, element, pageCode }) => (
                    <Route
                      key={path}
                      path={path}
                      element={(
                        <ProtectedRoute pageCode={pageCode}>
                          <Layout>{element}</Layout>
                        </ProtectedRoute>
                      )}
                    />
                  ))}
                  <Route
                    path="*"
                    element={(
                      <Suspense fallback={<PageLoadingFallback />}>
                        <NotFound />
                      </Suspense>
                    )}
                  />
                </Routes>
              </ErrorBoundary>
            </Router>
          </ChatProvider>
        </ToastProvider>
      </LayoutProvider>
      </AuthProvider>
    </Provider>
  );
}

export default App;
