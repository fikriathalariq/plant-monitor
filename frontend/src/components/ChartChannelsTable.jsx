import React, { useState, useCallback } from 'react';
import { Trash2, X, Copy, Check } from 'lucide-react';
import {
  LINE_STYLES,
  computeChannelStats,
  getValuesAtTimestamp,
  parseTs,
} from './MultiMachineTempChart';

function LineStylePreview({ style, width = 36 }) {
  return (
    <svg width={width} height="12" aria-hidden className="shrink-0">
      <line
        x1="0"
        y1="6"
        x2={width}
        y2="6"
        stroke={style.color}
        strokeWidth={style.borderWidth}
        strokeDasharray={style.borderDash.length ? style.borderDash.join(' ') : undefined}
      />
    </svg>
  );
}

function formatCursorTime(ts) {
  const d = parseTs(ts);
  const p = (n) => String(n).padStart(2, '0');
  return `${p(d.getDate())}/${p(d.getMonth() + 1)}/${d.getFullYear()} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

function formatCellValue(value) {
  return value != null && !Number.isNaN(value) ? value.toFixed(1) : '';
}

/** TSV untuk paste langsung ke Excel (#, Waktu, lalu 1 kolom per kanal). */
function buildAnalogTsv(cursors, selectedMachines, machineNames, multiData) {
  const headers = ['#', 'Waktu', ...selectedMachines.map((code) => machineNames[code] || code)];
  const rows = cursors.map((cur, ci) => {
    const readings = getValuesAtTimestamp(multiData, cur.timestamp, selectedMachines);
    const byCode = Object.fromEntries(readings.map((r) => [r.code, r.value]));
    return [
      `M${ci + 1}`,
      formatCursorTime(cur.timestamp),
      ...selectedMachines.map((code) => formatCellValue(byCode[code])),
    ];
  });
  return [headers, ...rows].map((row) => row.join('\t')).join('\n');
}

/**
 * Tabel kanal + Analog (measurement cursor) — gaya industrial.
 * Tab Analog: 1 kolom = 1 kanal, 1 baris = 1 titik ukur (mudah copy ke Excel).
 */
export default function ChartChannelsTable({
  selectedMachines,
  machineNames = {},
  machineUnits = {},
  multiData,
  hiddenChannels,
  onToggleChannel,
  scaleMin,
  scaleMax,
  cursors = [],
  onRemoveCursor,
  onClearCursors,
}) {
  const [activeTab, setActiveTab] = useState('channels');
  const [copied, setCopied] = useState(false);

  const handleCopyToExcel = useCallback(async () => {
    const tsv = buildAnalogTsv(cursors, selectedMachines, machineNames, multiData);
    try {
      await navigator.clipboard.writeText(tsv);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      // Fallback: textarea tersembunyi + execCommand
      const ta = document.createElement('textarea');
      ta.value = tsv;
      ta.setAttribute('readonly', '');
      ta.style.position = 'fixed';
      ta.style.left = '-9999px';
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      ta.remove();
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    }
  }, [cursors, selectedMachines, machineNames, multiData]);

  if (!selectedMachines.length) return null;

  const yMin = scaleMin !== '' && scaleMin != null ? parseFloat(scaleMin) : null;
  const yMax = scaleMax !== '' && scaleMax != null ? parseFloat(scaleMax) : null;

  return (
    <div className="border-t border-[#9ec5e8] bg-[#f0f7fc]">
      <div className="flex items-center border-b border-[#9ec5e8] bg-[#dceaf5]">
        <button
          type="button"
          onClick={() => setActiveTab('channels')}
          className={`px-3.5 py-1.5 text-sm font-semibold border-r border-[#9ec5e8] ${
            activeTab === 'channels' ? 'bg-white text-[#1e3a5f]' : 'text-[#5a7a9a] hover:bg-[#e8f2fa]'
          }`}
        >
          Channels
        </button>
        <button
          type="button"
          onClick={() => setActiveTab('analog')}
          className={`px-3.5 py-1.5 text-sm font-semibold border-r border-[#9ec5e8] ${
            activeTab === 'analog' ? 'bg-white text-[#1e3a5f]' : 'text-[#5a7a9a] hover:bg-[#e8f2fa]'
          }`}
        >
          Analog
          {cursors.length > 0 && (
            <span className="ml-1 px-1.5 py-0.5 rounded bg-red-100 text-red-700 text-xs">{cursors.length}</span>
          )}
        </button>
        {activeTab === 'analog' && cursors.length > 0 && (
          <div className="ml-auto mr-2 flex items-center gap-2">
            <button
              type="button"
              onClick={handleCopyToExcel}
              className={`text-xs font-medium flex items-center gap-1 px-2 py-0.5 rounded ${
                copied
                  ? 'text-green-700 bg-green-50'
                  : 'text-[#1e3a5f] hover:bg-white border border-[#9ec5e8] bg-white/70'
              }`}
              title="Salin tabel sebagai TSV untuk paste ke Excel"
            >
              {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
              {copied ? 'Disalin' : 'Salin ke Excel'}
            </button>
            <button
              type="button"
              onClick={onClearCursors}
              className="text-xs text-red-600 hover:underline flex items-center gap-0.5"
            >
              <X className="w-3.5 h-3.5" />
              Reset kursor
            </button>
          </div>
        )}
      </div>

      {activeTab === 'channels' && (
        <div className="overflow-x-auto max-h-52 overflow-y-auto">
          <table className="w-full text-sm border-collapse">
            <thead className="sticky top-0 bg-[#e8f2fa] z-10">
              <tr className="text-[#1e3a5f] border-b border-[#9ec5e8]">
                <th className="w-9 px-1.5 py-1.5 font-semibold text-center border-r border-[#c5dced]"> </th>
                <th className="w-14 px-1.5 py-1.5 font-semibold border-r border-[#c5dced]">Garis</th>
                <th className="px-2.5 py-1.5 font-semibold text-right border-r border-[#c5dced] whitespace-nowrap">Min</th>
                <th className="px-2.5 py-1.5 font-semibold text-right border-r border-[#c5dced] whitespace-nowrap">Max</th>
                <th className="px-2.5 py-1.5 font-semibold text-right border-r border-[#c5dced] whitespace-nowrap">Nilai</th>
                <th className="px-2.5 py-1.5 font-semibold text-center border-r border-[#c5dced] w-16">Satuan</th>
                <th className="px-2.5 py-1.5 font-semibold text-left">Kanal</th>
              </tr>
            </thead>
            <tbody>
              {selectedMachines.map((code, idx) => {
                const style = LINE_STYLES[idx % LINE_STYLES.length];
                const visible = !hiddenChannels.includes(code);
                const stats = computeChannelStats(multiData, code);
                const unit = machineUnits[code] || multiData?.meta?.[code]?.unit || '—';
                const name = machineNames[code] || code;
                const displayMin = yMin != null && !Number.isNaN(yMin) ? yMin : stats.min;
                const displayMax = yMax != null && !Number.isNaN(yMax) ? yMax : stats.max;

                return (
                  <tr
                    key={code}
                    className={`border-b border-[#d4e8f7] hover:bg-[#e8f4fc] ${visible ? '' : 'opacity-45'}`}
                  >
                    <td className="px-1.5 py-1 text-center border-r border-[#d4e8f7]">
                      <input
                        type="checkbox"
                        checked={visible}
                        onChange={() => onToggleChannel(code)}
                        className="rounded border-[#9ec5e8] w-4 h-4"
                      />
                    </td>
                    <td className="px-1.5 py-1 border-r border-[#d4e8f7]">
                      <LineStylePreview style={style} width={44} />
                    </td>
                    <td className="px-2.5 py-1 text-right font-mono text-[#1e3a5f] border-r border-[#d4e8f7]">
                      {displayMin != null ? displayMin.toFixed(1) : '—'}
                    </td>
                    <td className="px-2.5 py-1 text-right font-mono text-[#1e3a5f] border-r border-[#d4e8f7]">
                      {displayMax != null ? displayMax.toFixed(1) : '—'}
                    </td>
                    <td className="px-2.5 py-1 text-right font-mono font-semibold text-[#1e3a5f] border-r border-[#d4e8f7]">
                      {stats.current != null ? stats.current.toFixed(1) : '—'}
                    </td>
                    <td className="px-2.5 py-1 text-center text-[#5a7a9a] border-r border-[#d4e8f7]">{unit}</td>
                    <td className="px-2.5 py-1 text-left text-[#1e3a5f] font-medium truncate max-w-[14rem]" title={name}>
                      {name}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {activeTab === 'analog' && (
        <div className="overflow-x-auto max-h-60 overflow-y-auto">
          {cursors.length === 0 ? (
            <p className="px-3 py-5 text-sm text-[#5a7a9a] text-center">
              Aktifkan <strong>Measurement Cursor</strong>, lalu klik pada grafik untuk menaruh titik ukur.
            </p>
          ) : (
            <table className="w-full text-sm border-collapse select-text">
              <thead className="sticky top-0 bg-[#e8f2fa] z-10">
                <tr className="text-[#1e3a5f] border-b border-[#9ec5e8]">
                  <th className="px-2.5 py-1.5 font-semibold text-left border-r border-[#c5dced] w-12 whitespace-nowrap">#</th>
                  <th className="px-2.5 py-1.5 font-semibold text-left border-r border-[#c5dced] whitespace-nowrap">Waktu</th>
                  {selectedMachines.map((code, idx) => {
                    const style = LINE_STYLES[idx % LINE_STYLES.length];
                    const name = machineNames[code] || code;
                    return (
                      <th
                        key={code}
                        className="px-2.5 py-1.5 font-semibold text-right border-r border-[#c5dced] whitespace-nowrap min-w-[5.5rem]"
                        title={name}
                      >
                        <div className="flex flex-col items-end gap-0.5">
                          <LineStylePreview style={style} width={28} />
                          <span className="truncate max-w-[9rem]">{name}</span>
                        </div>
                      </th>
                    );
                  })}
                  <th className="w-10 px-1.5 py-1.5 print:hidden" />
                </tr>
              </thead>
              <tbody>
                {cursors.map((cur, ci) => {
                  const readings = getValuesAtTimestamp(multiData, cur.timestamp, selectedMachines);
                  const byCode = Object.fromEntries(readings.map((r) => [r.code, r.value]));
                  return (
                    <tr key={cur.id} className="border-b border-[#d4e8f7] hover:bg-[#e8f4fc]">
                      <td className="px-2.5 py-1 font-bold text-red-700 border-r border-[#d4e8f7] whitespace-nowrap">
                        M{ci + 1}
                      </td>
                      <td className="px-2.5 py-1 font-mono text-[#1e3a5f] border-r border-[#d4e8f7] whitespace-nowrap">
                        {formatCursorTime(cur.timestamp)}
                      </td>
                      {selectedMachines.map((code) => {
                        const val = byCode[code];
                        return (
                          <td
                            key={code}
                            className="px-2.5 py-1 text-right font-mono font-semibold text-[#1e3a5f] border-r border-[#d4e8f7] whitespace-nowrap"
                          >
                            {val != null && !Number.isNaN(val) ? val.toFixed(1) : '—'}
                          </td>
                        );
                      })}
                      <td className="px-1.5 py-1 text-center print:hidden">
                        <button
                          type="button"
                          onClick={() => onRemoveCursor(cur.id)}
                          className="p-0.5 text-red-500 hover:bg-red-50 rounded"
                          title="Hapus kursor"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
