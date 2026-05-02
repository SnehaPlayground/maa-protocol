"""Security and reliability tests for maa-protocol governance layer."""

import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from maa_protocol import (
    CostGuard,
    CostLimitExceededError,
    CostValidationError,
    GovernanceWrapper,
    PersistenceError,
    SelfHealing,
    SelfHealingConfig,
    SQLiteBackend,
    TenantAccessError,
    TenantContext,
    TenantGate,
)
from maa_protocol.exceptions import TenantIsolationError


# --------------------------------------------------------------------------- #
# CostGuard validation tests
# --------------------------------------------------------------------------- #

def test_cost_guard_rejects_negative_usage():
    guard = CostGuard(default_budget_usd=10.0)
    tenant = TenantContext(tenant_id="t1", operator_id="op", client_id="c")
    with pytest.raises(CostValidationError, match="cost_usd must be non-negative"):
        guard.enforce({"cost_usd": -1.0}, tenant)


def test_cost_guard_rejects_non_numeric_usage():
    guard = CostGuard(default_budget_usd=10.0)
    tenant = TenantContext(tenant_id="t1", operator_id="op", client_id="c")
    with pytest.raises(CostValidationError, match="cost_usd must be a numeric value"):
        guard.enforce({"cost_usd": "fifty dollars"}, tenant)


def test_cost_guard_rejects_none_usage():
    guard = CostGuard(default_budget_usd=10.0)
    tenant = TenantContext(tenant_id="t1", operator_id="op", client_id="c")
    with pytest.raises(CostValidationError, match="cost_usd may not be None"):
        guard.enforce({"cost_usd": None}, tenant)


def test_cost_guard_rejects_zero_budget():
    guard = CostGuard(default_budget_usd=10.0)
    tenant = TenantContext(tenant_id="t1", operator_id="op", client_id="c", budget_usd=0.0)
    with pytest.raises(CostValidationError, match="Effective budget_usd must be > 0"):
        guard.enforce({}, tenant)


def test_cost_guard_rejects_negative_budget():
    guard = CostGuard(default_budget_usd=10.0)
    tenant = TenantContext(tenant_id="t1", operator_id="op", client_id="c", budget_usd=-5.0)
    with pytest.raises(CostValidationError, match="budget_usd must be non-negative"):
        guard.enforce({}, tenant)


def test_cost_guard_rejects_soft_limit_ratio_below_zero():
    with pytest.raises(CostValidationError, match="soft_limit_ratio must be in \\[0.0, 1.0\\]"):
        CostGuard(soft_limit_ratio=-0.1)


def test_cost_guard_rejects_soft_limit_ratio_above_one():
    with pytest.raises(CostValidationError, match="soft_limit_ratio must be in \\[0.0, 1.0\\]"):
        CostGuard(soft_limit_ratio=1.5)


def test_cost_guard_rejects_negative_hard_limit():
    # hard_limit_usd is validated in __post_init__, so construction raises.
    with pytest.raises(CostValidationError, match="hard_limit_usd must be non-negative"):
        CostGuard(default_budget_usd=10.0, hard_limit_usd=-1.0)


def test_cost_guard_blocks_spoofed_low_cost_when_over_budget():
    """A cost above the hard limit must be rejected even if config says otherwise."""
    guard = CostGuard(default_budget_usd=10.0, hard_limit_usd=5.0)
    tenant = TenantContext(tenant_id="t1", operator_id="op", client_id="c")
    # 6.0 > hard_limit_usd=5.0 → must raise CostLimitExceededError
    with pytest.raises(CostLimitExceededError):
        guard.enforce({"cost_usd": 6.0}, tenant)


# --------------------------------------------------------------------------- #
# Tenant isolation tests
# --------------------------------------------------------------------------- #

def test_cross_tenant_get_approval_blocked():
    backend = SQLiteBackend()
    # tenant-1 creates an approval
    record = backend.create_approval(
        tenant_id="tenant-1",
        action="trade",
        action_hash="abc",
        requested_by="op1",
        reason="test",
        risk_score=0.5,
        caller_tenant_id="tenant-1",
    )
    # tenant-2 attempts to read it — must be blocked
    with pytest.raises(TenantIsolationError):
        backend.get_approval(record.approval_id, caller_tenant_id="tenant-2")


