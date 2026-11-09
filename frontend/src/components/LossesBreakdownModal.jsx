import React, { useState, useMemo } from 'react';
import {
  X, Clock, PowerOff, Flame, Zap, Gauge, AlertTriangle, Lightbulb,
  ChevronDown, ChevronRight, ExternalLink, Wrench, Activity
} from 'lucide-react';

function inferGroupName(machineName = '') {
  const n = machineName.toUpperCase();
  if (n.startsWith('JR ') || n.startsWith('JR_')) return 'Jet Rapid';
  if (n.startsWith('JD ') || n.startsWith('JD_') || n.includes('JET MINI')) return 'Jet Dyeing';
  if (n.startsWith('ZET')) return 'Zet';
  if (n.includes('MERS')) return 'Mercerize';
  if (n.includes('SANFOR')) return 'Sanforize';
  if (n.includes('MONFONG') || n.includes('EHWA') || n.includes('STENTER')) return 'Stenter';
  if (n.includes('WASH')) return 'Washing';
  if (n.includes('PAD')) return 'Pad Steam';
  if (n.includes('BAKAR') || n.includes('SINGE')) return 'Bakar Bulu';
  return 'Lain-lain';
}

// Helper untuk mengestimasi rata-rata tekanan uap dari steam_series (fallback jika backend belum di-restart)
function estimatePressureFromSeries(processes, steamSeries) {
  if (!steamSeries || steamSeries.length === 0 || !processes || processes.length === 0) return null;
  const toShiftMin = (hhmm) => {
    if (!hhmm || typeof hhmm !== 'string' || !hhmm.includes(':')) return null;
    const [h, m] = hhmm.split(':').map(Number);
    if (isNaN(h) || isNaN(m)) return null;
    const total = h * 60 + m;
    return total < 360 ? total + 1440 : total; // 06:00 = 360
  };

  let sumPr = 0;
  let countPr = 0;

  processes.forEach((p) => {
    if (p.avg_steam_pressure != null) {
      sumPr += Number(p.avg_steam_pressure);
      countPr += 1;
      return;
    }
    const sMin = toShiftMin(p.start_time);
    const eMin = toShiftMin(p.end_time);
    if (sMin == null || eMin == null) return;
    const lo = Math.min(sMin, eMin);
    const hi = Math.max(sMin, eMin);
    steamSeries.forEach((pt) => {
      const ptMin = toShiftMin(pt.time);
      if (ptMin != null && ptMin >= lo && ptMin <= hi && pt.pressure > 0) {
        sumPr += Number(pt.pressure);
        countPr += 1;
      }
    });
  });

  return countPr > 0 ? +(sumPr / countPr).toFixed(2) : null;
}

function IndicatorBadges({ steamOkPct, avgPressure, effTotal, compact = false }) {
  if (steamOkPct == null && avgPressure == null && effTotal == null) {
    return <span className="text-[10px] text-gray-400 italic">Mesin Kontinu (Non-Batch)</span>;
  }

  const okTone =
    steamOkPct == null
      ? 'bg-gray-100 text-gray-600 border-gray-200'
      : steamOkPct >= 80
        ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
        : steamOkPct >= 50
          ? 'bg-amber-50 text-amber-700 border-amber-200'
          : 'bg-red-50 text-red-700 border-red-200';

  const prTone =
    avgPressure == null
      ? 'bg-gray-100 text-gray-600 border-gray-200'
      : avgPressure >= 3.8
        ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
        : avgPressure >= 3.5
          ? 'bg-amber-50 text-amber-700 border-amber-200'
          : 'bg-red-50 text-red-700 border-red-200';

  const effTone =
    effTotal == null
      ? 'bg-gray-100 text-gray-600 border-gray-200'
      : effTotal >= 85
        ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
        : effTotal >= 70
          ? 'bg-amber-50 text-amber-700 border-amber-200'
          : 'bg-red-50 text-red-700 border-red-200';

  const sz = compact ? 'text-[9.5px] px-1.5 py-0.5' : 'text-[10.5px] px-2 py-0.5';

  return (
    <div className="flex flex-wrap items-center gap-1">
      <span className={`inline-flex items-center gap-1 rounded border font-semibold ${sz} ${okTone}`} title="% Batch dengan Tekanan Uap Sehat (≥ 3.8 bar)">
        <span className="opacity-75 font-normal">% Sehat:</span>
        <b>{steamOkPct != null ? `${steamOkPct}%` : '-'}</b>
      </span>
      <span className={`inline-flex items-center gap-1 rounded border font-semibold ${sz} ${prTone}`} title="Rata-rata Tekanan Uap (bar)">
        <span className="opacity-75 font-normal">Avg Press:</span>
        <b>{avgPressure != null ? `${avgPressure} bar` : '-'}</b>
      </span>
      <span className={`inline-flex items-center gap-1 rounded border font-semibold ${sz} ${effTone}`} title="Rata-rata Efisiensi Durasi Proses (%)">
        <span className="opacity-75 font-normal">Eff Total:</span>
        <b>{effTotal != null ? `${effTotal}%` : '-'}</b>
      </span>
    </div>
  );
}

