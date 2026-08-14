import { test, expect } from "@playwright/test";

function uniqueEmail() {
  return `e2e-scan-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`;
}

async function signUp(page: import("@playwright/test").Page) {
  const email = uniqueEmail();
  await page.goto("/signup");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("correct-horse-battery-staple");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page).toHaveURL(/\/quizzes$/);
}

/** Stubs `navigator.mediaDevices.getUserMedia` before any page script runs,
 * so the capture screen's own init logic (web/app/(app)/scan/page.tsx)
 * observes a deterministic rejection regardless of whether this machine has
 * a real camera (Subtask 7c.2 DoD: "verified by a test that mocks
 * getUserMedia rejection"). */
async function stubGetUserMediaRejection(page: import("@playwright/test").Page, errorName: string) {
  await page.addInitScript((name) => {
    const reject = () => Promise.reject(new DOMException("stubbed for e2e", name));
    if (!navigator.mediaDevices) {
      Object.defineProperty(navigator, "mediaDevices", { value: {}, configurable: true });
    }
    navigator.mediaDevices.getUserMedia = reject;
  }, errorName);
}

test("camera permission denial shows a distinct, actionable error state and disables capture", async ({
  page,
}) => {
  await signUp(page);
  await stubGetUserMediaRejection(page, "NotAllowedError");

  await page.goto("/scan");

  await expect(page.getByTestId("camera-permission-denied")).toBeVisible();
  await expect(page.getByTestId("camera-permission-denied")).toContainText(/denied/i);
  await expect(page.getByTestId("camera-unavailable")).toHaveCount(0);
  await expect(page.getByTestId("capture-button")).toBeDisabled();
});

test("no camera available shows a distinct message from permission denial", async ({ page }) => {
  await signUp(page);
  await stubGetUserMediaRejection(page, "NotFoundError");

  await page.goto("/scan");

  await expect(page.getByTestId("camera-unavailable")).toBeVisible();
  await expect(page.getByTestId("camera-unavailable")).toContainText(/no camera available/i);
  await expect(page.getByTestId("camera-permission-denied")).toHaveCount(0);
  await expect(page.getByTestId("capture-button")).toBeDisabled();
});

test("the scan route is reachable from the nav and has no horizontal overflow at 375px", async ({
  page,
}) => {
  await signUp(page);
  await stubGetUserMediaRejection(page, "NotFoundError");

  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/quizzes");
  await page.getByTestId("mobile-nav-toggle").click();
  await page.getByTestId("mobile-nav-panel").getByRole("link", { name: "Scan" }).click();
  await expect(page).toHaveURL(/\/scan$/);
  await expect(page.getByTestId("camera-unavailable")).toBeVisible();

  const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
  expect(scrollWidth).toBeLessThanOrEqual(377);
});
