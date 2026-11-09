import React, { useState, useEffect, useMemo, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../lib/api';
import { format } from 'date-fns';

import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip as RechartsTooltip, ResponsiveContainer, LineChart, Line, ReferenceLine,
  ComposedChart, BarChart, Bar, Cell, LabelList, PieChart, Pie, Legend,
} from 'recharts';
import {
  Calendar, Activity, X, Search, AlertTriangle, Gauge, Timer, Zap, Clock,
  ChevronLeft, ChevronRight, RefreshCw, Flame, ArrowRight, Printer, CheckCircle2,
  TrendingDown, Wind, PowerOff, Download, Layers, Sparkles, ExternalLink
} from 'lucide-react';

import { AVAILABILITY_PHASE as PHASE_COLORS } from '../lib/phaseColors';
import LossesBreakdownModal from '../components/LossesBreakdownModal';
import { ShareToChatButton } from '../components/chat/ShareToChatButton';

// ── Single availability bar for one machine ────────────────────────
function AvailabilityBar({ machine, machineAnomalies = [], onMachineClick }) {
  const [tooltip, setTooltip] = useState(null);

  // Collect all unique anomalies for this machine
  const allAnomalies = [...new Set(machineAnomalies.flatMap(a => a.anomaly_types))];

  return (
    <div 
      className="flex items-center gap-2 py-1.5 px-1.5 -mx-1.5 rounded-md group hover:bg-gray-100 transition-colors cursor-pointer"
      onClick={() => onMachineClick(machine.machine_id)}
    >
      {/* Machine label & Anomalies */}
      <div className="flex flex-col items-end flex-shrink-0 w-28 truncate">
        <div
          className="text-xs font-semibold text-gray-700 group-hover:text-blue-700 text-right leading-tight transition-colors w-full text-right truncate"
          title={machine.machine_name}
        >
          {machine.machine_name}
        </div>
        {allAnomalies.length > 0 && (
          <span className="inline-flex items-center gap-0.5 text-[9px] font-bold text-red-600 bg-red-50 px-1 py-0.5 rounded border border-red-100 mt-0.5">
            <AlertTriangle className="w-2.5 h-2.5" />
            {allAnomalies.join(', ')}
          </span>
        )}
      </div>

      {/* Bar */}
      <div className="relative flex-1">
        <div className="w-full h-5 flex rounded overflow-hidden shadow-inner bg-gray-100">
          {machine.segments.map((seg, i) => {
            const color = PHASE_COLORS[seg.state] || PHASE_COLORS.OFF;
            return (
              <div
                key={i}
                className={`${color.bg} h-full flex-shrink-0 cursor-pointer transition-opacity hover:opacity-80`}
                style={{ width: `${seg.width_pct}%` }}
                onMouseEnter={(e) => {
                  const rect = e.currentTarget.getBoundingClientRect();
                  setTooltip({ state: seg.state, label: color.label, x: rect.left, y: rect.top });
                }}
                onMouseLeave={() => setTooltip(null)}
                onClick={() => onMachineClick(machine.machine_id)}
              />
            );
          })}
        </div>
        {tooltip && (
          <div className="fixed z-50 px-2 py-1 bg-gray-800 text-white text-xs rounded shadow-lg pointer-events-none"
            style={{ left: tooltip.x, top: tooltip.y - 30 }}>
            {tooltip.label}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Horizontal bar chart for "Jumlah Proses Per Mesin" per group ───
function ProcessCountBarGroup({ group, onMachineClick }) {
  const data = group.machines.map((m) => ({
    id: m.id,
    name: m.name,
    process_count: m.process_count,
  }));
  const maxCount = Math.max(1, ...data.map((d) => d.process_count));
  const height = Math.max(60, data.length * 30);

  const barColor = (count) => {
    if (count <= 0) return '#e5e7eb';
    const ratio = count / maxCount;
    if (ratio > 0.75) return '#1d4ed8';
    if (ratio > 0.5) return '#3b82f6';
    if (ratio > 0.25) return '#60a5fa';
    return '#93c5fd';
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <h3 className="text-xs font-semibold text-gray-700">{group.group_name}</h3>
        <span className="text-xs text-gray-400">{group.total_group_processes} total</span>
      </div>
      <div style={{ height }} className="w-full">
        <ResponsiveContainer width="100%" height="100%" minHeight={1} minWidth={1}>
          <BarChart
            layout="vertical"
            data={data}
            margin={{ top: 0, right: 24, left: 0, bottom: 0 }}
            barCategoryGap={6}
            onClick={(state) => {
              const id = state?.activePayload?.[0]?.payload?.id;
              if (id) onMachineClick(id);
            }}
          >
            <XAxis type="number" hide domain={[0, 'dataMax']} />
            <YAxis
              type="category"
              dataKey="name"
              width={110}
              tick={{ fontSize: 11, fill: '#4b5563' }}
              axisLine={false}
              tickLine={false}
            />
            <RechartsTooltip
              cursor={{ fill: '#f3f4f6' }}
              contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }}
              formatter={(value) => [`${value} proses`, '']}
            />
            <Bar dataKey="process_count" radius={[0, 4, 4, 0]} maxBarSize={16} cursor="pointer">
              {data.map((d, i) => (
                <Cell key={i} fill={barColor(d.process_count)} />
              ))}
              <LabelList
                dataKey="process_count"
                position="right"
                style={{ fontSize: 11, fill: '#6b7280', fontWeight: 600 }}
              />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

const formatBackendDate = (dateStr) => {
  if (!dateStr || dateStr === '-' || dateStr === 'In Progress') return dateStr;
  const months = {'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04', 'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08', 'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'};
  try {
    const parts = dateStr.replace(',', '').split(' ');
    if (parts.length === 4) {
      return `${parts[0].padStart(2, '0')}/${months[parts[1]] || '00'}/${parts[2]} ${parts[3]}`;
    }
    return dateStr;
  } catch(e) {
    return dateStr;
  }
};

const formatChangeover = (minutes) => {
  if (!minutes || minutes <= 0) return '-';
  const h = Math.floor(minutes / 60);
  const m = Math.round(minutes % 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
};

const PARETO_BAR_COLORS = {
  red: '#ef4444',
  orange: '#f97316',
  blue: '#3b82f6',
  purple: '#a855f7',
  gray: '#6b7280',
};

const BOILER_PIE_COLORS = { Ideal: '#10B981', Rendah: '#F59E0B', Tinggi: '#EF4444' };


// --- BEGIN V2 HELPERS ---
export function summarizeBoilerAlerts(boiler) {
  const list = boiler?.alert_history ?? [];
  const isSig  = (a) => a.alert_type === 'NO_SIGNAL';
  const isReg  = (a) => a.alert_type === 'REGULATION';
  const crit   = list.filter((a) => a.severity === 'CRITICAL' && !isReg(a));
  const warn   = list.filter((a) => a.severity === 'WARNING' && !isSig(a) && !isReg(a));
  const noSig  = list.filter(isSig);
  const regTotal = boiler?.regulation_summary?.total ?? (list.some(isReg) ? list.filter(isReg).length : null);
  const by = (arr, t) => arr.filter((a) => a.alert_type === t).length;
  return {
    critical: { total: crit.length, steam: by(crit, 'STEAM_PRESSURE'), hto: by(crit, 'HTO_TEMPERATURE'), signal: by(crit, 'NO_SIGNAL') },
    regulasi: regTotal,
    warning:  warn.length,
    noSignal: noSig.length,
  };
}

const num = (v, d = 1) => (v == null || Number.isNaN(+v) ? null : +(+v).toFixed(d));

export function buildStory(daily, boiler) {
  const o = daily?.oee_lite ?? {};
  const wc = daily?.world_class ?? {};
  const k = boiler?.kpi_summary ?? {};
  const gk = daily?.production_summary ?? {};
  const alerts = summarizeBoilerAlerts(boiler);
  const steamTon = k.total_steam_usage_kg != null ? num(k.total_steam_usage_kg / 1000, 1) : null;

  if (daily?.total_steam_usage && k.total_steam_usage_kg &&
      Math.abs(daily.total_steam_usage - k.total_steam_usage_kg) / k.total_steam_usage_kg > 0.01) {
    console.warn('[DailyReport] steam daily vs boiler berbeda >1%', daily.total_steam_usage, k.total_steam_usage_kg);
  }

  const kpis = [
    { 
      key: 'steam',  label: 'Total Steam',   value: steamTon, unit: 'ton',
      idealPct: k.pressure_ideal_percent,
      caption: k.pressure_ideal_percent != null ? `Tekanan Ideal: ${k.pressure_ideal_percent}%` : null,
      subItems: k.pressure_ideal_percent != null ? [
        { label: 'Tekanan Ideal', val: `${k.pressure_ideal_percent}%` }
      ] : []
    },
    { 
      key: 'batch',  label: 'Total Proses',  value: daily?.total_processes, unit: 'batch',
      caption: gk.fresh_yd != null ? `FRESH: ${gk.fresh_yd.toLocaleString('id-ID')} yd | CREAPING: ${gk.creaping_yd.toLocaleString('id-ID')} yd | Lainnya: ${gk.other_yd.toLocaleString('id-ID')} yd` : null,
      subItems: [
        gk.fresh_yd != null ? { label: 'FRESH', val: `${gk.fresh_yd.toLocaleString('id-ID')} yd` } : null,
        gk.creaping_yd != null ? { label: 'CREAPING', val: `${gk.creaping_yd.toLocaleString('id-ID')} yd` } : null,
        gk.other_yd != null && Number(gk.other_yd) > 0 ? { label: 'Lainnya', val: `${Number(gk.other_yd).toLocaleString('id-ID')} yd` } : null,
      ].filter(Boolean)
    },
    { key: 'avail',  label: 'Availability',  value: o.availability, unit: '%', target: wc.availability },
    { key: 'eff',    label: 'Efisiensi',     value: o.performance,  unit: '%', target: wc.performance },
    { key: 'oee',    label: 'OEE-Lite',      value: o.combined,     unit: '%', target: wc.combined },
    { 
      key: 'power',  label: 'Estimasi Listrik', value: gk.power_kwh != null ? num(gk.power_kwh, 1) : null, unit: 'kWh',
      caption: gk.power_lwbp_kwh != null ? `LWBP: ${gk.power_lwbp_kwh.toLocaleString('id-ID')} kWh | WBP: ${gk.power_wbp_kwh.toLocaleString('id-ID')} kWh` : null,
      subItems: [
        gk.power_lwbp_kwh != null ? { label: 'LWBP', val: `${gk.power_lwbp_kwh.toLocaleString('id-ID')} kWh` } : null,
        gk.power_wbp_kwh != null ? { label: 'WBP', val: `${gk.power_wbp_kwh.toLocaleString('id-ID')} kWh` } : null,
      ].filter(Boolean)
    },
  ];

  return { kpis, alerts };
}

export function buildBoard(daily) {
  const rows = new Map();
  const get = (id, name) => rows.get(id) ?? rows.set(id, { 
    id, name, batch: null, avail: null, eff: null, loss: null, 
    steamUsage: null, steamEff: null, steamOk: null, powerUsage: null, powerEff: null,
    steamLossKg: null, steamLossRp: null, powerLwbpRp: null, powerWbpRp: null, powerLossRp: null,
    outputYd: null, steamCostPerYd: null, powerCostPerYd: null, totalCostPerYd: null
  }).get(id);
  (daily?.availability_summary?.machines ?? []).forEach((m) => { get(m.machine_id, m.machine_name).avail = m.availability; });
  (daily?.efficiency_summary?.machines ?? []).forEach((m) => {
    const r = get(m.machine_id, m.machine_name); 
    r.eff = m.avg_eff; 
    r.loss = m.total_loss_time_str;
    r.steamUsage = m.steam_usage;
    r.steamEff = m.steam_eff;
    r.steamOk = m.steam_ok_pct;
    r.powerUsage = m.power_usage;
    r.powerEff = m.power_eff;
    
    r.steamLossKg = m.steam_loss_kg;
    r.steamLossRp = m.steam_loss_rp;
    r.powerLwbpRp = m.power_lwbp_rp;
    r.powerWbpRp = m.power_wbp_rp;
    r.powerLossRp = m.power_loss_rp;
    
    r.outputYd = m.output_yd;
    r.steamCostPerYd = m.steam_cost_per_yd;
    r.powerCostPerYd = m.power_cost_per_yd;
    r.totalCostPerYd = m.total_cost_per_yd;
  });
  (daily?.heatmap_groups ?? []).forEach((g) => g.machines.forEach((m) => { get(m.id, m.name).batch = m.process_count; }));
  const tone = (v, ok, warn) => (v == null ? 'na' : v >= ok ? 'ok' : v >= warn ? 'warn' : 'bad');
  return [...rows.values()]
    .map((r) => {
      const oeeVal = (r.avail != null && r.eff != null) ? ((r.avail * r.eff) / 100) : null;
      return {
        ...r,
        oee: oeeVal,
        availTone: tone(r.avail, 75, 50),
        effTone: tone(r.eff, 75, 50),
        oeeTone: tone(oeeVal, 75, 50),
        steamEffTone: tone(r.steamEff, 80, 60),
        steamOkTone: tone(r.steamOk, 80, 60),
        powerEffTone: tone(r.powerEff, 80, 60)
      };
    })
    .sort((a, b) => (a.eff ?? 999) - (b.eff ?? 999));
}


const CHART_MODES = {
  steam: {
    label: 'Steam & Tekanan',
    area: { key: 'steam', name: 'Steam (kg/j)', fill: '#bfdbfe', stroke: '#60a5fa' },
    line: { key: 'pressure', name: 'Tekanan (bar)', stroke: '#f59e0b', domain: [0, 8], step: false, integer: false },
  },
  hto: {
    label: 'HTO & Suhu Oli',
    area: { key: 'hto_usage', name: 'Beban HTO (kCal/j)', fill: '#fed7aa', stroke: '#f97316' },
    line: { key: 'hto_temp', name: 'Suhu Oli HTO (°C)', stroke: '#ef4444', domain: ['auto', 'auto'], step: false, integer: false },
  },
  power: {
    label: 'Listrik & Mesin Aktif',
    area: { key: 'power_kw', name: 'Est. Beban Listrik (kW)', fill: '#ddd6fe', stroke: '#8b5cf6' },
    line: { key: 'active_machines', name: 'Mesin Aktif', stroke: '#10b981', domain: [0, 'dataMax + 2'], step: true, integer: true },
  },
};

export function buildSteamChart(boiler) {
  const data = (boiler?.chart_data ?? []).map((p) => ({ 
    time: p.time, 
    steam: p.steam_usage, 
    pressure: p.Steam_Pr,
    hto_usage: p.hto_usage,
    hto_temp: p.Oil_Temp,
    power_kw: p.power_kw,
    active_machines: p.active_machines
  }));
  const marks = (boiler?.alert_history ?? [])
    .filter((a) => a.severity === 'CRITICAL')
    .map((a) => {
      if (!a.created_at) return { time: '00:00', title: a.title };
      const [h, m] = String(a.created_at).slice(11, 16).split(':').map(Number);
      return { time: `${String(h || 0).padStart(2, '0')}:${String(Math.floor((m || 0) / 10) * 10).padStart(2, '0')}`, title: a.title };
    });
  return { data, marks };
}

const TONE = { critical: 'bg-rose-50 text-rose-700 border-rose-200/80', regulasi: 'bg-amber-50 text-amber-700 border-amber-200/80',
               warning: 'bg-yellow-50 text-yellow-700 border-yellow-200/80', signal: 'bg-slate-50 text-slate-600 border-slate-200/80' };

function AlertChips({ alerts }) {
  const Chip = ({ tone, label, value, hint }) => (
    <span title={hint} className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs font-semibold ${TONE[tone]}`}>
      <span className="w-1.5 h-1.5 rounded-full bg-current" />{label}<b className="tabular-nums">{value ?? '—'}</b>
    </span>);
  return (
    <div className="flex flex-wrap gap-2 mb-4">
      <Chip tone="critical" label="Critical" value={alerts.critical.total}
            hint={`${alerts.critical.steam} tekanan · ${alerts.critical.hto} HTO · ${alerts.critical.signal} sinyal`} />
      <Chip tone="regulasi" label="Regulasi" value={alerts.regulasi}
            hint={alerts.regulasi == null ? 'Data regulasi belum tersedia di API' : 'Pembakaran melambat'} />
      <Chip tone="warning"  label="Warning" value={alerts.warning} />
      <Chip tone="signal"   label="Sinyal hilang" value={alerts.noSignal} hint="Sensor NO_SIGNAL (dihitung per kejadian)" />
    </div>);
}

function KpiCard({ k }) {
  const pct = k.target ? Math.min(100, (k.value / k.target) * 100) : null;
  const diff = (k.value != null && k.target != null) ? +(k.value - k.target).toFixed(1) : null;

  // Icon & color styling matching reference report
  let IconComp = Activity;
  let iconBoxClass = 'bg-blue-50 text-blue-600 border border-blue-100';
  let barColor = 'bg-[#2563eb]';

  if (k.key === 'steam') {
    IconComp = Gauge;
    iconBoxClass = 'bg-blue-50 text-blue-600 border border-blue-100';
  } else if (k.key === 'batch') {
    IconComp = Layers;
    iconBoxClass = 'bg-sky-50 text-sky-600 border border-sky-100';
  } else if (k.key === 'avail') {
    IconComp = Clock;
    iconBoxClass = 'bg-blue-50 text-blue-600 border border-blue-100';
    barColor = 'bg-[#2563eb]';
  } else if (k.key === 'eff') {
    IconComp = Activity;
    iconBoxClass = 'bg-emerald-50 text-emerald-600 border border-emerald-100';
    barColor = 'bg-emerald-500';
  } else if (k.key === 'oee') {
    IconComp = Sparkles;
    iconBoxClass = 'bg-amber-50 text-amber-600 border border-amber-100';
    barColor = 'bg-amber-500';
  } else if (k.key === 'power') {
    IconComp = Zap;
    iconBoxClass = 'bg-teal-50 text-teal-600 border border-teal-100';
  }

  return (
    <div className="bg-white rounded-2xl sm:rounded-3xl border border-slate-200/80 p-3.5 sm:p-4 shadow-xs hover:shadow-sm transition-all flex flex-col justify-between h-full min-h-[175px]">
      <div>
        <div className="flex items-center gap-2">
          <div className={`w-7 h-7 rounded-full flex items-center justify-center shrink-0 ${iconBoxClass}`}>
            <IconComp className="w-3.5 h-3.5" />
          </div>
          <span className="text-xs font-bold text-slate-700 tracking-tight truncate">{k.label}</span>
        </div>
        <div className="text-2xl sm:text-[26px] font-bold text-slate-900 tracking-tight tabular-nums mt-2 leading-none">
          {k.value ?? '—'}
          <span className="text-xs font-semibold text-slate-400 ml-1 font-sans">{k.unit}</span>
        </div>
      </div>

      {/* Footer Area - Uniform height across all cards */}
      <div className="mt-3.5 pt-2.5 border-t border-slate-100/90 min-h-[58px] flex flex-col justify-center">
        {/* Case A: Cards with progress bar target (avail, eff, oee) */}
        {pct != null && (
          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-[11px] font-medium leading-none">
              <span className="text-slate-400">Target</span>
              <span className="text-slate-600 font-semibold tabular-nums">{k.target}%</span>
            </div>
            <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
              <div className={`h-full rounded-full ${barColor} transition-all duration-500`} style={{ width: `${pct}%` }} />
            </div>
            <div className="flex items-center justify-between text-[10px] text-slate-400 leading-none">
              <span>Selisih</span>
              {diff != null ? (
                <span className={`font-bold tabular-nums ${diff >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>
                  {diff > 0 ? `+${diff}%` : `${diff}%`}
                </span>
              ) : (
                <span className="font-semibold text-slate-400">—</span>
              )}
            </div>
          </div>
        )}

        {/* Case B: Total Steam (has idealPct for boiler pressure) */}
        {k.key === 'steam' && (
          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-[11px] font-medium leading-none">
              <span className="text-slate-400">Tekanan Ideal</span>
              <span className="text-blue-600 font-bold tabular-nums">
                {k.idealPct != null ? `${k.idealPct}%` : '—'}
              </span>
            </div>
            <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
              <div 
                className="h-full rounded-full bg-blue-500 transition-all duration-500" 
                style={{ width: `${Math.min(100, Math.max(0, k.idealPct ?? 0))}%` }} 
              />
            </div>
            <div className="flex items-center justify-between text-[10px] text-slate-400 leading-none">
              <span>Status Pasokan</span>
              <span className={`font-semibold tabular-nums ${(k.idealPct ?? 0) >= 85 ? 'text-emerald-600' : 'text-amber-600'}`}>
                {(k.idealPct ?? 0) >= 85 ? 'Optimal' : 'Perlu Pantau'}
              </span>
            </div>
          </div>
        )}

        {/* Case C: Structured sub-items (Total Proses, Estimasi Listrik) */}
        {k.subItems && k.subItems.length > 0 && k.key !== 'steam' && (
          <div className="space-y-1">
            {k.subItems.map((item, idx) => (
              <div key={idx} className="flex items-center justify-between text-[10.5px] leading-tight">
                <span className="font-semibold text-slate-400 text-[10px] uppercase tracking-wider">{item.label}:</span>
                <span className="font-semibold text-slate-700 tabular-nums">{item.val}</span>
              </div>
            ))}
          </div>
        )}

        {/* Fallback if caption exists without subItems / pct */}
        {k.caption && (!k.subItems || k.subItems.length === 0) && pct == null && k.key !== 'steam' && (
          <div className="text-[10.5px] text-slate-500 font-medium leading-tight">
            {k.caption}
          </div>
        )}
      </div>
    </div>
  );
}
// --- END V2 HELPERS ---


// --- DATA LOSSES HARIAN COMPONENT ---
function LossCard({ title, value, unit, icon, disabled, onClick }) {
  return (
    <div
      onClick={!disabled && onClick ? onClick : undefined}
      className={`flex flex-col justify-between p-3 sm:p-3.5 rounded-2xl border bg-white transition-all ${
        disabled
          ? 'opacity-50 grayscale cursor-not-allowed'
          : 'border-slate-200/80 shadow-xs hover:border-rose-300 hover:shadow-sm hover:-translate-y-0.5 cursor-pointer group'
      }`}
    >
      <div>
        <div className="flex items-center gap-2 mb-2">
          <div className={`w-6 h-6 rounded-lg flex items-center justify-center shrink-0 ${
            disabled ? 'bg-slate-100 text-slate-400' : 'bg-rose-50 text-rose-500 border border-rose-100 group-hover:bg-rose-500 group-hover:text-white transition-colors'
          }`}>
            {icon}
          </div>
          <span className="text-xs font-bold text-slate-700 group-hover:text-slate-900 truncate">{title}</span>
        </div>
        <div className="flex items-baseline gap-1 mt-1">
          <span className={`text-xl sm:text-2xl font-black tabular-nums font-mono leading-none ${disabled ? 'text-slate-400' : 'text-rose-600'}`}>
            {value != null ? (typeof value === 'number' ? value.toLocaleString('id-ID') : value) : '—'}
          </span>
          <span className="text-xs font-semibold text-slate-400">{unit}</span>
        </div>
      </div>
      {!disabled && onClick && (
        <div className="mt-2 pt-1.5 border-t border-slate-100 flex items-center justify-between text-[10px] text-slate-400 group-hover:text-rose-600 font-semibold transition-colors no-print">
          <span>Lihat Rincian</span>
          <ArrowRight className="w-3 h-3" />
        </div>
      )}
    </div>
  );
}

export default function DailyReport() {
  const navigate = useNavigate();
  const [selectedDate, setSelectedDate] = useState(() => {
    const saved = sessionStorage.getItem('dailyReportDate');
    if (saved) return saved;
    const now = new Date();
    if (now.getHours() < 6) now.setDate(now.getDate() - 1);
    return now.toISOString().split('T')[0];
  });

  useEffect(() => {
    sessionStorage.setItem('dailyReportDate', selectedDate);
  }, [selectedDate]);

  const [reportData, setReportData]   = useState(null);
  const [loading, setLoading]         = useState(false);
  const [error, setError]             = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [boardMode, setBoardMode] = useState('mode1');
  const [chartViewMode, setChartViewMode] = useState('steam');


  // Modal state
  const [dailyChartDetail, setDailyChartDetail] = useState(null);
  const [isDailyModalOpen, setIsDailyModalOpen] = useState(false);
  const [processAnalyticsDetail, setProcessAnalyticsDetail] = useState(null);
  const [processModalError, setProcessModalError] = useState(null);
  const [selectedProcessId, setSelectedProcessId] = useState(null);
  const [isProcessModalOpen, setIsProcessModalOpen] = useState(false);

  // Efficiency Problem Modal State
  const [selectedProblemCategory, setSelectedProblemCategory] = useState(null);
  const [isProblemModalOpen, setIsProblemModalOpen] = useState(false);
  const [selectedLossCategory, setSelectedLossCategory] = useState(null);

  // ── Boiler mini-summary (lazy loaded when section scrolls into view) ──
  const [boilerData, setBoilerData]       = useState(null);
  const [boilerLoading, setBoilerLoading] = useState(false);
  const [boilerError, setBoilerError]     = useState(null);
  const [boilerInView, setBoilerInView]   = useState(false);
  const boilerSectionRef = useRef(null);
  const boilerLoadedDateRef = useRef(null);

  const [dailyAnomalies, setDailyAnomalies] = useState([]);
  const [anomalyStats, setAnomalyStats] = useState(null);

  
  const fetchBoiler = (date, isManual = false) => {
    setBoilerLoading(true);
    setBoilerError(null);
    api.get(`/report/boiler-summary?date=${date}`, { cache: isManual ? false : undefined })
      .then((res) => {
        if (res.data.error) {
          setBoilerError(res.data.error);
          setBoilerData(null);
        } else {
          setBoilerData(res.data);
        }
        boilerLoadedDateRef.current = date;
      })
      .catch((err) => {
        console.error('Gagal mengambil ringkasan boiler:', err);
        setBoilerError('Gagal memuat ringkasan boiler.');
      })
      .finally(() => setBoilerLoading(false));
  };

  const handleRefresh = () => {
    fetchReport(selectedDate, true);
    fetchBoiler(selectedDate, true);
  };

  const fetchReport = async (date, isManual = false) => {
    setLoading(true);
    setError(null);
    try {
      const [summaryResult, anomalyResult] = await Promise.allSettled([
        api.get(`/report/daily-summary?date=${date}`, { cache: isManual ? false : undefined }),
        api.get(`/anomalies/?date=${date}`)
      ]);

      // 1. Evaluasi laporan harian utama
      if (summaryResult.status === 'fulfilled') {
        const summaryData = summaryResult.value.data;
        if (summaryData?.error) {
          setError(summaryData.error);
          setReportData(null);
        } else {
          setReportData(summaryData);
        }
      } else {
        const err = summaryResult.reason;
        console.error('Gagal mengambil daily summary:', err);
        const errMsg =
          err?.response?.data?.message ||
          err?.response?.data?.detail ||
          'Gagal mengambil data laporan. Pastikan koneksi atau izin akses sesuai.';
        setError(errMsg);
        setReportData(null);
      }

      // 2. Evaluasi anomali (opsional / graceful degradation)
      if (anomalyResult.status === 'fulfilled') {
        setDailyAnomalies(anomalyResult.value.data?.data || []);
        setAnomalyStats(anomalyResult.value.data?.summary || null);
      } else {
        console.warn(
          'Data anomali tidak tersedia (status: ' +
          (anomalyResult.reason?.response?.status || anomalyResult.reason?.message) +
          ')'
        );
        setDailyAnomalies([]);
        setAnomalyStats(null);
      }
    } catch (err) {
      console.error('Unexpected error in fetchReport:', err);
      setError('Terjadi kesalahan yang tidak terduga.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { 
    fetchReport(selectedDate);
    fetchBoiler(selectedDate);
  }, [selectedDate]);

  const changeDate = (days) => {
    const d = new Date(selectedDate);
    d.setDate(d.getDate() + days);
    setSelectedDate(d.toISOString().split('T')[0]);
  };

  // Observe boiler section visibility to lazy-fetch its data
  useEffect(() => {
    const el = boilerSectionRef.current;
    if (!el) return undefined;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) setBoilerInView(true);
      },
      { rootMargin: '250px' }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!boilerInView) return;
    if (boilerLoadedDateRef.current === selectedDate) return;
    fetchBoiler(selectedDate);
  }, [boilerInView, selectedDate]);

  const openDailyChartModal = (machineId) => {
    navigate(`/machine-daily-analytics/${machineId}/${selectedDate}`);
  };

  const openProcessAnalyticsModal = async (processId) => {
    setSelectedProcessId(processId);
    setIsProcessModalOpen(true);
    setProcessAnalyticsDetail(null);
    setProcessModalError(null);
    try {
      const res = await api.get(`/report/process/${processId}/analytics`, { cache: false });
      setProcessAnalyticsDetail(res.data);
    } catch (err) {
      console.error('Gagal mengambil process analytics:', err);
      setProcessModalError(err.response?.data?.message || err.message || 'Gagal memuat analitik proses.');
    }
  };

  const closeModal = () => { setIsDailyModalOpen(false); setDailyChartDetail(null); };
  const closeProcessModal = () => { setIsProcessModalOpen(false); setProcessAnalyticsDetail(null); setProcessModalError(null); };

  const openProblemModal = (category) => {
    setSelectedProblemCategory(category);
    setIsProblemModalOpen(true);
  };
  const closeProblemModal = () => {
    setIsProblemModalOpen(false);
    setSelectedProblemCategory(null);
  };

  // ── Client-side search / filter ────────────────────────────────
  const filteredHistoryGroups = useMemo(() => {
    if (!reportData) return [];
    const q = searchQuery.trim().toLowerCase();
    if (!q) return reportData.history_groups;

    return reportData.history_groups.reduce((acc, group) => {
      const filteredItems = group.items.filter(item =>
        [item.machine_name, item.machine_code, String(item.batch_number),
         item.start_time, item.end_time, String(item.max_temp),
         item.nomor_order, item.artikel_kain, item.batch_kain]
          .some(field => field && String(field).toLowerCase().includes(q))
      );
      if (filteredItems.length > 0) acc.push({ ...group, items: filteredItems });
      return acc;
    }, []);
  }, [reportData, searchQuery]);

  const totalFiltered = useMemo(
    () => filteredHistoryGroups.reduce((s, g) => s + g.items.length, 0),
    [filteredHistoryGroups]
  );

  // ── Executive summary insight (narrative headline) ─────────────
  const summary = useMemo(() => {
    if (!reportData) return null;
    const oee = reportData.oee_lite?.combined ?? 0;
    const availability = reportData.oee_lite?.availability ?? 0;
    const performance = reportData.oee_lite?.performance ?? 0;
    const target = reportData.world_class?.combined ?? 85;
    const oeeOk = oee >= target;
    const topIdle = (reportData.downtime_ranking || [])[0] || null;
    const lowEff = reportData.efficiency_problems?.total_low_efficiency ?? 0;
    const totalAnalyzed = reportData.efficiency_problems?.total_analyzed ?? 0;
    return { oee, availability, performance, target, oeeOk, topIdle, lowEff, totalAnalyzed };
  }, [reportData]);

  // ── Boiler mini charts (derived client-side, same logic as Boiler Report) ──
  const boilerPressurePie = useMemo(() => {
    if (!boilerData?.pressure_dist) return [];
    const { ideal = 0, under = 0, over = 0 } = boilerData.pressure_dist;
    const total = ideal + under + over;
    if (total === 0) return [];
    const pct = (v) => Number(((v / total) * 100).toFixed(1));
    return [
      { name: 'Ideal', value: pct(ideal) },
      { name: 'Rendah', value: pct(under) },
      { name: 'Tinggi', value: pct(over) },
    ];
  }, [boilerData]);

  const boilerDemandHistogram = useMemo(() => {
    const usages = (boilerData?.chart_data || []).map((d) => d.steam_usage).filter((u) => u > 0);
    if (usages.length === 0) return [];
    const min = Math.min(...usages);
    const max = Math.max(...usages);
    const binCount = 10;
    const binSize = (max - min) / binCount || 1;
    const bins = Array.from({ length: binCount }, (_, i) => ({
      name: `${Math.round(min + i * binSize)}`,
      count: 0,
    }));
    usages.forEach((u) => {
      let idx = Math.floor((u - min) / binSize);
      if (idx >= binCount) idx = binCount - 1;
      if (idx < 0) idx = 0;
      bins[idx].count += 1;
    });
    return bins;
  }, [boilerData]);

  const boilerKpi = boilerData?.kpi_summary;
  const boilerFuelCalibrated = boilerData?.fuel_config?.steam_calibrated || boilerData?.fuel_config?.hto_calibrated;


  const handlePrint = () => {
    const style = document.createElement('style');
    style.id = 'daily-print-page-style';
    style.textContent = '@page { size: A4 landscape; margin: 8mm 6mm; }';
    document.head.appendChild(style);

    document.documentElement.classList.add('printing-daily');

    const cleanup = () => {
      document.documentElement.classList.remove('printing-daily');
      document.getElementById('daily-print-page-style')?.remove();
    };
    window.addEventListener('afterprint', cleanup, { once: true });

    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        window.print();
      });
    });
  };

  return (
    <div className="h-full overflow-y-auto bg-slate-50 pb-12 print-area font-sans antialiased text-slate-800">
      {/* 🚀 Top Header Toolbar: title + date navigation 🚀 */}
      <div className="sticky top-0 z-20 bg-white/95 backdrop-blur-md border-b border-slate-200/80 px-3 sm:px-6 py-2.5 flex items-center justify-between gap-3 no-print">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-10 h-10 rounded-2xl bg-gradient-to-br from-blue-500 to-blue-700 text-white flex items-center justify-center shrink-0 shadow-sm">
            <Activity className="w-5 h-5 text-white" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h1 className="text-base sm:text-lg font-extrabold text-slate-900 tracking-tight truncate">Ringkasan Produksi</h1>
              <span className="text-xs text-slate-400 font-semibold hidden md:inline">· Daily Report</span>
              <a
                href="/daily-report-deep"
                className="inline-flex items-center gap-1 text-[11px] font-bold text-indigo-700 bg-indigo-50 hover:bg-indigo-100 px-2.5 py-0.5 rounded-full border border-indigo-200 transition-colors shadow-2xs"
                title="Buka Laman Eksperimen Analisis Mendalam"
              >
                ✨ V2 Deep &rarr;
              </a>
            </div>
            <p className="text-[10px] sm:text-xs text-slate-500 truncate font-medium">
              Overview performa produksi: {format(new Date(selectedDate), 'EEEE, dd MMM yyyy')} 
              <span className="hidden sm:inline"> (06:00 - 06:00 WIB)</span>
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <div className="flex items-center bg-slate-100/90 rounded-full p-0.5 border border-slate-200/80 shadow-2xs">
            <button onClick={() => changeDate(-1)} className="p-1 sm:p-1.5 text-slate-500 hover:text-slate-800 hover:bg-white rounded-full transition-all cursor-pointer">
              <ChevronLeft size={16} />
            </button>
            <input 
              type="date" 
              className="bg-transparent border-none text-xs sm:text-sm font-semibold text-slate-700 focus:ring-0 px-1 sm:px-2 cursor-pointer outline-none w-[110px] sm:w-[130px] text-center"
              value={selectedDate}
              onChange={(e) => setSelectedDate(e.target.value)}
              max={format(new Date(), 'yyyy-MM-dd')}
            />
            <button onClick={() => changeDate(1)} className="p-1 sm:p-1.5 text-slate-500 hover:text-slate-800 hover:bg-white rounded-full transition-all cursor-pointer">
              <ChevronRight size={16} />
            </button>
          </div>
          <button 
            onClick={handleRefresh}
            className="p-1.5 sm:p-2 text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-full transition-colors border border-slate-200/80 shadow-2xs bg-white cursor-pointer"
            title="Refresh halaman"
          >
            <RefreshCw size={16} className={loading || boilerLoading ? "animate-spin" : ""} />
          </button>
          <ShareToChatButton
            reportPayload={{
              report_type: 'DAILY_REPORT',
              title: `Laporan Harian Pabrik • ${selectedDate}`,
              subtitle: `Periode 06:00 - 06:00 WIB`,
              metrics: {
                'Tanggal': selectedDate,
                'Total Batch': reportData?.total_processes != null ? `${reportData.total_processes} batch` : '-',
                'Steam Usage': reportData?.total_steam_usage != null ? `${reportData.total_steam_usage} kg` : '-',
                'OEE Gabungan': reportData?.oee_lite?.combined != null ? `${reportData.oee_lite.combined}%` : '-',
              },
              target_url: `/daily-report?date=${selectedDate}`,
            }}
            variant="outline"
            label="Bagikan"
          />
          <button
            onClick={handlePrint}
            className="hidden sm:flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-slate-200/90 bg-white hover:bg-slate-50 text-xs font-bold text-slate-700 shadow-2xs transition-all cursor-pointer"
            title="Print / Cetak Laporan"
          >
            <Printer size={15} className="text-slate-500" />
            <span>Cetak</span>
          </button>
        </div>
      </div>


      <div className="p-3 sm:p-6 max-w-7xl mx-auto space-y-4 sm:space-y-6">
        
        {/* Header khusus Print */}
        <div className="hidden print:block mb-4 pb-2 border-b-2 border-gray-800">
          <h1 className="text-2xl font-extrabold text-gray-900 tracking-tight">DAILY PRODUCTION REPORT</h1>
          <p className="text-sm text-gray-600 font-medium">Tanggal: {format(new Date(selectedDate), 'EEEE, dd MMM yyyy')} (06:00 - 06:00)</p>
        </div>

      {(loading && !reportData) ? (
        <div className="space-y-4 sm:space-y-6">
          {/* KPI 6 Cards Skeleton */}
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
            {[1, 2, 3, 4, 5, 6].map((i) => (
              <div key={i} className="bg-white rounded-2xl sm:rounded-3xl border border-slate-200/90 p-3.5 sm:p-4 shadow-xs flex flex-col justify-between min-h-[175px]">
                <div>
                  <div className="flex items-center gap-2">
                    <div className="w-7 h-7 rounded-full skeleton-shimmer shrink-0" />
                    <div className="w-20 h-3 rounded-md skeleton-shimmer" />
                  </div>
                  <div className="w-24 h-7 rounded-md skeleton-shimmer mt-2" />
                </div>
                <div className="mt-3.5 pt-2.5 border-t border-slate-100/90 space-y-1.5 min-h-[58px] flex flex-col justify-center">
                  <div className="w-full h-2 rounded-full skeleton-shimmer" />
                  <div className="w-3/4 h-2 rounded-full skeleton-shimmer" />
                </div>
              </div>
            ))}
          </div>

          {/* Losses Panel Skeleton */}
          <div className="bg-gradient-to-br from-amber-50/40 via-orange-50/20 to-white border border-amber-200/80 rounded-2xl p-4 shadow-2xs space-y-3">
            <div className="flex items-center gap-2">
              <div className="w-5 h-5 rounded-md skeleton-shimmer" />
              <div className="w-36 h-4 rounded skeleton-shimmer" />
            </div>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
              {[1, 2, 3, 4, 5, 6].map((i) => (
                <div key={i} className="bg-white rounded-xl border border-slate-200/80 p-3 flex flex-col gap-2.5 shadow-2xs">
                  <div className="flex items-center gap-2">
                    <div className="w-6 h-6 rounded-md skeleton-shimmer shrink-0" />
                    <div className="w-20 h-3 rounded skeleton-shimmer" />
                  </div>
                  <div className="w-16 h-5 rounded skeleton-shimmer mt-1" />
                </div>
              ))}
            </div>
          </div>

          {/* Boiler & Energy Section Skeleton */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <div className="lg:col-span-2 bg-white rounded-2xl border border-slate-200/90 p-4 shadow-2xs space-y-3">
              <div className="flex items-center justify-between">
                <div className="w-40 h-5 rounded skeleton-shimmer" />
                <div className="w-24 h-5 rounded-full skeleton-shimmer" />
              </div>
              <div className="h-[250px] rounded-xl skeleton-shimmer" />
            </div>
            <div className="bg-white rounded-2xl border border-slate-200/90 p-4 shadow-2xs space-y-3">
              <div className="w-32 h-5 rounded skeleton-shimmer" />
              <div className="space-y-2.5">
                {[1, 2, 3, 4].map((i) => (
                  <div key={i} className="h-10 rounded-xl skeleton-shimmer" />
                ))}
              </div>
            </div>
          </div>

          {/* Department Breakdown Skeleton */}
          <div className="bg-white rounded-2xl border border-slate-200/90 p-4 shadow-2xs space-y-3">
            <div className="flex items-center justify-between">
              <div className="w-48 h-5 rounded skeleton-shimmer" />
              <div className="w-28 h-6 rounded-full skeleton-shimmer" />
            </div>
            <div className="space-y-2">
              {[1, 2, 3, 4, 5].map((i) => (
                <div key={i} className="h-11 rounded-xl skeleton-shimmer" />
              ))}
            </div>
          </div>
        </div>
      ) : error ? (
        <div className="bg-red-50 border-l-4 border-red-500 p-4 rounded-r-xl"><div className="flex"><div className="flex-shrink-0"><AlertTriangle className="h-5 w-5 text-red-500" /></div><div className="ml-3"><h3 className="text-sm font-medium text-red-800">Gagal Memuat Laporan</h3><div className="mt-2 text-sm text-red-700"><p>{error}</p></div></div></div></div>
      ) : !reportData ? (
        <div className="text-center text-slate-400 py-10">Memuat atau data tidak tersedia...</div>
      ) : (
        <div className="space-y-4 sm:space-y-6 animate-fade-in">
          {/* ① ALERT BOILER CHIPS */}
          

          {/* ② KPI (6 kartu) */}
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
            {buildStory(reportData, boilerData).kpis.map(k => <KpiCard key={k.key} k={k} />)}
          </div>

          {/* 🔻 DATA LOSSES HARIAN PANEL */}
          {reportData?.losses_summary && (
            <div className="bg-white rounded-2xl sm:rounded-3xl border border-slate-200/80 p-4 sm:p-5 shadow-xs space-y-3.5 mb-4 mt-4">
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-xl bg-amber-50 text-amber-600 border border-amber-200/80 flex items-center justify-center shrink-0 shadow-2xs">
                    <TrendingDown className="w-4 h-4 text-amber-600" />
                  </div>
                  <div>
                    <h3 className="font-bold text-slate-900 text-sm sm:text-base leading-tight">Data Losses Harian</h3>
                    <p className="text-[11px] text-slate-400 font-medium">Rekapitulasi downtime, loss steam, dan energi hari ini</p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setSelectedLossCategory('time_loss')}
                  className="bg-sky-50 text-sky-600 hover:bg-sky-100 border border-sky-200/70 font-bold px-3 py-1 rounded-full text-xs shadow-2xs transition-all flex items-center gap-1 cursor-pointer"
                >
                  <span>Lihat Detail</span>
                  <ArrowRight className="w-3 h-3" />
                </button>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
                <LossCard 
                  title="Waktu Inefisiensi" 
                  value={reportData.losses_summary.time_loss_hours} 
                  unit="Jam" 
                  icon={<Clock size={16} />} 
                  onClick={() => setSelectedLossCategory('time_loss')}
                />
                <LossCard 
                  title="Downtime (Avail)" 
                  value={reportData.losses_summary.avail_loss_hours} 
                  unit="Jam" 
                  icon={<PowerOff size={16} />} 
                  onClick={() => setSelectedLossCategory('avail_loss')}
                />
                <LossCard 
                  title="Loss Steam" 
                  value={reportData.losses_summary.steam_loss_kg} 
                  unit="Kg" 
                  icon={<Flame size={16} />} 
                  onClick={() => setSelectedLossCategory('steam_loss')}
                />
                <LossCard 
                  title="Loss Listrik" 
                  value={reportData.losses_summary.power_loss_kwh} 
                  unit="kWh" 
                  icon={<Zap size={16} />} 
                  onClick={() => setSelectedLossCategory('power_loss')}
                />
                <LossCard 
                  title="Energi Angin" 
                  value={null}
                  unit="Coming Soon" 
                  icon={<Wind size={16} />} 
                  disabled 
                />
                <LossCard 
                  title="SFC (Batu Bara)" 
                  value={boilerData?.kpi_summary?.specific_fuel_consumption} 
                  unit="Ratio" 
                  icon={<Gauge size={16} />} 
                  onClick={() => setSelectedLossCategory('sfc_loss')}
                />
              </div>
            </div>
          )}

          {/* ③ STEAM & TEKANAN 24 JAM & ④ BOILER SNAPSHOT */}
          <div ref={boilerSectionRef} className="grid lg:grid-cols-3 gap-4">
            <div className="lg:col-span-2 bg-gradient-to-br from-white to-slate-50/50 rounded-2xl border border-slate-200/90 shadow-2xs p-4 sm:p-5">
                <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-4 gap-2">
                  <h2 className="text-sm font-bold text-gray-800 flex items-center gap-2"><Flame size={16} className="text-orange-500" /> Analitik Energi & Mesin (24 Jam)</h2>
                  <div className="flex rounded-md shadow-sm" role="group">
                    {Object.keys(CHART_MODES).map((mode) => (
                      <button
                        key={mode}
                        onClick={() => setChartViewMode(mode)}
                        type="button"
                        className={`px-3 py-1.5 text-xs font-medium border ${
                          chartViewMode === mode
                            ? 'bg-blue-50 text-blue-700 border-blue-200 z-10'
                            : 'bg-white text-gray-700 border-gray-200 hover:bg-gray-50'
                        } ${mode === 'steam' ? 'rounded-l-lg' : ''} ${mode === 'power' ? 'rounded-r-lg' : ''} ${mode === 'hto' ? '-ml-px' : ''} ${mode === 'power' ? '-ml-px' : ''}`}
                      >
                        {CHART_MODES[mode].label}
                      </button>
                    ))}
                  </div>
                </div>
                
                <div className="h-[250px]">
                  {boilerLoading ? <div className="animate-pulse h-full bg-gray-100 rounded"></div> : boilerData ? (
                    <ResponsiveContainer width="100%" height="100%">
                      <ComposedChart data={buildSteamChart(boilerData).data} key={chartViewMode} margin={{ top: 8, right: 12, left: 10, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f3f4f6" />
                        <XAxis dataKey="time" minTickGap={30} tick={{ fontSize: 11, fill: '#9ca3af' }} axisLine={false} tickLine={false} />
                        
                        <YAxis 
                          yAxisId="left" 
                          width={48}
                          tick={{ fontSize: 11, fill: CHART_MODES[chartViewMode].area.stroke }} 
                          axisLine={false} 
                          tickLine={false}
                          tickFormatter={(v) => {
                            if (v >= 1000000) return `${(v / 1000000).toFixed(1)}M`;
                            if (v >= 1000) return `${Math.round(v / 1000)}k`;
                            return v;
                          }}
                        />
                        <YAxis 
                          yAxisId="right" 
                          width={36}
                          orientation="right" 
                          domain={CHART_MODES[chartViewMode].line.domain} 
                          allowDecimals={!CHART_MODES[chartViewMode].line.integer} 
                          tick={{ fontSize: 11, fill: CHART_MODES[chartViewMode].line.stroke }} 
                          axisLine={false} 
                          tickLine={false} 
                        />
                        
                        <RechartsTooltip 
                          contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)', fontSize: '12px' }} 
                          formatter={(value, name) => [typeof value === 'number' ? value.toLocaleString('id-ID') : value, name]}
                        />
                        
                        <Area yAxisId="left" type="monotone" dataKey={CHART_MODES[chartViewMode].area.key} stroke={CHART_MODES[chartViewMode].area.stroke} fill={CHART_MODES[chartViewMode].area.fill} fillOpacity={0.5} name={CHART_MODES[chartViewMode].area.name} connectNulls={false} />
                        <Line yAxisId="right" type={CHART_MODES[chartViewMode].line.step ? 'stepAfter' : 'monotone'} dataKey={CHART_MODES[chartViewMode].line.key} stroke={CHART_MODES[chartViewMode].line.stroke} dot={false} strokeWidth={2} name={CHART_MODES[chartViewMode].line.name} connectNulls={false} />
                        
                        {chartViewMode === 'steam' && buildSteamChart(boilerData).marks.map((m, i) => (
                          <ReferenceLine key={i} yAxisId="left" x={m.time} stroke="#ef4444" strokeDasharray="3 3" />
                        ))}
                      </ComposedChart>
                    </ResponsiveContainer>
                  ) : <div className="h-full flex items-center justify-center text-gray-400">Data boiler tidak tersedia</div>}
                </div>
              </div>
            
            <div className="bg-gradient-to-br from-white to-slate-50/50 rounded-2xl border border-slate-200/90 shadow-2xs p-4 sm:p-5">
               <h2 className="text-sm font-bold text-gray-800 mb-4">Boiler Snapshot</h2>
               {boilerLoading ? <div className="animate-pulse h-32 bg-gray-100 rounded"></div> : boilerData ? (
                 <div className="space-y-4">
                    <div className="grid grid-cols-2 gap-2">
                       <div className="p-2 bg-gray-50 rounded text-center">
                          <div className="text-[10px] text-gray-500 uppercase">Avg Tekanan</div>
                          <div className="font-bold">{boilerData.kpi_summary?.avg_pressure ?? '—'} <span className="text-xs font-normal">bar</span></div>
                       </div>
                       <div className="p-2 bg-gray-50 rounded text-center">
                          <div className="text-[10px] text-gray-500 uppercase">Avg Suhu Oli</div>
                          <div className="font-bold">{boilerData.kpi_summary?.avg_oil_temp ?? '—'} <span className="text-xs font-normal">°C</span></div>
                       </div>
                    </div>
                    {(() => {
                        const totalDist = (boilerData.pressure_dist?.under || 0) + (boilerData.pressure_dist?.ideal || 0) + (boilerData.pressure_dist?.over || 0) || 288;
                        const pUnder = Math.round(((boilerData.pressure_dist?.under || 0) / totalDist) * 100);
                        const pIdeal = Math.round(((boilerData.pressure_dist?.ideal || 0) / totalDist) * 100);
                        const pOver = Math.round(((boilerData.pressure_dist?.over || 0) / totalDist) * 100);
                        return (
                          <div className="p-3 bg-gray-50 rounded border border-gray-100">
                              <div className="text-xs text-gray-500 mb-2 text-center font-semibold">Distribusi Tekanan</div>
                              <div className="flex justify-between text-[10px] font-bold mb-1.5 px-1">
                                <span className="text-yellow-600">{pUnder}% Under</span>
                                <span className="text-green-600">{pIdeal}% Ideal</span>
                                <span className="text-red-600">{pOver}% Over</span>
                              </div>
                              <div className="flex h-2.5 rounded-full overflow-hidden shadow-inner">
                                 <div className="bg-yellow-400" style={{ width: `${pUnder}%` }} title="Under"></div>
                                 <div className="bg-green-500" style={{ width: `${pIdeal}%` }} title="Ideal"></div>
                                 <div className="bg-red-500" style={{ width: `${pOver}%` }} title="Over"></div>
                              </div>
                          </div>
                        );
                    })()}

                    {/* Boiler Alerts Inside Snapshot */}
                    <div className="pt-3 mt-1 border-t border-gray-100">
                        {(() => {
                            const story = buildStory(reportData, boilerData);
                            return <AlertChips alerts={story.alerts} />;
                        })()}
                    </div>
                 </div>
               ) : <div className="text-sm text-gray-400 text-center py-6">Data tidak tersedia</div>}
            </div>
          </div>

          {/* ⑤ TIMELINE & ⑥ PARETO */}
          <div className="grid lg:grid-cols-3 gap-4">
            <div className="lg:col-span-2 bg-gradient-to-br from-white to-slate-50/50 rounded-2xl border border-slate-200/90 shadow-2xs p-4 sm:p-5 overflow-hidden">
              <h2 className="text-sm font-bold text-gray-800 mb-4 flex items-center gap-2"><Clock size={16} className="text-blue-500"/> Timeline Mesin</h2>
              <div className="max-h-[300px] overflow-y-auto pr-2 space-y-4 custom-scrollbar">
                {(reportData.availability_groups ?? []).map(g => (
                  <div key={g.group_name}>
                    <div className="text-[11px] font-bold text-gray-400 mb-1">{g.group_name}</div>
                    {g.machines.map(m => (
                       <AvailabilityBar key={m.machine_id} machine={m} onMachineClick={openDailyChartModal} />
                    ))}
                  </div>
                ))}
              </div>
            </div>
            
            <div className="bg-gradient-to-br from-white to-slate-50/50 rounded-2xl border border-slate-200/90 shadow-2xs p-4 sm:p-5 overflow-hidden">
               <h2 className="text-sm font-bold text-gray-800 mb-4 flex items-center gap-2"><AlertTriangle size={16} className="text-red-500"/> Pareto Penyebab Loss</h2>
               <div className="max-h-[300px] overflow-y-auto pr-2 custom-scrollbar">
                 <div className="space-y-3">
                   {(reportData.efficiency_problems?.categories ?? []).map(cat => {
                     const maxCount = Math.max(1, ...(reportData.efficiency_problems.categories.map(c => c.count)));
                     const w = Math.max(5, (cat.count / maxCount) * 100);
                     const colorClass = cat.color === 'red' ? 'bg-red-500' : cat.color === 'orange' ? 'bg-orange-500' : cat.color === 'blue' ? 'bg-blue-500' : 'bg-gray-500';
                     return (
                       <div key={cat.code} className="cursor-pointer group" onClick={() => openProblemModal(cat)}>
                         <div className="flex justify-between text-xs mb-1">
                           <span className="font-medium text-gray-700 group-hover:text-blue-600 transition-colors">{cat.label}</span>
                           <span className="font-bold text-gray-900">{cat.count}</span>
                         </div>
                         <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                           <div className={`h-full rounded-full ${colorClass}`} style={{ width: `${w}%` }}></div>
                         </div>
                       </div>
                     );
                   })}
                 </div>
               </div>
            </div>
          </div>

          {/* ⑦ PAPAN MESIN */}
          <div className="bg-white rounded-2xl sm:rounded-3xl border border-slate-200/80 shadow-xs overflow-hidden">
                          <div className="p-4 border-b border-gray-100 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
               <h2 className="text-sm font-bold text-gray-800 flex items-center gap-2"><Activity size={16} className="text-indigo-500"/> Papan Mesin</h2>
               <div className="flex gap-2 text-[11px] sm:text-xs">
                 <button className={`px-3 py-1.5 rounded-full ${boardMode==='mode1'?'bg-indigo-500 text-white font-medium':'bg-gray-100 text-gray-600 hover:bg-gray-200'} transition-colors`} onClick={() => setBoardMode('mode1')}>Energi & Efisiensi</button>
                 <button className={`px-3 py-1.5 rounded-full ${boardMode==='mode2'?'bg-indigo-500 text-white font-medium':'bg-gray-100 text-gray-600 hover:bg-gray-200'} transition-colors`} onClick={() => setBoardMode('mode2')}>Rupiah & Loss</button>
                 <button className={`px-3 py-1.5 rounded-full ${boardMode==='mode3'?'bg-indigo-500 text-white font-medium':'bg-gray-100 text-gray-600 hover:bg-gray-200'} transition-colors`} onClick={() => setBoardMode('mode3')}>Cost / Output</button>
               </div>
              </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm text-left">
                <thead className="bg-gray-50 text-gray-500 text-[11px] uppercase">
                  <tr>
                    <th className="px-4 py-3 font-semibold">Mesin</th>
                    <th className="px-4 py-3 font-semibold text-center">Batch</th>
                    <th className="px-4 py-3 font-semibold text-right">Availability</th>
                    <th className="px-4 py-3 font-semibold text-right">Efisiensi</th>
                    <th className="px-4 py-3 font-semibold text-right">OEE</th>
                      <th className="px-4 py-3 font-semibold text-right border-r border-gray-200">Total Loss Time</th>
                      {boardMode === 'mode1' && (
                        <>
                          <th className="px-4 py-3 font-semibold text-right">Steam Usage</th>
                          <th className="px-4 py-3 font-semibold text-right">Steam Eff</th>
                          <th className="px-4 py-3 font-semibold text-right">% Sehat</th>
                          <th className="px-4 py-3 font-semibold text-right">Listrik</th>
                          <th className="px-4 py-3 font-semibold text-right">Listrik Eff</th>
                        </>
                      )}
                      
                      {boardMode === 'mode2' && (
                        <>
                          <th className="px-4 py-3 font-semibold text-right">Steam Loss (kg)</th>
                          <th className="px-4 py-3 font-semibold text-right">Steam Loss (Rp)</th>
                          <th className="px-4 py-3 font-semibold text-right">Listrik LWBP (Rp)</th>
                          <th className="px-4 py-3 font-semibold text-right">Listrik WBP (Rp)</th>
                          <th className="px-4 py-3 font-semibold text-right">Listrik Loss (Rp)</th>
                        </>
                      )}
                      
                      {boardMode === 'mode3' && (
                        <>
                          <th className="px-4 py-3 font-semibold text-right">Output (yd)</th>
                          <th className="px-4 py-3 font-semibold text-right">Steam Cost/yd</th>
                          <th className="px-4 py-3 font-semibold text-right">Listrik Cost/yd</th>
                          <th className="px-4 py-3 font-semibold text-right">Total Cost/yd</th>
                        </>
                      )}
                      <th className="px-4 py-3 font-semibold text-center border-l border-gray-200">Aksi</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {buildBoard(reportData).map(r => (
                    <tr key={r.id} className="hover:bg-gray-50 transition-colors">
                      <td className="px-4 py-3 font-bold text-gray-800">{r.name}</td>
                      <td className="px-4 py-3 text-center font-medium text-gray-600">{r.batch ?? '—'}</td>
                      <td className="px-4 py-3 text-right">
                        <span className={`inline-flex items-center gap-1.5 font-bold ${r.availTone==='bad'?'bg-rose-50 text-rose-700 border-rose-200/80':r.availTone==='warn'?'bg-amber-50 text-amber-700 border-amber-200/80':'bg-emerald-50 text-emerald-700 border-emerald-200/80'} border px-2.5 py-0.5 rounded-full text-xs font-bold`}>
                          {r.avail != null ? `${num(r.avail)}%` : '—'}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <span className={`inline-flex px-2 py-0.5 rounded font-bold ${r.effTone==='bad'?'bg-rose-50 text-rose-700 border-rose-200/80':r.effTone==='warn'?'bg-amber-50 text-amber-700 border-amber-200/80':'bg-emerald-50 text-emerald-700 border-emerald-200/80'} border px-2.5 py-0.5 rounded-full text-xs font-bold`}>
                          {r.eff != null ? `${num(r.eff)}%` : '—'}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right">
                          <span className={`inline-flex px-2 py-0.5 rounded font-bold ${r.oeeTone==='bad'?'bg-rose-50 text-rose-700 border-rose-200/80':r.oeeTone==='warn'?'bg-amber-50 text-amber-700 border-amber-200/80':'bg-emerald-50 text-emerald-700 border-emerald-200/80'} border px-2.5 py-0.5 rounded-full text-xs font-bold`}>
                            {r.oee != null ? `${num(r.oee)}%` : '-'}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-right font-medium text-gray-600 border-r border-gray-200">{r.loss ?? '-'}</td>
                          
                          {boardMode === 'mode1' && (
                            <>
                              <td className="px-4 py-3 text-right font-medium text-gray-600">{r.steamUsage != null ? `${num(r.steamUsage)} kg` : '-'}</td>
                              <td className="px-4 py-3 text-right">
                                <span className={`inline-flex px-2 py-0.5 rounded font-bold ${r.steamEffTone==='bad'?'bg-rose-50 text-rose-700 border-rose-200/80':r.steamEffTone==='warn'?'bg-amber-50 text-amber-700 border-amber-200/80':r.steamEffTone==='ok'?'bg-emerald-50 text-emerald-700 border-emerald-200/80':'bg-slate-50 text-slate-700 border-slate-200/80'} border px-2.5 py-0.5 rounded-full text-xs font-bold`}>
                                  {r.steamEff != null ? `${num(r.steamEff)}%` : '-'}
                                </span>
                              </td>
                              <td className="px-4 py-3 text-right">
                                <span className={`inline-flex px-2 py-0.5 rounded font-bold ${r.steamOkTone==='bad'?'bg-rose-50 text-rose-700 border-rose-200/80':r.steamOkTone==='warn'?'bg-amber-50 text-amber-700 border-amber-200/80':r.steamOkTone==='ok'?'bg-emerald-50 text-emerald-700 border-emerald-200/80':'bg-slate-50 text-slate-700 border-slate-200/80'} border px-2.5 py-0.5 rounded-full text-xs font-bold`}>
                                  {r.steamOk != null ? `${num(r.steamOk)}%` : '-'}
                                </span>
                              </td>
                              <td className="px-4 py-3 text-right font-medium text-gray-600">{r.powerUsage != null ? `${num(r.powerUsage)} kWh` : '-'}</td>
                              <td className="px-4 py-3 text-right">
                                <span className={`inline-flex px-2 py-0.5 rounded font-bold ${r.powerEffTone==='bad'?'bg-rose-50 text-rose-700 border-rose-200/80':r.powerEffTone==='warn'?'bg-amber-50 text-amber-700 border-amber-200/80':r.powerEffTone==='ok'?'bg-emerald-50 text-emerald-700 border-emerald-200/80':'bg-slate-50 text-slate-700 border-slate-200/80'} border px-2.5 py-0.5 rounded-full text-xs font-bold`}>
                                  {r.powerEff != null ? `${num(r.powerEff)}%` : '-'}
                                </span>
                              </td>
                            </>
                          )}
                          
                          {boardMode === 'mode2' && (
                            <>
                              <td className="px-4 py-3 text-right font-medium text-gray-600">{r.steamLossKg != null ? `${num(r.steamLossKg)} kg` : '-'}</td>
                              <td className="px-4 py-3 text-right font-bold text-red-600">{r.steamLossRp != null ? `Rp ${num(r.steamLossRp)}` : '-'}</td>
                              <td className="px-4 py-3 text-right font-medium text-gray-600">{r.powerLwbpRp != null ? `Rp ${num(r.powerLwbpRp)}` : '-'}</td>
                              <td className="px-4 py-3 text-right font-medium text-orange-600">{r.powerWbpRp != null ? `Rp ${num(r.powerWbpRp)}` : '-'}</td>
                              <td className="px-4 py-3 text-right font-bold text-red-600">{r.powerLossRp != null ? `Rp ${num(r.powerLossRp)}` : '-'}</td>
                            </>
                          )}
                          
                          {boardMode === 'mode3' && (
                            <>
                              <td className="px-4 py-3 text-right font-medium text-gray-600">{r.outputYd != null ? num(r.outputYd) : '-'}</td>
                              <td className="px-4 py-3 text-right font-medium text-gray-600">{r.steamCostPerYd != null ? `Rp ${num(r.steamCostPerYd)}` : '-'}</td>
                              <td className="px-4 py-3 text-right font-medium text-gray-600">{r.powerCostPerYd != null ? `Rp ${num(r.powerCostPerYd)}` : '-'}</td>
                              <td className="px-4 py-3 text-right font-bold text-indigo-600">{r.totalCostPerYd != null ? `Rp ${num(r.totalCostPerYd)}` : '-'}</td>
                            </>
                          )}
                          
                          <td className="px-4 py-3 text-center border-l border-gray-200">
                          <button onClick={() => openDailyChartModal(r.id)} className="text-[#0066fe] hover:text-blue-800 font-bold px-2.5 py-0.5 rounded-full hover:bg-blue-50 transition-colors text-xs cursor-pointer">
                          Grafik
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* ⑧ SARAN TINDAKAN */}
          <div className="rounded-xl border border-dashed border-gray-300 bg-gray-50 p-6 text-sm text-gray-500 text-center flex flex-col items-center justify-center">
             <div className="w-10 h-10 bg-white rounded-full flex items-center justify-center shadow-sm mb-2 border border-gray-100">🚧</div>
             <b className="text-gray-700">Saran Tindakan</b>
             <p className="mt-1">Fitur cerdas ini sedang dalam pengerjaan (Coming Soon).</p>
          </div>
        </div>
      )}
      </div>

      {/* Modal Daily Chart */}
      {isDailyModalOpen && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-2 sm:p-4 bg-black bg-opacity-50 backdrop-blur-sm">
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-[95%] lg:max-w-4xl overflow-hidden flex flex-col max-h-[90vh]">
            <div className="flex justify-between items-center p-4 sm:p-6 border-b border-gray-100">
              <div>
                <h3 className="text-lg sm:text-xl font-bold text-gray-800">
                  {dailyChartDetail ? `Grafik Harian: ${dailyChartDetail.machine_name}` : 'Memuat grafik...'}
                </h3>
                {dailyChartDetail && <p className="text-sm text-gray-500 mt-1">Periode: {dailyChartDetail.date_range}</p>}
              </div>
              <button onClick={closeModal} className="text-gray-400 hover:text-gray-600 transition-colors p-1 rounded-full hover:bg-gray-100">
                <X size={24} />
              </button>
            </div>
            <div className="p-4 sm:p-6 overflow-y-auto">
              {!dailyChartDetail ? (
                <div className="flex justify-center items-center h-64">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
                </div>
              ) : (
                <div className="h-[300px] sm:h-[400px] w-full">
                  <ResponsiveContainer width="100%" height="100%" minHeight={1} minWidth={1}>
                    <LineChart data={dailyChartDetail.chart_data} margin={{ top: 20, right: 30, left: -20, bottom: 5 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" vertical={false} />
                      <XAxis dataKey="time" tick={{ fontSize: 12, fill: '#6b7280' }} axisLine={false} tickLine={false} interval="preserveStartEnd" minTickGap={30} />
                      <YAxis yAxisId="left"  tick={{ fontSize: 12, fill: '#6b7280' }} axisLine={false} tickLine={false} />
                      <YAxis yAxisId="right" orientation="right" domain={[0, 5]} tick={{ fontSize: 12, fill: '#6b7280' }} axisLine={false} tickLine={false} />
                      <RechartsTooltip contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }} />
                      <Line yAxisId="left"  type="monotone" dataKey="temp"     stroke="#ef4444" strokeWidth={2} dot={false} name="Suhu (°C)" />
                      <Line yAxisId="right" type="monotone" dataKey="pressure" stroke="#8b5cf6" strokeWidth={2} dot={false} name="Tekanan (bar)" />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Modal Process Analytics (Compact UI) */}
      {isProcessModalOpen && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-2 sm:p-4 bg-black bg-opacity-50 backdrop-blur-sm">
          <div className="bg-gray-50 rounded-xl shadow-2xl w-full max-w-[95%] lg:max-w-5xl overflow-hidden flex flex-col max-h-[95vh] text-sm">
            
            {/* Header Modal */}
            <div className="flex justify-between items-center p-3 sm:p-4 bg-white border-b border-gray-100 shrink-0">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-full bg-blue-50 text-blue-600 flex items-center justify-center font-bold">
                  {processAnalyticsDetail ? processAnalyticsDetail.machine_name.charAt(0) : <Activity className="animate-spin w-4 h-4" />}
                </div>
                <div>
                  <h3 className="text-base sm:text-lg font-bold text-gray-800 leading-tight">
                    {processAnalyticsDetail ? processAnalyticsDetail.machine_name : 'Memuat data...'}
                  </h3>
                  {processAnalyticsDetail && (
                    <p className="text-xs text-gray-500">Batch #{processAnalyticsDetail.batch_number}</p>
                  )}
                </div>
              </div>
              <button onClick={closeProcessModal} className="text-gray-400 hover:text-gray-600 transition-colors p-1 rounded-full hover:bg-gray-100">
                <X size={20} />
              </button>
            </div>

            {/* Modal Content */}
            <div className="p-4 sm:p-6 overflow-y-auto overflow-x-hidden flex-1 space-y-4 sm:space-y-6">
              {processModalError ? (
                <div className="flex flex-col items-center justify-center h-64 text-center p-6">
                  <div className="w-12 h-12 rounded-full bg-rose-50 text-rose-500 flex items-center justify-center mb-3">
                    <X size={24} />
                  </div>
                  <p className="text-sm font-semibold text-slate-800 mb-1">{processModalError}</p>
                  <p className="text-xs text-slate-500 mb-4">Terjadi kendala saat mengambil analitik proses.</p>
                  <button
                    type="button"
                    onClick={() => selectedProcessId && openProcessAnalyticsModal(selectedProcessId)}
                    className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-semibold shadow-sm transition-colors"
                  >
                    Coba Lagi
                  </button>
                </div>
              ) : !processAnalyticsDetail ? (
                <div className="flex justify-center items-center h-64">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
                </div>
              ) : (
                <>
                  {/* Identity & KPI (Compact 2 columns on desktop) */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    
                    {/* Identity Panel */}
                    <div className="bg-white rounded-lg border border-gray-100 p-3 sm:p-4 flex flex-col justify-center shadow-sm">
                      <div className="grid grid-cols-2 gap-x-2 gap-y-2 text-xs sm:text-sm">
                        <div><span className="text-gray-400 block mb-0.5">Order/Warna</span><span className="font-semibold text-gray-700">{processAnalyticsDetail.identity.nomor_order} / {processAnalyticsDetail.identity.nomor_warna}</span></div>
                        <div><span className="text-gray-400 block mb-0.5">Artikel</span><span className="font-semibold text-gray-700 truncate block">{processAnalyticsDetail.identity.artikel_kain}</span></div>
                        <div><span className="text-gray-400 block mb-0.5">Batch Kain</span><span className="font-semibold text-gray-700">{processAnalyticsDetail.identity.batch}</span></div>
                        <div><span className="text-gray-400 block mb-0.5">Program</span><span className="font-semibold text-indigo-600 truncate block">{processAnalyticsDetail.identity.program}</span></div>
                        <div><span className="text-gray-400 block mb-0.5">Operator</span><span className="font-semibold text-gray-700">{processAnalyticsDetail.identity.operator}</span></div>
                        <div><span className="text-gray-400 block mb-0.5 text-xs sm:text-sm uppercase tracking-wider">Waktu Proses</span><span className="font-semibold text-gray-800">{formatBackendDate(processAnalyticsDetail.identity.heat_start_time)} - {formatBackendDate(processAnalyticsDetail.identity.end_time)}</span></div>
                      </div>
                    </div>

                    {/* KPI Panel */}
                    <div className="grid grid-cols-4 gap-2">
                      <div className="bg-white rounded-lg border border-gray-100 flex flex-col items-center justify-center p-2 text-center shadow-sm">
                        <span className="text-xs sm:text-sm text-gray-500 font-medium mb-0.5">Durasi Aktual</span>
                        <span className="text-base sm:text-lg font-bold text-gray-800">{processAnalyticsDetail.kpi.duration_effective || '-'}m</span>
                      </div>
                      <div className="bg-white rounded-lg border border-gray-100 flex flex-col items-center justify-center p-2 text-center shadow-sm">
                        <span className="text-xs sm:text-sm text-gray-500 font-medium mb-0.5">Durasi Ideal</span>
                        <span className="text-base sm:text-lg font-bold text-gray-800">{processAnalyticsDetail.timing.total_ideal || '-'}m</span>
                      </div>
                      <div className={`rounded-lg border flex flex-col items-center justify-center p-2 text-center shadow-sm ${processAnalyticsDetail.kpi.efficiency >= 80 ? 'bg-green-50 border-green-100 text-green-700' : processAnalyticsDetail.kpi.efficiency >= 60 ? 'bg-yellow-50 border-yellow-100 text-yellow-700' : 'bg-red-50 border-red-100 text-red-700'}`}>
                        <span className="text-xs sm:text-sm font-medium mb-0.5 opacity-80">Efisiensi</span>
                        <span className="text-lg sm:text-xl font-extrabold">{processAnalyticsDetail.kpi.efficiency ? processAnalyticsDetail.kpi.efficiency + '%' : '-'}</span>
                      </div>
                      <div className="bg-white rounded-lg border border-gray-100 flex flex-col items-center justify-center p-2 text-center shadow-sm">
                        <span className="text-xs sm:text-sm text-gray-500 font-medium mb-0.5">Loss Time</span>
                        <span className={`text-base sm:text-lg font-bold ${(processAnalyticsDetail.kpi.loss_time || 0) > 0 ? 'text-red-600' : 'text-gray-800'}`}>
                          {processAnalyticsDetail.kpi.loss_time ? `+${processAnalyticsDetail.kpi.loss_time}m` : '-'}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Phase Breakdown Progress Bar */}
                  {Object.keys(processAnalyticsDetail.phase_breakdown).length > 0 && (
                    <div className="bg-white rounded-lg border border-gray-100 p-3">
                      <div className="flex justify-between items-end mb-1">
                        <span className="text-sm font-bold text-gray-700">Phase Breakdown</span>
                        <div className="flex gap-3 text-xs">
                          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-red-400"></span>Heat ({processAnalyticsDetail.phase_breakdown.heat || 0}%)</span>
                          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-orange-400"></span>Hold ({processAnalyticsDetail.phase_breakdown.hold || 0}%)</span>
                          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-blue-400"></span>Cool ({processAnalyticsDetail.phase_breakdown.cooling || 0}%)</span>
                        </div>
                      </div>
                      <div className="w-full h-3 flex rounded-full overflow-hidden bg-gray-100">
                        <div style={{ width: `${processAnalyticsDetail.phase_breakdown.heat || 0}%` }} className="bg-red-400 h-full" />
                        <div style={{ width: `${processAnalyticsDetail.phase_breakdown.hold || 0}%` }} className="bg-orange-400 h-full" />
                        <div style={{ width: `${processAnalyticsDetail.phase_breakdown.cooling || 0}%` }} className="bg-blue-400 h-full" />
                      </div>
                    </div>
                  )}

                  {/* Chart and Timing details row */}
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                    {/* Chart */}
                    <div className="md:col-span-2 bg-white rounded-lg border border-gray-100 p-3">
                       <h4 className="text-sm font-bold text-gray-700 mb-2">Profil Suhu & Tekanan</h4>
                       <div className="h-[200px] w-full">
                         <ResponsiveContainer width="100%" height="100%" minHeight={1} minWidth={1}>
                           <LineChart data={processAnalyticsDetail.chart_data} margin={{ top: 5, right: 0, left: -25, bottom: 0 }}>
                             <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" vertical={false} />
                             <XAxis dataKey="time" tick={{ fontSize: 12, fill: '#9ca3af' }} axisLine={false} tickLine={false} interval="preserveStartEnd" minTickGap={20} />
                             <YAxis yAxisId="left" tick={{ fontSize: 12, fill: '#9ca3af' }} axisLine={false} tickLine={false} />
                             <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 12, fill: '#9ca3af' }} axisLine={false} tickLine={false} domain={[0, 5]} />
                             <RechartsTooltip contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)', fontSize: '12px' }} formatter={(value) => parseFloat(value).toFixed(2)} />
                             <Line yAxisId="left" type="monotone" dataKey="temp" stroke="#ef4444" strokeWidth={2} dot={false} name="Suhu (°C)" />
                             <Line yAxisId="right" type="monotone" dataKey="pressure" stroke="#8b5cf6" strokeWidth={2} dot={false} name="Steam (bar)" />
                           </LineChart>
                         </ResponsiveContainer>
                       </div>
                    </div>
                    
                    {/* Timing details */}
                    <div className="bg-white rounded-lg border border-gray-100 p-3">
                       <h4 className="text-sm font-bold text-gray-700 mb-2">Detail Fase</h4>
                       <div className="space-y-2">
                         <div className="flex justify-between items-center bg-gray-50 p-2 rounded text-sm">
                           <span className="text-gray-500">Heating</span>
                           <span className="font-medium text-gray-800">{processAnalyticsDetail.timing.heat_actual || 0}m <span className="text-gray-400 text-xs ml-1">(Ideal: {processAnalyticsDetail.timing.heat_ideal || 0}m)</span></span>
                         </div>
                         <div className="flex justify-between items-center bg-gray-50 p-2 rounded text-sm">
                           <span className="text-gray-500">Holding</span>
                           <span className="font-medium text-gray-800">{processAnalyticsDetail.timing.hold_actual || 0}m <span className="text-gray-400 text-xs ml-1">(Ideal: {processAnalyticsDetail.timing.keep_ideal || 0}m)</span></span>
                         </div>
                         <div className="flex justify-between items-center bg-gray-50 p-2 rounded text-sm">
                           <span className="text-gray-500">Cooling</span>
                           <span className="font-medium text-gray-800">{processAnalyticsDetail.timing.cool_actual || 0}m <span className="text-gray-400 text-xs ml-1">(Ideal: {processAnalyticsDetail.timing.cool_ideal || 0}m)</span></span>
                         </div>
                         <div className="pt-2 border-t border-gray-100 flex justify-between items-center text-sm">
                           <span className="text-gray-500">Max Temp</span>
                           <span className="font-bold text-red-500">
                             {processAnalyticsDetail.timing.peak_temp || '-'}°C 
                             <span className="text-gray-400 text-xs ml-1 font-normal">(Ideal: {processAnalyticsDetail.timing.max_temp_prg || '-'}°C)</span>
                           </span>
                         </div>
                       </div>
                    </div>
                  </div>

                  {/* Masalah / Catatan */}
                  {processAnalyticsDetail.identity.masalah && (
                    <div className="bg-red-50 rounded-lg border border-red-100 p-3">
                      <h4 className="text-sm font-bold text-red-800 mb-1">Catatan / Masalah</h4>
                      <p className="text-sm text-red-600">{processAnalyticsDetail.identity.masalah}</p>
                    </div>
                  )}
                  {processAnalyticsDetail.identity.keterangan && (
                    <div className="bg-blue-50 rounded-lg border border-blue-100 p-3">
                      <h4 className="text-sm font-bold text-blue-800 mb-1">Keterangan</h4>
                      <p className="text-sm text-blue-600">{processAnalyticsDetail.identity.keterangan}</p>
                    </div>
                  )}

                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── DATA LOSSES HARIAN BREAKDOWN MODAL ────────────────────── */}
      <LossesBreakdownModal
        isOpen={!!selectedLossCategory}
        onClose={() => setSelectedLossCategory(null)}
        categoryKey={selectedLossCategory}
        reportData={reportData}
        boilerData={boilerData}
        selectedDate={selectedDate}
      />

      {/* ── EFFICIENCY PROBLEM DETAILS MODAL ──────────────────────── */}
      {isProblemModalOpen && selectedProblemCategory && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-2 sm:p-4 bg-black/60 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-6xl max-h-[95vh] overflow-hidden flex flex-col border border-gray-100">
            {/* Header */}
            <div className={`px-4 sm:px-6 py-4 flex justify-between items-center ${
                selectedProblemCategory.color === 'red' ? 'bg-red-50 border-b border-red-100' :
                selectedProblemCategory.color === 'orange' ? 'bg-orange-50 border-b border-orange-100' :
                selectedProblemCategory.color === 'blue' ? 'bg-blue-50 border-b border-blue-100' :
                selectedProblemCategory.color === 'purple' ? 'bg-purple-50 border-b border-purple-100' :
                'bg-gray-50 border-b border-gray-100'
              }`}
            >
              <div>
                <h3 className={`text-lg sm:text-xl font-bold flex items-center gap-2 ${
                  selectedProblemCategory.color === 'red' ? 'text-red-800' :
                  selectedProblemCategory.color === 'orange' ? 'text-orange-800' :
                  selectedProblemCategory.color === 'blue' ? 'text-blue-800' :
                  selectedProblemCategory.color === 'purple' ? 'text-purple-800' :
                  'text-gray-800'
                }`}>
                  <AlertTriangle size={20} />
                  Problem: {selectedProblemCategory.label}
                </h3>
                <p className="text-sm text-gray-500 mt-1">
                  Menampilkan {selectedProblemCategory.processes.length} proses pada tanggal ini.
                </p>
              </div>
              <button 
                onClick={closeProblemModal}
                className="p-2 hover:bg-black/5 rounded-full transition-colors"
              >
                <X size={24} className="text-gray-500" />
              </button>
            </div>

            {/* Content Table */}
            <div className="flex-1 overflow-auto p-4 sm:p-6 bg-gray-50/50">
              <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-100 text-sm">
                  <thead className="bg-gray-50 sticky top-0">
                    <tr>
                      <th className="px-4 py-3 text-left font-semibold text-gray-600">Mesin</th>
                      <th className="px-4 py-3 text-left font-semibold text-gray-600">Batch</th>
                      <th className="px-4 py-3 text-left font-semibold text-gray-600">Mulai</th>
                      <th className="px-4 py-3 text-left font-semibold text-gray-600">Selesai</th>
                      <th className="px-4 py-3 text-right font-semibold text-gray-600">Total Durasi</th>
                      <th className="px-4 py-3 text-right font-semibold text-gray-600">Eff. Total</th>
                      <th className="px-4 py-3 text-right font-semibold text-orange-600">Delay Heat</th>
                      <th className="px-4 py-3 text-right font-semibold text-blue-600">Delay Cool</th>
                      <th className="px-4 py-3 text-right font-semibold text-red-600">Delay Total</th>
                      <th className="px-4 py-3 text-center font-semibold text-gray-600">Aksi</th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-gray-50">
                    {selectedProblemCategory.processes.map((p) => (
                      <tr key={p.id} className="hover:bg-gray-50">
                        <td className="px-4 py-3 font-bold text-gray-800">{p.machine_name}</td>
                        <td className="px-4 py-3">
                          <a
                            href={`/history/report/${p.id}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="font-semibold text-blue-600 hover:text-blue-800 hover:underline inline-flex items-center gap-1 group"
                            title="Buka laporan proses di tab baru"
                          >
                            <span>{p.batch_number}</span>
                            <ExternalLink size={11} className="opacity-0 group-hover:opacity-100 transition-opacity" />
                          </a>
                          <div className="text-xs text-gray-500">{p.nomor_order}</div>
                        </td>
                        <td className="px-4 py-3 font-medium text-gray-600">{p.start_time}</td>
                        <td className="px-4 py-3 font-medium text-gray-600">{p.end_time}</td>
                        <td className="px-4 py-3 text-right font-medium text-gray-800">{p.total_duration}m</td>
                        <td className="px-4 py-3 text-right">
                          <span className="bg-red-50 text-red-700 px-2 py-1 rounded font-bold">
                            {p.eff_total}%
                          </span>
                        </td>
                        <td className="px-4 py-3 text-right font-semibold text-orange-600">
                          {p.delay_heat > 0 ? `+${p.delay_heat}m` : '-'}
                        </td>
                        <td className="px-4 py-3 text-right font-semibold text-blue-600">
                          {p.delay_cool > 0 ? `+${p.delay_cool}m` : '-'}
                        </td>
                        <td className="px-4 py-3 text-right font-bold text-red-600">
                          {p.delay_total > 0 ? `+${p.delay_total}m` : '-'}
                        </td>
                        <td className="px-4 py-3 text-center">
                           <a 
                             href={`/history/report/${p.id}`}
                             target="_blank"
                             rel="noopener noreferrer"
                             className="inline-flex items-center gap-1 text-blue-600 hover:text-blue-800 font-semibold px-2.5 py-1 bg-blue-50 hover:bg-blue-100 border border-blue-200/80 rounded-lg transition-colors text-xs"
                             title="Buka laporan proses lengkap di tab baru"
                           >
                             <span>Detail</span>
                             <ExternalLink size={12} />
                           </a>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
