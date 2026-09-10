import { chromium } from 'playwright';
import path from 'path';
import fs from 'fs';

const OUTPUT_DIR = process.env.DEMO_RECORDINGS_DIR || path.resolve(process.cwd(), 'recordings');
const APP_URL = process.env.DEMO_APP_URL || 'http://localhost:3000';
const DEFAULT_STRATEGY_ID = process.env.DEMO_STRATEGY_ID || '76991c53-7ab2-46e0-bc6b-0dd82263ab21';

if (!fs.existsSync(OUTPUT_DIR)) {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
}

/**
 * Injects a stylish demonstration cursor that mimics human touch/click.
 */
export async function injectDemoCursor(page) {
  await page.evaluate(() => {
    if (document.getElementById('demo-cursor')) return;
    const cursor = document.createElement('div');
    cursor.id = 'demo-cursor';
    cursor.style.cssText = `
      position: fixed;
      width: 18px;
      height: 18px;
      border-radius: 50%;
      background: rgba(249, 115, 22, 0.95);
      border: 2px solid #ffffff;
      box-shadow: 0 2px 10px rgba(0,0,0,0.35);
      pointer-events: none;
      z-index: 9999999;
      transform: translate(-50%, -50%);
      transition: transform 0.08s ease, background 0.12s ease;
      left: -100px;
      top: -100px;
    `;
    document.body.appendChild(cursor);

    window.addEventListener('mousemove', (e) => {
      cursor.style.left = e.clientX + 'px';
      cursor.style.top = e.clientY + 'px';
    });
    window.addEventListener('mousedown', () => {
      cursor.style.transform = 'translate(-50%, -50%) scale(0.75)';
      cursor.style.background = 'rgba(234, 88, 12, 1)';
    });
    window.addEventListener('mouseup', () => {
      cursor.style.transform = 'translate(-50%, -50%) scale(1)';
      cursor.style.background = 'rgba(249, 115, 22, 0.95)';
    });
  });
}

/**
 * Smoothly interpolates mouse movement with cubic easing.
 */
export async function smoothMove(page, start, end, steps = 22) {
  for (let i = 1; i <= steps; i++) {
    const t = i / steps;
    const ease = t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
    const x = start.x + (end.x - start.x) * ease;
    const y = start.y + (end.y - start.y) * ease;
    await page.mouse.move(x, y);
    await page.waitForTimeout(16);
  }
}

/**
 * Smoothly scrolls an inner container (e.g. bypasses TradingView chart canvas zoom traps).
 */
export async function smoothScrollContainer(page, targetY, durationMs = 700) {
  await page.evaluate(async ({ targetY, durationMs }) => {
    const el = document.querySelector('.lg\\:overflow-y-auto') || document.querySelector('main > div > div:nth-child(2) > div');
    if (!el) return;
    const startY = el.scrollTop;
    const diff = targetY - startY;
    const startTime = performance.now();
    return new Promise((resolve) => {
      function step(now) {
        const elapsed = now - startTime;
        const progress = Math.min(elapsed / durationMs, 1);
        const ease = progress < 0.5 ? 2 * progress * progress : -1 + (4 - 2 * progress) * progress;
        el.scrollTop = startY + diff * ease;
        if (progress < 1) {
          requestAnimationFrame(step);
        } else {
          resolve();
        }
      }
      requestAnimationFrame(step);
    });
  }, { targetY, durationMs });
  await page.waitForTimeout(durationMs + 80);
}

