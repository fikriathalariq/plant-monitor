import React, { useMemo } from 'react';
import { PHASE_COLORS } from '../lib/phaseColors';
import { SHIFT_MINUTES } from './TimeGridAxis';
import { pressureTextClass } from './SteamPressureRow';

const STATE_ITEMS = [
  { key: 'HEAT', label: 'Heat', colorKey: 'HEAT' },
  { key: 'STEADY', label: 'Keep', colorKey: 'STEADY' },
  { key: 'COOL', label: 'Cool', colorKey: 'COOL' },
  { key: 'RUNNING', label: 'Run', colorKey: 'RUNNING' },
  { key: 'other', label: 'Lain', colorKey: 'OFF' },
];

export function getStateAtBucket(segments, bucketIndex) {
  if (!segments?.length) return 'OFF';
  const pct = (bucketIndex / SHIFT_MINUTES) * 100;
  for (const seg of segments) {
    const start = seg.start_pct ?? 0;
    const end = start + (seg.width_pct ?? 0);
    if (pct >= start && pct < end) return seg.state || 'OFF';
  }
  return 'OFF';
}

export function computeHoverStats(data, pct) {
  if (!data || pct == null) return null;
  const bucketIndex = Math.min(
    SHIFT_MINUTES - 1,
    Math.max(0, Math.floor((pct / 100) * SHIFT_MINUTES)),
  );

  const counts = { HEAT: 0, STEADY: 0, COOL: 0, RUNNING: 0, other: 0 };
  for (const group of data.groups || []) {
    for (const machine of group.machines || []) {
      const state = getStateAtBucket(machine.segments, bucketIndex);
      if (state === 'HEAT') counts.HEAT += 1;
      else if (state === 'STEADY') counts.STEADY += 1;
      else if (state === 'COOL') counts.COOL += 1;
      else if (state === 'RUNNING') counts.RUNNING += 1;
      else counts.other += 1;
    }
  }

  const steamVals = data.steam_heatmap?.values || [];
  const pressVals = data.steam_pressure?.values || [];
  const steam = bucketIndex < steamVals.length ? steamVals[bucketIndex] : null;
  const pressure = bucketIndex < pressVals.length ? pressVals[bucketIndex] : null;

  return { bucketIndex, counts, steam, pressure };
}

/**
 * Tooltip minimalis di dekat crosshair.
 * props.stats dari computeHoverStats; position = { left, top, flipX, flipY }
 */
export function CrosshairPanel({
  timeLabel,
  stats,
  left,
  top,
  flipX = false,
  flipY = false,
}) {
  const visibleStates = useMemo(() => {
    if (!stats?.counts) return [];
    return STATE_ITEMS.filter((item) => (stats.counts[item.key] || 0) > 0);
  }, [stats]);

  if (!stats || !timeLabel) return null;

  const steamLabel = stats.steam != null && !Number.isNaN(stats.steam)
    ? `${Math.round(stats.steam).toLocaleString('id-ID')} kg/h`
    : '—';
  const pressLabel = stats.pressure != null && !Number.isNaN(stats.pressure)
    ? `${Number(stats.pressure).toFixed(1)} barg`
    : '—';
  const pressClass = pressureTextClass(stats.pressure);

  return (
    <div
      className="pointer-events-none absolute z-50 print:hidden"
      style={{
        left,
        top,
        transform: `translate(${flipX ? '-100%' : '8px'}, ${flipY ? '8px' : 'calc(-100% - 8px)'})`,
      }}
    >
      <div className="bg-gray-900/95 text-white rounded-md shadow-lg px-2.5 py-2 min-w-[7.5rem] max-w-[11rem]">
        <p className="text-xs font-bold tabular-nums leading-none mb-1.5">{timeLabel}</p>
        <div className="border-t border-white/10 mb-1.5" />

        {visibleStates.length > 0 && (
          <>
            <div className="flex items-end gap-2.5 mb-0.5">
              {visibleStates.map((item) => {
                const hex = PHASE_COLORS[item.colorKey]?.hex || '#94a3b8';
                return (
                  <div key={item.key} className="flex flex-col items-center gap-0.5">
                    <div className="flex items-center gap-0.5">
                      <span
                        className="inline-block w-1.5 h-1.5 rounded-full shrink-0"
                        style={{ backgroundColor: hex }}
                      />
                      <span className="text-xs font-semibold tabular-nums leading-none">
                        {stats.counts[item.key]}
                      </span>
                    </div>
                    <span className="text-[8px] text-gray-400 leading-none">{item.label}</span>
                  </div>
                );
              })}
            </div>
            <div className="border-t border-white/10 my-1.5" />
          </>
        )}

        <div className="flex justify-between items-baseline gap-3 text-[11px] leading-snug">
          <span className="text-gray-400">Uap</span>
          <span className="font-medium tabular-nums text-white">{steamLabel}</span>
        </div>
        <div className="flex justify-between items-baseline gap-3 text-[11px] leading-snug mt-0.5">
          <span className="text-gray-400">Tekanan</span>
          <span className={`font-medium tabular-nums ${pressClass}`}>{pressLabel}</span>
        </div>
      </div>
    </div>
  );
}

export default CrosshairPanel;
