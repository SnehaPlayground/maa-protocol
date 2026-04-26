"""
access_control.py — MAA Protocol RBAC Runtime Enforcement
Version: v1.1 | Date: 2026-04-22

Enforces role-based access control for all sensitive Maa operations.
Role hierarchy (lower ordinal = higher privilege):
  SYSTEM(0) > OPERATOR(1) > AGENT(2) > CLIENT(3)

Import note: This file lives in ops/multi-agent-orchestrator/ alongside
tenant_context.py, tenant_paths.py, tenant_gate.py. Use relative imports
(direct module names, no "ops.multi_agent_orchestrator." prefix) for all
co-located imports. The workspace uses symlinked subdirectories, not packages.
"""

import os
import json
import traceback
from enum import Enum
from pathlib import Path
from typing import Optional


class Role(Enum):
    SYSTEM = 0
    OPERATOR = 1
    AGENT = 2
    CLIENT = 3

    def __ge__(self, other: "Role") -> bool:
        return self.value >= other.value

    def __gt__(self, other: "Role") -> bool:
        return self.value > other.value

    def __le__(self, other: "Role") -> bool:
        return self.value <= other.value

    def __lt__(self, other: "Role") -> bool:
        return self.value < other.value


# ── Role Resolution ────────────────────────────────────────────────────────────

def get_caller_role() -> Role:
    """Resolve the role of the current caller context.

    Child agents are spawned with MAA_CALLER_ROLE=agent in environment.
    Direct Python calls (operator context) default to OPERATOR.
    task_orchestrator internal calls must set MAA_CALLER_ROLE=system before
    calling any require_* function — see spawn_child_agent() for pattern.
    """
    role_env = os.environ.get("MAA_CALLER_ROLE", "").lower()
    if role_env == "system":
        return Role.SYSTEM
    elif role_env == "agent":
        return Role.AGENT
    elif role_env == "operator":
        return Role.OPERATOR
    elif role_env == "client":
        return Role.CLIENT
    # Default: OPERATOR (human in context)
    return Role.OPERATOR


# ── Tenant context helper (co-located import) ─────────────────────────────────

def _parse_tenant_str(tenant_id: str):
    """Parse 'operator/client' string into TenantContext (same dir, no pkg prefix)."""
    from tenant_context import parse_tenant_context, DEFAULT_TENANT
    if not tenant_id or tenant_id == "default" or tenant_id == "default/default":
        return DEFAULT_TENANT
    if '/' in tenant_id:
        op, cl = tenant_id.split('/', 1)
        return parse_tenant_context({"operator_id": op, "client_id": cl})
    return parse_tenant_context({"operator_id": tenant_id, "client_id": tenant_id})


def get_task_audit_path(task_id: str, tenant_id: Optional[str] = None) -> Path:
    """Return the audit log path for a given task_id."""
    from tenant_paths import TenantPathResolver
    if tenant_id:
        tc = _parse_tenant_str(tenant_id)
    else:
        from tenant_context import DEFAULT_TENANT
        tc = DEFAULT_TENANT
    resolver = TenantPathResolver(tc)
    audit_dir = resolver.resolve("audit")
    return audit_dir / f"{task_id}.audit.jsonl"


