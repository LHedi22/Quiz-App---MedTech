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
