<!-- Version: v1.0 -->
# Maa Protocol — Operational Runbook

> The single source of truth for operating the Mother Agent in production.

---

## What Is Maa Protocol?

Maa (Mother Agent) Protocol is the multi-agent orchestration layer for a Maa deployment. It governs how tasks enter, flow through child agents, get validated, and are delivered as finished output to the requesting user or operator.

**Key principle:** End users never see a timeout, a failure, or a placeholder as the final state. They receive either a validated result, or a specific honest escalation with a clear next step.

---

## Architecture at a Glance

```
User / Operator → [Any Channel] → Mother Agent → Child Agent Pool
                                              ↓
                                      Validation Gate
                                              ↓
                                      Completion Marker
                                              ↓
                                      Mother Agent validates
                                              ↓
                                      Delivered to requester
```

---

## Task Lifecycle

### Status Reference

| Status | Meaning | Requester Sees |
|---|---|---|
| `pending` | Task submitted, not yet started | Nothing |
| `queued` | At concurrency limit, waiting for slot | "Task queued" message |
| `running` | Child agent actively working | "Still working" if > 5 min |
| `completed` | Child agent finished, output written | Nothing (internal) |
| `validated` | Output passed validation gate | The finished output |
| `needs_revision` | Output failed validation | Alert with reasons |
| `circuit_open` | Error rate > 5%% for this label, spawning halted | Alert |
| `exhausted` | All 3 child attempts + Mother self-execution failed | Honest escalation |

### Standard Flow

```
pending → running → completed → validated → [output delivered]
                ↓
         needs_revision → pending (retry)
                ↓
           exhausted → escalation to requester
```

---

## How to Submit a Task

### Via CLI (inside workspace)

```bash
python3 ops/multi-agent-orchestrator/task_orchestrator.py submit <task_type> "<prompt>" [--output-dir DIR] [--run] [--validator-prompt "custom criteria"]
```

**Task types:**
- `market-brief` — Daily market report
- `research` — Deep research
- `email-draft` — Professional email drafting
- `growth-report` — Revenue/growth analysis

**Example:**
```bash
python3 ops/multi-agent-orchestrator/task_orchestrator.py submit research "What is the current outlook for Indian IT sector exports?" --run
```

### Via Telegram (direct message to Sneha)

Simply send the request in natural language. If the request triggers Maa protocol, Sneha will:
1. Classify the task type
2. Submit to the orchestrator
3. Monitor progress
4. Deliver the validated output

---

## Monitoring a Running Task

### Check status
```bash
python3 ops/multi-agent-orchestrator/task_orchestrator.py status <task_id>
```

### List all tasks
```bash
python3 ops/multi-agent-orchestrator/task_orchestrator.py list [--limit 20]
```

### Watch live logs
```bash
tail -f ops/multi-agent-orchestrator/logs/<task_id>.completion
```

### Progress signal files
For long-running tasks, the Mother Agent writes progress signals to:
```
ops/multi-agent-orchestrator/logs/<task_id>.progress
```
These are read by the parent session and surfaced as "still working" updates.

---

## Observability Dashboard

```bash
python3 ops/observability/maa_metrics.py dashboard      # ASCII dashboard
python3 ops/observability/maa_metrics.py summary       # Plain summary
python3 ops/observability/maa_metrics.py resources    # Live system resources
python3 ops/observability/maa_metrics.py summary --since 24  # Last 24h only
```

**Alert threshold:** If any single label's error rate exceeds 5% in 24h, the operator is alerted automatically.

---

## Self-Healing Checks

### Run health check manually
```bash
python3 scripts/health_check.py                # Human-readable
python3 scripts/health_check.py --json        # Machine-readable
python3 scripts/health_check.py --threshold 80 # Custom critical threshold
```

### Run cleanup manually
```bash
python3 scripts/auto_cleanup.py                # Default (7-day threshold)
python3 scripts/auto_cleanup.py --days 3       # Custom threshold
python3 scripts/auto_cleanup.py --dry-run      # Preview what would be removed
```

