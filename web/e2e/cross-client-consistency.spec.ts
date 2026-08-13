import { test, expect } from "@playwright/test";
import { scanVersion, seedQuiz } from "./pythonRegression";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

// Subtask 7b.3: the web app has no scan-initiating UI at all (scanning is
// mobile-only per CLAUDE.md's phase split), so this scans via the real
// /scan endpoint directly - exactly the fallback the Steps section itself
// allows ("or the /scan endpoint directly if mobile hardware isn't
// available"). "Mobile's next status fetch" is simulated with the same
// GET /submissions/{id} call mobile's own batch-summary screen makes
// (docs/PROGRESS.md's Phase 8.4 entry), since no mobile hardware/emulator
// exists in this environment (an established, already-documented constraint
// - see docs/BLOCKERS.md item 3).
test("a scanned submission appears correctly in the dashboard, and a web correction is visible to mobile's next fetch", async ({
  page,
}) => {
  const seeded = seedQuiz(`Cross-client consistency ${Date.now()}`);
  const scanResult = scanVersion(
    seeded.version_id,
    "ambiguous:0",
    seeded.token,
    "cross-client-student",
  );
  expect(scanResult.status).toBe("needs_review");
  expect(scanResult.flagged_question_numbers.length).toBe(1);
  const flaggedQuestionNo = scanResult.flagged_question_numbers[0];
  const correctOption = scanResult.correct_option_for_flagged_row!;

  await page.goto("/login");
  await page.getByLabel("Email").fill(seeded.email);
  await page.getByLabel("Password").fill(seeded.password);
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page).toHaveURL(/\/quizzes$/);

  // DoD 1: visible, with correct data, in the dashboard - reached via a
  // normal navigation/refetch, not any special-cased fetch.
  await page.goto(`/results/${seeded.quiz_id}`);
  const row = page.getByTestId("submission-row");
  await expect(row).toHaveCount(1);
  await expect(row).toHaveAttribute("data-status", "needs_review");
  await expect(page.getByText("cross-client-student")).toBeVisible();

  await page.getByRole("link", { name: "Review" }).click();
  await expect(page).toHaveURL(new RegExp(`/submissions/${scanResult.submission_id}$`));
  await expect(page.getByText(`Question ${flaggedQuestionNo}`)).toBeVisible();

  await page.getByLabel("Correct option").selectOption(correctOption);
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByTestId("submission-status")).toHaveText("finalized");

  // DoD 2: reflected in mobile's next status fetch - GET /submissions/{id}
  // directly, the same call mobile's batch-summary screen makes.
  const mobileFetch = await page.request.get(
    `${API_BASE_URL}/submissions/${scanResult.submission_id}`,
    { headers: { Authorization: `Bearer ${seeded.token}` } },
  );
  expect(mobileFetch.ok()).toBe(true);
  const mobileBody = await mobileFetch.json();
  expect(mobileBody.status).toBe("finalized");
  expect(mobileBody.answers.every((a: { flagged: boolean }) => !a.flagged)).toBe(true);
});
