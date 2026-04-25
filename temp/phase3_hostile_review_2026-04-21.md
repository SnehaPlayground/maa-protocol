# Phase 3 hostile review notes — 2026-04-21

## Verdict
Not review-clean. Phase 3 should **not** be marked complete in progress.txt yet.

## What I verified
- `task_orchestrator.py` compiles.
- Module imports and auto-starts a background poller.
- `test_phase2_runtime.py` still passes: 42/42.
- `test_trust_fixes.py` remains 60/71, same as before.
- Canonical payload fields exist in `_deliver_progress_update()`.

## Critical findings

### 1) Tenant-scoped running tasks are invisible to the new poller
`_scan_and_ping()` only scans `TASKS_DIR` (legacy default path):
- function lines ~1468-1472
- it does **not** scan `tenants/{operator}/clients/{client}/tasks/`

I verified this directly:
- a default running task produced `logs/review-default-running.progress`
- an equivalent tenant-scoped running task produced **no** progress signal

Impact:
- Phase 3 is not actually transport-agnostic across the multi-tenant architecture
- tenant tasks can run silently forever from the poller’s perspective
- this directly conflicts with the broader architecture and Phase 6 tenancy work

### 2) `_deliver_progress_update()` is not tenant-aware
It always reads/writes using legacy default paths:
- state file: `f"{TASKS_DIR}/{task_id}.json"`
- progress file: `f"{LOGS_DIR}/{task_id}.progress"`

Impact:
- even if the poller later found tenant tasks, delivery would still fail for tenant-scoped task state
- current implementation is hard-wired to legacy storage layout

### 3) Poller starts at module import time, not only runtime execution boundaries
Top-level calls currently include:
- `_reconcile_running_children()`
- `_mark_stale_running_tasks()`
- `start_progress_poller()`

Impact:
- every import of `task_orchestrator.py` starts a daemon thread
- tests/importers get background side effects they did not ask for
- this is operationally risky and violates clean import semantics
- it already prints noisy startup output during tests

This may not break functionality immediately, but it is bad runtime hygiene.

### 4) `progress.txt` is currently inaccurate about the test story
Current `progress.txt` says:
- `test_trust_fixes.py → 60/71 (11 failures = Phase 3 features not built)`

That statement is no longer accurate.
The 11 failures are **not** "Phase 3 features not built". They are mostly:
- suspicious short-output test mismatch
- circuit breaker missing
- load shedding queue missing
- mother self-execution missing

So `progress.txt` definitely needs correction, not a simple upgrade.

### 5) Trust test coverage for Phase 3 is still too shallow
`test_progress_ping()` only checks string presence:
- constants exist
- function names exist
- threading appears in file
- `.progress` appears in code

It does **not** validate:
- tenant-scoped polling
- second ping at 10 minutes
- dedup correctness in live state
- canonical payload fields
- import-time side effects

Impact:
- current green signal for Phase 3 is overstated

## Non-blocking observations
- `_send_progress_update(..., channel="telegram")` still carries a Telegram-specific parameter name even though it is unused. Not a functional bug, but muddy for a "transport-agnostic" claim.
- progress ping timing uses `updated_at` / `mother_self_exec_at` / `created_at`, not a dedicated `task_started_at`. This is acceptable but semantically imprecise if future code updates `updated_at` for unrelated reasons.

## Conclusion
Phase 3 has meaningful progress, but after hostile review it is **not complete enough to mark as satisfied**.

Minimum blockers before updating progress.txt as complete:
1. make `_scan_and_ping()` scan tenant-scoped task paths
2. make `_deliver_progress_update()` resolve tenant-aware task/log paths
3. stop starting the poller on plain import, or make startup behavior explicit/safe
4. correct `progress.txt` test-status language
5. add real Phase 3 regression tests for tenant paths + second ping + payload fields
