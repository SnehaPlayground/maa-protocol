# MAA Protocol Community Runbook
**Version:** v1.0
**Target:** Self-hosters, open-source adopters, community operators
**Prerequisite:** Maa Protocol Phases 1–13 deployed and operational

---

## What Is Maa Protocol?

Maa (Mother Agent Architecture) is a production-grade multi-agent orchestration system. It runs child agents with failover, enforces tenant isolation, maintains observability, and prevents end users from seeing timeout or silent failure states.

**Key guarantees:**
- No user-facing timeout errors — ever
- Zero-fabrication completion validation
- Tenant-isolated task state and metrics
- Operator-controlled external action approvals
- Cost controls and quota enforcement per tenant

---

## Quick Start (First-Time Install)

### 1. Prerequisites

| Resource | Minimum | Recommended |
|---|---|---|
| OS | Ubuntu 20.04 / Debian 12 / macOS 13 | Ubuntu 22.04 LTS |
| CPU | 2 cores | 4+ cores |
| RAM | 4 GB | 8+ GB |
| Disk | 10 GB free | 20+ GB SSD |
| Python | 3.10+ | 3.11+ |
| Access | OpenClaw workspace | OpenClaw workspace with gateway |

### 2. Install Steps

```bash
# 1. Clone the workspace (or extract release archive)
git clone <repository-url> /root/.openclaw/workspace
cd /root/.openclaw/workspace

# 2. Run the pre-deploy gate (validates everything)
bash scripts/pre_deploy_gate.sh
# Expected output: PRE-DEPLOY GATE PASSED (72/72)

# 3. Verify runtime health
python3 ops/observability/maa_metrics.py dashboard
# Expected: all green, no critical errors

# 4. Submit a test task
python3 ops/multi-agent-orchestrator/task_orchestrator.py submit \
  research \
  "test: verify Phase 14 community install" \
  --run

# 5. Watch it run
python3 ops/multi-agent-orchestrator/task_orchestrator.py status <task_id>
```

### 3. Verify Success

```bash
# Should return a validated task within 5 minutes
python3 ops/multi-agent-orchestrator/task_orchestrator.py status <task_id>
# Expected: status=validated, attempts ≤ 4
```

---

## Configuration Profiles

Four safe deployment profiles are provided in `templates/maa-product/`:

| Profile | Use Case | Concurrency | Multi-Tenant |
|---|---|---|---|
| `laptop.json` | Personal use, single user | 2 children max | No |
| `small-vps.json` | Small server, 1–2 operators | 4 children max | Optional |
| `single-tenant.json` | Single business deployment | 4 children max | No |
| `community-server.json` | Multi-tenant community | 8 children max | Yes |

**Choose the profile closest to your deployment and edit only the values documented in each file.**

---

## Safe Default Settings (What Gets Enabled by Default)

When you deploy using any sample config, these are **enabled automatically**:

| Feature | Default | Notes |
|---|---|---|
| Quota enforcement | ✅ ON | Per-tenant daily task + runtime caps |
| Audit logging | ✅ ON | All mutations written to YYYY-MM.jsonl |
| Health checks | ✅ ON | Every 4 hours via cron |
| Pre-deploy gate | ✅ ON | Daily at 6 AM IST |
| Continuous health monitor | ✅ ON | Every 15 minutes |
| Circuit breaker | ✅ ON | 5% error rate threshold |
| Approval gate | ✅ ON | External actions blocked until approved |
| Conservative concurrency | ✅ ON | Max 4 concurrent children |
| Tenant isolation | ✅ ON | Phase 1+2 path + rate limit enforcement |

These are **disabled by default** (intentional):

| Feature | Default | Notes |
|---|---|---|
| Public write integrations | ❌ OFF | Requires explicit operator enablement |
| Risky outbound automations | ❌ OFF | Requires approval gate |
| Multi-tenant mode | ❌ OFF | Enable only via community-server.json |
| Canary routing | ❌ OFF for laptop/small-vps/single-tenant, optional for community-server | Enable only after stable v1.x verified |

