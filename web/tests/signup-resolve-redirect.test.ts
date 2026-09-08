import { describe, expect, test } from "vitest";
import { resolveSignupRedirect } from "@/app/signup/resolveRedirect";

describe("resolveSignupRedirect (web-app audit B7)", () => {
  test("a session (email confirmation off) -> /quizzes", () => {
    expect(
      resolveSignupRedirect({
        data: { session: { access_token: "t" }, user: { identities: [{ id: "i" }] } },
        error: null,
      }),
    ).toBe("/quizzes");
  });

  test("no session + a real new user (confirmation on) -> pending state, NOT /quizzes", () => {
    expect(
      resolveSignupRedirect({
        data: { session: null, user: { identities: [{ id: "i" }] } },
        error: null,
      }),
    ).toBe("/signup?pending=1");
  });

  test("no session + user with no identities -> explicit 'already exists' message", () => {
    const url = resolveSignupRedirect({
      data: { session: null, user: { identities: [] } },
      error: null,
    });
    expect(url).toMatch(/^\/signup\?error=/);
    expect(decodeURIComponent(url)).toMatch(/already exists/i);
  });

  test("a signUp error is passed through", () => {
    expect(
      resolveSignupRedirect({ data: { session: null, user: null }, error: { message: "weak password" } }),
    ).toBe("/signup?error=weak%20password");
  });
});
