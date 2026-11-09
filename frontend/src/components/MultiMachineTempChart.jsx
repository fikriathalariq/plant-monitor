import React, { useMemo, useRef, useImperativeHandle, forwardRef, useEffect, useState, useCallback } from 'react';
import {
  Chart as ChartJS,
  LinearScale,
  TimeScale,
  PointElement,
  LineElement,
  Tooltip,
  Legend,
} from 'chart.js';
import zoomPlugin from 'chartjs-plugin-zoom';
import 'chartjs-adapter-date-fns';
import { Line } from 'react-chartjs-2';

ChartJS.register(
  LinearScale,
  TimeScale,
  PointElement,
  LineElement,
  Tooltip,
  Legend,
  zoomPlugin,
);

/** Gaya garis B&W — dibedakan pola dash & ketebalan (cocok cetak hitam-putih) */
export const LINE_STYLES = [
  { color: '#000000', borderDash: [], borderWidth: 2.5, pointStyle: 'circle' },
  { color: '#1e293b', borderDash: [8, 4], borderWidth: 2.5, pointStyle: 'rect' },
  { color: '#334155', borderDash: [2, 3], borderWidth: 2, pointStyle: 'triangle' },
  { color: '#475569', borderDash: [10, 3, 2, 3], borderWidth: 2.5, pointStyle: 'rectRot' },
  { color: '#64748b', borderDash: [15, 5], borderWidth: 2, pointStyle: 'star' },
  { color: '#0f172a', borderDash: [5, 5, 1, 5], borderWidth: 3, pointStyle: 'crossRot' },
  { color: '#525252', borderDash: [1, 2], borderWidth: 2, pointStyle: 'circle' },
  { color: '#171717', borderDash: [12, 3, 3, 3], borderWidth: 2, pointStyle: 'rect' },
];

export function parseTs(ts) {
  const [date, time] = ts.split(' ');
  const [y, m, d] = date.split('-').map(Number);
  const [hh, mm] = time.split(':').map(Number);
  return new Date(y, m - 1, d, hh, mm);
}

function parseNum(str) {
  if (str === '' || str === null || str === undefined) return undefined;
  const n = parseFloat(str);
  return Number.isNaN(n) ? undefined : n;
}

const MAJOR_TICK_COUNT = 6;
const PRIMARY_Y_DEFAULT_MIN = 0;
const PRIMARY_Y_DEFAULT_MAX = 150;
const NICE_FACTORS = [1, 2, 2.5, 5, 10];

/** Step "bagus" untuk label sumbu industrial (1, 2, 2.5, 5, 10, …) */
function niceStep(roughStep) {
  if (!roughStep || roughStep <= 0 || !Number.isFinite(roughStep)) return 1;
  const exp = Math.floor(Math.log10(roughStep));
  const magnitude = 10 ** exp;
  const f = roughStep / magnitude;
  for (const nf of NICE_FACTORS) {
    if (f <= nf + 1e-9) return nf * magnitude;
  }
  return 10 * magnitude;
}

/** Naikkan ke kandidat nice-step berikutnya (untuk memperluas rentang auto). */
function nextNiceStep(step) {
  if (!step || step <= 0 || !Number.isFinite(step)) return 1;
  const exp = Math.floor(Math.log10(step));
  const magnitude = 10 ** exp;
  const f = step / magnitude;
  for (const nf of NICE_FACTORS) {
    if (nf > f + 1e-9) return nf * magnitude;
  }
  return 10 * magnitude;
}

function formatTickValue(value) {
  if (!Number.isFinite(value)) return '';
  const rounded = Math.round(value * 1000) / 1000;
  if (Math.abs(rounded - Math.round(rounded)) < 1e-6) return String(Math.round(rounded));
  // Angka "cantik" setengah: 2.5, 7.5, …
  if (Math.abs(rounded * 2 - Math.round(rounded * 2)) < 1e-6) {
    return (Math.round(rounded * 2) / 2).toFixed(1);
  }
  if (Math.abs(rounded) < 10) return rounded.toFixed(2).replace(/\.?0+$/, '');
  return rounded.toFixed(1);
}

/**
 * Hitung min/max/step dengan jumlah tick mayor tetap —
 * span selalu = (tickCount-1) * step agar grid Y kiri & kanan sejajar.
 */
