<!-- Version: v1.0 -->
<!-- Last updated: 2026-04-22 by Maa maintainer -->
<!-- Phase: 11 of MAA Protocol Commercial Deployment Action Plan v1.2 -->

# Disaster Recovery — Multi-Agent Orchestrator
=============================================

## Overview

This document defines the backup strategy, restore procedure, corruption detection,
escalation path, and annual drill process for the Mother Agent Orchestrator (MAA).

**RPO Target: < 24 hours** — maximum acceptable data loss window.
**RTO Target: < 30 minutes** — maximum acceptable downtime window.

---

## Backup Targets

| Path | Description | Frequency | Retention |
|---|---|---|---|
| `data/observability/maa_metrics.json` | Core observability store | Daily | 90 days |
| `ops/multi-agent-orchestrator/tasks/` | Legacy/default task state files | Daily | 90 days |
| `ops/multi-agent-orchestrator/logs/` | Legacy/default orchestrator logs, completion markers | Daily | 90 days |
| `tenants/*/config/` | Per-tenant operator configs | Daily | 90 days |
| `tenants/*/tasks/` | Operator-scoped tenant task state | Daily | 90 days |
| `tenants/*/logs/` | Operator-scoped tenant logs/markers | Daily | 90 days |
| `tenants/*/outputs/` | Operator-scoped tenant outputs | Daily | 90 days |
| `tenants/*/clients/*/config/` | Per-client configs | Daily | 90 days |
| `tenants/*/clients/*/tasks/` | Client-scoped task state | Daily | 90 days |
| `tenants/*/clients/*/logs/` | Client-scoped logs/markers | Daily | 90 days |
| `tenants/*/clients/*/outputs/` | Client-scoped outputs | Daily | 90 days |

---

## Backup Schedule

```
CRON_TZ=Asia/Calcutta
0 2 * * *  python3 /root/.openclaw/workspace/scripts/disaster_recovery_backup.py
```

Runs daily at 02:00 IST. Archives are stored at `/archive/maa-backups/YYYY-MM-DD/`.

---

## Backup Naming Convention

```
/archive/maa-backups/YYYY-MM-DD/maa-state.tar.gz
```

Each backup is a `tar.gz` archive containing workspace-relative paths under:
```
maa-state/
  data/observability/
    maa_metrics.json
    task_dedup_registry.json
  ops/multi-agent-orchestrator/tasks/
    *.json
  ops/multi-agent-orchestrator/logs/
    *.json
    *.completion
    *.validation
    *.reflection
  tenants/
    {operator_id}/
      config/operator.json
      tasks/
      logs/
      outputs/
      clients/{client_id}/
        config/client.json
        tasks/
        logs/
        outputs/
```

---

## Retention Policy

- **Retention: 90 days**
- Auto-rotation: backup cron deletes archives older than 90 days
- Completion markers and validation reports are excluded from age-based deletion (audit trail)
- A marker file `maa-state/.backup_manifest.json` records backup metadata (timestamp, version, file count)

---

## Corruption Detection

On every restore attempt and during periodic health checks:

1. Load each `.json` file with `json.loads()` — if it raises `JSONDecodeError`, the file is corrupt.
2. On corruption detection:
   - Write a `.corrupt` marker alongside the corrupt file (e.g., `foo.json.corrupt`)
   - Do NOT overwrite the corrupt file with the backup copy
   - Log the corruption event to `logs/disaster_recovery_corruptions.log`
   - Include in the restore report

Corrupt files are never silently overwritten with backup data during normal restore.

---

## Restore Procedure

> ⚠️ **Stop all Mother Agent services before restoring.**
> This prevents active writes from conflicting with a restore operation.

### Step 1 — Stop services

```bash
# Stop the gateway/orchestrator crons and active sessions
openclaw gateway stop     # or ctrl-C all running openclaw processes
# Confirm no openclaw processes remain
ps aux | grep openclaw
```

### Step 2 — Identify the backup to restore

```bash
# Find the latest good backup
ls -t /archive/maa-backups/ | head -5

# Verify backup integrity before attempting restore
python3 /root/.openclaw/workspace/scripts/disaster_recovery_test.py
# Exits 0 if clean, exits 1 if corruption found
```

### Step 3 — Extract backup

```bash
BACKUP_DATE="2026-04-20"   # replace with actual date
BACKUP_DIR="/archive/maa-backups/${BACKUP_DATE}"
mkdir -p /tmp/maa-restore
tar -xzf "${BACKUP_DIR}/maa-state.tar.gz" -C /tmp/maa-restore/
```

### Step 4 — Verify JSON integrity of restored files

```bash
python3 /root/.openclaw/workspace/scripts/disaster_recovery_test.py --restore-dir /tmp/maa-restore/
```

Any corrupt files are reported with `.corrupt` markers written alongside them.
If any critical files (task state, metrics) are corrupt, escalate before proceeding.

### Step 5 — Restore individual components (selective restore)

> **NOTE:** The tar archive extracts to a `maa-state/` prefix, so paths inside the
> extracted directory look like `maa-state/data/observability/maa_metrics.json`
> (NOT `observability/maa_metrics.json` directly). The examples below use the
> correct extracted paths.

```bash
# Verify what was extracted — paths are prefixed with maa-state/
find /tmp/maa-restore -type f | head -20

# Restore metrics store (overwrite current)
cp /tmp/maa-restore/maa-state/data/observability/maa_metrics.json \
   /root/.openclaw/workspace/data/observability/maa_metrics.json

# Restore specific tenant config
cp /tmp/maa-restore/maa-state/tenants/{operator_id}/config/operator.json \
   /root/.openclaw/workspace/tenants/{operator_id}/config/operator.json

# Task state files — restore individually to avoid disrupting active tasks
# Only restore tasks with status in {exhausted, completed} unless explicitly directed
```

