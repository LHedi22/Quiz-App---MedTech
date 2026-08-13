import { test, expect } from "@playwright/test";
import { scanVersionQrUnreadable, seedQuiz } from "./pythonRegression";

// Subtask 7b.5 (QR-unreadable case): /scan never creates a submission row
// when the QR code can't be decoded (backend/app/routers/scan.py raises a
// distinct qr_unreadable 422 before any DB write) - so there is nothing for
// the web app to "surface" for this case beyond confirming that no phantom
// or mis-attributed row appears anywhere in its UI. Web itself has no
// scan-initiating UI (mobile-only per CLAUDE.md), so a distinct
// QR-failure *signal* is necessarily mobile's own concern (Phase 8.4's
// batch-summary screen), not something a Next.js screen could show even in
// principle - this test verifies the web-relevant half of that fact.
test("an unreadable QR scan creates no submission, so nothing appears in the dashboard", async ({
  page,
}) => {
  const seeded = seedQuiz(`QR unreadable regression ${Date.now()}`);
  const result = scanVersionQrUnreadable(seeded.version_id, seeded.token, "qr-fail-student");

  expect(result.status_code).toBe(422);
  expect((result.body as { detail?: { error?: string } }).detail?.error).toBe("qr_unreadable");

  await page.goto("/login");
  await page.getByLabel("Email").fill(seeded.email);
  await page.getByLabel("Password").fill(seeded.password);
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page).toHaveURL(/\/quizzes$/);

  await page.goto(`/results/${seeded.quiz_id}`);
  await expect(page.getByTestId("empty-state")).toBeVisible();
  await expect(page.getByTestId("submission-row")).toHaveCount(0);
  await expect(page.getByText("qr-fail-student")).not.toBeVisible();
});
