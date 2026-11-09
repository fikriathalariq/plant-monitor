import React from 'react';

export const HALF_HOURS = 48;
export const SHIFT_MINUTES = 24 * 60;

/**
 * Grid vertikal 30-menit untuk timeline shift 24 jam.
 */
export function TimeGrid({ progressPct, overlay = false, showNow = true }) {
  return (
    <div className={`absolute inset-0 pointer-events-none ${overlay ? 'z-20' : 'z-0'}`} aria-hidden>
      {Array.from({ length: HALF_HOURS + 1 }, (_, i) => {
        const isHour = i % 2 === 0;
        const left = `${(i / HALF_HOURS) * 100}%`;
        if (overlay) {
          return (
            <div
              key={i}
              className={`absolute top-0 bottom-0 ${isHour ? 'w-[1.5px] bg-slate-900/45' : 'w-px bg-slate-900/18'}`}
              style={{ left }}
            />
          );
        }
        return (
          <div
            key={i}
            className={`absolute top-0 bottom-0 ${isHour ? 'border-l border-slate-400/55' : 'border-l border-slate-300/40'}`}
            style={{ left }}
          />
        );
      })}
      {showNow && progressPct < 100 && (
        <div
          className={`absolute top-0 bottom-0 ${overlay ? 'z-30' : 'z-10'} w-[2px] bg-cyan-400 shadow-[0_0_6px_rgba(34,211,238,0.55)] print:hidden`}
          style={{ left: `${progressPct}%` }}
        />
      )}
    </div>
  );
}

export function TimeAxis({ timeLabels, progressPct }) {
  return (
    <div className="relative h-8 w-full min-w-0 bg-slate-800 border-b border-slate-600 box-border">
      <TimeGrid progressPct={progressPct} showNow={false} />
      {(timeLabels || []).map((t, i) => (
        <span
          key={i}
          className="absolute bottom-1 -translate-x-1/2 text-[10px] sm:text-[11px] font-medium text-cyan-100/90 tabular-nums z-10"
          style={{ left: `${t.pct}%` }}
        >
          {t.label}
        </span>
      ))}
      {progressPct < 100 && (
        <div className="absolute top-0 bottom-0 z-20 w-[2px] bg-cyan-400 print:hidden" style={{ left: `${progressPct}%` }} />
      )}
    </div>
  );
}

export default { TimeGrid, TimeAxis, HALF_HOURS, SHIFT_MINUTES };
