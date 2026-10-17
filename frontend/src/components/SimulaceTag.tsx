import { cs } from "../i18n/cs";

/** Dashed outline tag marking simulated data (CLAUDE.md hard rule 5). */
export default function SimulaceTag() {
  return (
    <span
      title={cs.common.simulatedHint}
      className="inline-flex items-center whitespace-nowrap rounded-[3px] border border-dashed border-nis-ink bg-white px-1.5 text-2xs font-bold uppercase leading-5 tracking-wide text-nis-ink"
    >
      {cs.common.simulated}
    </span>
  );
}
