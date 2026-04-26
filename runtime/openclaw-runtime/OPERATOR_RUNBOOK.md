# MAA PROTOCOL — OPERATOR RUNBOOK
Version: v1.0
Effective: 2026-04-22
Owner: Maa operator / Mother Agent

> Everything an operator needs to run and troubleshoot Maa without the original deployer present.

---

## QUICK STATUS CHECK (do this first)

```bash
# One-line system health
python3 ops/observability/maa_metrics.py dashboard

# Pre-deploy gate result
python3 ops/multi-agent-orchestrator/task_orchestrator.py gate-status
```

---

## COMMON OPERATIONS

### How to check if MAA is healthy

```bash
python3 ops/observability/maa_metrics.py dashboard
```

Look for:
- ✅ MAA OK — system is healthy
- ⚠️ MAA DEGRADED — one or more labels have elevated error rate; check Recent Errors
- 🔴 MAA CRITICAL — metrics store unwritable or system health check failed

---

### How to check running tasks

```bash
# List all tasks (newest first)
python3 ops/multi-agent-orchestrator/task_orchestrator.py list --limit 10

# Check a specific task
python3 ops/multi-agent-orchestrator/task_orchestrator.py status <task_id>
```

---

### How to submit a task manually

```bash
python3 ops/multi-agent-orchestrator/task_orchestrator.py submit <task_type> "<prompt>" --run
```

**Task types:** `market-brief`, `research`, `email-draft`, `growth-report`, `custom`

**Example:**
```bash
python3 ops/multi-agent-orchestrator/task_orchestrator.py submit research "What is the current outlook for Indian IT sector exports?" --run
```

---

### How to check progress on a running task

```bash
# Read the progress log
cat ops/multi-agent-orchestrator/logs/<task_id>.progress

# Check task state
python3 ops/multi-agent-orchestrator/task_orchestrator.py status <task_id>
```

---

## WHAT TO DO IF...

### A task is stuck (status = running for > 20 minutes)

1. Check the progress log:
```bash
cat ops/multi-agent-orchestrator/logs/<task_id>.progress
```

2. Check if child agents are still running:
```bash
cat ops/multi-agent-orchestrator/logs/running_children.json
```

3. If child has stalled but no progress file exists — the child may have crashed silently:
   - Mother self-execution will trigger automatically after 3 failed child attempts
   - Wait for escalation or check task status again in 5 minutes

4. If you need to force-exhaust and escalate immediately:
   - Edit the task state file: set `"status": "exhausted"` and `"child_exhausted": true`
   - The system will treat it as an escalation

---

### Pre-deploy gate fails

1. Check what failed:
```bash
cat logs/pre_deploy_gate_latest.json
```

2. Run tests directly to see failures:
```bash
python3 ops/multi-agent-orchestrator/tests/test_trust_fixes.py 2>&1 | grep FAIL
bash scripts/pre_deploy_gate.sh 2>&1 | grep FAIL
```

3. Most failures are caused by:
   - Metrics store corruption → run `python3 scripts/auto_cleanup.py --days 3` and retry
   - Missing template files → check `agents/templates/*/v1.0.md` exist
   - Stale running children → run `python3 scripts/continuous_health_monitor.py` to reconcile

4. If gate keeps failing after cleanup, contact the system maintainer

---

### Circuit breaker has tripped (label = circuit_open)

This is normal self-protection. It means >5% error rate on that task type in the rolling 1-hour window.

1. Check which label is affected:
```bash
python3 ops/observability/maa_metrics.py dashboard
```

2. Check Recent Errors to understand what failed

3. The circuit breaker resets automatically when the rolling window expires and error rate drops below 5%

4. If you need to manually reset immediately (not recommended unless you know the root cause is fixed):
   - Edit `ops/multi-agent-orchestrator/task_orchestrator.py` — find `_circuit_state` dict and clear it
   - Or restart the gateway: `openclaw gateway restart`

---

### Continuous health monitor finds a critical issue

1. Check the alert file:
```bash
cat ops/multi-agent-orchestrator/logs/continuous_health_monitor_alerts.json
```

