import { afterEach, describe, expect, test, vi } from "vitest";
import { AuthExpiredError, handledAsAuthExpiry } from "@/lib/authError";

describe("handledAsAuthExpiry", () => {
  const original = window.location;

  afterEach(() => {
    Object.defineProperty(window, "location", { configurable: true, value: original });
  });

  test("redirects to /login and returns true for an AuthExpiredError", () => {
    const assign = vi.fn();
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { ...original, assign },
    });

    expect(handledAsAuthExpiry(new AuthExpiredError())).toBe(true);
    expect(assign).toHaveBeenCalledWith("/login");
  });

  test("returns false and does not redirect for any other error", () => {
    const assign = vi.fn();
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { ...original, assign },
    });

    expect(handledAsAuthExpiry(new Error("network"))).toBe(false);
    expect(handledAsAuthExpiry("nope")).toBe(false);
    expect(assign).not.toHaveBeenCalled();
  });
});
