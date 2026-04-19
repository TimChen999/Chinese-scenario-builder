/**
 * Tests for the `apiFetch` wrapper.
 *
 * Covers the four named cases from DESIGN.md Step 8:
 *   - ok response is validated and returned
 *   - schema mismatch throws ApiError
 *   - non-2xx HTTP throws ApiError carrying the status
 *   - low-level network error throws ApiError
 */

import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { z } from "zod";

import { ApiError, apiFetch } from "../../src/api/client";
import { server } from "../mocks/server";

const TestSchema = z.object({ value: z.string() });

describe("apiFetch", () => {
  it("ok_response_validated", async () => {
    server.use(
      http.get("/api/test", () => HttpResponse.json({ value: "hi" })),
    );
    const result = await apiFetch("/test", TestSchema);
    expect(result).toEqual({ value: "hi" });
  });

  it("schema_mismatch_throws", async () => {
    server.use(
      http.get("/api/test", () => HttpResponse.json({ wrong: "field" })),
    );
    await expect(apiFetch("/test", TestSchema)).rejects.toBeInstanceOf(ApiError);
  });

  it("http_error_throws", async () => {
    server.use(
      http.get("/api/test", () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );
    await expect(apiFetch("/test", TestSchema)).rejects.toMatchObject({
      status: 500,
      message: "boom",
    });
  });

  it("network_error_throws", async () => {
    server.use(http.get("/api/test", () => HttpResponse.error()));
    await expect(apiFetch("/test", TestSchema)).rejects.toBeInstanceOf(ApiError);
  });
});
