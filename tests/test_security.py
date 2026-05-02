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


def test_concurrent_approvals_all_succeed():
    """Multiple threads writing to the same SQLiteBackend must not corrupt data."""
    backend = SQLiteBackend()
    errors = []

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
