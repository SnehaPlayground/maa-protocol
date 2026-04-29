"""Canary routing guard — splits traffic between stable and canary versions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
import random


@dataclass(slots=True)
class CanaryRouter:
    stable_version: str = "v1"
    canary_version: str = "v2"
    traffic_split: float = 0.1

    def route_metadata(
        self,
        state: Mapping[str, Any] | None,
        tenant: Any,
        config: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        selected = self.stable_version
        if self.traffic_split > 0:
            seed = hash(str(state)) % 10000
            rng = random.Random(seed)
            if rng.random() < self.traffic_split:
                selected = self.canary_version
        return {
            "selected_version": selected,
            "stable_version": self.stable_version,
            "canary_version": self.canary_version,
            "traffic_split": self.traffic_split,
        }