function computeAxisBounds(dataValues, userMin, userMax, tickCount = MAJOR_TICK_COUNT) {
  const intervals = tickCount - 1;
  let dMin = dataValues.length ? Math.min(...dataValues) : 0;
  let dMax = dataValues.length ? Math.max(...dataValues) : 100;
  if (!Number.isFinite(dMin) || !Number.isFinite(dMax)) {
    dMin = 0;
    dMax = 100;
  }
  if (dMin === dMax) {
    dMin -= 1;
    dMax += 1;
  }

  // Min & max terkunci: bagi rentang rata persis (0–150 → step 30, tick 0/30/…/150).
  // Jangan niceStep-kan step-nya — itu yang bikin 30 jadi 50 dan tick tidak genap.
  if (userMin != null && userMax != null && userMax > userMin) {
    const step = (userMax - userMin) / intervals;
    return { min: userMin, max: userMax, step, tickCount };
  }

  const rawMin = userMin ?? dMin;
  const rawMax = userMax ?? dMax;
  const rawSpan = Math.max(rawMax - rawMin, Number.EPSILON);
  let step = niceStep(rawSpan / intervals);

  if (userMin != null) {
    const min = userMin;
    let max = min + intervals * step;
    while (max < rawMax - 1e-9) {
      step = nextNiceStep(step);
      max = min + intervals * step;
    }
    return { min, max, step, tickCount };
  }

  if (userMax != null) {
    const max = userMax;
    let min = max - intervals * step;
    while (min > rawMin + 1e-9) {
      step = nextNiceStep(step);
      min = max - intervals * step;
    }
    return { min, max, step, tickCount };
  }

  // Fully auto: min/max nice, span tepat intervals * step (sejajar dengan sumbu lain).
  let min = Math.floor(rawMin / step) * step;
  if (Object.is(min, -0)) min = 0;
  let max = min + intervals * step;
  let guard = 0;
  while (max < rawMax - 1e-9 && guard < 40) {
    step = nextNiceStep(step);
    min = Math.floor(rawMin / step) * step;
    if (Object.is(min, -0)) min = 0;
    max = min + intervals * step;
    guard += 1;
  }

  return { min, max, step, tickCount };
}

function collectAxisValues(datasets, axisId) {
  const values = [];
  datasets.forEach((ds) => {
    if (ds.yAxisID !== axisId) return;
    ds.data.forEach((p) => {
      if (p.y != null && !Number.isNaN(p.y)) values.push(p.y);
    });
  });
  return values;
}

function buildAlignedLinearScale(bounds, opts) {
  const { position, title, drawGrid, tickColor } = opts;
  return {
    type: 'linear',
    position,
    min: bounds.min,
    max: bounds.max,
    title: title ? { display: true, text: title, color: '#1e3a5f', font: { size: 12, weight: '600' } } : undefined,
    grid: drawGrid
      ? { color: '#9ec5e8', lineWidth: 1, drawOnChartArea: true }
      : { drawOnChartArea: false },
    border: { display: true, color: '#6ba3cc', width: 1.5 },
    ticks: {
      color: tickColor || '#1e3a5f',
      font: { size: 11 },
      autoSkip: false,
      maxTicksLimit: bounds.tickCount,
      callback: (value) => formatTickValue(value),
    },
    afterBuildTicks(axis) {
      const intervals = bounds.tickCount - 1;
      const span = bounds.max - bounds.min;
      const ticks = [];
      for (let i = 0; i < bounds.tickCount; i++) {
        // Fraksi i/intervals — sama di Y kiri & kanan → grid sejajar.
        ticks.push({ value: bounds.min + (span * i) / intervals });
      }
      axis.ticks = ticks;
    },
  };
}

function pad(n) {
  return String(n).padStart(2, '0');
}

export function snapToNearestTimestamp(clickDate, timestamps) {
  if (!timestamps?.length || !clickDate) return null;
  const t = clickDate.getTime();
  let best = timestamps[0];
  let bestDiff = Infinity;
  timestamps.forEach((ts) => {
    const diff = Math.abs(parseTs(ts).getTime() - t);
    if (diff < bestDiff) {
      bestDiff = diff;
      best = ts;
    }
  });
  return best;
}

export function getValuesAtTimestamp(multiData, ts, codes) {
  const row = multiData?.table?.[ts] || {};
  return codes.map((code) => ({
    code,
    value: row[code]?.temp ?? null,
    unit: multiData?.meta?.[code]?.unit || '',
  }));
}

const Y_MINOR_DIVISIONS = 5;
const X_MINOR_DIVISIONS = 5;
const MINOR_GRID_COLOR = '#b7d0e6';
const MINOR_TICK_COLOR = '#6ba3cc';
const MAJOR_TICK_COLOR = '#1e3a5f';
/** Warna kisi minor untuk cetak — lebih gelap agar tetap terbaca di kertas A4. */
const MINOR_GRID_COLOR_PRINT = '#7a9bb8';
const MINOR_TICK_COLOR_PRINT = '#4a7aa0';

/**
 * Garis minor + tick mark (graduation) di sumbu Y kiri, Y kanan, dan X —
 * membantu baca nilai antar-tick mayor saat analisis / cetak.
 * Opsi via chart.options.plugins.minorGrid:
 *   pixelScale, printMode, gridColor, tickColor
 */
