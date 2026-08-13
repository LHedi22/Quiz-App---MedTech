import { test, expect } from "@playwright/test";

test("default page boots", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveTitle(/.+/);
});
