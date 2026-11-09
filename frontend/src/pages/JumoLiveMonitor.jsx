import React, { useCallback, useMemo, useState } from 'react';
import { RefreshCw, Radio, AlertTriangle, Search, Database, Cpu, Zap, Droplets, Layers, Flame } from 'lucide-react';
import api from '../lib/api';
import { useSmartPolling } from '../hooks/useSmartPolling';

const AUTO_REFRESH_MS = 30_000;

function fmtAge(iso) {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    const ageSec = (Date.now() - d.getTime()) / 1000;
    if (Number.isNaN(ageSec)) return '—';
    if (ageSec < 60) return `${Math.round(ageSec)}s`;
    if (ageSec < 3600) return `${Math.round(ageSec / 60)}m`;
    return `${(ageSec / 3600).toFixed(1)}h`;
  } catch {
    return '—';
  }
}

function formatNumber(val, dec = 0) {
  if (val == null || Number.isNaN(+val)) return '—';
  return Number(val).toLocaleString('id-ID', {
    minimumFractionDigits: dec,
    maximumFractionDigits: dec,
  });
}

function issueBadge(issue) {
  const styles = {
    CONTROLLER_DOWN: 'bg-rose-100 text-rose-800 border-rose-200',
    LIVE_NULL: 'bg-rose-50 text-rose-700 border-rose-200',
    UNMAPPED_MACHINE: 'bg-amber-100 text-amber-900 border-amber-200',
    AI_MISMATCH: 'bg-amber-50 text-amber-800 border-amber-200',
    DB_STALE: 'bg-slate-200 text-slate-800 border-slate-300',
  };
  return styles[issue] || 'bg-slate-100 text-slate-700 border-slate-200';
}

function rowClass(ch, ctrlOk) {
  if (!ctrlOk || ch.issues?.includes('CONTROLLER_DOWN')) return 'bg-rose-50/70 hover:bg-rose-100/50';
  if (ch.issues?.includes('UNMAPPED_MACHINE') || ch.issues?.includes('AI_MISMATCH')) {
    return 'bg-amber-50/60 hover:bg-amber-100/40';
  }
  if (ch.issues?.includes('LIVE_NULL') || ch.is_stale) return 'bg-slate-50/70 hover:bg-slate-100/60';
  return 'hover:bg-slate-50/60';
}

