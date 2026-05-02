from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, Mapping

from .guards.approval import ApprovalGate
from .guards.canary import CanaryRouter
from .guards.cost import CostGuard
from .guards.self_healing import SelfHealing
from .guards.tenant import AccessControl, TenantContext, TenantGate
from .observability.metrics import MetricsCollector, TimedBlock
from .persistence.base import PersistenceBackend, SQLiteBackend


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
        if self.approval_gate and self.approval_gate.persistence is None:
            self.approval_gate.persistence = self.persistence

    def invoke(self, state: Mapping[str, Any] | None = None, config: Mapping[str, Any] | None = None, **kwargs: Any) -> Any:
        def operation() -> Any:
            with TimedBlock(self.metrics, "governance.invoke"):
                resolved_state, resolved_config = self._prepare(state, config)
                result = self._execute(resolved_state, resolved_config, **kwargs)
                self._audit(resolved_state, "invoke.success", result)
                return result

        if self.self_healing:
            return self.self_healing.invoke_with_healing(operation)
        return operation()

    async def ainvoke(self, state: Mapping[str, Any] | None = None, config: Mapping[str, Any] | None = None, **kwargs: Any) -> Any:
        with TimedBlock(self.metrics, "governance.ainvoke"):
            resolved_state, resolved_config = self._prepare(state, config)
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

    def _prepare(self, state: Mapping[str, Any] | None, config: Mapping[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any]]:
        resolved_state = dict(state or {})
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

    def _audit(self, state: Mapping[str, Any], event_type: str, payload: Any) -> None:
        if not self.persistence:
            return
        governance = state.get("governance")
        if isinstance(governance, dict):
            tenant = governance.get("tenant")
            if isinstance(tenant, dict):
                tenant_id = tenant.get("tenant_id", state.get("tenant_id", "default"))
            else:
                tenant_id = state.get("tenant_id", "default")
        else:
            tenant_id = state.get("tenant_id", "default")
        tenant_id = str(tenant_id) if tenant_id else "default"
        self.persistence.write_audit_event(tenant_id=tenant_id, event_type=event_type, payload=json.dumps(payload, default=str))
