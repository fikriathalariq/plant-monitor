import React from 'react';
import { CheckCircle2, Flame, PauseCircle, Snowflake, Activity } from 'lucide-react';

/**
 * Resolve process status display from is_complete + thermal_status.
 * Returns: { Icon, label, bg, text, ring, iconBg, iconText }
 */
export function resolveProcessStatus(isComplete, thermalStatus) {
  if (isComplete) {
    return {
      key: 'DONE',
      Icon: CheckCircle2,
      label: 'Selesai',
      bg: 'bg-emerald-50',
      text: 'text-emerald-700',
      ring: 'ring-emerald-600/20',
      iconBg: 'bg-emerald-100',
      iconText: 'text-emerald-600',
    };
  }

  switch (thermalStatus) {
    case 'HEAT':
      return {
        key: 'HEAT',
        Icon: Flame,
        label: 'Heating',
        bg: 'bg-red-50',
        text: 'text-red-700',
        ring: 'ring-red-600/20',
        iconBg: 'bg-red-100',
        iconText: 'text-red-600',
      };
    case 'STEADY':
      return {
        key: 'STEADY',
        Icon: PauseCircle,
        label: 'Hold/Keeping',
        bg: 'bg-orange-50',
        text: 'text-orange-700',
        ring: 'ring-orange-600/20',
        iconBg: 'bg-orange-100',
        iconText: 'text-orange-600',
      };
    case 'COOL':
      return {
        key: 'COOL',
        Icon: Snowflake,
        label: 'Cooling',
        bg: 'bg-sky-50',
        text: 'text-sky-700',
        ring: 'ring-sky-600/20',
        iconBg: 'bg-sky-100',
        iconText: 'text-sky-600',
      };
    default:
      return {
        key: 'RUNNING',
        Icon: Activity,
        label: 'Berjalan',
        bg: 'bg-slate-50',
        text: 'text-slate-600',
        ring: 'ring-slate-600/20',
        iconBg: 'bg-slate-100',
        iconText: 'text-slate-500',
      };
  }
}

/**
 * Circular avatar icon that distinguishes Finished vs Running phases.
 */
export function ProcessStatusIcon({ isComplete, thermalStatus, size = 'md', className = '' }) {
  const status = resolveProcessStatus(isComplete, thermalStatus);
  const { Icon } = status;

  const sizeMap = {
    sm: { wrap: 'h-8 w-8', icon: 14 },
    md: { wrap: 'h-10 w-10', icon: 18 },
    lg: { wrap: 'h-12 w-12', icon: 22 },
  };
  const s = sizeMap[size] || sizeMap.md;

  return (
    <div
      className={`flex-shrink-0 ${s.wrap} rounded-full ${status.iconBg} ${status.iconText} flex items-center justify-center ${className}`}
      title={status.label}
    >
      <Icon size={s.icon} strokeWidth={2.25} />
    </div>
  );
}

/**
 * Pill badge with icon + label for status column.
 */
export function ProcessStatusBadge({ isComplete, thermalStatus, className = '' }) {
  const status = resolveProcessStatus(isComplete, thermalStatus);
  const { Icon } = status;

  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs leading-5 font-semibold rounded-full ring-1 ring-inset ${status.bg} ${status.text} ${status.ring} ${className}`}
    >
      <Icon size={12} strokeWidth={2.5} />
      {status.label}
    </span>
  );
}

export default ProcessStatusIcon;
