/**
 * Vitest global setup.
 *
 * - Extends `expect` with @testing-library/jest-dom matchers.
 * - Boots the MSW request mocker; tests register per-case handlers
 *   via `server.use(...)`. `onUnhandledRequest: "error"` catches
 *   silent fetch typos that would otherwise hit the real network.
 */

import "@testing-library/jest-dom/vitest";
import { afterAll, afterEach, beforeAll } from "vitest";

import { MockEventSource } from "./mocks/eventsource";
import { server } from "./mocks/server";

beforeAll(() => {
  server.listen({ onUnhandledRequest: "error" });
  // Inject the EventSource mock once. Per-test handlers can drive
  // it via `MockEventSource.last().emit(...)`.
  (globalThis as unknown as { EventSource: typeof MockEventSource }).EventSource =
    MockEventSource;

  // jsdom does not implement window.matchMedia. Provide a default
  // that reports desktop (>= 1024px) so the scenario page picks the
  // three-column layout by default. Per-test overrides in
  // ScenarioPage.test.tsx flip it to mobile for the stacking test.
  if (typeof window !== "undefined" && !("matchMedia" in window)) {
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      configurable: true,
      value: (query: string) => ({
        matches: query.includes("min-width") ? true : false,
        media: query,
        onchange: null,
        addEventListener: () => {},
        removeEventListener: () => {},
        addListener: () => {},
        removeListener: () => {},
        dispatchEvent: () => false,
      }),
    });
  }
});
afterEach(() => {
  server.resetHandlers();
  MockEventSource.reset();
});
afterAll(() => server.close());
