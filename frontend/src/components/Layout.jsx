import React, { useEffect, useRef } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Home, Gauge, Flame, List, Settings, LogIn, Activity, Zap, Cpu, ShieldAlert, Pointer, LineChart, Grid3x3, BarChart3, CalendarDays, HardHat, Radio, CalendarClock, PanelLeftOpen, LayoutDashboard } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { useLayout } from '../context/LayoutContext';
import { NavbarNested } from './sidebar/NavbarNested';
import { MobileHeader } from './MobileHeader';
import { TouchAppIcon } from './icons/TouchAppIcon';
import { MonitoringIcon } from './icons/MonitoringIcon';
import PageLoadingFallback from './PageLoadingFallback';
import { MessageSquare } from 'lucide-react';
import { useChat } from '../context/ChatContext';
import { ChatDrawer } from './chat/ChatDrawer';
import { ShareToChatModal } from './chat/ShareToChatModal';

// Daftar item untuk Mobile Bottom Nav
const NAV_ITEMS = [
  { path: '/home', label: 'Home', icon: Home, pageCode: 'dashboard' },
  { path: '/mesin-aktif', label: 'Mesin Aktif', icon: TouchAppIcon, pageCode: 'manual_input' },
  { path: '/boiler-steam', label: 'B-Steam', icon: Gauge, pageCode: 'boiler_report' },
  { path: '/boiler-hto', label: 'B-HTO', icon: Flame, pageCode: 'boiler_report' },
  { path: '/dashboard', label: 'Dashboard', icon: LayoutDashboard, pageCode: 'dashboard' },
  { path: '/history', label: 'History List', icon: List, pageCode: 'history' },
  { path: '/snapshot-history', label: 'Snapshot History', icon: Grid3x3, pageCode: 'snapshot_history' },
  { path: '/production-planning', label: 'Perencanaan', icon: CalendarClock, pageCode: 'production_planning' },
  { path: '/grafik', label: 'Analytics', icon: MonitoringIcon, pageCode: 'analytics' },
  { path: '/jumo-live', label: 'JUMO Live', icon: Radio, pageCode: 'jumo_live_monitor' },
  { path: '/performance-summary', label: 'Performance', icon: BarChart3, pageCode: 'performance_summary' },
  { path: '/daily-batch-overview', label: 'Daily Batch', icon: CalendarDays, pageCode: 'daily_batch_overview' },
  { path: '/daily-report', label: 'Daily Report', icon: Activity, pageCode: 'daily_report' },
  { path: '/machine-daily-report', label: 'Machine Daily', icon: Cpu, pageCode: 'machine_daily_report' },
  { path: '/monthly-report', label: 'Monthly Report', icon: Activity, pageCode: 'monthly_report' },
  { path: '/boiler-report', label: 'Boiler Report', icon: Zap, pageCode: 'boiler_report' },
  { path: '/boiler-calendar', label: 'Boiler Calendar', icon: CalendarDays, pageCode: 'boiler_calendar' },
  { path: '/dyeing-identities', label: 'Dyeing ID', icon: Activity, pageCode: 'dyeing_identities' },
  { path: '/anomalies', label: 'Anomali', icon: ShieldAlert, pageCode: 'anomaly_detection' },
  { path: '/engineer', label: 'Engineer', icon: HardHat, pageCode: 'engineer_workspace' },
];

