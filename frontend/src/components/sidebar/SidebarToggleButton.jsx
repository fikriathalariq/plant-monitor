import React from 'react';
import { Menu } from 'lucide-react';

export function SidebarToggleButton({ collapsed, onToggle, className = '' }) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={!collapsed}
      aria-controls="sidebar-nav-panel"
      aria-label={collapsed ? 'Perluas bilah samping' : 'Ciutkan bilah samping'}
      title={collapsed ? 'Perluas Sidebar' : 'Ciutkan Sidebar'}
      className={`group relative flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200/80 bg-white/90 p-2 text-slate-600 shadow-sm transition-all duration-300 hover:border-slate-300 hover:bg-slate-50 hover:text-slate-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 active:scale-95 ${className}`}
    >
      <Menu className="w-5 h-5" />
    </button>
  );
}
