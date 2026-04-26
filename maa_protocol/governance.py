from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .access_control import AccessControl
from .approval_gate import ApprovalGate
from .canary_router import CanaryRouter
from .cost_control import CostGuard
from .self_healing import SelfHealing, SelfHealingConfig
from .tenant_context import TenantContext
from .tenant_gate import TenantGate


@dataclass
class GovernanceWrapper:
    """Wrap a compiled LangGraph app with governance checks and metadata.

    Components are applied in this order:
    1. TenantGate — isolation and tenant-level limits
    2. AccessControl — RBAC checks
    3. CostGuard — budget enforcement
    4. CanaryRouter — version selection
    5. ApprovalGate — human approval for risky actions
    6. SelfHealing — retry with backoff (if enabled)
    """

    app: Any
    tenant_context: TenantContext | None = None
    cost_guard: CostGuard | None = None
    canary_router: CanaryRouter | None = None
    approval_gate: ApprovalGate | None = None
    access_control: AccessControl | None = None
    tenant_gate: TenantGate | None = None
    self_healing: SelfHealing | None = None
    enable_self_healing: bool = False

    def invoke(
        self,
        state: Mapping[str, Any] | None = None,
        config: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        state = dict(state or {})
        config = dict(config or {}) if config is not None else {}

        tenant = self._resolve_tenant(config)
        governance: dict[str, Any] = {"tenant": tenant.as_dict()}

        # 1. TenantGate — isolation and limit enforcement
        if self.tenant_gate:
            gate_result = self.tenant_gate.enforce(state, tenant, config)
            governance["tenant_gate"] = gate_result

        # 2. AccessControl — RBAC
        if self.access_control:
            governance["access"] = self.access_control.enforce(config)

        # 3. CostGuard — budget check
        if self.cost_guard:
            governance["cost"] = self.cost_guard.enforce(state, tenant, config)

        # 4. CanaryRouter — version routing
        if self.canary_router:
            route = self.canary_router.route_metadata(state, tenant, config)
            governance["canary"] = route
            state["agent_version"] = route["selected_version"]

        # 5. ApprovalGate — human approval gate
        if self.approval_gate:
            governance["approval"] = self.approval_gate.enforce(state, config)

        state.setdefault("governance", {}).update(governance)

        # 6. Execute with optional self-healing
        def _run():
            if hasattr(self.app, "invoke"):
                return self.app.invoke(state, config=config, **kwargs)
            if callable(self.app):
                return self.app(state, config=config, **kwargs)
            raise TypeError("Wrapped app must be callable or expose invoke()")

        if self.enable_self_healing or self.self_healing:
            healer = self.self_healing or SelfHealing()
            return healer.invoke_with_healing(_run)

        return _run()

    def _resolve_tenant(self, config: Mapping[str, Any]) -> TenantContext:
        if self.tenant_context and self.tenant_context.tenant_id != "default":
            return self.tenant_context
        return TenantContext.from_config(config)
