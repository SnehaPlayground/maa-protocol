"""Canary routing guard."""

from __future__ import annotations

import random
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class CanaryRouter:
    stable_version: str = "v1"
    canary_version: str = "v2"
    traffic_split: float = 0.1

    def __post_init__(self) -> None:
        if not 0.0 <= float(self.traffic_split) <= 1.0:
            raise ValueError("traffic_split must be in [0.0, 1.0]")

    def route_metadata(
        self,
        state: Mapping[str, Any] | None,
        tenant: Any,
        config: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        current_state = dict(state or {})
        selected = self.stable_version
        if self.traffic_split > 0:
            seed_basis = "::".join(
                [
                    getattr(tenant, "tenant_id", "tenant"),
                    str(current_state.get("action", "")),
                    str(current_state.get("operator_id", "")),
                ]
            )
            rng = random.Random(seed_basis)
            if rng.random() < self.traffic_split:
                selected = self.canary_version
        return {
            "selected_version": selected,
            "stable_version": self.stable_version,
            "canary_version": self.canary_version,
            "traffic_split": self.traffic_split,
        }
