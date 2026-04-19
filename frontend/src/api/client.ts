/**
 * Tiny `fetch` wrapper that:
 *   1. Prefixes every path with `/api` (Vite proxy strips it before
 *      forwarding to the backend on :8000).
 *   2. Validates the response body against a Zod schema -- callers
 *      get a typed result and we catch contract drift loudly.
 *   3. Throws a single `ApiError` for every failure so React Query's
 *      retry / error handling has one shape to deal with.
 *
 * See DESIGN.md Section 8 ("frontend") + Section 11 ("Testing").
 */

import type { z } from "zod";

const API_BASE = "/api";

/**
 * Single error type thrown by `apiFetch`. ``status`` is undefined
 * when the request never reached the server (network error, etc.).
 */
export class ApiError extends Error {
  status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/**
 * Perform a JSON HTTP request against the backend and return the
 * parsed body validated by ``schema``.
 *
 * @param path   Path under ``/api`` (with leading slash, e.g. ``/scenarios``).
 * @param schema Zod schema describing the expected response shape.
 * @param init   Optional ``RequestInit``; ``Content-Type: application/json``
 *               is set by default and merged with caller-supplied headers.
 * @throws ApiError on network failure, non-2xx status, invalid JSON, or
 *         schema validation failure.
 */
export async function apiFetch<T>(
  path: string,
  schema: z.ZodSchema<T>,
  init?: RequestInit,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        ...init?.headers,
      },
    });
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    throw new ApiError(`Network error: ${detail}`);
  }

  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`;
    try {
      const body = await response.json();
      if (body && typeof body === "object" && "detail" in body) {
        detail = String((body as { detail: unknown }).detail);
      }
    } catch {
      /* response body might not be JSON; fall through to default detail */
    }
    throw new ApiError(detail, response.status);
  }

  let body: unknown;
  try {
    body = await response.json();
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    throw new ApiError(`Invalid JSON response: ${detail}`);
  }

  const parsed = schema.safeParse(body);
  if (!parsed.success) {
    throw new ApiError(
      `Response did not match expected schema: ${parsed.error.message}`,
    );
  }
  return parsed.data;
}

/**
 * Helper for building the SSE URL for a job. Returned as a string
 * (not a Response) because EventSource constructs its own connection.
 */
export function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}
