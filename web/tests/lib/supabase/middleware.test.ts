import { describe, expect, test } from "vitest";
import { isPublicRoute } from "@/lib/supabase/middleware";

describe("isPublicRoute", () => {
  test("exact public paths are public", () => {
    expect(isPublicRoute("/login")).toBe(true);
    expect(isPublicRoute("/signup")).toBe(true);
  });

  test("child routes under a public path are public", () => {
    expect(isPublicRoute("/login/reset")).toBe(true);
    expect(isPublicRoute("/signup/pending")).toBe(true);
  });

  test("a bare-prefix sibling is NOT public by accident", () => {
    expect(isPublicRoute("/login-help")).toBe(false);
    expect(isPublicRoute("/signups")).toBe(false);
    expect(isPublicRoute("/loginish")).toBe(false);
  });

  test("protected routes are not public", () => {
    expect(isPublicRoute("/quizzes")).toBe(false);
    expect(isPublicRoute("/")).toBe(false);
    expect(isPublicRoute("/submissions/abc")).toBe(false);
  });
});
