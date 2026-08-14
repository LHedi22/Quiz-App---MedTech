import path from "path";
import { randomUUID } from "crypto";
import { test, expect } from "@playwright/test";
import { queryRows, runSql } from "./db";

function uniqueEmail() {
  return `e2e-results-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`;
}

test("results dashboard reflects a seeded set of mixed-status submissions exactly", async ({
  page,
}) => {
  const email = uniqueEmail();
  await page.goto("/signup");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("correct-horse-battery-staple");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page).toHaveURL(/\/quizzes$/);

  const title = `Results dashboard test ${Date.now()}`;
  await page.getByRole("link", { name: "New quiz" }).click();
  await page.getByLabel("Quiz title").fill(title);
  await page.getByRole("button", { name: "Create quiz" }).click();
  await page
    .locator('input[type="file"]')
    .setInputFiles(path.join(__dirname, "fixtures", "valid.xlsx"));
  await page.getByRole("button", { name: "Upload" }).click();
  await expect(page.getByText(/questions parsed and saved/)).toBeVisible();
  await page.getByRole("button", { name: "Continue to generate versions" }).click();

  await expect(page).toHaveURL(/\/quizzes\/[0-9a-f-]+$/);
  const quizIdMatch = page.url().match(/\/quizzes\/([0-9a-f-]+)$/);
  const quizId = quizIdMatch![1];

  await page.getByLabel("Number of versions").fill("1");
  await page.getByRole("button", { name: "Generate versions" }).click();
  await expect(page.getByTestId("download-pdf")).toHaveCount(1);

  // Seed 3 submissions directly (no endpoint creates one except the real
  // OMR pipeline) with known, mixed statuses - the dashboard's DoD requires
  // exact counts/data, not just "list renders".
  const versionRows = await queryRows<{ id: string }>(
    `select id from versions where quiz_id = $1 limit 1`,
    [quizId],
  );
  const versionId = versionRows[0].id;

  const finalizedId = randomUUID();
  const needsReviewId = randomUUID();
  const pendingId = randomUUID();

  await runSql(
    `insert into submissions (id, version_id, student_id, total_score, status, created_at)
     values
       ($1, $4, 'student-finalized', 3.0, 'finalized', now() - interval '3 minutes'),
       ($2, $4, 'student-needs-review', null, 'needs_review', now() - interval '2 minutes'),
       ($3, $4, 'student-pending', null, 'pending', now() - interval '1 minute')`,
    [finalizedId, needsReviewId, pendingId, versionId],
  );

  await page.goto(`/results/${quizId}`);

  const rowsLocator = page.getByTestId("submission-row");
  await expect(rowsLocator).toHaveCount(3);

  // Scoped to the desktop table body: Subtask 7c.1 added a mobile card view
  // of the same data, so an unscoped page-wide text query now matches both
  // representations (one CSS-hidden at this viewport, but still in the DOM).
  const tableBody = page.getByTestId("submissions-table-body");
  await expect(tableBody.getByText("student-finalized")).toBeVisible();
  await expect(tableBody.getByText("student-needs-review")).toBeVisible();
  await expect(tableBody.getByText("student-pending")).toBeVisible();

  const finalizedRow = rowsLocator.filter({ has: page.getByText("student-finalized") });
  await expect(finalizedRow).toHaveAttribute("data-status", "finalized");
  await expect(finalizedRow).toContainText("3");
  const needsReviewRow = rowsLocator.filter({ has: page.getByText("student-needs-review") });
  await expect(needsReviewRow).toHaveAttribute("data-status", "needs_review");
  const pendingRow = rowsLocator.filter({ has: page.getByText("student-pending") });
  await expect(pendingRow).toHaveAttribute("data-status", "pending");

  await page.getByLabel("Status").selectOption("needs_review");
  await expect(rowsLocator).toHaveCount(1);
  await expect(tableBody.getByText("student-needs-review")).toBeVisible();
  await expect(tableBody.getByText("student-finalized")).not.toBeVisible();

  await page.getByLabel("Status").selectOption("finalized");
  await expect(rowsLocator).toHaveCount(1);
  await expect(rowsLocator.first()).toHaveAttribute("data-status", "finalized");

  await page.getByLabel("Status").selectOption("all");
  await expect(rowsLocator).toHaveCount(3);

  await runSql(`delete from submissions where id = any($1::uuid[])`, [
    [finalizedId, needsReviewId, pendingId],
  ]);
});
