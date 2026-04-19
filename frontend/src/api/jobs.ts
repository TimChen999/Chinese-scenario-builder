/**
 * Typed wrappers around the `/jobs/*` backend routes.
 *
 * The SSE endpoint is exposed as a plain URL string here -- consumers
 * (see `useJobStream` in Step 10) construct their own `EventSource`
 * because `fetch` does not give us an event-stream abstraction.
 */

import { apiFetch, apiUrl } from "./client";
import { JobStatusSchema, type JobStatus } from "./schemas";

/** GET /jobs/{job_id} -- snapshot poll. */
export function getJobStatus(jobId: string): Promise<JobStatus> {
  return apiFetch<JobStatus>(`/jobs/${jobId}`, JobStatusSchema);
}

/**
 * Returns the URL to subscribe to via `new EventSource(...)` for
 * server-sent progress events. Path includes the `/api` prefix so
 * Vite's proxy rewrites it during dev.
 */
export function jobStreamUrl(jobId: string): string {
  return apiUrl(`/jobs/${jobId}/stream`);
}
