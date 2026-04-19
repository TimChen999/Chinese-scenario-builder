/**
 * Default MSW request handlers.
 *
 * Tests typically override these per-case via `server.use(...)`. The
 * defaults exist so the request-mock setup itself does not error
 * during teardown when no handler matches.
 *
 * Grouping: one handler per route family (DESIGN.md Section 11).
 */

import { http, HttpResponse } from "msw";

export const handlers = [
  http.get("/api/healthz", () => HttpResponse.json({ status: "ok" })),
];
