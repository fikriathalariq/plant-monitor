import React from 'react';
import { Link } from 'react-router-dom';
import { ShieldAlert } from 'lucide-react';

const AccessDenied = ({ pageCode }) => {
  return (
    <div className="flex h-full w-full items-center justify-center bg-gray-50 p-6">
      <div className="bg-white rounded-xl shadow-sm border border-red-100 p-8 max-w-md text-center">
        <ShieldAlert className="w-12 h-12 text-red-500 mx-auto mb-4" />
        <h2 className="text-xl font-bold text-gray-900 mb-2">Akses Ditolak</h2>
        <p className="text-gray-500 text-sm mb-1">
          Anda tidak memiliki izin untuk mengakses halaman ini{pageCode ? ` (${pageCode})` : ''}.
        </p>
        <p className="text-gray-400 text-xs mb-6">
          Hubungi administrator jika Anda merasa seharusnya memiliki akses.
        </p>
        <Link
          to="/home"
          className="inline-block px-4 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 font-medium transition-colors"
        >
          Kembali ke Home
        </Link>
      </div>
    </div>
  );
};

export default AccessDenied;
