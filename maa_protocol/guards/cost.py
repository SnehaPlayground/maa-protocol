"""Cost guard — enforces budget limits per tenant.

Trust model
───────────
``cost_usd`` read from *state* or *config* is treated as **untrusted input**.
The caller (GovernanceWrapper) is responsible for computing it server-side
from authoritative usage logs before passing it in.

This module does not fetch live market data or external prices.
All monetary values are in USD.

Expected shapes
───────────────
state: {
    "cost_usd": float,          # optional; defaults to 0.0
    "total_cost": float,         # optional; alias for cost_usd
    ...
}
config: {
    "cost_usd": float,           # optional; overrides state value
    "budget_usd": float,         # optional; overrides tenant budget
    "hard_limit_usd": float,     # optional; overrides instance hard_limit_usd
    ...
}
tenant: TenantContext (or any object with ``budget_usd`` attribute)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..exceptions import CostLimitExceededError


class CostValidationError(ValueError):
    """Raised when a CostGuard parameter or input value is invalid."""


def _float_or_die(value: Any, field_name: str) -> float:
    """Convert *value* to float; raise CostValidationError on failure or negativity."""
    if value is None:
        raise CostValidationError(f"{field_name} may not be None")
    try:
        f = float(value)
    except (TypeError, ValueError) as exc:
        raise CostValidationError(
            f"{field_name} must be a numeric value; got {value!r}"
        ) from exc
    if f < 0:
        raise CostValidationError(
            f"{field_name} must be non-negative; got {f}"
        )
    return f


@dataclass(slots=True)
class CostGuard:
    """Enforce per-tenant cost and budget limits.

    Parameters
    ----------
    default_budget_usd : float
        Budget assigned when no tenant budget is available (default: $50).
    hard_limit_usd : float | None
        Absolute ceiling on cost per invocation. None means no ceiling beyond
        ``budget_usd`` (default: None).
    soft_limit_ratio : float
        Ratio of ``budget_usd`` at which a soft-limit warning is triggered.
        Must be in ``[0.0, 1.0]`` (default: 0.8 = 80 %).

    Attributes
    ----------
    enforce() returns a dict with keys:
        cost_usd, budget_usd, hard_limit_usd, soft_limit_usd,
        soft_limit_reached (bool), hard_limit_reached (bool)
    """

    default_budget_usd: float = 50.0
    hard_limit_usd: float | None = None
    soft_limit_ratio: float = 0.8

    def __post_init__(self) -> None:
        # Validate all configurable float fields.
        _ = _float_or_die(self.default_budget_usd, "default_budget_usd")
        if self.hard_limit_usd is not None:
            _ = _float_or_die(self.hard_limit_usd, "hard_limit_usd")
        if not (0.0 <= self.soft_limit_ratio <= 1.0):
            raise CostValidationError(
                f"soft_limit_ratio must be in [0.0, 1.0]; got {self.soft_limit_ratio}"
            )

    def enforce(
        self,
        state: Mapping[str, Any] | None,
        tenant: Any,
        config: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Validate cost inputs and enforce limits.

        Raises
        ------
        CostValidationError
            If any numeric input is negative, None, or non-finite.
        CostLimitExceededError
            If usage exceeds the hard limit.
        """
        state = dict(state or {})
        config = dict(config or {})

        # ---- Parse & validate usage -------------------------------------- #
        raw_usage = config.get("cost_usd", state.get("cost_usd", state.get("total_cost", 0.0)))
        usage = _float_or_die(raw_usage, "cost_usd")

        # ---- Parse & validate budget ------------------------------------ #
        # Use getattr safely; distinguish "unset" from 0.0 so 0.0 budgets fail.
        raw_budget = config.get(
            "budget_usd",
            getattr(tenant, "budget_usd", self.default_budget_usd),
        )
        budget = _float_or_die(raw_budget, "budget_usd")
        if budget <= 0:
            raise CostValidationError(
                f"Effective budget_usd must be > 0; got {budget}. "
                "Check tenant budget configuration."
            )

        # ---- Parse & validate hard limit --------------------------------- #
        # Resolve effective hard limit: prefer an explicit value, else fall back
        # to the instance hard_limit_usd, else budget. "None" means "no override" and
        # should fall through to the next candidate, not trigger a validation error.
        hard_limit: float
        if self.hard_limit_usd is not None:
            hard_limit_raw = self.hard_limit_usd
        elif config.get("hard_limit_usd") is not None:
            hard_limit_raw = config["hard_limit_usd"]
        else:
            hard_limit_raw = budget  # default ceiling = full budget

        try:
            if hard_limit_raw is None:
                hard_limit = budget
            else:
                hard_limit = float(hard_limit_raw)
        except (TypeError, ValueError) as exc:
            raise CostValidationError(
                f"hard_limit_usd must be numeric; got {hard_limit_raw!r}"
            ) from exc
        if not (0.0 <= hard_limit):
            raise CostValidationError("hard_limit_usd must be non-negative")

        # ---- Derived soft limit ------------------------------------------ #
        soft_limit = budget * self.soft_limit_ratio
        soft_limit_reached = usage >= soft_limit
        hard_limit_reached = usage > hard_limit

        if hard_limit_reached:
            raise CostLimitExceededError(
                f"Hard cost limit exceeded: usage={usage:.4f}, limit={hard_limit:.4f}"
            )

        return {
            "cost_usd": usage,
            "budget_usd": budget,
            "hard_limit_usd": hard_limit,
            "soft_limit_usd": soft_limit,
            "soft_limit_reached": soft_limit_reached,
            "hard_limit_reached": hard_limit_reached,
        }
