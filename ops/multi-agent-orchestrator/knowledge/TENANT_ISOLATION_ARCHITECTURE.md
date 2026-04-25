# Maa Protocol — Hierarchical Tenant Isolation Architecture
**Version:** 1.0  
**Date:** 2026-04-21  
**Status:** Draft — Requires operator approval before implementation  
**Model:** Operator Tenant → Client Sub-Tenant (Hierarchical Two-Level)

---

## Overview

Maa Protocol v3 introduces hierarchical tenant isolation.

The architecture adds a **tenant context layer** over the existing Maa core — wrapping task routing, metric collection, data storage, and auth boundaries without modifying Maa core itself.

**Design principle:** Maa core remains unchanged. Tenant isolation is a wrapper that intercepts tasks, routes them with context, stores outputs per-tenant, and enforces boundaries. Child agents receive tenant context as a parameter — they execute without needing to know about isolation.

---

## Two-Level Tenant Model

### Level 1 — Operator Tenant
- An operator is the primary account holder for a deployment
- Each operator has their own namespace on the system
- Operators can see all their own data and all their clients' data
- Operators cannot see other operators' data

### Level 2 — Client Sub-Tenant
- Each client belongs to an operator
- Clients are isolated from other clients within the same operator
- A client cannot see another client's data
- Clients may have limited visibility into their own data depending on operator configuration

### Hierarchy Map
```
System
└── Operator_1 (deployment owner)
    └── Client_A
    └── Client_B
    └── Client_C
└── Operator_2 (future expansion)
    └── Client_X
    └── Client_Y
```

---

## Backward Compatibility

### Existing Tasks (pre-tenant era)
All tasks created before tenant isolation is deployed are tagged with:
```json
{
  "operator_id": "default",
  "client_id": "default"
}
```
The `default` operator is the system operator (the first operator). Existing task state files, logs, and outputs are treated as belonging to `default/default`.

**Behavior:** Existing tasks continue to work without modification. They are visible to the `default` operator with full access.

### New Tasks
All new tasks submitted after tenant isolation is deployed must include:
```json
{
  "operator_id": "<operator>",
  "client_id": "<client>"
}
```
Tasks without tenant context are rejected with an `UNAUTHORIZED` error at the orchestrator entry point.

---

## Tenant Context Object

Every task, metric, log entry, and data file is tagged with a tenant context:

```json
{
  "operator_id": "default_operator",
  "client_id": "client_001",
  "operator_label": "Default Operator",
  "client_label": "Acme Corp",
  "tenant_tier": "operator" | "client",
  "isolation_level": "full" | "soft",
  "created_at": "2026-04-21T01:00:00Z"
}
```

The tenant context is:
- Passed to child agents as an immutable parameter
- Written into every log entry, metric record, and data file
- Stored in task state as `tenant_context`
- Never stripped after assignment — the context follows the task throughout its lifecycle

---

## Directory Structure

```
/root/.openclaw/workspace/
├── tenants/                          # NEW: root for all tenant data
│   └── {operator_id}/
│       ├── config/
│       │   └── operator.json         # operator-level config, rate limits, settings
│       ├── clients/
│       │   └── {client_id}/
│       │       ├── config/
│       │       │   └── client.json   # client-level config, permissions
│       │       ├── tasks/            # task state files for this client's tasks
│       │       ├── logs/             # completion markers, validation reports
│       │       ├── outputs/          # agent output files
│       │       └── metrics/
│       │           └── tenant_metrics.json
│       └── metrics/
│           └── operator_metrics.json
├── ops/
│   └── multi-agent-orchestrator/
│       └── tasks/                    # NOTE: existing tasks dir retained for backward compat
└── data/
    └── reports/                      # NOTE: existing reports dir retained for backward compat
```

### Migration Path
- Phase 1: All new tenant data goes to `tenants/{operator_id}/...`
- Phase 2: After all clients are onboarded, existing `ops/multi-agent-orchestrator/tasks/` and `data/reports/` are migrated to tenant structure
- Phase 3: Old paths become aliases to tenant paths
- Default operator (`default`) has `tenants/default/` as its home

---

## Task Flow With Tenant Context

