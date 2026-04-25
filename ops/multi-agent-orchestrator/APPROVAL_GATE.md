<!-- Version: v1.0 -->
# MAA PROTOCOL — RUNTIME APPROVAL ENFORCEMENT
Version: 1.0
Prepared: 2026-04-22
Owner: Mother Agent, Maa deployment

---

## 1. PURPOSE

The pre-execution approval gate (Maa Protocol RULE 1) must be enforceable in
**runtime code**, not only in prompting. This document defines the approval
contract, the enforcement mechanism, and the operational flow.

**Binding rule (from GLOBAL_POLICY.md):**
> External actions require approval unless a runbook explicitly allows a low-risk action.
> When uncertain, pause and ask.

---

## 2. APPROVAL STATE CONTRACT

All approval state is stored in a single JSON file:

**File:** `data/email/approval_state.json`

**Structure:**
```json
{
  "approvals": {
    "<action_hash>": {
      "action_hash": "sha256_of_action",
      "requested_by": "agent_id",
      "task_id": "task-abc123",
      "action_type": "email_send|calendar_write|web_post|file_external|api_write",
      "target": "recipient@domain.com or /path/to/resource",
      "body_summary": "First 80 chars of body or description",
      "status": "pending|approved|rejected|expired|not_required",
      "approved_by": "operator|agent|system",
      "approved_at": "2026-04-22T10:00:00Z",
      "approver_token": "explicit_approval_token",
      "expires_at": "2026-04-22T12:00:00Z",
      "created_at": "2026-04-22T10:00:00Z"
    }
  }
}
```

**Action hash derivation:**
```python
import hashlib, json

def _action_hash(action_type, target, body_summary, tenant_id):
    raw = f"{action_type}|{target}|{body_summary}|{tenant_id}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]
```

**Action types requiring approval:**
| action_type | Description |
|---|---|
| `email_send` | Sending any outbound email |
| `calendar_write` | Creating or modifying calendar events |
| `web_post` | Posting to any public or external channel |
| `file_external` | Writing files outside the workspace |
| `api_write` | Writing to any external API (excluding internal Maa APIs) |
| `client_data_delete` | Deleting client-owned data |

**Action types NOT requiring approval:**
| action_type | Reason |
|---|---|
| `task_submit` | Internal operation — no external side effect |
| `task_state_write` | Internal operation |
| `metrics_record` | Internal operation |
| `progress_update` | Internal operation |

---

## 3. APPROVAL_GATE.py — OPERATIONS

Script: `ops/multi-agent-orchestrator/approval_gate.py`

### 3.1 Create Pending Approval

```bash
python3 approval_gate.py create \
  --agent mother \
  --task-id task-abc123 \
  --action-type email_send \
  --target "client@example.com" \
  --body-summary "Growth report for Q1 2026" \
  --tenant-id default
```

Output:
```
Approval pending:
  hash: a4f2c8...
  type: email_send
  target: client@example.com
  expires: 2026-04-22T12:00:00Z
```

### 3.2 Check Approval Status

```bash
python3 approval_gate.py check --hash a4f2c8...
```

Output: `approved` | `rejected` | `pending` | `expired` | `not_required`

### 3.3 Record Operator Approval

```bash
python3 approval_gate.py approve --hash a4f2c8... --token APPROVE_TO_SEND
```

### 3.4 Record Operator Rejection

```bash
python3 approval_gate.py reject --hash a4f2c8...
```

### 3.5 List Pending Approvals

```bash
python3 approval_gate.py list-pending
```

---

## 4. RUNTIME ENFORCEMENT

### 4.1 Pre-Spawn Approval Check

Every `spawn_child_agent()` call that has external side effects must pass
through `_check_approval_gate()` before execution:

```python
def _check_approval_gate(action_type, target, body_summary, tenant_context):
    """Returns (allowed: bool, reason: str)"""
    if action_type not in APPROVAL_REQUIRED_TYPES:
        return (True, "not_required")

    tc = parse_tenant_context(tenant_context)
    action_hash = _action_hash(action_type, target, body_summary, tc.operator_id)

    state = _load_approval_state()
    entry = state["approvals"].get(action_hash)

    if entry is None:
        return (False, f"Approval required for {action_type} — submit for operator review")

    if entry["status"] == "approved":
        return (True, "approved")

    if entry["status"] == "pending":
        return (False, "Approval pending — waiting for operator")

    if entry["status"] == "expired":
        return (False, "Approval expired — please resubmit")

    return (False, f"Approval status: {entry['status']}")
```

### 4.2 Enforcement in spawn_child_agent

The orchestrator checks `_check_approval_gate` **before** any spawn call
that has `action_type in APPROVAL_REQUIRED_TYPES`. If `allowed == False`,
the task is set to `blocked` status with the reason, and the operator is notified.

### 4.3 Auto-Expiry

Approvals expire 2 hours after creation (`expires_at`).

**Current implementation status:** expiry is enforced lazily by `approval_gate.py check`
when a pending approval is inspected. Continuous monitor-driven expiry marking runs via
`continuous_health_monitor.py` (Phase 7). Direct operator notification and automatic retry
when approval is later recorded are future enhancements, not active guarantees.

### 4.4 Block Behavior

When a task is blocked for lack of approval:
1. Task status → `blocked`
2. `approval_gate_reason` is written into task state
3. Spawn is halted before child execution

**Current implementation status:** Direct operator notification and automatic retry
when approval is later recorded are not yet implemented in runtime code. Those are
future enhancements, not active guarantees.

---

## 5. APPROVAL TOKEN RULES

| Token | Meaning | Effect |
|---|---|---|
| `APPROVE TO SEND` | Explicit operator approval | Status → approved |
| `SEND NOW` | Urgent operator approval | Status → approved, expedited |
| `APPROVED` | Generic operator approval | Status → approved |
| Any other token | Not a valid approval token | No effect — ignored |

**Token comparison is case-insensitive and whitespace-tolerant.**

---

## 6. IDEMPOTENCY IN APPROVAL

- Approval entries are keyed by `action_hash`
- Duplicate approval requests for the same hash are rejected (no double-approval)
- Re-submission of the same action after rejection: creates a **new** entry with a new hash
- If the same action is submitted twice while the first is still `pending`, the same entry is returned

---

## 7. AUDIT TRAIL

Every approval state change is logged:
```json
{
  "at": "2026-04-22T10:00:00Z",
  "action_hash": "a4f2c8...",
  "from_status": "pending",
  "to_status": "approved",
  "by": "operator",
  "task_id": "task-abc123"
}
```

Log file: `data/email/approval_audit.jsonl`
Retention: 7 years (financial-grade, per DATA_PRIVACY.md)

---

## 8. VERIFICATION

- [ ] `approval_gate.py` exists and all subcommands work
- [ ] `approval_state.json` is created on first use
- [ ] `_check_approval_gate()` blocks unapproved email_send actions
- [ ] Operator receives notification when task is blocked
- [ ] Approved action unblocks and task completes normally
- [ ] Expired approvals are marked expired by the continuous health monitor
- [ ] No credentials or tokens appear in approval_state.json bodies
- [ ] Approval audit log appends correctly

---

*Approval gate enforcement is active from the moment this document is deployed.*
*An authorized human approver must approve all external-facing actions before they execute.*
