// Dev-only mock backend (VITE_USE_MOCK=1). All data below is synthetic.
import type {
  CaseDetail,
  PlannedExamPatch,
  SourceDocument,
} from "./api-types";

export const MOCK_CASE_ID = "CASE-TEST-0001";

const docs: Record<string, SourceDocument> = {
  "DOC-TEST-001": {
    doc_id: "DOC-TEST-001",
    kind: "Zpráva z vyšetření (syntetická)",
    date: "2026-09-18",
    text:
      "CT hrudníku, břicha a pánve – syntetický testovací nález.\n\n" +
      "Srovnání: PET/CT v 05/2025 provedené na pracovišti Nemocnice Test-Sever (NTS) " +
      "bez významné změny proti předchozí studii.\n" +
      "Dále bylo provedeno MR pánve 02/2026 v našem zařízení.\n\n" +
      "Závěr: Stabilní nález, doporučena další kontrola.",
  },
  "DOC-TEST-002": {
    doc_id: "DOC-TEST-002",
    kind: "Žádanka (syntetická)",
    date: "2026-10-05",
    text:
      "Žádanka o vyšetření – syntetický text.\n" +
      "Prosíme o PET/CT\n   celého těla před konzilií MDT.\n" +
      "Klinická otázka: hodnocení odpovědi na léčbu.",
  },
  "DOC-TEST-003": {
    doc_id: "DOC-TEST-003",
    kind: "Zpráva z vyšetření (syntetická)",
    date: "2026-02-20",
    text:
      "MR pánve – syntetický testovací nález.\n" +
      "Drobná změna signálu bez jasného korelátu. Doporučeno srovnání s CT.",
  },
};

let current: CaseDetail = {
  case: {
    id: MOCK_CASE_ID,
    meeting: {
      id: "MTG-TEST-01",
      label: "Uro-onkologický MDT (test)",
      date: "2026-10-22",
      time: "14:30",
    },
    readiness: "not_ready",
    reason: "Chybí: PET/CT 05/2025 (NTS), žádost odeslána",
    date_offset_days: 412,
  },
  patient: {
    id: "PAC-TEST-0001",
    display_name: "Test Pacient",
    sex: "muž",
    age_band: "60–69 let",
    diagnoses: [{ code: "C61", text: "Zhoubný novotvar prostaty (test)" }],
  },
  planned_exam: {
    modality: "PET",
    regions: ["chest", "abdomen", "pelvis"],
    date: "2026-10-30",
    site: "Test-Motol, nukleární medicína",
    quote: "Prosíme o PET/CT celého těla před konzilií MDT.",
    source_doc_id: "DOC-TEST-002",
    confidence: 0.92,
  },
  timeline: [
    {
      kind: "referenced",
      date: "2025-05-15",
      modality: "PET/CT",
      regions: ["whole_body"],
      label: "PET/CT 05/2025 (NTS) – bez významné změny",
      availability: "not_found",
      study_id: null,
      doc_id: "DOC-TEST-001",
    },
    {
      kind: "treatment",
      date: "2025-08-01",
      modality: null,
      regions: [],
      label: "Zahájení hormonální léčby (test)",
      availability: null,
      study_id: null,
      doc_id: null,
    },
    {
      kind: "study",
      date: "2026-02-20",
      modality: "MR",
      regions: ["pelvis"],
      label: "Drobná změna signálu bez jasného korelátu",
      availability: "not_in_pacs",
      study_id: "STU-TEST-003",
      doc_id: "DOC-TEST-003",
    },
    {
      kind: "study",
      date: "2026-09-18",
      modality: "CT",
      regions: ["chest", "abdomen", "pelvis"],
      label: "Stabilní nález, doporučena další kontrola",
      availability: "available",
      study_id: "STU-TEST-001",
      doc_id: "DOC-TEST-001",
    },
    {
      kind: "mdt",
      date: "2026-10-22",
      modality: null,
      regions: [],
      label: "MDT 22. 10. (test)",
      availability: null,
      study_id: null,
      doc_id: null,
    },
  ],
  items: [
    {
      id: "ITEM-TEST-001",
      reasons: ["Srovnání s plánovaným PET", "Referenční studie v nálezu"],
      modality: "PET/CT",
      regions: ["whole_body"],
      target_date: "2025-05-15",
      availability: "not_found",
      state: "missing",
      holding_site: { id: "PRV-NTS", name: "Nemocnice Test-Sever" },
      evidence: {
        quote: "PET/CT v 05/2025 provedené na pracovišti Nemocnice Test-Sever (NTS)",
        doc_id: "DOC-TEST-001",
        confidence: 0.88,
      },
      request: {
        id: "PACS-REQ-000123",
        state: "SENT",
        updated_at: "2026-10-16T08:12:00",
      },
      simulated: true,
    },
    {
      id: "ITEM-TEST-002",
      reasons: ["Srovnání oblasti pánve"],
      modality: "MR",
      regions: ["pelvis"],
      target_date: "2026-02-20",
      availability: "not_in_pacs",
      state: "missing",
      holding_site: { id: "PRV-MOTOL", name: "Test-Motol, radiodiagnostika" },
      evidence: {
        quote: "MR pánve 02/2026 v našem zařízení",
        doc_id: "DOC-TEST-001",
        confidence: 0.54,
      },
      request: null,
      simulated: false,
    },
  ],
  open_issues: [
    {
      type: "low_confidence",
      text: "Datum studie MR pánve bylo extrahováno s nízkou jistotou (54 %).",
    },
  ],
  simulated: true,
};

const delay = <T>(value: T, ms = 250): Promise<T> =>
  new Promise((resolve) => setTimeout(() => resolve(value), ms));

export const mockApi = {
  getCase: (caseId: string): Promise<CaseDetail> => {
    if (caseId !== MOCK_CASE_ID) {
      return Promise.reject(new Error("Případ nenalezen (mock)"));
    }
    return delay(structuredClone(current));
  },
  getDocument: (_caseId: string, docId: string): Promise<SourceDocument> => {
    const doc = docs[docId];
    return doc ? delay(doc) : Promise.reject(new Error("Dokument nenalezen (mock)"));
  },
  recheck: (): Promise<void> => delay(undefined, 600),
  patchPlannedExam: (_caseId: string, patch: PlannedExamPatch): Promise<void> => {
    if (current.planned_exam) {
      current = {
        ...current,
        planned_exam: { ...current.planned_exam, ...patch },
      };
    }
    return delay(undefined);
  },
};
