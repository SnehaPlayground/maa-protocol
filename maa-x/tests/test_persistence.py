"""Tests for maa_x persistence module."""

import pytest
from maa_x.persistence import SQLiteBackend, ApprovalRecord, AuditEvent


def test_sqlite_backend_create_and_approve():
    db = SQLiteBackend(":memory:")
    record = db.create_approval(
        tenant_id="t", action="test", action_hash="h1",
        requested_by="op", reason="testing", risk_score=0.5,
    )
    assert record.approval_id
    assert not record.approved

    approved = db.approve(record.approval_id)
    assert approved is not None
    assert approved.approved


def test_sqlite_backend_get_approval():
    db = SQLiteBackend(":memory:")
    record = db.create_approval(
        tenant_id="t", action="get_test", action_hash="h2",
        requested_by="op", reason="testing", risk_score=0.5,
    )
    fetched = db.get_approval(record.approval_id)
    assert fetched is not None
    assert fetched.approval_id == record.approval_id


def test_sqlite_backend_audit_event():
    db = SQLiteBackend(":memory:")
    event = db.write_audit_event("t", "test.event", '{"key": "value"}')
    assert event.event_id
    assert event.tenant_id == "t"


def test_approval_record_slots():
    record = ApprovalRecord(
        approval_id="a1", tenant_id="t", action="test",
        action_hash="h", requested_by="op", reason="r", risk_score=0.5, approved=False,
    )
    assert hasattr(record, "approval_id")  # slots work


def test_audit_event_slots():
    event = AuditEvent(event_id="e1", tenant_id="t", event_type="test", payload="{}")
    assert hasattr(event, "event_id")