```
[Task submitted]
        │
        ▼
┌───────────────────────────────────────┐
│  TenantGate (new component)           │
│  - Extract tenant_context from request │
│  - Validate operator_id + client_id    │
│  - Reject if no context (unless       │
│    backward-compat mode for default)  │
│  - Write tenant_context to task state  │
└───────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────┐
│  Existing Maa Orchestrator            │
│  - Receives task with tenant_context   │
│  - Passes tenant_context to child     │
│    agents as parameter                │
│  - Routes to appropriate child pool    │
│  - All output stored in tenant path   │
└───────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────┐
│  TenantMetricCollector (wrapped)       │
│  - Adds tenant_context to every metric │
│  - Stores in tenants/{op}/metrics/     │
└───────────────────────────────────────┘
```

---

## Tenant Context Propagation to Child Agents

Child agents receive tenant context as an immutable task parameter:

```json
{
  "task_id": "research-123456",
  "task_type": "research",
  "task_prompt": "Analyze X for Client Y",
  "tenant_context": {
    "operator_id": "default_operator",
    "client_id": "client_001",
    "operator_label": "Default Operator",
    "client_label": "Acme Corp"
  }
}
```

**Agents must:**
- Include tenant_context in all writes (output files, log entries)
- Use tenant-scoped paths for all data
- Never write outside their assigned tenant path

**Agents must not:**
- Access other operators' paths
- Access other clients' paths within the same operator (unless operator-level task)
- Strip or modify tenant_context

---

## Auth Boundaries

### Operator-Level Permissions
| Action | Permission |
|---|---|
| See all own clients' data | ✅ Yes |
| Add new clients | ✅ Yes |
| Set per-client rate limits | ✅ Yes |
| See other operators' data | ❌ No |
| Modify other operators' config | ❌ No |

### Client-Level Permissions
| Action | Permission |
|---|---|
| See own data only | ✅ Yes |
| See other clients' data | ❌ No |
| See operator-level data | ❌ No |
| Modify own config | ❌ No (operator only) |

### Default Operator
- The default operator is the `default` operator
- The default operator has full visibility into all `default` operator data
- The default operator can create additional operators
- The platform may allow promotion of another operator to master in a future release

---

## Rate Limits

**Per-Operator Limits:**
```json
{
  "operator_id": "default_operator",
  "max_concurrent_tasks": 8,
  "max_tasks_per_hour": 200,
  "max_child_agents_per_task": 4,
  "rate_limit_window_hours": 1
}
```

**Per-Client Limits:**
```json
{
  "operator_id": "default_operator",
  "client_id": "client_001",
  "max_concurrent_tasks": 2,
  "max_tasks_per_hour": 50,
  "max_data_storage_gb": 10
}
```

**Enforcement:** TenantGate checks rate limits before accepting a task. If exceeded, task is rejected with `RATE_LIMIT_EXCEEDED` and the operator is notified.

---

## Metric Isolation

**Per-Tenant Metrics Store:**
- `tenants/{operator_id}/metrics/operator_metrics.json` — operator-level aggregates
- `tenants/{operator_id}/clients/{client_id}/metrics/tenant_metrics.json` — per-client metrics

**Metric record format:**
```json
{
  "label": "research.completion",
  "tenant_context": {
    "operator_id": "partha_primeidea",
    "client_id": "client_001"
  },
  "timestamp": "2026-04-21T01:00:00Z",
  "latency_ms": 2341,
  "result": "success"
}
```

**Aggregation:** Observability dashboard shows per-tenant breakdowns. Cross-tenant aggregation is operator-only within that operator's scope. No cross-operator aggregation.

---

## Audit Trail

Every significant action is logged with full tenant attribution:

```json
{
  "timestamp": "2026-04-21T01:00:00Z",
  "action": "task.submitted",
  "operator_id": "partha_primeidea",
  "client_id": "client_001",
  "task_id": "research-123456",
  "task_type": "research",
  "result": "accepted",
  "ip_or_channel": "telegram"
}
```

**Audit log location:** `tenants/{operator_id}/audit/{YYYY-MM}.jsonl`

**Retention:** Audit logs are never auto-deleted. They are stored indefinitely per operator.

---

## New Components

