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
import StudyStatusList from "../components/StudyStatusList";
import { ReadinessTag } from "../components/ReadinessBadge";
import { formatDate } from "../components/format";
import { Button, ErrorState } from "../components/ui";

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
  const [details, setDetails] = useState(false);
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

  const openIssueCount = data.open_issues.filter((i) => !i.acknowledged).length;
  const showDetails = () => {
    setDetails(true);
    window.setTimeout(() => document.getElementById("details")?.scrollIntoView({ behavior: "smooth" }), 50);
  };

  return (
    <div className="space-y-3">
      <header className="nis-panel flex flex-wrap items-center justify-between gap-3 px-4 py-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-baseline gap-x-3">
            <h1 className="text-2xl font-bold text-accent-600">{data.patient.display_name}</h1>
            <span className="text-lg text-nis-text">{cs.summary.born(data.patient.birth_year, data.patient.birth_band)}</span>
          </div>
          <div className="mt-0.5 text-sm text-nis-muted">
            {cs.header.meeting} {formatDate(data.case.meeting.date)} {data.case.meeting.time} – {data.case.meeting.label}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <span className="inline-flex items-center gap-2" data-readiness={data.case.readiness} title={data.case.reason}>
            <ReadinessTag state={data.case.readiness} />
          </span>
          <Button
            variant="secondary"
            icon="list"
            aria-expanded={details}
            aria-controls="details"
            onClick={() => (details ? setDetails(false) : showDetails())}
          >
            {details ? cs.summary.hideDetails : cs.summary.showDetails}
          </Button>
        </div>
      </header>

      <StudyStatusList
        caseId={caseId}
        items={data.items}
        checkStatus={data.check_status}
        openIssueCount={openIssueCount}
        showDemo={!presentation}
        requestsAvailable={data.requests_available !== false}
        onShowRequest={setRequestId}
        onShowDetails={showDetails}
      />

      {details && (
        <div id="details" className="space-y-3 border-t-2 border-dashed border-nis-line pt-3">
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
          <OpenIssuesPanel issues={data.open_issues} caseId={caseId} />
          {!presentation && <AgentChat caseId={caseId} onOpenSource={openSource} onShowRequest={setRequestId} />}
        </div>
      )}
      {requestId && <RequestDrawer requestId={requestId} onClose={closeRequest} />}
      {source && (
        <SourceDrawer caseId={caseId} docId={source.docId} quote={source.quote} onClose={closeSource} />
      )}
    </div>
  );
}
