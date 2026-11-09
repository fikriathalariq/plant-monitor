import React, { useRef, useEffect, useMemo } from 'react';
import { TimeGrid, SHIFT_MINUTES } from './TimeGridAxis';

export const STEAM_PRESSURE_SCALE = {
  min: 0,
  max: 6,
  criticalLow: 3.0,
};

export function pressureBarColor(value) {
  if (value == null || Number.isNaN(value)) return null;
  if (value < 3) return '#ef4444';
  if (value < 4.5) return '#f59e0b';
  return '#10b981';
}

export function pressureTextClass(value) {
  if (value == null || Number.isNaN(value)) return 'text-gray-400';
  if (value < 3) return 'text-red-400';
  if (value < 4.5) return 'text-amber-400';
  if (value <= 6) return 'text-emerald-400';
  return 'text-purple-400';
}

/**
 * Mini chart tekanan uap (barg) 0–6, canvas per-menit + grid overlay.
 */
export function SteamPressureRow({ pressure, progressPct = 100 }) {
  const canvasRef = useRef(null);
  const values = pressure?.values || [];
  const scaleMax = pressure?.scale_max ?? STEAM_PRESSURE_SCALE.max;
  const scaleMin = pressure?.scale_min ?? STEAM_PRESSURE_SCALE.min;
  const criticalLow = pressure?.critical_low ?? STEAM_PRESSURE_SCALE.criticalLow;
  const range = scaleMax - scaleMin || 1;

  const gridLines = useMemo(() => {
    const marks = [0, 2, 4, 6].filter((v) => v >= scaleMin && v <= scaleMax);
    return marks.map((v) => ({
      value: v,
      // Y dari atas: 6 barg di atas, 0 di bawah
      topPct: ((scaleMax - v) / range) * 100,
      critical: false,
    })).concat([{
      value: criticalLow,
      topPct: ((scaleMax - criticalLow) / range) * 100,
      critical: true,
    }]);
  }, [scaleMin, scaleMax, criticalLow, range]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const W = SHIFT_MINUTES;
    const H = 28;
    canvas.width = W;
    canvas.height = H;

    ctx.fillStyle = '#fafafa';
    ctx.fillRect(0, 0, W, H);

    for (let i = 0; i < SHIFT_MINUTES; i += 1) {
      const isFuture = progressPct < 100 && i >= values.length;
      if (isFuture) {
        ctx.fillStyle = '#e5e7eb';
        ctx.fillRect(i, 0, 1, H);
        continue;
      }
      const v = i < values.length ? values[i] : null;
      if (v == null || Number.isNaN(v)) continue;
      const clamped = Math.max(scaleMin, Math.min(scaleMax, Number(v)));
      const barH = Math.max(1, Math.round(((clamped - scaleMin) / range) * H));
      ctx.fillStyle = pressureBarColor(clamped) || '#94a3b8';
      ctx.fillRect(i, H - barH, 1, barH);
    }
  }, [values, progressPct, scaleMin, scaleMax, range]);

  return (
    <div
      className="relative h-7 w-full min-w-0 bg-[#fafafa] border-b border-gray-200 box-border print:h-5 steam-pressure-cell"
      title="Tekanan uap (barg), skala 0–6"
    >
      <canvas
        ref={canvasRef}
        className="absolute inset-0 w-full h-full"
        style={{ imageRendering: 'pixelated' }}
      />
      {/* Grid horizontal 0/2/4/6 + garis kritis 3 barg */}
      <div className="absolute inset-0 pointer-events-none z-[1]" aria-hidden>
        {gridLines.map((g) => (
          <div
            key={`${g.value}-${g.critical ? 'c' : 'n'}`}
            className="absolute left-0 right-0"
            style={{
              top: `${g.topPct}%`,
              borderTop: g.critical
                ? '1px dashed rgba(239,68,68,0.35)'
                : '1px solid rgba(0,0,0,0.08)',
            }}
          />
        ))}
      </div>
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

export default SteamPressureRow;
