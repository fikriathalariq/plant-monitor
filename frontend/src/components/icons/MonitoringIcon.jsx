import React from 'react';

/**
 * MonitoringIcon: Exact replica of Google Material Symbols Outlined 'monitoring'
 * used in port 8004 (monitoring/templates/base.html) for Grafik / Analytics.
 */
export const MonitoringIcon = ({ className = 'w-6 h-6', style, ...props }) => (
  <svg
    viewBox="0 -960 960 960"
    className={className}
    style={{ fill: 'currentColor', ...style }}
    aria-hidden="true"
    {...props}
  >
    <path d="M120 -120V-200L200 -280V-120ZM280 -120V-360L360 -440V-120ZM440 -120V-440L520 -359V-120ZM600 -120V-359L680 -439V-120ZM760 -120V-520L840 -600V-120ZM120 -327V-440L400 -720L560 -560L840 -840V-727L560 -447L400 -607Z" />
  </svg>
);

export default MonitoringIcon;
