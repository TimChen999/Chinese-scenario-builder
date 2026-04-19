/**
 * Typed wrappers around the `/scenarios/*` backend routes.
 *
 * Each function returns `Promise<T>` where `T` is inferred from the
 * Zod schema, so callers get autocomplete on the response shape.
 */

import { apiFetch } from "./client";
import {
  AnswerResultSchema,
  GenerateResponseSchema,
  ScenarioListSchema,
  ScenarioOutSchema,
  type AnswerResult,
  type GenerateResponse,
  type ScenarioList,
  type ScenarioOut,
} from "./schemas";

/** Options accepted by {@link listScenarios}. */
export interface ListScenariosOpts {
  limit?: number;
  cursor?: string | null;
  sceneType?: string | null;
}

/** GET /scenarios -- cursor-paginated library list. */
export function listScenarios(opts: ListScenariosOpts = {}): Promise<ScenarioList> {
  const params = new URLSearchParams();
  if (opts.limit) params.set("limit", String(opts.limit));
  if (opts.cursor) params.set("cursor", opts.cursor);
  if (opts.sceneType) params.set("scene_type", opts.sceneType);
  const qs = params.toString();
  return apiFetch<ScenarioList>(`/scenarios${qs ? `?${qs}` : ""}`, ScenarioListSchema);
}

/** GET /scenarios/{id} -- full scenario for the reader page. */
export function getScenario(id: string): Promise<ScenarioOut> {
  return apiFetch<ScenarioOut>(`/scenarios/${id}`, ScenarioOutSchema);
}

/** Body for {@link generateScenario}. Mirrors the backend's `GenerateRequest`. */
export interface GenerateBody {
  prompt: string;
  scene_hint?: string;
  region?: string;
  format_hint?: string;
}

/** POST /scenarios/generate -- start a generation job, returns its id. */
export function generateScenario(body: GenerateBody): Promise<GenerateResponse> {
  return apiFetch<GenerateResponse>(
    "/scenarios/generate",
    GenerateResponseSchema,
    { method: "POST", body: JSON.stringify(body) },
  );
}

/** POST /scenarios/{id}/tasks/{task_id}/answer -- submit a task answer. */
export function submitAnswer(
  scenarioId: string,
  taskId: string,
  answer: string,
): Promise<AnswerResult> {
  return apiFetch<AnswerResult>(
    `/scenarios/${scenarioId}/tasks/${taskId}/answer`,
    AnswerResultSchema,
    { method: "POST", body: JSON.stringify({ answer }) },
  );
}
