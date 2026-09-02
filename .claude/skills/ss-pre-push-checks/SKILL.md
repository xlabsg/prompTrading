---
name: ss-pre-push-checks
description: Use before committing, pushing, force-pushing, opening a PR, or claiming checks pass in the prompt-trading repo, to select the smallest set of tests and checks that actually cover the outgoing diff instead of reflexively running every suite or the whole Compose stack.
---

# PromptTrading pre-push checks

Run relevant local evidence once before a push. There is no repository-wide gate and no pre-commit hook here: CI (`.github/workflows/docker-build-push.yml`) only builds and pushes images, so nothing but this selection stands between a change and a broken deploy.

## Inspect the outgoing change

```sh
git status --short --branch
git diff --stat @{upstream}...HEAD   # committed scope vs. the real base
git diff --stat                      # unstaged
git diff --cached --stat             # staged
```

Verify the actual base ref (`origin/main`, or a PR's live base) rather than assuming. After merging a changed base, re-inspect the combined scope and rerun only the checks the merge invalidated.

## Select relevant evidence

Every behavior change needs the narrowest check that would fail for its regression. Add broader checks only for the surfaces the diff actually reaches.

- **A Python package** (`packages/<name>/`): run its own suite from the package root, where its `pytest.ini`/`pyproject.toml` lives.
  ```sh
  cd packages/<name> && pytest -q tests/test_<behavior>.py::test_<name>
  ```
  Widen to the package's full `pytest -q` when a shared contract changed; leave cross-package sweeps out unless the change is genuinely cross-cutting.
- **`services/api`**: run the owning unit test first. Its `tests/` are marked `integration`/`e2e_core`/`e2e_extended` and need the Compose stack; select by marker rather than running everything:
  ```sh
  cd services/api && pytest -q -m e2e_core
  ```
  Use the `integration-test` skill when the request is "run the integration tests" rather than "validate this diff".
- **`services/worker`**: worker changes that spawn containers need at least one real job run through the worker; a unit test of the job-selection logic is not evidence that the container path works.
- **Frontend** (`apps/web`): `npm run lint`, plus `npm run build` when the change touches imports, types, config, or anything the bundler resolves. `vite build` is the only type-level gate in this repo.
- **Database models or enums** (`packages/control_plane`): trace every consumer and confirm a migration exists under the service that owns the schema. A model field added without a migration passes tests and breaks the deployed stack.
- **Trading-critical paths** (risk engine, executor, monitor, order placement, WebSocket broadcasting): these need a regression test, per `AGENTS.md`. Never push a change here on inspection alone. Live-exchange checks run against OKX demo trading only, and never print credentials.
- **Docker, Compose, requirements, or image content**: rebuild the affected image (`./infra/compose/update.sh <service>`) and confirm the service comes up healthy. A `requirements.txt` edit that only passes locally proves nothing about the image.
- **Docs and comments only**: `git diff --check` and a read-through; skip the suites.

Do not repeat a check that already passed just because a commit or push follows.

## Full local rehearsal

Run the whole stack plus every suite only when the user asks, when diagnosing a failure that narrower runs cannot reproduce, or when the change spans the repository so broadly that no narrower set is credible.

## Protect history-rewriting pushes

Rebase is fine, including after review. Before a force push, fetch the current remote branch and record its exact OID, then publish with `--force-with-lease=<branch>:<observed-oid>` so a concurrent update aborts the push. Raw `--force` is never allowed. After any rewritten push, re-fetch heads and re-check review threads and CI — hashes and inline-comment anchors from before the rewrite are not current evidence.

## Handle failures

If a relevant check fails, stop and fix it or explain the blocker. Do not push and hope the deployed environment differs.

If a failure looks environment-specific, prove it: record the exact command, the failing test, and the specific mismatch; confirm the non-environmental evidence; prefer fixing the nondeterminism (see [ss-test-reliability](../ss-test-reliability/SKILL.md)) over documenting it.

## Push procedure

1. Run the selected checks once.
2. Commit with a Conventional Commit prefix and scope (`feat(api): ...`), per `AGENTS.md`.
3. Push, then verify the remote ref matches local `HEAD`:
   ```sh
   git rev-parse HEAD "origin/$(git branch --show-current)"
   ```
4. For a PR, state motivation, the exact commands run and their results, and attach UI or backtest captures for visible changes.

Report pending checks as pending. Inspect a failure before attributing it to the environment.
