/**
 * `useHistory` -- TanStack infinite-query hook over `/history`.
 *
 * Filter changes (correct-only / incorrect-only) bump the query key
 * so a fresh fetch is issued; the previous filter's pages are
 * dropped to avoid mixing them in the rendered list.
 */

import { useInfiniteQuery, type UseInfiniteQueryResult } from "@tanstack/react-query";

import { listHistory } from "../api/history";
import type { HistoryItem, HistoryList } from "../api/schemas";

/** Options accepted by {@link useHistory}. */
export interface UseHistoryOptions {
  correctOnly?: boolean;
  incorrectOnly?: boolean;
  limit?: number;
}

/**
 * Fetch attempt history with infinite pagination.
 * @returns the raw `useInfiniteQuery` result.
 */
export function useHistory(
  opts: UseHistoryOptions = {},
): UseInfiniteQueryResult<{ pages: HistoryList[]; pageParams: unknown[] }, Error> {
  const limit = opts.limit ?? 20;
  return useInfiniteQuery<
    HistoryList,
    Error,
    { pages: HistoryList[]; pageParams: unknown[] },
    [string, boolean, boolean, number],
    string | undefined
  >({
    queryKey: [
      "history",
      Boolean(opts.correctOnly),
      Boolean(opts.incorrectOnly),
      limit,
    ],
    queryFn: ({ pageParam }) =>
      listHistory({
        limit,
        cursor: pageParam ?? null,
        correctOnly: opts.correctOnly,
        incorrectOnly: opts.incorrectOnly,
      }),
    initialPageParam: undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

/** Helper: flatten paginated history pages into a single list. */
export function flattenHistory(
  data: { pages: HistoryList[] } | undefined,
): HistoryItem[] {
  return data?.pages.flatMap((p) => p.items) ?? [];
}