export default function JumoLiveMonitor() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [lastFetchAt, setLastFetchAt] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');

  const fetchData = useCallback(async (force = false) => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get('/jumo-live/', {
        params: force ? { force: true } : undefined,
        cache: force ? false : undefined,
      });
      setData(res.data);
      setLastFetchAt(new Date());
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Gagal memuat data');
    } finally {
      setLoading(false);
    }
  }, []);

  // Polling cerdas Modbus: pause otomatis saat tab diminimize, resume seketika saat fokus
  useSmartPolling(() => fetchData(false), AUTO_REFRESH_MS, {
    enabled: autoRefresh,
    immediate: true,
  });

  const summary = data?.summary;

  // Filter channel berdasarkan search query
  const filteredControllers = useMemo(() => {
    if (!data?.controllers) return [];
    if (!searchQuery.trim()) return data.controllers;

    const query = searchQuery.toLowerCase().trim();
    return data.controllers
      .map((ctrl) => {
        const matchesCtrl =
          ctrl.name.toLowerCase().includes(query) || (ctrl.ip && ctrl.ip.includes(query));
        if (matchesCtrl) return ctrl;

        const filteredChannels = (ctrl.channels || []).filter(
          (ch) =>
            ch.code.toLowerCase().includes(query) ||
            (ch.machine_name && ch.machine_name.toLowerCase().includes(query)) ||
            (ch.group && ch.group.toLowerCase().includes(query))
        );

        return {
          ...ctrl,
          channels: filteredChannels,
        };
      })
      .filter((ctrl) => ctrl.channels && ctrl.channels.length > 0);
  }, [data, searchQuery]);

  return (
    <div className="p-4 md:p-6 max-w-[1600px] mx-auto space-y-4">
      {/* Header Halaman */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-slate-900 flex items-center gap-2">
            <Radio className="w-5 h-5 text-emerald-700" />
            JUMO Live Monitor & Database Mesin
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 mt-1">
            Telemetri langsung Modbus TCP disandingkan dengan parameter database mesin (Daya, Uap, Air, Kain, HTO). Timeout{' '}
            {data?.modbus_timeout_sec ?? '—'}s · cache {data?.cache_ttl_sec ?? '—'}s.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-2 text-xs sm:text-sm text-slate-700 select-none cursor-pointer">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="rounded border-slate-300 text-emerald-600 focus:ring-emerald-500 cursor-pointer"
            />
            Auto-refresh 30s
          </label>
          <button
            type="button"
            onClick={() => fetchData(true)}
            disabled={loading}
            className="inline-flex items-center gap-2 px-3.5 py-1.5 text-xs sm:text-sm font-semibold rounded-xl bg-emerald-700 hover:bg-emerald-800 text-white shadow-xs disabled:opacity-60 transition-colors cursor-pointer"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            Refresh Now
          </button>
        </div>
      </div>

      {error && (
        <div className="flex items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 px-3.5 py-2.5 text-xs text-rose-800 shadow-2xs">
          <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0 text-rose-600" />
          <span>{error}</span>
        </div>
      )}

      {/* KPI Summary Cards */}
      {summary && (
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2.5 text-sm">
          {[
            ['Controller OK', summary.controllers_ok, 'text-emerald-700', 'bg-emerald-50/50'],
            ['Controller Fail', summary.controllers_fail, summary.controllers_fail > 0 ? 'text-rose-600 font-bold' : 'text-slate-800', 'bg-slate-50/50'],
            ['Channel Live', summary.channels_live, 'text-emerald-700 font-bold', 'bg-emerald-50/30'],
            ['Channel Null', summary.channels_null, summary.channels_null > 0 ? 'text-amber-600' : 'text-slate-800', 'bg-slate-50/50'],
            ['Unmapped', summary.unmapped, summary.unmapped > 0 ? 'text-amber-600' : 'text-slate-800', 'bg-slate-50/50'],
            ['DB Stale', summary.stale, summary.stale > 0 ? 'text-rose-600' : 'text-slate-800', 'bg-slate-50/50'],
            ['Total Channel', summary.channels_total, 'text-slate-900 font-bold', 'bg-slate-50'],
          ].map(([label, val, textClass, bgClass]) => (
            <div key={label} className={`border border-slate-200/80 rounded-xl p-3 bg-white shadow-2xs ${bgClass}`}>
              <div className="text-[11px] font-medium text-slate-500 truncate">{label}</div>
              <div className={`text-lg font-black mt-0.5 ${textClass}`}>{val}</div>
            </div>
          ))}
        </div>
      )}

      {/* Baris Kontrol: Pencarian & Info Timestamp */}
      <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
        <div className="relative flex-1 min-w-[260px] max-w-md">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            placeholder="Cari kode mesin, nama, atau grup..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-9 pr-3 py-1.5 text-xs rounded-xl border border-slate-200 bg-white placeholder-slate-400 text-slate-800 focus:outline-none focus:ring-1 focus:ring-emerald-500 focus:border-emerald-500 shadow-2xs"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 text-xs font-bold"
            >
              ×
            </button>
          )}
        </div>

        <div className="text-[11px] text-slate-400 flex items-center gap-1.5 flex-wrap">
          <span>Polled: {data?.polled_at || '—'}</span>
          {data?.from_cache != null && (
            <span>· {data.from_cache ? `cache ${data.cache_age_ms}ms` : 'fresh'}</span>
          )}
          {lastFetchAt && <span>· UI: {lastFetchAt.toLocaleTimeString()}</span>}
        </div>
      </div>

      {/* Daftar Controller dan Tabel Channel */}
      <div className="space-y-6">
        {filteredControllers.map((ctrl) => (
          <section key={ctrl.name} className="border border-slate-200/90 rounded-2xl bg-white shadow-xs overflow-hidden">
            <header
              className={`px-4 py-3 flex flex-wrap items-center justify-between gap-2 border-b ${
                ctrl.ok ? 'bg-emerald-50/70 border-emerald-100' : 'bg-rose-50/70 border-rose-100'
              }`}
            >
              <div>
                <div className="font-bold text-slate-900 text-sm flex items-center gap-2">
                  <span className={`w-2 h-2 rounded-full ${ctrl.ok ? 'bg-emerald-500 animate-pulse' : 'bg-rose-500'}`} />
                  {ctrl.name}{' '}
                  <span className="font-mono text-xs font-normal text-slate-500">({ctrl.ip})</span>
                </div>
                <div className="text-xs text-slate-600 mt-0.5 flex items-center gap-2 flex-wrap">
                  <span className={`font-semibold ${ctrl.ok ? 'text-emerald-700' : 'text-rose-700'}`}>
                    {ctrl.ok ? 'ONLINE' : 'DOWN'}
                  </span>
                  {ctrl.latency_ms != null && <span>· {ctrl.latency_ms} ms</span>}
                  <span>· AI {ctrl.num_ai} / channels {ctrl.channel_count}</span>
                  {ctrl.ai_mismatch && <span className="text-amber-700 font-semibold">· AI mismatch</span>}
                  {ctrl.error && <span className="text-rose-600">· {ctrl.error}</span>}
                </div>
              </div>
            </header>

            <div className="overflow-x-auto">
              <table className="min-w-full text-xs">
                <thead className="bg-slate-50 text-slate-600 border-b border-slate-200 text-left uppercase tracking-wider text-[10px]">
                  <tr>
                    <th className="px-3 py-2.5 font-bold text-center w-8">#</th>
                    <th className="px-3 py-2.5 font-bold min-w-[120px]">Mesin / Code</th>
                    <th className="px-3 py-2.5 font-bold min-w-[140px]">Group</th>
                    <th className="px-3 py-2.5 font-bold text-right min-w-[85px]">Live Modbus</th>
                    <th className="px-3 py-2.5 font-bold text-right min-w-[85px]">DB Temp</th>
                    <th className="px-3 py-2.5 font-bold text-center min-w-[85px]">Status DB</th>
                    <th className="px-3 py-2.5 font-bold text-center min-w-[75px]">Last Valid</th>

                    {/* Kolom Database Mesin (Specs / Master Parameters) */}
                    <th className="px-3 py-2.5 font-bold text-right text-sky-800 bg-sky-50/60 min-w-[105px]" title="Rata-rata Penggunaan Uap per jam (average_steam_usage)">
                      Avg Steam (kg/h)
                    </th>
                    <th className="px-3 py-2.5 font-bold text-right text-indigo-800 bg-indigo-50/60 min-w-[105px]" title="Daya Nominal Mesin (nominal_power)">
                      Nominal (kW)
                    </th>
                    <th className="px-3 py-2.5 font-bold text-right text-teal-800 bg-teal-50/60 min-w-[100px]" title="Kapasitas Air Maksimal (max_water_capacity)">
                      Max Water (L)
                    </th>
                    <th className="px-3 py-2.5 font-bold text-right text-emerald-800 bg-emerald-50/60 min-w-[100px]" title="Kapasitas Kain Maksimal (max_fabric_capacity)">
                      Max Fabric (kg)
                    </th>
                    <th className="px-3 py-2.5 font-bold text-right text-amber-800 bg-amber-50/60 min-w-[105px]" title="Kalori Rata-Rata HTO (avg_hto_calories)">
                      Avg HTO (kCal)
                    </th>

                    <th className="px-3 py-2.5 font-bold text-center min-w-[90px]">Issues</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {(ctrl.channels || []).map((ch) => (
                    <tr key={`${ctrl.name}-${ch.index}-${ch.code}`} className={`transition-colors ${rowClass(ch, ctrl.ok)}`}>
                      <td className="px-3 py-2 text-center text-slate-400 font-mono">{ch.index}</td>
                      <td className="px-3 py-2">
                        <div className="font-bold text-slate-900 leading-tight">
                          {ch.code}
                        </div>
                        {ch.machine_name && ch.machine_name !== ch.code && (
                          <div className="text-[10px] text-slate-500 font-medium">
                            {ch.machine_name}
                          </div>
                        )}
                      </td>
                      <td className="px-3 py-2 text-slate-600 truncate max-w-[180px]" title={ch.group || ''}>
                        {ch.group || '—'}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums font-mono">
                        {ch.live_value != null ? (
                          <span className="font-bold text-slate-900">{formatNumber(ch.live_value, 2)} °C</span>
                        ) : (
                          <span className="text-slate-300 font-sans">—</span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums font-mono text-slate-700">
                        {ch.db_temperature != null ? (
                          <span>{formatNumber(ch.db_temperature, 2)} °C</span>
                        ) : (
                          <span className="text-slate-300 font-sans">—</span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-center">
                        {ch.db_status ? (
                          <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold ${
                            ch.db_status === 'Running' || ch.db_status === 'HEAT'
                              ? 'bg-emerald-100 text-emerald-800'
                              : ch.db_status === 'STEADY'
                              ? 'bg-amber-100 text-amber-800'
                              : ch.db_status === 'COOL'
                              ? 'bg-cyan-100 text-cyan-800'
                              : ch.db_status === 'NO SIGNAL'
                              ? 'bg-rose-100 text-rose-800'
                              : 'bg-slate-100 text-slate-700'
                          }`}>
                            {ch.db_status}
                          </span>
                        ) : (
                          <span className="text-slate-300">—</span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-center text-slate-500 font-mono text-[11px]" title={ch.db_last_valid_reading_at || ''}>
                        {fmtAge(ch.db_last_valid_reading_at)}
                      </td>

                      {/* Data Spesifikasi Database Mesin */}
                      <td className="px-3 py-2 text-right tabular-nums font-mono bg-sky-50/20">
                        {ch.average_steam_usage != null && ch.average_steam_usage > 0 ? (
                          <span className="font-semibold text-sky-800">
                            {formatNumber(ch.average_steam_usage, 1)} <span className="text-[10px] text-sky-600 font-sans">kg/h</span>
                          </span>
                        ) : (
                          <span className="text-slate-300 font-sans">—</span>
                        )}
                      </td>

                      <td className="px-3 py-2 text-right tabular-nums font-mono bg-indigo-50/20">
                        {ch.nominal_power != null && ch.nominal_power > 0 ? (
                          <span className="font-semibold text-indigo-800">
                            {formatNumber(ch.nominal_power, 1)} <span className="text-[10px] text-indigo-600 font-sans">kW</span>
                          </span>
                        ) : (
                          <span className="text-slate-300 font-sans">—</span>
                        )}
                      </td>

                      <td className="px-3 py-2 text-right tabular-nums font-mono bg-teal-50/20">
                        {ch.max_water_capacity != null && ch.max_water_capacity > 0 ? (
                          <span className="font-semibold text-teal-800">
                            {formatNumber(ch.max_water_capacity, 0)} <span className="text-[10px] text-teal-600 font-sans">L</span>
                          </span>
                        ) : (
                          <span className="text-slate-300 font-sans">—</span>
                        )}
                      </td>

                      <td className="px-3 py-2 text-right tabular-nums font-mono bg-emerald-50/20">
                        {ch.max_fabric_capacity != null && ch.max_fabric_capacity > 0 ? (
                          <span className="font-semibold text-emerald-800">
                            {formatNumber(ch.max_fabric_capacity, 0)} <span className="text-[10px] text-emerald-600 font-sans">kg</span>
                          </span>
                        ) : (
                          <span className="text-slate-300 font-sans">—</span>
                        )}
                      </td>

                      <td className="px-3 py-2 text-right tabular-nums font-mono bg-amber-50/20">
                        {ch.avg_hto_calories != null && ch.avg_hto_calories > 0 ? (
                          <span className="font-semibold text-amber-800">
                            {formatNumber(ch.avg_hto_calories, 0)} <span className="text-[10px] text-amber-600 font-sans">kCal</span>
                          </span>
                        ) : (
                          <span className="text-slate-300 font-sans">—</span>
                        )}
                      </td>

                      <td className="px-3 py-2 text-center">
                        <div className="flex flex-wrap items-center justify-center gap-1">
                          {(ch.issues || []).length === 0 && (
                            <span className="text-[11px] text-emerald-600 font-semibold">✓ Normal</span>
                          )}
                          {(ch.issues || []).map((iss) => (
                            <span
                              key={iss}
                              className={`text-[9px] px-1.5 py-0.5 rounded font-bold border ${issueBadge(iss)}`}
                            >
                              {iss}
                            </span>
                          ))}
                        </div>
                      </td>
                    </tr>
                  ))}
                  {(!ctrl.channels || ctrl.channels.length === 0) && (
                    <tr>
                      <td colSpan={13} className="px-3 py-6 text-center text-slate-400">
                        Tidak ada channel yang cocok dengan pencarian
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>
        ))}

        {!loading && (!data?.controllers || data.controllers.length === 0) && !error && (
          <div className="border border-slate-200 rounded-2xl p-8 text-center bg-white shadow-xs">
            <Database className="w-8 h-8 text-slate-300 mx-auto mb-2" />
            <p className="text-sm font-semibold text-slate-600">Tidak ada data controller JUMO aktif.</p>
          </div>
        )}
      </div>
    </div>
  );
}
