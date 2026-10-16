import { cs } from "../i18n/cs";
import type { Availability } from "../services/api-types";

const STYLE: Record<Availability, string> = {
  available: "border-green-600 bg-green-50 text-green-900",
  not_in_pacs: "border-red-600 bg-red-50 text-red-900",
  unknown: "border-amber-600 bg-amber-50 text-amber-900",
  not_found: "border-red-600 bg-red-50 text-red-900",
};

const GLYPH: Record<Availability, string> = {
  available: "✓",
  not_in_pacs: "✕",
  unknown: "?",
  not_found: "✕",
};

export default function AvailabilityChip({ availability }: { availability: Availability }) {
  return (
    <span
      className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-[0.8rem] font-semibold ${STYLE[availability]}`}
    >
      <span aria-hidden="true">{GLYPH[availability]}</span>
      {cs.availability[availability]}
    </span>
  );
}
