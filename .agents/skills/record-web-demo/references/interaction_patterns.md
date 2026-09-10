# UI Interaction Patterns & Best Practices for Screencasts

Recording automated product walkthroughs requires mimicking organic human behavior while maintaining high visual clarity.

## 1. Demo Cursor Design
In headless browser recordings, native mouse pointers are invisible. To communicate user intent:
- **Visual Appearance**: High-contrast, vibrant accent color (e.g. `rgba(249, 115, 22, 0.95)` with a 2px white border and soft box-shadow `0 2px 10px rgba(0,0,0,0.35)`).
- **Physical Feedback**: Shrink on click (`scale(0.75)`) and return to baseline on mouse up. This signals clicks clearly without needing sound or distracting pulse rings.
- **Pointer Events**: Ensure `pointer-events: none` on the injected cursor DOM element so it never blocks real clicks or hover events.

## 2. Realistic Cursor Dynamics (`smoothMove`)
Never use instant teleportation (`page.mouse.move(x, y)` without steps).
- **Cubic Polynomial Easing**:
  ```javascript
  const ease = t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
  const x = start.x + (end.x - start.x) * ease;
  const y = start.y + (end.y - start.y) * ease;
  ```
- **Step Count**: 18-25 steps at 16ms intervals (~300-400ms per movement) gives a natural, intentional pace without feeling sluggish.

## 3. Typing Cadence
- Use delay: `22ms - 28ms` per keystroke (`page.keyboard.type(text, { delay: 24 })`).
- Add a 300ms pause after clicking the input field, and a 400ms pause after typing finishes before moving the mouse towards the action button.

## 4. Complex Chart & Dashboard Scrolling
- **The Issue**: Canvas elements (like TradingView Lightweight Charts or HTML5 charts) capture wheel events to zoom horizontal timelines. If the cursor is over the chart, standard `page.mouse.wheel` will zoom in/out instead of scrolling the page.
- **The Solution**: Use `smoothScrollContainer(page, targetY, durationMs)` to drive `scrollTop` directly with `requestAnimationFrame`. This guarantees 60fps buttery scrolling across the dashboard regardless of what elements sit underneath.
