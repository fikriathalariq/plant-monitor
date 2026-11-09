import React from 'react';
import { useNavigate } from 'react-router-dom';
import { FileText, CheckCircle2, Clock, Activity, Gauge, ExternalLink, Flame, Check } from 'lucide-react';
import { useAcknowledgeMessageMutation } from '../../store/chatApi';

export const ReportShareCard = ({ metadata, isMe, onCloseChat }) => {
  const navigate = useNavigate();
  if (!metadata) return null;

  const { title, subtitle, metrics = {}, target_url, report_type } = metadata;

  const handleNavigate = () => {
    if (target_url) {
      if (onCloseChat && window.innerWidth < 768) {
        onCloseChat();
      }
      navigate(target_url);
    }
  };

  return (
    <div
      onClick={handleNavigate}
      className={`rounded-xl p-3 border transition-all cursor-pointer shadow-xs max-w-[280px] sm:max-w-xs ${
        isMe
          ? 'bg-blue-600/10 border-blue-200/50 hover:bg-blue-600/15 text-slate-800'
          : 'bg-white border-slate-200 hover:border-blue-400 hover:shadow-sm text-slate-800'
      }`}
    >
      <div className="flex items-start gap-2.5 mb-2">
        <div className="w-8 h-8 rounded-lg bg-blue-500/15 text-blue-600 flex items-center justify-center shrink-0">
          <FileText className="w-4 h-4" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-blue-100 text-blue-800 uppercase tracking-wider">
              {report_type ? report_type.replace(/_/g, ' ') : 'LAPORAN'}
            </span>
          </div>
          <h4 className="text-xs font-semibold text-slate-900 truncate mt-0.5" title={title}>
            {title || 'Laporan Produksi'}
          </h4>
          {subtitle && <p className="text-[11px] text-slate-500 truncate">{subtitle}</p>}
        </div>
      </div>

      {Object.keys(metrics).length > 0 && (
        <div className="grid grid-cols-2 gap-1.5 py-1.5 px-2 rounded-lg bg-slate-50 border border-slate-100 text-[11px] mb-2">
          {Object.entries(metrics).map(([k, v]) => (
            <div key={k} className="flex flex-col">
              <span className="text-[10px] text-slate-500 leading-tight">{k}</span>
              <span className="font-medium text-slate-800 truncate">{v}</span>
            </div>
          ))}
        </div>
      )}

      {target_url && (
        <div className="flex items-center justify-between pt-1 border-t border-slate-100 text-[11px] font-medium text-blue-600">
          <span>Buka Laporan</span>
          <ExternalLink className="w-3.5 h-3.5" />
        </div>
      )}
    </div>
  );
};

