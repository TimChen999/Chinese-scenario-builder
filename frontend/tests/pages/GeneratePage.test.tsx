/**
 * Integration tests for `<GeneratePage>`.
 *
 * The form -> POST -> SSE -> redirect pipeline is exercised end to
 * end, with the EventSource mocked via `MockEventSource` and the
 * POST mocked via MSW.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import GeneratePage from "../../src/pages/GeneratePage";
import { MockEventSource } from "../mocks/eventsource";
import { server } from "../mocks/server";

/**
 * Renders the GeneratePage inside a Router with a sibling
 * LocationDisplay so tests can observe URL changes after navigation.
 */
function renderGenerate() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/generate"]}>
        <Routes>
          <Route path="/generate" element={<GeneratePage />} />
          <Route
            path="/scenarios/:id"
            element={<div data-testid="scenario-placeholder">scenario page</div>}
          />
        </Routes>
        <LocationDisplay />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function LocationDisplay() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
}

async function waitForEventSource(): Promise<MockEventSource> {
  await waitFor(() => expect(MockEventSource.last()).toBeDefined(), {
    timeout: 2000,
  });
  return MockEventSource.last()!;
}

describe("GeneratePage", () => {
  it("submits_form", async () => {
    let captured: unknown = null;
    server.use(
      http.post("/api/scenarios/generate", async ({ request }) => {
        captured = await request.json();
        return HttpResponse.json({ job_id: "job-1" });
      }),
    );

    renderGenerate();
    const user = userEvent.setup();

    await user.type(
      screen.getByLabelText(/what do you want to read/i),
      "ordering breakfast",
    );
    await user.selectOptions(screen.getByLabelText(/scene type/i), "menu");
    await user.type(screen.getByLabelText(/region/i), "Beijing");
    await user.click(screen.getByRole("button", { name: /^generate$/i }));

    await waitFor(() =>
      expect(captured).toEqual(
        expect.objectContaining({
          prompt: "ordering breakfast",
          scene_hint: "menu",
          region: "Beijing",
        }),
      ),
    );
  });

  it("shows_progress_after_submit", async () => {
    server.use(
      http.post("/api/scenarios/generate", () =>
        HttpResponse.json({ job_id: "job-1" }),
      ),
    );

    renderGenerate();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/what do you want to read/i), "test");
    await user.click(screen.getByRole("button", { name: /^generate$/i }));

    const es = await waitForEventSource();
    await act(async () => {
      es.emit("progress", { stage: "ocr_in_progress" });
    });

    expect(screen.getByText(/reading text from images/i)).toBeInTheDocument();
    expect(
      screen
        .getByText("Reading text from images")
        .closest("li"),
    ).toHaveAttribute("data-stage-state", "current");
  });

  it("redirects_on_done", async () => {
    server.use(
      http.post("/api/scenarios/generate", () =>
        HttpResponse.json({ job_id: "job-1" }),
      ),
    );

    renderGenerate();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/what do you want to read/i), "test");
    await user.click(screen.getByRole("button", { name: /^generate$/i }));

    const es = await waitForEventSource();
    await act(async () => {
      es.emit("done", { scenario_id: "abc-123" });
    });

    await waitFor(() =>
      expect(screen.getByTestId("location").textContent).toBe(
        "/scenarios/abc-123",
      ),
    );
    expect(screen.getByTestId("scenario-placeholder")).toBeInTheDocument();
  });

  it("shows_error_on_failure", async () => {
    server.use(
      http.post("/api/scenarios/generate", () =>
        HttpResponse.json({ job_id: "job-1" }),
      ),
    );

    renderGenerate();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/what do you want to read/i), "test");
    await user.click(screen.getByRole("button", { name: /^generate$/i }));

    const es = await waitForEventSource();
    await act(async () => {
      es.emit("failed", { error_message: "no usable images" });
    });

    await waitFor(() =>
      expect(screen.getByRole("alert")).toBeInTheDocument(),
    );
    expect(screen.getByText(/no usable images/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /try again/i }),
    ).toBeInTheDocument();
  });

  it("validates_empty_prompt", async () => {
    let postCalled = false;
    server.use(
      http.post("/api/scenarios/generate", () => {
        postCalled = true;
        return HttpResponse.json({ job_id: "x" });
      }),
    );

    renderGenerate();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /^generate$/i }));

    expect(screen.getByText(/please enter a prompt/i)).toBeInTheDocument();
    expect(postCalled).toBe(false);
  });
});
