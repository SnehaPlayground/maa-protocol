"""Cost guard for tenant-scoped budget enforcement."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from ..exceptions import CostLimitExceededError, CostValidationError


class CostGuardConfig(BaseModel):
    """Validated static configuration for :class:`CostGuard`."""

    model_config = ConfigDict(frozen=True)

    default_budget_usd: float = Field(default=50.0, gt=0.0)
    hard_limit_usd: float | None = Field(default=None, ge=0.0)
    soft_limit_ratio: float = Field(default=0.8, ge=0.0, le=1.0)

    @field_validator("default_budget_usd", "hard_limit_usd")
    @classmethod
    def _finite(cls, value: float | None) -> float | None:
        if value is not None and not isfinite(value):
            raise ValueError("must be finite")
        return value


@dataclass(slots=True)
class CostGuard:
    default_budget_usd: float = 50.0
    hard_limit_usd: float | None = None
    soft_limit_ratio: float = 0.8

    def __post_init__(self) -> None:
        try:
            config = CostGuardConfig(
                default_budget_usd=self.default_budget_usd,
                hard_limit_usd=self.hard_limit_usd,
                soft_limit_ratio=self.soft_limit_ratio,
            )
        except ValidationError as exc:
            raise CostValidationError(str(exc)) from exc
        self.default_budget_usd = config.default_budget_usd
        self.hard_limit_usd = config.hard_limit_usd
        self.soft_limit_ratio = config.soft_limit_ratio

    def enforce(
        self,
        state: Mapping[str, Any] | None,
        tenant: Any,
        config: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = dict(config or {})
        current_state = dict(state or {})

        usage_value = payload.get(
            "cost_usd",
            current_state.get("cost_usd", current_state.get("total_cost", 0.0)),
        )
        usage = self._coerce_non_negative(usage_value, "cost_usd")
        budget_value = payload.get(
            "budget_usd",
            getattr(tenant, "budget_usd", self.default_budget_usd),
        )
        budget = self._coerce_non_negative(budget_value, "budget_usd")
        if budget <= 0:
            raise CostValidationError("Effective budget_usd must be > 0")

        hard_limit_raw = payload.get("hard_limit_usd")
        if hard_limit_raw is None:
            hard_limit_raw = self.hard_limit_usd if self.hard_limit_usd is not None else budget
        hard_limit = self._coerce_non_negative(hard_limit_raw, "hard_limit_usd")
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

    @staticmethod
    def _coerce_non_negative(value: Any, field_name: str) -> float:
        if value is None:
            raise CostValidationError(f"{field_name} may not be None")
        try:
            numeric = float(value)
        except (TypeError, ValueError) as exc:
            raise CostValidationError(
                f"{field_name} must be a numeric value; got {value!r}"
            ) from exc
        if not isfinite(numeric) or numeric < 0:
            raise CostValidationError(
                f"{field_name} must be non-negative and finite; got {numeric}"
            )
        return numeric
