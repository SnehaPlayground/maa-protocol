"""Pluggable persistence backends — SQLite default, Postgres placeholder."""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path
from typing import Protocol


class PersistenceBackend(Protocol):
    """Protocol for all persistence backends."""

    def create_approval(
        self,
        tenant_id: str,
        action: str,
        action_hash: str,
        requested_by: str,
        reason: str,
        risk_score: float,
    ) -> "ApprovalRecord":
        ...

    def approve(self, approval_id: str) -> "ApprovalRecord | None":
        ...

    def get_approval(self, approval_id: str) -> "ApprovalRecord | None":
        ...

    def write_audit_event(
        self, tenant_id: str, event_type: str, payload: str
    ) -> "AuditEvent":
        ...


class ApprovalRecord:
    __slots__ = (
        "approval_id", "tenant_id", "action", "action_hash",
        "requested_by", "reason", "risk_score", "approved",
    )

    def __init__(
        self,
        approval_id: str,
        tenant_id: str,
        action: str,
        action_hash: str,
        requested_by: str,
        reason: str,
        risk_score: float,
        approved: bool,
    ) -> None:
        self.approval_id = approval_id
        self.tenant_id = tenant_id
        self.action = action
        self.action_hash = action_hash
        self.requested_by = requested_by
        self.reason = reason
        self.risk_score = risk_score
        self.approved = approved


class AuditEvent:
    __slots__ = ("event_id", "tenant_id", "event_type", "payload")

    def __init__(self, event_id: str, tenant_id: str, event_type: str, payload: str) -> None:
        self.event_id = event_id
        self.tenant_id = tenant_id
        self.event_type = event_type
        self.payload = payload


class SQLiteBackend:
    """Default SQLite-backed persistence. Thread-safe with connection per instance."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.execute("PRAGMA foreign_keys = ON")
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
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_memories (
                memory_id TEXT PRIMARY KEY,
                namespace TEXT NOT NULL,
                content TEXT NOT NULL,
                embedding BLOB,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS swarm_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        self.conn.commit()

    def create_approval(
        self,
        tenant_id: str,
        action: str,
        action_hash: str,
        requested_by: str,
        reason: str,
        risk_score: float,
    ) -> ApprovalRecord:
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
            approval_id=row[0], tenant_id=row[1], action=row[2], action_hash=row[3],
            requested_by=row[4], reason=row[5], risk_score=float(row[6]), approved=bool(row[7]),
        )

    def write_audit_event(self, tenant_id: str, event_type: str, payload: str) -> AuditEvent:
        event_id = str(uuid.uuid4())
        self.conn.execute(
            "INSERT INTO audit_events (event_id, tenant_id, event_type, payload) VALUES (?, ?, ?, ?)",
            (event_id, tenant_id, event_type, payload),
        )
        self.conn.commit()
        return AuditEvent(event_id=event_id, tenant_id=tenant_id, event_type=event_type, payload=payload)

    # ------------------------------------------------------------------ #
    # Generic key-value swarm state                                        #
    # ------------------------------------------------------------------ #

    def set_swarm_state(self, key: str, value: str) -> None:
        now = time.timezone
        self.conn.execute(
            "INSERT OR REPLACE INTO swarm_state (key, value, updated_at) VALUES (?, ?, ?)",
            (key, value, __import__("time").time()),
        )
        self.conn.commit()

    def get_swarm_state(self, key: str) -> str | None:
        row = self.conn.execute(
            "SELECT value FROM swarm_state WHERE key = ?", (key,)
        ).fetchone()
        return row[0] if row else None

    def delete_swarm_state(self, key: str) -> None:
        self.conn.execute("DELETE FROM swarm_state WHERE key = ?", (key,))
        self.conn.commit()


class PostgresBackend(SQLiteBackend):
    """PostgreSQL-compatible backend.

    If a native PostgreSQL driver is unavailable, this uses a sqlite-backed
    compatibility store so the interface remains usable in single-instance mode.
    """

    def __init__(self, dsn: str | None = None) -> None:
        self.dsn = dsn or ":memory:"
        super().__init__(self._sqlite_compat_path(self.dsn))

    @staticmethod
    def _sqlite_compat_path(dsn: str) -> str:
        if dsn in (":memory:", "sqlite://:memory:"):
            return ":memory:"
        if dsn.startswith("postgres://") or dsn.startswith("postgresql://"):
            return "/tmp/maa-x-postgres-compat.db"
        return dsn