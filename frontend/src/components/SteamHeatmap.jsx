import React, { useRef, useEffect } from 'react';
import { TimeGrid, SHIFT_MINUTES } from './TimeGridAxis';

/** Skala warna tetap pemakaian uap (kg/h) */
export const STEAM_HEAT_SCALE = [
  { value: 0, color: [255, 255, 255] },
  { value: 3000, color: [186, 230, 253] },
  { value: 4000, color: [37, 99, 235] },
  { value: 5000, color: [34, 197, 94] },
  { value: 6000, color: [234, 179, 8] },
  { value: 7000, color: [239, 68, 68] },
  { value: 8000, color: [0, 0, 0] },
];

function lerpColor(c1, c2, t) {
  const r = Math.round(c1[0] + (c2[0] - c1[0]) * t);
  const g = Math.round(c1[1] + (c2[1] - c1[1]) * t);
  const b = Math.round(c1[2] + (c2[2] - c1[2]) * t);
  return `rgb(${r} ${g} ${b})`;
}

export function steamHeatColor(value) {
  const v = Math.max(0, value || 0);
  if (v >= STEAM_HEAT_SCALE[STEAM_HEAT_SCALE.length - 1].value) {
    const c = STEAM_HEAT_SCALE[STEAM_HEAT_SCALE.length - 1].color;
    return `rgb(${c[0]} ${c[1]} ${c[2]})`;
  }
  for (let i = 0; i < STEAM_HEAT_SCALE.length - 1; i += 1) {
    const lo = STEAM_HEAT_SCALE[i];
    const hi = STEAM_HEAT_SCALE[i + 1];
    if (v >= lo.value && v < hi.value) {
      const t = (v - lo.value) / (hi.value - lo.value);
      return lerpColor(lo.color, hi.color, t);
    }
  }
  return 'rgb(255 255 255)';
}

export const STEAM_HEAT_LEGEND = [
  { label: '0', color: '#ffffff', border: true },
  { label: '3k', color: '#bae6fd' },
  { label: '4k', color: '#2563eb' },
  { label: '5k', color: '#22c55e' },
  { label: '6k', color: '#eab308' },
  { label: '7k', color: '#ef4444' },
  { label: '8k+', color: '#000000' },
];

export function SteamHeatmap({ heatmap, progressPct = 100 }) {
  const canvasRef = useRef(null);
  const values = heatmap?.values || [];

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const W = SHIFT_MINUTES;
    const H = 1;
    canvas.width = W;
    canvas.height = H;

    for (let i = 0; i < SHIFT_MINUTES; i++) {
      const isFuture = progressPct < 100 && i >= values.length;
      const v = (!isFuture && values[i] !== undefined) ? values[i] : 0;

      if (isFuture) {
        ctx.fillStyle = '#f1f5f9';
      } else if (v === 0) {
        ctx.fillStyle = '#e0e0e0';
      } else {
        ctx.fillStyle = steamHeatColor(v);
      }
      ctx.fillRect(i, 0, 1, H);
    }
  }, [values, progressPct]);

  return (
    <div
      className="relative h-6 w-full min-w-0 bg-slate-100 border-b border-gray-200 box-border print:h-5 steam-cell"
      title="Pemakaian uap agregat (skala tetap kg/h)"
    >
      <canvas
        ref={canvasRef}
        className="absolute inset-0 w-full h-full"
        style={{ imageRendering: 'pixelated' }}
      />
      <TimeGrid progressPct={progressPct} overlay showNow={false} />
      {progressPct < 100 && (
        <div
          className="absolute top-0 bottom-0 z-20 w-[2px] bg-cyan-400 print:hidden"
          style={{ left: `${progressPct}%` }}
        />
      )}
    </div>
  );
}

export default SteamHeatmap;
