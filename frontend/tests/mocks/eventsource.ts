/**
 * Mock `EventSource` for jsdom tests.
 *
 * jsdom ships no EventSource, so the real `useJobStream` would throw
 * "EventSource is not defined" the moment a test mounts a component
 * that uses it. We replace `globalThis.EventSource` with this class
 * in `tests/setup.ts` so every test sees the mock automatically.
 *
 * Tests drive the mock by calling `MockEventSource.last().emit(...)`
 * after the component has had a chance to subscribe.
 */

type Listener = (event: MessageEvent) => void;

export class MockEventSource {
  /** Every instance constructed during the current test, in order. */
  static instances: MockEventSource[] = [];

  url: string;
  closed = false;
  onerror: ((e: Event) => void) | null = null;
  private readonly listeners: Map<string, Listener[]> = new Map();

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: Listener): void {
    const list = this.listeners.get(type) ?? [];
    list.push(listener);
    this.listeners.set(type, list);
  }

  removeEventListener(type: string, listener: Listener): void {
    const list = this.listeners.get(type);
    if (!list) return;
    const idx = list.indexOf(listener);
    if (idx >= 0) list.splice(idx, 1);
  }

  close(): void {
    this.closed = true;
  }

  /**
   * Fire a typed event with a JSON-stringified payload, matching the
   * real EventSource contract for typed events emitted by sse-starlette.
   */
  emit(type: string, data: unknown): void {
    const event = new MessageEvent(type, {
      data: typeof data === "string" ? data : JSON.stringify(data),
    });
    const listeners = this.listeners.get(type);
    if (!listeners) return;
    // Copy the array so a listener that removes itself doesn't
    // perturb the iteration.
    [...listeners].forEach((l) => l(event));
  }

  /** Convenience: the most recently constructed instance. */
  static last(): MockEventSource | undefined {
    return MockEventSource.instances[MockEventSource.instances.length - 1];
  }

  /** Wipe instance history; called between tests. */
  static reset(): void {
    MockEventSource.instances = [];
  }
}
