/**
 * Library page -- grid of generated scenarios with scene-type filter.
 *
 * States rendered (in order of priority):
 *   1. error    -> ErrorBanner with retry
 *   2. loading  -> 6 skeleton cards
 *   3. empty    -> "No scenarios yet" + CTA to /generate
 *   4. data     -> grid of ScenarioCard
 *
 * Filter UI is a row of buttons (All / Menu / Sign / ...). Selecting
 * one updates local state which is part of the query key, so
 * TanStack auto-refetches with the new ``scene_type`` param.
 *
 * See DESIGN.md Section 8 (Library page).
 */

import { useState } from "react";
import { Link } from "react-router-dom";

import ErrorBanner from "../components/ErrorBanner";
import ScenarioCard from "../components/ScenarioCard";
import { flattenScenarios, useScenarios } from "../hooks/useScenarios";

const SCENE_TYPE_FILTERS: { value: string | null; label: string }[] = [
  { value: null, label: "All" },
  { value: "menu", label: "Menu" },
  { value: "sign", label: "Sign" },
  { value: "notice", label: "Notice" },
  { value: "label", label: "Label" },
  { value: "instruction", label: "Instruction" },
  { value: "map", label: "Map" },
];

export default function LibraryPage() {
  const [sceneType, setSceneType] = useState<string | null>(null);
  const {
    data,
    isPending,
    isError,
    error,
    refetch,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useScenarios({ sceneType });

  return (
    <section className="scenario-library-page space-y-4">
      <header className="scenario-library-header flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold text-slate-900">Library</h1>
        <Link
          to="/generate"
          className="scenario-library-new rounded bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700"
        >
          + New Scenario
        </Link>
      </header>

      <div
        role="toolbar"
        aria-label="Filter scenarios by scene type"
        className="scenario-library-filters flex flex-wrap items-center gap-2"
      >
        {SCENE_TYPE_FILTERS.map((opt) => {
          const isActive = sceneType === opt.value;
          return (
            <button
              key={opt.label}
              type="button"
              aria-pressed={isActive}
              onClick={() => setSceneType(opt.value)}
              className={[
                "scenario-library-filter rounded-full border px-3 py-1 text-xs",
                isActive
                  ? "border-slate-900 bg-slate-900 text-white"
                  : "border-slate-200 bg-white text-slate-600 hover:border-slate-300",
              ].join(" ")}
            >
              {opt.label}
            </button>
          );
        })}
      </div>

      {isError ? (
        <ErrorBanner
          message={error?.message || "Failed to load scenarios"}
          onRetry={() => refetch()}
        />
      ) : isPending ? (
        <LibrarySkeleton />
      ) : (
        <LibraryBody
          items={flattenScenarios(data)}
          hasNextPage={Boolean(hasNextPage)}
          isFetchingNextPage={isFetchingNextPage}
          onLoadMore={() => fetchNextPage()}
        />
      )}
    </section>
  );
}

interface LibraryBodyProps {
  items: ReturnType<typeof flattenScenarios>;
  hasNextPage: boolean;
  isFetchingNextPage: boolean;
  onLoadMore: () => void;
}

/** Renders the grid + load-more, or an empty state if no items. */
function LibraryBody({
  items,
  hasNextPage,
  isFetchingNextPage,
  onLoadMore,
}: LibraryBodyProps) {
  if (items.length === 0) {
    return (
      <div className="scenario-library-empty rounded-lg border border-dashed border-slate-300 bg-white p-10 text-center">
        <p className="text-slate-600">No scenarios yet.</p>
        <Link
          to="/generate"
          className="scenario-library-empty-cta mt-3 inline-block rounded bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700"
        >
          Generate your first one
        </Link>
      </div>
    );
  }

  return (
    <>
      <div className="scenario-library-grid grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {items.map((s) => (
          <ScenarioCard key={s.id} scenario={s} />
        ))}
      </div>
      {hasNextPage ? (
        <div className="text-center">
          <button
            type="button"
            onClick={onLoadMore}
            disabled={isFetchingNextPage}
            className="scenario-library-load-more rounded border border-slate-200 bg-white px-4 py-2 text-sm text-slate-700 hover:border-slate-300 disabled:opacity-50"
          >
            {isFetchingNextPage ? "Loading..." : "Load more"}
          </button>
        </div>
      ) : null}
    </>
  );
}

/** Six placeholder cards rendered while the first page is loading. */
function LibrarySkeleton() {
  return (
    <div
      data-testid="library-skeleton"
      className="scenario-library-skeleton grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3"
    >
      {Array.from({ length: 6 }).map((_, i) => (
        <div
          key={i}
          className="scenario-library-skeleton-card animate-pulse overflow-hidden rounded-lg border border-slate-200 bg-white"
        >
          <div className="aspect-[4/3] w-full bg-slate-100" />
          <div className="space-y-2 p-3">
            <div className="h-3 w-1/4 rounded bg-slate-100" />
            <div className="h-3 w-3/4 rounded bg-slate-100" />
            <div className="h-3 w-2/3 rounded bg-slate-100" />
          </div>
        </div>
      ))}
    </div>
  );
}
