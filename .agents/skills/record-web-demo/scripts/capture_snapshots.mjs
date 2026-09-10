import { chromium } from 'playwright';
import path from 'path';
import fs from 'fs';

const APP_URL = process.env.DEMO_APP_URL || 'http://localhost:3000';
const DEFAULT_STRATEGY_ID = process.env.DEMO_STRATEGY_ID || '76991c53-7ab2-46e0-bc6b-0dd82263ab21';
const OUTPUT_DIR = process.env.SNAPSHOT_OUTPUT_DIR || path.resolve(process.cwd(), 'docs/assets');

if (!fs.existsSync(OUTPUT_DIR)) {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
}

async function main() {
  console.log('[snapshot-tool] Launching browser with 1440x1050 viewport...');
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1050 },
    deviceScaleFactor: 2, // High DPI / Retina clarity
  });

  await page.addInitScript(() => {
    window.localStorage.setItem('i18nextLng', 'en');
  });

  // 1. Backtest full dashboard snapshot
  const backtestUrl = `${APP_URL}/strategy/${DEFAULT_STRATEGY_ID}/backtest`;
  console.log(`[snapshot-tool] Capturing Backtest Dashboard from ${backtestUrl}...`);
  await page.goto(backtestUrl, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(2000);

  const backtestImgPath = path.join(OUTPUT_DIR, 'backtest-dashboard.png');
  await page.screenshot({ path: backtestImgPath });
  console.log(`[snapshot-tool] Saved: ${backtestImgPath}`);

  // 2. Code & Diff snapshot
  const codeUrl = `${APP_URL}/strategy/${DEFAULT_STRATEGY_ID}/code`;
  console.log(`[snapshot-tool] Capturing Code & Diff View from ${codeUrl}...`);
  await page.goto(codeUrl, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(1500);

  const diffBtn = page.locator('button:has-text("Diff")').first();
  if (await diffBtn.isVisible()) {
    await diffBtn.click();
    await page.waitForTimeout(1000);
  }

  const codeDiffImgPath = path.join(OUTPUT_DIR, 'code-diff-view.png');
  await page.screenshot({ path: codeDiffImgPath });
  console.log(`[snapshot-tool] Saved: ${codeDiffImgPath}`);

  await browser.close();
  console.log('[snapshot-tool] All snapshots generated successfully!');
}

main().catch((err) => {
  console.error('[snapshot-tool] Error capturing snapshots:', err);
  process.exit(1);
});