export default function LossesBreakdownModal({
  isOpen,
  onClose,
  categoryKey,
  reportData,
  boilerData,
  selectedDate,
}) {
  const [expandedGroups, setExpandedGroups] = useState({});

  const toggleGroup = (groupName) => {
    setExpandedGroups((prev) => ({
      ...prev,
      [groupName]: !prev[groupName],
    }));
  };

  const modalData = useMemo(() => {
    if (!reportData || !categoryKey) return null;

    // 1. Build machine -> group lookup map
    const idToGroup = {};
    const nameToGroup = {};

    (reportData.heatmap_groups || []).forEach((g) => {
      (g.machines || []).forEach((m) => {
        if (m.id) idToGroup[m.id] = g.group_name;
        if (m.name) nameToGroup[m.name] = g.group_name;
      });
    });

    (reportData.availability_groups || []).forEach((g) => {
      (g.machines || []).forEach((m) => {
        if (m.machine_id) idToGroup[m.machine_id] = g.group_name;
        if (m.machine_name) nameToGroup[m.machine_name] = g.group_name;
      });
    });

    const getGroup = (mId, mName, explicitGroup) => {
      if (explicitGroup && explicitGroup !== 'Lain-lain') return explicitGroup;
      if (mId && idToGroup[mId]) return idToGroup[mId];
      if (mName && nameToGroup[mName]) return nameToGroup[mName];
      return explicitGroup || inferGroupName(mName);
    };

    const effMachines = reportData.efficiency_summary?.machines || [];
    const availMachines = reportData.availability_summary?.machines || [];
    const downtimeList = reportData.downtime_ranking || [];
    const problemCats = reportData.efficiency_problems?.categories || [];
    const steamSeries = reportData.steam_series || [];

    // Map problem counts per machine name
    const machineProblems = {};
    problemCats.forEach((cat) => {
      (cat.processes || []).forEach((p) => {
        if (!machineProblems[p.machine_name]) {
          machineProblems[p.machine_name] = { PRESSURE_LOW: 0, HEATING_SLOW: 0, COOLING_SLOW: 0, START_TEMP_HIGH: 0, OTHERS: 0 };
        }
        machineProblems[p.machine_name][cat.code] = (machineProblems[p.machine_name][cat.code] || 0) + 1;
      });
    });

    // =========================================================================
    // CATEGORY 1: WAKTU INEFISIENSI (time_loss)
    // =========================================================================
    if (categoryKey === 'time_loss') {
      const groupMap = {};

      effMachines.forEach((m) => {
        const gName = getGroup(m.machine_id, m.machine_name, m.group_name);
        if (!groupMap[gName]) {
          groupMap[gName] = {
            group_name: gName,
            machine_count: 0,
            batch_count: 0,
            overrun_batches: 0,
            actual_mins: 0,
            ideal_mins: 0,
            loss_mins: 0,
            heat_delay_mins: 0,
            cool_delay_mins: 0,
            pressure_low_count: 0,
            start_high_count: 0,
            steam_ok_weighted: 0,
            pressure_weighted: 0,
            pressure_batches: 0,
            eff_weighted: 0,
            machines: [],
          };
        }

        const procs = m.processes || [];
        let mActual = m.actual_duration_mins || 0;
        let mIdeal = m.ideal_duration_mins || 0;
        let mLoss = m.pos_loss_time_mins || 0;
        let mHeatDelay = 0;
        let mCoolDelay = 0;
        let mOverrun = 0;

        procs.forEach((p) => {
          const dTotal = Number(p.delay_total) || 0;
          const dHeat = Number(p.delay_heat) || 0;
          const dCool = Number(p.delay_cool) || 0;
          if (dTotal > 0) mOverrun += 1;
          if (dHeat > 0) mHeatDelay += dHeat;
          if (dCool > 0) mCoolDelay += dCool;

          if (!m.actual_duration_mins) {
            const eff = Number(p.eff_total) || 100;
            const estActual = eff > 0 && eff !== 100 && dTotal !== 0
              ? Math.abs(dTotal / (1 - eff / 100))
              : (Number(p.total_duration) || 0);
            const estIdeal = Math.max(0, estActual - dTotal);
            mActual += estActual;
            mIdeal += estIdeal;
            if (dTotal > 0) mLoss += dTotal;
          }
        });

        const mAvgPr = m.avg_steam_pressure != null
          ? m.avg_steam_pressure
          : estimatePressureFromSeries(procs, steamSeries);

        const probs = machineProblems[m.machine_name] || {};
        const g = groupMap[gName];
        if (procs.length > 0) {
          g.machine_count += 1;
          g.batch_count += procs.length;
          g.overrun_batches += mOverrun;
          g.actual_mins += mActual;
          g.ideal_mins += mIdeal;
          g.loss_mins += mLoss;
          g.heat_delay_mins += mHeatDelay;
          g.cool_delay_mins += mCoolDelay;
          g.pressure_low_count += (probs.PRESSURE_LOW || 0);
          g.start_high_count += (probs.START_TEMP_HIGH || 0);
          if (m.steam_ok_pct != null) g.steam_ok_weighted += m.steam_ok_pct * procs.length;
          if (m.avg_eff != null) g.eff_weighted += m.avg_eff * procs.length;
          if (mAvgPr != null) {
            g.pressure_weighted += mAvgPr * procs.length;
            g.pressure_batches += procs.length;
          }

          g.machines.push({
            machine_id: m.machine_id,
            machine_name: m.machine_name,
            batch_count: `${procs.length} batch`,
            usage_val: +(mActual / 60).toFixed(1),
            ideal_val: +(mIdeal / 60).toFixed(1),
            loss_val: +(mLoss / 60).toFixed(1),
            loss_sub: `${Math.round(mLoss)} mnt`,
            steam_ok_pct: m.steam_ok_pct,
            avg_pressure: mAvgPr,
            eff_total: m.avg_eff,
            note: mHeatDelay >= mCoolDelay && mHeatDelay > 0
              ? `Delay Heating +${Math.round(mHeatDelay)}m`
              : mCoolDelay > 0
                ? `Delay Cooling +${Math.round(mCoolDelay)}m`
                : 'Normal',
          });
        }
      });

      const totalLossHours = reportData.losses_summary?.time_loss_hours || 0;
      const groups = Object.values(groupMap)
        .filter((g) => g.batch_count > 0)
        .map((g) => {
          const usageHours = +(g.actual_mins / 60).toFixed(1);
          const idealHours = +(g.ideal_mins / 60).toFixed(1);
          const lossHours = +(g.loss_mins / 60).toFixed(1);
          const sharePct = totalLossHours > 0 ? Math.min(100, +((lossHours / totalLossHours) * 100).toFixed(1)) : 0;
          const steamOkPct = g.batch_count > 0 ? +(g.steam_ok_weighted / g.batch_count).toFixed(1) : null;
          const avgPressure = g.pressure_batches > 0 ? +(g.pressure_weighted / g.pressure_batches).toFixed(2) : null;
          const effTotal = g.batch_count > 0 ? +(g.eff_weighted / g.batch_count).toFixed(1) : null;

          let cause = 'Durasi proses terkendali';
          let action = 'Pertahankan kedisiplinan operator terhadap standar kurva program.';
          if (lossHours > 0) {
            if ((avgPressure != null && avgPressure < 3.8) || (steamOkPct != null && steamOkPct < 80)) {
              cause = `Suplai uap kurang sehat (% Sehat: ${steamOkPct ?? '-'}%, Avg Press: ${avgPressure ?? '-'} bar) memicu Heating lambat (+${Math.round(g.heat_delay_mins)} mnt) dan menurunkan Eff Total ke ${effTotal ?? '-'}%`;
              action = 'Stabilkan tekanan header uap ≥ 3.8 bar dan terapkan staggering jadwal start Heating antar-mesin besar.';
            } else if (g.heat_delay_mins >= g.cool_delay_mins && g.heat_delay_mins > 0) {
              cause = `Suplai uap sehat (Avg Press: ${avgPressure ?? '-'} bar), namun Heating/Holding molor +${Math.round(g.heat_delay_mins)} mnt sehingga Eff Total turun ke ${effTotal ?? '-'}%`;
              action = 'Periksa bukaan control valve uap, strainer & steam trap pada mesin terkait, serta percepat waktu tunggu cek sampel warna.';
            } else if (g.cool_delay_mins > 0) {
              cause = `Suplai uap sehat, namun fase Cooling lambat (+${Math.round(g.cool_delay_mins)} mnt) menekan Eff Total ke ${effTotal ?? '-'}%`;
              action = 'Cek tekanan & suhu air pendingin (cooling water), bersihkan kerak (scaling) pada Heat Exchanger, dan pastikan jalur drain lancar.';
            }
          }

          g.machines.sort((a, b) => b.loss_val - a.loss_val);
          return {
            ...g,
            usage_val: usageHours,
            ideal_val: idealHours,
            loss_val: lossHours,
            share_pct: sharePct,
            steam_ok_pct: steamOkPct,
            avg_pressure: avgPressure,
            eff_total: effTotal,
            cause,
            action,
          };
        })
        .sort((a, b) => b.loss_val - a.loss_val);

      const sumUsage = +groups.reduce((s, g) => s + g.usage_val, 0).toFixed(1);
      const sumIdeal = +groups.reduce((s, g) => s + g.ideal_val, 0).toFixed(1);

      return {
        title: 'Rincian Waktu Inefisiensi per Machine Group',
        subtitle: 'Korelasi % Sehat Uap, Avg Pressure, dan Eff Total (%) terhadap keterlambatan durasi proses',
        unit: 'Jam',
        showIndicators: true,
        icon: <Clock className="w-5 h-5 text-red-600" />,
        usageLabel: 'Total Durasi Aktual',
        idealLabel: 'Total Durasi Ideal',
        lossLabel: 'Total Waktu Inefisiensi',
        totalUsage: sumUsage,
        totalIdeal: sumIdeal,
        totalLoss: totalLossHours,
        groups,
      };
    }

    // =========================================================================
    // CATEGORY 2: DOWNTIME / AVAILABILITY (avail_loss)
    // =========================================================================
    if (categoryKey === 'avail_loss') {
      const groupMap = {};
      const downtimeById = {};
      downtimeList.forEach((d) => {
        downtimeById[d.machine_id] = d;
      });
      const changeoverById = {};
      effMachines.forEach((m) => {
        if (m.avg_changeover_minutes != null) {
          changeoverById[m.machine_id] = m.avg_changeover_minutes;
        }
      });

      availMachines.forEach((m) => {
        const gName = getGroup(m.machine_id, m.machine_name, m.group_name);
        if (!groupMap[gName]) {
          groupMap[gName] = {
            group_name: gName,
            machine_count: 0,
            uptime_hours: 0,
            capacity_hours: 0,
            loss_hours: 0,
            total_avail_pct: 0,
            changeover_list: [],
            stop_events: 0,
            machines: [],
          };
        }

        const upHours = +((m.uptime_minutes || 0) / 60).toFixed(1);
        const capHours = 24.0;
        const lossHours = +(((100 - (m.availability || 0)) / 100) * 24).toFixed(1);
        const dtInfo = downtimeById[m.machine_id];
        const coMins = changeoverById[m.machine_id];

        const g = groupMap[gName];
        g.machine_count += 1;
        g.uptime_hours += upHours;
        g.capacity_hours += capHours;
        g.loss_hours += lossHours;
        g.total_avail_pct += (m.availability || 0);
        if (coMins != null) g.changeover_list.push(coMins);
        if (dtInfo?.stop_events) g.stop_events += dtInfo.stop_events;

        g.machines.push({
          machine_id: m.machine_id,
          machine_name: m.machine_name,
          batch_count: dtInfo ? `${dtInfo.stop_events}x stop` : '-',
          usage_val: upHours,
          ideal_val: capHours,
          loss_val: lossHours,
          loss_sub: `Avail: ${m.availability}%`,
          eff_pct: m.availability,
          note: coMins != null ? `Changeover rata-rata: ${coMins} mnt` : `Uptime: ${m.uptime_str}`,
        });
      });

      const totalLossHours = reportData.losses_summary?.avail_loss_hours || 0;
      const groups = Object.values(groupMap)
        .map((g) => {
          const usageHours = +g.uptime_hours.toFixed(1);
          const idealHours = +g.capacity_hours.toFixed(1);
          const lossHours = +g.loss_hours.toFixed(1);
          const avgAvail = g.machine_count > 0 ? +(g.total_avail_pct / g.machine_count).toFixed(1) : 0;
          const avgCo = g.changeover_list.length > 0
            ? Math.round(g.changeover_list.reduce((a, b) => a + b, 0) / g.changeover_list.length)
            : null;
          const sharePct = totalLossHours > 0 ? Math.min(100, +((lossHours / totalLossHours) * 100).toFixed(1)) : 0;

          let cause = `Utilisasi grup ${avgAvail}% (${g.machine_count} mesin aktif)`;
          let action = 'Pertahankan koordinasi serah-terima shift dan kesiapan gerobak kain.';
          if (avgCo != null && avgCo > 45) {
            cause = `Jeda pergantian batch (Changeover) tinggi: rata-rata ${avgCo} menit (${g.stop_events}x mesin berhenti)`;
            action = 'Lakukan pre-staging kain & penimbangan obat/dyestuff sebelum batch sebelumnya selesai agar mesin langsung lanjut proses tanpa jeda tunggu lama.';
          } else if (avgAvail < 55) {
            cause = `Utilisasi mesin rendah (rata-rata hanya ${avgAvail}% dari kapasitas 24 jam)`;
            action = 'Evaluasi penjadwalan PPIC untuk menggabungkan lot pada mesin prioritas atau jadwalkan preventive maintenance terpusat pada mesin yang idle.';
          } else if (lossHours > 5) {
            cause = `Total waktu tunggu / mesin berhenti mencapai ${lossHours} jam (${g.stop_events}x stop event)`;
            action = 'Kurangi waktu tunggu konfirmasi lab/matching warna dan percepat proses bongkar-muat kain (loading/unloading).';
          }

          g.machines.sort((a, b) => b.loss_val - a.loss_val);
          return {
            ...g,
            usage_val: usageHours,
            ideal_val: idealHours,
            loss_val: lossHours,
            share_pct: sharePct,
            cause,
            action,
          };
        })
        .sort((a, b) => b.loss_val - a.loss_val);

      const sumUsage = +groups.reduce((s, g) => s + g.usage_val, 0).toFixed(1);
      const sumIdeal = +groups.reduce((s, g) => s + g.ideal_val, 0).toFixed(1);

      return {
        title: 'Rincian Downtime (Availability Loss) per Machine Group',
        subtitle: 'Total jam mesin berhenti / idle dibandingkan kapasitas jam kerja 24 jam per mesin aktif',
        unit: 'Jam',
        showIndicators: false,
        icon: <PowerOff className="w-5 h-5 text-red-600" />,
        usageLabel: 'Total Jam Jalan (Uptime)',
        idealLabel: 'Total Kapasitas (24h × Mesin)',
        lossLabel: 'Total Downtime (Idle)',
        totalUsage: sumUsage,
        totalIdeal: sumIdeal,
        totalLoss: totalLossHours,
        groups,
      };
    }

    // =========================================================================
    // CATEGORY 3: LOSS STEAM (steam_loss)
    // =========================================================================
    if (categoryKey === 'steam_loss') {
      const groupMap = {};

      effMachines.forEach((m) => {
        const gName = getGroup(m.machine_id, m.machine_name, m.group_name);
        if (!groupMap[gName]) {
          groupMap[gName] = {
            group_name: gName,
            machine_count: 0,
            batch_count: 0,
            usage_kg: 0,
            ideal_kg: 0,
            loss_kg: 0,
            loss_rp: 0,
            steam_ok_weighted: 0,
            pressure_weighted: 0,
            pressure_batches: 0,
            eff_weighted: 0,
            heat_delay_mins: 0,
            machines: [],
          };
        }

        const procs = m.processes || [];
        const usageKg = m.steam_usage || 0;
        const lossKg = m.steam_loss_kg || 0;
        const idealKg = m.steam_ideal_kg != null && m.steam_ideal_kg > 0
          ? m.steam_ideal_kg
          : Math.max(0, +(usageKg - lossKg).toFixed(1));
        const lossRp = m.steam_loss_rp || Math.round(lossKg * 350);

        const mAvgPr = m.avg_steam_pressure != null
          ? m.avg_steam_pressure
          : estimatePressureFromSeries(procs, steamSeries);

        let mHeatDelay = m.delay_heat_mins || 0;
        if (!m.delay_heat_mins && procs.length > 0) {
          procs.forEach((p) => {
            if ((Number(p.delay_heat) || 0) > 0) mHeatDelay += Number(p.delay_heat);
          });
        }

        const g = groupMap[gName];
        if (usageKg > 0 || lossKg > 0) {
          g.machine_count += 1;
          g.batch_count += procs.length;
          g.usage_kg += usageKg;
          g.ideal_kg += idealKg;
          g.loss_kg += lossKg;
          g.loss_rp += lossRp;
          g.heat_delay_mins += mHeatDelay;

          if (procs.length > 0) {
            if (m.steam_ok_pct != null) g.steam_ok_weighted += m.steam_ok_pct * procs.length;
            if (m.avg_eff != null) g.eff_weighted += m.avg_eff * procs.length;
            if (mAvgPr != null) {
              g.pressure_weighted += mAvgPr * procs.length;
              g.pressure_batches += procs.length;
            }
          }

          g.machines.push({
            machine_id: m.machine_id,
            machine_name: m.machine_name,
            batch_count: procs.length ? `${procs.length} batch` : 'Kontinu',
            usage_val: +usageKg.toFixed(1),
            ideal_val: +idealKg.toFixed(1),
            loss_val: +lossKg.toFixed(1),
            loss_sub: lossRp > 0 ? `Rp ${lossRp.toLocaleString('id-ID')}` : 'Rp 0',
            steam_ok_pct: m.steam_ok_pct,
            avg_pressure: mAvgPr,
            eff_total: m.avg_eff,
            note: mHeatDelay > 0 ? `Delay Heating: +${Math.round(mHeatDelay)} mnt` : 'Heating Normal',
          });
        }
      });

      const totalLossKg = reportData.losses_summary?.steam_loss_kg || 0;
      const groups = Object.values(groupMap)
        .filter((g) => g.usage_kg > 0 || g.loss_kg > 0)
        .map((g) => {
          const usageVal = +g.usage_kg.toFixed(1);
          const idealVal = +g.ideal_kg.toFixed(1);
          const lossVal = +g.loss_kg.toFixed(1);
          const lossPct = usageVal > 0 ? +((lossVal / usageVal) * 100).toFixed(1) : 0;
          const sharePct = totalLossKg > 0 ? Math.min(100, +((lossVal / totalLossKg) * 100).toFixed(1)) : 0;
          const steamOkPct = g.batch_count > 0 ? +(g.steam_ok_weighted / g.batch_count).toFixed(1) : null;
          const avgPressure = g.pressure_batches > 0 ? +(g.pressure_weighted / g.pressure_batches).toFixed(2) : null;
          const effTotal = g.batch_count > 0 ? +(g.eff_weighted / g.batch_count).toFixed(1) : null;

          let cause = 'Konsumsi uap sesuai target Best-of-Best';
          let action = 'Pertahankan pemeliharaan rutin steam trap dan isolasi pipa.';
          if (lossVal > 0) {
            if ((avgPressure != null && avgPressure < 3.8) || (steamOkPct != null && steamOkPct < 80)) {
              cause = `Suplai tekanan uap rendah (Avg Press: ${avgPressure ?? '-'} bar, % Sehat: ${steamOkPct ?? '-'}%) menurunkan Eff Total ke ${effTotal ?? '-'}% dan memicu kondensasi/heating panjang (+${lossVal.toLocaleString('id-ID')} kg)`;
              action = 'Stabilkan tekanan header uap ≥ 3.8 bar, periksa pembuangan kondensat di jalur utama, dan hindari puncak tarikan uap serentak.';
            } else if (effTotal != null && effTotal < 85) {
              cause = `Suplai uap sehat (Avg Press: ${avgPressure ?? '-'} bar, % Sehat: ${steamOkPct ?? '-'}%), namun Eff Total rendah (${effTotal}%) sehingga uap terbuang selama fase Heating/Holding molor (+${lossVal.toLocaleString('id-ID')} kg)`;
              action = 'Inspeksi kebocoran Steam Trap (trap los/jebol) dan katup by-pass uap pada mesin penyumbang loss tertinggi, serta pangkas waktu holding suhu 130°C.';
            } else {
              cause = `Deviasi pemakaian uap +${lossVal.toLocaleString('id-ID')} kg (${lossPct}% dari pemakaian grup)`;
              action = 'Pastikan level pengisian air (Liquor Ratio) tidak berlebih dan kurangi waktu tunggu sampel pada suhu tinggi.';
            }
          }

          g.machines.sort((a, b) => b.loss_val - a.loss_val);
          return {
            ...g,
            usage_val: usageVal,
            ideal_val: idealVal,
            loss_val: lossVal,
            loss_rp: Math.round(g.loss_rp),
            share_pct: sharePct,
            steam_ok_pct: steamOkPct,
            avg_pressure: avgPressure,
            eff_total: effTotal,
            cause,
            action,
          };
        })
        .sort((a, b) => b.loss_val - a.loss_val);

      const sumUsage = +groups.reduce((s, g) => s + g.usage_val, 0).toFixed(1);
      const sumIdeal = +groups.reduce((s, g) => s + g.ideal_val, 0).toFixed(1);
      const sumLossRp = groups.reduce((s, g) => s + (g.loss_rp || 0), 0);

      return {
        title: 'Rincian Loss Steam per Machine Group',
        subtitle: 'Analisis korelasi % Sehat Uap, Avg Pressure, dan Eff Total (%) terhadap pemborosan uap',
        unit: 'Kg',
        showIndicators: true,
        icon: <Flame className="w-5 h-5 text-red-600" />,
        usageLabel: 'Total Pemakaian Steam',
        idealLabel: 'Target Steam Ideal (BoB)',
        lossLabel: 'Total Loss Steam',
        totalUsage: sumUsage,
        totalIdeal: sumIdeal,
        totalLoss: totalLossKg,
        totalLossRp: sumLossRp,
        groups,
      };
    }

    // =========================================================================
    // CATEGORY 4: LOSS LISTRIK (power_loss) - 3-INDICATOR CORRELATION MATRIX
    // =========================================================================
    if (categoryKey === 'power_loss') {
      const groupMap = {};

      effMachines.forEach((m) => {
        const gName = getGroup(m.machine_id, m.machine_name, m.group_name);
        if (!groupMap[gName]) {
          groupMap[gName] = {
            group_name: gName,
            machine_count: 0,
            batch_count: 0,
            usage_kwh: 0,
            lwbp_kwh: 0,
            wbp_kwh: 0,
            ideal_kwh: 0,
            loss_kwh: 0,
            loss_rp: 0,
            steam_ok_weighted: 0,
            pressure_weighted: 0,
            pressure_batches: 0,
            eff_weighted: 0,
            heat_delay_mins: 0,
            cool_delay_mins: 0,
            machines: [],
          };
        }

        const procs = m.processes || [];
        const usageKwh = m.power_usage || 0;
        const lwbpKwh = m.total_power_lwbp_kwh || 0;
        const wbpKwh = m.total_power_wbp_kwh || 0;
        const idealKwh = m.power_ideal_kwh != null && m.power_ideal_kwh > 0
          ? m.power_ideal_kwh
          : (m.power_eff ? +((usageKwh * m.power_eff) / 100).toFixed(1) : usageKwh);
        const lossKwh = m.power_loss_kwh != null
          ? m.power_loss_kwh
          : Math.max(0, +(usageKwh - idealKwh).toFixed(1));
        const lossRp = m.power_loss_rp != null
          ? m.power_loss_rp
          : Math.round(lossKwh * 1035.8);

        const mAvgPr = m.avg_steam_pressure != null
          ? m.avg_steam_pressure
          : estimatePressureFromSeries(procs, steamSeries);

        let mHeatDelay = m.delay_heat_mins || 0;
        let mCoolDelay = m.delay_cool_mins || 0;
        if (!m.delay_heat_mins && !m.delay_cool_mins && procs.length > 0) {
          procs.forEach((p) => {
            if ((Number(p.delay_heat) || 0) > 0) mHeatDelay += Number(p.delay_heat);
            if ((Number(p.delay_cool) || 0) > 0) mCoolDelay += Number(p.delay_cool);
          });
        }

        const g = groupMap[gName];
        if (usageKwh > 0 || lossKwh > 0) {
          g.machine_count += 1;
          g.batch_count += procs.length;
          g.usage_kwh += usageKwh;
          g.lwbp_kwh += lwbpKwh;
          g.wbp_kwh += wbpKwh;
          g.ideal_kwh += idealKwh;
          g.loss_kwh += lossKwh;
          g.loss_rp += lossRp;
          g.heat_delay_mins += mHeatDelay;
          g.cool_delay_mins += mCoolDelay;

          if (procs.length > 0) {
            if (m.steam_ok_pct != null) g.steam_ok_weighted += m.steam_ok_pct * procs.length;
            if (m.avg_eff != null) g.eff_weighted += m.avg_eff * procs.length;
            if (mAvgPr != null) {
              g.pressure_weighted += mAvgPr * procs.length;
              g.pressure_batches += procs.length;
            }
          }

          g.machines.push({
            machine_id: m.machine_id,
            machine_name: m.machine_name,
            batch_count: procs.length ? `${procs.length} batch` : 'Kontinu',
            usage_val: +usageKwh.toFixed(1),
            ideal_val: +idealKwh.toFixed(1),
            loss_val: +lossKwh.toFixed(1),
            loss_sub: lossRp > 0 ? `Rp ${lossRp.toLocaleString('id-ID')}` : 'Rp 0',
            steam_ok_pct: m.steam_ok_pct,
            avg_pressure: mAvgPr,
            eff_total: m.avg_eff,
            note: `LWBP: ${lwbpKwh.toFixed(1)} | WBP: ${wbpKwh.toFixed(1)} kWh`,
          });
        }
      });

      const totalLossKwh = reportData.losses_summary?.power_loss_kwh || 0;
      const groups = Object.values(groupMap)
        .filter((g) => g.usage_kwh > 0 || g.loss_kwh > 0)
        .map((g) => {
          const usageVal = +g.usage_kwh.toFixed(1);
          const idealVal = +g.ideal_kwh.toFixed(1);
          const lossVal = +g.loss_kwh.toFixed(1);
          const wbpVal = +g.wbp_kwh.toFixed(1);
          const lwbpVal = +g.lwbp_kwh.toFixed(1);
          const wbpPct = usageVal > 0 ? +((wbpVal / usageVal) * 100).toFixed(1) : 0;
          const sharePct = totalLossKwh > 0 ? Math.min(100, +((lossVal / totalLossKwh) * 100).toFixed(1)) : 0;

          const steamOkPct = g.batch_count > 0 ? +(g.steam_ok_weighted / g.batch_count).toFixed(1) : null;
          const avgPressure = g.pressure_batches > 0 ? +(g.pressure_weighted / g.pressure_batches).toFixed(2) : null;
          const effTotal = g.batch_count > 0 ? +(g.eff_weighted / g.batch_count).toFixed(1) : null;
          const heatDelay = Math.round(g.heat_delay_mins);
          const coolDelay = Math.round(g.cool_delay_mins);

          const isSteamUnhealthy = (avgPressure != null && avgPressure < 3.8) || (steamOkPct != null && steamOkPct < 80);
          const isEffLow = effTotal != null && effTotal < 85;

          let scenarioBadge = null;
          let cause = '';
          let action = '';

          if (g.batch_count === 0) {
            // Mesin Kontinu (Non-Batch)
            scenarioBadge = { text: 'Operasi Mesin Kontinu', tone: 'bg-blue-50 text-blue-700 border-blue-200' };
            cause = `Mesin kontinu beroperasi dengan konsumsi LWBP ${lwbpVal} kWh & WBP ${wbpVal} kWh (${wbpPct}% di jam puncak).`;
            action = wbpPct >= 22
              ? 'Optimalkan jadwal proses kontinu agar meminimalkan operasi motor berdaya besar pada jam tarif puncak WBP (17:00–22:00).'
              : 'Pastikan motor sirkulasi/exhaust dimatikan saat jeda tunggu pergantian partai kain.';
          } else if (lossVal > 0 && isSteamUnhealthy && isEffLow) {
            // SKENARIO 1: Masalah Hulu / Suplai Uap Drop -> Eff Total Turun -> Listrik Bocor
            scenarioBadge = { text: 'Skenario 1: Efek Domino Suplai Uap Drop', tone: 'bg-red-100 text-red-800 border-red-200' };
            cause = `Avg Pressure rendah (${avgPressure ?? '-'} bar) & % Sehat Uap hanya ${steamOkPct ?? '-'}% menyebabkan Eff Total jatuh ke ${effTotal ?? '-'}% (Heating molor +${heatDelay} mnt). Pompa sirkulasi listrik terpaksa berputar lebih lama (+${lossVal} kWh) karena menunggu suhu naik.`;
            action = 'Akar masalah di suplai uap (bukan motor/operator). Stabilkan tekanan header uap ≥ 3.8 bar (% Sehat ≥ 80%) dan terapkan staggering jadwal start Heating antar-mesin besar.';
          } else if (lossVal > 0 && !isSteamUnhealthy && isEffLow && heatDelay >= coolDelay) {
            // SKENARIO 2: Suplai Uap Sehat, Tapi Heating/Holding Mesin Lambat -> Eff Total Turun
            scenarioBadge = { text: 'Skenario 2: Uap Sehat, Kendala Internal Mesin / Tunggu Operasi', tone: 'bg-amber-100 text-amber-800 border-amber-200' };
            cause = `Suplai uap pipa utama sehat (% Sehat: ${steamOkPct ?? '-'}%, Avg Press: ${avgPressure ?? '-'} bar), namun Eff Total tetap rendah (${effTotal ?? '-'}%) akibat fase Heating/Holding molor +${heatDelay} mnt sehingga membuang listrik +${lossVal} kWh.`;
            action = 'Karena tekanan uap sudah bagus, periksa komponen internal mesin (bukaan control valve uap, strainer mampet, steam trap) serta pangkas waktu tunggu matching warna lab / add-on obat saat pompa menyala.';
          } else if (lossVal > 0 && !isSteamUnhealthy && isEffLow && coolDelay > heatDelay) {
            // SKENARIO 3: Suplai Uap Sehat, Tapi Fase Cooling Lambat -> Eff Total Turun
            scenarioBadge = { text: 'Skenario 3: Uap Sehat, Kendala Sistem Pendinginan (Cooling)', tone: 'bg-sky-100 text-sky-800 border-sky-200' };
            cause = `Suplai uap sehat (% Sehat: ${steamOkPct ?? '-'}%, Avg Press: ${avgPressure ?? '-'} bar), namun Eff Total turun ke ${effTotal ?? '-'}% karena fase Cooling lambat (+${coolDelay} mnt) yang menahan pompa listrik tetap menyala (+${lossVal} kWh).`;
            action = 'Periksa debit & suhu suplai air pendingin (cooling water), lakukan descaling (pembersihan kerak) pada Heat Exchanger (HE) mesin, dan pastikan katup drain lancar.';
          } else if (lossVal > 0) {
            // SKENARIO 4A: Ketiga indikator relatif sehat, namun ada deviasi durasi minor pada beberapa batch
            scenarioBadge = { text: 'Skenario 4: Parameter Utama Sehat (Deviasi Minor / Jam WBP)', tone: 'bg-emerald-50 text-emerald-800 border-emerald-200' };
            cause = `Indikator rata-rata grup sehat (% Sehat: ${steamOkPct ?? '-'}%, Avg Press: ${avgPressure ?? '-'} bar, Eff Total: ${effTotal ?? '-'}%), namun terdapat keterlambatan minor (+${lossVal} kWh)${wbpPct >= 20 ? ` dengan ${wbpPct}% (${wbpVal} kWh) pemakaian di jam WBP (17:00–22:00)` : ''}.`;
            action = 'Segera matikan pompa utama begitu proses selesai (hindari mesin menyala saat tunggu bongkar kain) dan geser beban proses besar keluar dari jam tarif WBP (17:00–22:00).';
          } else {
            // SKENARIO 4B: Zero Loss kWh
            scenarioBadge = { text: 'Optimal: Efisiensi & Suplai Uap Sehat', tone: 'bg-emerald-100 text-emerald-800 border-emerald-200' };
            cause = `Ketiga parameter optimal (% Sehat: ${steamOkPct ?? '-'}%, Avg Press: ${avgPressure ?? '-'} bar, Eff Total: ${effTotal ?? '-'}%) tanpa loss kWh (LWBP: ${lwbpVal} | WBP: ${wbpVal} kWh).`;
            action = 'Pertahankan standar operasional mesin dan penjadwalan di luar jam puncak WBP.';
          }

          g.machines.sort((a, b) => b.loss_val - a.loss_val);
          return {
            ...g,
            usage_val: usageVal,
            ideal_val: idealVal,
            loss_val: lossVal,
            lwbp_val: lwbpVal,
            wbp_val: wbpVal,
            loss_rp: Math.round(g.loss_rp),
            share_pct: sharePct,
            steam_ok_pct: steamOkPct,
            avg_pressure: avgPressure,
            eff_total: effTotal,
            scenario_badge: scenarioBadge,
            cause,
            action,
          };
        })
        .sort((a, b) => b.loss_val - a.loss_val);

      const sumUsage = +groups.reduce((s, g) => s + g.usage_val, 0).toFixed(1);
      const sumIdeal = +groups.reduce((s, g) => s + g.ideal_val, 0).toFixed(1);
      const sumLossRp = groups.reduce((s, g) => s + (g.loss_rp || 0), 0);

      return {
        title: 'Rincian Loss Listrik per Machine Group',
        subtitle: 'Analisis Akar Masalah (Root-Cause) berdasarkan korelasi: 1) % Sehat Uap, 2) Avg Pressure, dan 3) Eff Total (%)',
        unit: 'kWh',
        showIndicators: true,
        icon: <Zap className="w-5 h-5 text-red-600" />,
        usageLabel: 'Total Pemakaian Listrik',
        idealLabel: 'Target Listrik Ideal',
        lossLabel: 'Total Loss Listrik',
        totalUsage: sumUsage,
        totalIdeal: sumIdeal,
        totalLoss: totalLossKwh,
        totalLossRp: sumLossRp,
        groups,
      };
    }

    // =========================================================================
    // CATEGORY 5: SFC BATU BARA (sfc_loss)
    // =========================================================================
    if (categoryKey === 'sfc_loss') {
      const sfc = boilerData?.kpi_summary?.specific_fuel_consumption;
      const totalSteamTon = boilerData?.kpi_summary?.total_steam_usage_kg
        ? +(boilerData.kpi_summary.total_steam_usage_kg / 1000).toFixed(1)
        : +((reportData.total_steam_usage || 0) / 1000).toFixed(1);
      const idealPrPct = boilerData?.kpi_summary?.pressure_ideal_percent ?? '-';

      return {
        title: 'Analisis Specific Fuel Consumption (SFC Batu Bara)',
        subtitle: 'Rasio efisiensi pembakaran batu bara boiler terhadap distribusi uap ke Machine Group',
        unit: 'Ratio',
        showIndicators: false,
        icon: <Gauge className="w-5 h-5 text-red-600" />,
        usageLabel: 'Total Produksi Steam',
        idealLabel: 'Kestabilan Tekanan Ideal',
        lossLabel: 'Rasio SFC Aktual',
        totalUsage: `${totalSteamTon} Ton`,
        totalIdeal: `${idealPrPct}%`,
        totalLoss: sfc ?? '-',
        isSfcOnly: true,
        groups: [],
      };
    }

    return null;
  }, [reportData, boilerData, categoryKey]);

  if (!isOpen || !modalData) return null;

  const topGroup = modalData.groups?.find((g) => g.loss_val > 0) || modalData.groups?.[0];

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-2 sm:p-4 bg-black/60 backdrop-blur-sm no-print"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-2xl shadow-2xl w-full max-w-7xl max-h-[92vh] overflow-hidden flex flex-col border border-gray-100"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-4 sm:px-6 py-4 bg-gradient-to-r from-red-50 via-orange-50/60 to-white border-b border-red-100 flex justify-between items-start gap-4">
          <div className="flex items-start gap-3">
            <div className="p-2.5 rounded-xl bg-white shadow-sm border border-red-100 mt-0.5">
              {modalData.icon}
            </div>
            <div>
              <h3 className="text-base sm:text-lg font-bold text-gray-900">
                {modalData.title}
              </h3>
              <p className="text-xs text-gray-600 mt-0.5">
                {modalData.subtitle} &bull; Tanggal: <span className="font-semibold text-gray-800">{selectedDate}</span>
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 hover:bg-black/5 rounded-full transition-colors text-gray-500 hover:text-gray-800"
          >
            <X size={22} />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-5 bg-gray-50/40">
          {/* 3 Summary Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="bg-white rounded-xl border border-gray-200/80 p-3.5 shadow-sm">
              <div className="text-[11px] font-semibold text-gray-500 uppercase tracking-wider">
                {modalData.usageLabel}
              </div>
              <div className="text-2xl font-bold text-gray-900 mt-1 tabular-nums">
                {typeof modalData.totalUsage === 'number' ? modalData.totalUsage.toLocaleString('id-ID') : modalData.totalUsage}
                {typeof modalData.totalUsage === 'number' && (
                  <span className="text-xs font-medium text-gray-400 ml-1.5">{modalData.unit}</span>
                )}
              </div>
            </div>

            <div className="bg-white rounded-xl border border-gray-200/80 p-3.5 shadow-sm">
              <div className="text-[11px] font-semibold text-gray-500 uppercase tracking-wider">
                {modalData.idealLabel}
              </div>
              <div className="text-2xl font-bold text-emerald-700 mt-1 tabular-nums">
                {typeof modalData.totalIdeal === 'number' ? modalData.totalIdeal.toLocaleString('id-ID') : modalData.totalIdeal}
                {typeof modalData.totalIdeal === 'number' && (
                  <span className="text-xs font-medium text-gray-400 ml-1.5">{modalData.unit}</span>
                )}
              </div>
            </div>

            <div className="bg-red-50/70 rounded-xl border border-red-200 p-3.5 shadow-sm">
              <div className="text-[11px] font-bold text-red-700 uppercase tracking-wider">
                {modalData.lossLabel}
              </div>
              <div className="flex items-baseline justify-between gap-2 mt-1">
                <div className="text-2xl font-black text-red-600 tabular-nums">
                  {typeof modalData.totalLoss === 'number' ? modalData.totalLoss.toLocaleString('id-ID') : modalData.totalLoss}
                  <span className="text-xs font-semibold text-red-500 ml-1.5">{modalData.unit}</span>
                </div>
                {modalData.totalLossRp != null && modalData.totalLossRp > 0 && (
                  <div className="text-xs font-bold text-red-700 bg-white/90 px-2 py-0.5 rounded border border-red-200">
                     Est. Rp {modalData.totalLossRp.toLocaleString('id-ID')}
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Highlight Recommendation Card (Prioritas Perbaikan #1) */}
          {topGroup && topGroup.loss_val > 0 && (
            <div className="bg-gradient-to-r from-amber-50 to-orange-50/60 border border-amber-200 rounded-xl p-4 shadow-sm">
              <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-2 pb-2.5 mb-2.5 border-b border-amber-200/70">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="inline-flex items-center justify-center px-2 py-0.5 text-[11px] font-bold bg-red-600 text-white rounded-md uppercase tracking-wide">
                    Prioritas #1
                  </span>
                  <h4 className="text-sm sm:text-base font-bold text-gray-900">
                    Losses Terbesar: Group <span className="text-red-700 underline decoration-red-300">{topGroup.group_name}</span>
                  </h4>
                  {topGroup.scenario_badge && (
                    <span className={`text-[11px] font-bold px-2 py-0.5 rounded border ${topGroup.scenario_badge.tone}`}>
                      {topGroup.scenario_badge.text}
                    </span>
                  )}
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  {modalData.showIndicators && (
                    <IndicatorBadges
                      steamOkPct={topGroup.steam_ok_pct}
                      avgPressure={topGroup.avg_pressure}
                      effTotal={topGroup.eff_total}
                    />
                  )}
                  <div className="text-xs font-bold text-red-700 bg-white px-2.5 py-1 rounded-lg border border-amber-200">
                    Kontribusi: {topGroup.loss_val.toLocaleString('id-ID')} {modalData.unit} ({topGroup.share_pct}%)
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
                <div className="bg-white/80 rounded-lg p-3 border border-amber-100">
                  <div className="font-bold text-gray-800 flex items-center gap-1.5 mb-1">
                    <AlertTriangle size={14} className="text-orange-600 shrink-0" />
                    Diagnosis Akar Masalah (Korelasi % Sehat, Avg Pressure & Eff Total):
                  </div>
                  <p className="text-gray-700 leading-relaxed">{topGroup.cause}</p>
                </div>
                <div className="bg-white/90 rounded-lg p-3 border border-emerald-200">
                  <div className="font-bold text-emerald-900 flex items-center gap-1.5 mb-1">
                    <Wrench size={14} className="text-emerald-600 shrink-0" />
                    Rekomendasi Cara Improve:
                  </div>
                  <p className="text-gray-700 leading-relaxed">{topGroup.action}</p>
                </div>
              </div>
            </div>
          )}

          {/* SFC Explanation if SFC clicked */}
          {modalData.isSfcOnly ? (
            <div className="bg-white rounded-xl border border-gray-200 p-4 space-y-3 text-xs text-gray-700">
              <div className="font-bold text-sm text-gray-900 flex items-center gap-2">
                <Lightbulb size={16} className="text-amber-500" />
                Cara Improve Rasio SFC (Specific Fuel Consumption) Batu Bara:
              </div>
              <ul className="list-disc pl-5 space-y-1.5 leading-relaxed">
                <li>
                  <strong>Staggering Beban Pemanasan (Heating):</strong> Hindari menyalakan fase <em>Heating</em> pada banyak mesin Jet Dyeing / Jet Rapid secara bersamaan agar tekanan boiler tidak drop drastis yang memicu umpan batu bara berlebih.
                </li>
                <li>
                  <strong>Jaga Kestabilan Tekanan Header (≥ 3.8 bar):</strong> Ketika tekanan uap stabil, pembakaran boiler berjalan pada titik efisiensi termal optimal (tidak sering mengalami <em>hunting</em> atau <em>regulasi</em>).
                </li>
                <li>
                  <strong>Minimalkan Steam Loss di Mesin Celup:</strong> Perbaiki kebocoran <em>steam trap</em> dan kurangi durasi <em>holding</em> suhu tinggi agar setiap kg uap yang diproduksi boiler terkonversi menjadi output kain yang produktif.
                </li>
              </ul>
            </div>
          ) : (
            /* Table per Machine Group */
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
              <div className="px-4 py-3 border-b border-gray-100 bg-gray-50/70 flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h4 className="text-sm font-bold text-gray-800">
                    Peringkat Machine Group (Diurutkan dari Losses Terbesar)
                  </h4>
                  <p className="text-[11px] text-gray-500">
                    Klik pada baris Machine Group untuk melihat rincian per mesin beserta indikator % Sehat, Avg Pressure, dan Eff Total
                  </p>
                </div>
                {modalData.showIndicators && (
                  <div className="flex items-center gap-3 text-[10px] text-gray-500 bg-white px-2.5 py-1 rounded-lg border border-gray-200">
                    <span className="font-semibold text-gray-700">Target Sehat:</span>
                    <span>% Sehat ≥ 80%</span>
                    <span>&bull;</span>
                    <span>Avg Press ≥ 3.8 bar</span>
                    <span>&bull;</span>
                    <span>Eff Total ≥ 85%</span>
                  </div>
                )}
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-xs border-collapse">
                  <thead className="bg-gray-100/80 border-b border-gray-200 text-gray-600">
                    <tr className="divide-x divide-gray-200/70">
                      <th className="px-2.5 py-2.5 text-left font-bold w-8">#</th>
                      <th className="px-3 py-2.5 text-left font-bold">Machine Group</th>
                      <th className="px-3 py-2.5 text-right font-bold">Total Pemakaian</th>
                      <th className="px-3 py-2.5 text-right font-bold">Target Ideal</th>
                      <th className="px-3 py-2.5 text-right font-bold text-red-700">Total Losses</th>
                      <th className="px-3 py-2.5 text-left font-bold w-28">% Kontribusi</th>
                      {modalData.showIndicators && (
                        <th className="px-3 py-2.5 text-left font-bold">
                          Indikator Korelasi<br/>
                          <span className="text-[10px] font-normal text-gray-500">(% Sehat | Avg Press | Eff Total)</span>
                        </th>
                      )}
                      <th className="px-3 py-2.5 text-left font-bold">Analisis Akar Masalah & Cara Improve</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200">
                    {modalData.groups.length === 0 ? (
                      <tr>
                        <td colSpan={modalData.showIndicators ? 8 : 7} className="px-4 py-8 text-center text-gray-400">
                          Tidak ada data untuk kategori ini pada tanggal terpilih.
                        </td>
                      </tr>
                    ) : (
                      modalData.groups.map((g, idx) => {
                        const isExpanded = !!expandedGroups[g.group_name];
                        return (
                          <React.Fragment key={g.group_name}>
                            <tr
                              onClick={() => toggleGroup(g.group_name)}
                              className={`cursor-pointer transition-colors divide-x divide-gray-100 ${
                                idx === 0 && g.loss_val > 0
                                  ? 'bg-red-50/30 hover:bg-red-50/60'
                                  : 'hover:bg-gray-50'
                              }`}
                            >
                              <td className="px-2.5 py-3 text-center font-bold text-gray-500">
                                {idx + 1}
                              </td>
                              <td className="px-3 py-3 whitespace-nowrap">
                                <div className="flex items-center gap-1.5">
                                  {isExpanded ? (
                                    <ChevronDown size={15} className="text-blue-600 shrink-0" />
                                  ) : (
                                    <ChevronRight size={15} className="text-gray-400 shrink-0" />
                                  )}
                                  <div>
                                    <div className="font-bold text-gray-900 text-sm">{g.group_name}</div>
                                    <div className="text-[10px] text-gray-500">
                                      {g.machine_count} mesin aktif
                                      {g.batch_count ? ` • ${g.batch_count} batch` : ''}
                                    </div>
                                  </div>
                                </div>
                              </td>
                              <td className="px-3 py-3 text-right font-semibold text-gray-800 whitespace-nowrap tabular-nums">
                                {g.usage_val.toLocaleString('id-ID')} <span className="text-[10px] text-gray-400 font-normal">{modalData.unit}</span>
                                {g.wbp_val != null && (
                                  <div className="text-[10px] text-gray-500 font-normal">
                                    LWBP: {g.lwbp_val} | WBP: <span className="text-orange-600 font-semibold">{g.wbp_val}</span>
                                  </div>
                                )}
                              </td>
                              <td className="px-3 py-3 text-right font-medium text-emerald-700 whitespace-nowrap tabular-nums">
                                {g.ideal_val.toLocaleString('id-ID')} <span className="text-[10px] text-gray-400 font-normal">{modalData.unit}</span>
                              </td>
                              <td className="px-3 py-3 text-right whitespace-nowrap tabular-nums">
                                <div className={`text-sm font-black ${g.loss_val > 0 ? 'text-red-600' : 'text-emerald-600'}`}>
                                  {g.loss_val > 0 ? `+${g.loss_val.toLocaleString('id-ID')}` : '0'} <span className="text-[10px] font-normal">{modalData.unit}</span>
                                </div>
                                {g.loss_rp != null && g.loss_rp > 0 && (
                                  <div className="text-[10px] font-semibold text-red-500">
                                    Rp {g.loss_rp.toLocaleString('id-ID')}
                                  </div>
                                )}
                              </td>
                              <td className="px-3 py-3 whitespace-nowrap">
                                <div className="flex items-center justify-between text-[11px] font-bold mb-1">
                                  <span className={g.share_pct >= 35 ? 'text-red-600' : 'text-gray-700'}>
                                    {g.share_pct}%
                                  </span>
                                </div>
                                <div className="w-full h-2 bg-gray-100 rounded-full overflow-hidden">
                                  <div
                                    className={`h-full rounded-full ${
                                      idx === 0 && g.loss_val > 0 ? 'bg-red-500' : 'bg-orange-400'
                                    }`}
                                    style={{ width: `${Math.max(g.loss_val > 0 ? 4 : 0, g.share_pct)}%` }}
                                  />
                                </div>
                              </td>
                              {modalData.showIndicators && (
                                <td className="px-3 py-3 min-w-[210px]">
                                  <IndicatorBadges
                                    steamOkPct={g.steam_ok_pct}
                                    avgPressure={g.avg_pressure}
                                    effTotal={g.eff_total}
                                  />
                                </td>
                              )}
                              <td className="px-3 py-3 min-w-[300px]">
                                {g.scenario_badge && (
                                  <div className="mb-1">
                                    <span className={`inline-block text-[10px] font-bold px-1.5 py-0.5 rounded border ${g.scenario_badge.tone}`}>
                                      {g.scenario_badge.text}
                                    </span>
                                  </div>
                                )}
                                <div className="text-gray-800 font-semibold leading-snug mb-1">
                                  {g.cause}
                                </div>
                                <div className="text-[11px] text-emerald-800 bg-emerald-50/80 border border-emerald-100 rounded px-2 py-1 leading-snug">
                                  <span className="font-bold">Cara Improve: </span>
                                  {g.action}
                                </div>
                              </td>
                            </tr>

                            {/* Expanded Machine List */}
                            {isExpanded && g.machines && g.machines.length > 0 && (
                              <tr className="bg-slate-50/90">
                                <td colSpan={modalData.showIndicators ? 8 : 7} className="px-4 py-3 border-t border-b border-slate-200">
                                  <div className="text-[11px] font-bold text-slate-600 mb-2 flex items-center justify-between">
                                    <span>Rincian Mesin pada Group {g.group_name} (Diurutkan dari Loss Terbesar):</span>
                                  </div>
                                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5">
                                    {g.machines.map((m) => (
                                      <div
                                        key={m.machine_id || m.machine_name}
                                        className="bg-white rounded-lg border border-slate-200 p-2.5 flex flex-col justify-between shadow-2xs"
                                      >
                                        <div className="flex items-center justify-between gap-2 border-b border-slate-100 pb-1.5 mb-1.5">
                                          <div>
                                            <span className="font-bold text-gray-900 text-xs">{m.machine_name}</span>
                                            <span className="text-[10px] text-gray-400 ml-1.5">({m.batch_count})</span>
                                          </div>
                                          {m.machine_id && (
                                            <a
                                              href={`/machine-daily-analytics/${m.machine_id}/${selectedDate}`}
                                              target="_blank"
                                              rel="noopener noreferrer"
                                              className="inline-flex items-center gap-1 text-[10px] font-semibold text-blue-600 hover:text-blue-800 bg-blue-50 hover:bg-blue-100 px-1.5 py-0.5 rounded transition-colors"
                                            >
                                              Grafik <ExternalLink size={10} />
                                            </a>
                                          )}
                                        </div>

                                        <div className="grid grid-cols-3 gap-1 text-[11px] mb-2">
                                          <div>
                                            <div className="text-[9px] text-gray-400 uppercase">Pemakaian</div>
                                            <div className="font-semibold text-gray-700">{m.usage_val} {modalData.unit}</div>
                                          </div>
                                          <div>
                                            <div className="text-[9px] text-gray-400 uppercase">Ideal</div>
                                            <div className="font-semibold text-emerald-700">{m.ideal_val} {modalData.unit}</div>
                                          </div>
                                          <div>
                                            <div className="text-[9px] text-gray-400 uppercase">Loss</div>
                                            <div className={`font-bold ${m.loss_val > 0 ? 'text-red-600' : 'text-emerald-600'}`}>
                                              {m.loss_val > 0 ? `+${m.loss_val}` : '0'} {modalData.unit}
                                            </div>
                                          </div>
                                        </div>

                                        {modalData.showIndicators && (
                                          <div className="mb-1.5">
                                            <IndicatorBadges
                                              steamOkPct={m.steam_ok_pct}
                                              avgPressure={m.avg_pressure}
                                              effTotal={m.eff_total}
                                              compact
                                            />
                                          </div>
                                        )}

                                        <div className="pt-1 border-t border-slate-50 flex items-center justify-between text-[10px] text-gray-500">
                                          <span className="truncate">{m.note}</span>
                                          <span className="font-semibold text-red-600 shrink-0 ml-1">{m.loss_sub}</span>
                                        </div>
                                      </div>
                                    ))}
                                  </div>
                                </td>
                              </tr>
                            )}
                          </React.Fragment>
                        );
                      })
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
