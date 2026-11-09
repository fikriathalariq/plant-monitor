import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Compass, Home, ArrowLeft } from 'lucide-react';

export default function NotFound() {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen w-full flex items-center justify-center bg-slate-900 text-slate-100 p-6 selection:bg-indigo-500 selection:text-white">
      <div className="max-w-md w-full text-center flex flex-col items-center">
        {/* Glow & Icon */}
        <div className="relative mb-6">
          <div className="absolute inset-0 bg-blue-500/20 rounded-full blur-2xl" />
          <div className="relative w-20 h-20 rounded-2xl bg-slate-800/80 border border-slate-700/80 flex items-center justify-center shadow-xl">
            <Compass className="w-10 h-10 text-blue-400 animate-pulse" />
          </div>
        </div>

        <span className="text-xs font-bold tracking-widest uppercase text-blue-400 mb-2">
          Error 404
        </span>
        <h1 className="text-2xl sm:text-3xl font-extrabold text-white mb-2 tracking-tight">
          Halaman Tidak Ditemukan
        </h1>
        <p className="text-sm text-slate-400 mb-8 leading-relaxed">
          Tautan yang Anda tuju mungkin salah ketik, sudah dipindahkan, atau tidak tersedia di sistem ini.
        </p>

        <div className="flex flex-col sm:flex-row items-center gap-3 w-full justify-center">
          <button
            type="button"
            onClick={() => { if (window.history.state && typeof window.history.state.idx === "number" && window.history.state.idx > 0) { navigate(-1); } else { navigate("/home"); } }}
            className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-sm font-semibold transition-all border border-slate-700 hover:border-slate-600"
          >
            <ArrowLeft className="w-4 h-4" />
            Kembali
          </button>
          <button
            type="button"
            onClick={() => navigate('/home')}
            className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold shadow-lg shadow-blue-500/25 transition-all"
          >
            <Home className="w-4 h-4" />
            Ke Beranda
          </button>
        </div>
      </div>
    </div>
  );
}
