import React, { useState, useEffect } from 'react';
import { Activity, LogOut, MessageSquare } from 'lucide-react';
import { useChat } from '../context/ChatContext';
import { useAuth } from '../context/AuthContext';
import api, { BACKEND_BASE_URL, fetchBrandingCached } from '../lib/api';

export function MobileHeader() {
  const { user, logout } = useAuth();
  const { toggleChat, unreadCount } = useChat();
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

  const initial = user?.username ? user.username.charAt(0).toUpperCase() : 'U';

  return (
    <header className="no-print shrink-0 h-14 bg-white border-b border-slate-200/80 flex items-center justify-between px-4 z-20 shadow-sm relative">
      <div className="flex items-center min-w-0">
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
      
      <div className="flex items-center shrink-0 ml-4 gap-2">
        <button
          type="button"
          onClick={toggleChat}
          title="Buka Chat"
          className="relative p-1.5 text-slate-600 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors"
        >
          <MessageSquare className="w-5 h-5" />
          {unreadCount > 0 && (
            <span className="absolute -top-0.5 -right-0.5 flex h-4 min-w-4 px-0.5 items-center justify-center rounded-full bg-rose-500 text-[9px] font-extrabold text-white">
              {unreadCount > 99 ? '99+' : unreadCount}
            </span>
          )}
        </button>
        <div 
          className="w-8 h-8 rounded-full bg-gradient-to-tr from-blue-600 to-indigo-600 flex items-center justify-center text-white font-bold text-xs shadow-sm"
          title={`${user?.username || 'User'} (${user?.role || 'Operator'})`}
        >
          {initial}
        </div>
        <button
          type="button"
          onClick={logout}
          title="Keluar / Logout"
          className="ml-2 p-1.5 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-all duration-300"
        >
          <LogOut className="w-5 h-5" />
        </button>
      </div>
    </header>
  );
}