### 1. TenantGate
**File:** `ops/multi-agent-orchestrator/tenant_gate.py`  
**Role:** Entry point interceptor. Validates tenant context on every task submission. Enforces rate limits. Rejects or accepts tasks before they reach the orchestrator.  
**Interface:** `submit_task(task_prompt, task_type, tenant_context) → task_id or Error`

### 2. TenantContext
**File:** `ops/multi-agent-orchestrator/tenant_context.py`  
**Role:** Immutable tenant context object. Passed to all components. Carries operator_id, client_id, tier, and labels.  
**Interface:** `TenantContext(...)` → context object with `.operator_id`, `.client_id`, `.paths()`, `.rate_limits()`

### 3. TenantMetricCollector
**File:** `ops/multi-agent-orchestrator/tenant_metrics.py`  
**Role:** Wraps the existing maa_metrics.py. Adds tenant_context to every metric record. Routes metrics to tenant-specific store.  
**Interface:** `record(label, tenant_context, value)` → stored in tenant path

### 4. TenantPathResolver
**File:** `ops/multi-agent-orchestrator/tenant_paths.py`  
**Role:** Resolves all paths based on tenant context. Ensures agents always write to the correct tenant path.  
**Interface:** `resolve(tenant_context, resource_type) → absolute_path`  
**Resources:** `tasks/`, `logs/`, `outputs/`, `metrics/`, `audit/`

### 5. OperatorConfigStore
**File:** `ops/multi-agent-orchestrator/config/operator_config.py`  
**Role:** CRUD for operator and client config. Rate limits, tier, permissions.  
**Interface:** `create_operator()`, `update_operator()`, `create_client()`, `deactivate_client()`

---

## Implementation Phases

### Phase 1 — Core Tenant Infrastructure (this session)
1. `TenantContext` dataclass
2. `TenantPathResolver` — path resolution for all resource types
3. `TenantGate` — entry validation, rate limiting, backward-compat for `default`
4. Tenant-aware `submit_task` path
5. Migration of current task state to `tenants/default/` structure

### Phase 2 — Metric Isolation (next session)
6. `TenantMetricCollector` wrapping `maa_metrics.py`
7. Per-tenant metrics store
8. Dashboard updated to show operator/client breakdown

### Phase 3 — Operator/Client Management (next session)
9. `OperatorConfigStore` — CRUD for operators and clients
10. Rate limit enforcement
11. Audit trail logging

### Phase 4 — Integration & Testing (after Phase 3)
12. End-to-end test with operator + client context
13. Failover test: agent fails → tenant context preserved
14. Isolation test: client A cannot see client B's data
15. Rate limit test: exceed limit → rejection + notification

---

## What Maa Core Does NOT Change

- `task_orchestrator.py` remains the orchestrator — it just receives tenant_context in the task dict
- `maa_metrics.py` remains — wrapped by TenantMetricCollector
- Child agent pool is unchanged — they receive tenant_context as a parameter
- Completion markers include tenant_context but use same format
- No new task statuses added
- No changes to `RUNBOOK.md` validation gates

---

## Backward Compatibility Guarantee

| Scenario | Behavior |
|---|---|
| Task submitted with `tenant_context` | Accepted, routed with context |
| Task submitted without context, operator=`default` | Accepted in backward-compat mode, tagged as `default/default` |
| Task submitted without context, operator≠`default` | **Rejected** — `UNAUTHORIZED: tenant context required` |
| Old task state files (no tenant field) | Continue working, treated as `default/default` |
| Old completion markers | Continue readable, mapped to `default/default` |

---

## Data Migration

**Step 1:** Create `tenants/default/` structure  
**Step 2:** Move `ops/multi-agent-orchestrator/tasks/*.json` → `tenants/default/tasks/`  
**Step 3:** Move `ops/multi-agent-orchestrator/logs/*.completion` → `tenants/default/logs/`  
**Step 4:** Move `data/reports/*` → `tenants/default/outputs/`  
**Step 5:** Update orchestrator to resolve paths via `TenantPathResolver`  
**Step 6:** Old paths become symlinks to new tenant paths (transparent alias)

**Safety:** Migration runs with `--dry-run` first. No data is deleted until verified correct.

---

## Status: Awaiting Operator Approval

This spec defines the complete architecture. No code will be written until the operator approves this document.

Questions or changes before implementation?