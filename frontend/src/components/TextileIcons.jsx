import React from "react";

const base = (size, className, props) => ({
  width: size,
  height: size,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.5,
  strokeLinecap: "round",
  strokeLinejoin: "round",
  className,
  "aria-hidden": "true",
  ...props,
});

// Jet Dyeing Machine: bejana bertekanan dengan aliran jet
export const JetDyeingIcon = ({ size = 24, className, ...props }) => (
  <svg {...base(size, className, props)}>
    <rect x="2.5" y="7" width="19" height="10" rx="5" />
    <circle cx="12" cy="4.5" r="1.5" />
    <path d="M6 12h4l2-2h4" />
    <path d="M14 12l-1.5-1.5M14 12l-1.5 1.5" />
    <path d="M5 17h14" strokeDasharray="1.5 2" />
  </svg>
);

// Stenter Machine: rangka dengan clip dan kain melintas
export const StenterIcon = ({ size = 24, className, ...props }) => (
  <svg {...base(size, className, props)}>
    <rect x="2" y="6" width="20" height="12" rx="1" />
    <path d="M5 6v2M9 6v2M13 6v2M17 6v2M5 16v2M9 16v2M13 16v2M17 16v2" />
    <path d="M2 12q2.5-2.5 5 0t5 0 5 0 5 0" />
  </svg>
);

// Ring Spinning Frame: bobbin dan ring benang
export const SpinningIcon = ({ size = 24, className, ...props }) => (
  <svg {...base(size, className, props)}>
    <rect x="10" y="4" width="4" height="12" rx="1" />
    <path d="M8 4h8M8 16h8" />
    <ellipse cx="12" cy="19.5" rx="6" ry="1.5" />
    <path d="M12 4q6-2 8 4" />
  </svg>
);

// Weaving Loom: rangka, benang lusi, dan shuttle
export const LoomIcon = ({ size = 24, className, ...props }) => (
  <svg {...base(size, className, props)}>
    <rect x="3" y="3" width="18" height="18" rx="1.5" />
    <path d="M7 3v18M10 3v18M14 3v18M17 3v18" />
    <rect x="5.5" y="10" width="13" height="4" rx="2" />
  </svg>
);

// Knitting Machine: jarum dan rajutan
export const KnittingIcon = ({ size = 24, className, ...props }) => (
  <svg {...base(size, className, props)}>
    <path d="M3 15h18" />
    <path d="M6 15V9l1.5-1.5M10 15V9l1.5-1.5M14 15V9l1.5-1.5M18 15V9l1.5-1.5" />
    <path d="M5 19q2-2 4 0t4 0 4 0 3 0" />
  </svg>
);

// Sewing Machine: badan, lengan, dan jarum
export const SewingIcon = ({ size = 24, className, ...props }) => (
  <svg {...base(size, className, props)}>
    <path d="M3 20h18" />
    <path d="M6 20V10h8l4 4v6" />
    <path d="M6 10V6h8v4" />
    <path d="M10 13v4" />
    <circle cx="10" cy="10" r="0.5" />
  </svg>
);

// Winding Machine: cone/bobbin dan pemandu benang
export const WindingIcon = ({ size = 24, className, ...props }) => (
  <svg {...base(size, className, props)}>
    <circle cx="12" cy="11" r="7" />
    <circle cx="12" cy="11" r="2.5" />
    <path d="M4 21h16" />
    <path d="M12 18v3" />
  </svg>
);

// Rotary Screen Printing: silinder cetak dan kain
export const PrintingIcon = ({ size = 24, className, ...props }) => (
  <svg {...base(size, className, props)}>
    <circle cx="9" cy="8" r="4" />
    <circle cx="15" cy="8" r="4" />
    <path d="M2 16h20" />
    <path d="M5 19h14" strokeDasharray="1.5 2" />
  </svg>
);

