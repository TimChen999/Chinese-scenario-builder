/**
 * Step-by-step progress checklist shown while a generation job runs.
 *
 * Renders the canonical six stages from DESIGN.md Section 7 with a
 * status icon per row:
 *   - "completed" (✓): the stage has been passed
 *   - "current"   (⏳): the stage is currently in progress
 *   - "pending"   (·): not yet reached
 *
 * Each row carries `data-stage-state` so tests can assert on it
 * without inspecting class names.
 */

interface GenerationStatusProps {
  /** Latest stage name from the SSE stream, or null before any event. */
  currentStage: string | null;
  /** When true, all stages are rendered as completed. */
  isDone: boolean;
}

interface StageDescriptor {
  key: string;
  label: string;
}

/**
 * Stage order. The keys must match the strings the orchestrator
 * emits in `on_progress` (DESIGN.md Section 7).
 */
const STAGES: StageDescriptor[] = [
  { key: "queries_generated", label: "Generated search queries" },
  { key: "images_searched", label: "Found candidate images" },
  { key: "images_downloaded", label: "Downloaded images" },
  { key: "images_filtered", label: "Filtered for quality" },
  { key: "ocr_in_progress", label: "Reading text from images" },
  { key: "assembling", label: "Assembling scenario" },
];

/** Status enum used by the renderer + carried in the DOM via data attribute. */
type StageState = "completed" | "current" | "pending";

function stateFor(
  stageKey: string,
  currentStage: string | null,
  isDone: boolean,
): StageState {
  if (isDone) return "completed";
  if (currentStage === null) return "pending";

  const stageIdx = STAGES.findIndex((s) => s.key === stageKey);
  const currentIdx = STAGES.findIndex((s) => s.key === currentStage);
  if (currentIdx < 0) {
    // Unknown current stage -- mark only this one as current if its
    // key matches verbatim (fall through to pending otherwise).
    return stageKey === currentStage ? "current" : "pending";
  }
  if (stageIdx < currentIdx) return "completed";
  if (stageIdx === currentIdx) return "current";
  return "pending";
}

const ICON: Record<StageState, string> = {
  completed: "✓",
  current: "⏳",
  pending: "·",
};

/**
 * Render the progress checklist. The "current" row gets an
 * `animate-pulse` class so the user sees ongoing work.
 */
export default function GenerationStatus({
  currentStage,
  isDone,
}: GenerationStatusProps) {
  return (
    <ul
      className="scenario-generation-status divide-y divide-slate-200 rounded border border-slate-200 bg-white"
      aria-label="Generation progress"
    >
      {STAGES.map((stage) => {
        const state = stateFor(stage.key, currentStage, isDone);
        return (
          <li
            key={stage.key}
            data-stage-state={state}
            className={[
              "scenario-generation-stage flex items-center gap-3 px-4 py-2 text-sm",
              state === "completed" ? "text-slate-700" : "",
              state === "current" ? "scenario-stage-current animate-pulse text-slate-900" : "",
              state === "pending" ? "text-slate-400" : "",
            ].join(" ")}
          >
            <span
              aria-hidden
              className={[
                "scenario-generation-stage-icon inline-block w-4 text-center",
                state === "completed" ? "text-emerald-500" : "",
                state === "current" ? "text-blue-500" : "",
              ].join(" ")}
            >
              {ICON[state]}
            </span>
            <span>{stage.label}</span>
          </li>
        );
      })}
    </ul>
  );
}