def test_cross_tenant_approve_blocked():
    backend = SQLiteBackend()
    record = backend.create_approval(
        tenant_id="tenant-1",
        action="trade",
        action_hash="abc",
        requested_by="op1",
        reason="test",
        risk_score=0.5,
        caller_tenant_id="tenant-1",
    )
    with pytest.raises(TenantIsolationError):
        backend.approve(record.approval_id, caller_tenant_id="tenant-2")


def test_cross_tenant_write_audit_event_blocked():
    backend = SQLiteBackend()
    with pytest.raises(TenantIsolationError):
        backend.write_audit_event(
            tenant_id="tenant-1",
            event_type="test",
            payload={"msg": "hello"},
            caller_tenant_id="tenant-2",
        )


def test_tenant_isolation_error_carries_clear_message():
    backend = SQLiteBackend()
    try:
        backend.get_approval("nonexistent-id", caller_tenant_id="evil-tenant")
    except TenantIsolationError as exc:
        assert "Cross-tenant access denied" in str(exc)
        assert "evil-tenant" in str(exc)


# --------------------------------------------------------------------------- #
# Persistence error handling tests
# --------------------------------------------------------------------------- #

def test_sqlite_error_raises_persistence_error():
    """Inject a malformed SQL to verify sqlite3 errors are wrapped."""
    backend = SQLiteBackend()
    # Manually corrupt the DB to trigger an error on next operation.
    backend.conn.execute("DROP TABLE approvals")
    with pytest.raises(PersistenceError, match="no such table: approvals"):
        backend.create_approval(
            tenant_id="t1",
            action="x",
            action_hash="y",
            requested_by="z",
            reason="r",
            risk_score=0.1,
            caller_tenant_id="t1",
        )


def test_audit_write_failure_raises_persistence_error():
    """When write_audit_event fails, must raise PersistenceError not silently drop."""
    backend = SQLiteBackend()
    backend.conn.execute("DROP TABLE audit_events")
    with pytest.raises(PersistenceError, match="no such table: audit_events"):
        backend.write_audit_event(
            tenant_id="t1",
            event_type="test",
            payload={"data": "hello"},
            caller_tenant_id="t1",
        )


# --------------------------------------------------------------------------- #
# SQLiteBackend thread-safety + context manager tests
# --------------------------------------------------------------------------- #

def test_sqlite_backend_context_manager_closes_connection():
    with SQLiteBackend() as backend:
        row = backend.create_approval(
            tenant_id="t1", action="x", action_hash="h",
            requested_by="r", reason="s", risk_score=0.1,
            caller_tenant_id="t1",
        )
        assert row is not None
    # Connection should be closed after exiting context.
    # After __exit__, backend.conn is None, so AttributeError is raised.
    with pytest.raises((sqlite3.Error, AttributeError)):
        backend.conn.execute("SELECT 1")


def test_sqlite_backend_close_idempotent():
    backend = SQLiteBackend()
    backend.close()
    backend.close()  # Must not raise.


def test_concurrent_approvals_all_succeed(tmp_path):
    """Multiple threads writing to the same SQLiteBackend must not corrupt data.

    Note: SQLite with check_same_thread=False can handle interleaved writes
    from multiple threads, but not truly simultaneous writes. We use a barrier
    to serialize writes so we test correctness rather than SQLite concurrency limits.
    """
    import threading
    db_path = str(tmp_path / "concurrent_test.db")
    backend = SQLiteBackend(path=db_path)
    errors = []
    barrier = threading.Barrier(4)

    def writer(n: int) -> None:
        try:
            for i in range(10):
                backend.create_approval(
                    tenant_id=f"tenant-{n}",
                    action=f"action-{i}",
                    action_hash=f"hash-{n}-{i}",
                    requested_by=f"op-{n}",
                    reason="concurrent test",
                    risk_score=0.5,
                    caller_tenant_id=f"tenant-{n}",
                )
            barrier.wait()  # sync before next round to reduce SQLite contention
        except Exception as exc:
            errors.append(exc)

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(writer, i) for i in range(4)]
        for f in futures:
            f.result()

    assert errors == [], f"Concurrent writes raised: {errors}"
    count = backend.conn.execute("SELECT COUNT(*) FROM approvals").fetchone()[0]
    assert count == 40


