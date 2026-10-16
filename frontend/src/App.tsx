import { Link, Route, Routes } from "react-router-dom";
import { cs } from "./i18n/cs";
import { isMockMode } from "./services/api";
import { MOCK_CASE_ID } from "./services/mock";
import DateSidebar from "./components/DateSidebar";
import AddPatient from "./pages/AddPatient";
import Dashboard from "./pages/Dashboard";
import DayView from "./pages/DayView";
import PatientDetail from "./pages/PatientDetail";

export default function App() {
  return (
    <>
      <nav className="flex items-center justify-between border-b border-slate-300 bg-white px-4 py-3">
        <Link to="/" className="text-xl font-bold text-accent-700">
          {cs.app.name}
        </Link>
        <div className="flex items-center gap-4">
          {isMockMode && (
            <Link className="font-semibold text-accent-700 underline" to={`/cases/${MOCK_CASE_ID}`}>
              {cs.app.homeMockLink}
            </Link>
          )}
          <Link
            to="/pridat"
            className="rounded-lg bg-accent-600 px-4 py-2 font-semibold text-white hover:bg-accent-700"
          >
            {cs.app.addPatient}
          </Link>
        </div>
      </nav>
      <div className="flex">
        <DateSidebar />
        <main className="min-w-0 flex-1">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/dny/:date" element={<DayView />} />
            <Route path="/pridat" element={<AddPatient />} />
            <Route path="/cases/:caseId" element={<PatientDetail />} />
            <Route path="*" element={<p className="p-6">{cs.app.notFound}</p>} />
          </Routes>
        </main>
      </div>
    </>
  );
}
