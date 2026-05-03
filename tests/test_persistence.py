import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from maa_protocol import PersistenceError, SQLiteBackend, TenantIsolationError


def test_create_and_get_approval_round_trip():
    backend = SQLiteBackend()
    record = backend.create_approval(
        tenant_id="tenant-1",
        action="trade",
        action_hash="hash-1",
        requested_by="op-1",
        reason="review",
        risk_score=0.5,
        caller_tenant_id="tenant-1",
    )
    fetched = backend.get_approval(record.approval_id, caller_tenant_id="tenant-1")
    assert fetched is not None
    assert fetched.action == "trade"


def test_cross_tenant_read_is_blocked():
    backend = SQLiteBackend()
    record = backend.create_approval(
        tenant_id="tenant-1",
        action="trade",
        action_hash="hash-1",
        requested_by="op-1",
        reason="review",
        risk_score=0.5,
        caller_tenant_id="tenant-1",
    )
    with pytest.raises(TenantIsolationError):
        backend.get_approval(record.approval_id, caller_tenant_id="tenant-2")


def test_cross_tenant_approve_is_blocked():
    backend = SQLiteBackend()
    record = backend.create_approval(
        tenant_id="tenant-1",
        action="trade",
        action_hash="hash-1",
        requested_by="op-1",
        reason="review",
        risk_score=0.5,
        caller_tenant_id="tenant-1",
    )
    with pytest.raises(TenantIsolationError):
        backend.approve(record.approval_id, caller_tenant_id="tenant-2")


def test_write_audit_event_redacts_secret_values():
    backend = SQLiteBackend()
    event = backend.write_audit_event(
        tenant_id="tenant-1",
        event_type="invoke",
        payload={"password": "secret", "action": "read"},
        caller_tenant_id="tenant-1",
    )
    data = json.loads(event.payload)
    assert data["password"] == "[REDACTED]"


def test_write_audit_event_cross_tenant_blocked():
    backend = SQLiteBackend()
    with pytest.raises(TenantIsolationError):
        backend.write_audit_event("tenant-1", "invoke", {"ok": True}, caller_tenant_id="tenant-2")


def test_list_approvals_returns_items():
    backend = SQLiteBackend()
    backend.create_approval(
        "tenant-1", "a1", "h1", "op", "reason", 0.1, caller_tenant_id="tenant-1"
    )
    backend.create_approval(
        "tenant-2", "a2", "h2", "op", "reason", 0.2, caller_tenant_id="tenant-2"
    )
    assert len(backend.list_approvals()) == 2
    assert len(backend.list_approvals("tenant-1")) == 1


def test_list_audit_events_returns_filtered_rows():
    backend = SQLiteBackend()
    backend.write_audit_event("tenant-1", "event-1", {"n": 1}, caller_tenant_id="tenant-1")
    backend.write_audit_event("tenant-2", "event-2", {"n": 2}, caller_tenant_id="tenant-2")
    assert len(backend.list_audit_events(limit=5)) == 2
    assert len(backend.list_audit_events("tenant-1", limit=5)) == 1


def test_sqlite_errors_are_wrapped_for_create(monkeypatch):
    backend = SQLiteBackend()

    def boom(sql, params):
        raise PersistenceError("SQLite error: table locked")

    monkeypatch.setattr(backend, "_execsql", boom)
    with pytest.raises(PersistenceError, match="Failed to create approval"):
        backend.create_approval(
            "tenant-1", "a", "h", "op", "reason", 0.1, caller_tenant_id="tenant-1"
        )


def test_sqlite_errors_are_wrapped_for_get(monkeypatch):
    backend = SQLiteBackend()

    def boom(sql, params):
        raise PersistenceError("SQLite error: boom")

    monkeypatch.setattr(backend, "_execsql", boom)
    with pytest.raises(PersistenceError, match="Failed to retrieve approval"):
        backend.get_approval("missing", caller_tenant_id="tenant-1")


def test_close_is_idempotent():
    backend = SQLiteBackend()
    backend.close()
    backend.close()


def test_context_manager_closes_connection():
    with SQLiteBackend() as backend:
        backend.write_audit_event("tenant-1", "invoke", {"ok": True}, caller_tenant_id="tenant-1")
    with pytest.raises(PersistenceError):
        backend.list_audit_events()


def test_concurrent_create_approval_succeeds():
    backend = SQLiteBackend()

    def worker(index: int) -> None:
        backend.create_approval(
            tenant_id=f"tenant-{index}",
            action="trade",
            action_hash=f"hash-{index}",
            requested_by="op",
            reason="review",
            risk_score=0.3,
            caller_tenant_id=f"tenant-{index}",
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(worker, range(12)))

    assert len(backend.list_approvals()) == 12
