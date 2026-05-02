from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(slots=True)
class ApprovalRecord:
    approval_id: str
    tenant_id: str
    action: str
    action_hash: str
    requested_by: str
    reason: str
    risk_score: float
    approved: bool


@dataclass(slots=True)
class AuditEvent:
    event_id: str
    tenant_id: str
    event_type: str
    payload: str


class PersistenceBackend(Protocol):
    def create_approval(self, tenant_id: str, action: str, action_hash: str, requested_by: str, reason: str, risk_score: float) -> ApprovalRecord: ...
    def approve(self, approval_id: str) -> ApprovalRecord | None: ...
    def get_approval(self, approval_id: str) -> ApprovalRecord | None: ...
    def write_audit_event(self, tenant_id: str, event_type: str, payload: str) -> AuditEvent: ...


class SQLiteBackend:
    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        self.conn = sqlite3.connect(self.path)
        self._init_db()

    def _init_db(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS approvals (
                approval_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                action TEXT NOT NULL,
                action_hash TEXT NOT NULL,
                requested_by TEXT NOT NULL,
                reason TEXT NOT NULL,
                risk_score REAL NOT NULL,
                approved INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_events (
                event_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )
        self.conn.commit()

    def create_approval(self, tenant_id: str, action: str, action_hash: str, requested_by: str, reason: str, risk_score: float) -> ApprovalRecord:
        approval_id = str(uuid.uuid4())
        self.conn.execute(
            "INSERT INTO approvals (approval_id, tenant_id, action, action_hash, requested_by, reason, risk_score, approved) VALUES (?, ?, ?, ?, ?, ?, ?, 0)",
            (approval_id, tenant_id, action, action_hash, requested_by, reason, risk_score),
        )
        self.conn.commit()
        return ApprovalRecord(approval_id, tenant_id, action, action_hash, requested_by, reason, risk_score, False)

    def approve(self, approval_id: str) -> ApprovalRecord | None:
        self.conn.execute("UPDATE approvals SET approved = 1 WHERE approval_id = ?", (approval_id,))
        self.conn.commit()
        return self.get_approval(approval_id)

    def get_approval(self, approval_id: str) -> ApprovalRecord | None:
        row = self.conn.execute(
            "SELECT approval_id, tenant_id, action, action_hash, requested_by, reason, risk_score, approved FROM approvals WHERE approval_id = ?",
            (approval_id,),
        ).fetchone()
        if not row:
            return None
        return ApprovalRecord(
            approval_id=row[0],
            tenant_id=row[1],
            action=row[2],
            action_hash=row[3],
            requested_by=row[4],
            reason=row[5],
            risk_score=float(row[6]),
            approved=bool(row[7]),
        )

    def write_audit_event(self, tenant_id: str, event_type: str, payload: str) -> AuditEvent:
        event_id = str(uuid.uuid4())
        self.conn.execute(
            "INSERT INTO audit_events (event_id, tenant_id, event_type, payload) VALUES (?, ?, ?, ?)",
            (event_id, tenant_id, event_type, payload),
        )
        self.conn.commit()
        return AuditEvent(event_id=event_id, tenant_id=tenant_id, event_type=event_type, payload=payload)

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "SQLiteBackend":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


class PostgresBackend:
    """Placeholder — raises NotImplementedError until a dedicated SQLAlchemy/Postgres implementation is added."""

    def create_approval(self, tenant_id: str, action: str, action_hash: str, requested_by: str, reason: str, risk_score: float) -> ApprovalRecord:
        raise NotImplementedError("PostgresBackend is not yet implemented")

    def approve(self, approval_id: str) -> ApprovalRecord | None:
        raise NotImplementedError("PostgresBackend is not yet implemented")

    def get_approval(self, approval_id: str) -> ApprovalRecord | None:
        raise NotImplementedError("PostgresBackend is not yet implemented")

    def write_audit_event(self, tenant_id: str, event_type: str, payload: str) -> AuditEvent:
        raise NotImplementedError("PostgresBackend is not yet implemented")

    def close(self) -> None:
        raise NotImplementedError("PostgresBackend is not yet implemented")

    def __enter__(self) -> "PostgresBackend":
        raise NotImplementedError("PostgresBackend is not yet implemented")

    def __exit__(self, *exc_info: object) -> None:
        raise NotImplementedError("PostgresBackend is not yet implemented")
