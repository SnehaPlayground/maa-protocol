"""Tenant isolation, RBAC access control, and tenant-level resource gates."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from ..exceptions import TenantAccessError


class TenantContext(BaseModel):
    """Validated tenant identity used by the governance wrapper."""

    model_config = ConfigDict(frozen=True)

    tenant_id: str
    operator_id: str
    client_id: str
    user_role: str = "viewer"
    tenant_tier: str = "standard"
    isolation_level: str = "strict"
    budget_usd: float = 50.0
    permissions: set[str] = Field(default_factory=set)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "tenant_id",
        "operator_id",
        "client_id",
        "user_role",
        "tenant_tier",
        "isolation_level",
    )
    @classmethod
    def _non_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value

    @field_validator("budget_usd")
    @classmethod
    def _budget_must_be_finite(cls, value: float) -> float:
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("budget_usd must be finite")
        return value

    @classmethod
    def from_config(cls, config: Mapping[str, Any] | None = None) -> TenantContext:
        payload = dict(config or {})
        required = ("tenant_id", "operator_id", "client_id")
        missing = [key for key in required if not str(payload.get(key, "")).strip()]
        if missing:
            missing_csv = ", ".join(missing)
            raise ValueError(f"Missing required tenant config: {missing_csv}")

        known = {
            "tenant_id",
            "operator_id",
            "client_id",
            "user_role",
            "tenant_tier",
            "isolation_level",
            "budget_usd",
            "permissions",
            "metadata",
        }
        metadata = dict(payload.get("metadata") or {})
        metadata.update({key: value for key, value in payload.items() if key not in known})

        try:
            return cls.model_validate(
                {
                    "tenant_id": payload["tenant_id"],
                    "operator_id": payload["operator_id"],
                    "client_id": payload["client_id"],
                    "user_role": payload.get("user_role", "viewer"),
                    "tenant_tier": payload.get("tenant_tier", "standard"),
                    "isolation_level": payload.get("isolation_level", "strict"),
                    "budget_usd": payload.get("budget_usd", 50.0),
                    "permissions": payload.get("permissions") or [],
                    "metadata": metadata,
                }
            )
        except ValidationError as exc:
            raise ValueError(f"Invalid tenant config: {exc}") from exc

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="python")


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
        payload = dict(config or {})
        role = str(payload.get("user_role") or (tenant.user_role if tenant else "viewer"))
        required = str(payload.get("required_permission", "invoke"))
        permissions = set(self.role_permissions.get(role, set()))
        if tenant is not None:
            permissions |= set(tenant.permissions)
        if required not in permissions:
            raise TenantAccessError(f"Role '{role}' missing required permission '{required}'")
        return {
            "role": role,
            "required_permission": required,
            "permissions": sorted(permissions),
            "allowed": True,
        }


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
        payload = dict(config or {})
        current_state = dict(state or {})
        limits = dict(self.tenant_limits.get(tenant.tenant_id, {}))
        max_cost = limits.get("max_cost_per_invoke", self.max_cost_per_invoke)
        max_tasks = limits.get("max_concurrent_tasks", self.max_concurrent_tasks)
        observed_cost = float(
            payload.get(
                "cost_usd",
                current_state.get("cost_usd", current_state.get("total_cost", 0.0)),
            )
        )
        active_tasks = int(payload.get("active_tasks", current_state.get("_active_task_count", 0)))

        if max_cost is not None and observed_cost > float(max_cost):
            raise TenantAccessError("cost_limit_exceeded")
        if max_tasks is not None and active_tasks >= int(max_tasks):
            raise TenantAccessError("concurrent_limit_exceeded")

        return {
            "tenant_id": tenant.tenant_id,
            "observed_cost_usd": observed_cost,
            "active_tasks": active_tasks,
            "max_cost_per_invoke": max_cost,
            "max_concurrent_tasks": max_tasks,
        }