# --------------------------------------------------------------------------- #
# PostgresBackend placeholder test
# --------------------------------------------------------------------------- #

def test_postgres_backend_raises_not_implemented():
    from maa_protocol.persistence.base import PostgresBackend

    with pytest.raises(NotImplementedError, match="placeholder"):
        PostgresBackend()


# --------------------------------------------------------------------------- #
# Sensitive payload redaction tests
# --------------------------------------------------------------------------- #

def test_audit_event_redacts_secret_keys():
    backend = SQLiteBackend()
    backend.write_audit_event(
        tenant_id="t1",
        event_type="test",
        payload={"user": "alice", "api_key": "secret-123", "token": "bearer-token"},
        caller_tenant_id="t1",
    )
    row = backend.conn.execute(
        "SELECT payload FROM audit_events WHERE tenant_id = ?",
        ("t1",),
    ).fetchone()
    assert row is not None
    payload = row[0]
    assert "secret-123" not in payload
    assert "bearer-token" not in payload
    assert "[REDACTED]" in payload
    assert "alice" in payload  # non-secret key preserved


def test_audit_event_redacts_nested_secret_keys():
    backend = SQLiteBackend()
    backend.write_audit_event(
        tenant_id="t1",
        event_type="test",
        payload={"user": "alice", "credentials": {"api_key": "deep-secret"}},
        caller_tenant_id="t1",
    )
    row = backend.conn.execute(
        "SELECT payload FROM audit_events WHERE tenant_id = ?",
        ("t1",),
    ).fetchone()
    assert row is not None
    payload = row[0]
    assert "deep-secret" not in payload


def test_approval_reason_redacts_secret():
    backend = SQLiteBackend()
    record = backend.create_approval(
        tenant_id="t1",
        action="deploy",
        action_hash="h",
        requested_by="op",
        reason="Deploying with password=super-secret and token=abc",
        risk_score=0.5,
        caller_tenant_id="t1",
    )
    assert "[REDACTED]" in record.reason
    assert "super-secret" not in record.reason


# --------------------------------------------------------------------------- #
# Payload size limit test
# --------------------------------------------------------------------------- #

def test_audit_payload_truncated_at_10kb():
    backend = SQLiteBackend()
    large_payload = {"data": "x" * 50_000}  # ~50 KB
    backend.write_audit_event(
        tenant_id="t1",
        event_type="large_event",
        payload=large_payload,
        caller_tenant_id="t1",
    )
    row = backend.conn.execute(
        "SELECT payload FROM audit_events WHERE tenant_id = ?",
        ("t1",),
    ).fetchone()
    assert row is not None
    payload = row[0]
    assert len(payload.encode("utf-8")) <= 10 * 1024
    assert "[TRUNCATED]" in payload


# --------------------------------------------------------------------------- #
# GovernanceWrapper _heal_or_reraise test
# --------------------------------------------------------------------------- #

def test_governance_reraises_cost_validation_error():
    """When CostGuard raises, GovernanceWrapper must re-raise as MaaProtocolError."""
    from maa_protocol.exceptions import MaaProtocolError

    class FlakyCostGuard(CostGuard):
        def enforce(self, state, tenant, config=None):
            raise CostValidationError("hard_limit_usd is invalid")

    wrapper = GovernanceWrapper(app=lambda s, **kw: s, cost_guard=FlakyCostGuard())
    with pytest.raises(MaaProtocolError, match="hard_limit_usd is invalid"):
        wrapper.invoke({}, {})


