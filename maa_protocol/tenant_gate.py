from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping


class TenantGateError(RuntimeError):
    pass


@dataclass
class TenantGate:
    """Enforces tenant-level isolation and resource limits for governed invocations.

    Acts as the hard isolation boundary — if a tenant's context or state violates
    the configured limits, execution is halted before the wrapped app runs.
    """

    max_concurrent_tasks: int | None = None
    max_cost_per_invoke: float | None = None
    tenant_limits: dict[str, dict[str, Any]] = field(default_factory=dict)
    block_on_isolation_violation: bool = True

    def evaluate(self, state: Mapping[str, Any] | None, tenant: Any, config: Mapping[str, Any] | None = None) -> dict[str, Any]:
        state = dict(state or {})
        config = dict(config or {})
        tenant_id = getattr(tenant, "tenant_id", "default") or "default"

        # Tenant-specific overrides
        tenant_limit = self.tenant_limits.get(tenant_id, {})

        max_concurrent = (
            tenant_limit["max_concurrent_tasks"]
            if "max_concurrent_tasks" in tenant_limit
            else self.max_concurrent_tasks
        )
        max_cost = (
            tenant_limit["max_cost_per_invoke"]
            if "max_cost_per_invoke" in tenant_limit
            else self.max_cost_per_invoke
        )

        violations: list[str] = []

        # Check cost per invoke
        if max_cost is not None:
            cost = float(state.get("total_cost", state.get("cost", 0.0)))
            if cost > max_cost:
                violations.append(f"cost_limit_exceeded: {cost:.4f} > {max_cost:.4f}")

        # Check concurrent task limit (stateless heuristic based on state flags)
        if max_concurrent is not None:
            active = int(state.get("_active_task_count", 0))
            if active >= max_concurrent:
                violations.append(f"concurrent_limit_exceeded: {active} >= {max_concurrent}")

        # Check isolation requirements
        isolation_level = str(getattr(tenant, "isolation_level", "full"))
        if isolation_level == "full":
            # Full isolation: ensure tenant_id is set and non-default for non-default operators
            if tenant_id == "default" and not getattr(tenant, "is_default", lambda: False)():
                violations.append("isolation_requires_named_tenant")

        # Check tenant tier
        tier = str(getattr(tenant, "tenant_tier", "operator"))
        if tier == "client":
            # Client tenants have stricter limits
            client_limit = tenant_limit.get("max_client_tasks", 3)
            if client_limit is not None:
                active = int(state.get("_active_task_count", 0))
                if active >= client_limit:
                    violations.append(f"client_task_limit_exceeded: {active} >= {client_limit}")

        allowed = len(violations) == 0

        return {
            "tenant_id": tenant_id,
            "violations": violations,
            "allowed": allowed,
            "isolation_level": isolation_level,
            "tenant_tier": tier,
            "max_cost": max_cost,
            "max_concurrent": max_concurrent,
        }

    def enforce(self, state: Mapping[str, Any] | None, tenant: Any, config: Mapping[str, Any] | None = None) -> dict[str, Any]:
        result = self.evaluate(state, tenant, config)
        if not result["allowed"] and self.block_on_isolation_violation:
            raise TenantGateError(
                f"TenantGate blocked invoke for tenant '{result['tenant_id']}': "
                + "; ".join(result["violations"])
            )
        return result


@dataclass
class TenantGateRegistry:
    """Registry to track active tasks per tenant for concurrent limit enforcement."""

    _active: dict[str, int] = field(default_factory=dict, repr=False)

    def register(self, tenant_id: str) -> None:
        self._active[tenant_id] = self._active.get(tenant_id, 0) + 1

    def unregister(self, tenant_id: str) -> None:
        current = self._active.get(tenant_id, 0)
        self._active[tenant_id] = max(0, current - 1)

    def active_count(self, tenant_id: str) -> int:
        return self._active.get(tenant_id, 0)
