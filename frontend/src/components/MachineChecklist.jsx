import React from 'react';

/**
 * Daftar checkbox mesin yang selalu terbuka — gaya port 8000 (/grafik/).
 * Beda dengan dropdown: langsung terlihat semua pilihan tanpa perlu diklik dulu.
 */
export default function MachineChecklist({
  options = [],
  selected = [],
  onChange,
  onSelectAll,
  onClearAll,
}) {
  const allSelected = options.length > 0 && options.every((o) => selected.includes(o.value));

  const toggle = (value) => {
    onChange(
      selected.includes(value)
        ? selected.filter((v) => v !== value)
        : [...selected, value],
    );
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <label className="text-sm font-semibold text-gray-700">Pilih Mesin</label>
        <button
          type="button"
          onClick={allSelected ? onClearAll : onSelectAll}
          className="text-sm text-indigo-600 font-medium hover:underline"
        >
          {allSelected ? 'Kosongkan' : 'Pilih Semua'}
        </button>
      </div>
      <div className="border border-gray-300 rounded-lg bg-gray-50/70 p-2 max-h-64 overflow-y-auto">
        {options.length === 0 ? (
          <p className="text-sm text-gray-400 text-center py-6">Tidak ada mesin</p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-2 gap-y-0.5">
            {options.map((opt) => (
              <label
                key={opt.value}
                className="flex items-center gap-2 px-2 py-1.5 rounded-md hover:bg-white cursor-pointer text-sm text-gray-700"
              >
                <input
                  type="checkbox"
                  checked={selected.includes(opt.value)}
                  onChange={() => toggle(opt.value)}
                  className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500 w-4 h-4 shrink-0"
                />
                <span className="truncate">{opt.label}</span>
              </label>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
