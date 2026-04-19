/**
 * `useGenerateScenario` -- TanStack mutation wrapper for the
 * "Start a generation job" call.
 *
 * Thin on purpose; the hook just exposes `mutateAsync` so the page
 * can `await` the resulting `{ job_id }` and feed it into
 * `useJobStream`.
 */

import { useMutation, type UseMutationResult } from "@tanstack/react-query";

import { generateScenario, type GenerateBody } from "../api/scenarios";
import type { GenerateResponse } from "../api/schemas";

/** Mutation hook that POSTs a generation request and returns the job id. */
export function useGenerateScenario(): UseMutationResult<
  GenerateResponse,
  Error,
  GenerateBody
> {
  return useMutation({
    mutationFn: (body: GenerateBody) => generateScenario(body),
  });
}
