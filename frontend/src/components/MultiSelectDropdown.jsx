import React, { useState, useRef, useEffect } from 'react';
import { ChevronDown } from 'lucide-react';

/**
 * Multi-select dropdown — dipakai untuk Machine Group dan Machine.
 */
export default function MultiSelectDropdown({
  options = [],
  selected = [],
  onChange,
  placeholder = 'Pilih...',
  emptyLabel = 'Semua',
  allLabel = 'Tampilkan semua',
  className = '',
  disabled = false,
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    const close = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, []);

  const toggle = (value) => {
    onChange(
      selected.includes(value)
        ? selected.filter((v) => v !== value)
        : [...selected, value],
    );
  };

  const label = selected.length === 0
    ? emptyLabel
    : selected.length === 1
      ? (options.find((o) => o.value === selected[0])?.label || '1 dipilih')
      : `${selected.length} dipilih`;

  return (
    <div className={`relative min-w-[10rem] ${className}`} ref={ref}>
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between gap-2 px-3 py-2.5 text-sm border border-gray-300 rounded-lg bg-white hover:border-gray-400 text-left disabled:opacity-50 disabled:cursor-not-allowed"
      >
        <span className="truncate text-gray-700">{placeholder ? `${placeholder}: ` : ''}{label}</span>
        <ChevronDown className={`w-4 h-4 text-gray-400 shrink-0 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="absolute z-50 mt-1 w-full min-w-[14rem] max-h-56 overflow-y-auto bg-white border border-gray-200 rounded-lg shadow-lg py-1">
          <button
            type="button"
            onClick={() => { onChange([]); setOpen(false); }}
            className="w-full text-left px-3 py-1.5 text-sm text-indigo-600 hover:bg-gray-50 font-medium"
          >
            {allLabel}
          </button>
          <div className="border-t border-gray-100 my-1" />
          {options.map((opt) => (
            <label
              key={opt.value}
              className="flex items-center gap-2.5 px-3 py-2 hover:bg-gray-50 cursor-pointer text-sm text-gray-700"
            >
              <input
                type="checkbox"
                className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                checked={selected.includes(opt.value)}
                onChange={() => toggle(opt.value)}
              />
              <span className="truncate">{opt.label}</span>
            </label>
          ))}
          {options.length === 0 && (
            <p className="px-3 py-2 text-sm text-gray-400">Tidak ada pilihan</p>
          )}
        </div>
      )}
    </div>
  );
}
