import { test, expect } from "@playwright/test";

function uniqueEmail() {
  return `e2e-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`;
}

test("sign up, log in, and log out all work against the real Supabase project", async ({
  page,
}) => {
  const email = uniqueEmail();
  const password = "correct-horse-battery-staple";

  await page.goto("/signup");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign up" }).click();

  await expect(page).toHaveURL(/\/quizzes$/);
  await expect(page.getByText(email)).toBeVisible();

  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login$/);

  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Log in" }).click();

  await expect(page).toHaveURL(/\/quizzes$/);
  await expect(page.getByText(email)).toBeVisible();
});

test("a protected route with no session cookie is redirected server-side", async ({
  browser,
}) => {
  // Fresh, cookie-less context - simulates hitting the route directly, not
  // just relying on a client-side guard that would only run after hydration.
  const context = await browser.newContext();
  const page = await context.newPage();

  const response = await page.goto("/quizzes");

  await expect(page).toHaveURL(/\/login$/);
  // The redirect must have happened before the client ever painted
  // /quizzes - assert on the final response, not just the eventual URL.
  expect(response?.url()).toMatch(/\/login$/);

  await context.close();
});
