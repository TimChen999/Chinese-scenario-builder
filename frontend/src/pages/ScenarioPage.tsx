/**
 * Scenario reader page -- image + scene_setup + raw_content + tasks.
 *
 * Composes with the Pinyin Tool extension (DESIGN.md Section 9):
 *   - scene_setup is rendered in a plain `<p lang="zh">` so the
 *     extension's mouseup-driven selection works on it.
 *   - raw_content goes through `<RawContent>` which enforces the
 *     extension-safety contract.
 *   - The reader root carries no `mouseup` / `mousedown` handler.
 *   - All class names use the `scenario-` prefix; none start with
 *     `hg-`.
 *
 * Layout: three columns on desktop (>= 1024 px), single stacked
 * column on smaller viewports. See `useIsDesktop` for the
 * breakpoint wiring.
 *
 * See DESIGN.md Section 8 (Scenario page).
 */

import { useState } from "react";
import { useParams } from "react-router-dom";

import RawContent from "../components/RawContent";
import TaskItem from "../components/TaskItem";
import ErrorBanner from "../components/ErrorBanner";
import { ApiError } from "../api/client";
import { useIsDesktop } from "../hooks/useIsDesktop";
import { useScenario } from "../hooks/useScenario";

export default function ScenarioPage() {
  const { id } = useParams<{ id: string }>();
  const isDesktop = useIsDesktop();
  const query = useScenario(id);
  // Score state lives on the page, not on the task, so it can sum
  // across the three task cards. Only first-attempt verdicts count.
  const [firstAttemptScore, setFirstAttemptScore] = useState(0);

  if (query.isPending) return <ScenarioSkeleton />;

  if (query.isError) {
    const apiErr =
      query.error instanceof ApiError ? query.error : (null as ApiError | null);
    if (apiErr?.status === 404) {
      return (
        <div className="scenario-not-found py-12 text-center">
          <h1 className="text-2xl font-semibold text-slate-700">
            Scenario not found
          </h1>
          <p className="mt-2 text-slate-500">
            This scenario does not exist or has been deleted.
          </p>
        </div>
      );
    }
    return (
      <ErrorBanner
        message={query.error?.message || "Failed to load scenario"}
        onRetry={() => query.refetch()}
      />
    );
  }

  const scenario = query.data;
  if (!scenario) return null;

  const handleFirstResult = (correct: boolean) => {
    if (correct) setFirstAttemptScore((s) => s + 1);
  };

  return (
    <div
      data-testid="scenario-grid"
      data-layout={isDesktop ? "grid" : "stacked"}
      className={[
        "scenario-reader gap-6",
        isDesktop ? "grid grid-cols-3" : "flex flex-col",
      ].join(" ")}
    >
      <aside className="scenario-reader-image">
        {scenario.source_image_url ? (
          <img
            src={scenario.source_image_url}
            alt="source"
            className="w-full rounded border border-slate-200 object-contain"
          />
        ) : (
          <div className="flex aspect-square w-full items-center justify-center rounded border border-dashed border-slate-300 text-slate-400">
            No image
          </div>
        )}
      </aside>

      <section className="scenario-reader-text space-y-4">
        <div>
          <h2 className="scenario-section-label text-xs uppercase tracking-wide text-slate-500">
            Setting
          </h2>
          <p
            lang="zh"
            data-scenario-content="setup"
            className="scenario-scene-setup mt-1 font-cjk text-base text-slate-800"
          >
            {scenario.scene_setup}
          </p>
        </div>

        <hr className="border-slate-200" />

        <div>
          <h2 className="scenario-section-label text-xs uppercase tracking-wide text-slate-500">
            Source text
          </h2>
          <RawContent text={scenario.raw_content} />
        </div>
      </section>

      <section className="scenario-reader-tasks space-y-3">
        <h2 className="scenario-section-label text-xs uppercase tracking-wide text-slate-500">
          Tasks
        </h2>
        {scenario.tasks.map((task, idx) => (
          <TaskItem
            key={task.id}
            scenarioId={scenario.id}
            task={task}
            positionIndex={idx}
            onFirstResult={handleFirstResult}
          />
        ))}
        <div className="scenario-reader-score mt-2 text-sm text-slate-600">
          Score: {firstAttemptScore}/{scenario.tasks.length}
        </div>
      </section>
    </div>
  );
}

/** Loading-state skeleton used while the scenario fetch is pending. */
function ScenarioSkeleton() {
  return (
    <div
      data-testid="scenario-skeleton"
      className="scenario-reader-skeleton grid animate-pulse grid-cols-1 gap-6 lg:grid-cols-3"
    >
      <div className="aspect-[4/3] rounded bg-slate-100" />
      <div className="space-y-3">
        <div className="h-4 w-3/4 rounded bg-slate-100" />
        <div className="h-4 w-2/3 rounded bg-slate-100" />
        <div className="h-32 w-full rounded bg-slate-100" />
      </div>
      <div className="space-y-3">
        <div className="h-12 rounded bg-slate-100" />
        <div className="h-12 rounded bg-slate-100" />
        <div className="h-12 rounded bg-slate-100" />
      </div>
    </div>
  );
}
