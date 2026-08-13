import path from "path";
import { test, expect } from "@playwright/test";
import { scanVersionFromUrl } from "./pythonRegression";

function uniqueEmail() {
  return `e2e-happy-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`;
}

// Subtask 7b.4: re-runs Phase 9.1's happy path, driving every web-facing
// step (signup/login, quiz creation, Excel upload, version generation, PDF
// download) through the real Next.js UI. Scanning has no web UI at all
// (mobile-only, per CLAUDE.md) - that one step consumes the exact signed
// URLs read out of the UI's own download links, so it's scanning precisely
// what a professor clicking "Download PDF" would receive, not a
// re-fetched-via-API substitute.
test("full happy path driven through the Next.js UI finalizes all 3 versions at the mathematically correct score", async ({
  page,
}) => {
  const email = uniqueEmail();
  await page.goto("/signup");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("correct-horse-battery-staple");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page).toHaveURL(/\/quizzes$/);

  await page.getByRole("link", { name: "New quiz" }).click();
  await page.getByLabel("Quiz title").fill(`Full happy path ${Date.now()}`);
  await page.getByRole("button", { name: "Create quiz" }).click();
  await page
    .locator('input[type="file"]')
    .setInputFiles(path.join(__dirname, "fixtures", "valid.xlsx"));
  await page.getByRole("button", { name: "Upload" }).click();
  await expect(page.getByText(/3 questions parsed and saved/)).toBeVisible();
  await page.getByRole("button", { name: "Continue to generate versions" }).click();
  await expect(page).toHaveURL(/\/quizzes\/[0-9a-f-]+$/);
  const quizId = page.url().match(/\/quizzes\/([0-9a-f-]+)$/)![1];

  await page.getByLabel("Number of versions").fill("3");
  await page.getByRole("button", { name: "Generate versions" }).click();

  const rows = page.locator("li[data-version-id]");
  await expect(rows).toHaveCount(3);
  const versions = await rows.evaluateAll((els) =>
    els.map((el) => {
      const link = el.querySelector('[data-testid="download-pdf"]') as HTMLAnchorElement | null;
      return { versionId: el.getAttribute("data-version-id")!, pdfUrl: link?.href ?? null };
    }),
  );
  expect(versions.every((v) => v.pdfUrl)).toBe(true);

  // Versions 0 and 2: every question correct (max score). Version 1: one
  // deliberately wrong answer - a differentiated, not uniformly-perfect,
  // set of scores actually exercises the score math (same rationale as
  // test_e2e_happy_path.py's own "not all-correct-only" design choice).
  const modes = ["correct", "wrong:0", "correct"];
  const results = versions.map((v, i) =>
    scanVersionFromUrl(v.versionId, v.pdfUrl!, modes[i], `happy-path-student-${i}`),
  );

  for (const [i, result] of results.entries()) {
    expect(result.status, `version ${i} status`).toBe("finalized");
    expect(result.total_score, `version ${i} score`).toBe(i === 1 ? 2.0 : 3.0);
    expect(result.flagged_question_numbers, `version ${i} flags`).toEqual([]);
  }

  // Confirmed in the Next.js dashboard too, not just via the API responses.
  await page.goto(`/results/${quizId}`);
  await expect(page.getByTestId("submission-row")).toHaveCount(3);
  for (const i of [0, 1, 2]) {
    const row = page.getByTestId("submission-row").filter({
      has: page.getByText(`happy-path-student-${i}`),
    });
    await expect(row).toHaveAttribute("data-status", "finalized");
    await expect(row).toContainText(i === 1 ? "2" : "3");
  }
});
