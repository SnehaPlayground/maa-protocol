from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..exceptions import CostLimitExceededError


@dataclass(slots=True)
class CostGuard:
    default_budget_usd: float = 50.0
    hard_limit_usd: float | None = None
    soft_limit_ratio: float = 0.8

    def enforce(self, state: Mapping[str, Any] | None, tenant: Any, config: Mapping[str, Any] | None = None) -> dict[str, Any]:
        state = dict(state or {})
        config = dict(config or {})
        usage = float(config.get("cost_usd", state.get("cost_usd", state.get("total_cost", 0.0))))
        budget = float(config.get("budget_usd", getattr(tenant, "budget_usd", self.default_budget_usd) or self.default_budget_usd))
        hard_limit = float(config.get("hard_limit_usd", self.hard_limit_usd if self.hard_limit_usd is not None else budget))
        soft_limit = budget * self.soft_limit_ratio
        over_soft = usage >= soft_limit
        over_hard = usage > hard_limit
        if over_hard:
            raise CostLimitExceededError(f"Hard cost limit exceeded: usage={usage:.4f}, limit={hard_limit:.4f}")
        return {
            "cost_usd": usage,
            "budget_usd": budget,
            "hard_limit_usd": hard_limit,
            "soft_limit_usd": soft_limit,
            "soft_limit_reached": over_soft,
            "hard_limit_reached": over_hard,
        }
