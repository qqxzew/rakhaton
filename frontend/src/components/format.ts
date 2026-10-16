import { cs } from "../i18n/cs";

/** "2026-10-22" -> "22. 10. 2026" (no Date object, avoids timezone shifts) */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return cs.common.none;
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return iso;
  return `${Number(m[3])}. ${Number(m[2])}. ${m[1]}`;
}

export function formatDateTime(iso: string): string {
  const time = /T(\d{2}:\d{2})/.exec(iso)?.[1];
  return time ? `${formatDate(iso)} ${time}` : formatDate(iso);
}

/** "2026-10-22" -> "22. 10." */
export function formatDayMonth(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  return m ? `${Number(m[3])}. ${Number(m[2])}.` : iso;
}

const WEEKDAYS = ["Ne", "Po", "Út", "St", "Čt", "Pá", "So"];

/** Short Czech weekday of an ISO date, computed in UTC so the timezone cannot move it. */
export function weekdayShort(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return "";
  return WEEKDAYS[new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]))).getUTCDay()];
}

/** Month-precision citations only know the month, so the approximate day is not shown. */
export function formatItemDate(iso: string | null | undefined, precision?: string | null): string {
  if (!iso) return cs.common.none;
  const m = /^(\d{4})-(\d{2})/.exec(iso);
  if (m && precision === "month") return `${m[2]}/${m[1]}`;
  if (m && precision === "year") return m[1];
  return formatDate(iso);
}

export function regionLabel(region: string): string {
  return cs.regions[region] ?? region;
}

export function regionsText(regions: string[]): string {
  return regions.length ? regions.map(regionLabel).join(", ") : cs.common.none;
}

export function percent(confidence: number | null | undefined): string {
  return confidence == null ? cs.common.none : `${Math.round(confidence * 100)} %`;
}

/** Inverse of regionLabel for the edit form: accepts Czech labels or raw codes. */
export function parseRegions(input: string): string[] {
  const byLabel = new Map(Object.entries(cs.regions).map(([k, v]) => [v.toLowerCase(), k]));
  return input
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean)
    .map((s) => byLabel.get(s.toLowerCase()) ?? s);
}
