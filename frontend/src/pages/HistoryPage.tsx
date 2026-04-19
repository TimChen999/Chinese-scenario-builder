/**
 * History page -- list of past attempts with correct/incorrect filter.
 *
 * Each row links back to the originating scenario for re-review. The
 * empty state nudges new users toward answering tasks before this
 * page is useful (DESIGN.md Section 8 "History page").
 */

import { useState } from "react";
import { Link } from "react-router-dom";

import ErrorBanner from "../components/ErrorBanner";
import { flattenHistory, useHistory } from "../hooks/useHistory";
import type { HistoryItem } from "../api/schemas";

type Filter = "all" | "correct" | "incorrect";

const FILTERS: { value: Filter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "correct", label: "Correct" },
  { value: "incorrect", label: "Incorrect" },
];

export default function HistoryPage() {
  const [filter, setFilter] = useState<Filter>("all");
  const opts = {
    correctOnly: filter === "correct",
    incorrectOnly: filter === "incorrect",
  };
  const {
    data,
    isPending,
    isError,
    error,
    refetch,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useHistory(opts);

  return (
    <section className="scenario-history-page space-y-4">
      <h1 className="text-2xl font-semibold text-slate-900">History</h1>

      <div
        role="toolbar"
        aria-label="Filter attempts"
        className="scenario-history-filters flex items-center gap-2"
      >
        {FILTERS.map((opt) => {
          const isActive = filter === opt.value;
          return (
            <button
              key={opt.value}
              type="button"
              aria-pressed={isActive}
              onClick={() => setFilter(opt.value)}
              className={[
                "scenario-history-filter rounded-full border px-3 py-1 text-xs",
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
          message={error?.message || "Failed to load history"}
          onRetry={() => refetch()}
        />
      ) : isPending ? (
        <HistorySkeleton />
      ) : (
        <HistoryBody
          items={flattenHistory(data)}
          hasNextPage={Boolean(hasNextPage)}
          isFetchingNextPage={isFetchingNextPage}
          onLoadMore={() => fetchNextPage()}
        />
      )}
    </section>
  );
}

interface HistoryBodyProps {
  items: HistoryItem[];
  hasNextPage: boolean;
  isFetchingNextPage: boolean;
  onLoadMore: () => void;
}

function HistoryBody({
  items,
  hasNextPage,
  isFetchingNextPage,
  onLoadMore,
}: HistoryBodyProps) {
  if (items.length === 0) {
    return (
      <div className="scenario-history-empty rounded-lg border border-dashed border-slate-300 bg-white p-10 text-center">
        <p className="text-slate-600">
          Answer some tasks to see your history.
        </p>
        <Link
          to="/generate"
          className="scenario-history-empty-cta mt-3 inline-block rounded bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700"
        >
          Generate a scenario
        </Link>
      </div>
    );
  }

  return (
    <>
      <ul className="scenario-history-list divide-y divide-slate-200 rounded border border-slate-200 bg-white">
        {items.map((item) => (
          <HistoryRow key={item.attempt_id} item={item} />
        ))}
      </ul>
      {hasNextPage ? (
        <div className="text-center">
          <button
            type="button"
            onClick={onLoadMore}
            disabled={isFetchingNextPage}
            className="scenario-history-load-more rounded border border-slate-200 bg-white px-4 py-2 text-sm text-slate-700 hover:border-slate-300 disabled:opacity-50"
          >
            {isFetchingNextPage ? "Loading..." : "Load more"}
          </button>
        </div>
      ) : null}
    </>
  );
}

/** One row in the history list; links back to the originating scenario. */
function HistoryRow({ item }: { item: HistoryItem }) {
  const date = new Date(item.attempted_at);
  return (
    <li className="scenario-history-row flex items-start gap-3 px-4 py-3 text-sm">
      <span
        aria-label={item.is_correct ? "correct" : "incorrect"}
        className={[
          "scenario-history-badge mt-0.5 inline-flex h-5 w-5 items-center justify-center rounded-full text-xs",
          item.is_correct
            ? "bg-emerald-100 text-emerald-700"
            : "bg-red-100 text-red-700",
        ].join(" ")}
      >
        {item.is_correct ? "✓" : "✗"}
      </span>
      <div className="flex-1">
        <p className="text-slate-700">
          <span className="text-slate-400">
            {date.toLocaleDateString()}{" "}
          </span>
          <span className="font-medium">{item.scenario_title}</span>
          <span className="text-slate-500"> — {item.task_prompt}</span>
        </p>
        <p className="mt-1 text-slate-600">
          You: <span className="font-cjk" lang="zh">{item.user_answer || "(blank)"}</span>
          {!item.is_correct ? (
            <>
              {"   "}Expected:{" "}
              <span className="font-cjk" lang="zh">{item.expected_answer}</span>
            </>
          ) : null}
        </p>
        <Link
          to={`/scenarios/${item.scenario_id}`}
          className="scenario-history-link mt-1 inline-block text-xs text-blue-600 hover:underline"
        >
          Review scenario
        </Link>
      </div>
    </li>
  );
}

function HistorySkeleton() {
  return (
    <ul
      data-testid="history-skeleton"
      className="scenario-history-skeleton divide-y divide-slate-200 rounded border border-slate-200 bg-white"
    >
      {Array.from({ length: 5 }).map((_, i) => (
        <li key={i} className="animate-pulse p-3">
          <div className="h-3 w-3/4 rounded bg-slate-100" />
          <div className="mt-2 h-3 w-1/2 rounded bg-slate-100" />
        </li>
      ))}
    </ul>
  );
}
