import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { cs } from "../i18n/cs";
import { useCaseDetail, useRecheck } from "../services/api";
import DemoControls from "../components/DemoControls";
import HeaderStrip from "../components/HeaderStrip";
import ImagingTimeline from "../components/ImagingTimeline";
import OpenIssuesPanel from "../components/OpenIssuesPanel";
import PlannedExamBox from "../components/PlannedExamBox";
import RequiredItemsTable from "../components/RequiredItemsTable";
import SourceDrawer from "../components/SourceDrawer";

const POLL_MS = 2000;
const POLL_DURATION_MS = 20000;

interface SourceRef {
  docId: string;
  quote: string | null;
}

export default function PatientDetail() {
  const { caseId = "" } = useParams<{ caseId: string }>();
  const [polling, setPolling] = useState(false);
  const [presentation, setPresentation] = useState(false);
  const [source, setSource] = useState<SourceRef | null>(null);
  const pollTimer = useRef<number>();

  const { data, isLoading, error, refetch } = useCaseDetail(caseId, polling ? POLL_MS : 0);
  const recheck = useRecheck(caseId);

  useEffect(() => {
    document.documentElement.classList.toggle("presentation", presentation);
    return () => document.documentElement.classList.remove("presentation");
  }, [presentation]);

  useEffect(() => () => window.clearTimeout(pollTimer.current), []);

  const onRecheck = () => {
    recheck.mutate(undefined, {
      onSuccess: () => {
        // the backend check runs in the background, so poll for a while
        setPolling(true);
        window.clearTimeout(pollTimer.current);
        pollTimer.current = window.setTimeout(() => setPolling(false), POLL_DURATION_MS);
      },
    });
  };

  const openSource = useCallback(
    (docId: string, quote: string | null) => setSource({ docId, quote }),
    [],
  );
  const closeSource = useCallback(() => setSource(null), []);

  if (isLoading) return <p className="p-6 text-lg">{cs.app.loading}</p>;

  if (error || !data) {
    return (
      <div className="p-6" role="alert">
        <p className="text-lg text-red-800">
          {cs.common.error}: {error?.message}
        </p>
        <button
          type="button"
          onClick={() => void refetch()}
          className="mt-2 rounded border-2 border-accent-600 px-3 py-1 font-semibold text-accent-700"
        >
          {cs.common.retry}
        </button>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-[110rem] space-y-4 p-4">
      <HeaderStrip
        data={data}
        presentation={presentation}
        rechecking={recheck.isPending || polling}
        onRecheck={onRecheck}
        onTogglePresentation={() => setPresentation((p) => !p)}
      />
      {recheck.isError && (
        <p role="alert" className="text-red-800">
          {cs.common.error}: {recheck.error.message}
        </p>
      )}
      <PlannedExamBox caseId={caseId} exam={data.planned_exam} onOpenSource={openSource} />
      <ImagingTimeline entries={data.timeline} onOpenSource={openSource} />
      <RequiredItemsTable items={data.items} onOpenSource={openSource} />
      <OpenIssuesPanel issues={data.open_issues} />
      {!presentation && <DemoControls />}
      {source && (
        <SourceDrawer caseId={caseId} docId={source.docId} quote={source.quote} onClose={closeSource} />
      )}
    </div>
  );
}
