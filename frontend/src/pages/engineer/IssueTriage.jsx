import React, { useState, useEffect } from 'react';
import { engineerApi } from '../../lib/engineerApi';

const STATUS_OPTIONS = ['OPEN', 'IN_PROGRESS', 'WAITING_PARTS', 'RESOLVED'];
const PRIORITY_OPTIONS = ['CRITICAL', 'HIGH', 'NORMAL'];

const priorityClass = (p) => {
  if (p === 'CRITICAL') return 'bg-red-100 text-red-800';
  if (p === 'HIGH') return 'bg-orange-100 text-orange-800';
  return 'bg-slate-100 text-slate-700';
};

export default function IssueTriage() {
  const [issues, setIssues] = useState([]);
  const [anomalies, setAnomalies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [machines, setMachines] = useState([]);
  const [users, setUsers] = useState([]);
  const [form, setForm] = useState({
    title: '', description: '', priority: 'NORMAL', machine_id: '', assigned_to_id: '', due_date: '',
  });
  const [editId, setEditId] = useState(null);
  const [editForm, setEditForm] = useState({});

  const load = async () => {
    setLoading(true);
    try {
      const [issueRes, machineRes, userRes] = await Promise.all([
        engineerApi.listIssues(),
        engineerApi.listMachines(),
        engineerApi.listUsers(),
      ]);
      setIssues(issueRes.data.data || []);
      setAnomalies(issueRes.data.unlinked_anomalies || []);
      setMachines(machineRes.data.data || []);
      setUsers(userRes.data.data || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const handleCreate = async (e) => {
    e.preventDefault();
    await engineerApi.createIssue({
      ...form,
      machine_id: form.machine_id ? Number(form.machine_id) : null,
      assigned_to_id: form.assigned_to_id ? Number(form.assigned_to_id) : null,
      due_date: form.due_date || null,
    });
    setShowForm(false);
    setForm({ title: '', description: '', priority: 'NORMAL', machine_id: '', assigned_to_id: '', due_date: '' });
    load();
  };

  const handleFromAnomaly = async (anomalyId) => {
    await engineerApi.createIssueFromAnomaly(anomalyId);
    load();
  };

  const handleUpdate = async (id) => {
    await engineerApi.updateIssue(id, {
      ...editForm,
      assigned_to_id: editForm.assigned_to_id ? Number(editForm.assigned_to_id) : undefined,
    });
    setEditId(null);
    load();
  };

  if (loading) return <div className="text-center py-12 text-slate-500">Memuat antrian...</div>;

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-2xl font-bold">Issue Triage Queue</h2>
          <p className="text-slate-500 text-sm">Antrian masalah terpadu</p>
        </div>
        <button type="button" onClick={() => setShowForm(!showForm)} className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium">
          + Issue Baru
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleCreate} className="bg-white border rounded-xl p-4 space-y-3 shadow-sm">
          <input className="w-full border rounded-lg px-3 py-2" placeholder="Judul" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} required />
          <textarea className="w-full border rounded-lg px-3 py-2" placeholder="Deskripsi" rows={2} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          <div className="grid grid-cols-2 gap-3">
            <select className="border rounded-lg px-3 py-2" value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}>
              {PRIORITY_OPTIONS.map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
            <select className="border rounded-lg px-3 py-2" value={form.machine_id} onChange={(e) => setForm({ ...form, machine_id: e.target.value })}>
              <option value="">Pilih mesin</option>
              {machines.map((m) => <option key={m.id} value={m.id}>{m.code}</option>)}
            </select>
            <select className="border rounded-lg px-3 py-2" value={form.assigned_to_id} onChange={(e) => setForm({ ...form, assigned_to_id: e.target.value })}>
              <option value="">Assign ke</option>
              {users.map((u) => <option key={u.id} value={u.id}>{u.username}</option>)}
            </select>
            <input type="date" className="border rounded-lg px-3 py-2" value={form.due_date} onChange={(e) => setForm({ ...form, due_date: e.target.value })} />
          </div>
          <button type="submit" className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm">Simpan</button>
        </form>
      )}

      {anomalies.length > 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
          <h3 className="font-semibold text-amber-900 mb-2">Anomali Belum Ditriage ({anomalies.length})</h3>
          <ul className="space-y-2">
            {anomalies.map((a) => (
              <li key={a.id} className="flex justify-between items-center text-sm bg-white rounded-lg p-3 border">
                <div>
                  <span className={`px-1.5 py-0.5 rounded text-xs ${priorityClass(a.priority)}`}>{a.priority}</span>
                  <span className="ml-2">{a.title}</span>
                  {a.machine && <span className="text-slate-500 ml-1">({a.machine.code})</span>}
                </div>
                <button type="button" onClick={() => handleFromAnomaly(a.anomaly_id)} className="text-blue-600 text-xs font-medium">
                  + Buat Issue
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="bg-white border rounded-xl overflow-hidden shadow-sm">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 border-b">
            <tr>
              <th className="text-left p-3">Prioritas</th>
              <th className="text-left p-3 hidden md:table-cell">Status</th>
              <th className="text-left p-3">Judul</th>
              <th className="text-left p-3 hidden sm:table-cell">Mesin</th>
              <th className="text-left p-3">Aksi</th>
            </tr>
          </thead>
          <tbody>
            {issues.map((issue) => (
              <tr key={issue.id} className="border-b last:border-0 hover:bg-slate-50">
                <td className="p-3">
                  <span className={`px-2 py-0.5 rounded text-xs font-medium ${priorityClass(issue.priority)}`}>
                    {issue.priority}
                  </span>
                </td>
                <td className="p-3 hidden md:table-cell text-slate-600">{issue.status}</td>
                <td className="p-3">
                  <p className="font-medium">{issue.title}</p>
                  <p className="text-xs text-slate-500">{issue.source_type}</p>
                </td>
                <td className="p-3 hidden sm:table-cell">{issue.machine?.code || '-'}</td>
                <td className="p-3">
                  {editId === issue.id ? (
                    <div className="space-y-1">
                      <select className="border rounded text-xs w-full" value={editForm.status || issue.status} onChange={(e) => setEditForm({ ...editForm, status: e.target.value })}>
                        {STATUS_OPTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
                      </select>
                      <button type="button" onClick={() => handleUpdate(issue.id)} className="text-blue-600 text-xs">Simpan</button>
                    </div>
                  ) : (
                    <button type="button" onClick={() => { setEditId(issue.id); setEditForm({ status: issue.status }); }} className="text-blue-600 text-xs">
                      Update
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {issues.length === 0 && <p className="p-6 text-center text-slate-500">Tidak ada issue terbuka</p>}
      </div>
    </div>
  );
}
