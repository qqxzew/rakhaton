import type { ReactElement } from "react";

// Simple line icons (24x24, stroke = currentColor). Add new ones to PATHS.
const PATHS = {
  home: <path d="M3 11l9-7 9 7M5 9.5V20h5v-6h4v6h5V9.5" />,
  calendar: (
    <>
      <rect x="3.5" y="5" width="17" height="15" rx="1.5" />
      <path d="M3.5 9.5h17M8 3v4M16 3v4" />
    </>
  ),
  userPlus: (
    <>
      <circle cx="10" cy="8" r="3.5" />
      <path d="M3.5 20c.6-3.6 3.2-5.5 6.5-5.5s5.9 1.9 6.5 5.5M18.5 8v6M15.5 11h6" />
    </>
  ),
  users: (
    <>
      <circle cx="9" cy="8.5" r="3" />
      <path d="M3 19c.5-3 2.8-4.7 6-4.7s5.5 1.7 6 4.7" />
      <circle cx="16.5" cy="9" r="2.5" />
      <path d="M16 14.3c2.6 0 4.4 1.4 5 4.2" />
    </>
  ),
  user: (
    <>
      <circle cx="12" cy="8" r="3.8" />
      <path d="M4.5 20c.7-4 3.6-6 7.5-6s6.8 2 7.5 6" />
    </>
  ),
  search: (
    <>
      <circle cx="10.5" cy="10.5" r="6" />
      <path d="M15 15l5 5" />
    </>
  ),
  chevronLeft: <path d="M15 5l-7 7 7 7" />,
  chevronRight: <path d="M9 5l7 7-7 7" />,
  chevronDown: <path d="M5 9l7 7 7-7" />,
  close: <path d="M6 6l12 12M18 6L6 18" />,
  check: <path d="M5 12.5l4.5 4.5L19 7.5" />,
  checkCircle: (
    <>
      <circle cx="12" cy="12" r="9.5" />
      <path d="M7.5 12.5l3 3 6-6.5" />
    </>
  ),
  warning: (
    <>
      <path d="M12 3.5L21.5 20h-19L12 3.5z" />
      <path d="M12 10v4.5M12 17.2v.1" />
    </>
  ),
  crossCircle: (
    <>
      <circle cx="12" cy="12" r="9.5" />
      <path d="M8.5 8.5l7 7M15.5 8.5l-7 7" />
    </>
  ),
  question: (
    <>
      <circle cx="12" cy="12" r="9.5" />
      <path d="M9.5 9.5a2.5 2.5 0 115 .2c0 1.8-2.5 2-2.5 3.8M12 17v.1" />
    </>
  ),
  scan: (
    <>
      <rect x="3.5" y="4" width="17" height="13" rx="1.5" />
      <path d="M8 21h8M12 17v4M9 10.5a3 3 0 106 0 3 3 0 10-6 0" />
    </>
  ),
  document: (
    <>
      <path d="M6 3h8l4 4v14H6z" />
      <path d="M14 3v4h4M9 12h6M9 16h6" />
    </>
  ),
  list: <path d="M9 6h11M9 12h11M9 18h11M4.5 6h.1M4.5 12h.1M4.5 18h.1" />,
  refresh: <path d="M19.5 8.5A8 8 0 005 7.5M4.5 15.5A8 8 0 0019 16.5M5 3.5v4h4M19 20.5v-4h-4" />,
  screen: (
    <>
      <rect x="3" y="4" width="18" height="12" rx="1.5" />
      <path d="M8 20h8M12 16v4" />
    </>
  ),
  edit: <path d="M4 20h4L19 9l-4-4L4 16v4zM13.5 6.5l4 4" />,
  flag: <path d="M5 21V4M5 4h11l-2 4 2 4H5" />,
  pulse: <path d="M3 12h4l2-5 4 10 2-5h6" />,
  mail: (
    <>
      <rect x="3" y="5.5" width="18" height="13" rx="1.5" />
      <path d="M3.5 6.5l8.5 6.5 8.5-6.5" />
    </>
  ),
  phone: (
    <path d="M5 4h4l1.5 4.5L8 10a11 11 0 006 6l1.5-2.5L20 15v4a1.5 1.5 0 01-1.5 1.5C10.5 20 4 13.5 3.5 5.5A1.5 1.5 0 015 4z" />
  ),
  chart: <path d="M4 20V4M4 20h16M8 16v-5M12 16V8M16 16v-3" />,
  chat: <path d="M4 5h16v11H9l-5 4V5z" />,
  menu: <path d="M4 6h16M4 12h16M4 18h16" />,
  plus: <path d="M12 5v14M5 12h14" />,
  info: (
    <>
      <circle cx="12" cy="12" r="9.5" />
      <path d="M12 11v6M12 7.5v.1" />
    </>
  ),
} satisfies Record<string, ReactElement>;

export type IconName = keyof typeof PATHS;

export default function Icon({
  name,
  size = "1.3em",
  strokeWidth = 1.8,
  className,
  title,
}: {
  name: IconName;
  /** em sizes scale with the text (and with presentation mode) */
  size?: number | string;
  strokeWidth?: number;
  className?: string;
  title?: string;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={`shrink-0 ${className ?? ""}`}
      aria-hidden={title ? undefined : true}
      role={title ? "img" : undefined}
    >
      {title && <title>{title}</title>}
      {PATHS[name]}
    </svg>
  );
}
