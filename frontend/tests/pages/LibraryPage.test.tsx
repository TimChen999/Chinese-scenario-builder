/**
 * Integration tests for `<LibraryPage>`.
 *
 * Each test wires up a fresh QueryClient + MemoryRouter and registers
 * MSW handlers for `/api/scenarios`. The "loading skeleton" test
 * registers a never-resolving handler so the pending state is
 * stable when the assertion runs.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router-dom";

import LibraryPage from "../../src/pages/LibraryPage";
import { server } from "../mocks/server";

function renderLibrary() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <LibraryPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const sampleScenarios = [
  {
    id: "id-1",
    request_prompt: "ordering breakfast in Beijing",
    scene_type: "menu",
    scene_setup: "你刚走进早餐店。",
    source_image_url: "/api/scenarios/id-1/image",
    source_url: null,
    created_at: new Date().toISOString(),
    task_count: 3,
  },
  {
    id: "id-2",
    request_prompt: "navigating Shanghai metro",
    scene_type: "sign",
    scene_setup: "你刚到地铁站。",
    source_image_url: null,
    source_url: null,
    created_at: new Date().toISOString(),
    task_count: 2,
  },
  {
    id: "id-3",
    request_prompt: "hotpot in Chongqing",
    scene_type: "menu",
    scene_setup: "你刚走进火锅店。",
    source_image_url: "/api/scenarios/id-3/image",
    source_url: null,
    created_at: new Date().toISOString(),
    task_count: 5,
  },
];

describe("LibraryPage", () => {
  beforeEach(() => {
    // Default: empty list. Per-test handlers override below.
    server.use(
      http.get("/api/scenarios", () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
    );
  });

  it("shows_loading_skeleton", () => {
    server.use(
      http.get(
        "/api/scenarios",
        // Hangs forever; the test only asserts the synchronous
        // pending state, so this never has to resolve.
        () => new Promise<Response>(() => {}),
      ),
    );
    renderLibrary();
    expect(screen.getByTestId("library-skeleton")).toBeInTheDocument();
  });

  it("renders_scenarios", async () => {
    server.use(
      http.get("/api/scenarios", () =>
        HttpResponse.json({ items: sampleScenarios, next_cursor: null }),
      ),
    );
    renderLibrary();
    await waitFor(() =>
      expect(
        screen.getByText("ordering breakfast in Beijing"),
      ).toBeInTheDocument(),
    );
    expect(screen.getByText("navigating Shanghai metro")).toBeInTheDocument();
    expect(screen.getByText("hotpot in Chongqing")).toBeInTheDocument();
  });

  it("shows_empty_state", async () => {
    renderLibrary();
    await waitFor(() =>
      expect(screen.getByText(/no scenarios yet/i)).toBeInTheDocument(),
    );
    expect(
      screen.getByRole("link", { name: /generate your first one/i }),
    ).toBeInTheDocument();
  });

  it("filter_by_scene_type", async () => {
    const requestedUrls: string[] = [];
    server.use(
      http.get("/api/scenarios", ({ request }) => {
        requestedUrls.push(request.url);
        return HttpResponse.json({ items: [], next_cursor: null });
      }),
    );

    renderLibrary();
    // Wait for the initial fetch.
    await waitFor(() =>
      expect(requestedUrls.some((u) => u.includes("/api/scenarios"))).toBe(true),
    );

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Menu", pressed: false }));

    await waitFor(() =>
      expect(requestedUrls.some((u) => u.includes("scene_type=menu"))).toBe(true),
    );
  });

  it("error_state", async () => {
    server.use(
      http.get("/api/scenarios", () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );
    renderLibrary();
    await waitFor(() =>
      expect(screen.getByRole("alert")).toBeInTheDocument(),
    );
    expect(
      screen.getByRole("button", { name: /retry/i }),
    ).toBeInTheDocument();
  });
});
