/**
 * Zod runtime schemas mirroring the backend Pydantic shapes.
 *
 * Two reasons we duplicate the shapes here in TypeScript:
 *   1. Type-safe inference: every `apiFetch` call returns an
 *      `infer`'d type, so consumers get autocomplete + compile errors.
 *   2. Runtime validation: catches contract drift between FE and BE
 *      early; better than crashing in a deeply nested render path.
 *
 * See DESIGN.md Section 5 (Data Model) for the canonical shapes.
 */

import { z } from "zod";

// Loose ISO datetime (the backend emits naive UTC; we accept either).
const datetime = z.string();
const nullableString = z.string().nullable().optional();

export const TaskOutSchema = z.object({
  id: z.string(),
  position_index: z.number().int(),
  prompt: z.string(),
  answer_type: z.string(),
  explanation: nullableString,
});
export type TaskOut = z.infer<typeof TaskOutSchema>;

export const ScenarioOutSchema = z.object({
  id: z.string(),
  request_prompt: z.string(),
  scene_type: z.string(),
  scene_setup: z.string(),
  raw_content: z.string(),
  source_image_url: nullableString,
  source_url: nullableString,
  created_at: datetime,
  tasks: z.array(TaskOutSchema),
});
export type ScenarioOut = z.infer<typeof ScenarioOutSchema>;

export const ScenarioSummarySchema = z.object({
  id: z.string(),
  request_prompt: z.string(),
  scene_type: z.string(),
  scene_setup: z.string(),
  source_image_url: nullableString,
  source_url: nullableString,
  created_at: datetime,
  task_count: z.number().int(),
});
export type ScenarioSummary = z.infer<typeof ScenarioSummarySchema>;

export const ScenarioListSchema = z.object({
  items: z.array(ScenarioSummarySchema),
  next_cursor: nullableString,
});
export type ScenarioList = z.infer<typeof ScenarioListSchema>;

export const JobStatusSchema = z.object({
  id: z.string(),
  status: z.enum(["pending", "running", "done", "failed"]),
  progress_stage: nullableString,
  scenario_id: nullableString,
  error_message: nullableString,
  created_at: nullableString,
  completed_at: nullableString,
});
export type JobStatus = z.infer<typeof JobStatusSchema>;

export const AnswerResultSchema = z.object({
  correct: z.boolean(),
  expected_answer: z.string(),
  acceptable_answers: z.array(z.string()),
  explanation: nullableString,
});
export type AnswerResult = z.infer<typeof AnswerResultSchema>;

export const HistoryItemSchema = z.object({
  attempt_id: z.number().int(),
  task_id: z.string(),
  scenario_id: z.string(),
  scenario_title: z.string(),
  task_prompt: z.string(),
  user_answer: z.string(),
  expected_answer: z.string(),
  is_correct: z.boolean(),
  attempted_at: datetime,
});
export type HistoryItem = z.infer<typeof HistoryItemSchema>;

export const HistoryListSchema = z.object({
  items: z.array(HistoryItemSchema),
  next_cursor: nullableString,
});
export type HistoryList = z.infer<typeof HistoryListSchema>;

export const GenerateResponseSchema = z.object({
  job_id: z.string(),
});
export type GenerateResponse = z.infer<typeof GenerateResponseSchema>;
