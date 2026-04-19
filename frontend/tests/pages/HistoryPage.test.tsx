/**
 * Integration tests for `<HistoryPage>`.
 *
 * Covers the named cases from DESIGN.md Step 12:
 *   - loading skeleton
 *   - renders attempts
 *   - filter switches refetch with incorrect_only=true
 *   - empty state CTA
 *   - row links to scenario
 *   - pagination "Load more" fetches next page
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router-dom";

import HistoryPage from "../../src/pages/HistoryPage";
import { server } from "../mocks/server";

function renderHistory() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <HistoryPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const baseAttempt = {
  attempt_id: 1,
  task_id: "task-1",
  scenario_id: "scen-1",
  scenario_title: "ordering breakfast",
  task_prompt: "What is the cheapest item?",
  user_answer: "包子",
  expected_answer: "油条",
  is_correct: false,
  attempted_at: new Date().toISOString(),
};

function buildAttempts(n: number) {
  return Array.from({ length: n }).map((_, i) => ({
    ...baseAttempt,
    attempt_id: i + 1,
    user_answer: `answer-${i + 1}`,
    is_correct: i % 2 === 0,
  }));
}

describe("HistoryPage", () => {
  beforeEach(() => {
    server.use(
      http.get("/api/history", () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
    );
  });

  it("loading_state", () => {
    server.use(
      http.get("/api/history", () => new Promise<Response>(() => {})),
    );
    renderHistory();
    expect(screen.getByTestId("history-skeleton")).toBeInTheDocument();
  });

  it("renders_attempts", async () => {
    server.use(
      http.get("/api/history", () =>
        HttpResponse.json({ items: buildAttempts(5), next_cursor: null }),
      ),
    );
    renderHistory();
    // Wait for real rows to appear (skeleton has 5 placeholder
    // <li>s with no text, so we anchor on the user-answer string
    // to know data is in the DOM).
    await waitFor(() =>
      expect(screen.getByText(/answer-1/)).toBeInTheDocument(),
    );
    expect(screen.getByText(/answer-5/)).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(5);
  });

  it("filter_incorrect", async () => {
    const requests: string[] = [];
    server.use(
      http.get("/api/history", ({ request }) => {
        requests.push(request.url);
        return HttpResponse.json({ items: [], next_cursor: null });
      }),
    );
    renderHistory();
    await waitFor(() =>
      expect(requests.some((u) => u.includes("/api/history"))).toBe(true),
    );

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Incorrect" }));

    await waitFor(() =>
      expect(requests.some((u) => u.includes("incorrect_only=true"))).toBe(true),
    );
  });

  it("empty_state", async () => {
    renderHistory();
    await waitFor(() =>
      expect(
        screen.getByText(/answer some tasks to see your history/i),
      ).toBeInTheDocument(),
    );
    expect(
      screen.getByRole("link", { name: /generate a scenario/i }),
    ).toBeInTheDocument();
  });

  it("row_links_to_scenario", async () => {
    server.use(
      http.get("/api/history", () =>
        HttpResponse.json({ items: [baseAttempt], next_cursor: null }),
      ),
    );
    renderHistory();
    const link = await screen.findByRole("link", { name: /review scenario/i });
    expect(link).toHaveAttribute("href", "/scenarios/scen-1");
  });

  it("pagination_loads_more", async () => {
    let requestCount = 0;
    server.use(
      http.get("/api/history", ({ request }) => {
        requestCount++;
        const url = new URL(request.url);
        const cursor = url.searchParams.get("cursor");
        if (!cursor) {
          return HttpResponse.json({
            items: buildAttempts(3),
            next_cursor: "cursor-1",
          });
        }
        // Second page -- different attempt ids so the test can spot
        // the new rows after "Load more".
        return HttpResponse.json({
          items: buildAttempts(2).map((a) => ({
            ...a,
            attempt_id: a.attempt_id + 100,
            user_answer: `page2-${a.attempt_id}`,
          })),
          next_cursor: null,
        });
      }),
    );

    renderHistory();
    // Wait for the first page's rows to appear (anchor on text so
    // we don't race against the skeleton's listitems).
    await waitFor(() =>
      expect(screen.getByText(/answer-1/)).toBeInTheDocument(),
    );
    expect(requestCount).toBe(1);
    expect(screen.getAllByRole("listitem")).toHaveLength(3);

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /load more/i }));

    await waitFor(() =>
      expect(screen.getByText(/page2-1/)).toBeInTheDocument(),
    );
    expect(requestCount).toBe(2);
    expect(screen.getAllByRole("listitem")).toHaveLength(5);
  });

  it("renders_correct_and_incorrect_badges", async () => {
    server.use(
      http.get("/api/history", () =>
        HttpResponse.json({
          items: [
            { ...baseAttempt, attempt_id: 1, is_correct: true },
            { ...baseAttempt, attempt_id: 2, is_correct: false },
          ],
          next_cursor: null,
        }),
      ),
    );
    renderHistory();
    // Wait for real rows; the skeleton listitems carry no aria-label.
    await waitFor(() =>
      expect(screen.getAllByLabelText(/correct/i).length).toBeGreaterThan(0),
    );
    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(within(items[0]).getByLabelText("correct")).toBeInTheDocument();
    expect(within(items[1]).getByLabelText("incorrect")).toBeInTheDocument();
  });
});
