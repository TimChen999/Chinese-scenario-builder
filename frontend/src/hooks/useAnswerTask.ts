/**
 * `useAnswerTask` -- mutation wrapper for the answer endpoint.
 *
 * Each TaskItem owns its own mutation instance so concurrent
 * submissions on different tasks do not interfere with each other.
 */

import { useMutation, type UseMutationResult } from "@tanstack/react-query";

import { submitAnswer } from "../api/scenarios";
import type { AnswerResult } from "../api/schemas";

/**
 * Returns a mutation whose `mutateAsync(answer)` POSTs the user's
 * answer for ``taskId`` under ``scenarioId`` and resolves to the
 * server's :class:`AnswerResult` verdict.
 */
export function useAnswerTask(
  scenarioId: string,
  taskId: string,
): UseMutationResult<AnswerResult, Error, string> {
  return useMutation({
    mutationFn: (answer: string) => submitAnswer(scenarioId, taskId, answer),
  });
}
