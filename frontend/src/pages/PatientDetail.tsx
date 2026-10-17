import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { cs } from "../i18n/cs";
import { useCaseDetail, useRecheck } from "../services/api";
import HeaderStrip from "../components/HeaderStrip";
import ImagingTimeline from "../components/ImagingTimeline";
import OpenIssuesPanel from "../components/OpenIssuesPanel";
import PlannedExamBox from "../components/PlannedExamBox";
import RequiredItemsTable from "../components/RequiredItemsTable";
import SourceDrawer from "../components/SourceDrawer";
import RequestDrawer from "../components/RequestDrawer";
import AgentChat from "../components/AgentChat";
import { ErrorState } from "../components/ui";

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
  const [requestId, setRequestId] = useState<string | null>(null);
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
  const closeRequest = useCallback(() => setRequestId(null), []);

  if (isLoading) return <p className="nis-panel p-4 text-nis-muted">{cs.app.loading}</p>;

  if (error || !data) {
    return (
      <ErrorState
        message={`${cs.common.error}: ${error?.message ?? ""}`}
        retryLabel={cs.common.retry}
        onRetry={() => void refetch()}
      />
    );
  }

  return (
    <div className="space-y-3">
      <HeaderStrip
        data={data}
        presentation={presentation}
        rechecking={recheck.isPending || polling}
        onRecheck={onRecheck}
        onTogglePresentation={() => setPresentation((p) => !p)}
      />
      {recheck.isError && (
        <p role="alert" className="nis-panel nis-row-danger px-3 py-2">
          {cs.common.error}: {recheck.error.message}
        </p>
      )}
      <PlannedExamBox caseId={caseId} exam={data.planned_exam} onOpenSource={openSource} />
      <ImagingTimeline entries={data.timeline} onOpenSource={openSource} />
      <RequiredItemsTable
        caseId={caseId}
        items={data.items}
        onOpenSource={openSource}
        showActions={!presentation}
        requestsAvailable={data.requests_available !== false}
        onShowRequest={setRequestId}
      />
      <OpenIssuesPanel issues={data.open_issues} />
      {!presentation && <AgentChat caseId={caseId} onOpenSource={openSource} onShowRequest={setRequestId} />}
      {requestId && <RequestDrawer requestId={requestId} onClose={closeRequest} />}
      {source && (
        <SourceDrawer caseId={caseId} docId={source.docId} quote={source.quote} onClose={closeSource} />
      )}
    </div>
  );
}
