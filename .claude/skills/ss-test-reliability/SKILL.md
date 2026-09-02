---
name: ss-test-reliability
description: Design, review, and diagnose stratsmith tests and fixtures that can fail nondeterministically — shared Postgres/Redis state, Docker Compose services, host ports, asyncio tasks, event loops, clocks, module-global singletons, subprocesses, and unawaited teardown. Use when adding or changing tests with those risks, investigating a flaky test, or reviewing test isolation; use ss-pre-push-checks separately to select which commands to run.
---

# Reliable stratsmith tests

Build tests that stay correct when the whole suite runs against a live Compose stack, not only when run alone on a quiet machine. This skill owns isolation and reliability decisions; it does not decide which tests to run for a push.

## Model the execution topology

Assume these layers overlap unless the configuration proves otherwise:

1. Tests in one file, sharing module-level fixtures and an event loop.
2. Separate files in one `pytest` process (`-p xdist` workers when used).
3. Independent `pytest` processes (a package suite and `services/api` integration suite).
4. Tests and the running Compose stack (`api`, `worker`, `postgres`, `redis`) touching the same database rows, Redis keys, and job queue.

Process isolation does not isolate Postgres rows, Redis keys and pub/sub channels, host ports, predictable filesystem paths, spawned Docker containers, or the OKX demo account. For every acquired resource name its owner, atomic allocation mechanism, observable readiness signal, registered cleanup, and quiescent completion signal.

Do not serialize a whole suite because one fixture lacks isolation. Narrow the exclusive scope or change how the resource is allocated first — a serial marker cannot protect a shared Redis key from another process.

## Allocate resources atomically

Use the owner's allocator instead of checking availability and claiming it later.

- Bind sockets with port `0` and read the assigned port only after the server reports listening. Never scan for a free port and bind it later.
- Use `tmp_path` / `tempfile.mkdtemp` for per-test roots; never a predictable shared path under `/tmp`.
- Namespace shared state per test: Redis key prefixes, pub/sub channel names, `Strategy`/`Job` rows, Docker container names, and output paths. Prefer a transaction rolled back in teardown, or a per-test schema, over `DELETE FROM` sweeps that race other tests.
- Keep stable recorded identifiers separate from ephemeral addresses; translate inside the fixture rather than forcing a live resource onto a recorded value.

Literal paths, URLs and symbols used only as parser inputs or expected values are not acquired resources — do not rewrite them because they look fixed.

## Contain process-global state

Treat `os.environ`, the working directory, `freezegun`/fake clocks, locale and timezone, `unittest.mock.patch` targets, module-level singletons and caches (engines, session factories, provider caches, registries), logging handlers, and the running event loop as exclusive mutable resources.

Prefer injecting a dependency or building an instance-local adapter. When mutation is required:

- capture whether the original value was absent or present, and restore that exact state;
- register restoration immediately (`monkeypatch`, a fixture `finally`, `addfinalizer`);
- wrap the smallest mutation scope in `try/finally`, keeping a fixture-level fallback when a failure before the local `finally` is plausible;
- patch the narrowest exact target the fixture owns — patch where the name is *used*, not where it is defined.

The data-provider caches are process-global by construction: a test that populates one must clear or namespace it, or the next test reads a cached response it never requested.

## Synchronize on state, not on sleep

A fixed `asyncio.sleep` is not evidence that setup completed or cleanup settled.

- Wait for an explicit readiness signal: a health endpoint, a job status transition, a pub/sub message, an `asyncio.Event`, a container's log line, an owned future.
- Use `asyncio.Event`/barriers to place a race at a deterministic point and prove two operations actually overlap.
- Use a timeout only to bound a wait, never as the condition that makes the assertion correct.
- Do not assert scheduler-dependent ordering unless that ordering is the behavior under test.
- When time itself is the subject, inject or fake the clock and always restore it.

Poll with a bounded loop on an observable condition (`until deadline: check; await sleep(0.05)`) rather than one long sleep.

## Budget timeouts against the lane

A per-test timeout overrides the suite default rather than yielding to it, so a value below the configured budget silently lowers what the lane granted. `services/api/pytest.ini` sets `timeout = 300` for integration tests that spawn containers; a tighter per-test value must carry the reason it is tighter. Raise fixture budgets with test budgets — setup and teardown pay the same contention, so lifting only the test budget moves a contended failure into teardown.

Where a timeout is the subject, keep the outer wait far larger than the timeout under test.

## Dispose to quiescence

Register cleanup immediately after acquisition so an assertion failure still releases the resource. Cleanup cancels tasks *and awaits them*, closes sessions and engines, unsubscribes pub/sub, removes spawned containers, and waits for subprocess exit.

Calling `task.cancel()`, `client.close()` or `container.kill()` without awaiting the completion signal is incomplete teardown. `asyncio` warns about pending tasks at loop close for a reason: an unawaited cancel can still mutate the database after the next test starts.

## Prove the intended regression

- Watch an ordinary regression fail before the fix when practical.
- For a new guard or validation rule, temporarily introduce the rejected case and confirm the intended failure.
- For a race, use barriers to prove overlap; repeating a test many times is not a race test.
- For ports, Redis keys, database rows, or containers, run two independent `pytest` processes concurrently when cross-process isolation is part of the fix.
- Assert on external state — rows, Redis contents, emitted WebSocket messages, exchange order state, logs, exit codes — not on a component's self-report.

## Reject flake-masking fixes

Do not present these as root-cause fixes for a deterministic local test:

- raising a timeout without naming the awaited state;
- adding retries or `flaky` markers;
- making the whole suite serial;
- swallowing an exception or an unhandled task exception;
- weakening an assertion or normalizing away unstable behavior;
- adding a sleep before cleanup or assertion.

Retries stay valid at a genuine external boundary — a live OKX or market-data endpoint. Keep the exception there.

Restoring a budget is not masking: returning a suite to the timeout the lane already granted, or sizing a bounded retry to contention actually measured, names the awaited work instead of inventing headroom.

## Diagnose an existing flake

Reproduce the topology, not the test: run the full owning suite (and a second concurrent process when a shared resource is suspected), not the single test. Collect the exact failing assertion, the ordering of tests before it, and the state of the shared resource at failure. A diagnosis-only request stays read-only — report cause and evidence unless the user also asks for a fix.

## Validate and report

Run the smallest focused regression for the affected behavior, then add topology-specific evidence only when the change owns that risk: global mutation needs restoration evidence; task/subprocess/container work needs quiescent-teardown evidence; shared Postgres, Redis, ports, or paths need concurrent independent-process evidence; a new guard needs a negative control.

Report exact commands and observed results. Never describe retries, skipped tests, or a pending run as passing.