const minorGridPlugin = {
  id: 'minorGrid',
  beforeDraw(chart) {
    const { ctx, chartArea, scales } = chart;
    if (!chartArea) return;

    const cfg = chart.options.plugins?.minorGrid || {};
    const scale = Math.max(1, cfg.pixelScale || 1);
    const printMode = !!cfg.printMode;
    const gridColor = cfg.gridColor || (printMode ? MINOR_GRID_COLOR_PRINT : MINOR_GRID_COLOR);
    const tickColor = cfg.tickColor || (printMode ? MINOR_TICK_COLOR_PRINT : MINOR_TICK_COLOR);
    const majorTickColor = cfg.majorTickColor || MAJOR_TICK_COLOR;
    // Cetak: garis lebih tebal & gelap; layar: tipis seperti sekarang.
    const minorGridWidth = (printMode ? 1.1 : 0.7) * scale;
    const minorTickWidth = (printMode ? 1.25 : 1) * scale;
    const majorTickWidth = (printMode ? 1.6 : 1.25) * scale;
    const dash = printMode
      ? [Math.round(4 * scale), Math.round(3 * scale)]
      : [Math.round(3 * scale), Math.round(2 * scale)];
    const minorLen = Math.round(4 * scale);
    const majorLen = Math.round(7 * scale);

    const drawHGrid = (yAxis, divisions) => {
      if (!yAxis?.ticks || yAxis.ticks.length < 2) return;
      ctx.strokeStyle = gridColor;
      ctx.lineWidth = minorGridWidth;
      ctx.setLineDash(dash);
      for (let i = 0; i < yAxis.ticks.length - 1; i++) {
        const v0 = yAxis.ticks[i].value;
        const v1 = yAxis.ticks[i + 1].value;
        const step = (v1 - v0) / divisions;
        for (let j = 1; j < divisions; j++) {
          const yPos = yAxis.getPixelForValue(v0 + step * j);
          if (yPos < chartArea.top || yPos > chartArea.bottom) continue;
          ctx.beginPath();
          ctx.moveTo(chartArea.left, yPos);
          ctx.lineTo(chartArea.right, yPos);
          ctx.stroke();
        }
      }
    };

    const drawVGrid = (xAxis, divisions) => {
      if (!xAxis?.ticks || xAxis.ticks.length < 2) return;
      ctx.strokeStyle = gridColor;
      ctx.lineWidth = minorGridWidth;
      ctx.setLineDash(dash);
      for (let i = 0; i < xAxis.ticks.length - 1; i++) {
        const t0 = xAxis.ticks[i].value;
        const t1 = xAxis.ticks[i + 1].value;
        const step = (t1 - t0) / divisions;
        for (let j = 1; j < divisions; j++) {
          const xPos = xAxis.getPixelForValue(t0 + step * j);
          if (xPos < chartArea.left || xPos > chartArea.right) continue;
          ctx.beginPath();
          ctx.moveTo(xPos, chartArea.top);
          ctx.lineTo(xPos, chartArea.bottom);
          ctx.stroke();
        }
      }
    };

    /** Tick pendek di tepi sumbu — mayor lebih panjang dari minor. */
    const drawYTicks = (yAxis, side, divisions) => {
      if (!yAxis?.ticks || yAxis.ticks.length < 2) return;
      const atLeft = side === 'left';
      const edge = atLeft ? chartArea.left : chartArea.right;
      const dir = atLeft ? -1 : 1;

      ctx.setLineDash([]);
      ctx.lineCap = 'butt';

      ctx.strokeStyle = tickColor;
      ctx.lineWidth = minorTickWidth;
      for (let i = 0; i < yAxis.ticks.length - 1; i++) {
        const v0 = yAxis.ticks[i].value;
        const v1 = yAxis.ticks[i + 1].value;
        const step = (v1 - v0) / divisions;
        for (let j = 1; j < divisions; j++) {
          const yPos = yAxis.getPixelForValue(v0 + step * j);
          if (yPos < chartArea.top || yPos > chartArea.bottom) continue;
          ctx.beginPath();
          ctx.moveTo(edge, yPos);
          ctx.lineTo(edge + dir * minorLen, yPos);
          ctx.stroke();
        }
      }

      ctx.strokeStyle = majorTickColor;
      ctx.lineWidth = majorTickWidth;
      yAxis.ticks.forEach((t) => {
        const yPos = yAxis.getPixelForValue(t.value);
        if (yPos < chartArea.top - 0.5 || yPos > chartArea.bottom + 0.5) return;
        ctx.beginPath();
        ctx.moveTo(edge, yPos);
        ctx.lineTo(edge + dir * majorLen, yPos);
        ctx.stroke();
      });
    };

    const drawXTicks = (xAxis, divisions) => {
      if (!xAxis?.ticks || xAxis.ticks.length < 2) return;
      const edge = chartArea.bottom;

      ctx.setLineDash([]);
      ctx.lineCap = 'butt';

      ctx.strokeStyle = tickColor;
      ctx.lineWidth = minorTickWidth;
      for (let i = 0; i < xAxis.ticks.length - 1; i++) {
        const t0 = xAxis.ticks[i].value;
        const t1 = xAxis.ticks[i + 1].value;
        const step = (t1 - t0) / divisions;
        for (let j = 1; j < divisions; j++) {
          const xPos = xAxis.getPixelForValue(t0 + step * j);
          if (xPos < chartArea.left || xPos > chartArea.right) continue;
          ctx.beginPath();
          ctx.moveTo(xPos, edge);
          ctx.lineTo(xPos, edge + minorLen);
          ctx.stroke();
        }
      }

      ctx.strokeStyle = majorTickColor;
      ctx.lineWidth = majorTickWidth;
      xAxis.ticks.forEach((t) => {
        const xPos = xAxis.getPixelForValue(t.value);
        if (xPos < chartArea.left - 0.5 || xPos > chartArea.right + 0.5) return;
        ctx.beginPath();
        ctx.moveTo(xPos, edge);
        ctx.lineTo(xPos, edge + majorLen);
        ctx.stroke();
      });
    };

    ctx.save();

    drawHGrid(scales.y, Y_MINOR_DIVISIONS);
    drawVGrid(scales.x, X_MINOR_DIVISIONS);

    drawYTicks(scales.y, 'left', Y_MINOR_DIVISIONS);
    if (scales.y1) drawYTicks(scales.y1, 'right', Y_MINOR_DIVISIONS);
    drawXTicks(scales.x, X_MINOR_DIVISIONS);

    ctx.restore();
  },
};

