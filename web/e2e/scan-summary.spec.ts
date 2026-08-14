import path from "path";
import { randomUUID } from "crypto";
import { test, expect } from "@playwright/test";
import { queryRows, runSql } from "./db";

function uniqueEmail() {
  return `e2e-scan-summary-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`;
}

/** The scan capture screen can't be driven end-to-end here (no fake-camera-
 * device setup, same documented constraint as Subtask 7c.2/7c.3 - see
 * docs/PROGRESS.md's Phase 7c.3 entry), so the summary counting logic
 * itself is unit-tested against `useScanQueue` state directly
 * (web/tests/lib/scan/summary.test.ts). What *is* fully testable end-to-end
 * without a camera is the review-link's target page,
 * web/app/(app)/scan/review/page.tsx, which is driven purely by the `ids`
 * query string - this test seeds two needs_review submissions for the same
 * quiz and confirms the review page shows only the one whose id is passed,
 * proving the filtered view is exact, not "all needs_review for this quiz"
 * (Subtask 7c.4 DoD). */
test("the scan review page shows exactly the submissions named in its ids param, not every needs_review submission for the quiz", async ({
  page,
}) => {
  const email = uniqueEmail();
  await page.goto("/signup");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("correct-horse-battery-staple");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page).toHaveURL(/\/quizzes$/);

  await page.getByRole("link", { name: "New quiz" }).click();
  await page.getByLabel("Quiz title").fill(`Scan summary test ${Date.now()}`);
  await page.getByRole("button", { name: "Create quiz" }).click();
  await page
    .locator('input[type="file"]')
    .setInputFiles(path.join(__dirname, "fixtures", "valid.xlsx"));
  await page.getByRole("button", { name: "Upload" }).click();
  await expect(page.getByText(/questions parsed and saved/)).toBeVisible();
  await page.getByRole("button", { name: "Continue to generate versions" }).click();
  await expect(page).toHaveURL(/\/quizzes\/[0-9a-f-]+$/);
  const quizId = page.url().match(/\/quizzes\/([0-9a-f-]+)$/)![1];

  await page.getByLabel("Number of versions").fill("1");
  await page.getByRole("button", { name: "Generate versions" }).click();
  await expect(page.getByTestId("download-pdf")).toHaveCount(1);

  const versionRows = await queryRows<{ id: string }>(
    `select id from versions where quiz_id = $1 limit 1`,
    [quizId],
  );
  const versionId = versionRows[0].id;

  // Two needs_review submissions on the *same* quiz/version: one stands in
  // for "this scan session", the other for a pre-existing unrelated
  // submission that must NOT leak into the session-scoped review link.
  const inSessionId = randomUUID();
  const otherId = randomUUID();
  await runSql(
    `insert into submissions (id, version_id, student_id, total_score, status)
     values
       ($1, $3, 'in-session-student', null, 'needs_review'),
       ($2, $3, 'other-student', null, 'needs_review')`,
    [inSessionId, otherId, versionId],
  );

  await page.goto(`/scan/review?ids=${inSessionId}`);

  await expect(page.getByTestId("scan-review-item")).toHaveCount(1);
  await expect(page.getByTestId("scan-review-item")).toHaveAttribute("data-submission-id", inSessionId);
  await expect(page.getByText("in-session-student")).toBeVisible();
  await expect(page.getByText("other-student")).toHaveCount(0);

  await page.getByTestId("scan-review-item").click();
  await expect(page).toHaveURL(new RegExp(`/submissions/${inSessionId}$`));

  await runSql(`delete from submissions where id = any($1::uuid[])`, [[inSessionId, otherId]]);
});

test("the scan review page shows an empty state when no ids are provided", async ({ page }) => {
  const email = uniqueEmail();
  await page.goto("/signup");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("correct-horse-battery-staple");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page).toHaveURL(/\/quizzes$/);

  await page.goto("/scan/review");
  await expect(page.getByTestId("empty-state")).toBeVisible();
  await expect(page.getByTestId("scan-review-item")).toHaveCount(0);
});