async function main() {
  console.log(`[demo-recorder] Starting Chromium session with viewport 1440x900...`);
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    recordVideo: {
      dir: OUTPUT_DIR,
      size: { width: 1440, height: 900 },
    },
  });

  const page = await context.newPage();
  
  // Enforce English localization
  await page.addInitScript(() => {
    window.localStorage.setItem('i18nextLng', 'en');
  });

  let currentPos = { x: 720, y: 450 };

  console.log('[1/16] Navigating to Dashboard...');
  await page.goto(APP_URL, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('text=Build your next strategy');
  await page.waitForSelector('text=Local Dev');
  await page.waitForTimeout(600);
  await injectDemoCursor(page);
  await page.mouse.move(currentPos.x, currentPos.y);

  console.log('[2/16] Focusing prompt input...');
  const promptTarget = { x: 550, y: 430 };
  await smoothMove(page, currentPos, promptTarget, 22);
  currentPos = promptTarget;
  await page.mouse.click(currentPos.x, currentPos.y);
  await page.waitForTimeout(300);

  console.log('[3/16] Typing quantitative strategy prompt...');
  const promptText = 'Build an intraday breakout strategy on ETH/USDT 15m candles with Bollinger Bands, exit at midline, and 1.5% stop loss.';
  await page.keyboard.type(promptText, { delay: 24 });
  await page.waitForTimeout(400);

  console.log('[4/16] Triggering strategy generation...');
  const createBtnTarget = { x: 790, y: 568 };
  await smoothMove(page, currentPos, createBtnTarget, 20);
  currentPos = createBtnTarget;
  await page.mouse.down();
  await page.waitForTimeout(120);
  await page.mouse.up();
  await page.waitForTimeout(350);

  console.log('[5/16] Navigating to generated strategy workspace...');
  await page.goto(`${APP_URL}/strategy/${DEFAULT_STRATEGY_ID}/code`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(1400);
  await injectDemoCursor(page);
  await page.mouse.move(currentPos.x, currentPos.y);

  console.log('[6/16] Inspecting generated Python logic...');
  const codeTarget = { x: 680, y: 440 };
  await smoothMove(page, currentPos, codeTarget, 22);
  currentPos = codeTarget;
  await page.waitForTimeout(400);
  await page.mouse.wheel(0, 160);
  await page.waitForTimeout(500);

  console.log('[7/16] Opening Git Diff inspection...');
  const diffBtnBox = await page.locator('button:has-text("Diff")').first().boundingBox();
  const diffBtnTarget = diffBtnBox ? { x: diffBtnBox.x + diffBtnBox.width / 2, y: diffBtnBox.y + diffBtnBox.height / 2 } : { x: 890, y: 110 };
  await smoothMove(page, currentPos, diffBtnTarget, 22);
  currentPos = diffBtnTarget;
  await page.mouse.click(currentPos.x, currentPos.y);
  await page.waitForTimeout(1300);

  console.log('[8/16] Navigating to Backtest Results tab...');
  const backtestTabBox = await page.locator('header button:has-text("Backtest")').first().boundingBox();
  const backtestTabTarget = backtestTabBox ? { x: backtestTabBox.x + backtestTabBox.width / 2, y: backtestTabBox.y + backtestTabBox.height / 2 } : { x: 785, y: 38 };
  await smoothMove(page, currentPos, backtestTabTarget, 22);
  currentPos = backtestTabTarget;
  await page.mouse.click(currentPos.x, currentPos.y);
  await page.waitForTimeout(1500);
  await injectDemoCursor(page);

  console.log('[9/16] Highlighting key performance metrics...');
  const returnCardTarget = { x: 560, y: 240 };
  await smoothMove(page, currentPos, returnCardTarget, 20);
  currentPos = returnCardTarget;
  await page.waitForTimeout(500);

  const sharpeCardTarget = { x: 900, y: 240 };
  await smoothMove(page, currentPos, sharpeCardTarget, 20);
  currentPos = sharpeCardTarget;
  await page.waitForTimeout(600);

  console.log('[10/16] Smooth scrolling down to Equity & Drawdown curves...');
  await smoothScrollContainer(page, 440, 750);

  console.log('[11/16] Tracing upward alpha equity trajectory...');
  const curveStart = { x: 420, y: 460 };
  const curveMid = { x: 490, y: 400 };
  const curvePeak = { x: 565, y: 375 };
  await smoothMove(page, currentPos, curveStart, 18);
  currentPos = curveStart;
  await page.waitForTimeout(150);
  await smoothMove(page, currentPos, curveMid, 18);
  currentPos = curveMid;
  await page.waitForTimeout(150);
  await smoothMove(page, currentPos, curvePeak, 20);
  currentPos = curvePeak;
  await page.waitForTimeout(800);

  console.log('[12/16] Scrolling down to Execution Details table...');
  await smoothScrollContainer(page, 860, 750);

  console.log('[13/16] Inspecting profitable executed trades...');
  const tradeRow1 = { x: 720, y: 440 };
  await smoothMove(page, currentPos, tradeRow1, 20);
  currentPos = tradeRow1;
  await page.waitForTimeout(600);

  const tradeRow2 = { x: 720, y: 550 };
  await smoothMove(page, currentPos, tradeRow2, 18);
  currentPos = tradeRow2;
  await page.waitForTimeout(800);

  console.log('[14/16] Navigating to Live Trading tab...');
  const liveTabBox = await page.locator('header button:has-text("Live")').first().boundingBox();
  const liveTabTarget = liveTabBox ? { x: liveTabBox.x + liveTabBox.width / 2, y: liveTabBox.y + liveTabBox.height / 2 } : { x: 805, y: 38 };
  await smoothMove(page, currentPos, liveTabTarget, 24);
  currentPos = liveTabTarget;
  await page.mouse.click(currentPos.x, currentPos.y);
  await page.waitForTimeout(1400);
  await injectDemoCursor(page);

  console.log('[15/16] Highlighting Paper Trading mode...');
  const startBtnTarget = { x: 885, y: 160 };
  await smoothMove(page, currentPos, startBtnTarget, 20);
  currentPos = startBtnTarget;
  await page.waitForTimeout(1500);

  console.log('[16/16] Finalizing video recording...');
  const video = page.video();
  await page.close();
  await context.close();
  await browser.close();

  const videoPath = await video.path();
  console.log(`\n[SUCCESS] Raw video saved at:\n${videoPath}\n`);
}

main().catch((err) => {
  console.error('[demo-recorder] Error during recording:', err);
  process.exit(1);
});
