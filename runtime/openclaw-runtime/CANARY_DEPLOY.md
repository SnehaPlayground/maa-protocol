# Canary Deployment — Action Spec
Version: v1.0
Last Updated: 2026-04-23
Author: Maa maintainer
Phase: 12 of MAA Protocol Commercial Deployment Action Plan v1.2

---

## Overview

Canary deployment routes a deterministic 10% of new tasks to an experimental
(canary) version of the MAA orchestrator while the remaining 90% continue on
the stable version. Error rates are monitored over a 24-hour window; the
canary is auto-promoted if error rate < 5% and auto-reverted if ≥ 5%.

---

## What "Canary" Means Here

Full binary-executable isolation (separate Python process per variant) would
require process-level sandboxing and is not implemented. Instead, this
implementation achieves **template-level isolation**:

- Canary tasks receive a different sub-agent template (`canary.md` instead of
  `v1.0.md`) with explicit canary branding and heightened monitoring notes
- The child prompt is prepended with `CANARY BUILD {version}` marker at spawn
- `canary_version` is recorded in task output metadata for traceability
- Canary traffic is deterministic (hash-based) so it is reproducible

This is meaningful behavioral isolation at the sub-agent template layer,
distinct from pure observability-only routing (where routing is recorded but
does not affect execution).

---

## Canary Router

**Module**: `ops/multi-agent-orchestrator/canary_router.py`

### `is_canary_deployed() → bool`
Returns `True` if `.canary_version` marker file exists.

### `get_canary_version() → str`
Returns the current canary version string from the marker file, or `""` if none.

### `get_stable_version() → str`
Returns stable version from `.stable_version` marker or `task_orchestrator.py`
`VERSION` constant.

### `route_to_canary(task_id: str) → bool`
Deterministic 10% sampling: `hash(task_id) mod 10 == 0` → canary.
Returns `False` if no canary is deployed.

### `canary_error_rate(window_h=24) → (float, dict)`
Computes error rate for canary tasks over the given window.
Returns `(error_rate, stats_dict)`.

### `check_and_decide() → int`
Auto-check entry point. Returns: `0`=promoted, `1`=reverted, `2`=monitoring open.

---

## Marker Files

| File | Location | Purpose |
|---|---|---|
| `.canary_version` | `ops/multi-agent-orchestrator/.canary_version` | Canary version string (e.g. `v1.1`). Presence means canary is **deployed**. |
| `.stable_version` | `ops/multi-agent-orchestrator/.stable_version` | Stable version string (written on promote or manually). |

Written by: `canary_router.py` and `scripts/canary_deploy.py`

---

## Canary Template

**File**: `agents/templates/researcher/canary.md`

A variant of the stable `v1.0.md` template with:
- Explicit `CANARY BUILD` header marker in the child prompt
- `Version: canary-v1` in the template doc
- Heightened monitoring notes (canary_extra success criterion)
- Same pillars, gates, and tool permissions as stable template

Only loaded when **both** conditions are true:
1. `task["canary_routed"] == True` (task was in the 10% canary sample)
2. `is_canary_deployed() == True` (marker file exists)

Otherwise the stable `v1.0.md` is used (or inline harness if template missing).

---

## Runtime Branching Flow

```
submit_task()
  └─ route_to_canary(task_id)  → sets task["canary_routed"] + task["canary_version"]
       └─ (only written to state, no behavioral change yet)

run_task_chain()
  └─ spawn_child_agent()
       └─ reads task["canary_routed"]
       └─ is_canary_deployed() → True?
            ├─ YES + canary_routed → load canary.md template + CANARY BUILD marker
            └─ NO or not routed    → load stable v1.0.md template (existing behavior)
       └─ harness_template_version = "canary-v1" or "v1.0" or "inline"
       └─ task["canary_version"] recorded in metadata after spawn
```

---

## Deploy Commands

### Deploy a new canary

```bash
python3 scripts/canary_deploy.py deploy v1.1
# writes v1.1 to .canary_version
# clears canary error log
# sends Telegram notification
# exit 0
```

### Check status

```bash
python3 scripts/canary_deploy.py status
# shows stable/canary version, routing %, 24h error rate
```

### Manual promote

```bash
python3 scripts/canary_deploy.py promote
# copies canary version → stable marker
# updates task_orchestrator.py VERSION
# clears canary marker
# sends Telegram notification
# exit 0
```

### Manual revert

```bash
python3 scripts/canary_deploy.py revert
# clears canary marker
# restores stable VERSION in task_orchestrator.py
# sends Telegram notification
# exit 1
```

### Auto check (for cron)

```bash
python3 scripts/canary_deploy.py check
# computes error rate over 24h window
# auto-promotes if < 5%, auto-reverts if ≥ 5%
# exit 0=promoted, 1=reverted, 2=monitoring window open
```

---

## Verification Test

```bash
# 1. Deploy canary v1.1
python3 scripts/canary_deploy.py deploy v1.1

# 2. Verify routing is active
python3 -c "
from ops.multi_agent_orchestrator.canary_router import route_to_canary
print([route_to_canary(f't{i}') for i in range(20)])
"
# Expect ~2 Trues in 20 (10%)

# 3. Submit 5 research tasks
for i in 1 2 3 4 5; do
  python3 ops/multi-agent-orchestrator/task_orchestrator.py submit research "test query $i"
done

# 4. Check that ~10% have canary_routed=True in their state files
# 5. Revert when done
python3 scripts/canary_deploy.py revert
```

---

## Error Rate Computation

Error rate is computed from `data/observability/maa_metrics.json` (the `tasks`
bucket) over a 24-hour rolling window. Only tasks with `status` in
`["exhausted", "failed"]` count as errors.

Minimum sample size: 5 tasks before a promote/revert decision is made.

---

## Telegram Notifications

Sent to `telegram:6483160` on:
- Canary deploy (with version and monitoring window)
- Canary promote (with new stable version)
- Canary revert (with reason)
- Auto-promote/revert via cron check

---

*Document version: v1.0 | Last reviewed: 2026-04-23*