// Open Width Washing Range: rol-rol pencucian dan kain
export const WashingIcon = ({ size = 24, className, ...props }) => (
  <svg {...base(size, className, props)}>
    <circle cx="5" cy="12" r="2" />
    <circle cx="12" cy="12" r="2" />
    <circle cx="19" cy="12" r="2" />
    <path d="M3 8q9-4 18 0" />
    <path d="M3 16q9 4 18 0" />
  </svg>
);

// Calender / Compactor: dua rol penekan
export const CalenderIcon = ({ size = 24, className, ...props }) => (
  <svg {...base(size, className, props)}>
    <rect x="3" y="4" width="18" height="6" rx="3" />
    <rect x="3" y="14" width="18" height="6" rx="3" />
    <path d="M12 10v4" />
  </svg>
);

// Steamer Machine: ruang uap dengan uap vertikal dan kain
export const SteamerIcon = ({ size = 24, className, ...props }) => (
  <svg {...base(size, className, props)}>
    <rect x="3" y="11" width="18" height="9" rx="1.5" />
    <path d="M3 14h18" />
    <path d="M7 11V8q2-1.5 0-3" />
    <path d="M12 11V7q2-1.5 0-3" />
    <path d="M17 11V8q2-1.5 0-3" />
    <path d="M6 17q3-1.5 6 0t6 0" />
  </svg>
);

/**
 * Menentukan komponen ikon mesin tekstil berdasarkan nama mesin dan grupnya.
 * - Jet Dyeing, Relax, dan Jet Printing -> JetDyeingIcon
 * - Stenter (Ehwa, Ilsung, Monfong, SPT2, SSD2, dll.) -> StenterIcon
 * - Calender / CDR / Comfit -> CalenderIcon
 * - Washing PRT -> WashingIcon
 * - Steamer -> SteamerIcon
 * - Flat / Printing -> PrintingIcon
 */
export const getMachineTextileIcon = (machineName = "", groupName = "") => {
  const name = String(machineName || "").toUpperCase();
  const group = String(groupName || "").toUpperCase();

  // 1. Washing (WASHING PRT, dll.)
  if (name.includes("WASHING")) {
    return WashingIcon;
  }

  // 2. Steamer (Steamer 1, Steamer 2, Temp Steamer, dll.)
  if (name.includes("STEAMER")) {
    return SteamerIcon;
  }

  // 3. Calender / Compactor (CDR SAMIL, CDR PRT, Calender, Comfit)
  if (name.includes("CDR") || name.includes("CALENDER") || name.includes("COMFIT")) {
    return CalenderIcon;
  }

  // 4. Stenter (Ehwa, Ilsung, Monfong, SPT 2, SSD 2, Babcock, SMCH, Dryer, Wet Set)
  if (
    name.includes("STENTER") ||
    name.includes("EHWA") ||
    name.includes("ILSUNG") ||
    name.includes("MONFONG") ||
    name.includes("SPT") ||
    name.includes("SSD") ||
    name.includes("BABCOCK") ||
    name.includes("SMCH") ||
    name.includes("DRYER") ||
    name.includes("WET SET") ||
    name.includes("WETSET")
  ) {
    return StenterIcon;
  }

  // 5. Jet Dyeing, Jet Relax, Jet Printing (JD, JR, ZET, JET)
  if (
    group.includes("JD") ||
    group.includes("JR") ||
    group.includes("JET") ||
    name.startsWith("JD") ||
    name.startsWith("JR") ||
    name.startsWith("ZET") ||
    name.includes("JET")
  ) {
    return JetDyeingIcon;
  }

  // 6. Flat / Screen Printing
  if (name.includes("FLAT") || name.includes("PRINT")) {
    return PrintingIcon;
  }

  return StenterIcon;
};

export default {
  JetDyeingIcon,
  StenterIcon,
  SpinningIcon,
  LoomIcon,
  KnittingIcon,
  SewingIcon,
  WindingIcon,
  PrintingIcon,
  WashingIcon,
  CalenderIcon,
  SteamerIcon,
  getMachineTextileIcon,
};
