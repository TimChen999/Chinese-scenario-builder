/**
 * `useScenarios` -- TanStack Query hook for the library page.
 *
 * Wraps `listScenarios` in an infinite query so pagination just
 * requires `fetchNextPage()` calls; the page returns one flattened
 * list to its consumer for easy mapping.
 *
 * See DESIGN.md Section 8 ("Library page") + Step 9.
 */

import { useInfiniteQuery, type UseInfiniteQueryResult } from "@tanstack/react-query";

import { listScenarios } from "../api/scenarios";
import type { ScenarioList, ScenarioSummary } from "../api/schemas";

/** Options accepted by {@link useScenarios}. */
export interface UseScenariosOptions {
  sceneType?: string | null;
  limit?: number;
}

/**
 * Fetches scenarios via `GET /scenarios`. The query key includes the
 * scene-type filter so changing it triggers a fresh fetch (rather
 * than appending to the existing pages).
 *
 * @returns the raw `useInfiniteQuery` result. Consumers typically
 *          read `data?.pages.flatMap(p => p.items)` for a flat list.
 */
export function useScenarios(
  opts: UseScenariosOptions = {},
): UseInfiniteQueryResult<{ pages: ScenarioList[]; pageParams: unknown[] }, Error> {
  const limit = opts.limit ?? 20;
  return useInfiniteQuery<
    ScenarioList,
    Error,
    { pages: ScenarioList[]; pageParams: unknown[] },
    [string, string | null, number],
    string | undefined
  >({
    queryKey: ["scenarios", opts.sceneType ?? null, limit],
    queryFn: ({ pageParam }) =>
      listScenarios({
        limit,
        sceneType: opts.sceneType ?? null,
        cursor: pageParam ?? null,
      }),
    initialPageParam: undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

/**
 * Helper: flatten the pages of a `useScenarios` result into a single
 * `ScenarioSummary[]`. Convenient for `.map(...)` in the page.
 */
export function flattenScenarios(
  data: { pages: ScenarioList[] } | undefined,
): ScenarioSummary[] {
  return data?.pages.flatMap((page) => page.items) ?? [];
}
