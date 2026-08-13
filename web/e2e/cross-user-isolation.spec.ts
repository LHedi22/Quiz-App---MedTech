import path from "path";
import { test, expect } from "@playwright/test";

function uniqueEmail(label: string) {
  return `e2e-${label}-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`;
}

async function signUp(page: import("@playwright/test").Page, email: string) {
  await page.goto("/signup");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("correct-horse-battery-staple");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page).toHaveURL(/\/quizzes$/);
}

// Subtask 7b.2: this system's data path is web -> FastAPI -> ownership check
// (app/db.py explicitly bypasses RLS as a trusted intermediary; the web app
// never talks to PostgREST/RLS directly - only Supabase Auth). So the
// meaningful cross-user guarantee to re-verify *through the Next.js app* is
// that the ownership checks the backend fix (docs/BLOCKERS.md's Phase 7
// entry) added are actually reachable and effective end-to-end from the UI,
// not the literal Subtask 1.2 PostgREST/RLS suite, which this architecture
// never routes web traffic through.
test("professor B can never see or reach professor A's quiz through the web app", async ({
  browser,
}) => {
  const contextA = await browser.newContext();
  const pageA = await contextA.newPage();
  const emailA = uniqueEmail("cross-user-a");
  await signUp(pageA, emailA);

  const title = `Professor A's private quiz ${Date.now()}`;
  await pageA.getByRole("link", { name: "New quiz" }).click();
  await pageA.getByLabel("Quiz title").fill(title);
  await pageA.getByRole("button", { name: "Create quiz" }).click();
  await pageA
    .locator('input[type="file"]')
    .setInputFiles(path.join(__dirname, "fixtures", "valid.xlsx"));
  await pageA.getByRole("button", { name: "Upload" }).click();
  await expect(pageA.getByText(/questions parsed and saved/)).toBeVisible();
  await pageA.getByRole("button", { name: "Continue to generate versions" }).click();
  await expect(pageA).toHaveURL(/\/quizzes\/[0-9a-f-]+$/);
  const quizAId = pageA.url().match(/\/quizzes\/([0-9a-f-]+)$/)![1];
  await pageA.getByLabel("Number of versions").fill("1");
  await pageA.getByRole("button", { name: "Generate versions" }).click();
  await expect(pageA.getByTestId("download-pdf")).toHaveCount(1);

  const contextB = await browser.newContext();
  const pageB = await contextB.newPage();
  const emailB = uniqueEmail("cross-user-b");
  await signUp(pageB, emailB);

  // B's own quiz list must never contain A's quiz title.
  await pageB.goto("/quizzes");
  await expect(pageB.getByText(title)).not.toBeVisible();

  // B directly guessing/typing A's quiz URL must not leak A's versions -
  // the ownership check (not RLS) is what's actually on this request path.
  await pageB.goto(`/quizzes/${quizAId}`);
  await expect(pageB.getByTestId("download-pdf")).toHaveCount(0);

  await contextA.close();
  await contextB.close();
});
