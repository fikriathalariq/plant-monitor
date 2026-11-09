import React from 'react';
import { Link, useLocation, Outlet } from 'react-router-dom';
import PageLoadingFallback from '../PageLoadingFallback';
import {
  LayoutDashboard, ListTodo, ClipboardCheck, Wrench, Calculator,
  Users, Cpu, ArrowLeft,
} from 'lucide-react';

const NAV = [
  { path: '/engineer', label: 'Command', icon: LayoutDashboard, end: true },
  { path: '/engineer/issues', label: 'Issues', icon: ListTodo },
  { path: '/engineer/inspection', label: 'Inspeksi', icon: ClipboardCheck },
  { path: '/engineer/spare-parts', label: 'Spare Part', icon: Wrench },
  { path: '/engineer/calculations', label: 'Hitung', icon: Calculator },
  { path: '/engineer/meetings', label: 'Rapat', icon: Users },
  { path: '/engineer/machines', label: 'Mesin', icon: Cpu },
];

export default function EngineerLayout() {
  const location = useLocation();

  const isActive = (path, end) => {
    if (end) return location.pathname === path;
    return location.pathname.startsWith(path);
  };

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col md:flex-row">
      {/* Desktop sidebar */}
      <aside className="hidden md:flex md:flex-col w-56 bg-slate-900 text-white shrink-0">
        <div className="p-4 border-b border-slate-700">
          <Link to="/home" className="flex items-center gap-2 text-slate-400 hover:text-white text-sm mb-2">
            <ArrowLeft className="w-4 h-4" /> Plant Monitor
          </Link>
          <h1 className="font-bold text-lg">Engineer Workspace</h1>
        </div>
        <nav className="flex-1 p-2 space-y-0.5">
          {NAV.map(({ path, label, icon: Icon, end }) => (
            <Link
              key={path}
              to={path}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                isActive(path, end)
                  ? 'bg-blue-600 text-white'
                  : 'text-slate-300 hover:bg-slate-800 hover:text-white'
              }`}
            >
              <Icon className="w-5 h-5 shrink-0" />
              {label}
            </Link>
          ))}
        </nav>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto pb-20 md:pb-6">
        <div className="md:hidden bg-slate-900 text-white px-4 py-3 flex items-center justify-between sticky top-0 z-30">
          <div>
            <Link to="/home" className="text-slate-400 text-xs">← Plant Monitor</Link>
            <h1 className="font-bold">Engineer Workspace</h1>
          </div>
        </div>
        <div className="p-4 md:p-6 max-w-7xl mx-auto">
          <React.Suspense fallback={<PageLoadingFallback />}>
            <Outlet />
          </React.Suspense>
        </div>
      </main>

      {/* Mobile bottom nav */}
      <nav className="md:hidden fixed bottom-0 left-0 right-0 bg-white border-t border-slate-200 z-40 flex justify-around py-1">
        {NAV.map(({ path, label, icon: Icon, end }) => (
          <Link
            key={path}
            to={path}
            className={`flex flex-col items-center py-2 px-1 text-[10px] font-medium min-w-0 ${
              isActive(path, end) ? 'text-blue-600' : 'text-slate-500'
            }`}
          >
            <Icon className="w-5 h-5 mb-0.5" />
            <span className="truncate">{label}</span>
          </Link>
        ))}
      </nav>
    </div>
  );
}
