import React from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { AlertTriangle, Home, RotateCcw, RefreshCw } from 'lucide-react';

class ErrorBoundaryClass extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    console.error('ErrorBoundary caught an error:', error, info);
  }

  componentDidUpdate(prevProps) {
    // Otomatis reset error jika rute berpindah sehingga user tidak terkunci pada layar error
    if (this.state.hasError && prevProps.location?.pathname !== this.props.location?.pathname) {
      this.setState({ hasError: false, error: null });
    }
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
  };

  handleGoHome = () => {
    this.setState({ hasError: false, error: null });
    if (this.props.navigate) {
      this.props.navigate('/home');
    } else {
      window.location.href = '/home';
    }
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex min-h-[70vh] w-full items-center justify-center bg-slate-50 p-6">
          <div className="bg-white rounded-2xl shadow-sm border border-rose-100 p-8 max-w-md w-full text-center">
            {/* Warning Icon Badge */}
            <div className="w-14 h-14 rounded-2xl bg-rose-50 border border-rose-200 flex items-center justify-center mx-auto mb-5 text-rose-500 shadow-sm">
              <AlertTriangle className="w-7 h-7" />
            </div>

            <h2 className="text-xl font-bold text-slate-900 mb-2">Terjadi Kesalahan</h2>
            <p className="text-slate-500 text-sm mb-6 leading-relaxed">
              Halaman ini gagal dimuat atau mengalami kendala teknis. Anda dapat kembali ke halaman utama (Home) atau mencoba memuat ulang.
            </p>

            {/* Tombol Aksi */}
            <div className="flex flex-col gap-2.5 w-full">
              {/* Opsi Utama: Kembali ke Home */}
              <button
                type="button"
                onClick={this.handleGoHome}
                className="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-xl font-medium transition-colors text-sm shadow-sm cursor-pointer"
              >
                <Home className="w-4 h-4" />
                Kembali ke Halaman Home
              </button>

              <div className="grid grid-cols-2 gap-2 pt-1">
                <button
                  type="button"
                  onClick={this.handleReset}
                  className="inline-flex items-center justify-center gap-1.5 px-3 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl font-medium transition-colors text-xs cursor-pointer border border-slate-200"
                >
                  <RotateCcw className="w-3.5 h-3.5" />
                  Coba Lagi
                </button>
                <button
                  type="button"
                  onClick={() => window.location.reload()}
                  className="inline-flex items-center justify-center gap-1.5 px-3 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl font-medium transition-colors text-xs cursor-pointer border border-slate-200"
                >
                  <RefreshCw className="w-3.5 h-3.5" />
                  Muat Ulang
                </button>
              </div>
            </div>

            {/* Collapsible detail teknis untuk admin/developer */}
            {this.state.error && (
              <details className="mt-5 text-left border-t border-slate-100 pt-3">
                <summary className="text-[11px] text-slate-400 hover:text-slate-600 cursor-pointer select-none">
                  Lihat detail teknis kesalahan
                </summary>
                <div className="mt-2 p-2.5 bg-slate-900 text-slate-200 rounded-lg text-[11px] font-mono overflow-x-auto max-h-36 leading-relaxed">
                  {this.state.error?.toString() || 'Unknown Error'}
                </div>
              </details>
            )}
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

export default function ErrorBoundary({ children }) {
  const location = useLocation();
  const navigate = useNavigate();
  return <ErrorBoundaryClass location={location} navigate={navigate}>{children}</ErrorBoundaryClass>;
}
