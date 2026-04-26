from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Any, Mapping


@dataclass(frozen=True)
class TenantContext:
    """Lightweight tenant context for LangGraph-facing governance."""

    tenant_id: str = "default"
    operator_id: str = "default"
    client_id: str = "default"
    user_role: str = "operator"
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    tenant_tier: str = "operator"
    isolation_level: str = "full"

    def is_default(self) -> bool:
        return self.tenant_id == "default" and self.operator_id == "default" and self.client_id == "default"


    @classmethod
    def from_config(cls, config: Mapping[str, Any] | None) -> "TenantContext":
        config = dict(config or {})
        tenant_id = str(config.get("tenant_id") or "default")
        operator_id = str(config.get("operator_id") or tenant_id or "default")
        client_id = str(config.get("client_id") or tenant_id or operator_id)
        tenant_tier = str(config.get("tenant_tier") or "operator")
        isolation_level = str(config.get("isolation_level") or "full")
        return cls(
            tenant_id=tenant_id,
            operator_id=operator_id,
            client_id=client_id,
            user_role=str(config.get("user_role") or "operator"),
            metadata={
                k: v
                for k, v in config.items()
                if k not in {
                    "tenant_id",
                    "operator_id",
                    "client_id",
                    "user_role",
                    "tenant_tier",
                    "isolation_level",
                }
            },
            tenant_tier=tenant_tier,
            isolation_level=isolation_level,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "operator_id": self.operator_id,
            "client_id": self.client_id,
            "user_role": self.user_role,
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
            "tenant_tier": self.tenant_tier,
            "isolation_level": self.isolation_level,
        }
