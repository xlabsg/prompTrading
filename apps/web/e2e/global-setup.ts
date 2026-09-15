import { request } from "@playwright/test";

const API_BASE_URL = process.env.E2E_API_BASE_URL || "http://localhost:8000";

/**
 * Fail fast with an actionable message when the dev stack is not up, instead of
 * letting every spec time out on a blank page.
 */
export default async function globalSetup(): Promise<void> {
  const ctx = await request.newContext();
  try {
    const res = await ctx.get(`${API_BASE_URL}/health`, { timeout: 10_000 });
    if (!res.ok()) {
      throw new Error(`health returned ${res.status()}`);
    }
  } catch (err) {
    throw new Error(
      `API not reachable at ${API_BASE_URL} (${(err as Error).message}).\n` +
        `Start the dev stack first:  cd infra/compose && ./update.sh`
    );
  } finally {
    await ctx.dispose();
  }
}