const Layout = ({ children }) => {
  const { user, canAccess } = useAuth();
  const { viewportTier, toggleSidebar } = useLayout();
  const { toggleChat, unreadCount } = useChat();
  const location = useLocation();

  const isProcessReportPage = location.pathname.startsWith('/history/report/');
  const isSnapshotPage = location.pathname === '/snapshot-history' || location.pathname === '/production-planning' || location.pathname === '/history';
  const isDashboardPage = location.pathname === '/dashboard';
  
  // Deteksi environment
  const isMobile = viewportTier === 'mobile';
  

  const mainRef = useRef(null);

  // Auto scroll restoration ke puncak halaman saat navigasi rute berubah
  useEffect(() => {
    if (mainRef.current) {
      mainRef.current.scrollTo({ top: 0, behavior: 'instant' });
    }
  }, [location.pathname]);

  const visibleItems = NAV_ITEMS.filter((item) => canAccess(item.pageCode));

  return (
    <div className="snapshot-print-flow flex h-screen w-screen overflow-hidden bg-slate-50 text-slate-900 print:h-auto print:w-auto print:overflow-visible">
      
      {/* 
        SIDEBAR CONTAINER 
        - Desktop: statis di flex flow
        - Tablet: absolute/fixed drawer
        - Mobile: hidden (pakai bottom nav)
      */}
      {!isMobile && !isProcessReportPage && (
        <>
          
          
          <div className="relative z-10 flex h-full">
            <NavbarNested />
          </div>

          
        </>
      )}

      {/* MAIN CONTENT AREA */}
      <div className={`snapshot-print-flow flex-1 flex flex-col min-w-0 relative print:overflow-visible print:h-auto ${
        !isProcessReportPage && isMobile ? 'pb-16' : 'pb-0'
      }`}>
        {/* RESTORED MOBILE HEADER */}
        {isMobile && !isProcessReportPage && (
          <MobileHeader />
        )}

        <main ref={mainRef}
          className={`snapshot-print-flow flex-1 bg-slate-50 min-h-0 print:overflow-visible print:h-auto ${
            isSnapshotPage ? 'flex flex-col overflow-hidden' : 'overflow-auto sidebar-scroll-hover'
          }`}
        >
          <React.Suspense fallback={<PageLoadingFallback />}>
            {children}
          </React.Suspense>
        </main>

        {/* BOTTOM NAV UNTUK MOBILE */}
        <div className={`no-print fixed bottom-0 left-0 right-0 h-16 bg-white border-t border-slate-200/80 items-center z-50 shadow-[0_-10px_40px_rgba(0,0,0,0.05)] overflow-x-auto snap-x hide-scrollbar ${
          isProcessReportPage || !isMobile ? 'hidden' : 'flex'
        }`}>
          {visibleItems.map(({ path, label, icon: Icon }) => (
            <Link
              key={path}
              to={path}
              onClick={() => {
                if (path === '/dashboard' && location.pathname === '/dashboard') {
                  const container = document.getElementById('dashboard-scroll-container');
                  if (container) container.scrollTo({ top: 0, behavior: 'smooth' });
                }
              }}
              className={`flex-shrink-0 flex flex-col items-center justify-center w-20 h-full transition-colors snap-center ${
                location.pathname === path ? 'text-blue-600' : 'text-slate-400 hover:text-slate-800'
              }`}
            >
              <Icon className={`w-6 h-6 mb-1 ${location.pathname === path ? 'fill-blue-100/50' : ''}`} />
              <span className="text-[10px] font-bold truncate px-1 w-full text-center">{label}</span>
            </Link>
          ))}
          <a href="#settings" className="flex-shrink-0 flex flex-col items-center justify-center w-20 h-full text-slate-400 hover:text-slate-800 transition-colors snap-center">
            <Settings className="w-6 h-6 mb-1" />
            <span className="text-[10px] font-bold">Settings</span>
          </a>
        </div>
      </div>

      {/* FLOATING ACTION BUTTON CHAT - Hanya tampil di Dashboard */}
      {user && isDashboardPage && (
        <button
          type="button"
          onClick={toggleChat}
          className={`no-print fixed z-40 flex items-center justify-center rounded-full bg-gradient-to-tr from-indigo-600 to-blue-600 text-white shadow-lg hover:shadow-indigo-500/30 hover:scale-105 active:scale-95 transition-all duration-200 ${
            isMobile ? 'bottom-20 right-4 w-12 h-12' : 'bottom-6 right-6 w-13 h-13'
          }`}
          title="Buka Chat Jaringan Lokal"
        >
          <MessageSquare className={isMobile ? 'w-5 h-5' : 'w-6 h-6'} />
          {unreadCount > 0 && (
            <span className="absolute -top-1 -right-1 flex h-5 min-w-5 px-1 items-center justify-center rounded-full bg-rose-500 text-[10px] font-extrabold text-white ring-2 ring-white animate-pulse">
              {unreadCount > 99 ? '99+' : unreadCount}
            </span>
          )}
        </button>
      )}

      {/* CHAT DRAWER & SHARE MODAL */}
      <ChatDrawer />
      <ShareToChatModal />
    </div>
  );
};

export default Layout;

