import path from "path";
import { test, expect } from "@playwright/test";

function uniqueEmail() {
  return `e2e-quiz-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`;
}

async function signUp(page: import("@playwright/test").Page) {
  const email = uniqueEmail();
  const password = "correct-horse-battery-staple";
  await page.goto("/signup");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page).toHaveURL(/\/quizzes$/);
}

test("uploading a malformed workbook surfaces every row error in the UI", async ({ page }) => {
  await signUp(page);

  await page.getByRole("link", { name: "New quiz" }).click();
  await page.getByLabel("Quiz title").fill("Malformed upload test");
  await page.getByRole("button", { name: "Create quiz" }).click();

  const fileInput = page.locator('input[type="file"]');
  await fileInput.setInputFiles(path.join(__dirname, "fixtures", "multiple_errors.xlsx"));
  await page.getByRole("button", { name: "Upload" }).click();

  // multiple_errors.xlsx (backend/tests/fixtures/excel): row 2 is missing its
  // question text, row 3 has an empty option and an invalid correct_option -
  // both rows' exact messages (test_parsing.py's own expectations) must be
  // visible, not just a generic "upload failed".
  await expect(page.getByText(/Row 2: question_text is empty/)).toBeVisible();
  await expect(
    page.getByText(/Row 3: option_b is empty; correct_option must be exactly one of A\/B\/C\/D, got 'E'/),
  ).toBeVisible();
});

test("successful quiz creation ends with N versions visible and downloadable", async ({
  page,
}) => {
  await signUp(page);

  await page.getByRole("link", { name: "New quiz" }).click();
  await page.getByLabel("Quiz title").fill("End to end quiz");
  await page.getByRole("button", { name: "Create quiz" }).click();

  const fileInput = page.locator('input[type="file"]');
  await fileInput.setInputFiles(path.join(__dirname, "fixtures", "valid.xlsx"));
  await page.getByRole("button", { name: "Upload" }).click();

  await expect(page.getByText(/3 questions parsed and saved/)).toBeVisible();
  await page.getByRole("button", { name: "Continue to generate versions" }).click();

  await expect(page).toHaveURL(/\/quizzes\/[0-9a-f-]+$/);
  await page.getByLabel("Number of versions").fill("3");
  await page.getByRole("button", { name: "Generate versions" }).click();

  const downloadLinks = page.getByTestId("download-pdf");
  await expect(downloadLinks).toHaveCount(3);

  const urls = await downloadLinks.evaluateAll((links) =>
    links.map((link) => (link as HTMLAnchorElement).href),
  );
  expect(new Set(urls).size).toBe(3);

  const responses = await Promise.all(urls.map((url) => page.request.get(url)));
  for (const response of responses) {
    expect(response.ok()).toBe(true);
    const body = await response.body();
    expect(body.subarray(0, 4).toString()).toBe("%PDF");
  }
  const bodies = await Promise.all(responses.map((r) => r.body()));
  const distinctByteLength = new Set(bodies.map((b) => b.length));
  const distinctContent = new Set(bodies.map((b) => b.toString("base64")));
  // Versions are independently shuffled - their rendered PDFs must not be
  // byte-identical (question/option order differs per version).
  expect(distinctContent.size).toBe(3);
  expect(distinctByteLength.size).toBeGreaterThanOrEqual(1);
});