2. Common critical issues and fixes:

   **metrics_writable = fail:**
   ```bash
   python3 scripts/auto_cleanup.py --days 1
   # Then verify:
   python3 scripts/continuous_health_monitor.py
   ```

   **task_states_valid = fail:**
   - A task state JSON is corrupted. Check the error message for which file.
   - If only one task is corrupted, you can safely move it to `archive/`

   **completion_markers = missing:**
   - For a completed/validated task, completion markers should exist
   - If the task output is already delivered, create an empty completion marker:
   ```bash
   touch ops/multi-agent-orchestrator/logs/<task_id>.completion
   ```

   **state_version_integrity = fail:**
   - This means a task's attempt_history has a regression (newer attempt has lower state_version than an older one)
   - Rare; usually means two tasks wrote to the same state file. Contact the system maintainer.

---

### Disk is at or above 90%

1. Run cleanup:
```bash
python3 scripts/auto_cleanup.py --days 3
```

2. Check what's using space:
```bash
du -sh /root/.openclaw/workspace/*/ | sort -h | tail -20
```

3. Archive old reports:
```bash
mv data/reports/2026-01-* archive/
```

4. If disk keeps filling, the metrics store may be growing unbounded — run:
```bash
python3 scripts/auto_cleanup.py --days 1
```

---

### A tenant is exceeding their rate limit

```bash
# Check tenant usage
python3 ops/multi-agent-orchestrator/tenant_crud.py usage <operator_id> <client_id> --since 24
```

To adjust limits:
```bash
python3 ops/multi-agent-orchestrator/tenant_crud.py update-client <operator_id> <client_id> --max-tasks-per-hour 100
```

To deactivate a tenant immediately:
```bash
python3 ops/multi-agent-orchestrator/tenant_crud.py deactivate-client <operator_id> <client_id>
```

---

### You need to approve an external action (email send, calendar write, public post)

The approval gate will surface the request to you automatically. You will receive a message with:
- What action is requested
- Who is requesting it
- What the target is
- Body summary

Reply with `APPROVE`, `APPROVE TO SEND`, or `SEND NOW` to authorize.
Reply with `REJECT` or ignore to deny.

---

## DAILY OPERATOR CHECKLIST

- [ ] Run dashboard: `python3 ops/observability/maa_metrics.py dashboard`
- [ ] Check gate status: `python3 ops/multi-agent-orchestrator/task_orchestrator.py gate-status`
- [ ] Review any escalated or exhausted tasks
- [ ] Check continuous health monitor log if any alerts fired:
```bash
cat ops/multi-agent-orchestrator/logs/continuous_health_monitor_alerts.json
```

---

## EMERGENCY CONTACTS

| Scenario | Action |
|---|---|
| MAA completely unresponsive | `openclaw gateway restart` |
| Disk full, cleanup doesn't help | Move archive/ files to external storage |
| Metrics store corrupted | `python3 scripts/auto_cleanup.py --days 0` then retry |
| Tenant data breach suspected | Deactivate tenant immediately, contact the system maintainer |

**The system maintainer should always be reachable** via the active support path configured for the deployment. For urgent issues, use the deployment's primary escalation channel.

---

## REFERENCE: KEY FILES

| File | Purpose |
|---|---|
| `ops/multi-agent-orchestrator/task_orchestrator.py` | Primary engine |
| `ops/observability/maa_metrics.py` | Metrics + dashboard |
| `ops/multi-agent-orchestrator/GLOBAL_POLICY.md` | Binding operational rules |
| `ops/multi-agent-orchestrator/NO_TIMEOUT_POLICY.md` | No timeout guarantee |
| `ops/multi-agent-orchestrator/SELF_HEALING_POLICY.md` | Self-maintenance rules |
| `ops/multi-agent-orchestrator/SLA.md` | This system's SLA |
| `scripts/health_check.py` | Disk/CPU/memory probe |
| `scripts/auto_cleanup.py` | Aged file cleanup |
| `scripts/continuous_health_monitor.py` | 15-min regression monitor |
| `logs/pre_deploy_gate_latest.json` | Last gate result |
| `ops/multi-agent-orchestrator/logs/continuous_health_monitor_alerts.json` | Critical alerts |

---

*Document owner: Mother Agent | Maa deployment*