### Step 6 — Restart services

```bash
# Restart gateway
openclaw gateway start

# Restart scheduled cron jobs
crontab -l | grep disaster_recovery
# If not present, add:
# CRON_TZ=Asia/Calcutta 0 2 * * * python3 /root/.openclaw/workspace/scripts/disaster_recovery_backup.py
```

### Step 7 — Post-restore verification

```bash
# Run health monitor to verify restored state
python3 /root/.openclaw/workspace/scripts/continuous_health_monitor.py

# Run pre-deploy gate
bash /root/.openclaw/workspace/scripts/pre_deploy_gate.sh
```

---

## Full Disaster Restore (Last Resort)

If the entire state is lost or destroyed:

1. Stop all services (Step 1)
2. Identify last good backup (Step 2)
3. Extract to a fresh directory (Step 3)
4. Run integrity test — if clean, proceed (Step 4)
5. Rename old state dirs as `_pre_disaster_YYYY-MM-DD`
   ```bash
   mv /root/.openclaw/workspace/data/observability \
      /root/.openclaw/workspace/data/observability_pre_disaster_$(date +%Y-%m-%d)
   mv /root/.openclaw/workspace/ops/multi-agent-orchestrator/tasks \
      /root/.openclaw/workspace/ops/multi-agent-orchestrator/tasks_pre_disaster_$(date +%Y-%m-%d)
   ```
6. Move restored state into place
   ```bash
   mv /tmp/maa-restore/maa-state/data/observability /root/.openclaw/workspace/data/observability
   mv /tmp/maa-restore/maa-state/ops/multi-agent-orchestrator/tasks /root/.openclaw/workspace/ops/multi-agent-orchestrator/tasks
   mv /tmp/maa-restore/maa-state/ops/multi-agent-orchestrator/logs /root/.openclaw/workspace/ops/multi-agent-orchestrator/logs
   # Restore tenant-scoped state as needed
   cp -R /tmp/maa-restore/maa-state/tenants /root/.openclaw/workspace/
   ```
7. Restart services (Step 6)
8. Post-restore verification (Step 7)

---

## Escalation Path

| Situation | Action |
|---|---|
| Backup fails to run | Alert via continuous_health_monitor, notify the operator via the configured alert channel |
| Corruption detected on restore | Do not proceed; notify the operator immediately with details |
| RTO exceeded (>30 min) | Escalate to the operator with a status update |
| RTO exceeded (>2h) | Escalate to the operator with recovery alternatives |
| Full data loss event | The operator decides on restore vs. fresh start |

Escalation via the configured alert channel:
```
🚨 MAA DISASTER RECOVERY — [brief description]
Backup: {date}
Status: {affected files / action taken}
Next step: {what is happening now}
```

---

## Annual Disaster Recovery Drill

**Schedule:** Every January (first week), conducted as a scheduled maintenance window.

### Drill Procedure

1. **Notify the operator** — announce drill start, expected duration, no service impact expected.
2. **Create isolated test restore dir** (not the live paths)
   ```bash
   DRILL_DIR="/tmp/maa-drill-$(date +%Y-%m-%d)"
   mkdir -p "$DRILL_DIR"
   ```
3. **Extract latest backup to test dir**
   ```bash
   tar -xzf "$(ls -t /archive/maa-backups/*/maa-state.tar.gz | head -1)" -C "$DRILL_DIR/"
   ```
4. **Run integrity check**
   ```bash
   python3 /root/.openclaw/workspace/scripts/disaster_recovery_test.py --restore-dir "$DRILL_DIR"
   ```
5. **Verify task state restoreability** — count active vs. terminal task records
6. **Measure restore time** — record start/end timestamps, report RTO estimate
7. **Report results to the operator**:
   ```
   📋 MAA DR Drill Results — {date}
   Backup used: {date}
   Files checked: N
   Corrupt files: 0 (or list if any)
   RTO estimate: {X} minutes
   Outcome: ✅ PASS / ❌ FAIL
   ```
8. **Clean up test restore dir**
   ```bash
   rm -rf "$DRILL_DIR"
   ```
9. **Log drill outcome** to `logs/disaster_recovery_drill_log.json`

### Drill Failure Criteria

- Any critical file (task state, metrics) is corrupt in the backup
- RTO estimate exceeds 30 minutes
- Restore procedure documentation is incomplete or inaccurate
- Corruption detection missed files that should have been flagged

Any failure must be followed by a corrective action (documentation fix, backup script fix, or process fix) within 1 week.

---

## Backup Verification (Automated)

The `disaster_recovery_test.py` script verifies:
1. JSON integrity for all restored `.json` files
2. Presence of all critical backup targets
3. Reports file count, corruption count, RPO/RTO estimates

Run manually or as part of the drill:
```bash
python3 /root/.openclaw/workspace/scripts/disaster_recovery_test.py
```

---

## Self-Hoster Notes

For self-hosted deployments (VPS/workstation/laptop):

- Store backups on a different volume or machine than the live data
- The `disaster_recovery_backup.py` script supports `--remote-dest` for rsync to remote storage
- Test restores on a non-production machine quarterly minimum
- Ensure the backup destination has sufficient free space (budget ~5 GB per month per tenant)

---

*Document version: v1.0 | Last reviewed: 2026-04-22*
