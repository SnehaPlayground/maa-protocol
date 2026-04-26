<!-- Version: v1.0 -->
# MAA PROTOCOL — DATA PRIVACY, RETENTION & DELETION
Version: 1.0
Prepared: 2026-04-22
Owner: Mother Agent, Maa deployment

---

## 1. DATA CLASSIFICATION

| Class | Examples | Handling |
|---|---|---|
| **Public** | Task outputs shared with the requester | Standard delivery |
| **Internal** | Metrics, logs, audit trails | Restricted access, no external sharing |
| **Sensitive** | Client names, email addresses, conversation content | Strict isolation, encrypted where possible |
| **Restricted** | API keys, tokens, credentials | Environment variables only, never in files |

**Classification rule:** Default to the most restrictive class unless the data
has a documented reason to be less restricted.

---

## 2. RETENTION SCHEDULE

| Data Type | Retention | Auto-Delete | Notes |
|---|---|---|---|
| Metrics store (`maa_metrics.json`) | 30 days | `auto_cleanup.py` trims at 30 days |滚动删除 oldest entries first |
| Task state files | 90 days after completion | `auto_cleanup.py` trims at 90 days | Active tasks (pending/running/queued) exempt |
| Completion markers | 90 days after task completion | `auto_cleanup.py` trims at 90 days | Used by health monitor — clean after verification |
| Validation reports | 90 days after task completion | `auto_cleanup.py` trims at 90 days | |
| Audit JSONL files | 7 years | Manual deletion only | Financial-grade retention; legal requirement |
| Email send records | 7 years | Manual deletion only | Financial-grade retention |
| Secrets (credentials, tokens) | Rotation-triggered | Not time-based | Rotate on suspicion or trigger, not calendar |
| Maintenance decision logs | 90 days | `auto_cleanup.py` trims at 90 days | |
| Reflection files | 90 days after task completion | `auto_cleanup.py` trims at 90 days | |
| Progress files | 30 days after task completion | `auto_cleanup.py` trims at 30 days | Short-term operational data |

---

## 3. PII HANDLING RULES

### 3.1 What counts as PII in the Maa context

- Client names and email addresses
- Conversation content from client interactions
- Task inputs that contain client data
- Tenant names and identifiers

### 3.2 Rules for PII

| Rule | Reason |
|---|---|
| No PII in task state filenames | Filenames are exposed in logs and alerts |
| No PII in agent prompts unless required | Reduces exposure surface |
| No PII in completion markers | Markers are not encrypted |
| No PII in validation reports unless required for audit | Audit reports may be shared more broadly |
| Sensitive PII must not appear in output files | Output files may be delivered to the requester |
| PII in task inputs: minimize scope | Only include what the task needs |

### 3.3 Anonymization for Debugging

When an operator asks for a debugging session or a sample task dump:
- Strip client names → replace with `[CLIENT_REDACTED]`
- Strip email addresses → replace with `[EMAIL_REDACTED]`
- Strip phone numbers → replace with `[PHONE_REDACTED]`
- Keep task structure and metadata intact

**Never provide raw task dumps to third parties for debugging without explicit operator approval.**

---

## 4. TENANT DATA DELETION

### 4.1 Client Sub-Tenant Deactivation

When a client sub-tenant is deactivated via `tenant_crud.py deactivate-client`:

1. **Immediate (deactivation time):**
   - Set `status: "deactivated"` in the client's `config/client.json`
   - Stop accepting new tasks for that `client_id`
   - Existing running tasks are allowed to complete

2. **Within 30 days:**
   - Delete all tenant-scoped files:
     - `tenants/{operator_id}/clients/{client_id}/tasks/*.json`
     - `tenants/{operator_id}/clients/{client_id}/logs/*.completion`
     - `tenants/{operator_id}/clients/{client_id}/logs/*.validation`
     - `tenants/{operator_id}/clients/{client_id}/outputs/*`
     - `tenants/{operator_id}/clients/{client_id}/metrics/*`
   - **Retain:** Operator-level audit JSONL files (`tenants/{operator_id}/audit/*.jsonl`)
     — runtime audit is written at operator scope and is retained for 7-year financial retention

3. **Audit trail:**
   - Log the deactivation event in `data/email/approval_audit.jsonl`
   - Include: operator_id, client_id, deactivated_at, deleted_file_count

