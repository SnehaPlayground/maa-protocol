from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Mapping

from .tenant_context import TenantContext


@dataclass
class CanaryRouter:
    stable_version: str = "stable"
    canary_version: str = "canary"
    traffic_split: float = 0.0

    def choose_version(self, state: Mapping[str, Any] | None, tenant: TenantContext, config: Mapping[str, Any] | None = None) -> str:
        config = dict(config or {})
        if "agent_version" in config:
            return str(config["agent_version"])
        key = str(config.get("canary_key") or self._default_key(state, tenant))
        bucket = self._bucket(key)
        return self.canary_version if bucket < self.traffic_split else self.stable_version

    def route_metadata(self, state: Mapping[str, Any] | None, tenant: TenantContext, config: Mapping[str, Any] | None = None) -> dict[str, Any]:
        version = self.choose_version(state, tenant, config)
        return {
            "selected_version": version,
            "stable_version": self.stable_version,
            "canary_version": self.canary_version,
            "traffic_split": self.traffic_split,
            "is_canary": version == self.canary_version,
        }

    def _default_key(self, state: Mapping[str, Any] | None, tenant: TenantContext) -> str:
        state = dict(state or {})
        messages = state.get("messages")
        if isinstance(messages, list) and messages:
            return f"{tenant.tenant_id}:{messages[0]}"
        return tenant.tenant_id

    @staticmethod
    def _bucket(key: str) -> float:
        digest = hashlib.sha256(key.encode()).hexdigest()
        value = int(digest[:8], 16)
        return value / 0xFFFFFFFF
