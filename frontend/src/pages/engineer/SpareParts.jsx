import React, { useState, useEffect } from 'react';
import { AlertTriangle, Plus } from 'lucide-react';
import { engineerApi } from '../../lib/engineerApi';

export default function SpareParts() {
  const [parts, setParts] = useState([]);
  const [machines, setMachines] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [lowOnly, setLowOnly] = useState(false);
  const [usageModal, setUsageModal] = useState(null);
  const [form, setForm] = useState({
    name: '', part_number: '', location: '', stock_quantity: 0, min_stock: 1, machine_ids: [],
  });
  const [usageForm, setUsageForm] = useState({ quantity: 1, machine_id: '', notes: '' });

  const load = async () => {
    const [pRes, mRes] = await Promise.all([
      engineerApi.listSpareParts(lowOnly),
      engineerApi.listMachines(),
    ]);
    setParts(pRes.data.data || []);
    setMachines(mRes.data.data || []);
  };

  useEffect(() => { load(); }, [lowOnly]);

  const handleCreate = async (e) => {
    e.preventDefault();
    await engineerApi.createSparePart(form);
    setShowForm(false);
    setForm({ name: '', part_number: '', location: '', stock_quantity: 0, min_stock: 1, machine_ids: [] });
    load();
  };

  const handleUsage = async () => {
    await engineerApi.logSpareUsage(usageModal.id, {
      quantity: Number(usageForm.quantity),
      machine_id: usageForm.machine_id ? Number(usageForm.machine_id) : null,
      notes: usageForm.notes,
    });
    setUsageModal(null);
    setUsageForm({ quantity: 1, machine_id: '', notes: '' });
    load();
  };

  const updateStock = async (part, delta) => {
    await engineerApi.updateSparePart(part.id, {
      stock_quantity: Math.max(0, part.stock_quantity + delta),
    });
    load();
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap justify-between gap-3 items-center">
        <div>
          <h2 className="text-2xl font-bold">Spare Parts Tracker</h2>
          <p className="text-slate-500 text-sm">Katalog, stok, dan riwayat pemakaian</p>
        </div>
        <div className="flex gap-2">
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={lowOnly} onChange={(e) => setLowOnly(e.target.checked)} />
            Stok rendah saja
          </label>
          <button type="button" onClick={() => setShowForm(!showForm)} className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm flex items-center gap-1">
            <Plus className="w-4 h-4" /> Tambah
          </button>
        </div>
      </div>

      {showForm && (
        <form onSubmit={handleCreate} className="bg-white border rounded-xl p-4 space-y-3 shadow-sm">
          <input className="w-full border rounded-lg px-3 py-2" placeholder="Nama spare part" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
          <div className="grid grid-cols-2 gap-3">
            <input className="border rounded-lg px-3 py-2" placeholder="Part number" value={form.part_number} onChange={(e) => setForm({ ...form, part_number: e.target.value })} />
            <input className="border rounded-lg px-3 py-2" placeholder="Lokasi gudang" value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} />
            <input type="number" className="border rounded-lg px-3 py-2" placeholder="Stok" value={form.stock_quantity} onChange={(e) => setForm({ ...form, stock_quantity: Number(e.target.value) })} />
            <input type="number" className="border rounded-lg px-3 py-2" placeholder="Min stok" value={form.min_stock} onChange={(e) => setForm({ ...form, min_stock: Number(e.target.value) })} />
          </div>
          <button type="submit" className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm">Simpan</button>
        </form>
      )}

      <div className="grid gap-3 md:grid-cols-2">
        {parts.map((sp) => (
          <div key={sp.id} className={`bg-white border rounded-xl p-4 shadow-sm ${sp.is_low_stock ? 'border-red-300 bg-red-50/30' : ''}`}>
            <div className="flex justify-between items-start">
              <div>
                <p className="font-bold">{sp.name}</p>
                <p className="text-xs text-slate-500">{sp.part_number} · {sp.location}</p>
              </div>
              {sp.is_low_stock && <AlertTriangle className="w-5 h-5 text-red-500" />}
            </div>
            <p className="text-2xl font-bold mt-2">
              {sp.stock_quantity} <span className="text-sm font-normal text-slate-500">{sp.unit}</span>
            </p>
            <p className="text-xs text-slate-500">Min: {sp.min_stock}</p>
            {sp.machines?.length > 0 && (
              <p className="text-xs mt-1 text-slate-600">Mesin: {sp.machines.map((m) => m.code).join(', ')}</p>
            )}
            <div className="flex gap-2 mt-3">
              <button type="button" onClick={() => updateStock(sp, 1)} className="text-xs border rounded px-2 py-1">+1</button>
              <button type="button" onClick={() => updateStock(sp, -1)} className="text-xs border rounded px-2 py-1">-1</button>
              <button type="button" onClick={() => setUsageModal(sp)} className="text-xs bg-blue-600 text-white rounded px-2 py-1 ml-auto">
                Catat Pemakaian
              </button>
            </div>
          </div>
        ))}
      </div>

      {parts.length === 0 && <p className="text-center text-slate-500 py-8">Belum ada spare part</p>}

      {usageModal && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl p-4 w-full max-w-sm space-y-3">
            <h3 className="font-bold">Pemakaian: {usageModal.name}</h3>
            <input type="number" className="w-full border rounded-lg px-3 py-2" value={usageForm.quantity} onChange={(e) => setUsageForm({ ...usageForm, quantity: e.target.value })} />
            <select className="w-full border rounded-lg px-3 py-2" value={usageForm.machine_id} onChange={(e) => setUsageForm({ ...usageForm, machine_id: e.target.value })}>
              <option value="">Mesin (opsional)</option>
              {machines.map((m) => <option key={m.id} value={m.id}>{m.code}</option>)}
            </select>
            <input className="w-full border rounded-lg px-3 py-2" placeholder="Catatan" value={usageForm.notes} onChange={(e) => setUsageForm({ ...usageForm, notes: e.target.value })} />
            <div className="flex gap-2">
              <button type="button" onClick={() => setUsageModal(null)} className="flex-1 border rounded-lg py-2">Batal</button>
              <button type="button" onClick={handleUsage} className="flex-1 bg-blue-600 text-white rounded-lg py-2">Simpan</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