### 4.2 Operator Tenant Deletion

When an operator tenant is deactivated:
- All client sub-tenants under that operator are also deactivated
- Same deletion timeline as client sub-tenant (30-day window)
- Audit JSONL files retained for 7 years

### 4.3 Hard Delete vs. Soft Delete

**Soft delete:** Set `status: "deactivated"` in config — no new tasks accepted, existing data preserved for 30 days. This is the default deactivation method.

**Hard delete:** Physically remove all tenant data within 24 hours of deactivation request. This is only available to an authorized operator and requires explicit operator confirmation before execution.

---

## 5. AUTO_CLEANUP.py — RETENTION ENFORCEMENT

`scripts/auto_cleanup.py` enforces the retention schedule:

| Rule | Threshold | Behavior |
|---|---|---|
| Metrics store | 30 days | Delete oldest entries beyond 30 days |
| Task state files | 90 days after completion | Delete .json files in tasks/ older than 90 days |
| Completion markers | 90 days after task completion | Delete .completion files older than 90 days |
| Validation reports | 90 days after task completion | Delete .validation files older than 90 days |
| Progress files | 30 days after task completion | Delete .progress files older than 30 days |
| Maintenance logs | 90 days | Delete .jsonl files older than 90 days |

**Active task exemption:** Tasks with status `pending`, `running`, `queued`,
`needs_revision`, `retry` are never deleted by auto_cleanup, regardless of age.

**Completion marker exemption:** Markers are retained for 90 days to allow
health monitor verification. After 90 days, they are deleted in the next cleanup run.

---

## 6. CROSS-TENANT DATA ISOLATION

| Rule | Enforcement |
|---|---|
| Tenant A cannot read Tenant B files | `TenantPathResolver` enforces path scoping at resolution time |
| Tenant A cannot write to Tenant B paths | Path resolution rejects `../` escape attempts |
| Operator cannot read client sub-tenant audit logs | Config-level `audit_read: false` blocks this |
| Client cannot access operator-level metrics | Client metrics are tenant-scoped only |

**Path escape prevention:**
- `TenantPathResolver.resolve()` validates that the resolved path starts with `TENANTS_ROOT`
- Any path not under `TENANTS_ROOT` is rejected
- Task submission with `tenant_id` containing `../` is rejected at entry gate

---

## 7. AUDIT LOG STRUCTURE

Audit logs are written to operator-scoped JSONL files:

**File:** `tenants/{operator_id}/audit/YYYY-MM.jsonl`

**Entry format:**
```json
{
  "at": "2026-04-22T10:00:00Z",
  "event": "task_submitted|task_validated|task_failed|tenant_deactivated|approval_recorded|email_sent",
  "task_id": "task-abc123",
  "operator_id": "primeidea",
  "client_id": "acme",
  "agent_id": "mother|researcher|...",
  "details": {}
}
```

**Retention:** 7 years — **no auto-deletion**. Manual deletion only upon legal requirement.

---

## 8. DATA HANDLING IN CHILD AGENTS

Child agents must follow these rules when processing tenant data:

| Rule | Implementation |
|---|---|
| No PII in tool responses | `child_output_is_usable()` strips credential-like strings |
| No tenant paths in completion markers | Marker contains only `task_id` + `completed_at` |
| Task output files are tenant-scoped | Written to `tenants/{op_id}/clients/{cl_id}/outputs/` |
| Metrics from child agents are tenant-scoped | `record_task()` keys by `task_id` + `tenant_id` |
| No cross-tenant metrics aggregation | Per-tenant metrics store only |

---

## 9. VERIFICATION CHECKLIST

- [ ] `auto_cleanup.py` respects 30/90 day retention thresholds
- [ ] Active task exemption works (pending/running tasks not deleted)
- [ ] Tenant deactivation via `tenant_crud.py` sets status correctly
- [ ] Deactivated tenant cannot spawn new tasks
- [ ] Audit JSONL files are NOT deleted by auto_cleanup
- [ ] Secrets are not in any workspace markdown files
- [ ] PII does not appear in task state filenames
- [ ] No PII in completion markers or validation reports
- [ ] Cross-tenant path escape is blocked by TenantPathResolver

---

*This document governs how long data lives, how it is deleted, and how PII is handled.*
*Any exception to these rules requires explicit operator approval.*
