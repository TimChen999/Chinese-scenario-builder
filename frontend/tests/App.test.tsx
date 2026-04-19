/**
 * App-level routing tests.
 *
 * Covers the three named cases from DESIGN.md Step 8:
 *   - renders the library at "/"
 *   - navigates between pages without a full reload
 *   - shows a 404 fallback for unknown routes
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router-dom";

import App from "../src/App";
import { server } from "./mocks/server";

/**
 * Build the same provider tree the real app uses, but with a
 * MemoryRouter so we can drive the route from the test.
 */
function renderApp(initialEntries: string[] = ["/"]) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={initialEntries}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("App", () => {
  beforeEach(() => {
    // The library page kicks off a /scenarios fetch as soon as it
    // mounts; stub the response so MSW does not log an unhandled-
    // request warning. Tests here only inspect static UI, so the
    // returned payload does not matter.
    server.use(
      http.get("/api/scenarios", () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
    );
  });

  it("renders_library_at_root", () => {
    renderApp(["/"]);
    expect(
      screen.getByRole("heading", { name: /library/i, level: 1 }),
    ).toBeInTheDocument();
  });

  it("navigates_between_pages", async () => {
    const user = userEvent.setup();
    renderApp(["/"]);

    await user.click(screen.getByRole("link", { name: /generate/i }));

    expect(
      screen.getByRole("heading", { name: /generate a scenario/i, level: 1 }),
    ).toBeInTheDocument();
  });

  it("404_route", () => {
    renderApp(["/nonsense"]);
    expect(screen.getByText(/not found/i)).toBeInTheDocument();
  });
});
