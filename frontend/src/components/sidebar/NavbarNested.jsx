import React, { useEffect, useState } from 'react';
import { useLayout } from '../../context/LayoutContext';
import { useAuth } from '../../context/AuthContext';
import api, { BACKEND_BASE_URL, fetchBrandingCached } from '../../lib/api';
import { 
  Home, Gauge, Flame, Pointer, Radio, ShieldAlert, CalendarClock, Grid3x3, List, CalendarDays, Activity, 
  LineChart, BarChart3, FileText, Cpu, Calendar, Zap, HardHat, Settings, Compass, LayoutDashboard, MessageSquare 
} from 'lucide-react';
import { SidebarToggleButton } from './SidebarToggleButton';
import { UserButton } from './UserButton';
import { NavbarLinksGroup } from './NavbarLinksGroup';
import { TouchAppIcon } from '../icons/TouchAppIcon';
import { MonitoringIcon } from '../icons/MonitoringIcon';

const NAV_GROUPS = [
  {
    title: 'Monitoring Real-time',
    items: [
      { label: 'Home', path: '/home', icon: Home, pageCode: 'dashboard' },
      { label: 'Mesin Aktif', path: '/mesin-aktif', icon: TouchAppIcon, pageCode: 'manual_input' },
      { label: 'Boiler Steam', path: '/boiler-steam', icon: Gauge, pageCode: 'boiler_report' },
      { label: 'Boiler HTO', path: '/boiler-hto', icon: Flame, pageCode: 'boiler_report' },
      { label: 'Dashboard', path: '/dashboard', icon: LayoutDashboard, pageCode: 'dashboard' },
      { label: 'JUMO Live Monitor', path: '/jumo-live', icon: Radio, pageCode: 'jumo_live_monitor' },
      { label: 'Deteksi Anomali', path: '/anomalies', icon: ShieldAlert, pageCode: 'anomaly_detection' },
    ],
  },
  {
    title: 'Operasional & Perencanaan',
    items: [
      { label: 'Perencanaan Produksi', path: '/production-planning', icon: CalendarClock, pageCode: 'production_planning' },
      { label: 'Snapshot History', path: '/snapshot-history', icon: Grid3x3, pageCode: 'snapshot_history' },
      { label: 'History List', path: '/history', icon: List, pageCode: 'history' },
      { label: 'Daily Batch Overview', path: '/daily-batch-overview', icon: CalendarDays, pageCode: 'daily_batch_overview' },
      { label: 'Dyeing Identities', path: '/dyeing-identities', icon: Activity, pageCode: 'dyeing_identities' },
    ],
  },
  {
    title: 'Analitik & Performa',
    items: [
      { label: 'Grafik / Analytics', path: '/grafik', icon: MonitoringIcon, pageCode: 'analytics' },
      { label: 'Performance Summary', path: '/performance-summary', icon: BarChart3, pageCode: 'performance_summary' },
      { label: 'Daily Report', path: '/daily-report', icon: FileText, pageCode: 'daily_report' },
      { label: 'Daily Report V2 (Deep)', path: '/daily-report-deep', icon: Compass, pageCode: 'daily_report' },
    ],
  },
  {
    title: 'Rekap Laporan Mesin',
    items: [
      { label: 'Machine Daily Report', path: '/machine-daily-report', icon: Cpu, pageCode: 'machine_daily_report' },
      { label: 'Monthly Report', path: '/monthly-report', icon: Calendar, pageCode: 'monthly_report' },
    ],
  },
  {
    title: 'Utilitas & Boiler',
    items: [
      { label: 'Boiler Report', path: '/boiler-report', icon: Zap, pageCode: 'boiler_report' },
      { label: 'Boiler Calendar', path: '/boiler-calendar', icon: CalendarDays, pageCode: 'boiler_calendar' },
    ],
  },
  {
    title: 'Pengaturan & Workspace',
    items: [
      { label: 'Engineer Workspace', path: '/engineer', icon: HardHat, pageCode: 'engineer_workspace' },
      { label: 'Chat Jaringan Lokal', path: '#chat', icon: MessageSquare, pageCode: null },
      { label: 'Settings', path: '#settings', icon: Settings, pageCode: null },
    ],
  },
];

export function NavbarNested() {
  const { sidebarCollapsed, toggleSidebar } = useLayout();
  const { canAccess } = useAuth();
  

  const [logoUrl, setLogoUrl] = useState(null);
  const [imgError, setImgError] = useState(false);
  const [companyName, setCompanyName] = useState("Plant Monitor");

  useEffect(() => {
    fetchBrandingCached().then(res => {
      if (res.data.logo_url) {
        setLogoUrl(`${BACKEND_BASE_URL}${res.data.logo_url}`);
      }
      if (res.data.name) {
        setCompanyName(res.data.name);
      }
    }).catch(err => {
      console.warn("Could not load branding", err);
      setImgError(true);
    });
  }, []);

  return (
    <aside
      className={`no-print flex flex-col bg-white border-r border-slate-200/80 shadow-sm shrink-0 transition-[width] duration-300 ease-in-out ${
        sidebarCollapsed ? 'w-20' : 'w-64'
      }`}
    >
      {/* HEADER */}
      <div className="shrink-0 h-14 flex items-center pl-6 pr-5 border-b border-slate-100/80 overflow-hidden">
        <div className={`flex items-center whitespace-nowrap overflow-hidden transition-all duration-300 ${sidebarCollapsed ? 'w-0 opacity-0' : 'w-full opacity-100'}`}>
          {logoUrl && !imgError ? (
            <img 
              src={logoUrl} 
              alt={`${companyName} Logo`} 
              onError={() => setImgError(true)} 
              className="w-6 h-6 object-contain shrink-0 mr-2 rounded-sm" 
            />
          ) : (
            <Activity className="w-6 h-6 text-blue-600 shrink-0 mr-2" />
          )}
          <div className="flex flex-col min-w-0">
            <span className="text-base font-extrabold text-slate-900 tracking-tight truncate">{companyName}</span>
            
          </div>
        </div>
        <SidebarToggleButton collapsed={sidebarCollapsed} onToggle={toggleSidebar} className="shrink-0 ml-auto" />
      </div>

      {/* SCROLL AREA */}
      <nav className="flex-1 sidebar-scroll-hover pl-3 pr-1 py-4 overflow-hidden">
        <div className="space-y-6">
          {NAV_GROUPS.map((group, index) => {
            const visibleItems = group.items.filter(item => {
              if (item.pageCode === null) return true;
              return canAccess(item.pageCode);
            });

            if (visibleItems.length === 0) return null;

            return (
              <div key={group.title} className="space-y-1">
                <p className={`px-3 text-[10px] font-bold tracking-wider text-slate-400 uppercase transition-all duration-300 overflow-hidden whitespace-nowrap ${sidebarCollapsed ? 'opacity-0 h-0 mb-0' : 'opacity-100 h-auto mb-2'}`}>
                  {group.title}
                </p>
                {visibleItems.map(item => (
                  <NavbarLinksGroup 
                    key={item.label} 
                    {...item} 
                    collapsed={sidebarCollapsed} 
                    
                  />
                ))}
              </div>
            );
          })}
        </div>
      </nav>

      {/* FOOTER */}
      <UserButton collapsed={sidebarCollapsed} />
    </aside>
  );
}



