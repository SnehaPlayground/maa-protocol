<!-- Version: v1.0 -->
<!-- Last updated: 2026-04-22 by Maa maintainer -->
<!-- Phase: 12 of MAA Protocol Commercial Deployment Action Plan v1.2 -->

# VERSIONING — MAA Protocol Release Management
================================================

## Overview

This document defines the versioning policy, release process, rollback procedure,
and canary deployment strategy for the Mother Agent Orchestrator (MAA).

**Current version: v1.0**

---

## Version Format

```
vMAJOR.MINOR
```

- **MAJOR**: Breaking changes — new API, removed fields, modified behavior
- **MINOR**: Additive changes — new features, new fields, backward-compatible enhancements

Examples: `v1.0`, `v1.1`, `v2.0`

---

## Where Version Is Defined

| File | Location | Purpose |
|---|---|---|
| `task_orchestrator.py` | `VERSION = "v1.0"` (first constant after shebang) | Runtime version |
| All `.md` docs | `<!-- Version: v1.0 -->` as first line | Doc version |
| Backup manifest | `"version": "v1.0"` | Backup metadata |

---

## Release Process

### Pre-Release Checklist

Before tagging a new version:

- [ ] Run full pre-deploy gate: `bash scripts/pre_deploy_gate.sh`
- [ ] Run continuous health monitor: `python3 scripts/continuous_health_monitor.py`
- [ ] All existing tests pass
- [ ] No outstanding critical alerts
- [ ] Backup is confirmed clean: `python3 scripts/disaster_recovery_test.py`
- [ ] The operator has been briefed on changes

### Tagging a Release

```bash
cd /root/.openclaw/workspace
# Update VERSION in task_orchestrator.py
# Update <!-- Version: --> in all modified .md files
# Commit with message: "Release v1.X — changelog summary"
git add -A
git commit -m "Release v1.X — changelog summary"
git tag -a v1.X -m "MAA Protocol v1.X — release notes"
```

### Post-Release Actions

1. Trigger full backup: `python3 scripts/disaster_recovery_backup.py`
2. Run health monitor to confirm all systems nominal
3. Notify the operator via the configured release channel with a release summary

---

## Canary Deployment

### When to Use Canary

- Any change to `task_orchestrator.py` that affects child agent behavior
- Any change to `tenant_gate.py` that affects task acceptance logic
- Any change to core runtime paths or state management

### Canary Process

See `scripts/canary_deploy.py` for the full automated canary workflow.

Summary:
1. Mark current stable version as `vSTABLE`
2. Deploy new version as `vCANARY`
3. Record deterministic 10% canary eligibility on new tasks for 24 hours
4. Monitor error rate via `scripts/continuous_health_monitor.py`
5. If error rate < 5% → promote canary metadata to stable, notify the operator
6. If error rate > 5% → revert metadata to stable, notify the operator

> **Current implementation**: Template-level isolation via canary.md variant + CANARY BUILD marker at spawn time. Child agents receive a different sub-agent template with distinct branding when routed to canary. The routing is deterministic (hash-based, 10%) and reproducible. Full binary-executable isolation (separate process per variant) is not implemented.

### Manual Canary (No canary_deploy.py)

```bash
# 1. Mark current version
CANARY_VERSION="v1.1"
echo "$CANARY_VERSION" > /root/.openclaw/workspace/ops/multi-agent-orchestrator/.canary_version

# 2. Monitor via health monitor
python3 scripts/continuous_health_monitor.py

# 3. Check error rate in metrics after 24h
# 4. Promote or revert based on error rate
```

---

## Rollback Procedure

### When to Roll Back

- Error rate exceeds 5% during canary monitoring window
- Critical health monitor failures after promotion
- Data corruption or state integrity issues
- The operator requests rollback

### Rollback Steps

```bash
# 1. Stop the orchestrator / block new task submissions
# (via require_operator_role() gate — no new tasks accepted)

# 2. Identify the last known good version
git log --oneline -5
# or check task state for last healthy run

# 3. Restore from backup if needed
python3 scripts/disaster_recovery_test.py
# If clean: restore individual files or full state as appropriate

# 4. Restore specific files from last known good backup
# e.g., for task_orchestrator rollback:
# cp /archive/maa-backups/YYYY-MM-DD/maa-state/tasks/...  /root/.openclaw/workspace/ops/multi-agent-orchestrator/

# 5. Restart services
openclaw gateway restart

# 6. Verify
python3 scripts/continuous_health_monitor.py
```

### Full State Rollback (Last Resort)

```bash
# Stop all services first
openclaw gateway stop

# Rename corrupt state
mv /root/.openclaw/workspace/ops/multi-agent-orchestrator/tasks \
   /root/.openclaw/workspace/ops/multi-agent-orchestrator/tasks_corrupt_$(date +%Y-%m-%d)

# Extract last good backup
tar -xzf /archive/maa-backups/YYYY-MM-DD/maa-state.tar.gz -C /

# Restart
openclaw gateway start
```

---

## Version Compatibility

| Component | Version | Notes |
|---|---|---|
| `task_orchestrator.py` | v1.0 | Core runtime |
| `tenant_gate.py` | v1.0 | Rate limiting + quota |
| `access_control.py` | v1.0 | RBAC enforcement |
| `approval_gate.py` | v1.0 | Runtime approval |
| `idempotency.py` | v1.0 | Dedup layer |
| Health monitor | v1.0 | Community release |
| Canary deploy | v1.0 | Community release |

---

## Self-Hoster Notes

For self-hosted deployments:

- Always test new versions in a non-production environment first
- Canary deployment is strongly recommended for any runtime change
- Maintain a local backup on a separate volume (in addition to the automated daily backup)
- After updating any file, run the health monitor to verify system integrity before accepting new tasks

---

*Document version: v1.0 | Last reviewed: 2026-04-22*