---

## How to Update Safely

### Patch Updates (v1.0 → v1.1)

```bash
# 1. Pull the update
cd /root/.openclaw/workspace
git pull

# 2. Run pre-deploy gate immediately
bash scripts/pre_deploy_gate.sh

# 3. If gate passes → update is safe to deploy
# If gate fails → do NOT deploy; report the failure
```

### Minor Updates (v1.1 → v1.2)

```bash
# 1. Check changelog
cat CHANGELOG.md  # or release notes

# 2. Run gate on current stable version
bash scripts/pre_deploy_gate.sh

# 3. Enable canary for the new version (recommended)
python3 ops/multi-agent-orchestrator/canary_router.py deploy v1.2

# 4. Monitor for 24 hours
python3 ops/multi-agent-orchestrator/canary_router.py status

# 5. Promote if error rate < 5%, revert if ≥ 5%
python3 ops/multi-agent-orchestrator/canary_router.py check
```

### Major Updates (v2.0)

- Requires breaking-change review
- Run full test suite: `python3 ops/multi-agent-orchestrator/tests/test_trust_fixes.py`
- Canary must run for 48 hours
- Rollback plan must be documented before deploy

---

## Common Failures and Recovery

### Symptom: "pre-deploy gate fails — trust tests drop"

**Cause:** A recent code change broke a trust mechanism.

**Recovery:**
```bash
# 1. Identify which test failed
bash scripts/pre_deploy_gate.sh 2>&1 | grep FAILED

# 2. Revert to last known-good commit
cd /root/.openclaw/workspace
git revert HEAD

# 3. Re-run gate
bash scripts/pre_deploy_gate.sh

# 4. If still failing, escalate via bug report template
```

### Symptom: "Task stuck in running state"

**Cause:** Child agent did not write completion marker; orphan process.

**Recovery:**
```bash
# 1. Check task status
python3 ops/multi-agent-orchestrator/task_orchestrator.py status <task_id>

# 2. Check progress file
cat logs/<task_id>.progress

# 3. Check whether the child is genuinely stuck or still progressing
python3 ops/multi-agent-orchestrator/task_orchestrator.py list --limit 10

# 4. Run health monitor to reconcile stale entries
python3 scripts/continuous_health_monitor.py

# 5. If the task is still stuck, review the task state + progress file and re-run the chain only if safe
python3 ops/multi-agent-orchestrator/task_orchestrator.py run <task_id>
```

### Symptom: "Quota exceeded errors on all tasks"

**Cause:** Daily task or runtime quota hit for the tenant.

**Recovery:**
```bash
# 1. Check current usage
python3 ops/multi-agent-orchestrator/tenant_crud.py usage <operator_id> <client_id> --since 24

# 2. Wait for reset (midnight IST for default tenant), or
# 3. Operator override: raise the hourly cap temporarily
python3 ops/multi-agent-orchestrator/tenant_crud.py update-client <operator_id> <client_id> --max-tasks-per-hour 100
```

### Symptom: "Circuit breaker OPEN — no tasks spawn"

**Cause:** Error rate exceeded 5% in the rolling 1-hour window.

**Recovery:**
```bash
# 1. Check which task type triggered the breaker
python3 ops/observability/maa_metrics.py dashboard

# 2. Identify the failing pattern
#    - Transient: wait 1 hour for auto-reset
#    - Structural: fix the child agent template or input

# 3. Manually reset the breaker (if root cause is fixed)
#    (Contact the operator to run the reset command)
```

### Symptom: "Disk full during backup"

**Cause:** Retention policy not enforced; old files accumulating.

**Recovery:**
```bash
# 1. Check disk usage
python3 scripts/health_check.py

# 2. Run aggressive cleanup
python3 scripts/auto_cleanup.py --days 30

# 3. Run disaster recovery backup to verify restore still works
python3 scripts/disaster_recovery_test.py
```

### Symptom: "Approval gate blocks all external actions"

**Cause:** External action attempted without required operator approval.

