import asyncio
from concurrent.futures import ThreadPoolExecutor

import pytest

from maa_protocol import (
    AccessControl,
    ApprovalGate,
    ApprovalPersistenceError,
    ApprovalRequiredError,
    CanaryRouter,
    CostGuard,
    CostLimitExceededError,
    CostValidationError,
    GovernanceWrapper,
    MaaProtocolError,
    PostgresBackend,
    SelfHealing,
    SelfHealingConfig,
    SQLiteBackend,
    TenantAccessError,
    TenantContext,
    TenantGate,
)


class FakeApp:
    def __init__(self) -> None:
        self.calls: list[tuple[dict, dict]] = []

    def invoke(self, state, config=None, **kwargs):
        self.calls.append((state, config or {}))
        return {"state": state, "config": config or {}, "kwargs": kwargs}


class AsyncFakeApp:
    async def ainvoke(self, state, config=None, **kwargs):
        return {"state": state, "config": config or {}, "kwargs": kwargs, "async": True}


def tenant() -> TenantContext:
    return TenantContext(
        tenant_id="tenant-1",
        operator_id="op-1",
        client_id="client-1",
        user_role="operator",
        permissions={"invoke", "approve"},
    )


def approved_gate(backend: SQLiteBackend) -> tuple[ApprovalGate, str]:
    gate = ApprovalGate(risk_threshold=0.7, persistence=backend)
    record = gate.create_request(
        {"action": "ship"},
        {"tenant_id": "tenant-1", "operator_id": "op-1", "risk_score": 0.95},
    )
    backend.approve(record.approval_id, caller_tenant_id="tenant-1")
    return gate, record.approval_id


def test_tenant_context_from_config_requires_ids():
    with pytest.raises(ValueError, match="Missing required tenant config"):
        TenantContext.from_config({"tenant_id": "tenant-1"})


def test_tenant_context_from_config_collects_metadata():
    ctx = TenantContext.from_config(
        {
            "tenant_id": "tenant-1",
            "operator_id": "op-1",
            "client_id": "client-1",
            "region": "in",
        }
    )
    assert ctx.metadata["region"] == "in"


def test_approval_gate_requires_persistence_to_create_request():
    with pytest.raises(ApprovalPersistenceError):
        ApprovalGate().create_request(
            {},
            {"tenant_id": "tenant-1", "operator_id": "op-1", "risk_score": 0.8},
        )


def test_approval_gate_blocks_high_risk_action():
    gate = ApprovalGate(risk_threshold=0.7, persistence=SQLiteBackend())
    with pytest.raises(ApprovalRequiredError):
        gate.enforce(
            {"action": "delete"},
            {"tenant_id": "tenant-1", "operator_id": "op-1", "risk_score": 0.9},
        )


def test_approval_gate_allows_preapproved_action():
    backend = SQLiteBackend()
    gate, approval_id = approved_gate(backend)
    result = gate.enforce(
        {"action": "ship"},
        {
            "tenant_id": "tenant-1",
            "operator_id": "op-1",
            "risk_score": 0.95,
            "approval_id": approval_id,
        },
    )
    assert result["approved"] is True


def test_cost_guard_rejects_nan():
    guard = CostGuard()
    with pytest.raises(CostValidationError):
        guard.enforce({"cost_usd": float("nan")}, tenant())


def test_cost_guard_enforces_hard_limit():
    guard = CostGuard(default_budget_usd=10.0, hard_limit_usd=5.0)
    with pytest.raises(CostLimitExceededError):
        guard.enforce({"cost_usd": 6.0}, tenant())


def test_tenant_gate_rejects_over_limit_cost():
    gate = TenantGate(max_cost_per_invoke=5.0)
    with pytest.raises(TenantAccessError):
        gate.enforce({"cost_usd": 10.0}, tenant())


def test_access_control_rejects_missing_permission():
    access = AccessControl()
    with pytest.raises(TenantAccessError):
        access.enforce(
            {"user_role": "viewer", "required_permission": "manage_tenants"},
            tenant(),
        )


def test_canary_router_returns_selected_version():
    router = CanaryRouter(
        stable_version="v1",
        canary_version="v2",
        traffic_split=0.0,
    )
    result = router.route_metadata({"action": "x"}, tenant())
    assert result["selected_version"] == "v1"


def test_self_healing_recovers_after_retry():
    attempts = {"count": 0}

    def flaky():
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise RuntimeError("boom")
        return "ok"

    healing = SelfHealing(
        SelfHealingConfig(max_attempts=3, initial_interval=0.001, max_interval=0.001)
    )
    assert healing.invoke_with_healing(flaky) == "ok"
    assert attempts["count"] == 3


