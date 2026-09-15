import { test, expect, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import path from "node:path";

/**
 * The user journey that API tests cannot see.
 *
 * Drives the real UI through the real agent container + LLM:
 *   1. create a strategy and answer the requirements chat;
 *   2. let it generate, then deliberately open the Overview view so its
 *      auto-generation window is observable;
 *   3. assert the properties we shipped fixes for:
 *      - the overview renders;
 *      - the chat bubble never streams the agent's internal prompt/file/skill
 *        text (the `token` stream must carry only the assistant's answer);
 *      - the sidebar does not show the five-step strategy-generation pipeline
 *        while the *overview* is generating;
 *      - `/generate_overview` fires exactly once, and a reload does not add a
 *        second run.
 */
const INTERNAL_MARKERS = [
  "Work on the existing trading strategy",
  "First decide what the request",
  "name: analyze",
  "functions.write(",
];

const PROMPT = "BTC-USDT 1h 双均线金叉做多死叉做空，2% 追踪止损";
const NUDGE = "你来定，按你的建议直接生成完整策略，不需要再确认。";
// A pure question. No "don't edit" instruction: the product promises a question
// answers without rewriting the strategy, and this asserts that it does.
const REFINE_QUESTION = "用一句话说明这个策略的核心逻辑。";

async function visible(page: Page, testId: string): Promise<boolean> {
  return page
    .getByTestId(testId)
    .first()
    .isVisible()
    .catch(() => false);
}

async function chatStatus(page: Page, strategyId: string): Promise<string> {
  const res = await page.request.get(`/api/strategies/${strategyId}`);
  return (await res.json())?.chat_status;
}

/** Published `strategy.py`, i.e. the live workspace the user sees. */
async function publishedStrategy(page: Page, strategyId: string): Promise<string> {
  const res = await page.request.get(`/api/strategies/${strategyId}/files`);
  const files = ((await res.json())?.files ?? []) as Array<{ name: string; content?: string }>;
  return (files.find((f) => f.name === "strategy.py")?.content ?? "").trim();
}

/**
 * Drop a strategy's overview so opening the Overview view must generate it.
 * The generation agent usually writes overview.md itself, which would otherwise
 * make the auto-generation path unreachable.
 */
function removeOverview(strategyId: string): void {
  const composeFile = path.resolve(process.cwd(), "..", "..", "infra", "compose", "docker-compose.dev.yml");
  execFileSync(
    "docker",
    [
      "compose",
      "-f",
      composeFile,
      "exec",
      "-T",
      "api",
      "rm",
      "-f",
      `/workspaces/${strategyId}/strategy/overview.md`,
    ],
    { stdio: "ignore" },
  );
}

test("create → generate → overview: one trigger, no internal leak", async ({ page }) => {
  test.setTimeout(20 * 60 * 1000);

  const generateOverviewBodies: string[] = [];
  let generateAndBacktestCount = 0;
  page.on("request", (req) => {
    if (req.method() !== "POST") return;
    if (req.url().includes("/generate_and_backtest")) generateAndBacktestCount += 1;
    if (req.url().includes("/chat/stream")) {
      const body = req.postData() || "";
      if (body.includes("/generate_overview")) generateOverviewBodies.push(body);
    }
  });

  await page.addInitScript(() => window.localStorage.setItem("asp_language", "en"));
  await page.goto("/");

  await page.getByTestId("new-strategy-input").fill(PROMPT);
  await page.getByRole("button", { name: "Create strategy" }).click();
  await page.waitForURL(/\/strategy\/[0-9a-f-]+\/overview/, { timeout: 60_000 });
  const strategyId = page.url().match(/strategy\/([0-9a-f-]+)/)![1];
  test.info().annotations.push({ type: "strategy", description: strategyId });

  let leaked: string | null = null;
  const sampleChat = async () => {
    const chatText = await page
      .getByTestId("chat-messages")
      .first()
      .innerText({ timeout: 2000 })
      .catch(() => "");
    const hit = INTERNAL_MARKERS.find((m) => chatText.includes(m));
    if (hit) leaked = hit;
  };

  // Phase 1: answer the requirements chat until it hands off to generation.
  let nudges = 0;
  const readyDeadline = Date.now() + 8 * 60 * 1000;
  while (Date.now() < readyDeadline) {
    await sampleChat();
    if (leaked) break;

    const status = await chatStatus(page, strategyId).catch(() => "");
    if (status === "ready" || status === "generating" || status === "done") break;

    if (status === "chatting" && nudges < 5) {
      const input = page.getByTestId("chat-input");
      if (await input.isEnabled().catch(() => false)) {
        await input.fill(NUDGE);
        await page.getByTestId("chat-send").click();
        nudges += 1;
        await page.waitForTimeout(3000);
        continue;
      }
    }
    await page.waitForTimeout(1000);
  }
  expect(leaked, `chat bubble streamed internal text: ${leaked}`).toBeNull();

  // Leave the Overview view after the chat hands off, so the overview's
  // auto-generation is not consumed by the transition to the code view when
  // generation completes -- we observe that window ourselves in phase 3.
  await page.goto(`/strategy/${strategyId}/code`);

  // Remount mid-generation: the console must attach to the running job, not
  // start another one, and must not touch the overview while code is being
  // generated. This is the "a reload re-triggers generation" class.
  await page.reload();
  await page.waitForTimeout(5_000);
  expect(generateAndBacktestCount, "remount started a second generation").toBe(1);
  expect(generateOverviewBodies.length, "overview generation ran during strategy generation").toBe(0);

  // Phase 2: wait for generation to finish.
  const doneDeadline = Date.now() + 10 * 60 * 1000;
  while (Date.now() < doneDeadline) {
    await sampleChat();
    if (leaked) break;
    if ((await chatStatus(page, strategyId).catch(() => "")) === "done") break;
    await page.waitForTimeout(2000);
  }
  expect(leaked, `chat bubble streamed internal text: ${leaked}`).toBeNull();
  expect(await chatStatus(page, strategyId), "strategy did not finish generating").toBe("done");

  // Phase 2b: a chat refine turn is where internal context used to leak into the
  // bubble, and where a "question" used to rewrite the strategy. Ask a pure
  // question and assert the reply streams clean *and* the code is untouched.
  const chatInput = page.getByTestId("chat-input");
  const codeBefore = await publishedStrategy(page, strategyId);
  await chatInput.fill(REFINE_QUESTION);
  await page.getByTestId("chat-send").click();
  await expect(chatInput).toBeDisabled({ timeout: 15_000 });
  await expect(chatInput).toBeEnabled({ timeout: 5 * 60 * 1000 });
  await sampleChat();
  expect(leaked, `chat bubble streamed internal text: ${leaked}`).toBeNull();

  const codeAfter = await publishedStrategy(page, strategyId);
  expect(codeAfter, "a question rewrote strategy.py").toBe(codeBefore);
  expect(codeAfter.length, "strategy.py is empty after the refine turn").toBeGreaterThan(0);

  // Phase 3: remove the overview the generation agent wrote, so opening the
  // Overview view must run the auto-generation path, then watch it.
  removeOverview(strategyId);
  await page.goto(`/strategy/${strategyId}/overview`);

  let sawOverviewGenerating = false;
  let generationCardDuringOverview = false;
  let overviewRendered = false;
  const overviewDeadline = Date.now() + 6 * 60 * 1000;
  while (Date.now() < overviewDeadline) {
    await sampleChat();
    if (leaked) break;

    if (await visible(page, "overview-auto-generating")) {
      sawOverviewGenerating = true;
      if (await visible(page, "generation-card")) generationCardDuringOverview = true;
    }
    if (await visible(page, "overview-content")) {
      overviewRendered = true;
      break;
    }
    await page.waitForTimeout(1000);
  }

  expect(leaked, `chat bubble streamed internal text: ${leaked}`).toBeNull();
  expect(overviewRendered, "overview content did not render").toBe(true);
  expect(sawOverviewGenerating, "the overview-generation state was never observed").toBe(true);
  expect(
    generationCardDuringOverview,
    "the sidebar showed the strategy-generation pipeline while generating the overview",
  ).toBe(false);

  // Phase 4: exactly one run, and a reload must not add another.
  expect(generateOverviewBodies.length, "expected one /generate_overview call").toBe(1);
  await page.reload();
  await page.waitForTimeout(10_000);
  expect(
    generateOverviewBodies.length,
    "reloading the overview re-triggered /generate_overview",
  ).toBe(1);
});
