from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .tenant_context import TenantContext


class BudgetExceededError(RuntimeError):
    pass


@dataclass
class CostGuard:
    """Tracks simple per-tenant budgets for governed LangGraph invocations."""

    budget_per_tenant: float | None = None
    default_budget: float | None = None
    tenant_budgets: dict[str, float] = field(default_factory=dict)
    alert_threshold: float = 0.8

    def budget_for(self, tenant: TenantContext, config: Mapping[str, Any] | None = None) -> float | None:
        config = dict(config or {})
        if "max_cost" in config and config["max_cost"] is not None:
            return float(config["max_cost"])
        if tenant.tenant_id in self.tenant_budgets:
            return float(self.tenant_budgets[tenant.tenant_id])
        if self.budget_per_tenant is not None:
            return float(self.budget_per_tenant)
        if self.default_budget is not None:
            return float(self.default_budget)
        return None

    def current_cost(self, state: Mapping[str, Any] | None) -> float:
        state = dict(state or {})
        value = state.get("total_cost", state.get("cost", 0.0))
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def enforce(self, state: Mapping[str, Any] | None, tenant: TenantContext, config: Mapping[str, Any] | None = None) -> dict[str, Any]:
        cost = self.current_cost(state)
        budget = self.budget_for(tenant, config)
        if budget is not None and cost > budget:
            raise BudgetExceededError(
                f"Tenant '{tenant.tenant_id}' exceeded budget: cost={cost:.4f}, budget={budget:.4f}"
            )
        ratio = (cost / budget) if budget not in (None, 0) else 0.0
        return {
            "tenant_id": tenant.tenant_id,
            "current_cost": cost,
            "budget": budget,
            "alert": bool(budget is not None and ratio >= self.alert_threshold),
            "ratio": ratio,
        }