def test_self_healing_async_recovers_after_retry():
    attempts = {"count": 0}

    async def flaky():
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise RuntimeError("boom")
        return "ok"

    healing = SelfHealing(
        SelfHealingConfig(max_attempts=2, initial_interval=0.001, max_interval=0.001)
    )
    assert asyncio.run(healing.ainvoke_with_healing(flaky)) == "ok"


def test_governance_wrapper_invoke_injects_metadata_and_audits():
    backend = SQLiteBackend()
    gate, approval_id = approved_gate(backend)
    wrapper = GovernanceWrapper(
        app=FakeApp(),
        tenant_context=tenant(),
        access_control=AccessControl(),
        approval_gate=gate,
        cost_guard=CostGuard(default_budget_usd=20.0),
        canary_router=CanaryRouter(traffic_split=0.0),
        tenant_gate=TenantGate(max_cost_per_invoke=15.0, max_concurrent_tasks=3),
        persistence=backend,
    )
    result = wrapper.invoke(
        {"action": "ship"},
        config={
            "user_role": "operator",
            "cost_usd": 1.5,
            "risk_score": 0.95,
            "approval_id": approval_id,
        },
    )
    assert result["state"]["governance"]["approval"]["approved"] is True
    assert result["state"]["governance"]["canary"]["selected_version"] == "v1"
    assert len(backend.list_audit_events()) >= 2


def test_governance_wrapper_ainvoke_works():
    backend = SQLiteBackend()
    gate, approval_id = approved_gate(backend)
    wrapper = GovernanceWrapper(
        app=AsyncFakeApp(),
        tenant_context=tenant(),
        access_control=AccessControl(),
        approval_gate=gate,
        persistence=backend,
    )
    result = asyncio.run(
        wrapper.ainvoke(
            {"action": "ship"},
            config={"user_role": "operator", "risk_score": 0.95, "approval_id": approval_id},
        )
    )
    assert result["async"] is True


def test_governance_wrapper_requires_valid_tenant_when_not_preconfigured():
    wrapper = GovernanceWrapper(
        app=FakeApp(),
        access_control=AccessControl(),
        persistence=SQLiteBackend(),
    )
    with pytest.raises(MaaProtocolError, match="Invalid tenant configuration"):
        wrapper.invoke({}, config={"user_role": "operator"})


def test_governance_wrapper_wraps_cost_errors():
    wrapper = GovernanceWrapper(
        app=FakeApp(),
        tenant_context=tenant(),
        access_control=AccessControl(),
        cost_guard=CostGuard(default_budget_usd=10.0, hard_limit_usd=5.0),
        persistence=SQLiteBackend(),
    )
    with pytest.raises(CostLimitExceededError):
        wrapper.invoke({}, config={"user_role": "operator", "cost_usd": 6.0})


def test_governance_wrapper_uses_self_healing_for_sync_invokes():
    attempts = {"count": 0}

    def flaky(state, config=None, **kwargs):
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise RuntimeError("transient")
        return {"state": state, "config": config or {}}

    wrapper = GovernanceWrapper(
        app=flaky,
        tenant_context=tenant(),
        access_control=AccessControl(),
        self_healing=SelfHealing(
            SelfHealingConfig(max_attempts=2, initial_interval=0.001, max_interval=0.001)
        ),
        persistence=SQLiteBackend(),
    )
    result = wrapper.invoke({}, config={"user_role": "operator"})
    assert result["state"]["governance"]["tenant"]["tenant_id"] == "tenant-1"
    assert attempts["count"] == 2


def test_governance_wrapper_supports_callable_without_invoke():
    wrapper = GovernanceWrapper(
        app=lambda state, config=None, **kwargs: {"state": state, "config": config or {}},
        tenant_context=tenant(),
        access_control=AccessControl(),
        persistence=SQLiteBackend(),
    )
    result = wrapper.invoke({}, config={"user_role": "operator"})
    assert result["state"]["governance"]["tenant"]["operator_id"] == "op-1"


def test_governance_wrapper_concurrent_invokes_persist_audit():
    backend = SQLiteBackend()
    wrapper = GovernanceWrapper(
        app=FakeApp(),
        tenant_context=tenant(),
        access_control=AccessControl(),
        persistence=backend,
    )

    def run_once(_: int) -> None:
        wrapper.invoke({"action": "read"}, config={"user_role": "operator"})

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(run_once, range(4)))

    assert len(backend.list_audit_events()) >= 8


def test_postgres_backend_is_placeholder():
    with pytest.raises(NotImplementedError):
        PostgresBackend()
