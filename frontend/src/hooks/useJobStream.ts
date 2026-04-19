/**
 * `useJobStream` -- subscribe to a backend job's SSE stream and
 * return its current state as React state.
 *
 * Returned shape:
 *   stage:       latest progress stage emitted, or null
 *   isDone:      true once a "done" event arrives
 *   scenarioId:  populated by the "done" event
 *   error:       populated by the "failed" event or low-level error
 *
 * The hook closes the EventSource on cleanup (component unmount or
 * jobId change) so we never leave dangling streams open.
 *
 * Tests inject a mock `EventSource` (see tests/mocks/eventsource.ts)
 * because jsdom does not ship one.
 */

import { useEffect, useState } from "react";

import { jobStreamUrl } from "../api/jobs";

/** Shape returned by {@link useJobStream}. */
export interface JobStreamState {
  /** Latest stage from a "progress" event; null until first event. */
  stage: string | null;
  /** True once a "done" event has been received. */
  isDone: boolean;
  /** scenario_id from the "done" event, or null until then. */
  scenarioId: string | null;
  /** error_message from a "failed" event, or null. */
  error: string | null;
}

/**
 * Subscribe to the SSE stream for ``jobId``. Pass ``null`` to defer
 * subscription (e.g. before the user has submitted the form).
 */
export function useJobStream(jobId: string | null): JobStreamState {
  const [state, setState] = useState<JobStreamState>({
    stage: null,
    isDone: false,
    scenarioId: null,
    error: null,
  });

  useEffect(() => {
    if (!jobId) return;
    // Reset state for the new job; otherwise switching jobs would
    // briefly show the previous job's stage.
    setState({ stage: null, isDone: false, scenarioId: null, error: null });

    const source = new EventSource(jobStreamUrl(jobId));

    const onProgress = (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data);
        if (typeof data.stage === "string") {
          setState((prev) => ({ ...prev, stage: data.stage }));
        }
      } catch {
        /* ignore malformed payload */
      }
    };

    const onDone = (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data);
        setState((prev) => ({
          ...prev,
          isDone: true,
          scenarioId: typeof data.scenario_id === "string" ? data.scenario_id : null,
        }));
      } catch {
        setState((prev) => ({ ...prev, isDone: true }));
      }
      source.close();
    };

    const onFailed = (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data);
        setState((prev) => ({
          ...prev,
          error:
            typeof data.error_message === "string"
              ? data.error_message
              : "Generation failed",
        }));
      } catch {
        setState((prev) => ({ ...prev, error: "Generation failed" }));
      }
      source.close();
    };

    source.addEventListener("progress", onProgress);
    source.addEventListener("done", onDone);
    source.addEventListener("failed", onFailed);
    source.onerror = () => {
      // Browser fires onerror for both transient reconnects and
      // hard failures. We treat repeated errors after a "done"
      // event as harmless; before "done" they become a banner.
      setState((prev) =>
        prev.isDone || prev.error ? prev : { ...prev, error: "Connection lost" },
      );
    };

    return () => {
      source.removeEventListener("progress", onProgress);
      source.removeEventListener("done", onDone);
      source.removeEventListener("failed", onFailed);
      source.close();
    };
  }, [jobId]);

  return state;
}
