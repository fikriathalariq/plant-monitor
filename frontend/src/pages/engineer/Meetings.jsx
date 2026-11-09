import React, { useState, useEffect } from 'react';
import { Calendar, CheckCircle } from 'lucide-react';
import { engineerApi } from '../../lib/engineerApi';

export default function Meetings() {
  const [meetings, setMeetings] = useState([]);
  const [actions, setActions] = useState([]);
  const [users, setUsers] = useState([]);
  const [machines, setMachines] = useState([]);
  const [tab, setTab] = useState('actions');
  const [showMeeting, setShowMeeting] = useState(false);
  const [showAction, setShowAction] = useState(false);
  const [selectedMeeting, setSelectedMeeting] = useState(null);
  const [meetingForm, setMeetingForm] = useState({
    title: '', meeting_date: '', participants: '', agenda: '', notes: '',
  });
  const [actionForm, setActionForm] = useState({
    description: '', assignee_id: '', due_date: '', machine_id: '', create_issue: true,
  });

  const load = async () => {
    const [mRes, aRes, uRes, machRes] = await Promise.all([
      engineerApi.listMeetings(),
      engineerApi.listActionItems(),
      engineerApi.listUsers(),
      engineerApi.listMachines(),
    ]);
    setMeetings(mRes.data.data || []);
    setActions(aRes.data.data || []);
    setUsers(uRes.data.data || []);
    setMachines(machRes.data.data || []);
  };

  useEffect(() => { load(); }, []);

  const createMeeting = async (e) => {
    e.preventDefault();
    await engineerApi.createMeeting(meetingForm);
    setShowMeeting(false);
    setMeetingForm({ title: '', meeting_date: '', participants: '', agenda: '', notes: '' });
    load();
  };

  const createAction = async (e) => {
    e.preventDefault();
    await engineerApi.createActionItem({
      ...actionForm,
      meeting_id: selectedMeeting?.id || null,
      assignee_id: actionForm.assignee_id ? Number(actionForm.assignee_id) : null,
      machine_id: actionForm.machine_id ? Number(actionForm.machine_id) : null,
    });
    setShowAction(false);
    setActionForm({ description: '', assignee_id: '', due_date: '', machine_id: '', create_issue: true });
    load();
  };

  const completeAction = async (id) => {
    await engineerApi.updateActionItem(id, { status: 'DONE' });
    load();
  };

  const openMeeting = async (id) => {
    const res = await engineerApi.getMeeting(id);
    setSelectedMeeting(res.data.data);
    setTab('detail');
  };

  const openActions = actions.filter((a) => a.status === 'OPEN');
  const overdue = openActions.filter((a) => a.due_date && new Date(a.due_date) < new Date());

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap justify-between gap-3">
        <div>
          <h2 className="text-2xl font-bold">Meeting & Action Items</h2>
          <p className="text-slate-500 text-sm">{overdue.length} overdue · {openActions.length} terbuka</p>
        </div>
        <div className="flex gap-2">
          <button type="button" onClick={() => setShowMeeting(!showMeeting)} className="border rounded-lg px-4 py-2 text-sm">
            + Rapat
          </button>
          <button type="button" onClick={() => setShowAction(!showAction)} className="bg-blue-600 text-white rounded-lg px-4 py-2 text-sm">
            + Action Item
          </button>
        </div>
      </div>

      {showMeeting && (
        <form onSubmit={createMeeting} className="bg-white border rounded-xl p-4 space-y-3 shadow-sm">
          <input className="w-full border rounded-lg px-3 py-2" placeholder="Judul rapat" value={meetingForm.title} onChange={(e) => setMeetingForm({ ...meetingForm, title: e.target.value })} required />
          <input type="date" className="w-full border rounded-lg px-3 py-2" value={meetingForm.meeting_date} onChange={(e) => setMeetingForm({ ...meetingForm, meeting_date: e.target.value })} required />
          <input className="w-full border rounded-lg px-3 py-2" placeholder="Peserta (pisah koma)" value={meetingForm.participants} onChange={(e) => setMeetingForm({ ...meetingForm, participants: e.target.value })} />
          <textarea className="w-full border rounded-lg px-3 py-2" placeholder="Agenda" rows={2} value={meetingForm.agenda} onChange={(e) => setMeetingForm({ ...meetingForm, agenda: e.target.value })} />
          <textarea className="w-full border rounded-lg px-3 py-2" placeholder="Catatan rapat" rows={3} value={meetingForm.notes} onChange={(e) => setMeetingForm({ ...meetingForm, notes: e.target.value })} />
          <button type="submit" className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm">Simpan Rapat</button>
        </form>
      )}

      {showAction && (
        <form onSubmit={createAction} className="bg-white border rounded-xl p-4 space-y-3 shadow-sm">
          <textarea className="w-full border rounded-lg px-3 py-2" placeholder="Deskripsi action item" rows={2} value={actionForm.description} onChange={(e) => setActionForm({ ...actionForm, description: e.target.value })} required />
          <div className="grid grid-cols-2 gap-3">
            <select className="border rounded-lg px-3 py-2" value={actionForm.assignee_id} onChange={(e) => setActionForm({ ...actionForm, assignee_id: e.target.value })}>
              <option value="">Assign ke</option>
              {users.map((u) => <option key={u.id} value={u.id}>{u.username}</option>)}
            </select>
            <input type="date" className="border rounded-lg px-3 py-2" value={actionForm.due_date} onChange={(e) => setActionForm({ ...actionForm, due_date: e.target.value })} />
            <select className="border rounded-lg px-3 py-2 col-span-2" value={actionForm.machine_id} onChange={(e) => setActionForm({ ...actionForm, machine_id: e.target.value })}>
              <option value="">Link ke mesin (opsional)</option>
              {machines.map((m) => <option key={m.id} value={m.id}>{m.code}</option>)}
            </select>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={actionForm.create_issue} onChange={(e) => setActionForm({ ...actionForm, create_issue: e.target.checked })} />
            Buat issue di triage queue
          </label>
          <button type="submit" className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm">Simpan Action</button>
        </form>
      )}

      <div className="flex gap-2">
        {['actions', 'meetings', 'detail'].map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium capitalize ${
              tab === t ? 'bg-blue-600 text-white' : 'bg-white border'
            }`}
          >
            {t === 'detail' && selectedMeeting ? selectedMeeting.title.slice(0, 15) : t}
          </button>
        ))}
      </div>

      {tab === 'actions' && (
        <div className="space-y-2">
          {openActions.map((a) => {
            const isOverdue = a.due_date && new Date(a.due_date) < new Date();
            return (
              <div key={a.id} className={`bg-white border rounded-xl p-4 flex justify-between items-start gap-3 ${isOverdue ? 'border-red-300' : ''}`}>
                <div>
                  <p className="font-medium text-sm">{a.description}</p>
                  <p className="text-xs text-slate-500 mt-1">
                    {a.assignee?.username || 'unassigned'}
                    {a.machine && ` · ${a.machine.code}`}
                    {a.due_date && ` · due ${a.due_date}`}
                  </p>
                  {a.meeting_title && <p className="text-xs text-blue-600 mt-1">Dari: {a.meeting_title}</p>}
                </div>
                <button type="button" onClick={() => completeAction(a.id)} className="text-green-600 shrink-0">
                  <CheckCircle className="w-5 h-5" />
                </button>
              </div>
            );
          })}
          {openActions.length === 0 && <p className="text-slate-500 text-center py-8">Semua action selesai</p>}
        </div>
      )}

      {tab === 'meetings' && (
        <div className="space-y-2">
          {meetings.map((m) => (
            <button
              key={m.id}
              type="button"
              onClick={() => openMeeting(m.id)}
              className="w-full text-left bg-white border rounded-xl p-4 hover:border-blue-300"
            >
              <div className="flex justify-between">
                <p className="font-medium">{m.title}</p>
                <span className="text-xs text-slate-500 flex items-center gap-1">
                  <Calendar className="w-3 h-3" /> {m.meeting_date}
                </span>
              </div>
              <p className="text-xs text-slate-500 mt-1">{m.action_count} action items</p>
            </button>
          ))}
        </div>
      )}

      {tab === 'detail' && selectedMeeting && (
        <div className="bg-white border rounded-xl p-4 space-y-4">
          <h3 className="font-bold text-lg">{selectedMeeting.title}</h3>
          <p className="text-sm text-slate-500">{selectedMeeting.meeting_date} · {selectedMeeting.participants}</p>
          <div>
            <p className="text-sm font-medium">Agenda</p>
            <p className="text-sm text-slate-600">{selectedMeeting.agenda || '-'}</p>
          </div>
          <div>
            <p className="text-sm font-medium">Catatan</p>
            <p className="text-sm text-slate-600 whitespace-pre-wrap">{selectedMeeting.notes || '-'}</p>
          </div>
          <div>
            <p className="text-sm font-medium mb-2">Action Items</p>
            {selectedMeeting.action_items?.map((a) => (
              <div key={a.id} className="text-sm border-b py-2 flex justify-between">
                <span>{a.description}</span>
                <span className="text-slate-500">{a.status}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