### Maintenance log
Every maintenance decision is logged to:
```
memory/maintenance_decisions/YYYY-MM-DD.jsonl
```

---

## Pre-Deploy Gate

Before any production deployment, run:
```bash
bash scripts/pre_deploy_gate.sh
```

This runs:
1. Trust regression test pack (51 tests)
2. Observability dashboard smoke
3. Disk health check

Exits 0 on pass, exits 1 on failure.

---

## Debugging a Failed Task

### Step 1: Check task state
```bash
python3 ops/multi-agent-orchestrator/task_orchestrator.py status <task_id>
```

Look for: `status`, `attempts`, `last_error`, `child_failure_reason`, `revision_reasons`

### Step 2: Check completion marker
```bash
cat ops/multi-agent-orchestrator/logs/<task_id>.completion
```

### Step 3: Check validation report
```bash
cat ops/multi-agent-orchestrator/logs/<task_id>.validation
```

### Step 4: Check observability errors
```bash
python3 ops/observability/maa_metrics.py summary --since 1
```

### Step 5: Check child agent session
```bash
openclaw session list
# then
openclaw session history <session_id>
```

---

## Escalation

When a task reaches `exhausted` status after the full failover chain, the requester receives a message with:
1. What was requested
2. What was attempted and why each attempt failed
3. What alternatives exist
4. What to do next

---

## Maintenance Schedule

| Action | Cadence | Command/Trigger |
|---|---|---|
| Health check | Every 4h | Cron: `0 */4 * * *` |
| Email pipeline | Every 1h | Cron: `0 * * * *` |
| Backup | Every 2h | Cron: `0 */2 * * *` |
| Pre-deploy gate | Before deployment | `bash scripts/pre_deploy_gate.sh` |
| Memory dedup | Weekly (manual) | `python3 scripts/memory_dedup.py` |
| Temp/data cleanup | Post-task + 7-day cron | `python3 scripts/auto_cleanup.py --days 7` |

---

## Key Files Reference

| File | Purpose |
|---|---|
| `ops/multi-agent-orchestrator/task_orchestrator.py` | Core runtime — task submission, spawn, validation, failover |
| `ops/multi-agent-orchestrator/GLOBAL_POLICY.md` | Binding rules for all agent work |
| `ops/multi-agent-orchestrator/NO_TIMEOUT_POLICY.md` | Zero user-facing timeout rule |
| `ops/multi-agent-orchestrator/SELF_HEALING_POLICY.md` | Self-healing and maintenance policy |
| `ops/observability/maa_metrics.py` | Observability CLI |
| `data/observability/maa_metrics.json` | Event store |
| `scripts/health_check.py` | Disk + resource probe |
| `scripts/auto_cleanup.py` | Aged file cleanup |
| `scripts/maintenance_logger.py` | Append-only JSONL logger |
| `scripts/pre_deploy_gate.sh` | Pre-deploy regression gate |
| `ops/multi-agent-orchestrator/tasks/` | Task state files |
| `ops/multi-agent-orchestrator/logs/` | Completion markers + validation reports |
| `agents/mother/agent/SOUL.md` | Mother Agent personality and principles |

---

## Rules in One Page

1. **No timeout errors ever** — child fails → respawn → self-execute → escalate
2. **Validate before delivery** — completeness, facts, format, quality, channel fit
3. **No fabricated completions** — output file + completion marker + validation gate
4. **Progress ping > 5 min** — send a "still working" update
5. **Escalation only when genuinely stuck** — with specific reason and next steps
6. **Pre-execution approval gate** — research → game plan → approval → execute
7. **Circuit breaker** — error rate > 5%% per label in 1h → halt spawning for that label
8. **Load shedding** — max 4 concurrent children; excess tasks queued and auto-drained
7. **Alert cooldown 2h** — same critical won't alert twice within 2 hours
8. **Disk ≥ 90%** — pause heavy tasks, alert the operator immediately
