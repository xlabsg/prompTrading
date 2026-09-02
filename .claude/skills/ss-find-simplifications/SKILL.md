---
name: ss-find-simplifications
description: Use when working in the stratsmith repo to find non-obvious simplification candidates — dead, duplicated, speculative, over-built, added-then-removed, or hand-rolled-where-a-library-exists surfaces — and to turn them into evidence-backed proposals or targeted TODO markers rather than vague "this looks complex" complaints.
---

# Finding stratsmith simplifications

Turn a broad "find things to simplify" request into evidence-backed candidates that actually remove or collapse surface area. Guidance, not a checklist: follow the code, keep judgment active, and prefer a few well-proven candidates over a pile of thin guesses.

## Start with repo context

- Read `AGENTS.md` and `CLAUDE.md` before judging anything: readability and performance first, no speculative abstractions.
- Read `packages/risk_engine/DESIGN.md` before proposing anything inside the risk engine. Its nine validation checks, reconciliation, and snowflake IDs are intentional; a proposal that collapses one must beat the recorded rationale, not just cite simplicity.
- Treat the `executor`/`enhanced_executor`, `monitor`/`enhanced_monitor`, `manager`/`enhanced_manager` pairs as a deliberate seam by default. Removing an unused method *inside* one is still fair game; deleting a twin is a product decision, not a cleanup, unless the user overrides.
- `packages/strategy_sdk` is a published authoring surface. Its `Protocol` definitions may look unused inside this repo and still be load-bearing for strategy authors.

## What counts as a strong candidate

A strong simplification removes, folds, or demotes something real, with evidence that the current design costs more than it buys:

- A service method, router endpoint, config knob, enum member, model column, helper, or package has no production consumer.
- Tests, docs, or fixtures are the only consumers, and the behavior they pin is not load-bearing.
- Two representations mirror the same fact — a database column and a derived field, a Redis key and a table, a Pydantic schema and a TypeScript interface that drifted.
- A protocol or base class has methods every implementation must define but no caller uses.
- Speculative product generality with no owner: unused job kinds, half-wired providers, config paths no deployment sets, dead frontend routes.
- A migration path, compatibility shim, or special-case branch that only protects an unused API.
- Hand-rolled code reimplements what a maintained library or the standard library already provides, and the swap deletes the implementation *plus* its dedicated tests. Retry/backoff loops, rate limiters, caches, glob matching, datetime arithmetic, and pagination are the usual suspects.
- The simplified behavior differs slightly but is still reasonable and easier to explain.

Thin candidates do not qualify: one typo, "this file is long", or a removal without call-site proof.

## Survey broadly

Give each domain a real pass; do not let the first good candidate stop the survey. Useful domains here:

- **API surface:** routers, services, and schemas in `services/api/app` — endpoints without a frontend caller, service methods with one caller that could be private.
- **Trading engine:** manager/executor/monitor lifecycles, duplicated state between the database, in-memory session state, and the exchange.
- **Agent:** pipelines, tools, prompt assembly — the recent refactor left deleted modules and new adapters; check for orphaned imports, dead skills, and tools no prompt references.
- **Data:** provider clients and the new cache layer — duplicated normalization across `binance`, `okx`, and `us_stock`.
- **Control plane:** models, enums, and schemas with no writer or no reader.
- **Frontend:** components, hooks, and query keys with no mount point; state mirrored between TanStack Query and local state.
- **Infra:** Compose services, image layers, and requirements entries nothing imports.

Start with the largest production deltas; a survey that stops at obviously unused symbols misses the files where duplicated lifecycle machinery carries the real cost.

## Audit trust and lifecycle boundaries

For every defensive copy, validator, and captured callback, name where the value came from and who owns it next. Same-process typed calls ordinarily borrow read-only values; parsers, config loaders, queues, model/tool JSON, exchange responses, and wire decoders own or validate their data. A test built around a hostile fake is evidence of a possibly speculative contract, not automatic justification for keeping it.

For complex async code, draw the ownership graph and map each sentinel, readiness flag, cancellation path, and disposer to a distinct owner or transition. When several mechanisms mirror the same liveness fact, propose one lifecycle controller. Preserve separate machinery where it protects rollback, first-terminal-outcome arbitration, container ownership, or dispose-to-quiescence.

## Simplify prose with the code

Comments and docs are maintained surface area. Delete comments that restate code or duplicate rationale owned elsewhere; keep required local contracts. Apply [ss-prose-standard](../ss-prose-standard/SKILL.md) when a survey includes prose.

## Prove or reject each candidate

Classify consumers before writing anything:

- **Production:** `packages/*/`, `services/*/app` and `worker/`, `apps/web/src`, Compose configs, and anything a container entrypoint reaches.
- **Non-production:** tests, docs, fixtures, comments.
- **Ambiguous:** scripts and examples that may be smoke paths — inspect before classifying.

Use `rg` first — the exact symbol, the enum *value* as well as its name, the route path string, the config key, the Redis channel name, the column name in migrations, and the string as it appears in TypeScript. Then read the call sites. Dynamic dispatch, string-keyed registries, SQLAlchemy relationship names, and Pydantic field aliases will not show up in a naive symbol search.

Reject or downgrade a candidate when a production caller exists and removal would be a feature decision; when a documented design rationale outweighs the new evidence; when removal forces unrelated churn without reducing the public surface; or when the idea is correct but tiny — in that case leave a targeted marker instead.

## Write it up

For a durable proposal, write it where the team will find it — a `docs/` note or the PR body — with:

- an action-oriented title;
- **Problem:** the current API, the files, and the consumer evidence, with production callers separated from tests and docs;
- **Proposal:** exactly what to remove, fold, demote, or rehome, including tests, docs, migrations, and frontend types;
- **What we give up:** the strongest counterargument, stated legibly;
- **Acceptance criteria:** the observable end state;
- **Risks:** API and behavior changes, and why the tradeoff is still reasonable.

Be concrete enough that an implementing change can follow the trail. Avoid "simplify this package".

For small local cleanups that are clearly useful but not design decisions, use an inline marker with a stable tag and an action — `TODO(dup-normalizer): fold into data.cache once okx uses it` — never a speculative complaint.

## Validation

Run the checks [ss-pre-push-checks](../ss-pre-push-checks/SKILL.md) selects for whatever the removal touched, plus `git diff --check`. When reporting, say what was surveyed, what was intentionally excluded, and which checks actually ran.
