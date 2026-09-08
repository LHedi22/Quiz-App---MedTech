import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { useReachability } from "@/lib/scan/useReachability";

function setNavigatorOnLine(value: boolean) {
  Object.defineProperty(navigator, "onLine", { value, configurable: true });
}

describe("useReachability", () => {
  const originalOnLine = navigator.onLine;

  beforeEach(() => {
    setNavigatorOnLine(true);
  });

  afterEach(() => {
    setNavigatorOnLine(originalOnLine);
    vi.unstubAllGlobals();
  });

  test("a successful ping reports online", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 200 })));
    const { result } = renderHook(() => useReachability("/health", 999999));
    await waitFor(() => expect(result.current).toBe(true));
  });

  test("navigator.onLine = false plus an 'offline' event reports offline without waiting for a ping", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 200 })));
    const { result } = renderHook(() => useReachability("/health", 999999));
    await waitFor(() => expect(result.current).toBe(true));

    setNavigatorOnLine(false);
    window.dispatchEvent(new Event("offline"));

    await waitFor(() => expect(result.current).toBe(false));
  });

  test("a fetch failure (backend unreachable even though the network interface is up) reports offline", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const { result } = renderHook(() => useReachability("/health", 999999));
    await waitFor(() => expect(result.current).toBe(false));
  });

  test("a reachable-but-erroring backend (503) reports offline, not online", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 503 })));
    const { result } = renderHook(() => useReachability("/health", 999999));
    await waitFor(() => expect(result.current).toBe(false));
  });

  test("a 4xx from the ping still counts as online (the backend answered)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 404 })));
    const { result } = renderHook(() => useReachability("/health", 999999));
    await waitFor(() => expect(result.current).toBe(true));
  });
});
