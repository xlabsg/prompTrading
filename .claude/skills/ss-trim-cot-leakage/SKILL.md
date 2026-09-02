---
name: ss-trim-cot-leakage
description: Use when auditing or fixing prose that reads like a leaked reasoning transcript — dead references to a planning session or uncommitted draft, change narration such as "used to", "no longer", "the old X", PR or review vantage ("this PR adds", "rejected in review"), reviewer-addressed justifications, control-flow narration, or hedged planning residue in comments, docstrings, docs, or commit-adjacent notes.
---

# Trimming chain-of-thought leakage

Chain-of-thought leakage is prose whose vantage is the authoring session rather than the repository: it cites artifacts only that session could see, narrates the change instead of the state, or argues with a reviewer who has left.

The fix is not deletion alone. When a passage carries factual clauses, restate each so it stands at HEAD, then delete the transcript around it; a passage carrying none — an audit code, a control-flow walkthrough — is deleted outright. [ss-prose-standard](../ss-prose-standard/SKILL.md) owns the complete-proposition rule this skill applies. Guidance, not a script.

## The one test

For every suspect passage ask: **could a reader at HEAD, with no access to any session transcript, PR thread, or uncommitted draft, resolve every reference and verify every claim?**

If no, restate the surviving facts from the repository's vantage and delete the rest. If yes, it is not leakage, however historical it sounds — but resolvability only clears this skill's bar: on a current-state surface (a README, a docstring) a resolvable change story is still change narration, and class 3 below routes it to its proper home.

## Taxonomy

1. **Dead planning citations** — `(decision 7)`, `(audit C2)`, `plan §1.4`, phase labels (`T4`, `P-I`), "per the design doc" with no path. If the decision has a committed owner, cite it by name and path; otherwise delete the citation and restate its factual clause so it stands alone.
2. **PR and branch vantage** — "this PR adds", "the previous commit", "a follow-up will". State the shipped mechanism or the extension point; deferred work becomes a `TODO(tag):` marker or an issue reference.
3. **Change narration and version stamps** — "used to", "no longer", "the old client", "now we", "for now", "v1 of this". State the present behavior. A fixed regression becomes a present-tense counterfactual ("without the lock, two workers claim the same job"), never repo history ("used to double-claim").
4. **Review choreography** — "rejected in review", "as the reviewer noted", draft ordinals. Keep the surviving decision and rationale as plain fact; delete who said it when.
5. **Reviewer-addressed justification** — "this cast is safe — it simply…", "this is correct because…". A comment arguing its own correctness addresses a reviewer, not a maintainer. State the invariant that makes the code safe, or delete the comment if the code shows it.
6. **Restatement and derivation transcripts** — control-flow narration ("first we fetch, then we normalize"), test walkthroughs, proofs of obvious branches. Delete; keep only a non-obvious contract or invariant.
7. **Hedges and planning residue** — "probably fine", "should be enough", deferrals with no marker. Promote to `TODO`/`FIXME` or restate as the actual bound; delete the hedge.
8. **Authoring-language slips** — Chinese fragments left in otherwise-English comments and docs, or English residue in Chinese prose. Translate or delete.

## What is not leakage

Over-eager trimming fails in both directions — deleting durable references while keeping dead ones. Keep these:

- **Issue and PR references that resolve** — `#412`, `TODO(mark): ...`, "issue #N owns the follow-up".
- **Suppression justifications** — `# noqa: E501 -- generated URL`, `# type: ignore[arg-type] -- SQLAlchemy stub gap`, an explained bare `except`. Fix a wrong reason; never delete it.
- **Counterfactual-present regression pins** — "without the idempotency key, a retry double-places the order".
- **Measured bounds** — "(measured: 5k bars ≈ 0.3s)" calibrating a constant; "measured" is load-bearing.
- **Runtime old/new state** — "the old session drains before the new one accepts orders" describes live objects, not repo history.
- **Migration and compatibility facts** — "rows written before the `side` column default may hold NULL" is a live data contract a reader must know.
- **External references that resolve outside the repo** — OKX API section names, RFC citations, exchange field names.
- **Instrumental "used to"** — "the key used to sign requests" is instrumental, not temporal.
- **"This PR" in process docs** — `AGENTS.md` describing what a PR body should contain legitimately says "PR"; the ban is on code or docs adopting one PR's vantage.
- **`v1` as a path or protocol segment** — `/api/v1/...` is an identifier, not a version stamp.

## Workflow

1. **Scope.** Require an explicit scope. Exclude `node_modules`, `apps/web/dist`, `THIRD_PARTY_LICENSES`, lockfiles, and generated migrations. Recorded fixtures are derivatives: change the owning source and regenerate rather than hand-editing.
2. **Audit read-only first.** Run the [recall batteries](references/recall-batteries.md), calibrating each probe against a known positive and a near-miss negative before trusting its output, then judge every hit semantically. The batteries over-match by design and under-match by nature — also read the densest prose in scope (module docstrings, READMEs, long comments) with no pattern in hand.
3. **Fix the owner first.** Docstrings that feed generated docs or agent tool descriptions get fixed at the source, then regenerated. Model-visible text (agent prompts, tool descriptions) and user-visible strings change only with owning behavior evidence — otherwise leave them and report the deferral.
4. **Before deleting, enumerate propositions.** Check the overcorrection traps: a trim that flips an obligation into an endorsement, promotes a hypothetical to a shipped feature, deletes a true fact, or drops provenance is worse than the leakage.
5. **Verify.** Re-run the batteries expecting only sanctioned keeps and this skill's own files (which quote leaked wording as calibration). Confirm every remaining citation resolves at HEAD, run `git diff --check`, and run the tests owning any changed visible string.
