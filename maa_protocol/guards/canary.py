from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Mapping


@dataclass(slots=True)
class CanaryRouter:
    stable_version: str = "stable"
    canary_version: str = "canary"
    traffic_split: float = 0.0

    def __post_init__(self) -> None:
        if not (0.0 <= self.traffic_split <= 1.0):
            raise ValueError(
                f"traffic_split must be between 0.0 and 1.0, got {self.traffic_split}"
            )

    def route_metadata(self, state: Mapping[str, Any] | None, tenant: Any, config: Mapping[str, Any] | None = None) -> dict[str, Any]:
        state = dict(state or {})
        config = dict(config or {})
        key = str(config.get("routing_key") or state.get("routing_key") or getattr(tenant, "tenant_id", "default"))
        bucket = self._bucket(key)
        selected = self.canary_version if bucket < self.traffic_split else self.stable_version
        return {
            "selected_version": selected,
            "stable_version": self.stable_version,
            "canary_version": self.canary_version,
            "traffic_split": self.traffic_split,
            "routing_key": key,
            "bucket": bucket,
        }

    @staticmethod
    def _bucket(key: str) -> float:
        digest = sha256(key.encode()).hexdigest()
        value = int(digest[:8], 16)
        return value / 0xFFFFFFFF
