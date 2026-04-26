from maa_protocol import (
    AccessControl,
    ApprovalGate,
    ApprovalRequiredError,
    CanaryRouter,
    CostGuard,
    GovernanceWrapper,
    SelfHealing,
    SelfHealingConfig,
    TenantContext,
    TenantGate,
    TenantGateError,
)


class FakeApp:
    def invoke(self, state, config=None, **kwargs):
        return {
            "state": state,
            "config": config or {},
            "kwargs": kwargs,
        }


def test_tenant_context_from_config_maps_fields_correctly():
    ctx = TenantContext.from_config(
        {
            "tenant_id": "tenant-1",
            "operator_id": "operator-1",
            "client_id": "client-1",
            "user_role": "analyst",
            "tenant_tier": "client",
            "isolation_level": "partial",
            "custom": "value",
        }
    )

    assert ctx.tenant_id == "tenant-1"
    assert ctx.operator_id == "operator-1"
    assert ctx.client_id == "client-1"
    assert ctx.user_role == "analyst"
    assert ctx.tenant_tier == "client"
    assert ctx.isolation_level == "partial"
    assert ctx.metadata == {"custom": "value"}


def test_approval_gate_requires_token_for_high_risk_action():
    gate = ApprovalGate(risk_threshold=0.7)

    try:
        gate.enforce({}, {"risk_flags": ["high_risk"]})
        assert False, "Expected approval gate to block unapproved high-risk action"
    except ApprovalRequiredError:
        pass

    result = gate.enforce({}, {"risk_flags": ["high_risk"], "approval_token": "APPROVED"})
    assert result["approved"] is True
    assert result["needs_approval"] is True


def test_tenant_gate_honors_zero_override_limit():
    tenant = TenantContext(tenant_id="tenant-1", operator_id="op", client_id="client")
    gate = TenantGate(
        max_concurrent_tasks=5,
        tenant_limits={"tenant-1": {"max_concurrent_tasks": 0}},
    )

    try:
        gate.enforce({"_active_task_count": 0}, tenant)
        assert False, "Expected zero override to block immediately"
    except TenantGateError as exc:
        assert "concurrent_limit_exceeded" in str(exc)


def test_governance_wrapper_injects_governance_metadata():
    wrapper = GovernanceWrapper(
        app=FakeApp(),
        tenant_context=TenantContext(tenant_id="tenant-1", operator_id="op", client_id="client"),
        cost_guard=CostGuard(default_budget=50.0),
        canary_router=CanaryRouter(stable_version="v1", canary_version="v2", traffic_split=0.0),
        approval_gate=ApprovalGate(risk_threshold=0.7),
        access_control=AccessControl(),
        tenant_gate=TenantGate(max_cost_per_invoke=30.0, max_concurrent_tasks=10),
    )

    result = wrapper.invoke(
        {"messages": ["hello"], "total_cost": 10.0},
        config={"user_role": "operator", "risk_flags": ["high_risk"], "approval_token": "APPROVED"},
    )

    governance = result["state"]["governance"]
    assert set(governance.keys()) == {"tenant", "tenant_gate", "access", "cost", "canary", "approval"}
    assert governance["approval"]["approved"] is True
    assert governance["cost"]["budget"] == 50.0


def test_self_healing_recovers_after_retries():
    attempts = {"count": 0}

    def flaky():
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise ValueError("boom")
        return "ok"

    healer = SelfHealing(SelfHealingConfig(max_attempts=3, initial_interval=0.0, max_interval=0.0))
    assert healer.invoke_with_healing(flaky) == "ok"
    assert attempts["count"] == 3
