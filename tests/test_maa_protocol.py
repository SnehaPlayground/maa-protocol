import asyncio

import pytest

from maa_protocol import (
    AccessControl,
    ApprovalGate,
    ApprovalRequiredError,
    CanaryRouter,
    CostGuard,
    GovernanceWrapper,
    SelfHealing,
    SelfHealingConfig,
    SQLiteBackend,
    TenantAccessError,
    TenantContext,
    TenantGate,
)


class FakeApp:
    def invoke(self, state, config=None, **kwargs):
        return {
            "state": state,
            "config": config or {},
            "kwargs": kwargs,
        }


class AsyncFakeApp:
    async def ainvoke(self, state, config=None, **kwargs):
        return {
            "state": state,
            "config": config or {},
            "kwargs": kwargs,
            "async": True,
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
            "budget_usd": 25.0,
            "permissions": ["invoke"],
            "custom": "value",
        }
    )

    assert ctx.tenant_id == "tenant-1"
    assert ctx.operator_id == "operator-1"
    assert ctx.client_id == "client-1"
    assert ctx.user_role == "analyst"
    assert ctx.tenant_tier == "client"
    assert ctx.isolation_level == "partial"
    assert ctx.budget_usd == 25.0
    assert ctx.permissions == {"invoke"}
    assert ctx.metadata == {"custom": "value"}


def test_approval_gate_creates_persisted_request_for_high_risk_action():
    backend = SQLiteBackend()
    gate = ApprovalGate(risk_threshold=0.7, persistence=backend)

    with pytest.raises(ApprovalRequiredError):
        gate.enforce({"action": "send_email"}, {"risk_flags": ["high_risk"]})

    rows = backend.conn.execute("SELECT COUNT(*) FROM approvals").fetchone()[0]
    assert rows == 1


def test_approval_gate_allows_preapproved_action():
    backend = SQLiteBackend()
    gate = ApprovalGate(risk_threshold=0.7, persistence=backend)
    request = gate.create_request({"action": "send_email"}, {"risk_score": 0.95, "tenant_id": "tenant-1"})
    backend.approve(request.approval_id)

    result = gate.enforce(
        {"action": "send_email"},
        {"risk_score": 0.95, "tenant_id": "tenant-1", "approval_id": request.approval_id},
    )
    assert result["approved"] is True


def test_tenant_gate_honors_zero_override_limit():
    tenant = TenantContext(tenant_id="tenant-1", operator_id="op", client_id="client")
    gate = TenantGate(max_concurrent_tasks=5, tenant_limits={"tenant-1": {"max_concurrent_tasks": 0}})

    with pytest.raises(TenantAccessError):
        gate.enforce({"_active_task_count": 0}, tenant)


def test_cost_guard_blocks_hard_limit():
    guard = CostGuard(default_budget_usd=10.0, hard_limit_usd=5.0)
    tenant = TenantContext(tenant_id="tenant-1", operator_id="op", client_id="client")
    with pytest.raises(Exception):
        guard.enforce({"cost_usd": 6.0}, tenant)


def test_governance_wrapper_injects_governance_metadata():
    backend = SQLiteBackend()
    gate = ApprovalGate(risk_threshold=0.7, persistence=backend)
    request = gate.create_request({"action": "ship_trade"}, {"risk_score": 0.9, "tenant_id": "tenant-1", "operator_id": "op"})
    backend.approve(request.approval_id)

    wrapper = GovernanceWrapper(
        app=FakeApp(),
        tenant_context=TenantContext(tenant_id="tenant-1", operator_id="op", client_id="client", user_role="operator"),
        cost_guard=CostGuard(default_budget_usd=50.0),
        canary_router=CanaryRouter(stable_version="v1", canary_version="v2", traffic_split=0.0),
        approval_gate=gate,
        access_control=AccessControl(),
        tenant_gate=TenantGate(max_cost_per_invoke=30.0, max_concurrent_tasks=10),
        persistence=backend,
    )

    result = wrapper.invoke(
        {"messages": ["hello"], "total_cost": 10.0, "action": "ship_trade"},
        config={"user_role": "operator", "risk_score": 0.9, "approval_id": request.approval_id, "operator_id": "op"},
    )

    governance = result["state"]["governance"]
    assert set(governance.keys()) >= {"tenant", "tenant_gate", "access", "cost", "canary", "approval", "observability"}
    assert governance["approval"]["approved"] is True
    assert governance["cost"]["budget_usd"] == 50.0


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


def test_governance_wrapper_async_path():
    backend = SQLiteBackend()
    gate = ApprovalGate(risk_threshold=0.7, persistence=backend)
    request = gate.create_request({"action": "async_op"}, {"risk_score": 0.9, "tenant_id": "tenant-1", "operator_id": "op"})
    backend.approve(request.approval_id)

    wrapper = GovernanceWrapper(
        app=AsyncFakeApp(),
        tenant_context=TenantContext(tenant_id="tenant-1", operator_id="op", client_id="client", user_role="operator"),
        approval_gate=gate,
        access_control=AccessControl(),
        persistence=backend,
    )

    result = asyncio.run(
        wrapper.ainvoke({"action": "async_op"}, config={"user_role": "operator", "risk_score": 0.9, "approval_id": request.approval_id, "operator_id": "op"})
    )
    assert result["async"] is True


def test_audit_events_are_persisted():
    backend = SQLiteBackend()
    wrapper = GovernanceWrapper(
        app=FakeApp(),
        tenant_context=TenantContext(tenant_id="tenant-9", operator_id="op", client_id="client", user_role="operator"),
        access_control=AccessControl(),
        persistence=backend,
    )
    wrapper.invoke({"messages": ["hi"]}, config={"user_role": "operator"})
    count = backend.conn.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0]
    assert count >= 1
