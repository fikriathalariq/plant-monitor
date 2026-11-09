import React, { useState, useEffect, createContext, useContext, useCallback, useRef } from 'react';
import api, { registerUnauthorizedHandler, clearStaleInFlightRequests } from '../lib/api';

const AuthContext = createContext();
const AUTH_CACHE_KEY = 'pm_auth_cache';

function getInitialAuthCache() {
  try {
    const raw = sessionStorage.getItem(AUTH_CACHE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed && parsed.user) {
        return {
          user: parsed.user,
          allowedPages: parsed.allowedPages ?? null,
          hasCache: true,
        };
      }
    }
  } catch {
    // Ignore JSON parsing errors
  }
  return { user: null, allowedPages: null, hasCache: false };
}

export const AuthProvider = ({ children }) => {
  const initialCacheRef = useRef(getInitialAuthCache());
  const [user, setUser] = useState(initialCacheRef.current.user);
  const [allowedPages, setAllowedPages] = useState(initialCacheRef.current.allowedPages); // null = superuser/staff (semua diizinkan)
  const [loading, setLoading] = useState(!initialCacheRef.current.hasCache);
  const lastActiveRef = useRef(Date.now());

  const fetchSession = useCallback((options = {}) => {
    return api
      .get('/auth/me', { cache: false })
      .then((res) => {
        if (res.data.authenticated) {
          const userData = { 
            username: res.data.username, 
            isStaff: !!res.data.is_staff,
            role: res.data.role 
          };
          const pages = res.data.is_staff ? null : (res.data.allowed_pages || []);
          setUser(userData);
          setAllowedPages(pages);
          try {
            sessionStorage.setItem(
              AUTH_CACHE_KEY,
              JSON.stringify({ user: userData, allowedPages: pages })
            );
          } catch {
            // Ignore sessionStorage errors
          }
        } else {
          setUser(null);
          setAllowedPages([]);
          try {
            sessionStorage.removeItem(AUTH_CACHE_KEY);
          } catch {
            // Ignore
          }
        }
      })
      .catch((err) => {
        // Jika fetchSession gagal karena unauthorized (401), kosongkan state
        if (err.response?.status === 401) {
          setUser(null);
          setAllowedPages([]);
          try {
            sessionStorage.removeItem(AUTH_CACHE_KEY);
          } catch {
            // Ignore
          }
        }
      });
  }, []);

  useEffect(() => {
    fetchSession().finally(() => setLoading(false));
  }, [fetchSession]);

  useEffect(() => {
    // Jika session Django habis (401 dari API manapun atau HTML redirect), paksa balik ke login
    registerUnauthorizedHandler(() => {
      setUser(null);
      setAllowedPages([]);
      try {
        sessionStorage.removeItem(AUTH_CACHE_KEY);
      } catch {
        // Ignore
      }
    });
  }, []);

  // Idle Tab Wakeup & Network Reconnect Handler
  // Jika tab ditinggalkan lama (> 3 menit) lalu dibuka kembali atau reconnect,
  // bersihkan in-flight requests yang menggantung dan verifikasi session di background
  useEffect(() => {
    const handleWakeup = () => {
      const now = Date.now();
      const elapsedMinutes = (now - lastActiveRef.current) / (1000 * 60);
      lastActiveRef.current = now;

      if (elapsedMinutes >= 3) {
        clearStaleInFlightRequests();
        fetchSession();
      }
    };

    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        handleWakeup();
      } else {
        lastActiveRef.current = Date.now();
      }
    };

    const onOnline = () => {
      clearStaleInFlightRequests();
      fetchSession();
    };

    document.addEventListener('visibilitychange', onVisibilityChange);
    window.addEventListener('online', onOnline);

    return () => {
      document.removeEventListener('visibilitychange', onVisibilityChange);
      window.removeEventListener('online', onOnline);
    };
  }, [fetchSession]);

  const login = async (username, password) => {
    const res = await api.post('/auth/login', { username, password });
    if (res.data.success) {
      await fetchSession();
      return true;
    }
    return false;
  };

  const logout = async () => {
    try {
      await api.post('/auth/logout');
    } catch {
      // Ignore logout errors
    } finally {
      setUser(null);
      setAllowedPages([]);
      try {
        sessionStorage.removeItem(AUTH_CACHE_KEY);
      } catch {
        // Ignore
      }
    }
  };

  // allowedPages === null berarti user staff/superuser -> semua halaman diizinkan
  const canAccess = (pageCode) => {
    if (!pageCode) return true;
    if (allowedPages === null) return true;
    return allowedPages.includes(pageCode);
  };

  return (
    <AuthContext.Provider value={{ user, allowedPages, login, logout, loading, canAccess }}>
      {loading ? (
        <div className="flex h-screen w-screen items-center justify-center bg-slate-900 text-slate-300">
          <div className="flex flex-col items-center gap-3">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
            <span className="text-xs font-semibold tracking-wider text-slate-400">MEMUAT SISTEM...</span>
          </div>
        </div>
      ) : (
        children
      )}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