const measurementCursorPlugin = {
  id: 'measurementCursors',
  afterDatasetsDraw(chart) {
    const cfg = chart.options.plugins?.measurementCursors;
    if (!cfg?.cursors?.length) return;
    const { ctx, chartArea, scales } = chart;
    const xScale = scales.x;
    if (!xScale || !chartArea) return;

    ctx.save();
    cfg.cursors.forEach((cur, i) => {
      const x = xScale.getPixelForValue(parseTs(cur.timestamp));
      if (x < chartArea.left || x > chartArea.right) return;

      ctx.strokeStyle = '#b91c1c';
      ctx.lineWidth = 1.25;
      ctx.setLineDash([5, 4]);
      ctx.beginPath();
      ctx.moveTo(x, chartArea.top);
      ctx.lineTo(x, chartArea.bottom);
      ctx.stroke();

      ctx.setLineDash([]);
      ctx.fillStyle = '#b91c1c';
      ctx.font = 'bold 11px Consolas, monospace';
      ctx.fillText(`M${i + 1}`, x + 3, chartArea.top + 13);
    });
    ctx.restore();
  },
};

ChartJS.register(minorGridPlugin, measurementCursorPlugin);

const axisLayoutPlugin = {
  id: 'axisLayoutTracker',
  afterLayout(chart) {
    if (chart.$onLayoutChange && chart.chartArea) {
      chart.$onLayoutChange({
        left: chart.chartArea.left,
        top: chart.chartArea.top,
        right: chart.chartArea.right,
        bottom: chart.chartArea.bottom,
        width: chart.width,
        height: chart.height,
      });
    }
  },
};
ChartJS.register(axisLayoutPlugin);

function canvasPoint(chart, clientX, clientY) {
  const rect = chart.canvas.getBoundingClientRect();
  const sx = chart.width / rect.width;
  const sy = chart.height / rect.height;
  return {
    x: (clientX - rect.left) * sx,
    y: (clientY - rect.top) * sy,
  };
}

function scaleFont(font, factor) {
  if (!font) return font;
  return { ...font, size: Math.max(1, Math.round((font.size || 10) * factor)) };
}

function scaleNum(n, factor, fallback = 1) {
  const v = n == null ? fallback : n;
  return Math.max(1, Math.round(v * factor));
}

/**
 * Klon opsi chart untuk ekspor/print.
 * pixelScale  — skala semua elemen visual (font, garis, padding) agar proporsi sama di canvas besar.
 * fontBoost   — pengali tambahan khusus font (biar terbaca di kertas A4).
 */
