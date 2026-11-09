import React, { useState, useEffect } from 'react';
import { useToast } from '../../context/ToastContext';
import { Camera, Save, Send, WifiOff } from 'lucide-react';
import {
  engineerApi, saveInspectionDraft, getInspectionDrafts, removeInspectionDraft,
} from '../../lib/engineerApi';
import { API_BASE_URL } from '../../lib/api';

const mediaBase = API_BASE_URL.replace('/api/v1', '');

const DEFAULT_ITEMS = [
  { id: 'temp_abnormal', label: 'Suhu abnormal', required: true },
  { id: 'steam_leak', label: 'Kebocoran steam', required: true },
  { id: 'sensor_error', label: 'Sensor error', required: true },
  { id: 'spare_worn', label: 'Spare part aus', required: false },
  { id: 'noise_vibration', label: 'Kebisingan/getaran', required: false },
];

export default function FieldInspection() {
  const toast = useToast();
  const [machines, setMachines] = useState([]);
  const [inspections, setInspections] = useState([]);
  const [drafts, setDrafts] = useState([]);
  const [machineId, setMachineId] = useState('');
  const [severity, setSeverity] = useState('NORMAL');
  const [notes, setNotes] = useState('');
  const [recommendation, setRecommendation] = useState('');
  const [checklist, setChecklist] = useState({});
  const [photo, setPhoto] = useState(null);
  const [online, setOnline] = useState(navigator.onLine);
  const [saving, setSaving] = useState(false);

  const load = async () => {
    const [mRes, iRes] = await Promise.all([
      engineerApi.listMachines(),
      engineerApi.listInspections(),
    ]);
    setMachines(mRes.data.data || []);
    setInspections(iRes.data.data || []);
    setDrafts(getInspectionDrafts());
  };

  useEffect(() => {
    load();
    const onOnline = () => setOnline(true);
    const onOffline = () => setOnline(false);
    window.addEventListener('online', onOnline);
    window.addEventListener('offline', onOffline);
    return () => {
      window.removeEventListener('online', onOnline);
      window.removeEventListener('offline', onOffline);
    };
  }, []);

  const toggleCheck = (id) => {
    setChecklist((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const saveDraft = () => {
    const localId = `draft-${Date.now()}`;
    saveInspectionDraft({
      localId,
      machine_id: machineId,
      severity,
      notes,
      recommendation,
      checklist_results: checklist,
      saved_at: new Date().toISOString(),
    });
    setDrafts(getInspectionDrafts());
    toast.info('Draft disimpan secara lokal');
  };

  const loadDraft = (draft) => {
    setMachineId(String(draft.machine_id || ''));
    setSeverity(draft.severity || 'NORMAL');
    setNotes(draft.notes || '');
    setRecommendation(draft.recommendation || '');
    setChecklist(draft.checklist_results || {});
  };

  const submit = async (asDraft = false) => {
    if (!machineId) return toast.warning('Silakan pilih mesin terlebih dahulu');
    setSaving(true);
    const payload = {
      machine_id: Number(machineId),
      checklist_results: checklist,
      severity,
      notes,
      recommendation,
      status: asDraft ? 'DRAFT' : 'SUBMITTED',
    };

    if (!online && !asDraft) {
      saveInspectionDraft({ localId: `draft-${Date.now()}`, ...payload, pending_sync: true });
      toast.info('Mode Offline: Disimpan sebagai draft untuk sinkronisasi nanti');
      setSaving(false);
      return;
    }

    try {
      const res = await engineerApi.createInspection(payload);
      if (photo && res.data.data?.id) {
        await engineerApi.uploadInspectionPhoto(res.data.data.id, photo);
      }
      setMachineId('');
      setChecklist({});
      setNotes('');
      setRecommendation('');
      setPhoto(null);
      load();
    } catch (e) {
      console.error(e);
      toast.error('Gagal menyimpan hasil inspeksi');
    } finally {
      setSaving(false);
    }
  };

  const syncDraft = async (draft) => {
    try {
      await engineerApi.createInspection({
        machine_id: Number(draft.machine_id),
        checklist_results: draft.checklist_results,
        severity: draft.severity,
        notes: draft.notes,
        recommendation: draft.recommendation,
        status: 'SUBMITTED',
      });
      removeInspectionDraft(draft.localId);
      load();
    } catch (e) {
      toast.error('Sinkronisasi draft gagal, coba beberapa saat lagi');
    }
  };

  return (
    <div className="space-y-6 max-w-lg mx-auto md:max-w-2xl">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">Field Inspection</h2>
          <p className="text-slate-500 text-sm">Pengecekan lapangan mobile-first</p>
        </div>
        {!online && (
          <span className="flex items-center gap-1 text-amber-600 text-xs bg-amber-50 px-2 py-1 rounded-full">
            <WifiOff className="w-3 h-3" /> Offline
          </span>
        )}
      </div>

      {drafts.length > 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 space-y-2">
          <p className="font-medium text-sm text-amber-900">Draft Lokal ({drafts.length})</p>
          {drafts.map((d) => (
            <div key={d.localId} className="flex justify-between items-center text-sm bg-white rounded-lg p-2 border">
              <button type="button" onClick={() => loadDraft(d)} className="text-blue-600">
                Mesin #{d.machine_id} — {new Date(d.saved_at).toLocaleString()}
              </button>
              {d.pending_sync && online && (
                <button type="button" onClick={() => syncDraft(d)} className="text-green-600 text-xs">Sync</button>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="bg-white border rounded-xl p-4 space-y-4 shadow-sm">
        <select
          className="w-full border rounded-lg px-3 py-3 text-base"
          value={machineId}
          onChange={(e) => setMachineId(e.target.value)}
        >
          <option value="">Pilih Mesin</option>
          {machines.map((m) => <option key={m.id} value={m.id}>{m.code} — {m.name}</option>)}
        </select>

        <div>
          <p className="text-sm font-medium mb-2">Checklist</p>
          <div className="space-y-2">
            {DEFAULT_ITEMS.map((item) => (
              <label key={item.id} className="flex items-center gap-3 p-3 bg-slate-50 rounded-lg cursor-pointer">
                <input
                  type="checkbox"
                  checked={!!checklist[item.id]}
                  onChange={() => toggleCheck(item.id)}
                  className="w-5 h-5"
                />
                <span className="text-sm">{item.label}</span>
                {checklist[item.id] && <span className="ml-auto text-red-500 text-xs">ISSUE</span>}
              </label>
            ))}
          </div>
        </div>

        <select className="w-full border rounded-lg px-3 py-2" value={severity} onChange={(e) => setSeverity(e.target.value)}>
          <option value="OK">OK</option>
          <option value="NORMAL">Normal</option>
          <option value="HIGH">High</option>
          <option value="CRITICAL">Critical</option>
        </select>

        <textarea className="w-full border rounded-lg px-3 py-2" rows={2} placeholder="Catatan" value={notes} onChange={(e) => setNotes(e.target.value)} />
        <textarea className="w-full border rounded-lg px-3 py-2" rows={2} placeholder="Rekomendasi tindakan" value={recommendation} onChange={(e) => setRecommendation(e.target.value)} />

        <label className="flex items-center gap-2 border border-dashed rounded-lg p-4 cursor-pointer hover:bg-slate-50">
          <Camera className="w-5 h-5 text-slate-400" />
          <span className="text-sm text-slate-600">{photo ? photo.name : 'Ambil / upload foto'}</span>
          <input type="file" accept="image/*" capture="environment" className="hidden" onChange={(e) => setPhoto(e.target.files?.[0])} />
        </label>

        <div className="flex gap-2">
          <button type="button" onClick={saveDraft} className="flex-1 border rounded-lg py-3 text-sm font-medium flex items-center justify-center gap-1">
            <Save className="w-4 h-4" /> Draft
          </button>
          <button type="button" disabled={saving} onClick={() => submit(true)} className="flex-1 border rounded-lg py-3 text-sm">
            Simpan Draft
          </button>
          <button type="button" disabled={saving} onClick={() => submit(false)} className="flex-1 bg-blue-600 text-white rounded-lg py-3 text-sm font-medium flex items-center justify-center gap-1">
            <Send className="w-4 h-4" /> Submit
          </button>
        </div>
      </div>

      <div className="space-y-2">
        <h3 className="font-semibold">Riwayat Inspeksi</h3>
        {inspections.slice(0, 10).map((ins) => (
          <div key={ins.id} className="bg-white border rounded-lg p-3 text-sm">
            <div className="flex justify-between">
              <span className="font-medium">{ins.machine?.code}</span>
              <span className={`text-xs px-2 py-0.5 rounded ${ins.severity === 'CRITICAL' ? 'bg-red-100' : 'bg-slate-100'}`}>
                {ins.severity}
              </span>
            </div>
            <p className="text-slate-500 text-xs">{new Date(ins.created_at).toLocaleString()} — {ins.status}</p>
            {ins.photo_url && <img src={`${mediaBase}${ins.photo_url}`} alt="" className="mt-2 rounded-lg max-h-32 object-cover" />}
          </div>
        ))}
      </div>
    </div>
  );
}
