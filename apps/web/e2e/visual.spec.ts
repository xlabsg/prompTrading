import { test, expect } from "@playwright/test";

/**
 * Visual baselines for the console shell.
 *
 * Pixel snapshots are tied to a rendering platform (fonts, antialiasing), so they
 * are opt-in rather than part of the default suite — a baseline that fails on
 * every machine but the author's is noise. Run them explicitly and regenerate
 * baselines when the UI intentionally changes:
 *
 *   VISUAL_E2E=1 npx playwright test visual --update-snapshots
 *   VISUAL_E2E=1 npm run e2e:visual
 *
 * Dynamic regions (charts, animated cards) are excluded so the diff reflects
 * layout, not motion or data.
 */
test.describe("visual", () => {
  test.skip(process.env.VISUAL_E2E !== "1", "opt-in: set VISUAL_E2E=1");

  test("console dashboard", async ({ page }) => {
    await page.addInitScript(() => window.localStorage.setItem("asp_language", "en"));
    await page.goto("/");
    await expect(page.getByRole("button", { name: "Create strategy" })).toBeVisible();

    await expect(page).toHaveScreenshot("console-dashboard.png", {
      animations: "disabled",
      fullPage: false,
      maxDiffPixelRatio: 0.02,
      // Framer-motion cards settle at slightly different positions frame to
      // frame; mask the prompt card body so the baseline tracks the shell.
      mask: [page.getByTestId("new-strategy-input")],
    });
  });
});
