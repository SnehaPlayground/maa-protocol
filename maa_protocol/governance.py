"""Core governance wrapper for LangGraph-style applications."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .exceptions import MaaProtocolError, PersistenceError
from .guards import (
    AccessControl,
    ApprovalGate,
    CanaryRouter,
    CostGuard,
    SelfHealing,
    TenantContext,
    TenantGate,
)
from .observability import MetricsCollector, TimedBlock
from .persistence import PersistenceBackend, SQLiteBackend


@dataclass(slots=True)
class GovernanceWrapper:
    app: Any
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
        if self.approval_gate is not None and self.approval_gate.persistence is None:
            self.approval_gate.persistence = self.persistence

    def invoke(
        self,
        state: Mapping[str, Any] | None = None,
        config: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        def operation() -> Any:
            with TimedBlock(self.metrics, "governance.invoke"):
                resolved_state, resolved_config, tenant = self._prepare(state, config)
                result = self._execute_sync(resolved_state, resolved_config, **kwargs)
                self._audit(
                    tenant.tenant_id,
                    "invoke.success",
                    {"result_type": type(result).__name__},
                )
                return result

        try:
            if self.self_healing is not None:
                return self.self_healing.invoke_with_healing(operation)
            return operation()
        except MaaProtocolError:
            raise
        except Exception as exc:
            raise MaaProtocolError(f"Governance error during invoke: {exc}") from exc

    async def ainvoke(
        self,
        state: Mapping[str, Any] | None = None,
        config: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        async def operation() -> Any:
            with TimedBlock(self.metrics, "governance.ainvoke"):
                resolved_state, resolved_config, tenant = self._prepare(state, config)
                result = await self._execute_async(resolved_state, resolved_config, **kwargs)
                self._audit(
                    tenant.tenant_id,
                    "ainvoke.success",
                    {"result_type": type(result).__name__},
                )
                return result

        try:
            if self.self_healing is not None:
                return await self.self_healing.ainvoke_with_healing(operation)
            return await operation()
        except MaaProtocolError:
            raise
        except Exception as exc:
            raise MaaProtocolError(f"Governance error during ainvoke: {exc}") from exc

    def _prepare(
        self,
        state: Mapping[str, Any] | None,
        config: Mapping[str, Any] | None,
    ) -> tuple[dict[str, Any], dict[str, Any], TenantContext]:
        resolved_state = dict(state or {})
        resolved_state.pop("governance", None)
        resolved_config = dict(config or {})
        tenant = self._resolve_tenant(resolved_config)
        resolved_state.setdefault("tenant_id", tenant.tenant_id)
        resolved_state.setdefault("operator_id", tenant.operator_id)
        resolved_state.setdefault("client_id", tenant.client_id)

        governance: dict[str, Any] = {"tenant": tenant.as_dict()}
        if self.tenant_gate is not None:
            governance["tenant_gate"] = self.tenant_gate.enforce(
                resolved_state,
                tenant,
                resolved_config,
            )
        if self.access_control is not None:
            governance["access"] = self.access_control.enforce(resolved_config, tenant)
        if self.cost_guard is not None:
            governance["cost"] = self.cost_guard.enforce(resolved_state, tenant, resolved_config)
        if self.canary_router is not None:
            canary = self.canary_router.route_metadata(resolved_state, tenant, resolved_config)
            selected_version = canary.get("selected_version")
            if not selected_version:
                raise MaaProtocolError("Canary router did not return selected_version")
            governance["canary"] = canary
            resolved_state["agent_version"] = selected_version
        if self.approval_gate is not None:
            approval_config = dict(resolved_config)
            approval_config.setdefault("tenant_id", tenant.tenant_id)
            approval_config.setdefault("operator_id", tenant.operator_id)
            governance["approval"] = self.approval_gate.enforce(resolved_state, approval_config)
        governance["observability"] = self.metrics.snapshot().summary()
        resolved_state["governance"] = governance
        self.metrics.increment("governance.prepared")
        self._audit(tenant.tenant_id, "governance.prepared", governance)
        return resolved_state, resolved_config, tenant

    def _resolve_tenant(self, config: Mapping[str, Any]) -> TenantContext:
        if self.tenant_context is not None:
            return self.tenant_context
        try:
            return TenantContext.from_config(config)
        except Exception as exc:
            raise MaaProtocolError(f"Invalid tenant configuration: {exc}") from exc

    def _execute_sync(self, state: dict[str, Any], config: dict[str, Any], **kwargs: Any) -> Any:
        if hasattr(self.app, "invoke"):
            return self.app.invoke(state, config=config, **kwargs)
        if callable(self.app):
            return self.app(state, config=config, **kwargs)
        raise TypeError("Wrapped app must be callable or expose invoke()")

    async def _execute_async(
        self,
        state: dict[str, Any],
        config: dict[str, Any],
        **kwargs: Any,
    ) -> Any:
        if hasattr(self.app, "ainvoke"):
            return await self.app.ainvoke(state, config=config, **kwargs)
        if hasattr(self.app, "invoke"):
            return await asyncio.to_thread(self.app.invoke, state, config=config, **kwargs)
        if callable(self.app):
            return await asyncio.to_thread(self.app, state, config=config, **kwargs)
        raise TypeError("Wrapped app must be callable or expose invoke()/ainvoke()")

    def _audit(self, tenant_id: str, event_type: str, payload: Any) -> None:
        if self.persistence is None:
            return
        try:
            self.persistence.write_audit_event(
                tenant_id,
                event_type,
                payload,
                caller_tenant_id=tenant_id,
            )
        except PersistenceError:
            self.metrics.increment("governance.audit.error")
            raise