def _log_permission_denied(operation: str, required: Role, task_id: Optional[str] = None) -> None:
    """Append a permission denied event to the audit trail."""
    caller = get_caller_role()
    entry = {
        "event": "permission_denied",
        "operation": operation,
        "required_role": required.name,
        "caller_role": caller.name,
        "task_id": task_id,
        "trace": traceback.format_exc(),
        "at": __import__("datetime").datetime.now().isoformat() + "Z",
    }
    try:
        audit_path = get_task_audit_path(task_id or "system")
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        with open(audit_path, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass  # Never fail on audit logging itself


# ── Core Enforcement ──────────────────────────────────────────────────────────

def assert_role(required: Role, operation: str = "unknown", task_id: Optional[str] = None) -> None:
    """Raise PermissionError if caller role is lower (less privileged) than required.

    Role privilege ordinals: SYSTEM=0 (highest) → OPERATOR=1 → AGENT=2 → CLIENT=3 (lowest).
    If caller ordinal > required ordinal → caller has less privilege → deny.
    If caller ordinal <= required ordinal → caller has equal or higher privilege → allow.
    """
    caller = get_caller_role()
    if caller.value > required.value:  # caller is less privileged than required
        _log_permission_denied(operation, required, task_id)
        raise PermissionError(
            f"Maa RBAC: role {caller.name} cannot perform '{operation}'. "
            f"Required: {required.name} or higher."
        )


def assert_system(operation: str = "unknown", task_id: Optional[str] = None) -> None:
    """Require SYSTEM role (Mother Agent internal only)."""
    assert_role(Role.SYSTEM, operation, task_id)


def assert_operator(operation: str = "unknown", task_id: Optional[str] = None) -> None:
    """Require OPERATOR or SYSTEM (human operator)."""
    assert_role(Role.OPERATOR, operation, task_id)


def assert_minimum(role: Role, operation: str = "unknown", task_id: Optional[str] = None) -> None:
    """Require a specific minimum role."""
    assert_role(role, operation, task_id)


# ── Pre-built operation checks ─────────────────────────────────────────────────

def require_spawn_child_agent(task_id: Optional[str] = None) -> None:
    """Only SYSTEM (Mother Agent) can spawn child agents."""
    assert_system("spawn_child_agent", task_id)


def require_approve_external_action(task_id: Optional[str] = None) -> None:
    """OPERATOR or SYSTEM only."""
    assert_operator("approve_external_action", task_id)


def require_delete_tenant_data(task_id: Optional[str] = None) -> None:
    """OPERATOR or SYSTEM only."""
    assert_operator("delete_tenant_data", task_id)


def require_create_tenant(task_id: Optional[str] = None) -> None:
    """OPERATOR or SYSTEM only."""
    assert_operator("create_tenant", task_id)


def require_deactivate_tenant(task_id: Optional[str] = None) -> None:
    """OPERATOR or SYSTEM only."""
    assert_operator("deactivate_tenant", task_id)


def require_view_all_metrics(task_id: Optional[str] = None) -> None:
    """OPERATOR or SYSTEM only."""
    assert_operator("view_all_metrics", task_id)


def require_submit_task(task_id: Optional[str] = None) -> None:
    """OPERATOR or SYSTEM only."""
    assert_operator("submit_task", task_id)


def require_run_pre_deploy_gate(task_id: Optional[str] = None) -> None:
    """OPERATOR or SYSTEM only."""
    assert_operator("run_pre_deploy_gate", task_id)


# ── Tenant Path Resolution with Role ─────────────────────────────────────────

def resolve_path_for_caller(caller_role: Role, tenant_id: str, path_type: str) -> str:
    """Resolve a tenant-scoped path if the caller has sufficient role.

    Args:
        caller_role: Role of the requesting entity
        tenant_id: operator/client or 'default/default'
        path_type: 'tasks' | 'logs' | 'outputs' | 'metrics' | 'audit'
    Returns:
        Resolved absolute path as string, or empty string if role insufficient.
    """
    # Enforce minimum role: OPERATOR or higher (SYSTEM, OPERATOR)
    if caller_role.value > Role.OPERATOR.value:
        _log_permission_denied(f"resolve_path:{path_type}", Role.OPERATOR)
        return ""
    from tenant_paths import TenantPathResolver
    tc = _parse_tenant_str(tenant_id)
    resolver = TenantPathResolver(tc)
    if path_type == "tasks":
        return str(resolver.resolve("tasks"))
    elif path_type == "logs":
        return str(resolver.resolve("logs"))
    elif path_type == "outputs":
        return str(resolver.resolve("outputs"))
    elif path_type == "metrics":
        return str(resolver.resolve("metrics"))
    elif path_type == "audit":
        return str(resolver.resolve("audit"))
    return ""


# ── CLI helper ────────────────────────────────────────────────────────────────

def require_operator_role() -> None:
    """For CLI entry points. Exits with code 1 if not OPERATOR or higher."""
    # Use .value directly so CLI enforcement matches the documented ordinal model
    # (lower ordinal = higher privilege; AGENT=2 or CLIENT=3 are less privileged than OPERATOR=1).
    if get_caller_role().value > Role.OPERATOR.value:
        _log_permission_denied("cli:require_operator_role", Role.OPERATOR)
        print("ERROR: This command requires OPERATOR role.", file=__import__("sys").stderr)
        print("       Contact your Maa operator if you need access.", file=__import__("sys").stderr)
        raise SystemExit(1)


# ── Context manager for SYSTEM role in Mother Agent ───────────────────────────

class SystemRole:
    """Context manager: temporarily set MAA_CALLER_ROLE=system for a block.

    Usage:
        with SystemRole():
            require_spawn_child_agent(task_id)  # → passes because caller is SYSTEM

    Pattern needed in task_orchestrator.py before calling any require_* function
    that requires SYSTEM role. Restore happens on exit or on exception.
    """
    def __enter__(self):
        self._original = os.environ.get("MAA_CALLER_ROLE")
        os.environ["MAA_CALLER_ROLE"] = "system"
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._original is None:
            os.environ.pop("MAA_CALLER_ROLE", None)
        else:
            os.environ["MAA_CALLER_ROLE"] = self._original
        return False  # don't suppress exceptions


if __name__ == "__main__":
    # Smoke test
    print(f"Current role: {get_caller_role().name}")
    print("ACCESS_CONTROL.py v1.1 loaded OK")