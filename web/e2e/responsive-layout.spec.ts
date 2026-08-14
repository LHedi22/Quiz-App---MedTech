import path from "path";
import { randomUUID } from "crypto";
import { test, expect, type Page } from "@playwright/test";
import { queryRows, runSql } from "./db";

function uniqueEmail() {
  return `e2e-responsive-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`;
}

const BREAKPOINTS = [
  { name: "mobile", width: 375, height: 812 },
  { name: "tablet", width: 768, height: 1024 },
  { name: "desktop", width: 1024, height: 800 },
];

/** No horizontal scrollbar at this viewport - the actual overflow contract
 * from Subtask 7c.1's DoD, not just "looks fine on resize". A couple of px
 * of tolerance absorbs scrollbar-width rounding across engines. */
async function expectNoHorizontalOverflow(page: Page, width: number) {
  const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
  expect(scrollWidth).toBeLessThanOrEqual(width + 2);
}

async function checkAllBreakpoints(page: Page, url: string) {
  for (const bp of BREAKPOINTS) {
    await page.setViewportSize({ width: bp.width, height: bp.height });
    await page.goto(url);
    await expectNoHorizontalOverflow(page, bp.width);
  }
}

test("app shell, quiz creation, and version download stay overflow-free at 375/768/1024px", async ({
  page,
}) => {
  const email = uniqueEmail();
  await page.goto("/signup");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("correct-horse-battery-staple");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page).toHaveURL(/\/quizzes$/);

  await checkAllBreakpoints(page, "/quizzes");
  await checkAllBreakpoints(page, "/account");

  // Mobile nav: hidden on desktop, toggleable and reaches every route on mobile.
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/quizzes");
  await expect(page.getByTestId("mobile-nav-toggle")).toBeVisible();
  await expect(page.getByTestId("mobile-nav-panel")).toHaveCount(0);
  await page.getByTestId("mobile-nav-toggle").click();
  await expect(page.getByTestId("mobile-nav-panel")).toBeVisible();
  await expect(page.getByTestId("mobile-nav-panel").getByRole("link", { name: "Results" })).toBeVisible();
  await expect(page.getByTestId("mobile-nav-panel").getByRole("link", { name: "Scan" })).toBeVisible();

  await page.setViewportSize({ width: 1024, height: 800 });
  await page.goto("/quizzes");
  await expect(page.getByTestId("mobile-nav-toggle")).not.toBeVisible();
  await expect(page.getByRole("navigation").getByRole("link", { name: "Results" })).toBeVisible();

  await checkAllBreakpoints(page, "/quizzes/new");

  const title = `Responsive test ${Date.now()}`;
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/quizzes/new");
  await page.getByLabel("Quiz title").fill(title);
  await page.getByRole("button", { name: "Create quiz" }).click();
  await page
    .locator('input[type="file"]')
    .setInputFiles(path.join(__dirname, "fixtures", "valid.xlsx"));
  await page.getByRole("button", { name: "Upload" }).click();
  await expect(page.getByText(/questions parsed and saved/)).toBeVisible();
  await expectNoHorizontalOverflow(page, 375);
  await page.getByRole("button", { name: "Continue to generate versions" }).click();
  await expect(page).toHaveURL(/\/quizzes\/[0-9a-f-]+$/);
  const quizId = page.url().match(/\/quizzes\/([0-9a-f-]+)$/)![1];

  await checkAllBreakpoints(page, `/quizzes/${quizId}`);

  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto(`/quizzes/${quizId}`);
  await page.getByLabel("Number of versions").fill("1");
  await page.getByRole("button", { name: "Generate versions" }).click();
  await expect(page.getByTestId("download-pdf")).toHaveCount(1);
  await expectNoHorizontalOverflow(page, 375);
});

test("results dashboard has no overflow at any breakpoint and the mobile card view carries identical fields to the desktop table", async ({
  page,
}) => {
  const email = uniqueEmail();
  await page.goto("/signup");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("correct-horse-battery-staple");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page).toHaveURL(/\/quizzes$/);

  await page.getByRole("link", { name: "New quiz" }).click();
  await page.getByLabel("Quiz title").fill(`Responsive results ${Date.now()}`);
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
  const submissionId = randomUUID();
  await runSql(
    `insert into submissions (id, version_id, student_id, total_score, status)
     values ($1, $2, 'responsive-student', 2.5, 'finalized')`,
    [submissionId, versionId],
  );

  await checkAllBreakpoints(page, `/results/${quizId}`);

  // Field parity: same seeded row, read from the desktop table then the
  // mobile card, values must match exactly (Subtask 7c.1 DoD).
  await page.setViewportSize({ width: 1024, height: 800 });
  await page.goto(`/results/${quizId}`);
  const row = page.getByTestId("submission-row");
  await expect(row).toBeVisible();
  const tableScore = await row.locator('[data-field="score"]').innerText();
  const tableDate = await row.locator('[data-field="created_at"]').innerText();
  const tableStatus = await row.getAttribute("data-status");

  await page.setViewportSize({ width: 375, height: 812 });
  const card = page.getByTestId("submission-card");
  await expect(card).toBeVisible();
  const cardScore = await card.locator('[data-field="score"]').innerText();
  const cardDate = await card.locator('[data-field="created_at"]').innerText();
  const cardStatus = await card.getAttribute("data-status");

  expect(cardScore).toBe(tableScore);
  expect(cardDate).toBe(tableDate);
  expect(cardStatus).toBe(tableStatus);
  await expect(card).toContainText("responsive-student");

  await runSql(`delete from submissions where id = $1`, [submissionId]);
});

test("flagged-answer review screen has no overflow at any breakpoint", async ({ page }) => {
  const email = uniqueEmail();
  await page.goto("/signup");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("correct-horse-battery-staple");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page).toHaveURL(/\/quizzes$/);

  await page.getByRole("link", { name: "New quiz" }).click();
  await page.getByLabel("Quiz title").fill(`Responsive review ${Date.now()}`);
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
    `select order_index from questions where quiz_id = $1 order by order_index limit 1`,
    [quizId],
  );
  const questionNo = questionRows[0].order_index;

  const submissionId = randomUUID();
  const answerId = randomUUID();
  await runSql(
    `insert into submissions
       (id, version_id, student_id, student_name, name_confidence, name_flagged, total_score, status)
     values ($1, $2, null, 'Long Student Name For Overflow Testing', 40.0, true, null, 'needs_review')`,
    [submissionId, versionId],
  );
  await runSql(
    `insert into answers (id, submission_id, question_no, detected_option, confidence, flagged, correct, score)
     values ($1, $2, $3, null, 0.4, true, null, null)`,
    [answerId, submissionId, questionNo],
  );

  for (const bp of BREAKPOINTS) {
    await page.setViewportSize({ width: bp.width, height: bp.height });
    await page.goto(`/submissions/${submissionId}`);
    await expect(page.getByTestId("flagged-name")).toBeVisible();
    await expect(page.getByTestId("flagged-answer")).toHaveCount(1);
    await expectNoHorizontalOverflow(page, bp.width);
  }

  await runSql(`delete from submissions where id = $1`, [submissionId]);
});
