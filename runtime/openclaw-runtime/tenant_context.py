#!/usr/bin/env python3
"""
TenantContext — Immutable tenant context object for hierarchical two-level tenancy.
Operator Tenant → Client Sub-Tenant model.
"""
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, UTC


@dataclass(frozen=True)
class TenantContext:
    """
    Immutable tenant context. Passed to all components and never modified after creation.
    """
    operator_id: str
    client_id: str
    operator_label: str = ""
    client_label: str = ""
    tenant_tier: str = "operator"  # "operator" | "client"
    isolation_level: str = "full"   # "full" | "soft"
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def is_default(self) -> bool:
        return self.operator_id == "default" and self.client_id == "default"

    def is_operator_level(self) -> bool:
        return self.client_id == "" or self.client_id == self.operator_id

    def path_key(self) -> str:
        """Unique path-safe key for this tenant context."""
        return f"{self.operator_id}/{self.client_id}"

    def __str__(self) -> str:
        return f"Tenant({self.operator_id}/{self.client_id})"


# ── Default tenant (backward compat for existing tasks) ──────────────────────
DEFAULT_TENANT = TenantContext(
    operator_id="default",
    client_id="default",
    operator_label="Default Operator",
    client_label="Default",
    tenant_tier="operator",
    isolation_level="full",
)


def parse_tenant_context(raw: Optional[dict]) -> TenantContext:
    """
    Parse a raw dict (e.g. from task state) into a TenantContext.
    Falls back to DEFAULT_TENANT if raw is None or missing required fields.
    """
    if not raw:
        return DEFAULT_TENANT
    operator_id = raw.get("operator_id", "default")
    client_id = raw.get("client_id", "default")
    if operator_id == "default" and client_id == "default":
        return DEFAULT_TENANT
    return TenantContext(
        operator_id=operator_id,
        client_id=client_id,
        operator_label=raw.get("operator_label", operator_id),
        client_label=raw.get("client_label", client_id),
        tenant_tier=raw.get("tenant_tier", "client"),
        isolation_level=raw.get("isolation_level", "full"),
        created_at=raw.get("created_at", datetime.now(UTC).isoformat()),
    )


def require_tenant_context(raw: Optional[dict]) -> TenantContext:
    """
    Like parse_tenant_context, but raises ValueError if context is missing
    for non-default operators. Used by TenantGate to enforce tenant context.
    """
    if not raw:
        raise ValueError("UNAUTHORIZED: tenant context required")
    operator_id = raw.get("operator_id", "")
    client_id = raw.get("client_id", "")
    if not operator_id:
        raise ValueError("UNAUTHORIZED: tenant context required")
    return parse_tenant_context(raw)