import React, { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import { engineerApi } from '../../lib/engineerApi';

const TABS = ['overview', 'batch', 'issues', 'calibration', 'inspections', 'notes', 'spare'];

export default function MachineDossier() {
  const { machineId } = useParams();
  const [data, setData] = useState(null);
  const [tab, setTab] = useState('overview');
  const [noteText, setNoteText] = useState('');
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const res = await engineerApi.getDossier(machineId);
      setData(res.data.data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [machineId]);

  const addNote = async () => {
    if (!noteText.trim()) return;
    await engineerApi.createNote({ machine_id: Number(machineId), content: noteText });
    setNoteText('');
    load();
  };

  if (loading) return <div className="text-center py-12">Memuat dossier...</div>;
  if (!data) return <div className="text-center py-12 text-red-500">Mesin tidak ditemukan</div>;

  const m = data.machine;

  return (
    <div className="space-y-4">
      <Link to="/engineer/machines" className="text-blue-600 text-sm">← Daftar Mesin</Link>

      <div className="bg-white border rounded-xl p-4 shadow-sm">
        <div className="flex flex-wrap justify-between gap-2">
          <div>
            <h2 className="text-2xl font-bold">{m.code}</h2>
            <p className="text-slate-500">{m.name} · {m.group}</p>
          </div>
          <div className="text-right">
            <p className="text-3xl font-bold text-blue-600">{m.temperature?.toFixed(1) ?? '-'}°C</p>
            <p className="text-sm text-slate-500">Status: {m.manual_status || 'AUTO'}</p>
          </div>
        </div>
        {data.active_batch && (
          <p className="mt-2 text-sm bg-green-50 text-green-800 rounded-lg px-3 py-2 inline-block">
            Batch aktif #{data.active_batch.batch_number} sejak {new Date(data.active_batch.start_time).toLocaleString()}
          </p>
        )}
      </div>

      <div className="flex gap-1 overflow-x-auto pb-1">
        {TABS.map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium whitespace-nowrap ${
              tab === t ? 'bg-blue-600 text-white' : 'bg-white border text-slate-600'
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === 'overview' && (
        <div className="bg-white border rounded-xl p-4">
          <h3 className="font-semibold mb-3">Suhu 24 Jam</h3>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={data.chart_24h}>
              <XAxis dataKey="time" tick={{ fontSize: 10 }} />
              <YAxis tick={{ fontSize: 10 }} />
              <Tooltip />
              <Line type="monotone" dataKey="temp" stroke="#2563eb" dot={false} strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {tab === 'batch' && (
        <div className="bg-white border rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 border-b">
              <tr>
                <th className="p-3 text-left">Batch</th>
                <th className="p-3 text-left">Mulai</th>
                <th className="p-3 text-left">Durasi (min)</th>
                <th className="p-3 text-left">Efisiensi</th>
              </tr>
            </thead>
            <tbody>
              {data.batch_history.map((b) => (
                <tr key={b.id} className="border-b">
                  <td className="p-3">#{b.batch_number}</td>
                  <td className="p-3">{b.start_time ? new Date(b.start_time).toLocaleString() : '-'}</td>
                  <td className="p-3">{b.total_duration?.toFixed(0) ?? '-'}</td>
                  <td className="p-3">{b.efficiency?.toFixed(2) ?? '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === 'issues' && (
        <div className="space-y-2">
          {data.open_issues.map((i) => (
            <div key={i.id} className="bg-white border rounded-lg p-3 text-sm">
              <span className="font-medium">{i.title}</span> — {i.status} ({i.priority})
            </div>
          ))}
          {data.anomalies.map((a) => (
            <div key={a.id} className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-sm">
              Anomali: {a.type} ({a.severity})
            </div>
          ))}
          {!data.open_issues.length && !data.anomalies.length && (
            <p className="text-slate-500 text-sm">Tidak ada masalah terbuka</p>
          )}
        </div>
      )}

      {tab === 'calibration' && (
        <div className="bg-white border rounded-xl p-4 text-sm">
          {data.calibration ? (
            <div className="space-y-2">
              <p>y = {data.calibration.a_coeff}x² + {data.calibration.b_coeff}x + {data.calibration.c_coeff}</p>
              <p>Status: {data.calibration.is_active ? 'Aktif' : 'Nonaktif'}</p>
              <p className="text-slate-500">{data.calibration.notes}</p>
            </div>
          ) : (
            <p className="text-slate-500">Belum ada kalibrasi</p>
          )}
        </div>
      )}

      {tab === 'inspections' && (
        <div className="space-y-2">
          {data.inspections.map((ins) => (
            <div key={ins.id} className="bg-white border rounded-lg p-3 text-sm">
              <p className="font-medium">{ins.severity} — {ins.status}</p>
              <p className="text-slate-500">{new Date(ins.created_at).toLocaleString()}</p>
              <p>{ins.notes}</p>
            </div>
          ))}
        </div>
      )}

      {tab === 'notes' && (
        <div className="space-y-3">
          <div className="flex gap-2">
            <textarea
              className="flex-1 border rounded-lg px-3 py-2 text-sm"
              rows={2}
              placeholder="Tambah catatan engineer..."
              value={noteText}
              onChange={(e) => setNoteText(e.target.value)}
            />
            <button type="button" onClick={addNote} className="bg-blue-600 text-white px-4 rounded-lg text-sm self-end">
              Simpan
            </button>
          </div>
          {data.notes.map((n) => (
            <div key={n.id} className="bg-white border rounded-lg p-3 text-sm">
              <p>{n.content}</p>
              <p className="text-xs text-slate-400 mt-1">{n.author?.username} · {new Date(n.created_at).toLocaleString()}</p>
            </div>
          ))}
        </div>
      )}

      {tab === 'spare' && (
        <div className="space-y-2">
          {data.spare_parts.map((sp) => (
            <div key={sp.id} className="bg-white border rounded-lg p-3 text-sm flex justify-between">
              <span>{sp.name} ({sp.part_number})</span>
              <span className={sp.is_low_stock ? 'text-red-600 font-medium' : ''}>
                Stok: {sp.stock_quantity}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
