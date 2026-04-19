/**
 * Integration tests for `<ScenarioPage>`.
 *
 * Covers the named cases from DESIGN.md Step 11:
 *   - renders the full scenario from the API
 *   - shows a loading skeleton while pending
 *   - shows a "not found" UI on 404
 *   - increments the score after a correct first attempt
 *   - switches to the stacked layout below the lg breakpoint
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import ScenarioPage from "../../src/pages/ScenarioPage";
import { server } from "../mocks/server";

function renderScenario(scenarioId = "abc-123") {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/scenarios/${scenarioId}`]}>
        <Routes>
          <Route path="/scenarios/:id" element={<ScenarioPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const fullScenario = {
  id: "abc-123",
  request_prompt: "ordering breakfast in Beijing",
  scene_type: "menu",
  scene_setup: "你刚走进早餐店,服务员递给你菜单。",
  raw_content: "豆浆 3元\n油条 2元\n包子(肉) 4元",
  source_image_url: "/api/scenarios/abc-123/image",
  source_url: null,
  created_at: new Date().toISOString(),
  tasks: [
    {
      id: "task-1",
      position_index: 0,
      prompt: "What is the cheapest item?",
      answer_type: "exact",
      explanation: null,
    },
    {
      id: "task-2",
      position_index: 1,
      prompt: "How much is 豆浆?",
      answer_type: "numeric",
      explanation: null,
    },
    {
      id: "task-3",
      position_index: 2,
      prompt: "Which item costs 4 元?",
      answer_type: "exact",
      explanation: null,
    },
  ],
};

describe("ScenarioPage", () => {
  it("renders_full_scenario", async () => {
    server.use(
      http.get("/api/scenarios/abc-123", () => HttpResponse.json(fullScenario)),
    );

    renderScenario();

    await waitFor(() =>
      expect(screen.getByText(fullScenario.scene_setup)).toBeInTheDocument(),
    );
    // Image, raw_content, and all 3 task prompts visible.
    expect(screen.getByRole("img")).toHaveAttribute(
      "src",
      "/api/scenarios/abc-123/image",
    );
    // RawContent: query by data attribute and compare textContent
    // directly so newlines survive (getByText collapses whitespace).
    const rawNode = document.querySelector(
      "[data-scenario-content='raw']",
    ) as HTMLElement | null;
    expect(rawNode).not.toBeNull();
    expect(rawNode!.textContent).toBe("豆浆 3元\n油条 2元\n包子(肉) 4元");
    expect(
      screen.getByText("What is the cheapest item?"),
    ).toBeInTheDocument();
    expect(screen.getByText("How much is 豆浆?")).toBeInTheDocument();
    expect(screen.getByText("Which item costs 4 元?")).toBeInTheDocument();
  });

  it("loading_state", () => {
    server.use(
      http.get("/api/scenarios/abc-123", () => new Promise<Response>(() => {})),
    );
    renderScenario();
    expect(screen.getByTestId("scenario-skeleton")).toBeInTheDocument();
  });

  it("not_found", async () => {
    server.use(
      http.get("/api/scenarios/abc-123", () =>
        HttpResponse.json({ detail: "scenario not found" }, { status: 404 }),
      ),
    );
    renderScenario();
    await waitFor(() =>
      expect(screen.getByText(/scenario not found/i)).toBeInTheDocument(),
    );
  });

  it("score_updates_on_correct", async () => {
    server.use(
      http.get("/api/scenarios/abc-123", () => HttpResponse.json(fullScenario)),
      http.post(
        "/api/scenarios/abc-123/tasks/task-1/answer",
        () =>
          HttpResponse.json({
            correct: true,
            expected_answer: "油条",
            acceptable_answers: ["油条"],
            explanation: "y",
          }),
      ),
    );

    renderScenario();
    const user = userEvent.setup();
    await waitFor(() =>
      expect(screen.getByText(/score: 0\/3/i)).toBeInTheDocument(),
    );

    await user.type(screen.getByLabelText(/answer for task 1/i), "油条");
    await user.click(screen.getAllByRole("button", { name: /submit/i })[0]);

    await waitFor(() =>
      expect(screen.getByText(/score: 1\/3/i)).toBeInTheDocument(),
    );
  });

  describe("stacks_on_small_viewport", () => {
    let originalMatchMedia: typeof window.matchMedia;

    beforeEach(() => {
      originalMatchMedia = window.matchMedia;
      // Force matchMedia to report mobile (no min-width:1024px match).
      Object.defineProperty(window, "matchMedia", {
        writable: true,
        configurable: true,
        value: (query: string) => ({
          matches: false,
          media: query,
          onchange: null,
          addEventListener: () => {},
          removeEventListener: () => {},
          addListener: () => {},
          removeListener: () => {},
          dispatchEvent: () => false,
        }),
      });
    });

    afterEach(() => {
      Object.defineProperty(window, "matchMedia", {
        writable: true,
        configurable: true,
        value: originalMatchMedia,
      });
    });

    it("layout_stacked_below_lg", async () => {
      server.use(
        http.get("/api/scenarios/abc-123", () =>
          HttpResponse.json(fullScenario),
        ),
      );

      renderScenario();
      await waitFor(() =>
        expect(screen.getByTestId("scenario-grid")).toBeInTheDocument(),
      );
      const grid = screen.getByTestId("scenario-grid");
      expect(grid).toHaveAttribute("data-layout", "stacked");
      expect(grid.className).toContain("flex");
      expect(grid.className).not.toContain("grid-cols-3");
    });
  });
});
