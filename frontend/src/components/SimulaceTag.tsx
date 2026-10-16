import { cs } from "../i18n/cs";

export default function SimulaceTag() {
  return (
    <span
      title={cs.common.simulatedHint}
      className="inline-flex items-center rounded border border-dashed border-slate-500 bg-slate-50 px-1.5 py-0.5 text-[0.7rem] font-semibold uppercase tracking-wide text-slate-700"
    >
      {cs.common.simulated}
    </span>
  );
}