**Recovery:**
```bash
# 1. Identify pending approval
python3 ops/multi-agent-orchestrator/approval_gate.py list-pending

# 2. Operator reviews and approves or rejects
python3 ops/multi-agent-orchestrator/approval_gate.py approve <action_hash>
#    or
python3 ops/multi-agent-orchestrator/approval_gate.py reject <action_hash>
```

---

## Disaster Recovery (5-Minute RTO)

```bash
# 1. Identify the backup to restore from
ls /root/.openclaw/workspace/archive/maa-backups/

# 2. Run restore verification against the latest archive
python3 scripts/disaster_recovery_test.py --restore-dir /tmp/maa-restore-check

# 3. If restore verification fails, stop and investigate backup integrity before touching live state

# 4. Verify operational health
bash scripts/pre_deploy_gate.sh
```

**RTO target:** < 30 minutes from failure detection to operational restore.
**RPO:** < 24 hours (daily backup captures all state).

---

## Multi-Tenant Community Server (community-server.json)

If deploying the multi-tenant profile:

```bash
# Onboard a new client
python3 ops/multi-agent-orchestrator/tenant_crud.py create-client <operator_id> <client_id> "Client Label"

# Set their rate limits
python3 ops/multi-agent-orchestrator/tenant_crud.py update-client \
  <operator_id> <client_id> \
  --max-tasks-per-hour 50

# Check their usage
python3 ops/multi-agent-orchestrator/tenant_crud.py usage <operator_id> <client_id> --since 24
```

**Isolated by default:** Each client can only read/write their own task state, logs, and outputs. Cross-tenant access is blocked at the OS filesystem level via tenant_paths.py enforcement.

---

## Monitoring and Alerts

| Check | Command | Frequency |
|---|---|---|
| System health | `python3 scripts/health_check.py` | On demand |
| Full dashboard | `python3 ops/observability/maa_metrics.py dashboard` | On demand |
| Pre-deploy gate | `bash scripts/pre_deploy_gate.sh` | Daily 6 AM IST |
| Continuous monitor | `python3 scripts/continuous_health_monitor.py` | Every 15 min |
| Gate status | `python3 ops/multi-agent-orchestrator/task_orchestrator.py gate-status` | On demand |
| Task list | `python3 ops/multi-agent-orchestrator/task_orchestrator.py list --limit 10` | On demand |

---

## Getting Help

| Need | Where to Go |
|---|---|
| Bug report | Open an issue with the **bug report template** (see CONTRIBUTING.md) |
| Feature request | Open an issue with the **feature request template** |
| Security vulnerability | See **SECURITY.md** → responsible disclosure section |
| Operational question | Check **OPERATOR_RUNBOOK.md** first |
| Cost / quota question | See **COST_CONTROL.md** |
| Tenant isolation question | See **DATA_PRIVACY.md** |

**Before filing an issue:** run `bash scripts/pre_deploy_gate.sh` and include the output. Include your OS, Python version, and deployment profile.

---

## Security Checklist (Pre-Deployment)

- [ ] Changed all default passwords
- [ ] `.gitignore` covers `secrets.env`, `*.token`, `*.key`
- [ ] No credentials in workspace markdown files (run `python3 scripts/secrets_scanner.py`)
- [ ] Firewall blocks non-essential ports
- [ ] SSH root login disabled
- [ ] Backup cron is active: `crontab -l | grep maa`
- [ ] Telegram/notification credentials are environment-variable backed, not in config files
- [ ] The operator has reviewed and approved the deployment checklist in `SECURITY.md`

---

## Operational Boundaries (What Maa Will NOT Do)

Maa Protocol is designed to be safe for community deployment. It will **not**:

- Send outbound email without explicit approval recorded in `approval_state.json`
- Expose one tenant's data to another tenant
- Spawn child agents without valid tenant context
- Fabricate task completion — every output must pass the validation gate
- Run without the pre-deploy gate in place
- Execute external side effects from unapproved sources

If any of the above occurs, treat it as a **security incident** and file a bug report immediately.

---

*Last updated: v1.0 — Phase 14 initial release*
