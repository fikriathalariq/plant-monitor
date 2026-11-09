import React, { useState, useEffect, useRef } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { 
  User, 
  Lock, 
  Eye, 
  EyeOff, 
  Loader2, 
  AlertCircle, 
  Flame, 
  Activity, 
  ArrowRight,
  Gauge,
  Layers,
  MessageCircle
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import api, { BACKEND_BASE_URL, fetchBrandingCached } from '../lib/api';

const REMEMBERED_USER_KEY = 'plant_monitor_remembered_username';

const Login = () => {
  const { urlUsername, '*': urlPassword } = useParams();
  const [searchParams] = useSearchParams();

  const [username, setUsername] = useState(() => {
    return searchParams.get('username') || urlUsername || localStorage.getItem(REMEMBERED_USER_KEY) || '';
  });
  const [password, setPassword] = useState('');
  const [rememberMe, setRememberMe] = useState(() => !!localStorage.getItem(REMEMBERED_USER_KEY));
  const [showPassword, setShowPassword] = useState(false);
  const [capsLockActive, setCapsLockActive] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(() => {
    return searchParams.get('error') || '';
  });

  // Branding dari CompanyProfile
  const [logoUrl, setLogoUrl] = useState('/suritex-logo.jpg');
  const [companyName, setCompanyName] = useState('PT. Suritex');
  const [imgError, setImgError] = useState(false);

  const { login } = useAuth();
  const navigate = useNavigate();
  const usernameInputRef = useRef(null);
  const passwordInputRef = useRef(null);

  useEffect(() => {
    // Ambil branding dinamis dari backend CompanyProfile
    fetchBrandingCached()
      .then((res) => {
        if (res.data.logo_url) {
          setLogoUrl(`${BACKEND_BASE_URL}${res.data.logo_url}`);
        }
        if (res.data.name) {
          setCompanyName(res.data.name);
        }
      })
      .catch(() => {
        // Fallback default sudah /suritex-logo.jpg
      });
  }, []);

  // Auto-login jika parameter urlUsername & urlPassword terdeteksi di URL
  useEffect(() => {
    if (urlUsername && urlPassword) {
      try {
        const cleanUser = decodeURIComponent(urlUsername).trim();
        const cleanPass = decodeURIComponent(urlPassword).replace(/\/+$/, '');
        if (cleanUser && cleanPass) {
          setSubmitting(true);
          login(cleanUser, cleanPass)
            .then((ok) => {
              if (ok) {
                const nextUrl = searchParams.get('next');
                if (nextUrl && nextUrl.startsWith('/') && !nextUrl.startsWith('/api') && !nextUrl.startsWith('/admin')) {
                  navigate(nextUrl, { replace: true });
                } else {
                  navigate('/home', { replace: true });
                }
              } else {
                setError('Login otomatis gagal: Username atau password salah.');
                setUsername(cleanUser);
                setSubmitting(false);
              }
            })
            .catch((err) => {
              const msg = err.response?.data?.message || 'Login otomatis gagal. Silakan periksa kredensial Anda.';
              setError(msg);
              setUsername(cleanUser);
              setSubmitting(false);
            });
        }
      } catch (e) {
        console.error('Error auto-logging in:', e);
      }
    }
  }, [urlUsername, urlPassword]);

  useEffect(() => {
    // Fokus otomatis pada kolom yang belum terisi
    if (username) {
      passwordInputRef.current?.focus();
    } else {
      usernameInputRef.current?.focus();
    }
  }, []);

  const handleKeyDown = (e) => {
    if (e.getModifierState) {
      setCapsLockActive(e.getModifierState('CapsLock'));
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (submitting) return;

    setError('');
    setSubmitting(true);

    try {
      const ok = await login(username.trim(), password);
      if (ok) {
        if (rememberMe) {
          localStorage.setItem(REMEMBERED_USER_KEY, username.trim());
        } else {
          localStorage.removeItem(REMEMBERED_USER_KEY);
        }
        const params = new URLSearchParams(window.location.search);
        const nextUrl = params.get('next');
        if (nextUrl) {
          if (nextUrl.startsWith('/') && !nextUrl.startsWith('/api') && !nextUrl.startsWith('/admin')) {
            navigate(nextUrl, { replace: true });
          } else {
            window.location.href = nextUrl;
          }
        } else {
          navigate('/home', { replace: true });
        }
      } else {
        setError('Username atau password salah. Silakan periksa kembali kredensial Anda.');
      }
    } catch (err) {
      const msg = err.response?.data?.message || 'Gagal terhubung ke server. Periksa koneksi jaringan atau coba beberapa saat lagi.';
      setError(msg);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen w-full flex bg-slate-900 text-slate-800 antialiased selection:bg-indigo-500 selection:text-white">
      {/* ═══════════════════════════════════════════════════════════════════ */}
      {/* LEFT SIDE: HERO INDUSTRIAL SHOWCASE (DESKTOP ONLY)                 */}
      {/* ═══════════════════════════════════════════════════════════════════ */}
      <div className="hidden lg:flex lg:w-7/12 xl:w-3/5 relative bg-gradient-to-br from-slate-950 via-slate-900 to-indigo-950 p-12 flex-col justify-between overflow-hidden border-r border-slate-800">
        {/* Decorative Ambient Glows */}
        <div className="absolute -top-32 -left-32 w-96 h-96 bg-indigo-500/10 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute bottom-0 right-0 w-[500px] h-[500px] bg-blue-600/10 rounded-full blur-3xl pointer-events-none" />
        
        {/* Technical Grid Pattern */}
        <div 
          className="absolute inset-0 opacity-[0.03] pointer-events-none"
          style={{
            backgroundImage: `radial-gradient(circle at 1px 1px, #ffffff 1px, transparent 0)`,
            backgroundSize: '24px 24px'
          }}
        />

        {/* Top: Company Header & Brand */}
        <div className="relative z-10 flex items-center gap-4">
          <div className="w-14 h-14 rounded-2xl bg-white p-1.5 shadow-xl shadow-black/40 border border-white/20 flex items-center justify-center shrink-0">
            {logoUrl && !imgError ? (
              <img 
                src={logoUrl} 
                alt={`${companyName} Logo`} 
                onError={() => setImgError(true)} 
                className="w-full h-full object-contain rounded-xl"
              />
            ) : (
              <Activity className="w-8 h-8 text-indigo-600" />
            )}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-lg font-black tracking-tight text-white">{companyName}</span>
              <span className="px-2 py-0.5 rounded-full text-[10px] font-extrabold uppercase tracking-wider bg-indigo-500/20 text-indigo-300 border border-indigo-400/30">
                Dyeing &amp; Finishing
              </span>
            </div>
            <p className="text-xs text-slate-400">Intelligent Plant Operations &amp; Thermodynamic Monitoring</p>
          </div>
        </div>

        {/* Middle: Value Proposition & Hero Highlights */}
        <div className="relative z-10 my-auto py-10 max-w-xl space-y-6">
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-white/5 border border-white/10 backdrop-blur-md">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            <span className="text-xs font-semibold text-slate-300">PINN &amp; AI Physics-Informed Neural Network</span>
          </div>

          <h1 className="text-3xl xl:text-4xl font-black text-white tracking-tight leading-tight">
            Sistem Terpadu Diagnostik Energi &amp; Monitoring Mesin Pintar
          </h1>

          <p className="text-sm text-slate-300 leading-relaxed">
            Platform analitik terintegrasi untuk mendeteksi deviasi siklus celup, kebocoran uap riil vs ideal, serta kalkulasi akuntabilitas kinerja antar-shift kerja secara presisi.
          </p>

          {/* 3 Industrial Feature Badges */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-3">
            <div className="bg-white/5 backdrop-blur-sm p-3.5 rounded-xl border border-white/10 space-y-1.5 hover:bg-white/10 transition-colors">
              <div className="w-8 h-8 rounded-lg bg-orange-500/20 text-orange-400 flex items-center justify-center">
                <Flame className="w-4 h-4" />
              </div>
              <h4 className="text-xs font-bold text-white">Loss Uap &amp; Listrik</h4>
              <p className="text-[11px] text-slate-400 leading-snug">Attribution finansial kebocoran uap boiler &amp; penalti WBP.</p>
            </div>

            <div className="bg-white/5 backdrop-blur-sm p-3.5 rounded-xl border border-white/10 space-y-1.5 hover:bg-white/10 transition-colors">
              <div className="w-8 h-8 rounded-lg bg-blue-500/20 text-blue-400 flex items-center justify-center">
                <Gauge className="w-4 h-4" />
              </div>
              <h4 className="text-xs font-bold text-white">Normalitas Mesin</h4>
              <p className="text-[11px] text-slate-400 leading-snug">Benchmark 60 batch historis per program &amp; audit 3 fase.</p>
            </div>

            <div className="bg-white/5 backdrop-blur-sm p-3.5 rounded-xl border border-white/10 space-y-1.5 hover:bg-white/10 transition-colors">
              <div className="w-8 h-8 rounded-lg bg-indigo-500/20 text-indigo-400 flex items-center justify-center">
                <Layers className="w-4 h-4" />
              </div>
              <h4 className="text-xs font-bold text-white">Akuntabilitas Shift</h4>
              <p className="text-[11px] text-slate-400 leading-snug">Transparansi kedisiplinan waktu jeda changeover antar-shift.</p>
            </div>
          </div>
        </div>

        {/* Bottom: System Status Footer */}
        <div className="relative z-10 pt-6 border-t border-slate-800/80 flex items-center justify-between text-xs text-slate-400">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-emerald-500 inline-block" />
            <span>Server &amp; IoT Gateway: <strong className="text-slate-200">Operasional</strong></span>
          </div>
          <span className="text-[11px] text-slate-500 font-mono">Suritex Plant Monitor v2.4</span>
        </div>
      </div>

      {/* ═══════════════════════════════════════════════════════════════════ */}
      {/* RIGHT SIDE: LOGIN FORM CARD (DESKTOP & MOBILE RESPONSIVE)          */}
      {/* ═══════════════════════════════════════════════════════════════════ */}
      <div className="w-full lg:w-5/12 xl:w-2/5 min-h-screen bg-slate-50 flex flex-col justify-between p-6 sm:p-10 lg:p-12 overflow-y-auto">
        <div className="w-full max-w-sm mx-auto my-auto space-y-6">
          {/* Mobile Header Branding (Shown on mobile, hidden on lg) */}
          <div className="lg:hidden text-center space-y-3 pb-2">
            <div className="inline-flex w-16 h-16 rounded-2xl bg-white p-2 shadow-md border border-slate-200 items-center justify-center">
              {logoUrl && !imgError ? (
                <img 
                  src={logoUrl} 
                  alt={`${companyName} Logo`} 
                  onError={() => setImgError(true)} 
                  className="w-full h-full object-contain rounded-xl"
                />
              ) : (
                <Activity className="w-8 h-8 text-indigo-600" />
              )}
            </div>
            <div>
              <h2 className="text-xl font-black text-slate-900 tracking-tight">{companyName}</h2>
              <p className="text-xs text-slate-500">Plant Monitoring &amp; Energy Intelligence</p>
            </div>
          </div>

          {/* Form Header */}
          <div className="space-y-1 text-center lg:text-left">
            <h2 className="text-2xl font-black text-slate-900 tracking-tight">Selamat Datang</h2>
            <p className="text-xs sm:text-sm text-slate-500">
              Silakan masukkan kredensial untuk mengakses dashboard analitik.
            </p>
          </div>

          {/* Error Alert Banner */}
          {error && (
            <div className="bg-rose-50 border border-rose-200 rounded-xl p-3.5 flex items-start gap-3 text-xs text-rose-800 animate-in fade-in duration-200">
              <AlertCircle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
              <div className="flex-1 font-medium">{error}</div>
            </div>
          )}

          {/* Login Form */}
          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Username Field */}
            <div className="space-y-1.5">
              <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider">
                Username / NIK Operator
              </label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
                  <User className="w-4 h-4" />
                </div>
                <input
                  ref={usernameInputRef}
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="Masukkan username..."
                  required
                  disabled={submitting}
                  autoComplete="username"
                  className="w-full pl-10 pr-3.5 py-2.5 bg-white border border-slate-300 rounded-xl text-sm text-slate-800 placeholder-slate-400 shadow-2xs focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-600 transition-all disabled:bg-slate-100 disabled:cursor-not-allowed"
                />
              </div>
            </div>

            {/* Password Field */}
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider">
                  Password
                </label>
                <div className="flex items-center gap-2">
                  {capsLockActive && (
                    <span className="text-[10px] font-bold text-amber-600 bg-amber-50 border border-amber-200 px-1.5 py-0.5 rounded">
                      ⚠️ Caps Lock
                    </span>
                  )}
                  <a
                    href="https://wa.me/6285823818266?text=Halo%20Admin%2C%20saya%20mengalami%20kendala%20lupa%20kata%20sandi%20di%20Plant%20Monitor"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs font-semibold text-indigo-600 hover:text-indigo-700 hover:underline transition-colors cursor-pointer"
                  >
                    Lupa sandi?
                  </a>
                </div>
              </div>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
                  <Lock className="w-4 h-4" />
                </div>
                <input
                  ref={passwordInputRef}
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  onKeyDown={handleKeyDown}
                  onKeyUp={handleKeyDown}
                  placeholder="••••••••"
                  required
                  disabled={submitting}
                  autoComplete="current-password"
                  className="w-full pl-10 pr-10 py-2.5 bg-white border border-slate-300 rounded-xl text-sm text-slate-800 placeholder-slate-400 shadow-2xs focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-600 transition-all disabled:bg-slate-100 disabled:cursor-not-allowed"
                />
                <button
                  type="button"
                  tabIndex={-1}
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute inset-y-0 right-0 pr-3 flex items-center text-slate-400 hover:text-slate-600 transition-colors cursor-pointer"
                  title={showPassword ? 'Sembunyikan password' : 'Tampilkan password'}
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            {/* Remember Me Checkbox */}
            <div className="flex items-center justify-between pt-1">
              <label className="flex items-center gap-2 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={rememberMe}
                  onChange={(e) => setRememberMe(e.target.checked)}
                  disabled={submitting}
                  className="w-4 h-4 rounded text-indigo-600 border-slate-300 focus:ring-indigo-500 cursor-pointer"
                />
                <span className="text-xs font-medium text-slate-600">Ingat username saya</span>
              </label>

              <span className="text-[11px] text-slate-400 hidden sm:inline">
                Sesi Terenkripsi
              </span>
            </div>

            {/* Submit Button */}
            <button
              type="submit"
              disabled={submitting}
              className="w-full py-2.5 px-4 bg-indigo-600 hover:bg-indigo-700 active:scale-[0.99] text-white text-sm font-bold rounded-xl shadow-md shadow-indigo-600/20 transition-all flex items-center justify-center gap-2 cursor-pointer disabled:opacity-75 disabled:cursor-not-allowed disabled:active:scale-100 mt-2"
            >
              {submitting ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Memverifikasi Kredensial...</span>
                </>
              ) : (
                <>
                  <span>Masuk ke Dashboard</span>
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>
          </form>

          {/* Support / Help Info via WhatsApp */}
          <div className="pt-4 border-t border-slate-200 text-center space-y-2">
            <p className="text-xs text-slate-500">
              Kendala akses akun atau lupa kata sandi?
            </p>
            <a
              href="https://wa.me/6285823818266?text=Halo%20Admin%2C%20saya%20mengalami%20kendala%20lupa%20kata%20sandi%20akun%20Plant%20Monitor"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center justify-center gap-2 text-xs font-bold text-emerald-800 hover:text-emerald-900 bg-emerald-50 hover:bg-emerald-100 border border-emerald-300/80 px-4 py-2 rounded-xl transition-all shadow-2xs group cursor-pointer w-full"
            >
              <MessageCircle className="w-4 h-4 text-emerald-600 group-hover:scale-110 transition-transform" />
              <span>WhatsApp Admin: +62 858-2381-8266</span>
            </a>
          </div>
        </div>

        {/* Mobile / Screen Bottom Copyright */}
        <div className="text-center pt-6 text-[11px] text-slate-400">
          &copy; {new Date().getFullYear()} {companyName} &bull; Plant Monitor Platform
        </div>
      </div>
    </div>
  );
};

export default Login;