function buildExportOptions(baseOptions, pixelScale, fontBoost = 1) {
  const fontScale = pixelScale * fontBoost;
  const basePlugins = baseOptions.plugins || {};
  const baseLegendLabels = basePlugins.legend?.labels || {};
  const basePad = baseOptions.layout?.padding || {};
  const cloned = {
    ...baseOptions,
    responsive: false,
    maintainAspectRatio: false,
    animation: false,
    devicePixelRatio: 1,
    layout: {
      padding: {
        left: scaleNum(basePad.left ?? 8, pixelScale),
        right: scaleNum(basePad.right ?? 18, pixelScale),
        top: scaleNum(basePad.top ?? 10, pixelScale),
        bottom: scaleNum(basePad.bottom ?? 4, pixelScale),
      },
    },
    plugins: {
      ...basePlugins,
      legend: {
        ...basePlugins.legend,
        labels: {
          ...baseLegendLabels,
          font: scaleFont(baseLegendLabels.font || { size: 12, weight: '600' }, fontScale),
          boxWidth: scaleNum(baseLegendLabels.boxWidth || 34, pixelScale),
          boxHeight: scaleNum(baseLegendLabels.boxHeight || 3, pixelScale),
          padding: scaleNum(baseLegendLabels.padding || 14, pixelScale),
        },
      },
      tooltip: { ...basePlugins.tooltip, enabled: false },
      // Matikan plugin interaktif yang tidak relevan untuk cetak
      zoom: undefined,
      measurementCursors: basePlugins.measurementCursors,
      // Skala + gelapkan kisi minor agar terbaca di kertas A4
      minorGrid: {
        pixelScale,
        printMode: true,
        gridColor: MINOR_GRID_COLOR_PRINT,
        tickColor: MINOR_TICK_COLOR_PRINT,
      },
    },
    scales: {},
  };
  Object.entries(baseOptions.scales || {}).forEach(([key, scale]) => {
    const tickFont = scale.ticks?.font || { size: key === 'x' ? 10 : 11 };
    const titleFont = scale.title?.font || { size: 12, weight: '600' };
    const baseGridWidth = scale.grid?.lineWidth != null ? scale.grid.lineWidth : 1;
    cloned.scales[key] = {
      ...scale,
      border: scale.border
        ? { ...scale.border, width: scaleNum(scale.border.width || 1.5, pixelScale) }
        : scale.border,
      grid: scale.grid
        ? {
          ...scale.grid,
          // Grid mayor sedikit lebih gelap saat cetak
          color: scale.grid.drawOnChartArea === false
            ? scale.grid.color
            : (scale.grid.color === '#9ec5e8' || !scale.grid.color ? '#6ba3cc' : scale.grid.color),
          lineWidth: scale.grid.drawOnChartArea === false
            ? scale.grid.lineWidth
            : scaleNum(Math.max(baseGridWidth, 1.15), pixelScale),
        }
        : scale.grid,
      ticks: {
        ...scale.ticks,
        font: scaleFont(tickFont, fontScale),
        padding: scaleNum(scale.ticks?.padding || 4, pixelScale),
        // Kurangi kepadatan label waktu saat cetak
        ...(key === 'x' ? { maxTicksLimit: 8, maxRotation: 0 } : {}),
      },
      title: scale.title
        ? {
          ...scale.title,
          font: scaleFont(titleFont, fontScale),
          padding: { top: scaleNum(4, pixelScale), bottom: scaleNum(4, pixelScale) },
        }
        : scale.title,
    };
  });
  return cloned;
}

/** Klon datasets dengan ketebalan garis & dash disesuaikan resolusi canvas. */
function scaleDatasets(datasets, pixelScale) {
  return (datasets || []).map((ds) => ({
    ...ds,
    borderWidth: scaleNum(ds.borderWidth || 2, pixelScale),
    borderDash: Array.isArray(ds.borderDash)
      ? ds.borderDash.map((d) => Math.round(d * pixelScale))
      : ds.borderDash,
    pointRadius: 0,
    pointHoverRadius: 0,
  }));
}

/**
 * Render grafik ke PNG di canvas tersembunyi dengan ukuran & skala visual sesuai target cetak.
 * opts.pixelScale — proporsi elemen vs canvas (biasanya = PRINT_SCALE).
 * opts.fontBoost  — ekstra perbesaran font untuk keterbacaan kertas (default 1.35).
 */
function renderExportImage(chartData, baseOptions, width, height, opts = {}) {
  const pixelScale = opts.pixelScale ?? opts.fontScale ?? 1.3;
  const fontBoost = opts.fontBoost ?? 1;
  return new Promise((resolve) => {
    if (!chartData || !baseOptions || !width || !height) {
      resolve(null);
      return;
    }
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    canvas.style.position = 'fixed';
    canvas.style.left = '-99999px';
    canvas.style.top = '0';
    document.body.appendChild(canvas);

    const exportOptions = buildExportOptions(baseOptions, pixelScale, fontBoost);
    const exportData = {
      ...chartData,
      datasets: scaleDatasets(chartData.datasets, pixelScale),
    };
    const chart = new ChartJS(canvas.getContext('2d'), {
      type: 'line',
      data: exportData,
      options: exportOptions,
    });

    requestAnimationFrame(() => {
      let dataUrl = null;
      try {
        dataUrl = chart.toBase64Image('image/png', 1);
      } finally {
        chart.destroy();
        canvas.remove();
      }
      resolve(dataUrl);
    });
  });
}

function applyAxisZoom(chart, axis, p1, p2, onZoomChange) {
  const scale = chart.scales[axis];
  if (!scale) return;
  const v1 = scale.getValueForPixel(p1);
  const v2 = scale.getValueForPixel(p2);
  if (v1 == null || v2 == null || v1 === v2) return;
  const min = Math.min(v1, v2);
  const max = Math.max(v1, v2);
  if (typeof chart.zoomScale === 'function') {
    chart.zoomScale(axis, { min, max });
  } else {
    scale.min = min;
    scale.max = max;
    chart.update('none');
  }
  onZoomChange?.(true);
}

