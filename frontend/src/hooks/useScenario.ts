/**
 * `useScenario` -- TanStack Query hook for one full scenario.
 *
 * Disabled when ``id`` is undefined so the route param can be
 * absent on initial mount without firing a bogus fetch.
 */

import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { getScenario } from "../api/scenarios";
import type { ScenarioOut } from "../api/schemas";

/**
 * Fetches `GET /scenarios/{id}`. Pass undefined to defer the query.
 */
export function useScenario(
  id: string | undefined,
): UseQueryResult<ScenarioOut, Error> {
  return useQuery({
    queryKey: ["scenario", id],
    queryFn: () => getScenario(id!),
    enabled: Boolean(id),
  });
}
