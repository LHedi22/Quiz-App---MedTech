import path from "path";
import { randomUUID } from "crypto";
import { test, expect } from "@playwright/test";
import { queryRows, runSql } from "./db";

function uniqueEmail() {
  return `e2e-review-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`;
}

test("correcting a flagged answer updates the UI live; multiple flags all require resolving", async ({
  page,
}) => {
  const email = uniqueEmail();
  await page.goto("/signup");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("correct-horse-battery-staple");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page).toHaveURL(/\/quizzes$/);

  await page.getByRole("link", { name: "New quiz" }).click();
  await page.getByLabel("Quiz title").fill(`Review test ${Date.now()}`);
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
  const questionRows = await queryRows<{ order_index: number }>(
    `select order_index from questions where quiz_id = $1 order by order_index limit 2`,
    [quizId],
  );
  expect(questionRows.length).toBe(2);
  const [questionNoA, questionNoB] = questionRows.map((r) => r.order_index);

  // Seed a needs_review submission with 2 flagged answers directly - no
  // endpoint creates one except the real OMR pipeline (same reasoning as
  // the results-dashboard test).
  const submissionId = randomUUID();
  const answerAId = randomUUID();
  const answerBId = randomUUID();
  await runSql(
    `insert into submissions (id, version_id, student_id, total_score, status)
     values ($1, $2, 'student-review-test', null, 'needs_review')`,
    [submissionId, versionId],
  );
  await runSql(
    `insert into answers (id, submission_id, question_no, detected_option, confidence, flagged, correct, score)
     values
       ($1, $3, $4, null, 0.4, true, null, null),
       ($2, $3, $5, null, 0.4, true, null, null)`,
    [answerAId, answerBId, submissionId, questionNoA, questionNoB],
  );

  await page.goto(`/submissions/${submissionId}`);
  await page.evaluate(() => {
    (window as unknown as { __noReload: boolean }).__noReload = true;
  });

  await expect(page.getByTestId("submission-status")).toHaveText("needs_review");
  await expect(page.getByTestId("flagged-answer")).toHaveCount(2);

  // Resolve the first flagged answer.
  const firstAnswer = page.getByTestId("flagged-answer").first();
  await firstAnswer.getByLabel("Correct option").selectOption("A");
  await firstAnswer.getByRole("button", { name: "Save" }).click();

  // Boundary: one of two resolved must NOT finalize the submission yet.
  await expect(page.getByTestId("flagged-answer")).toHaveCount(1);
  await expect(page.getByTestId("submission-status")).toHaveText("needs_review");

  // Resolve the second (last) flagged answer.
  const remainingAnswer = page.getByTestId("flagged-answer").first();
  await remainingAnswer.getByLabel("Correct option").selectOption("B");
  await remainingAnswer.getByRole("button", { name: "Save" }).click();

  await expect(page.getByTestId("submission-status")).toHaveText("finalized");
  await expect(page.getByText("This submission is finalized.")).toBeVisible();
  await expect(page.getByTestId("flagged-answer")).toHaveCount(0);

  // No manual page refresh happened at any point - the marker set right
  // after the initial load survives every correction.
  await expect
    .poll(() => page.evaluate(() => (window as unknown as { __noReload?: boolean }).__noReload))
    .toBe(true);

  await runSql(`delete from submissions where id = $1`, [submissionId]);
});
