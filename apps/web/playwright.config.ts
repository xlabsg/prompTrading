import { defineConfig, devices } from "@playwright/test";

/**
 * UI end-to-end tests.
 *
 * These drive a real browser against the running dev Compose stack (api/worker)
 * and, where a flow needs it, a real agent container + LLM. They exist because
 * API-level tests cannot see what the user actually sees: an overview that
 * re-renders as "generating the strategy", a chat bubble that streams internal
 * prompt text, a page that triggers a second generation on remount.
 *
 * Prerequisites:
 *   cd infra/compose && ./update.sh          # api + worker must be running
 *   infra/compose/.env must carry the LLM key
 *
 * The web app under test is Vite dev (current source, no build step); it proxies
 * /api to the host-exposed API on :8000.
 */
const WEB_PORT = Number(process.env.E2E_WEB_PORT || 4173);
const API_BASE_URL = process.env.E2E_API_BASE_URL || "http://localhost:8000";
const WEB_BASE_URL = `http://localhost:${WEB_PORT}`;

export default defineConfig({
  testDir: "./e2e",
  // Real agent + LLM turns run for minutes; nothing here is a unit test.
  timeout: 20 * 60 * 1000,
  expect: { timeout: 60 * 1000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  forbidOnly: Boolean(process.env.CI),
  reporter: [["list"], ["html", { open: "never" }]],
  outputDir: "test-results",
  globalSetup: "./e2e/global-setup.ts",

  use: {
    baseURL: WEB_BASE_URL,
    trace: "retain-on-failure",
    video: "retain-on-failure",
    screenshot: "only-on-failure",
    actionTimeout: 30 * 1000,
    navigationTimeout: 60 * 1000,
  },

  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],

  webServer: {
    // Production build served by `vite preview`, so the suite drives the same
    // artifact the app ships (and avoids the Vite 8 dev-time `import.meta.env`
    // runtime error). `/api` is proxied to the host-side API by vite.config.
    command: `npm run build && npm run preview -- --port ${WEB_PORT} --strictPort`,
    url: WEB_BASE_URL,
    reuseExistingServer: true,
    timeout: 180 * 1000,
  },
});
