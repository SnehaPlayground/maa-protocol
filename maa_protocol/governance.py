"""Core governance wrapper — pure Python, zero-dependency beyond Python stdlib.

All public API inputs (``state``, ``config``) are treated as **untrusted**.
The wrapper sanitizes and validates governance-related fields before passing
them to guards or the wrapped app.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

from .exceptions import MaaProtocolError
from .guards.approval import ApprovalGate
from .guards.canary import CanaryRouter
from .guards.cost import CostGuard
from .guards.self_healing import SelfHealing
from .guards.tenant import AccessControl, TenantContext, TenantGate
from .observability.metrics import MetricsCollector, TimedBlock
from .persistence.base import PersistenceBackend, SQLiteBackend


# --------------------------------------------------------------------------- #
# App protocol
# --------------------------------------------------------------------------- #

class AppProtocol(Protocol):
    """Minimal protocol for a governable app — either ``invoke`` or ``ainvoke``."""

    def invoke(self, state: Mapping[str, Any], *, config: Mapping[str, Any]) -> Any:
        ...

    async def ainvoke(self, state: Mapping[str, Any], *, config: Mapping[str, Any]) -> Any:
        ...


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

# Governance metadata keys that are considered safe to propagate.
_VALID_GOVERNANCE_KEYS = frozenset({
    "tenant", "tenant_gate", "access", "cost", "canary",
    "approval", "observability", "agent_version", "action",
})

# Max length for any string field extracted from state/config.
_MAX_STRING_FIELD = 10_000


def _sanitize_string(value: Any, max_len: int = _MAX_STRING_FIELD) -> str:
    """Coerce *value* to a stripped string, truncating at *max_len*."""
    if not isinstance(value, str):
        try:
            value = str(value)
        except Exception:
            return ""
    return value.strip()[:max_len]


def _sanitize_governance_state(state: dict[str, Any]) -> dict[str, Any]:
    """Strip dangerous keys from *state*; preserve governance metadata.

    Note: ``governance`` is intentionally preserved so guards can read it.
    Tenant resolution happens in ``_prepare``.
    """
    if not isinstance(state, dict):
        return {}
    result = {}
    # Copy only known-safe top-level keys; drop anything suspicious.
    for key in _VALID_GOVERNANCE_KEYS:
        if key in state:
            result[key] = state[key]
    return result


# --------------------------------------------------------------------------- #
# Governance wrapper
# --------------------------------------------------------------------------- #

@dataclass(slots=True)
class GovernanceWrapper:
    """Governance wrapper for LangGraph-style applications.

    Parameters
    ----------
    app : callable | invoke()-able | ainvoke()-able
        The underlying application to govern.
    tenant_context : TenantContext | None
        Statically configured tenant (default: resolved from config per call).
    cost_guard : CostGuard | None
        Budget enforcement guard.
    canary_router : CanaryRouter | None
        Traffic-split guard.
    approval_gate : ApprovalGate | None
        Risk-based approval guard.
    access_control : AccessControl | None
        RBAC guard.
    tenant_gate : TenantGate | None
        Concurrency / isolation guard.
    self_healing : SelfHealing | None
        Retry + circuit-breaker for the wrapped app.
    persistence : PersistenceBackend | None
        Approval and audit persistence (default: in-memory SQLite).
    metrics : MetricsCollector
        Observability collector (default: noop).
    """

    app: Any  # AppProtocol in field, but Any avoids mypy false positives with dynamically dispatched apps.
    tenant_context: TenantContext | None = None
    cost_guard: CostGuard | None = None
    canary_router: CanaryRouter | None = None
    approval_gate: ApprovalGate | None = None
    access_control: AccessControl | None = None
    tenant_gate: TenantGate | None = None
    self_healing: SelfHealing | None = None
    persistence: PersistenceBackend | None = None
    metrics: MetricsCollector = field(default_factory=MetricsCollector)

    def __post_init__(self) -> None:
        if self.persistence is None:
            self.persistence = SQLiteBackend()
        if self.approval_gate and hasattr(self.approval_gate, "persistence") and self.approval_gate.persistence is None:
            self.approval_gate.persistence = self.persistence

    # ------------------------------------------------------------------ #
    # Public invoke
    # ------------------------------------------------------------------ #

    def invoke(
        self,
        state: Mapping[str, Any] | None = None,
        config: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        def operation() -> Any:
            with TimedBlock(self.metrics, "governance.invoke"):
                try:
                    resolved_state, resolved_config = self._prepare(state, config)
                except Exception as exc:
                    self.metrics.increment("governance.prepare.error")
                    self._heal_or_reraise(exc, "invoke")
                    raise  # unreachable; silence mypy
                result = self._execute(resolved_state, resolved_config, **kwargs)
                self._audit(resolved_state, "invoke.success", result)
                return result

        if self.self_healing:
            return self.self_healing.invoke_with_healing(operation)
        return operation()

    # ------------------------------------------------------------------ #
    # Public ainvoke
    # ------------------------------------------------------------------ #

    async def ainvoke(
        self,
        state: Mapping[str, Any] | None = None,
        config: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        with TimedBlock(self.metrics, "governance.ainvoke"):
            try:
                resolved_state, resolved_config = self._prepare(state, config)
            except Exception as exc:
                self.metrics.increment("governance.prepare.error")
                self._heal_or_reraise(exc, "ainvoke")
                raise  # unreachable

            if hasattr(self.app, "ainvoke"):
                result = await self.app.ainvoke(resolved_state, config=resolved_config, **kwargs)
            elif hasattr(self.app, "invoke"):
                result = await asyncio.to_thread(self.app.invoke, resolved_state, config=resolved_config, **kwargs)
            elif callable(self.app):
                result = await asyncio.to_thread(self.app, resolved_state, config=resolved_config, **kwargs)
            else:
                raise TypeError("Wrapped app must be callable or expose invoke()/ainvoke()")

            self._audit(resolved_state, "ainvoke.success", result)
        return result

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _prepare(
        self,
        state: Mapping[str, Any] | None,
        config: Mapping[str, Any] | None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Resolve tenant, enforce all guards, inject governance metadata."""
        resolved_state = _sanitize_governance_state(dict(state or {}))
        resolved_config = dict(config or {})

        tenant = self._resolve_tenant(resolved_config)
        governance: dict[str, Any] = {"tenant": tenant.as_dict()}
        resolved_state.setdefault("tenant_id", tenant.tenant_id)
        resolved_state.setdefault("operator_id", tenant.operator_id)

        if self.tenant_gate:
            governance["tenant_gate"] = self.tenant_gate.enforce(resolved_state, tenant, resolved_config)
        if self.access_control:
            governance["access"] = self.access_control.enforce(resolved_config, tenant)
        if self.cost_guard:
            governance["cost"] = self.cost_guard.enforce(resolved_state, tenant, resolved_config)
        if self.canary_router:
            governance["canary"] = self.canary_router.route_metadata(resolved_state, tenant, resolved_config)
            resolved_state["agent_version"] = governance["canary"]["selected_version"]
        if self.approval_gate:
            governance["approval"] = self.approval_gate.enforce(resolved_state, resolved_config)
        governance["observability"] = self.metrics.snapshot()

        resolved_state.setdefault("governance", {}).update(governance)
        self.metrics.increment("governance.prepared")
        self._audit(resolved_state, "governance.prepared", governance)
        return resolved_state, resolved_config

    def _execute(self, state: dict[str, Any], config: dict[str, Any], **kwargs: Any) -> Any:
        if hasattr(self.app, "invoke"):
            return self.app.invoke(state, config=config, **kwargs)
        if callable(self.app):
            return self.app(state, config=config, **kwargs)
        raise TypeError("Wrapped app must be callable or expose invoke()")

    def _resolve_tenant(self, config: Mapping[str, Any]) -> TenantContext:
        if self.tenant_context and self.tenant_context.tenant_id != "default":
            return self.tenant_context
        return TenantContext.from_config(config)

    def _heal_or_reraise(self, exc: Exception, operation: str) -> None:
        """Attempt self-healing for *operation* on *exc*, then re-raise."""
        if self.self_healing is None:
            raise MaaProtocolError(
                f"Governance error during {operation}: {exc}"
            ) from exc

        def _fallback(err: Exception) -> Any:
            raise MaaProtocolError(
                f"Self-healing exhausted for {operation}; original error: {err}"
            ) from err

        self.self_healing.invoke_with_healing(lambda: None, fallback=_fallback)
        raise MaaProtocolError(
            f"Governance error during {operation}: {exc}"
        ) from exc

    def _audit(
        self,
        state: Mapping[str, Any],
        event_type: str,
        payload: Any,
        *,
        caller_tenant_id: str | None = None,
    ) -> None:
        """Write an audit event; on failure, increment error metric but never silently drop."""
        if not self.persistence:
            return
        # Resolve tenant_id for the audit record.
        tenant_id = self._resolve_tenant_id(state)
        if not tenant_id:
            tenant_id = "default"

        try:
            self.persistence.write_audit_event(
                tenant_id=tenant_id,
                event_type=event_type,
                payload=payload,
                caller_tenant_id=caller_tenant_id,
            )
        except Exception as exc:
            # Never let a failing audit silently suppress itself.
            # Log to metrics and re-raise as a wrapped MaaProtocolError.
            self.metrics.increment("governance.audit.error")
            raise MaaProtocolError(
                f"Failed to write audit event '{event_type}': {exc}"
            ) from exc

    def _resolve_tenant_id(self, state: Mapping[str, Any]) -> str:
        """Extract and validate tenant_id from state."""
        governance = state.get("governance")
        if isinstance(governance, dict):
            tenant = governance.get("tenant")
            if isinstance(tenant, dict):
                tid = tenant.get("tenant_id")
                if isinstance(tid, str) and tid.strip():
                    return tid.strip()[:_MAX_STRING_FIELD]
        tid = state.get("tenant_id")
        if isinstance(tid, str) and tid.strip():
            return tid.strip()[:_MAX_STRING_FIELD]
        return "default"
