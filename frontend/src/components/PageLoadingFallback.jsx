import React, { useState, useEffect } from 'react';

export default function PageLoadingFallback() {
  const [showSlowNotice, setShowSlowNotice] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => {
      setShowSlowNotice(true);
    }, 7000);
    return () => clearTimeout(timer);
  }, []);

  return (
    <div className="flex flex-col items-center justify-center min-h-[50vh] w-full p-8 transition-opacity duration-200">
      <div className="relative flex items-center justify-center">
        <div className="h-9 w-9 animate-spin rounded-full border-2 border-blue-600/20 border-t-blue-600" />
      </div>
      <p className="mt-3 text-xs font-medium text-slate-400">Memuat halaman...</p>
      {showSlowNotice && (
        <div className="mt-4 flex flex-col items-center gap-2 text-center">
          <p className="text-xs text-amber-500/90 max-w-xs">
            Pemuatan memerlukan waktu lebih lama dari biasanya.
          </p>
          <button
            onClick={() => window.location.reload()}
            className="text-xs px-3 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded border border-slate-700 transition-colors cursor-pointer"
          >
            Segarkan Halaman
          </button>
        </div>
      )}
    </div>
  );
}