const MultiMachineTempChart = forwardRef(function MultiMachineTempChart({
  multiData,
  selectedMachines,
  machineNames = {},
  hiddenChannels = [],
  axisLimits,
  zoomMode = 'xy',
  cursorMode = false,
  cursors = [],
  onCursorPlace,
  onZoomChange,
  onToggleChannel,
}, ref) {
  const chartRef = useRef(null);
  const containerRef = useRef(null);
  const cursorModeRef = useRef(cursorMode);
  const onCursorPlaceRef = useRef(onCursorPlace);
  const onZoomChangeRef = useRef(onZoomChange);
  const [chartArea, setChartArea] = useState(null);
  const [axisDrag, setAxisDrag] = useState(null);

  cursorModeRef.current = cursorMode;
  onCursorPlaceRef.current = onCursorPlace;
  onZoomChangeRef.current = onZoomChange;

  const handleLayoutChange = useCallback((area) => {
    setChartArea(area);
  }, []);

  useEffect(() => {
    const chart = chartRef.current;
    if (chart) chart.$onLayoutChange = handleLayoutChange;
    return () => {
      if (chartRef.current) chartRef.current.$onLayoutChange = null;
    };
  }, [handleLayoutChange]);

  useEffect(() => {
    if (!axisDrag) return undefined;

    const onMove = (e) => {
      const chart = chartRef.current;
      if (!chart) return;
      const pt = canvasPoint(chart, e.clientX, e.clientY);
      setAxisDrag((d) => {
        if (!d) return null;
        return { ...d, end: d.axis === 'y' ? pt.y : pt.x };
      });
    };

    const onUp = (e) => {
      const chart = chartRef.current;
      if (!chart || !axisDrag) {
        setAxisDrag(null);
        return;
      }
      const pt = canvasPoint(chart, e.clientX, e.clientY);
      const end = axisDrag.axis === 'y' ? pt.y : pt.x;
      const area = chart.chartArea;
      if (axisDrag.axis === 'y' && area) {
        const lo = area.top;
        const hi = area.bottom;
        const c1 = Math.max(lo, Math.min(hi, axisDrag.start));
        const c2 = Math.max(lo, Math.min(hi, end));
        applyAxisZoom(chart, 'y', c1, c2, onZoomChangeRef.current);
      } else if (axisDrag.axis === 'x' && area) {
        const lo = area.left;
        const hi = area.right;
        const c1 = Math.max(lo, Math.min(hi, axisDrag.start));
        const c2 = Math.max(lo, Math.min(hi, end));
        applyAxisZoom(chart, 'x', c1, c2, onZoomChangeRef.current);
      }
      setAxisDrag(null);
    };

    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
  }, [axisDrag]);

  const startAxisDrag = (axis, e) => {
    if (cursorMode) return;
    const chart = chartRef.current;
    if (!chart) return;
    e.preventDefault();
    const pt = canvasPoint(chart, e.clientX, e.clientY);
    setAxisDrag({ axis, start: axis === 'y' ? pt.y : pt.x, end: axis === 'y' ? pt.y : pt.x });
  };

  useImperativeHandle(ref, () => ({
    resetZoom: () => {
      chartRef.current?.resetZoom();
      onZoomChange?.(false);
    },
    zoomIn: () => {
      chartRef.current?.zoom(1.15);
      onZoomChange?.(true);
    },
    zoomOut: () => {
      chartRef.current?.zoom(0.87);
      onZoomChange?.(true);
    },
    /**
     * opts.width/opts.height: render ulang di canvas tersembunyi persis sesuai ukuran itu
     *   (aspect-ratio dikunci ke target — dipakai untuk print preview agar tidak ada letterbox).
     * opts.scale: render ulang dengan resolusi lebih tinggi tapi aspect-ratio sama seperti tampilan layar
     *   (dipakai untuk unduhan PNG berkualitas lebih baik).
     * opts.pixelScale / opts.fontBoost: skala visual & ekstra keterbacaan font.
     * tanpa opts: kembalikan gambar apa adanya dari canvas yang sedang tampil.
     */
    getChartImage: (opts) => {
      if (opts?.width && opts?.height) {
        const pixelScale = opts.pixelScale ?? opts.fontScale ?? 3;
        return renderExportImage(chartData, options, opts.width, opts.height, {
          pixelScale,
          fontBoost: opts.fontBoost ?? 0.92,
        });
      }
      if (opts?.scale) {
        const chart = chartRef.current;
        if (!chart) return null;
        const w = Math.round(chart.width * opts.scale);
        const h = Math.round(chart.height * opts.scale);
        return renderExportImage(chartData, options, w, h, {
          pixelScale: opts.scale,
          fontBoost: opts.fontBoost ?? 1.1,
        });
      }
      return chartRef.current?.toBase64Image('image/png', 1);
    },
  }));

  const hiddenSet = useMemo(() => new Set(hiddenChannels), [hiddenChannels]);

  const { chartData, options } = useMemo(() => {
    if (!multiData || selectedMachines.length === 0) {
      return { chartData: null, options: null };
    }

    const units = {};
    selectedMachines.forEach((code) => {
      units[code] = multiData.meta?.[code]?.unit || '';
    });

    const unitSymbols = selectedMachines.map((code) => units[code] || '');
    const uniqueUnits = [...new Set(unitSymbols)].filter((u) => u !== '');
    const primaryUnit = uniqueUnits[0] || '';
    const secondaryUnit = uniqueUnits[1] || null;

    const yMin = parseNum(axisLimits?.yMin);
    const yMax = parseNum(axisLimits?.yMax);
    const y1Min = parseNum(axisLimits?.y1Min);
    const y1Max = parseNum(axisLimits?.y1Max);

    const datasets = selectedMachines.map((code, idx) => {
      const style = LINE_STYLES[idx % LINE_STYLES.length];
      const unitSymbol = units[code] || '';
      const axisId = secondaryUnit && unitSymbol === secondaryUnit ? 'y1' : 'y';
      const displayName = machineNames[code] || code;
      const labelText = unitSymbol ? `${displayName} (${unitSymbol})` : displayName;

      const points = multiData.timestamps.map((ts) => {
        const entry = multiData.table[ts]?.[code];
        const yVal = entry?.temp;
        if (yVal === null || yVal === undefined) return { x: parseTs(ts), y: null };
        return { x: parseTs(ts), y: yVal };
      });

      return {
        label: labelText,
        machineCode: code,
        data: points,
        borderColor: style.color,
        backgroundColor: 'transparent',
        borderDash: style.borderDash,
        borderWidth: style.borderWidth,
        fill: false,
        pointRadius: 0,
        pointHoverRadius: 5,
        pointHoverBorderWidth: 2,
        pointStyle: style.pointStyle,
        tension: 0.15,
        spanGaps: true,
        yAxisID: axisId,
        hidden: hiddenSet.has(code),
      };
    });

    const yValues = collectAxisValues(datasets, 'y');
    const y1Values = secondaryUnit ? collectAxisValues(datasets, 'y1') : [];
    const yDataMax = yValues.length ? Math.max(...yValues) : 0;
    const yDataMin = yValues.length ? Math.min(...yValues) : 0;
    const effectiveYMax = yMax ?? (yDataMax > PRIMARY_Y_DEFAULT_MAX ? undefined : PRIMARY_Y_DEFAULT_MAX);
    const effectiveYMin = yMin ?? (yDataMin < PRIMARY_Y_DEFAULT_MIN ? undefined : PRIMARY_Y_DEFAULT_MIN);
    const yBounds = computeAxisBounds(yValues, effectiveYMin, effectiveYMax, MAJOR_TICK_COUNT);
    const y1Bounds = secondaryUnit
      ? computeAxisBounds(y1Values, y1Min, y1Max, MAJOR_TICK_COUNT)
      : null;

    const yLabelLeft = primaryUnit ? `Nilai (${primaryUnit})` : 'Nilai';

    const scales = {
      x: {
        type: 'time',
        time: { tooltipFormat: 'dd/MM/yyyy HH:mm' },
        grid: { color: '#9ec5e8', lineWidth: 1 },
        border: { display: true, color: '#6ba3cc', width: 1 },
        ticks: {
          color: '#1e3a5f',
          maxRotation: 0,
          font: { size: 10, family: 'Consolas, monospace' },
          maxTicksLimit: 10,
          callback(value) {
            const d = new Date(value);
            if (Number.isNaN(d.getTime())) return '';
            return [
              `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`,
              `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()}`,
            ];
          },
        },
      },
      y: buildAlignedLinearScale(yBounds, {
        position: 'left',
        title: yLabelLeft,
        drawGrid: true,
      }),
    };

    if (secondaryUnit && y1Bounds) {
      scales.y1 = buildAlignedLinearScale(y1Bounds, {
        position: 'right',
        title: `Nilai (${secondaryUnit})`,
        drawGrid: false,
      });
    }

    const opts = {
      responsive: true,
      maintainAspectRatio: false,
      layout: { padding: { left: 4, right: 8, top: 4, bottom: 0 } },
      backgroundColor: '#ffffff',
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: {
          display: true,
          position: 'top',
          align: 'start',
          labels: {
            color: '#1e3a5f',
            font: { size: 12, weight: '600' },
            boxWidth: 34,
            boxHeight: 2,
            padding: 14,
            usePointStyle: false,
            generateLabels(chartInstance) {
              return chartInstance.data.datasets.map((ds, i) => ({
                text: ds.label,
                fillStyle: 'transparent',
                strokeStyle: ds.borderColor,
                lineWidth: ds.borderWidth,
                lineDash: ds.borderDash,
                lineCap: 'butt',
                hidden: !chartInstance.isDatasetVisible(i),
                datasetIndex: i,
              }));
            },
          },
          onClick(evt, legendItem) {
            const code = selectedMachines[legendItem.datasetIndex];
            if (code) onToggleChannel?.(code);
          },
        },
        measurementCursors: { cursors },
        tooltip: {
          backgroundColor: 'rgba(255,255,255,0.98)',
          titleColor: '#1e3a5f',
          bodyColor: '#334155',
          borderColor: '#9ec5e8',
          borderWidth: 1,
          padding: 10,
          cornerRadius: 2,
          titleFont: { size: 11, weight: '600' },
          bodyFont: { size: 10, family: 'Consolas, monospace' },
          callbacks: {
            title(items) {
              if (!items.length) return '';
              const d = new Date(items[0].parsed.x);
              return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
            },
            label(ctx) {
              const v = ctx.parsed.y;
              return v == null ? `${ctx.dataset.label}: —` : `${ctx.dataset.label}: ${v.toFixed(1)}`;
            },
          },
        },
        zoom: {
          zoom: {
            wheel: { enabled: true, speed: 0.08 },
            pinch: { enabled: true },
            drag: {
              enabled: zoomMode === 'xy',
              modifierKey: 'shift',
              backgroundColor: 'rgba(30, 58, 95, 0.1)',
              borderColor: '#1e3a5f',
              borderWidth: 1,
              mode: 'xy',
            },
            mode: zoomMode === 'xy' ? 'xy' : zoomMode,
            onZoomComplete: () => onZoomChange?.(true),
          },
          pan: {
            enabled: true,
            mode: zoomMode === 'xy' ? 'xy' : zoomMode,
            modifierKey: 'ctrl',
            threshold: 8,
            onPanComplete: () => onZoomChange?.(true),
          },
          limits: {
            x: { min: 'original', max: 'original' },
            y: { min: 'original', max: 'original' },
          },
        },
      },
      scales,
      onClick(evt) {
        if (!cursorModeRef.current || !onCursorPlaceRef.current) return;
        const chart = chartRef.current;
        if (!chart?.scales?.x) return;
        const xVal = chart.scales.x.getValueForPixel(evt.x);
        if (xVal == null) return;
        const snapped = snapToNearestTimestamp(new Date(xVal), multiData.timestamps);
        if (snapped) onCursorPlaceRef.current(snapped);
      },
    };

    return { chartData: { datasets }, options: opts };
  }, [
    multiData,
    selectedMachines,
    machineNames,
    hiddenSet,
    axisLimits,
    zoomMode,
    cursors,
    onZoomChange,
    onToggleChannel,
  ]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart?.options?.plugins?.zoom) return;
    const zm = zoomMode === 'xy' ? 'xy' : zoomMode;
    chart.options.plugins.zoom.zoom.mode = zm;
    chart.options.plugins.zoom.zoom.drag.enabled = zoomMode === 'xy';
    chart.options.plugins.zoom.pan.mode = zm;
    chart.update('none');
  }, [zoomMode]);

  if (!chartData) return null;

  const plotH = chartArea ? chartArea.bottom - chartArea.top : 0;
  const plotW = chartArea ? chartArea.right - chartArea.left : 0;
  const xStripH = chartArea ? chartArea.height - chartArea.bottom : 28;

  return (
    <div
      ref={containerRef}
      className={`relative h-full w-full bg-white ${cursorMode ? 'cursor-crosshair' : ''}`}
    >
      <Line ref={chartRef} data={chartData} options={options} />

      {/* Drag zoom sumbu Y — strip kiri (area label tick Y) */}
      {chartArea && zoomMode === 'y' && !cursorMode && (
        <div
          className="absolute z-20 cursor-ns-resize bg-[#1e3a5f]/[0.03] hover:bg-[#1e3a5f]/[0.08] border-r border-dashed border-[#9ec5e8]"
          style={{ left: 0, top: chartArea.top, width: chartArea.left, height: plotH }}
          title="Drag vertikal: pilih rentang nilai Y untuk zoom"
          onMouseDown={(e) => startAxisDrag('y', e)}
        />
      )}

      {/* Drag zoom sumbu X — strip bawah (area label tick waktu) */}
      {chartArea && zoomMode === 'x' && !cursorMode && (
        <div
          className="absolute z-20 cursor-ew-resize bg-[#1e3a5f]/[0.03] hover:bg-[#1e3a5f]/[0.08] border-t border-dashed border-[#9ec5e8]"
          style={{ left: chartArea.left, top: chartArea.bottom, width: plotW, height: Math.max(xStripH, 24) }}
          title="Drag horizontal: pilih rentang waktu untuk zoom"
          onMouseDown={(e) => startAxisDrag('x', e)}
        />
      )}

      {/* Preview seleksi saat drag sumbu */}
      {axisDrag && chartArea && (
        <>
          {axisDrag.axis === 'y' && (
            <div
              className="absolute z-30 pointer-events-none border-y-2 border-[#1e3a5f] bg-[#1e3a5f]/10"
              style={{
                left: chartArea.left,
                width: plotW,
                top: Math.min(axisDrag.start, axisDrag.end),
                height: Math.max(2, Math.abs(axisDrag.end - axisDrag.start)),
              }}
            />
          )}
          {axisDrag.axis === 'x' && (
            <div
              className="absolute z-30 pointer-events-none border-x-2 border-[#1e3a5f] bg-[#1e3a5f]/10"
              style={{
                top: chartArea.top,
                height: plotH,
                left: Math.min(axisDrag.start, axisDrag.end),
                width: Math.max(2, Math.abs(axisDrag.end - axisDrag.start)),
              }}
            />
          )}
        </>
      )}
    </div>
  );
});

export function computeChannelStats(multiData, code) {
  if (!multiData?.timestamps) return { min: null, max: null, current: null };
  const temps = multiData.timestamps
    .map((ts) => multiData.table[ts]?.[code]?.temp)
    .filter((v) => v != null && !Number.isNaN(v));
  if (!temps.length) return { min: null, max: null, current: null };
  return {
    min: Math.min(...temps),
    max: Math.max(...temps),
    current: temps[temps.length - 1],
  };
}

export default MultiMachineTempChart;
