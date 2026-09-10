---
name: record-web-demo
description: >-
  Automates recording high-fidelity product walkthroughs, animated GIFs, and MP4 demos
  for web applications using Playwright and FFmpeg. Handles human-like cursor animations,
  typing simulation, smooth scrolling through complex data dashboards (including
  TradingView lightweight charts), Docker hot-syncing, test state seeding, and
  palette-optimized GIF compression for GitHub READMEs (<5MB).
---

# Web Demo Recording & Visual Asset Generation

This skill provides an automated workflow to record polished, human-like product walkthroughs of web applications, producing lightweight, high-definition animated GIFs (<5MB) and MP4 videos for documentation, GitHub READMEs, and marketing materials.

## Quick Start Workflow

### Step 1: Ensure Local Environment & State are Ready
1. Confirm the web application and backend services are accessible (e.g. `http://localhost:3000`).
2. If frontend changes were recently compiled, hot-sync the build to Nginx without restarting containers:
   ```bash
   cd apps/web && npm run build
   docker cp dist/. compose-web-1:/usr/share/nginx/html/
   ```
3. Verify test strategy and backtest records exist with clean English titles, realistic metrics, and positive PnL trades.

### Step 2: Run Automated Playwright Recording
Execute the modular recording runner:
```bash
node .agents/skills/record-web-demo/scripts/record_demo.mjs
```
This launches a headless Chromium session, injects an animated demonstration cursor, performs human-paced typing and smooth easing navigation, records the video via Playwright's native `recordVideo`, and outputs a raw `.webm` recording.

### Step 3: Compress & Convert Assets via FFmpeg
Run the conversion script to produce both H.264 MP4 and a palette-optimized GIF under 5MB:
```bash
bash .agents/skills/record-web-demo/scripts/convert_assets.sh <input.webm> docs/assets/hero-demo
```
Output files generated:
- `docs/assets/hero-demo.mp4` (~2.0MB, H.264 high-profile, faststart)
- `docs/assets/hero-demo.gif` (~4.2MB, two-pass Bayer dithered palette, 12fps)

### Step 4: Capture High-Res Feature Screenshots
For deep-dive sections (e.g., Backtest performance dashboard, Git diff viewer):
```bash
node .agents/skills/record-web-demo/scripts/capture_snapshots.mjs
```
Generates `docs/assets/backtest-dashboard.png` (1050p full bleed, no cutoff).

---

## Core Techniques & Problem Solvers

### 1. Natural Human Interaction Simulation
- **Demo Cursor**: Injected via [`record_demo.mjs`](./scripts/record_demo.mjs) (`injectDemoCursor`), rendering an orange indicator with soft drop shadow and scale shrink on mouse click.
- **Cubic Bézier Easing**: Uses `smoothMove` with cubic acceleration/deceleration (`4t³` / `1 - (-2t+2)³/2`) to avoid robotic, linear cursor motion.
- **Typing Cadence**: Characters typed at 22-28ms delays with realistic sentence-end pauses.

### 2. Canvas & Chart Scroll Handling
- **The Issue**: Web charting engines (e.g., TradingView Lightweight Charts, SVG charts) intercept `mouse.wheel` events to zoom time horizons, blocking standard page scrolling.
- **The Fix**: The runner uses `smoothScrollContainer(page, targetY, durationMs)` which drives the container's `scrollTop` using browser-native `requestAnimationFrame`, smoothly bypassing chart event swallows.

### 3. Palette-Optimized GIF Encoding (<5MB)
Standard GIF encoders create massive files (20-40MB for a 25-second screencast). This skill uses a 2-pass filtergraph:
```bash
ffmpeg -y -i input.webm -vf "fps=12,scale=840:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=80:stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=3" output.gif
```
See [FFmpeg Recipes](./references/ffmpeg_recipes.md) for parameter tuning across light and dark mode interfaces.

---

## Verification & Quality Checklist

Before committing generated media to Git:
1. **File Size Check**: Run `ls -lh docs/assets/` to ensure `hero-demo.gif` is <= 4.5MB.
2. **Visual Inspection**: View the GIF using `view_file` to confirm:
   - All text and code snippets are 100% English.
   - Curves and crosshairs are sharp without color banding or ghosting.
   - Trades table displays positive returns cleanly.
3. **Embedded Link Verification**: Ensure `README.md` references the updated assets with proper responsive `<img>` tags.
