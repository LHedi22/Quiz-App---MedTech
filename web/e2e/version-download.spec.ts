import path from "path";
import { test, expect } from "@playwright/test";

function uniqueEmail() {
  return `e2e-dl-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`;
}

test("each version's download link is stable and points at a distinct, correct PDF", async ({
  page,
}) => {
  const email = uniqueEmail();
  await page.goto("/signup");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("correct-horse-battery-staple");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page).toHaveURL(/\/quizzes$/);

  await page.getByRole("link", { name: "New quiz" }).click();
  await page.getByLabel("Quiz title").fill("Download screen test");
  await page.getByRole("button", { name: "Create quiz" }).click();
  await page
    .locator('input[type="file"]')
    .setInputFiles(path.join(__dirname, "fixtures", "valid.xlsx"));
  await page.getByRole("button", { name: "Upload" }).click();
  await expect(page.getByText(/questions parsed and saved/)).toBeVisible();
  await page.getByRole("button", { name: "Continue to generate versions" }).click();

  await page.getByLabel("Number of versions").fill("2");
  await page.getByRole("button", { name: "Generate versions" }).click();

  const downloadLinks = page.getByTestId("download-pdf");
  await expect(downloadLinks).toHaveCount(2);
  const urls = await downloadLinks.evaluateAll((links) =>
    links.map((link) => (link as HTMLAnchorElement).href),
  );

  // Each version's own signed URL is stable, storage-backed content, not
  // regenerated per request - fetching the same link twice must return
  // byte-identical content both times (mirrors the backend's own
  // test_pdf_storage_endpoint.py::test_repeated_downloads_...).
  for (const url of urls) {
    const first = await (await page.request.get(url)).body();
    const second = await (await page.request.get(url)).body();
    expect(first.equals(second)).toBe(true);
    expect(first.subarray(0, 4).toString()).toBe("%PDF");
  }

  // ...and the two versions' PDFs remain distinct from each other.
  const [bodyA, bodyB] = await Promise.all(
    urls.map(async (url) => (await page.request.get(url)).body()),
  );
  expect(bodyA.equals(bodyB)).toBe(false);
});
