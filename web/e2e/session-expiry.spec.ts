import { test, expect } from "@playwright/test";

function uniqueEmail() {
  return `e2e-expiry-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`;
}

// Subtask 7b.2: an expired session and a cleared/invalidated one hit the
// exact same code path in lib/supabase/middleware.ts's updateSession()
// (supabase.auth.getUser() fails either way) - clearing cookies mid-session
// is a faithful, reproducible stand-in for waiting out a real token expiry.
test("a session invalidated mid-use redirects to login cleanly, with no leaked protected content", async ({
  page,
  context,
}) => {
  const email = uniqueEmail();
  await page.goto("/signup");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("correct-horse-battery-staple");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page).toHaveURL(/\/quizzes$/);
  await expect(page.getByText(email)).toBeVisible();

  await context.clearCookies();

  await page.goto("/quizzes");

  // Clean redirect, not an infinite loop back through a protected route.
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("heading", { name: "Log in" })).toBeVisible();
  // No stale protected content ever painted before the redirect.
  await expect(page.getByText(email)).not.toBeVisible();

  // Navigating again confirms it's a stable redirected state, not a loop
  // that happens to have landed on /login once.
  await page.goto("/results");
  await expect(page).toHaveURL(/\/login$/);
});

// web-app audit B6: the case above is a *navigation* (proxy.ts redirects
// cleanly). This covers an in-page fetch failing 401 while the professor
// sits on a client-rendered page - it must redirect to /login, not leave a
// dead-end "Could not load…" message.
test("a 401 from an in-page API fetch redirects to login instead of dead-ending", async ({
  page,
}) => {
  const email = uniqueEmail();
  await page.goto("/signup");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("correct-horse-battery-staple");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page).toHaveURL(/\/quizzes$/);

  // The session cookie is still valid (proxy.ts lets the page render), but
  // the backend rejects the bearer token on the in-page fetch.
  await page.route("**/quizzes/*/submissions*", (route) =>
    route.fulfill({ status: 401, contentType: "application/json", body: "{}" }),
  );

  await page.goto("/results/00000000-0000-0000-0000-000000000000");

  // The professor is navigated away from the dead page (to /login; the
  // still-valid cookie may then bounce them on to /quizzes via proxy.ts) -
  // the point is they are NOT stranded on /results with a "Could not load…"
  // message and no way forward.
  await expect(page).not.toHaveURL(/\/results\//);
  await expect(page.getByText(/could not load/i)).not.toBeVisible();
});
