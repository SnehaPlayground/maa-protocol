"""Tests for maa_x core governance."""

import pytest
from maa_x import GovernanceWrapper
from maa_x.guards import (
    ApprovalGate,
    CanaryRouter,
    CostGuard,
    SelfHealing,
    SelfHealingConfig,
    TenantContext,
    TenantGate,
)
from maa_x.persistence import SQLiteBackend
from maa_x.exceptions import CostLimitExceededError, ApprovalRequiredError


class DummyApp:
    def invoke(self, state, config=None):
        return {"result": "ok", "state": state}


def test_governance_wrapper_basic_invoke():
    backend = SQLiteBackend()
    wrapper = GovernanceWrapper(
        app=DummyApp(),
        tenant_context=TenantContext(tenant_id="test"),
        persistence=backend,
    )
    result = wrapper.invoke({"msg": "hello"})
    assert result["result"] == "ok"


def test_cost_guard_enforce():
    guard = CostGuard(default_budget_usd=10.0)
    tenant = TenantContext(tenant_id="t", budget_usd=10.0)
    result = guard.enforce({}, tenant, {"cost_usd": 5.0})
    assert result["cost_usd"] == 5.0
    assert result["budget_usd"] == 10.0
    assert not result["hard_limit_reached"]


def test_cost_guard_hard_limit():
    guard = CostGuard(default_budget_usd=10.0)
    tenant = TenantContext(tenant_id="t", budget_usd=10.0)
    with pytest.raises(CostLimitExceededError):
        guard.enforce({}, tenant, {"cost_usd": 15.0})


def test_approval_gate_approve_preapproved():
    backend = SQLiteBackend(":memory:")
    gate = ApprovalGate(risk_threshold=0.7, persistence=backend)
    # Risk score below threshold → needs_approval=False, no hash check
    result = gate.assess({}, {"approval_id": "dummy", "risk_score": 0.3})
    assert not result["needs_approval"]


def test_canary_router():
    router = CanaryRouter(stable_version="v1", canary_version="v2", traffic_split=0.0)
    tenant = TenantContext(tenant_id="t")
    result = router.route_metadata({}, tenant, {})
    assert result["selected_version"] == "v1"


def test_self_healing_config_defaults():
    config = SelfHealingConfig()
    assert config.max_retries == 3
    assert config.backoff_multiplier == 2.0


def test_governance_with_cost_guard():
    wrapper = GovernanceWrapper(
        app=DummyApp(),
        tenant_context=TenantContext(tenant_id="test", budget_usd=50.0),
        cost_guard=CostGuard(default_budget_usd=50.0),
        persistence=SQLiteBackend(),
    )
    result = wrapper.invoke({"msg": "hello"}, config={"cost_usd": 10.0})
    assert result["result"] == "ok"


def test_governance_audit_writes():
    backend = SQLiteBackend()
    wrapper = GovernanceWrapper(app=DummyApp(), persistence=backend)
    wrapper.invoke({"msg": "test"})
    # Smoke test: no exception means audit write succeeded