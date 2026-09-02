---
name: ss-prose-standard
description: Use when writing, reviewing, restoring, trimming, or auditing prose in the prompt-trading repo — deciding where documentation or comments are required across Markdown, docstrings, code and test comments, agent prompts, tool descriptions, error messages, and user-visible UI strings.
---

# PromptTrading prose standard

Write enough to preserve the contract, then remove reasoning transcripts, repetition, and decoration. A contract is an obligation, invariant, precondition, postcondition, or compatibility promise that a caller, callee, implementer, producer, or consumer relies on.

This skill owns editorial judgment and required coverage; use [ss-trim-cot-leakage](../ss-trim-cot-leakage/SKILL.md) for hunting reasoning-transcript leakage specifically. Guidance, not a script.

Comments describe non-obvious contracts or rationale that code cannot express. They do not restate what the code already says.

## Inputs and exclusions

Require an explicit scope. If it is missing, say so and stop; do not infer a repository-wide scope.

Review and audit tasks report findings without editing. Explicitly requested write, fix, or trim tasks apply clear changes.

Exclude generated and vendored content: `apps/web/dist`, `node_modules`, `THIRD_PARTY_LICENSES`, lockfiles, and migration SQL that a tool emitted. Put exclusions after inclusion globs so a later include cannot re-admit them (`rg ... --glob '!node_modules/**'`).

Treat fixtures and recorded outputs as derivative: change the owning source or scenario and regenerate, rather than hand-editing the recording.

## Preserve the complete proposition

Before editing, identify every proposition in the passage and preserve each relevant:

- actor and action;
- condition, timing, and ordering;
- modality — must, may, never;
- negative guarantee and exception;
- ownership, side effect, failure mode, and consequence.

Remove adjectives, repetition, and narration only when every factual clause survives and the result is clearer. A smaller word count alone is not an improvement.

Keep a complete local contract at the point of use — behavior, failure, ownership, consequence. Link aggressively to the owning document for architecture, rationale, algorithms, and history: one explanation has one home, though essential contract facts may repeat locally.

Keep non-obvious rationale when omitting it could plausibly cause misuse or an incorrect "simplification". Otherwise state the consequence and link the rationale home.

## Required coverage by location

This is not a one-way shortening pass. Add or restore prose when the code does not communicate a required contract below; do not add a comment when the facts are already obvious locally.

- **Public docstrings** (`strategy_sdk`, `risk_engine`, `okx_sdk`, service methods): document caller-visible return distinctions, raised exceptions, side effects, ownership, timing, cancellation, and durability. Units and sign conventions on anything numeric — price, size, PnL, fees — are contract, not decoration.
- **Internal comments:** orient non-local structure and genuinely complicated local structure — invariants, race ordering, ownership, security boundaries, surprising failure behavior. Delete control-flow narration and code restatement.
- **Module docstrings:** the module's role, its dependencies, and non-obvious architecture choices, linking each choice to its owning explanation.
- **Tests:** explain only non-obvious test design — why a fixture, an indirect observation, or a real-service dependency is necessary. Delete walkthroughs and inventories.
- **READMEs:** the consumer contract — configuration, semantics, failures, limitations, extension points. Note that `AGENTS.md` says not to write new README files by default; improve the ones that exist rather than adding more.
- **Runbooks** (`LIVE_TRADING_SETUP.md` and similar): prerequisites, required actions, the real entry path, observable verification, and concise warnings. Anything touching real funds states the failure mode explicitly.
- **Agent prompts and tool descriptions:** wording is behavior. Inspect the exact text the model receives, and change it only with evidence from a run, not by inspection.
- **Error messages and diagnostics:** name the failing subject or path, the violated rule, and the correction when it is non-obvious. Remove internal execution narration; never include a credential, key, or raw exchange payload.
- **UI strings:** inspect text, tooltips, placeholders, accessibility names, and format templates together. Preserve user data and code tokens verbatim.
- **Config and Compose comments:** explain access limits, non-obvious wiring or load order, security stance, and likely misuse. Do not narrate entries the file already shows.

Preserve searchable mechanism names and meaningful modal, temporal, or negative emphasis. Normalize only decorative emphasis.

## Workflow

1. Confirm the scope, the branch or base, and the applicable `AGENTS.md` / `CLAUDE.md` rules.
2. Read the owning code or document before judging a passage.
3. Inspect the whole requested scope, not only the largest files. Use searches to find candidates, then judge semantically.
4. Classify each candidate: keep, add, trim, restore, restructure, or defer. Apply changes only when the task authorizes edits; never manufacture edits to hit a deletion target.
5. Update the owner before any derivative artifact, then re-check analogous passages once a new rule emerges.
6. Run `git diff --check` and, for user- or model-visible strings, the behavior test that owns them.
7. Report the scope inspected, the changes made, deliberate keeps, deferrals, and checks actually run.

## Borderline decisions

A case is borderline only when two versions both satisfy the complete-proposition rule and trade accepted principles. A rewrite with one proposition-preserving answer is not borderline: apply it and report it. Never weaken a proposition to make progress.
