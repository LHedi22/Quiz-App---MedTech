import { test, expect } from "@playwright/test";

// web-app audit A4: every response carries the baseline security headers
// configured in next.config.ts.
test("baseline security headers are present on a page response", async ({ page }) => {
  const response = await page.goto("/login");
  expect(response).not.toBeNull();

  const headers = response!.headers();

  expect(headers["x-frame-options"]).toBe("DENY");
  expect(headers["x-content-type-options"]).toBe("nosniff");
  expect(headers["referrer-policy"]).toBe("same-origin");
  expect(headers["strict-transport-security"]).toContain("max-age=63072000");
  expect(headers["permissions-policy"]).toContain("camera=(self)");

  const csp = headers["content-security-policy-report-only"];
  expect(csp, "report-only CSP should be set").toBeTruthy();
  expect(csp).toContain("frame-ancestors 'none'");
  expect(csp).toContain("default-src 'self'");
});