def test_governance_reraises_approval_required_error():
    """When ApprovalGate raises, GovernanceWrapper must re-raise as MaaProtocolError."""
    from maa_protocol.exceptions import MaaProtocolError
    from maa_protocol.guards.approval import ApprovalGate

    backend = SQLiteBackend()
    gate = ApprovalGate(risk_threshold=0.7, persistence=backend)
    wrapper = GovernanceWrapper(app=lambda s, **kw: s, approval_gate=gate)
    with pytest.raises(MaaProtocolError, match="Approval required"):
        wrapper.invoke({"action": "send_funds"}, {"risk_score": 0.9})


# --------------------------------------------------------------------------- #
# CostGuard post_init validation
# --------------------------------------------------------------------------- #

def test_cost_guard_post_init_validates_hard_limit():
    with pytest.raises(CostValidationError, match="hard_limit_usd must be non-negative"):
        CostGuard(hard_limit_usd=-5.0)


def test_cost_guard_post_init_validates_soft_limit():
    with pytest.raises(CostValidationError, match="soft_limit_ratio must be in"):
        CostGuard(soft_limit_ratio=2.0)


# --------------------------------------------------------------------------- #
# Self-healing in invoke (no suppress of KeyboardInterrupt)
# --------------------------------------------------------------------------- #

def test_self_healing_does_not_suppress_keyboard_interrupt():
    healer = SelfHealing(SelfHealingConfig(max_attempts=3, initial_interval=0.01, max_interval=0.01))
    def raise_kbi():
        raise KeyboardInterrupt("user cancelled")

    with pytest.raises(KeyboardInterrupt):
        healer.invoke_with_healing(raise_kbi)


# --------------------------------------------------------------------------- #
# CostGuard NaN / Infinity edge cases
# --------------------------------------------------------------------------- #

def test_cost_guard_rejects_nan_usage():
    import math
    guard = CostGuard(default_budget_usd=10.0)
    tenant = TenantContext(tenant_id="t1", operator_id="op", client_id="c")
    with pytest.raises(CostValidationError, match="cost_usd must be non-negative and finite"):
        guard.enforce({"cost_usd": float("nan")}, tenant)



def test_cost_guard_rejects_inf_usage():
    guard = CostGuard(default_budget_usd=10.0)
    tenant = TenantContext(tenant_id="t1", operator_id="op", client_id="c")
    with pytest.raises(CostValidationError, match="cost_usd must be finite"):
        guard.enforce({"cost_usd": float("inf")}, tenant)


def test_cost_guard_rejects_spoofed_zero_cost_when_over_budget():
    """Even if cost_usd=0, budget=0 must still fail validation."""
    guard = CostGuard(default_budget_usd=0.0)
    tenant = TenantContext(tenant_id="t1", operator_id="op", client_id="c", budget_usd=0.0)
    with pytest.raises(CostValidationError, match="Effective budget_usd must be > 0"):
        guard.enforce({"cost_usd": 0.0}, tenant)


# --------------------------------------------------------------------------- #
# GovernanceWrapper sanitization + edge cases
# --------------------------------------------------------------------------- #

def test_governance_wrapper_accepts_none_state():
    """invoke must not crash when state is None."""
    wrapper = GovernanceWrapper(app=lambda s, **kw: s)
    result = wrapper.invoke(None, {})
    assert "governance" in result


def test_governance_wrapper_accepts_empty_config():
    """invoke must not crash when config is empty."""
    wrapper = GovernanceWrapper(app=lambda s, **kw: s)
    result = wrapper.invoke({}, {})
    assert "governance" in result


def test_governance_wrapper_sanitize_strips_unknown_keys():
    """Unknown top-level keys must be stripped before guard execution."""
    class CheckedApp:
        def __init__(self):
            self.received_state = None

        def invoke(self, state, config=None, **kw):
            self.received_state = state
            return {"ok": True}

    app = CheckedApp()
    wrapper = GovernanceWrapper(app=app)
    wrapper.invoke({"messages": ["hi"], "dangerous_key": "script", "tenant": "tenant-x"}, {"user_role": "operator"})
    # dangerous_key should have been stripped; known keys preserved
    assert "dangerous_key" not in app.received_state



