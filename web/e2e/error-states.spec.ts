import { test, expect } from "@playwright/test";

function uniqueEmail() {
  return `e2e-errstate-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`;
}

// web-app audit B8: an unknown route renders the friendly 404 page, not
// Next's default. (The server-component data-failure path - error.tsx /
// inline load errors - is covered in tests/error-states.test.tsx, since
// those fetches run on the Next server and can't be intercepted from the
// browser.)
test("an unknown route renders the 404 page", async ({ page }) => {
  await page.goto("/signup");
  await page.getByLabel("Email").fill(uniqueEmail());
  await page.getByLabel("Password").fill("correct-horse-battery-staple");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page).toHaveURL(/\/quizzes$/);

  await page.goto("/this-route-does-not-exist");
  await expect(page.getByTestId("not-found")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Page not found" })).toBeVisible();
});
