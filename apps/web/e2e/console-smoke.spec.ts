import { test, expect } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => window.localStorage.setItem("asp_language", "en"));
});

test("console renders the new-strategy prompt", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Create strategy" })).toBeVisible();
  await expect(page.getByPlaceholder(/Build an intraday breakout/)).toBeVisible();
});