export const MachineSnapshotCard = ({ metadata, isMe }) => {
  if (!metadata) return null;
  const { machine_code, machine_name, status, temperature, speed, timestamp } = metadata;

  const isRunning = status === 'RUNNING';
  const isStop = status === 'STOP' || status === 'OFF';

  return (
    <div
      className={`rounded-xl p-3 border shadow-xs max-w-[280px] sm:max-w-xs ${
        isMe ? 'bg-indigo-600/10 border-indigo-200/50 text-slate-800' : 'bg-white border-slate-200 text-slate-800'
      }`}
    >
      <div className="flex items-center justify-between gap-2 mb-2 pb-1.5 border-b border-slate-100">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg bg-indigo-500/15 text-indigo-600 flex items-center justify-center shrink-0">
            <Activity className="w-4 h-4" />
          </div>
          <div>
            <div className="text-xs font-bold text-slate-900">{machine_code}</div>
            <div className="text-[10px] text-slate-500 truncate max-w-[120px]">{machine_name}</div>
          </div>
        </div>
        <span
          className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
            isRunning
              ? 'bg-emerald-100 text-emerald-800 border border-emerald-300'
              : isStop
              ? 'bg-rose-100 text-rose-800 border border-rose-300'
              : 'bg-amber-100 text-amber-800 border border-amber-300'
          }`}
        >
          {status || 'UNKNOWN'}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-2 text-xs">
        <div className="flex items-center gap-1.5 bg-slate-50 p-1.5 rounded border border-slate-100">
          <Flame className="w-3.5 h-3.5 text-amber-500" />
          <div>
            <div className="text-[10px] text-slate-500 leading-none">Suhu</div>
            <div className="font-semibold text-slate-800">
              {temperature !== undefined && temperature !== null ? `${temperature}°C` : '-'}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-1.5 bg-slate-50 p-1.5 rounded border border-slate-100">
          <Gauge className="w-3.5 h-3.5 text-blue-500" />
          <div>
            <div className="text-[10px] text-slate-500 leading-none">Speed</div>
            <div className="font-semibold text-slate-800">
              {speed !== undefined && speed !== null ? `${speed} m/m` : '-'}
            </div>
          </div>
        </div>
      </div>

      {timestamp && (
        <div className="mt-1.5 text-[10px] text-slate-400 flex items-center justify-end gap-1">
          <Clock className="w-3 h-3" />
          <span>Snapshot @ {timestamp}</span>
        </div>
      )}
    </div>
  );
};

export const ChartBookmarkCard = ({ metadata, isMe, onCloseChat }) => {
  const navigate = useNavigate();
  if (!metadata) return null;

  const { machine_code, time_label, start_time, end_time, note } = metadata;

  const handleOpenChart = () => {
    let url = `/grafik?machine=${encodeURIComponent(machine_code || '')}`;
    if (start_time && end_time) {
      url += `&start=${encodeURIComponent(start_time)}&end=${encodeURIComponent(end_time)}`;
    }
    if (onCloseChat && window.innerWidth < 768) {
      onCloseChat();
    }
    navigate(url);
  };

  return (
    <div
      onClick={handleOpenChart}
      className={`rounded-xl p-3 border transition-all cursor-pointer shadow-xs max-w-[280px] sm:max-w-xs ${
        isMe
          ? 'bg-emerald-600/10 border-emerald-200/50 hover:bg-emerald-600/15 text-slate-800'
          : 'bg-white border-slate-200 hover:border-emerald-400 hover:shadow-sm text-slate-800'
      }`}
    >
      <div className="flex items-center gap-2 mb-1.5">
        <div className="w-7 h-7 rounded-lg bg-emerald-500/15 text-emerald-600 flex items-center justify-center shrink-0">
          <Activity className="w-4 h-4" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-xs font-bold text-slate-900 truncate">
            {machine_code ? `Grafik ${machine_code}` : 'Bookmark Grafik'}
          </div>
          {time_label && <div className="text-[10px] text-slate-500 truncate">{time_label}</div>}
        </div>
      </div>

      {note && <p className="text-xs text-slate-600 mb-2 italic">"{note}"</p>}

      <div className="flex items-center justify-between pt-1 border-t border-slate-100 text-[11px] font-medium text-emerald-600">
        <span>Buka Titik Grafik</span>
        <ExternalLink className="w-3.5 h-3.5" />
      </div>
    </div>
  );
};

export const ActionCheckCard = ({ messageId, metadata, isMe }) => {
  const [acknowledge, { isLoading }] = useAcknowledgeMessageMutation();
  if (!metadata) return null;

  const isDone = !!metadata.acknowledged;

  const handleAcknowledge = async () => {
    if (isDone || isMe || isLoading) return;
    try {
      await acknowledge(messageId).unwrap();
    } catch (err) {
      console.error('Failed to acknowledge action:', err);
    }
  };

  return (
    <div
      className={`rounded-xl p-3 border shadow-xs max-w-[280px] sm:max-w-xs ${
        isDone
          ? 'bg-emerald-50/60 border-emerald-200 text-slate-800'
          : 'bg-amber-50/70 border-amber-200 text-slate-800'
      }`}
    >
      <div className="flex items-start gap-2 mb-2">
        <div
          className={`w-7 h-7 rounded-lg flex items-center justify-center shrink-0 ${
            isDone ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'
          }`}
        >
          {isDone ? <CheckCircle2 className="w-4 h-4" /> : <Clock className="w-4 h-4" />}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <span
              className={`text-[9px] font-bold px-1.5 py-0.5 rounded uppercase tracking-wider ${
                isDone ? 'bg-emerald-200 text-emerald-800' : 'bg-amber-200 text-amber-900'
              }`}
            >
              {isDone ? 'SUDAH DIKERJAKAN' : 'PERLU TINDAKAN'}
            </span>
          </div>
          <div className="text-xs font-semibold text-slate-900 mt-1">
            {metadata.task_name || 'Instruksi Lapangan'}
          </div>
        </div>
      </div>

      {isDone ? (
        <div className="bg-white/80 rounded-lg p-1.5 border border-emerald-100 text-[10px] text-emerald-800 flex items-center justify-between">
          <span className="font-medium truncate">Dikonfirmasi oleh {metadata.acknowledged_by || 'Operator'}</span>
          <span className="text-slate-400 shrink-0 ml-1">{metadata.acknowledged_at ? metadata.acknowledged_at.slice(11, 16) : ''}</span>
        </div>
      ) : isMe ? (
        <div className="text-[10px] text-amber-700 italic flex items-center gap-1">
          <Clock className="w-3 h-3" />
          <span>Menunggu konfirmasi penerima...</span>
        </div>
      ) : (
        <button
          onClick={handleAcknowledge}
          disabled={isLoading}
          className="w-full mt-1 py-1.5 px-3 rounded-lg bg-emerald-600 hover:bg-emerald-700 active:bg-emerald-800 text-white font-semibold text-xs flex items-center justify-center gap-1.5 shadow-xs transition-colors"
        >
          <Check className="w-3.5 h-3.5" />
          <span>{isLoading ? 'Memproses...' : 'Konfirmasi Sudah Dicek'}</span>
        </button>
      )}
    </div>
  );
};
