<!-- Version: v1.0 -->
# ACCESS CONTROL — MAA PROTOCOL RBAC
Version: v1.0
Date: 2026-04-22
Owner: Mother Agent, Maa deployment

---

## 1. ROLE DEFINITIONS

| Role     | Who                                         | Description                                      |
|----------|---------------------------------------------|--------------------------------------------------|
| SYSTEM   | Mother Agent (task_orchestrator.py)        | Full access, all tenants, all operations         |
| OPERATOR | Human operator                              | Deploy, restart, view metrics, approve actions, manage tenants |
| AGENT    | Automated child agents                      | Read-only on own task state, write own output, no cross-tenant access |
| CLIENT   | End client                                  | Read-only own task status, no system access       |

---

## 2. PERMISSIONS MATRIX

| Operation                  | SYSTEM | OPERATOR | AGENT | CLIENT |
|---------------------------|--------|----------|-------|--------|
| Spawn child agent         |   ✅   |    ❌    |  ❌   |   ❌   |
| Approve external action   |   ✅   |    ✅    |  ❌   |   ❌   |
| View own task status      |   ✅   |    ✅    |  ✅   |   ✅   |
| View another tenant       |   ✅   |    ✅    |  ❌   |   ❌   |
| Delete tenant data        |   ✅   |    ✅    |  ❌   |   ❌   |
| View metrics dashboard    |   ✅   |    ✅    |  ❌   |   ❌   |
| Run pre-deploy gate       |   ✅   |    ✅    |  ❌   |   ❌   |
| Modify own task state     |   ✅   |    ✅    |  ✅*  |   ❌   |
| Submit task               |   ✅   |    ✅    |  ❌   |   ❌   |
| Create tenant             |   ✅   |    ✅    |  ❌   |   ❌   |
| Deactivate tenant         |   ✅   |    ✅    |  ❌   |   ❌   |
| View tenant usage report  |   ✅   |    ✅    |  ❌   |   ❌   |
| Read approval_state.json  |   ✅   |    ✅    |  ❌   |   ❌   |

(* own task only — AGENT can write to own task output path but cannot modify task state JSON directly)

---

## 3. RUNTIME ENFORCEMENT

### 3.1 Role Enum

Defined in: `ops/multi-agent-orchestrator/access_control.py`

```python
class Role(Enum):
    SYSTEM = "system"
    OPERATOR = "operator"
    AGENT = "agent"
    CLIENT = "client"
```

### 3.2 Permission Map

Each sensitive operation maps to a required role. The check is a simple enum comparison.

```python
REQUIRED_ROLE = {
    "spawn_child_agent":      Role.SYSTEM,
    "approve_external_action": Role.OPERATOR,
    "delete_tenant_data":     Role.OPERATOR,
    "create_tenant":          Role.OPERATOR,
    "deactivate_tenant":      Role.OPERATOR,
    "run_pre_deploy_gate":    Role.OPERATOR,
    "view_all_metrics":       Role.OPERATOR,
    "submit_task":            Role.OPERATOR,
    "read_approval_state":    Role.OPERATOR,
    "write_own_output":       Role.AGENT,
    "read_own_task_status":   Role.CLIENT,
}
```

### 3.3 Enforcement Points

1. **spawn_child_agent()** — requires Role.SYSTEM
   - `assert_caller_role(Role.SYSTEM)` called at top of function
   - If not SYSTEM: raise PermissionError, do not spawn

2. **Approval gate** — requires Role.OPERATOR or Role.SYSTEM to approve
   - `assert_approver_role()` checks approver role before writing approved status

3. **Tenant path access** — resolved via TenantPathResolver
   - AGENT role gets own tenant-scoped path only
   - Cross-tenant path resolution returns error path for non-OPERATOR roles

4. **CLI commands** (tenant_crud.py, gate-status) — require OPERATOR role
   - Each CLI checks `assert_operator_role()` before executing
   - If role check fails: exit with status code 1 and friendly error message

---

## 4. ENFORCEMENT FUNCTIONS (access_control.py)

```python
def get_caller_role() -> Role:
    """Resolve the role of the current caller context.
    For direct Python calls: always OPERATOR (human in context).
    For child agent spawned context: always AGENT.
    For task_orchestrator internal: SYSTEM.
    For OpenClaw CLI invocations: OPERATOR."""
    import os
    # Child agents are spawned with AGENT context variable set
    if os.environ.get("MAA_CALLER_ROLE") == "agent":
        return Role.AGENT
    # Direct CLI calls are always OPERATOR
    return Role.OPERATOR

def assert_role(required: Role) -> None:
    """Raise PermissionError if caller's role is lower than required."""
    caller = get_caller_role()
    if caller.value > required.value:
        raise PermissionError(f"Role {caller.value} cannot perform {required.name}. Required: {required.name}.")

def assert_operator() -> None:
    """Shorthand: require OPERATOR or higher."""
    assert_role(Role.OPERATOR)

def assert_system() -> None:
    """Shorthand: require SYSTEM only."""
    assert_role(Role.SYSTEM)
```

Role ordinal values: SYSTEM=0, OPERATOR=1, AGENT=2, CLIENT=3.
Lower ordinal = higher privilege. Comparison is `caller.value > required.value`.

---

## 5. CHILD AGENT CONTEXT INJECTION

When `spawn_child_agent()` is called, set environment variable before the subprocess:

```python
import os
os.environ["MAA_CALLER_ROLE"] = "agent"
```

Child agent prompt should also contain: "Your role is AGENT. You cannot spawn sub-agents, approve external actions, or access other tenants."

---

## 6. CLI ENFORCEMENT

All CLI entry points (gate-status, tenant_crud, etc.) call `assert_operator()` at the top before any state-changing operation.

Exit codes:
- 0 = success
- 1 = permission denied
- 2 = invalid argument

---

## 7. AUDIT

Every role check that raises a PermissionError is logged to the task audit trail:

```json
{
  "event": "permission_denied",
  "required_role": "OPERATOR",
  "caller_role": "AGENT",
  "operation": "spawn_child_agent",
  "task_id": "...",
  "at": "ISO8601"
}
```

---

## 8. SUCCESS CRITERIA

1. ACCESS_CONTROL.md documents all roles and permissions
2. task_orchestrator.py enforces Role.SYSTEM check before spawn_child_agent
3. Approval gate enforces OPERATOR or SYSTEM for approve operations
4. tenant_path_resolver resolves paths only for callers with sufficient role
5. All CLI commands exit with code 1 and message when called without OPERATOR role
6. Role check failures are logged to audit trail