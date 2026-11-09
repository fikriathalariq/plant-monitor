import React from 'react';
import { LogOut, MessageSquare } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useChat } from '../../context/ChatContext';

export function UserButton({ collapsed }) {
  const { user, logout } = useAuth();
  const { toggleChat, unreadCount } = useChat();
  
  if (!user) return null;

  const initial = user.username ? user.username.charAt(0).toUpperCase() : 'U';

  return (
    <div className="pl-6 pr-4 py-3 border-t border-slate-200/80 bg-slate-50/50 flex items-center overflow-hidden whitespace-nowrap">
      <div 
        className="w-8 h-8 rounded-full bg-gradient-to-tr from-blue-600 to-indigo-600 flex items-center justify-center text-white font-bold text-xs shrink-0 shadow-sm"
        title={collapsed ? `${user.username} (${user.role || 'Operator'})` : undefined}
      >
        {initial}
      </div>
      
      <div className={`transition-all duration-300 overflow-hidden ${collapsed ? 'w-0 opacity-0' : 'flex-1 opacity-100 ml-3'}`}>
        <p className="text-xs font-semibold text-slate-800 truncate">{user.username}</p>
        <p className="text-[10px] text-slate-500 capitalize truncate">{user.role || 'Operator'}</p>
      </div>

      <button
        type="button"
        onClick={toggleChat}
        title="Buka Chat Jaringan Lokal"
        className={`relative flex items-center justify-center text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition-all duration-300 shrink-0 cursor-pointer ${
          collapsed ? 'w-0 h-0 opacity-0 translate-x-4 pointer-events-none' : 'w-7 h-7 ml-1 opacity-100 translate-x-0'
        }`}
      >
        <MessageSquare className="w-4 h-4 shrink-0" />
        {unreadCount > 0 && (
          <span className="absolute -top-1 -right-1 flex h-4 min-w-4 px-0.5 items-center justify-center rounded-full bg-rose-500 text-[8.5px] font-extrabold text-white animate-pulse">
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </button>

      <button
        type="button"
        onClick={logout}
        title="Keluar / Logout"
        className={`flex items-center justify-center text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-all duration-300 shrink-0 cursor-pointer ${
          collapsed ? 'w-0 h-0 opacity-0 translate-x-4 pointer-events-none' : 'w-7 h-7 ml-1 opacity-100 translate-x-0'
        }`}
      >
        <LogOut className="w-4 h-4 shrink-0" />
      </button>
    </div>
  );
}
