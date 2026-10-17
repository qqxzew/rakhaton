import { cs } from "../i18n/cs";
import SimulaceTag from "./SimulaceTag";
import { Panel } from "./ui";

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
    <Panel
      id="demo-controls"
      icon="pulse"
      className="border-dashed"
      title={
        <>
          {cs.demoControls.title} <SimulaceTag />
          <span className="text-sm font-normal text-nis-muted">({cs.demoControls.soon})</span>
        </>
      }
    >
      <div className="flex flex-wrap gap-2">
        {ACTIONS.map((label) => (
          <button key={label} type="button" disabled className="nis-btn-secondary">
            {label}
          </button>
        ))}
      </div>
    </Panel>
  );
}
