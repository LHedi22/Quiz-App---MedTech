import { afterEach, describe, expect, test, vi } from "vitest";
import { ApiError, ApiTimeoutError, listQuizzes } from "@/lib/api/client";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("api client request()", () => {
  test("attaches an abort signal to every request", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify([]), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await listQuizzes("token");

    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(init.signal).toBeInstanceOf(AbortSignal);
  });

  test("maps a fetch TimeoutError to ApiTimeoutError (still an ApiError)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new DOMException("The operation timed out.", "TimeoutError")),
    );

    const err = await listQuizzes("token").catch((e) => e);
    expect(err).toBeInstanceOf(ApiTimeoutError);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiTimeoutError).status).toBe(0);
    expect((err as Error).message).toMatch(/timed out/i);
  });

  test("lets a non-timeout fetch rejection propagate unchanged", async () => {
    const networkError = new TypeError("Failed to fetch");
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(networkError));

    const err = await listQuizzes("token").catch((e) => e);
    expect(err).toBe(networkError);
  });
});
