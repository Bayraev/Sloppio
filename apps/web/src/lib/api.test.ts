import { describe, expect, it, vi } from "vitest";
import { ApiRequestError, api, API_BASE } from "@/lib/api";

function mockFetch(status: number, body: unknown) {
  const fn = vi.fn().mockResolvedValue(
    new Response(typeof body === "string" ? body : JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    })
  );
  vi.stubGlobal("fetch", fn);
  return fn;
}

describe("api client", () => {
  it("builds the right URL for generations with filters", async () => {
    const fn = mockFetch(200, { generations: [] });
    await api.generations({ project_id: "p1", status: "failed" });
    const [url] = fn.mock.calls[0];
    expect(String(url)).toBe(`${API_BASE}/generations?project_id=p1&status=failed`);
  });

  it("parses detail objects into ApiRequestError with code", async () => {
    mockFetch(429, { detail: { code: "budget_exceeded", message: "Limit reached" } });
    const err = await api.createGeneration({}).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiRequestError);
    expect((err as ApiRequestError).code).toBe("budget_exceeded");
    expect((err as ApiRequestError).message).toBe("Limit reached");
  });

  it("handles plain-string error details", async () => {
    mockFetch(400, { detail: "Title is required" });
    const err = await api.createProject("", "").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiRequestError);
    expect((err as ApiRequestError).message).toBe("Title is required");
  });
});
