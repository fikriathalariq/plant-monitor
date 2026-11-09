/**
 * Warna fase mesin — konsisten di seluruh aplikasi.
 * Heating = merah, Keeping = orange.
 */
export const PHASE_COLORS = {
  HEAT:    { bg: 'bg-red-500',    label: 'Heating',  hex: '#ef4444', light: 'bg-red-100',    text: 'text-red-700' },
  STEADY:  { bg: 'bg-orange-500', label: 'Keeping',  hex: '#f97316', light: 'bg-orange-100', text: 'text-orange-700' },
  COOL:    { bg: 'bg-sky-500',    label: 'Cooling',  hex: '#0ea5e9', light: 'bg-sky-100',    text: 'text-sky-700' },
  RUNNING: { bg: 'bg-emerald-500', label: 'Running', hex: '#10b981', light: 'bg-emerald-100', text: 'text-emerald-700' },
  OFF:     { bg: 'bg-slate-300',  label: 'Off',      hex: '#cbd5e1', light: 'bg-slate-100',  text: 'text-slate-500' },
  OFFLINE: { bg: 'bg-slate-400',  label: 'Offline',  hex: '#94a3b8', light: 'bg-slate-200',  text: 'text-slate-600' },
  NOSIGNAL:{ bg: 'bg-amber-400',  label: 'No Signal', hex: '#fbbf24', light: 'bg-amber-100', text: 'text-amber-800' },
  FAULT:   { bg: 'bg-black',      label: 'Fault',    hex: '#000000', light: 'bg-gray-200',   text: 'text-gray-900' },
  ERROR:   { bg: 'bg-amber-300',  label: 'No Data',  hex: '#fcd34d', light: 'bg-amber-50',   text: 'text-amber-700' },
};

export const STATUS_TILE = {
  HEAT: { bg: 'bg-red-500', ring: 'ring-red-300', text: 'text-white', label: 'HEAT' },
  STEADY: { bg: 'bg-orange-500', ring: 'ring-orange-300', text: 'text-white', label: 'KEEP' },
  COOL: { bg: 'bg-sky-500', ring: 'ring-sky-300', text: 'text-white', label: 'COOL' },
  RUNNING: { bg: 'bg-emerald-500', ring: 'ring-emerald-300', text: 'text-white', label: 'RUN' },
  Running: { bg: 'bg-emerald-500', ring: 'ring-emerald-300', text: 'text-white', label: 'RUN' },
  OFF: { bg: 'bg-slate-100', ring: 'ring-slate-200', text: 'text-slate-400', label: 'OFF', muted: true },
  NOSIGNAL: { bg: 'bg-amber-100', ring: 'ring-amber-300', text: 'text-amber-800', label: 'NO SIG', muted: true },
};

export const STATUS_LEGEND = [
  { key: 'RUNNING', label: 'Run', color: 'bg-emerald-500' },
  { key: 'HEAT', label: 'Heat', color: 'bg-red-500' },
  { key: 'COOL', label: 'Cool', color: 'bg-sky-500' },
  { key: 'STEADY', label: 'Steady', color: 'bg-orange-500' },
  { key: 'OFF', label: 'Off', color: 'bg-slate-300' },
  { key: 'NOSIGNAL', label: 'No Sig', color: 'bg-amber-400' },
];

export const STATUS_BADGE = {
  Running: 'bg-emerald-50 text-emerald-700 ring-emerald-600/20',
  HEAT: 'bg-red-50 text-red-700 ring-red-600/20',
  STEADY: 'bg-orange-50 text-orange-700 ring-orange-600/20',
  COOL: 'bg-sky-50 text-sky-700 ring-sky-600/20',
  Stop: 'bg-slate-50 text-slate-700 ring-slate-600/20',
  'No Signal': 'bg-amber-50 text-amber-800 ring-amber-600/20',
  NOSIGNAL: 'bg-amber-50 text-amber-800 ring-amber-600/20',
};

/** Untuk Daily Report availability bar (hex untuk recharts jika perlu) */
export const AVAILABILITY_PHASE = {
  HEAT:    { bg: 'bg-red-500',    label: 'Heating',  hex: '#ef4444' },
  STEADY:  { bg: 'bg-orange-500', label: 'Keeping',  hex: '#f97316' },
  COOL:    { bg: 'bg-sky-400',    label: 'Cooling',  hex: '#38bdf8' },
  RUNNING: { bg: 'bg-emerald-400', label: 'Running', hex: '#4ade80' },
  OFF:     { bg: 'bg-gray-200',   label: 'Off',      hex: '#e5e7eb' },
};
