---
name: ss-code-review
description: Use when reviewing a pull request or a branch diff in the stratsmith repo — orients the reviewer to this codebase's standards (AGENTS.md conventions, trading-critical paths, risk engine and credential handling, async lifecycle, Compose topology) and the review-specific checks that the code alone cannot show.
---

# Reviewing a stratsmith change

**Guidance, not a complete checklist.** Establish the real base ref, read the full diff plus enough surrounding code to understand the design, then prioritize correctness, money-losing behavior, credential safety, lifecycle, and broken required behavior over style. One substantiated blocker beats a list of nits.

```sh
git fetch origin && git diff --stat origin/main...HEAD
```

Re-establish the base and re-read after a retarget or a merge.

## Sources of truth

- `AGENTS.md` and `CLAUDE.md`: repository conventions, structure, and testing expectations.
- `packages/risk_engine/SDK_QUICK_REFERENCE.md`, then `TRADING_SDK_API.md` and `DESIGN.md` for anything touching risk control or order execution.
- `packages/control_plane/control_plane/models.py` and `enums.py`: the shared schema every service reads.
- `LIVE_TRADING_SETUP.md`: what the live path assumes about credentials and OKX configuration.

## Blocking requirements

1. **Trading-critical changes carry a regression test.** Strategy evaluation, order placement, position/PnL tracking, TP/SL and trailing-stop math, reconciliation, and WebSocket broadcasting are the paths where a silent bug costs real money. Inspection is not evidence.
2. **Money math is exact and directional.** Check sign conventions (long vs. short, entry vs. exit), rounding and tick/lot size, fee handling, and leverage. Verify a numeric claim against a worked example in the review, not against the author's summary.
3. **No secret reaches a log, exception message, response body, or test fixture.** Trading credentials are Fernet-encrypted at rest; confirm a new code path decrypts as late as possible and never re-serializes plaintext. `.env` keys stay documented, never embedded.
4. **Schema changes ship with a migration and every consumer updated.** A new or renamed field on a `control_plane` model must have its migration, and every service, router, and frontend type that reads it must move in the same diff.
5. **Async lifecycle is complete.** Every acquired session, client, task, subscription, and spawned container has an owner and a cleanup path that runs on the failure branch too. `cancel()` without `await` and a `close()` inside a `try` with no `finally` are defects, not style.
6. **New API surface is validated at the boundary.** Pydantic models, not manual dict digging; explicit status codes; no unbounded query that a caller can widen.
7. **Frontend and backend contracts agree.** A changed response shape updates the TypeScript types and the query keys that cache it.

## Manual checks

- **Intent and interface contracts:** trace both sides of every changed interface — errors, cancellation, ownership, and disposal, not just the happy path.
- **Concurrency and ordering:** for background jobs, Redis pub/sub consumers, and the worker's container spawning, check races before publication, cancellation mid-await, independent error reporting, and whether a retry can double-place an order. Idempotency at the exchange boundary is a correctness question, not a nicety.
- **Failure and partial state:** what happens when the exchange rejects, times out, or returns a partial fill; when Redis is down; when the container dies mid-job. A path that leaves the database claiming a state the exchange does not have is a blocker — check the reconciliation path.
- **Scope, ownership, necessity:** map each new abstraction, option, defensive copy, and compatibility path to a current production consumer. Challenge speculative generality and unrelated features.
- **Configuration and defaults:** ask what evidence supports each new default, especially risk limits, timeouts, and retry counts. Require an explicit choice or an explicit deferral.
- **Prompts and model-visible text:** for agent changes, read the exact prompt, tool schema, and tool result the model receives. Wording is behavior; review it as such.
- **Enforcement:** follow every denial path to the operation that executes it, and exercise alternate callers that bypass the validated facade.
- **Test strength:** assertions must fail on the intended regression and verify external state — rows, Redis contents, emitted messages, exchange state — rather than restating the implementation. Coverage is necessary, not sufficient.
- **Test reliability:** for resource-owning, asynchronous, or Compose-dependent tests, apply [ss-test-reliability](../ss-test-reliability/SKILL.md).
- **Prose:** review added comments, docstrings, and docs semantically with [ss-prose-standard](../ss-prose-standard/SKILL.md); flag change narration and reasoning-transcript residue via [ss-trim-cot-leakage](../ss-trim-cot-leakage/SKILL.md).
- **Evidence:** confirm the author ran the checks that [ss-pre-push-checks](../ss-pre-push-checks/SKILL.md) would have selected, and review the semantic gaps no check can detect.

## Reporting findings

State the defect, location, impact, and evidence. Put a localized defect inline on the tightest relevant range; use a PR-level comment for cross-cutting architecture or scope. Separate blockers from suggestions. When receiving review, verify each claim and either fix it or rebut it on technical grounds, without performative agreement.
