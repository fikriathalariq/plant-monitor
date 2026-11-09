import { useChat } from '../../context/ChatContext';
import React, { useState, useEffect } from 'react';
import { ChevronRight } from 'lucide-react';
import { Link, useLocation } from 'react-router-dom';

export function NavbarLinksGroup({ icon: Icon, label, path, links, collapsed, closeTabletOverlay }) {
  const { toggleChat, unreadCount } = useChat();
  const hasLinks = Array.isArray(links);
  const [opened, setOpened] = useState(false);
  const location = useLocation();

  const isMatch = (p) => location.pathname === p || (p !== '/' && location.pathname.startsWith(p + '/'));
  const isActive = hasLinks
    ? links.some((link) => isMatch(link.path))
    : isMatch(path);

  useEffect(() => {
    if (isActive && hasLinks && !collapsed) {
      setOpened(true);
    }
  }, [isActive, hasLinks, collapsed]);

  const handleClick = (e) => {
    if (path === '#chat') {
      e.preventDefault();
      toggleChat();
      if (closeTabletOverlay) {
        closeTabletOverlay();
      }
      return;
    }
    if (hasLinks) {
      e.preventDefault();
      setOpened((o) => !o);
    } else {
      if (closeTabletOverlay) {
        closeTabletOverlay();
      }
    }
  };

  // Render flat link
  if (!hasLinks) {
    return (
      <Link
        to={path}
        onClick={handleClick}
        title={collapsed ? label : undefined}
        className={`group flex items-center px-3 py-2 rounded-md text-sm font-medium transition-colors mb-0.5 overflow-hidden whitespace-nowrap ${
          isActive
            ? 'bg-blue-50 text-blue-700'
            : 'text-slate-600 hover:bg-slate-100/80 hover:text-slate-900'
        }`}
      >
        <div className="relative shrink-0">
          <Icon className={`w-5 h-5 shrink-0 transition-colors ${isActive ? 'text-blue-600' : 'text-slate-400 group-hover:text-slate-600'}`} />
          {path === '#chat' && collapsed && unreadCount > 0 && (
            <span className="absolute -top-1 -right-1 w-2.5 h-2.5 rounded-full bg-rose-500 ring-2 ring-white" />
          )}
        </div>
        <div className={`transition-all duration-300 overflow-hidden ${collapsed ? 'w-0 opacity-0' : 'flex-1 opacity-100 ml-3 flex items-center justify-between'}`}>
          <span className="truncate block">
            {label}
          </span>
          {path === '#chat' && unreadCount > 0 && (
            <span className="ml-1.5 px-1.5 py-0.2 rounded-full bg-rose-500 text-white text-[9.5px] font-extrabold shadow-2xs">
              {unreadCount > 99 ? '99+' : unreadCount}
            </span>
          )}
        </div>
      </Link>
    );
  }

  // Render accordion group
  return (
    <div className="mb-0.5">
      <button
        type="button"
        onClick={handleClick}
        title={collapsed ? label : undefined}
        className={`w-full group flex items-center justify-between px-3 py-2 rounded-md text-sm font-medium transition-colors overflow-hidden whitespace-nowrap ${
          isActive && !opened ? 'bg-blue-50/50' : 'hover:bg-slate-100/80'
        }`}
      >
        <div className="flex items-center min-w-0 shrink-0">
          <Icon className={`w-5 h-5 shrink-0 transition-colors ${isActive ? 'text-blue-600' : 'text-slate-400 group-hover:text-slate-600'}`} />
          <div className={`transition-all duration-300 overflow-hidden ${collapsed ? 'w-0 opacity-0' : 'flex-1 opacity-100 ml-3'}`}>
            <span className={`truncate block ${isActive ? 'text-blue-700 font-semibold' : 'text-slate-700'}`}>
              {label}
            </span>
          </div>
        </div>
        <ChevronRight 
          className={`shrink-0 text-slate-400 transition-all duration-300 ${opened ? 'rotate-90' : ''} ${collapsed ? 'w-0 opacity-0 translate-x-4' : 'w-4 h-4 opacity-100 translate-x-0'}`} 
        />
      </button>

      {/* Sub-menu with height animation */}
      <div 
        className="overflow-hidden transition-all duration-300 ease-in-out" 
        style={{ 
          maxHeight: !collapsed && opened ? `${links.length * 44}px` : '0px', 
          opacity: !collapsed && opened ? 1 : 0 
        }}
      >
        <div className="ml-5 mt-1 space-y-0.5 border-l border-slate-200 pl-2 pb-1">
          {links.map((link) => {
            const isSubActive = location.pathname === link.path;
            return (
              <Link
                key={link.label}
                to={link.path}
                onClick={closeTabletOverlay}
                className={`block px-3 py-2 text-sm rounded-md transition-colors truncate ${
                  isSubActive
                    ? 'text-blue-700 font-medium bg-blue-50/50'
                    : 'text-slate-500 hover:text-slate-900 hover:bg-slate-50'
                }`}
              >
                {link.label}
              </Link>
            );
          })}
        </div>
      </div>
    </div>
  );
}
