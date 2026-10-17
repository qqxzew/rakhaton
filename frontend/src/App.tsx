import { useState } from "react";
import { Link, NavLink, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { cs } from "./i18n/cs";
import { isMockMode } from "./services/api";
import { MOCK_CASE_ID } from "./services/mock";
import DateSidebar from "./components/DateSidebar";
import { formatDayMonth, weekdayShort } from "./components/format";
import { ButtonLink, Icon, type IconName } from "./components/ui";
import AddPatient from "./pages/AddPatient";
import Dashboard from "./pages/Dashboard";
import DayView from "./pages/DayView";
import PatientDetail from "./pages/PatientDetail";
import Worklist from "./pages/Worklist";
import Hospitals from "./pages/Hospitals";
import Integration from "./pages/Integration";
import Stats from "./pages/Stats";

interface RailItem {
  to: string;
  label: string;
  icon: IconName;
  end?: boolean;
}

// Left icon rail. New screens (stats, agent chat, …) add an entry here.
const RAIL: RailItem[] = [
  { to: "/", label: cs.app.crumbDashboard, icon: "home", end: true },
  { to: "/pridat", label: cs.app.addPatient, icon: "userPlus" },
  { to: "/zadosti", label: cs.system.rail.worklist, icon: "inbox" },
  { to: "/nemocnice", label: cs.system.rail.hospitals, icon: "building" },
  { to: "/integrace", label: cs.system.rail.integration, icon: "network" },
  { to: "/statistiky", label: cs.stats.rail, icon: "chart" },
  ...(isMockMode ? [{ to: `/cases/${MOCK_CASE_ID}`, label: cs.app.homeMockLink, icon: "user" as IconName }] : []),
];

function IconRail() {
  return (
    <nav
      aria-label={cs.app.navLabel}
      className="fixed inset-y-0 left-0 z-30 flex w-14 flex-col items-center border-r border-nis-line bg-white"
    >
      <Link
        to="/"
        aria-label={cs.app.name}
        className="flex h-14 w-full items-center justify-center border-b border-nis-line"
      >
        <span className="flex h-8 w-8 items-center justify-center rounded-full bg-accent-600 text-xs font-bold text-white">
          PK
        </span>
      </Link>
      <ul className="mt-2 flex flex-col items-center gap-1">
        {RAIL.map((item) => (
          <li key={item.to}>
            <NavLink
              to={item.to}
              end={item.end}
              aria-label={item.label}
              title={item.label}
              className={({ isActive }) =>
                `flex h-10 w-10 items-center justify-center rounded-nis ${
                  isActive ? "bg-accent-50 text-accent-600" : "text-nis-icon hover:bg-accent-50 hover:text-accent-600"
                }`
              }
            >
              <Icon name={item.icon} size="1.6em" />
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}

function useCrumb(): string | null {
  const { pathname } = useLocation();
  const day = /^\/dny\/(\d{4}-\d{2}-\d{2})/.exec(pathname);
  if (pathname === "/") return cs.app.crumbDashboard;
  if (day) return `MDT ${weekdayShort(day[1])} ${formatDayMonth(day[1])}`;
  if (pathname.startsWith("/pridat")) return cs.app.addPatient;
  if (pathname.startsWith("/cases/")) return cs.app.crumbPatient;
  if (pathname.startsWith("/zadosti")) return cs.system.rail.worklist;
  if (pathname.startsWith("/nemocnice")) return cs.system.rail.hospitals;
  if (pathname.startsWith("/integrace")) return cs.system.rail.integration;
  if (pathname.startsWith("/statistiky")) return cs.stats.rail;
  return null;
}

function TopBar() {
  const navigate = useNavigate();
  const crumb = useCrumb();
  const [q, setQ] = useState("");

  const onSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const term = q.trim();
    navigate(term ? `/pridat?q=${encodeURIComponent(term)}` : "/pridat");
  };

  return (
    <header className="sticky top-0 z-20 flex h-14 items-center gap-4 border-b border-nis-line bg-white pl-[4.5rem] pr-4">
      <Link to="/" className="shrink-0 leading-tight">
        <span className="block text-2xs text-nis-muted">{cs.app.org}</span>
        <span className="block text-lg font-medium text-nis-text">{cs.app.name}</span>
      </Link>
      <form role="search" onSubmit={onSearch} className="relative w-full max-w-sm">
        <Icon name="search" className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-nis-icon" />
        <input
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          aria-label={cs.app.searchLabel}
          placeholder={cs.app.searchPlaceholder}
          className="nis-input pl-8"
        />
      </form>
      <nav aria-label={cs.app.breadcrumbLabel} className="hidden min-w-0 truncate text-base md:block">
        <Link to="/" className="text-accent-600 hover:underline">
          {cs.app.home}
        </Link>
        {crumb && (
          <>
            <span className="mx-1 text-nis-muted">/</span>
            <span className="text-nis-ink">{crumb}</span>
          </>
        )}
      </nav>
      <div className="ml-auto flex shrink-0 items-center gap-3">
        <ButtonLink to="/pridat" variant="primary" icon="plus">
          {cs.app.addPatient}
        </ButtonLink>
      </div>
    </header>
  );
}

export default function App() {
  const location = useLocation();
  return (
    <>
      <IconRail />
      <TopBar />
      <div className="flex items-start gap-3 py-3 pl-[4.25rem] pr-3">
        <DateSidebar />
        <main className="min-w-0 flex-1">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/dny/:date" element={<DayView />} />
            <Route path="/pridat" element={<AddPatient key={location.search} />} />
            <Route path="/cases/:caseId" element={<PatientDetail />} />
            <Route path="/zadosti" element={<Worklist />} />
            <Route path="/nemocnice" element={<Hospitals />} />
            <Route path="/integrace" element={<Integration />} />
            <Route path="/statistiky" element={<Stats />} />
            <Route path="*" element={<p className="nis-panel p-4">{cs.app.notFound}</p>} />
          </Routes>
        </main>
      </div>
    </>
  );
}
