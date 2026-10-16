import { cs } from "../i18n/cs";
import SimulaceTag from "./SimulaceTag";

const ACTIONS = [
  cs.demoControls.approve,
  cs.demoControls.waive,
  cs.demoControls.simulateReply,
  cs.demoControls.simulateCall,
  cs.demoControls.simulateDelivery,
  cs.demoControls.showMessage,
];

// Placeholder for the request actions of a later task; hidden in presentation mode.
export default function DemoControls() {
  return (
    <section
      className="rounded-xl border border-dashed border-slate-400 bg-slate-50 p-4"
      aria-labelledby="demo-controls-title"
    >
      <h2 id="demo-controls-title" className="mb-2 flex items-center gap-2 text-lg font-bold">
        {cs.demoControls.title} <SimulaceTag />
        <span className="text-sm font-normal text-slate-600">({cs.demoControls.soon})</span>
      </h2>
      <div className="flex flex-wrap gap-2">
        {ACTIONS.map((label) => (
          <button
            key={label}
            type="button"
            disabled
            className="cursor-not-allowed rounded border border-slate-400 px-3 py-1 text-slate-500"
          >
            {label}
          </button>
        ))}
      </div>
    </section>
  );
}
