import React, { useState, useEffect } from 'react';
import { Play, Save, Plus } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import { engineerApi } from '../../lib/engineerApi';

export default function CalculationWorkbench() {
  const [sessions, setSessions] = useState([]);
  const [machines, setMachines] = useState([]);
  const [active, setActive] = useState(null);
  const [showNew, setShowNew] = useState(false);
  const [running, setRunning] = useState(false);
  const [kIdeal, setKIdeal] = useState('');
  const [form, setForm] = useState({
    title: '', machine_id: '', start_time: '', end_time: '',
  });

  const load = async () => {
    const [sRes, mRes] = await Promise.all([
      engineerApi.listCalculations(),
      engineerApi.listMachines(),
    ]);
    setSessions(sRes.data.data || []);
    setMachines(mRes.data.data || []);
  };

  useEffect(() => { load(); }, []);

  const openSession = async (id) => {
    const res = await engineerApi.getCalculation(id);
    setActive(res.data.data);
  };

  const createSession = async (e) => {
    e.preventDefault();
    const res = await engineerApi.createCalculation({
      title: form.title,
      machine_id: Number(form.machine_id),
      start_time: new Date(form.start_time).toISOString(),
      end_time: new Date(form.end_time).toISOString(),
      parameters: {},
    });
    setShowNew(false);
    await openSession(res.data.data.id);
    load();
  };

  const runCalc = async () => {
    if (!active) return;
    setRunning(true);
    try {
      const params = {};
      if (kIdeal) params.k_ideal = parseFloat(kIdeal);
      const res = await engineerApi.runCalculation(active.id, params);
      setActive({ ...active, results: res.data.data, parameters: { ...active.parameters, ...params } });
    } finally {
      setRunning(false);
    }
  };

  const finalize = async () => {
    if (!active) return;
    await engineerApi.updateCalculation(active.id, { status: 'FINAL' });
    setActive({ ...active, status: 'FINAL' });
    load();
  };

  const results = active?.results;
  const chartData = results?.calibrated_series?.map((p, i) => ({
    time: p.time?.slice(11, 16),
    calibrated: p.value,
    raw: results.raw_series?.[i]?.value,
  })) || [];

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-2xl font-bold">Calculation Workbench</h2>
          <p className="text-slate-500 text-sm">Sensor → validasi → perhitungan → hasil</p>
        </div>
        <button type="button" onClick={() => setShowNew(!showNew)} className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm flex items-center gap-1">
          <Plus className="w-4 h-4" /> Sesi Baru
        </button>
      </div>

      {showNew && (
        <form onSubmit={createSession} className="bg-white border rounded-xl p-4 space-y-3 shadow-sm">
          <input className="w-full border rounded-lg px-3 py-2" placeholder="Judul sesi" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} required />
          <select className="w-full border rounded-lg px-3 py-2" value={form.machine_id} onChange={(e) => setForm({ ...form, machine_id: e.target.value })} required>
            <option value="">Pilih mesin</option>
            {machines.map((m) => <option key={m.id} value={m.id}>{m.code}</option>)}
          </select>
          <div className="grid grid-cols-2 gap-3">
            <input type="datetime-local" className="border rounded-lg px-3 py-2" value={form.start_time} onChange={(e) => setForm({ ...form, start_time: e.target.value })} required />
            <input type="datetime-local" className="border rounded-lg px-3 py-2" value={form.end_time} onChange={(e) => setForm({ ...form, end_time: e.target.value })} required />
          </div>
          <button type="submit" className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm">Buat Sesi</button>
        </form>
      )}

      <div className="grid md:grid-cols-3 gap-4">
        <div className="md:col-span-1 space-y-2">
          <h3 className="font-semibold text-sm">Riwayat Sesi</h3>
          {sessions.map((s) => (
            <button
              key={s.id}
              type="button"
              onClick={() => openSession(s.id)}
              className={`w-full text-left bg-white border rounded-lg p-3 text-sm hover:border-blue-300 ${
                active?.id === s.id ? 'border-blue-500 ring-1 ring-blue-200' : ''
              }`}
            >
              <p className="font-medium truncate">{s.title}</p>
              <p className="text-xs text-slate-500">{s.machine?.code} · {s.status}</p>
            </button>
          ))}
        </div>

        <div className="md:col-span-2 space-y-4">
          {active ? (
            <>
              <div className="bg-white border rounded-xl p-4">
                <div className="flex justify-between items-start mb-4">
                  <div>
                    <h3 className="font-bold text-lg">{active.title}</h3>
                    <p className="text-sm text-slate-500">{active.machine?.code} · {active.status}</p>
                  </div>
                  <div className="flex gap-2">
                    <input
                      className="border rounded px-2 py-1 text-sm w-28"
                      placeholder="k_ideal"
                      value={kIdeal}
                      onChange={(e) => setKIdeal(e.target.value)}
                    />
                    <button type="button" disabled={running} onClick={runCalc} className="bg-indigo-600 text-white px-3 py-1.5 rounded-lg text-sm flex items-center gap-1">
                      <Play className="w-4 h-4" /> {running ? '...' : 'Run'}
                    </button>
                    {active.status === 'DRAFT' && (
                      <button type="button" onClick={finalize} className="border rounded-lg px-3 py-1.5 text-sm flex items-center gap-1">
                        <Save className="w-4 h-4" /> Final
                      </button>
                    )}
                  </div>
                </div>

                {!results && <p className="text-slate-500 text-sm">Klik Run untuk tarik data sensor dan hitung</p>}

                {results && (
                  <div className="space-y-4">
                    <div className="grid grid-cols-4 gap-2 text-center text-sm">
                      <div className="bg-slate-50 rounded-lg p-2">
                        <p className="text-slate-500 text-xs">Count</p>
                        <p className="font-bold">{results.stats?.count ?? '-'}</p>
                      </div>
                      <div className="bg-slate-50 rounded-lg p-2">
                        <p className="text-slate-500 text-xs">Min</p>
                        <p className="font-bold">{results.stats?.min ?? '-'}°</p>
                      </div>
                      <div className="bg-slate-50 rounded-lg p-2">
                        <p className="text-slate-500 text-xs">Max</p>
                        <p className="font-bold">{results.stats?.max ?? '-'}°</p>
                      </div>
                      <div className="bg-slate-50 rounded-lg p-2">
                        <p className="text-slate-500 text-xs">Avg</p>
                        <p className="font-bold">{results.stats?.avg ?? '-'}°</p>
                      </div>
                    </div>

                    {chartData.length > 0 && (
                      <ResponsiveContainer width="100%" height={200}>
                        <LineChart data={chartData}>
                          <XAxis dataKey="time" tick={{ fontSize: 10 }} />
                          <YAxis tick={{ fontSize: 10 }} />
                          <Tooltip />
                          <Legend />
                          <Line type="monotone" dataKey="calibrated" stroke="#2563eb" dot={false} strokeWidth={2} name="Calibrated" />
                          <Line type="monotone" dataKey="raw" stroke="#94a3b8" dot={false} strokeWidth={1} name="Raw" />
                        </LineChart>
                      </ResponsiveContainer>
                    )}

                    {results.outliers?.length > 0 && (
                      <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-sm">
                        <p className="font-medium text-amber-900">{results.outliers.length} outlier terdeteksi</p>
                      </div>
                    )}

                    {results.analysis && Object.keys(results.analysis).length > 0 && (
                      <div className="bg-slate-50 rounded-lg p-3 text-sm">
                        <p className="font-medium mb-2">Hasil Analisis Termal</p>
                        <div className="grid grid-cols-2 gap-1">
                          {Object.entries(results.analysis).map(([k, v]) => (
                            <div key={k} className="flex justify-between">
                              <span className="text-slate-500">{k}</span>
                              <span className="font-mono text-xs">{String(v)}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {results.calibration && (
                      <p className="text-xs text-slate-500">
                        Kalibrasi: y = {results.calibration.a_coeff}x² + {results.calibration.b_coeff}x + {results.calibration.c_coeff}
                      </p>
                    )}
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="bg-white border rounded-xl p-8 text-center text-slate-500">
              Pilih atau buat sesi perhitungan
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
