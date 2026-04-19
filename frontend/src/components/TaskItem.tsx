/**
 * One interactive comprehension-task card on the Scenario page.
 *
 * Self-contained: owns its own input, mutation, and result panel.
 * Notifies the parent only of the FIRST result via
 * `onFirstResult` so the page-level score reflects first-attempt
 * correctness only (DESIGN.md Section 8 "Re-attempt" rule).
 *
 * Re-attempts are allowed: clicking "Try again" clears the result
 * panel and lets the user submit again, but the parent is never
 * notified again -- the score does not change.
 */

import { useState, type FormEvent } from "react";

import { useAnswerTask } from "../hooks/useAnswerTask";
import type { AnswerResult, TaskOut } from "../api/schemas";

interface TaskItemProps {
  /** Owning scenario id; used by the answer endpoint URL. */
  scenarioId: string;
  /** Task to render. */
  task: TaskOut;
  /** 1-indexed display number derived from the task's array position. */
  positionIndex: number;
  /**
   * Called once with the verdict of the user's FIRST submission.
   * Subsequent re-attempts do not re-fire this callback.
   */
  onFirstResult: (correct: boolean) => void;
}

/**
 * Render the task prompt + input + result panel. Stateful only
 * inside its own component; the parent supplies callbacks for
 * scoring.
 */
export default function TaskItem({
  scenarioId,
  task,
  positionIndex,
  onFirstResult,
}: TaskItemProps) {
  const [answer, setAnswer] = useState("");
  const [result, setResult] = useState<AnswerResult | null>(null);
  // First-attempt latch: parent gets notified once and only once.
  const [hasFirstAttempted, setHasFirstAttempted] = useState(false);
  const mutation = useAnswerTask(scenarioId, task.id);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!answer.trim()) return;
    try {
      const verdict = await mutation.mutateAsync(answer);
      setResult(verdict);
      if (!hasFirstAttempted) {
        setHasFirstAttempted(true);
        onFirstResult(verdict.correct);
      }
    } catch {
      /* mutation.error renders the failure below */
    }
  };

  const handleTryAgain = () => {
    setResult(null);
    setAnswer("");
    mutation.reset();
  };

  return (
    <div
      className="scenario-task-item rounded-lg border border-slate-200 bg-white p-3 shadow-sm"
      data-task-id={task.id}
    >
      <p className="scenario-task-prompt mb-2 text-sm font-medium text-slate-900">
        <span className="scenario-task-number text-slate-500">
          {positionIndex + 1}.{" "}
        </span>
        {task.prompt}
      </p>

      {result ? (
        <ResultPanel result={result} onTryAgain={handleTryAgain} />
      ) : (
        <form onSubmit={handleSubmit} className="space-y-2">
          <input
            type="text"
            aria-label={`Answer for task ${positionIndex + 1}`}
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            placeholder="Your answer"
            className="scenario-task-input w-full rounded border border-slate-300 px-2 py-1.5 text-sm focus:border-slate-500 focus:outline-none"
          />
          <div className="flex items-center gap-2">
            <button
              type="submit"
              disabled={mutation.isPending}
              className="scenario-task-submit rounded bg-slate-900 px-3 py-1 text-xs font-medium text-white hover:bg-slate-700 disabled:opacity-50"
            >
              {mutation.isPending ? "Submitting..." : "Submit"}
            </button>
            {mutation.error ? (
              <span className="scenario-task-error text-xs text-red-600">
                {mutation.error.message}
              </span>
            ) : null}
          </div>
        </form>
      )}
    </div>
  );
}

interface ResultPanelProps {
  result: AnswerResult;
  onTryAgain: () => void;
}

/** Shows correct / incorrect plus the canonical answer + explanation. */
function ResultPanel({ result, onTryAgain }: ResultPanelProps) {
  return (
    <div
      className={[
        "scenario-task-result space-y-2 rounded border-l-4 p-2 text-sm",
        result.correct
          ? "scenario-task-correct border-emerald-500 bg-emerald-50 text-emerald-900"
          : "scenario-task-wrong border-red-500 bg-red-50 text-red-900",
      ].join(" ")}
      role="status"
    >
      <p className="scenario-task-result-label font-semibold">
        {result.correct ? "✓ Correct" : "✗ Incorrect"}
      </p>
      {!result.correct ? (
        <p className="scenario-task-expected">
          Expected: <span className="font-cjk" lang="zh">{result.expected_answer}</span>
        </p>
      ) : null}
      {result.explanation ? (
        <p className="scenario-task-explanation text-slate-700">
          {result.explanation}
        </p>
      ) : null}
      <button
        type="button"
        onClick={onTryAgain}
        className="scenario-task-try-again rounded border border-slate-300 bg-white px-2 py-1 text-xs text-slate-700 hover:border-slate-400"
      >
        Try again
      </button>
    </div>
  );
}
