/**
 * Unit tests for `<TaskItem>`.
 *
 * Each test wires up MSW for the answer endpoint and exercises one
 * branch of the component's state machine.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import TaskItem from "../../src/components/TaskItem";
import type { TaskOut } from "../../src/api/schemas";
import { server } from "../mocks/server";

const task: TaskOut = {
  id: "task-1",
  position_index: 0,
  prompt: "What is the cheapest item?",
  answer_type: "exact",
  explanation: null,
};

function renderTask(props: Partial<{ onFirstResult: (correct: boolean) => void }> = {}) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <TaskItem
        scenarioId="scen-1"
        task={task}
        positionIndex={0}
        onFirstResult={props.onFirstResult ?? (() => {})}
      />
    </QueryClientProvider>,
  );
}

describe("TaskItem", () => {
  it("shows_input_initially", () => {
    renderTask();
    expect(screen.getByLabelText(/answer for task 1/i)).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("submits_answer", async () => {
    let captured: { url: string; body: unknown } | null = null;
    server.use(
      http.post(
        "/api/scenarios/:scenarioId/tasks/:taskId/answer",
        async ({ request }) => {
          captured = { url: request.url, body: await request.json() };
          return HttpResponse.json({
            correct: true,
            expected_answer: "油条",
            acceptable_answers: ["油条"],
            explanation: "yes",
          });
        },
      ),
    );

    renderTask();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/answer for task 1/i), "油条");
    await user.click(screen.getByRole("button", { name: /submit/i }));

    await waitFor(() => expect(captured).not.toBeNull());
    expect(captured!.url).toContain("/scenarios/scen-1/tasks/task-1/answer");
    expect(captured!.body).toEqual({ answer: "油条" });
  });

  it("shows_correct_state", async () => {
    server.use(
      http.post(
        "/api/scenarios/:scenarioId/tasks/:taskId/answer",
        () =>
          HttpResponse.json({
            correct: true,
            expected_answer: "油条",
            acceptable_answers: ["油条", "youtiao"],
            explanation: "youtiao is 2 yuan",
          }),
      ),
    );

    const onFirstResult = vi.fn();
    renderTask({ onFirstResult });
    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/answer for task 1/i), "油条");
    await user.click(screen.getByRole("button", { name: /submit/i }));

    await waitFor(() =>
      expect(screen.getByText(/correct/i)).toBeInTheDocument(),
    );
    expect(screen.getByText(/youtiao is 2 yuan/i)).toBeInTheDocument();
    expect(onFirstResult).toHaveBeenCalledWith(true);
  });

  it("shows_wrong_state", async () => {
    server.use(
      http.post(
        "/api/scenarios/:scenarioId/tasks/:taskId/answer",
        () =>
          HttpResponse.json({
            correct: false,
            expected_answer: "油条",
            acceptable_answers: ["油条"],
            explanation: "youtiao costs 2 yuan, not baozi",
          }),
      ),
    );

    const onFirstResult = vi.fn();
    renderTask({ onFirstResult });
    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/answer for task 1/i), "包子");
    await user.click(screen.getByRole("button", { name: /submit/i }));

    await waitFor(() =>
      expect(screen.getByText(/incorrect/i)).toBeInTheDocument(),
    );
    expect(screen.getByText(/expected:/i)).toBeInTheDocument();
    expect(screen.getByText(/油条/)).toBeInTheDocument();
    expect(screen.getByText(/youtiao costs 2 yuan/i)).toBeInTheDocument();
    expect(onFirstResult).toHaveBeenCalledWith(false);
  });

  it("try_again_clears_result", async () => {
    server.use(
      http.post(
        "/api/scenarios/:scenarioId/tasks/:taskId/answer",
        () =>
          HttpResponse.json({
            correct: false,
            expected_answer: "油条",
            acceptable_answers: ["油条"],
            explanation: "x",
          }),
      ),
    );

    renderTask();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/answer for task 1/i), "包子");
    await user.click(screen.getByRole("button", { name: /submit/i }));

    await waitFor(() =>
      expect(screen.getByText(/incorrect/i)).toBeInTheDocument(),
    );

    await user.click(screen.getByRole("button", { name: /try again/i }));

    expect(screen.queryByText(/incorrect/i)).not.toBeInTheDocument();
    expect(screen.getByLabelText(/answer for task 1/i)).toBeInTheDocument();
  });
});
