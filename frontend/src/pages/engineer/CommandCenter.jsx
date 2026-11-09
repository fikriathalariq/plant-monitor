import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import {
  AlertTriangle, Zap, ClipboardList, Wrench, Calendar, RefreshCw,
} from 'lucide-react';
import { engineerApi } from '../../lib/engineerApi';

function StatCard({ label, value, color, to }) {
  const inner = (
    <div className={`rounded-xl p-4 border ${color} bg-white shadow-sm`}>
      <p className="text-2xl font-bold">{value}</p>
      <p className="text-sm text-slate-600 mt-1">{label}</p>
    </div>
  );
  return to ? <Link to={to}>{inner}</Link> : inner;
}

export default function CommandCenter() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [mineOnly, setMineOnly] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const res = await engineerApi.commandCenter(mineOnly);
      setData(res.data.data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [mineOnly]);

  if (loading && !data) {
    return <div className="text-center py-12 text-slate-500">Memuat command center...</div>;
  }

  const s = data?.summary || {};

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-2xl font-bold text-slate-900">Command Center</h2>
          <p className="text-slate-500 text-sm">Ringkasan pekerjaan hari ini</p>
        </div>
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-2 text-sm text-slate-600">
            <input type="checkbox" checked={mineOnly} onChange={(e) => setMineOnly(e.target.checked)} />
            Hanya tugas saya
          </label>
          <button type="button" onClick={load} className="p-2 rounded-lg border hover:bg-slate-50">
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="Issue terbuka" value={s.open_issues ?? 0} color="border-orange-200" to="/engineer/issues" />
        <StatCard label="Kritis" value={s.critical_issues ?? 0} color="border-red-200" to="/engineer/issues" />
        <StatCard label="Anomali" value={s.unresolved_anomalies ?? 0} color="border-amber-200" to="/engineer/issues" />
        <StatCard label="Inspeksi draft" value={s.pending_inspections ?? 0} color="border-blue-200" to="/engineer/inspection" />
        <StatCard label="Stok rendah" value={s.low_stock_parts ?? 0} color="border-purple-200" to="/engineer/spare-parts" />
        <StatCard label="Action overdue" value={s.overdue_actions ?? 0} color="border-rose-200" to="/engineer/meetings" />
        <StatCard label="Jatuh tempo hari ini" value={s.due_today_actions ?? 0} color="border-teal-200" to="/engineer/meetings" />
      </div>

      {data?.boiler_kpi_yesterday && (
        <div className="bg-white rounded-xl border p-4 shadow-sm">
          <div className="flex items-center gap-2 mb-3">
            <Zap className="w-5 h-5 text-amber-500" />
            <h3 className="font-semibold">Boiler KPI Kemarin</h3>
          </div>
          <div className="grid grid-cols-3 gap-4 text-sm">
            <div>
              <p className="text-slate-500">Total Uap</p>
              <p className="font-bold">{data.boiler_kpi_yesterday.total_steam_kg?.toFixed(0) ?? '-'} kg</p>
            </div>
            <div>
              <p className="text-slate-500">Total Bahan Bakar</p>
              <p className="font-bold">{data.boiler_kpi_yesterday.total_fuel_kg?.toFixed(0) ?? '-'} kg</p>
            </div>
            <div>
              <p className="text-slate-500">SFC</p>
              <p className="font-bold">{data.boiler_kpi_yesterday.specific_fuel_consumption?.toFixed(2) ?? '-'}</p>
            </div>
          </div>
        </div>
      )}

      {data?.energy_widgets?.length > 0 && (
        <div className="bg-white rounded-xl border p-4 shadow-sm">
          <h3 className="font-semibold mb-3 flex items-center gap-2">
            <Zap className="w-4 h-4 text-amber-500" /> Kondisi Energi (Live)
          </h3>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            {data.energy_widgets.map((w) => (
              <div key={w.id} className="bg-slate-50 rounded-lg p-3">
                <p className="text-xs text-slate-500 truncate">{w.name}</p>
                <p className="text-lg font-bold">{w.value} {w.unit}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="grid md:grid-cols-2 gap-4">
        <div className="bg-white rounded-xl border p-4 shadow-sm">
          <h3 className="font-semibold mb-3 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-orange-500" /> Mesin Bermasalah
          </h3>
          {data?.problem_machines?.length ? (
            <ul className="space-y-2">
              {data.problem_machines.map((m) => (
                <li key={m.id}>
                  <Link to={`/engineer/machines/${m.id}`} className="text-blue-600 hover:underline text-sm">
                    {m.code} — {m.name} ({m.manual_status || 'issue'})
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-slate-500">Tidak ada mesin bermasalah</p>
          )}
        </div>

        <div className="bg-white rounded-xl border p-4 shadow-sm">
          <h3 className="font-semibold mb-3 flex items-center gap-2">
            <ClipboardList className="w-4 h-4 text-blue-500" /> Issue Terbaru
          </h3>
          {data?.recent_issues?.length ? (
            <ul className="space-y-2">
              {data.recent_issues.map((i) => (
                <li key={i.id} className="text-sm border-b pb-2 last:border-0">
                  <span className={`inline-block px-1.5 py-0.5 rounded text-xs mr-1 ${
                    i.priority === 'CRITICAL' ? 'bg-red-100 text-red-700' : 'bg-slate-100'
                  }`}>{i.priority}</span>
                  {i.title}
                  {i.machine && <span className="text-slate-500"> — {i.machine.code}</span>}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-slate-500">Tidak ada issue terbuka</p>
          )}
        </div>
      </div>

      <div className="bg-white rounded-xl border p-4 shadow-sm">
        <h3 className="font-semibold mb-3 flex items-center gap-2">
          <Calendar className="w-4 h-4 text-teal-500" /> Action Items
        </h3>
        {data?.recent_actions?.length ? (
          <ul className="space-y-2">
            {data.recent_actions.map((a) => (
              <li key={a.id} className="flex justify-between text-sm border-b pb-2">
                <span>{a.description}</span>
                <span className={`text-xs ${a.due_date && new Date(a.due_date) < new Date() ? 'text-red-600' : 'text-slate-500'}`}>
                  {a.due_date || 'no due'}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-slate-500">Tidak ada action item</p>
        )}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Link to="/engineer/inspection" className="bg-blue-600 text-white rounded-xl p-4 text-center font-medium hover:bg-blue-700">
          Mulai Inspeksi
        </Link>
        <Link to="/engineer/calculations" className="bg-indigo-600 text-white rounded-xl p-4 text-center font-medium hover:bg-indigo-700">
          Perhitungan
        </Link>
        <Link to="/engineer/issues" className="bg-orange-600 text-white rounded-xl p-4 text-center font-medium hover:bg-orange-700">
          Triage Issues
        </Link>
        <Link to="/engineer/spare-parts" className="bg-purple-600 text-white rounded-xl p-4 text-center font-medium hover:bg-purple-700 flex items-center justify-center gap-1">
          <Wrench className="w-4 h-4" /> Spare Parts
        </Link>
      </div>
    </div>
  );
}
