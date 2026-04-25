# Changelog

All notable changes to Maa Protocol are documented here.

Maa Protocol follows [Semantic Versioning](https://semver.org/). Versions follow `vMAJOR.MINOR` format.

---

## v1.0 — Initial Production Release

**Released:** 2026-04-23
**Status:** Stable — deployment-ready

### What's New

| Phase | Feature | Status |
|---|---|---|
| 1 | Spawnable child-agent templates (5 types) | ✅ |
| 2 | Runtime harness enforcement | ✅ |
| 3 | Live progress + transport-agnostic delivery | ✅ |
| 4 | Circuit breaker, load shedding, mother self-execution | ✅ |
| 5 | Operational HTML dashboard | ✅ |
| 6 | Tenant Phase 2 — CRUD, metrics, usage reporting | ✅ |
| 7 | Continuous regression monitoring (15-min cron) | ✅ |
| 8 | SLA documentation + operator runbook | ✅ |
| 9 | Security hardening — secrets scanner, runtime approval gate, data privacy | ✅ |
| 10 | Access control + RBAC (SYSTEM > OPERATOR > AGENT > CLIENT) | ✅ |
| 11 | Idempotency, task dedup, side-effect dedup | ✅ |
| 12 | Canary deployment router (10% hash routing, auto-promote/revert) | ✅ |
| 13 | Cost controls — daily/monthly spend caps, degrade modes, runtime minute accounting | ✅ |
| 14 | Community open-source release package | ✅ |

### Core Guarantees

- **No user-facing timeout errors** — ever. Child-agent failures trigger automatic failover chain (Agent 1 → Agent 2 → Agent 3 → Mother self-execution → honest Partha escalation).
- **Zero-fabrication completion validation** — all task completions verified via structured output checks and completion markers.
- **Tenant-isolated task state and metrics** — operator/client hierarchy with isolated paths, rate limits, and audit trails.
- **Operator-controlled external action approvals** — every send-email, calendar-write, web-post checked against `approval_state.json` at runtime.
- **Cost controls per tenant** — daily/monthly spend caps, runtime minute budgets, degrade modes (reject / queue / require-approval) with automatic enforcement.
- **Deterministic canary routing** — 10% of new tasks routed to canary version; auto-promotes if error rate < 5% over 24h, auto-reverts if ≥ 5%.

### Security

- Secrets scanner (scans all workspace markdown files; alerts on any token/key pattern)
- Tenant isolation test pack (6 checks: path escape, cross-tenant read/write, rate limit bypass, audit path, tenant deactivation)
- Runtime approval gate enforced in `task_orchestrator.py` before any external side effect
- RBAC enforced at every mutating operation (spawn, approve, tenant CRUD, task submit)
- No credentials stored in markdown files

### Operational Surface

| CLI | Purpose |
|---|---|
| `python3 task_orchestrator.py submit <task_type> <input>` | Submit a new task |
| `python3 task_orchestrator.py status <task_id>` | Check task status |
| `python3 task_orchestrator.py list` | List all tasks |
| `python3 task_orchestrator.py gate-status` | Show last pre-deploy gate result |
| `python3 tenant_crud.py list-operators` | List operators |
| `python3 tenant_crud.py usage <op> <client>` | Show tenant usage |
| `python3 approval_gate.py check <ahash>` | Check approval state |
| `python3 canary_router.py status` | Show canary/stable versions |
| `python3 canary_router.py deploy v1.x` | Deploy canary version |
| `python3 scripts/continuous_health_monitor.py` | Run health check |
| `bash scripts/pre_deploy_gate.sh` | Run full pre-deploy gate |

### Files in Release

```
ops/multi-agent-orchestrator/
  task_orchestrator.py       # Core runtime (~1500 lines)
  tenant_gate.py             # Quota + rate limit enforcement
  access_control.py          # RBAC enforcement
  approval_gate.py           # Runtime approval CLI
  idempotency.py             # Task + side-effect dedup
  canary_router.py           # Canary routing + CLI
  SELF_HEALING_POLICY.md
  NO_TIMEOUT_POLICY.md
  GLOBAL_POLICY.md
  RUNBOOK.md
  SLA.md
  OPERATOR_RUNBOOK.md
  CLIENT_ONEPAGER.md
  ACCESS_CONTROL.md
  SECURITY.md
  APPROVAL_GATE.md
  DATA_PRIVACY.md
  COST_CONTROL.md
  VERSIONING.md
  DISASTER_RECOVERY.md
  COMMUNITY_RUNBOOK.md
  CONTRIBUTING.md
  RELEASE_CHECKLIST.md

agents/
  templates/
    researcher/v1.0.md
    executor/v1.0.md
    coder/v1.0.md
    verifier/v1.0.md
    communicator/v1.0.md

scripts/
  health_check.py
  auto_cleanup.py
  maintenance_logger.py
  continuous_health_monitor.py
  pre_deploy_gate.sh
  tenant_isolation_test.py
  secrets_scanner.py
  disaster_recovery_backup.py
  disaster_recovery_test.py
  tenant_onboard.py
  tenant_usage_governance_report.py
  canary_deploy.py

templates/
  maa-product/
    community-server.json
    laptop.json
    small-vps.json
    single-tenant.json
    runtime-config.template.json
```

### Known Constraints

- Canary binary-executable isolation (separate process per variant) is not implemented; template-level isolation is used instead.
- Multi-tenant operator/client management is available (Phase 6/10) but production multi-client deployment requires operator to configure per-client rate limits before first use.
- Backup restore is tested and clean; full automated restore orchestration is a future enhancement.

---

*Next release: v1.1 — feature additions and performance improvements*