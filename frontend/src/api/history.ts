/**
 * Typed wrapper around `GET /history`.
 *
 * Kept separate from `scenarios.ts` even though the design folder
 * structure does not enumerate this file, because mixing the
 * two route families in one module would obscure the API surface.
 */

import { apiFetch } from "./client";
import { HistoryListSchema, type HistoryList } from "./schemas";

/** Options accepted by {@link listHistory}. */
export interface ListHistoryOpts {
  limit?: number;
  cursor?: string | null;
  correctOnly?: boolean;
  incorrectOnly?: boolean;
}

/** GET /history -- cursor-paginated attempts, newest first. */
export function listHistory(opts: ListHistoryOpts = {}): Promise<HistoryList> {
  const params = new URLSearchParams();
  if (opts.limit) params.set("limit", String(opts.limit));
  if (opts.cursor) params.set("cursor", opts.cursor);
  if (opts.correctOnly) params.set("correct_only", "true");
  if (opts.incorrectOnly) params.set("incorrect_only", "true");
  const qs = params.toString();
  return apiFetch<HistoryList>(
    `/history${qs ? `?${qs}` : ""}`,
    HistoryListSchema,
  );
}
