import React from 'react';

/** API "YYYY-MM-DD HH:MM" ↔ input datetime-local "YYYY-MM-DDTHH:MM" */
export function toDateTimeLocalValue(apiValue) {
  if (!apiValue) return '';
  const normalized = apiValue.trim().replace('T', ' ');
  const m = normalized.match(/^(\d{4}-\d{2}-\d{2})\s+(\d{2}):(\d{2})/);
  if (!m) return '';
  return `${m[1]}T${m[2]}:${m[3]}`;
}

export function fromDateTimeLocalValue(localValue) {
  if (!localValue) return '';
  return localValue.replace('T', ' ');
}

/**
 * Pemilih tanggal & waktu native (kalender + jam/menit) — sama seperti /grafik/ port 8000.
 * Nilai API: "YYYY-MM-DD HH:MM"
 */
export default function DateTimePicker({ value, onChange, disabled = false, className = '' }) {
  return (
    <input
      type="datetime-local"
      value={toDateTimeLocalValue(value)}
      disabled={disabled}
      onChange={(e) => onChange(fromDateTimeLocalValue(e.target.value))}
      className={`w-full border border-gray-300 rounded-md text-sm px-3 py-2.5 bg-white disabled:opacity-50 disabled:cursor-not-allowed [color-scheme:light] ${className}`}
    />
  );
}
