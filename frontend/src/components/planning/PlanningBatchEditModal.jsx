import React, { useEffect, useMemo, useState } from 'react';
import { X } from 'lucide-react';
import {
  SHIFT_MINUTES,
  clockLabelToOffset,
  hasOverlap,
  offsetToClockLabel,
} from '../../lib/planningGeometry';

/**
 * Modal edit batch — AUTO: 3 durasi + program; MANUAL: 1 durasi Running.
 * onSave(updatedBatch) hanya commit ke state client — KECUALI utk batch "lanjutan"
 * (batch.isContinuation), yang datanya diambil dari `sourceStartOffsetMinutes`/`sourceBlocks`
 * (koordinat plan HARI SEBELUMNYA) dan disimpan langsung via PATCH cross-plan oleh pemanggil.
 * Lihat PLANNING_V3_IMPORT_FIX_AND_CROSSDAY_PLAN.md §10.
 */
export default function PlanningBatchEditModal({
  open,
  batch,
  machineCode,
  machineName,
  operationMode = 'AUTO',
  siblingBatches = [],
  programs = [],
  onClose,
  onSave,
  onDelete,
}) {
  const isManual = operationMode === 'MANUAL';
  const isContinuation = !!batch?.isContinuation;

  const [label, setLabel] = useState('');
  const [programId, setProgramId] = useState('');
  const [startClock, setStartClock] = useState('06:00');
  const [heat, setHeat] = useState(0);
  const [hold, setHold] = useState(0);
  const [cool, setCool] = useState(0);
  const [running, setRunning] = useState(0);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!open || !batch) return;
    setLabel(batch.label || '');
    setProgramId(batch.programId != null ? String(batch.programId) : '');
    // Batch "lanjutan" (continuation): tampilkan & edit struktur ASLI-nya (dari plan hari
    // sebelumnya), bukan tail yg dipotong di board hari ini.
    const effectiveStart = isContinuation
      ? (batch.sourceStartOffsetMinutes || 0)
      : (batch.startOffsetMinutes || 0);
    const effectiveBlocks = isContinuation ? (batch.sourceBlocks || []) : (batch.blocks || []);
    setStartClock(offsetToClockLabel(effectiveStart));
    if (isManual) {
      setRunning(effectiveBlocks?.[0]?.durationMinutes || 0);
      setHeat(0);
      setHold(0);
      setCool(0);
    } else {
      const byPhase = Object.fromEntries(
        effectiveBlocks.map((b) => [b.phase, b.durationMinutes || 0]),
      );
      setHeat(byPhase.HEAT || 0);
      setHold(byPhase.STEADY || 0);
      setCool(byPhase.COOL || 0);
      setRunning(0);
    }
    setError('');
  }, [open, batch, isManual, isContinuation]);

  const total = useMemo(() => {
    if (isManual) return Number(running) || 0;
    return (Number(heat) || 0) + (Number(hold) || 0) + (Number(cool) || 0);
  }, [isManual, heat, hold, cool, running]);

  const validate = () => {
    const start = clockLabelToOffset(startClock);
    if (start < 0 || start >= SHIFT_MINUTES) {
      return 'Jam mulai di luar rentang shift.';
    }
    if (isManual) {
      if (running < 1) return 'Durasi Running minimal 1 menit.';
    } else {
      const vals = [heat, hold, cool].map(Number);
      if (vals.some((v) => Number.isNaN(v) || v < 0)) return 'Durasi tidak boleh negatif.';
      if (vals.every((v) => v === 0)) return 'Minimal satu fase harus > 0 menit.';
      if (vals.some((v) => v > 0 && v < 1)) return 'Fase aktif minimal 1 menit.';
    }
    // Batch boleh meluber ke shift hari berikutnya (start + total > SHIFT_MINUTES) — hanya
    // durasi TOTAL per batch yang dibatasi 24 jam (anomali), sinkron dengan backend
    // (_validate_batches_payload di api_planning.py).
    if (total > SHIFT_MINUTES) {
      return `Total durasi batch melebihi 24 jam (${total} menit) — kemungkinan data anomali.`;
    }
    // Utk continuation, siblingBatches yg dipunya parent adalah batch board HARI INI (frame
    // yang berbeda dari plan sumber) — overlap thd sibling ASLI-nya divalidasi otoritatif oleh
    // backend saat PATCH (respons 400/409 akan tampil sbg error di sini).
    if (!isContinuation && hasOverlap(siblingBatches, batch.clientId, start, total)) {
      return 'Bentrok dengan proses lain di mesin ini.';
    }
    return '';
  };

  const handleProgramChange = (e) => {
    const val = e.target.value;
    setProgramId(val);
    if (!val) return;
    const prog = programs.find((p) => String(p.id) === val);
    if (!prog) return;
    setHeat(Math.round(Number(prog.durasi_heating_ideal) || 0));
    setHold(Math.round(Number(prog.durasi_keeping_ideal) || 0));
    setCool(Math.round(Number(prog.durasi_cooling_ideal) || 0));
  };

  const handleSave = () => {
    const err = validate();
    if (err) {
      setError(err);
      return;
    }
    const start = clockLabelToOffset(startClock);
    const newBlocks = isManual
      ? [{ phase: 'RUNNING', durationMinutes: Number(running) }]
      : [
        { phase: 'HEAT', durationMinutes: Number(heat) },
        { phase: 'STEADY', durationMinutes: Number(hold) },
        { phase: 'COOL', durationMinutes: Number(cool) },
      ];
    const programIdVal = isManual || !programId ? null : Number(programId);
    const programNameVal = isManual || !programId
      ? ''
      : (programs.find((p) => String(p.id) === programId)?.nama || '');
    const updated = isContinuation
      ? {
        ...batch,
        label: label.trim(),
        programId: programIdVal,
        programName: programNameVal,
        sourceStartOffsetMinutes: start,
        sourceBlocks: newBlocks,
      }
      : {
        ...batch,
        label: label.trim(),
        startOffsetMinutes: start,
        programId: programIdVal,
        programName: programNameVal,
        blocks: newBlocks,
      };
    onSave(updated);
  };

  if (!open || !batch) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/40 print:hidden">
      <div
        className="bg-white rounded-xl shadow-xl w-full max-w-md border border-gray-200"
        role="dialog"
        aria-modal="true"
        aria-labelledby="batch-edit-title"
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
          <div>
            <h2 id="batch-edit-title" className="text-sm font-semibold text-gray-900">
              Edit proses
            </h2>
            <p className="text-[11px] text-gray-500 mt-0.5">
              {machineName || machineCode}
              {' · '}
              {isManual ? 'Manual (ON/OFF)' : 'AUTO (Heat/Hold/Cool)'}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-500"
            aria-label="Tutup"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="px-4 py-3 space-y-3">
          {isContinuation && (
            <p className="text-[11px] text-sky-800 bg-sky-50 border border-sky-100 rounded-lg px-2.5 py-1.5">
              Proses lanjutan dari plan <strong>hari sebelumnya</strong> (meluber lewat jam 06:00).
              Perubahan di sini akan langsung disimpan ke plan sumbernya.
            </p>
          )}
          <label className="block">
            <span className="text-[11px] font-medium text-gray-600">Label</span>
            <input
              type="text"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              className="mt-1 w-full text-sm border border-gray-200 rounded-lg px-2.5 py-1.5"
              placeholder="Opsional"
            />
          </label>

          {!isManual && (
            <label className="block">
              <span className="text-[11px] font-medium text-gray-600">Program target</span>
              <select
                value={programId}
                onChange={handleProgramChange}
                className="mt-1 w-full text-sm border border-gray-200 rounded-lg px-2.5 py-1.5 bg-white"
              >
                <option value="">(Tidak ada program)</option>
                {programs.map((p) => (
                  <option key={p.id} value={p.id}>{p.nama}</option>
                ))}
              </select>
              <span className="block text-[10px] text-gray-400 mt-0.5">
                Memilih program menimpa durasi Heat/Hold/Cool dari Master Program.
              </span>
            </label>
          )}

          <label className="block">
            <span className="text-[11px] font-medium text-gray-600">Jam mulai</span>
            <input
              type="time"
              step={900}
              value={startClock}
              onChange={(e) => setStartClock(e.target.value)}
              className="mt-1 w-full text-sm border border-gray-200 rounded-lg px-2.5 py-1.5"
            />
            <span className="block text-[10px] text-gray-400 mt-0.5">
              Relatif shift mulai 06:00 (snap 15 menit disarankan).
            </span>
          </label>

          {isManual ? (
            <label className="block">
              <span className="text-[11px] font-medium text-gray-600">Durasi Running (menit)</span>
              <input
                type="number"
                min={1}
                value={running}
                onChange={(e) => setRunning(e.target.value)}
                className="mt-1 w-full text-sm border border-gray-200 rounded-lg px-2.5 py-1.5"
              />
            </label>
          ) : (
            <div className="grid grid-cols-3 gap-2">
              {[
                ['Heat', heat, setHeat],
                ['Hold', hold, setHold],
                ['Cool', cool, setCool],
              ].map(([name, val, setter]) => (
                <label key={name} className="block">
                  <span className="text-[11px] font-medium text-gray-600">{name} (m)</span>
                  <input
                    type="number"
                    min={0}
                    value={val}
                    onChange={(e) => setter(e.target.value)}
                    className="mt-1 w-full text-sm border border-gray-200 rounded-lg px-2.5 py-1.5"
                  />
                </label>
              ))}
            </div>
          )}

          <p className="text-xs text-gray-600 tabular-nums">
            Total: <span className="font-semibold">{total}</span> menit
            {total > 0 && (
              <span className="text-gray-400">
                {' '}(~{Math.floor(total / 60)}j {total % 60}m)
              </span>
            )}
          </p>
          {clockLabelToOffset(startClock) + total > SHIFT_MINUTES && (
            <p className="text-[11px] text-amber-700 bg-amber-50 border border-amber-100 rounded-lg px-2.5 py-1.5">
              Berlanjut {(clockLabelToOffset(startClock) + total) - SHIFT_MINUTES} menit ke shift hari berikutnya
              (selesai {offsetToClockLabel((clockLabelToOffset(startClock) + total) % SHIFT_MINUTES)} besok).
            </p>
          )}

          {error && (
            <p className="text-xs text-red-600 bg-red-50 border border-red-100 rounded-lg px-2.5 py-1.5">
              {error}
            </p>
          )}
        </div>

        <div className="flex items-center justify-between gap-2 px-4 py-3 border-t border-gray-100 bg-gray-50/80 rounded-b-xl">
          <button
            type="button"
            onClick={() => onDelete?.(batch.clientId)}
            className="text-xs text-red-600 hover:text-red-800 font-medium px-2 py-1.5"
          >
            {isContinuation ? 'Hapus proses (di plan sumber)' : 'Hapus proses'}
          </button>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={onClose}
              className="text-xs px-3 py-1.5 rounded-lg border border-gray-200 hover:bg-white"
            >
              Batal
            </button>
            <button
              type="button"
              onClick={handleSave}
              className="text-xs px-3 py-1.5 rounded-lg bg-indigo-600 text-white hover:bg-indigo-700"
            >
              Terapkan
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