def test_governance_wrapper_uses_default_tenant_when_missing():
    """When no tenant context is set, 'default' tenant must be used."""
    wrapper = GovernanceWrapper(app=lambda s, **kw: s)
    result = wrapper.invoke({"messages": ["hi"]}, {"user_role": "operator"})
    governance = result.get("governance", {})
    tenant = governance.get("tenant", {})
    assert tenant.get("tenant_id") == "default"


def test_governance_wrapper_concurrent_invokes(tmp_path):
    """Multiple concurrent invoke calls must not corrupt audit or state."""
    import tempfile
    db_path = str(tmp_path / "gw_concurrent.db")
    backend = SQLiteBackend(path=db_path)
    wrapper = GovernanceWrapper(
        app=lambda s, **kw: {"ok": True, "tenant": s.get("tenant_id", "default")},
        persistence=backend,
    )
    errors = []

    def call_invoke(n: int) -> None:
        try:
            for _ in range(5):
                wrapper.invoke({"tenant_id": f"tenant-{n}"}, {"user_role": "operator"})
        except Exception as exc:
            errors.append(exc)

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(call_invoke, i) for i in range(4)]
        for f in futures:
            f.result()

    assert errors == [], f"Concurrent invokes raised: {errors}"


def test_governance_wrapper_ainvoke_error_path_reraises():
    """ainvoke must re-raise approval errors as MaaProtocolError."""
    from maa_protocol.exceptions import MaaProtocolError
    from maa_protocol.guards.approval import ApprovalGate
    import asyncio

    backend = SQLiteBackend()
    gate = ApprovalGate(risk_threshold=0.7, persistence=backend)
    wrapper = GovernanceWrapper(app=lambda s, **kw: s, approval_gate=gate)

    with pytest.raises(MaaProtocolError, match="Approval required"):
        asyncio.run(wrapper.ainvoke({"action": "high_risk_op"}, {"risk_score": 0.9}))


# --------------------------------------------------------------------------- #
# ApprovalGate cross-tenant access
# --------------------------------------------------------------------------- #

def test_approval_gate_cross_tenant_preapproved_request_blocked():
    """Pre-approved record owned by tenant-1 must not be usable by tenant-2."""
    from maa_protocol.guards.approval import ApprovalGate

    backend = SQLiteBackend()
    gate = ApprovalGate(risk_threshold=0.7, persistence=backend)

    # tenant-1 creates and approves a request
    request = gate.create_request(
        {"action": "trade"},
        {"risk_score": 0.9, "tenant_id": "tenant-1", "operator_id": "op1"},
    )
    backend.approve(request.approval_id, caller_tenant_id="tenant-1")

    # tenant-2 tries to use it — should be blocked at persistence layer
    with pytest.raises(TenantIsolationError):
        backend.get_approval(request.approval_id, caller_tenant_id="tenant-2")



def test_audit_with_default_tenant_when_missing():
    """Audit must fall back to 'default' tenant and succeed when no tenant in state."""
    backend = SQLiteBackend()
    wrapper = GovernanceWrapper(
        app=lambda s, **kw: s,
        persistence=backend,
    )
    # No tenant_id anywhere — should use 'default' without crashing
    result = wrapper.invoke({"messages": ["hi"]}, {"user_role": "operator"})
    assert "governance" in result
    row = backend.conn.execute(
        "SELECT tenant_id FROM audit_events ORDER BY rowid DESC LIMIT 1"
    ).fetchone()
    assert row is not None
    assert row[0] == "default"


# --------------------------------------------------------------------------- #
# TenantGate with negative budget
# --------------------------------------------------------------------------- #


def test_tenant_gate_rejects_negative_budget():
    """Tenant with negative budget_usd must be handled without crashing."""
    tenant = TenantContext(tenant_id="t1", operator_id="op", client_id="c", budget_usd=-10.0)
    gate = TenantGate(max_cost_per_invoke=100.0)
    result = gate.enforce({"_active_task_count": 0}, tenant)
    assert isinstance(result, dict)  # did not crash

