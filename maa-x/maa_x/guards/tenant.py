"""Tenant isolation, RBAC access control, and tenant-level resource gates."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ..exceptions import TenantAccessError


@dataclass(slots=True)
class TenantContext:
    tenant_id: str = "default"
    operator_id: str = "unknown"
    client_id: str = "unknown"
    user_role: str = "viewer"
    tenant_tier: str = "standard"
    isolation_level: str = "strict"
    budget_usd: float = 50.0
    permissions: set[str] = field(default_factory=set)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_config(cls, config: Mapping[str, Any] | None = None) -> "TenantContext":
        config = dict(config or {})
        known = {
            "tenant_id", "operator_id", "client_id", "user_role",
            "tenant_tier", "isolation_level", "budget_usd", "permissions",
        }
        metadata = {k: v for k, v in config.items() if k not in known}
        permissions = config.get("permissions") or []
        return cls(
            tenant_id=str(config.get("tenant_id", "default")),
            operator_id=str(config.get("operator_id", "unknown")),
            client_id=str(config.get("client_id", "unknown")),
            user_role=str(config.get("user_role", "viewer")),
            tenant_tier=str(config.get("tenant_tier", "standard")),
            isolation_level=str(config.get("isolation_level", "strict")),
            budget_usd=float(config.get("budget_usd", 50.0)),
            permissions={str(item) for item in permissions},
            metadata=metadata,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "operator_id": self.operator_id,
            "client_id": self.client_id,
            "user_role": self.user_role,
            "tenant_tier": self.tenant_tier,
            "isolation_level": self.isolation_level,
            "budget_usd": self.budget_usd,
            "permissions": sorted(self.permissions),
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class AccessControl:
    role_permissions: dict[str, set[str]] = field(
        default_factory=lambda: {
            "admin": {"invoke", "approve", "manage_tenants"},
            "operator": {"invoke", "approve"},
            "analyst": {"invoke"},
            "viewer": set(),
        }
    )

    def enforce(
        self,
        config: Mapping[str, Any] | None = None,
        tenant: TenantContext | None = None,
    ) -> dict[str, Any]:
        config = dict(config or {})
        role = str(config.get("user_role") or (tenant.user_role if tenant else "viewer"))
        required = str(config.get("required_permission", "invoke"))
        permissions = set(self.role_permissions.get(role, set())) | (tenant.permissions if tenant else set())
        allowed = required in permissions
        if not allowed:
            raise TenantAccessError(f"Role '{role}' missing required permission '{required}'")
        return {"role": role, "required_permission": required, "allowed": allowed, "permissions": sorted(permissions)}


@dataclass(slots=True)
class TenantGate:
    max_cost_per_invoke: float | None = None
    max_concurrent_tasks: int | None = None
    tenant_limits: dict[str, dict[str, Any]] = field(default_factory=dict)

    def enforce(
        self,
        state: Mapping[str, Any] | None,
        tenant: TenantContext,
        config: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        state = dict(state or {})
        config = dict(config or {})
        limits = dict(self.tenant_limits.get(tenant.tenant_id, {}))
        max_cost = limits.get("max_cost_per_invoke", self.max_cost_per_invoke)
        concurrent_limit = limits.get("max_concurrent_tasks", self.max_concurrent_tasks)
        observed_cost = float(config.get("cost_usd", state.get("cost_usd", state.get("total_cost", 0.0))))
        active_tasks = int(config.get("active_tasks", state.get("_active_task_count", 0)))
        if max_cost is not None and observed_cost > float(max_cost):
            raise TenantAccessError("cost_limit_exceeded")
        if concurrent_limit is not None and active_tasks >= int(concurrent_limit):
            raise TenantAccessError("concurrent_limit_exceeded")
        return {
            "tenant_id": tenant.tenant_id,
            "max_cost_per_invoke": max_cost,
            "max_concurrent_tasks": concurrent_limit,
            "observed_cost_usd": observed_cost,
            "active_tasks": active_tasks,
        }