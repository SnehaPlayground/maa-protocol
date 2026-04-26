<!-- Version: v1.0 -->
# Mother Agent — Self-Healing & Memory Metabolism Policy

## Purpose

Keep Maa Protocol healthy between tasks — proactively monitor disk/resource pressure, clean aged temp files, deduplicate stale memory fragments, and log every maintenance action with an audit trail.

This policy is additive. It does not override the no-timeout policy, failover chain, or approval gate.

---

## Health Check Triggers

### 1. Pre-task Health Check
Before every Mother Agent task submission:
- Run `python3 /root/.openclaw/workspace/scripts/health_check.py --json`
- Evaluate disk usage:
  - **< 75%** → proceed normally
  - **75–84.9%** → log `warn`, proceed
  - **85–89.9%** → run `auto_cleanup.py`, then proceed
  - **≥ 90%** → log `critical`, pause new heavy tasks, alert the operator

### 2. Periodic Health Check
Recommended cron cadence:
```bash
0 */4 * * * python3 /root/.openclaw/workspace/scripts/health_check.py --json
```
Every 4 hours, check disk, CPU, and memory. Only surface to the operator when status is `critical` or cleanup materially changes system state.

### 3. Post-task Cleanup
After every task completes:
- Remove temporary files older than 24h from task-specific working dirs
- Leave validated outputs, completion markers, and final reports only

---

## Cleanup Scope

### Target directories
- `/root/.openclaw/workspace/temp/`
- `/root/.openclaw/workspace/data/email/`
- `/root/.openclaw/workspace/data/reports/`
- `/root/.openclaw/workspace/data/transcripts/`

### Never delete
- `AGENTS.md`, `SOUL.md`, `MEMORY.md`, `SECURITY.md`, `USER.md`, `IDENTITY.md`
- Anything in `ops/multi-agent-orchestrator/tasks/`
- Completion markers (`*.completion`)
- Validation reports (`*.validation`)
- Active state JSON files
- Any file modified in the last 24 hours (even if in temp/)

---

## Memory Metabolism (M3)

### Exact Deduplication Only
- Scan `memory/*.md` for exact duplicate full-file content
- Keep the newest file
- Archive older duplicates as `.bak`
- Log every deduplication decision to `memory/maintenance_decisions/{date}.jsonl`

### Explicit Non-Goal
- **Do not auto-summarize or distill memory files via LLM**
- Any memory compression beyond exact deduplication requires explicit operator approval

---

## Decision Logging

Every maintenance action must be logged with:
- `timestamp`
- `action` (e.g. `disk_check`, `cleanup`, `memory_dedup`)
- `outcome` (`ok`, `warn`, `critical`, `removed`, `skipped`)
- `details` (JSON payload: disk %, files removed, bytes freed, etc.)

Log destination:
- `memory/maintenance_decisions/YYYY-MM-DD.jsonl`

---

## Escalation Rules

Alert the operator immediately when:
- Disk usage reaches **90%+** after cleanup attempt
- Cleanup script fails on a critical path
- Resource health check returns `critical`
- Memory dedup finds conflicting duplicates that cannot be auto-resolved safely

Do **not** alert the operator for routine `warn` thresholds or ordinary aged-file cleanup unless the cleanup materially changed the system state or removed unexpected files.

---

## Implementation Files

| File | Role |
|---|---|
| `scripts/health_check.py` | Disk + resource probe |
| `scripts/auto_cleanup.py` | Aged temp/data cleanup |
| `scripts/maintenance_logger.py` | Append-only JSONL decision log |
| `scripts/memory_dedup.py` | Exact duplicate memory detection (future) |
| `ops/multi-agent-orchestrator/SELF_HEALING_POLICY.md` | This policy |

---

## Operational Rule

Self-healing is part of task quality, not an optional background hobby.
A clean workspace, low disk pressure, and a durable audit trail are part of Maa Protocol reliability.
