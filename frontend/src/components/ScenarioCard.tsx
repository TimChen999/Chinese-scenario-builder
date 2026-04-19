/**
 * Library-grid card for one scenario.
 *
 * Renders a clickable thumbnail + headline metadata. Designed to be
 * informationally cheap: the parent page can render a hundred of
 * these without any per-card HTTP fetch.
 *
 * The whole card is a single React Router `<Link>` so click + middle-
 * click + cmd-click all work the way users expect.
 */

import { Link } from "react-router-dom";

import type { ScenarioSummary } from "../api/schemas";

interface ScenarioCardProps {
  scenario: ScenarioSummary;
}

/**
 * Format an ISO datetime as a coarse "X days ago" string.
 *
 * Coarse on purpose -- a library grid's job is not to show exact
 * times, and absolute clocks across timezones invite confusion.
 */
function relativeAge(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const minutes = (Date.now() - then) / 60_000;
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${Math.floor(minutes)}m ago`;
  const hours = minutes / 60;
  if (hours < 24) return `${Math.floor(hours)}h ago`;
  const days = hours / 24;
  if (days < 7) return `${Math.floor(days)}d ago`;
  const weeks = days / 7;
  if (weeks < 5) return `${Math.floor(weeks)}w ago`;
  return new Date(iso).toLocaleDateString();
}

/**
 * Render a single library card. Class names use the `scenario-`
 * prefix so they cannot collide with the Pinyin Tool extension's
 * `hg-*` overlay classes (DESIGN.md Section 9).
 */
export default function ScenarioCard({ scenario }: ScenarioCardProps) {
  return (
    <Link
      to={`/scenarios/${scenario.id}`}
      className="scenario-card group flex flex-col overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm transition hover:border-slate-300 hover:shadow"
    >
      {scenario.source_image_url ? (
        <img
          src={scenario.source_image_url}
          alt=""
          className="scenario-card-thumb aspect-[4/3] w-full object-cover"
          loading="lazy"
        />
      ) : (
        <div className="scenario-card-thumb-placeholder aspect-[4/3] w-full bg-slate-100 text-slate-400 flex items-center justify-center text-sm">
          No image
        </div>
      )}

      <div className="scenario-card-body flex flex-1 flex-col gap-2 p-3">
        <span className="scenario-card-type-badge inline-block w-fit rounded bg-slate-100 px-2 py-0.5 text-xs uppercase tracking-wide text-slate-600">
          {scenario.scene_type}
        </span>
        <p className="scenario-card-prompt line-clamp-2 text-sm font-medium text-slate-900">
          {scenario.request_prompt}
        </p>
        <p className="scenario-card-setup line-clamp-1 font-cjk text-sm text-slate-500" lang="zh">
          {scenario.scene_setup}
        </p>
        <div className="scenario-card-meta mt-auto flex items-center justify-between text-xs text-slate-500">
          <span>{scenario.task_count} task{scenario.task_count === 1 ? "" : "s"}</span>
          <span>{relativeAge(scenario.created_at)}</span>
        </div>
      </div>
    </Link>
  );
}
