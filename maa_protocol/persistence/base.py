"""Pluggable persistence backends for approvals and audit events."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from ..exceptions import PersistenceError, TenantIsolationError

_SECRET_KEYS = {
    "secret",
    "key",
    "password",
    "token",
    "credential",
    "credentials",
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "bearer",
    "private",
    "session",
}
_MAX_PAYLOAD_BYTES = 10 * 1024


class PersistenceBackend(Protocol):
    def create_approval(
        self,
        tenant_id: str,
        action: str,
        action_hash: str,
        requested_by: str,
        reason: str,
        risk_score: float,
        *,
        caller_tenant_id: str | None = None,
    ) -> ApprovalRecord:
        ...

    def approve(
        self,
        approval_id: str,
        *,
        caller_tenant_id: str | None = None,
    ) -> ApprovalRecord | None:
        ...

    def get_approval(
        self,
        approval_id: str,
        *,
        caller_tenant_id: str | None = None,
    ) -> ApprovalRecord | None:
        ...

    def write_audit_event(
        self,
        tenant_id: str,
        event_type: str,
        payload: Any,
        *,
        caller_tenant_id: str | None = None,
    ) -> AuditEvent:
        ...


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


def _redact_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: ("[REDACTED]" if key.lower() in _SECRET_KEYS else _redact_sensitive(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_sensitive(item) for item in value]
    return value


def _redact_plain_text(text: str) -> str:
    redacted = text
    for key in _SECRET_KEYS:
        redacted = redacted.replace(f"{key}=", f"{key}=[REDACTED]")
    return redacted


def _sanitize_payload(payload: Any) -> str:
    if isinstance(payload, str):
        raw = _redact_plain_text(payload)
    else:
        raw = json.dumps(_redact_sensitive(payload), default=str, separators=(",", ":"))
    encoded = raw.encode("utf-8")
    if len(encoded) <= _MAX_PAYLOAD_BYTES:
        return raw
    truncated = encoded[: _MAX_PAYLOAD_BYTES - len("...[TRUNCATED]")].decode(
        "utf-8",
        errors="ignore",
    )
    return truncated + "...[TRUNCATED]"


class SQLiteBackend:
    """Thread-safe SQLite backend with tenant isolation."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        self._lock = threading.RLock()
        self.conn: sqlite3.Connection | None = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._init_db()

    def close(self) -> None:
        with self._lock:
            if self.conn is not None:
                self.conn.close()
                self.conn = None

    def __enter__(self) -> SQLiteBackend:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def _require_conn(self) -> sqlite3.Connection:
        if self.conn is None:
            raise PersistenceError("SQLite connection is closed")
        return self.conn

    def _init_db(self) -> None:
        self._execsql(
            """
            CREATE TABLE IF NOT EXISTS approvals (
                approval_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                action TEXT NOT NULL,
                action_hash TEXT NOT NULL,
                requested_by TEXT NOT NULL,
                reason TEXT NOT NULL,
                risk_score REAL NOT NULL,
                approved INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL
            )
            """,
            (),
        )
        self._execsql(
            "CREATE INDEX IF NOT EXISTS idx_approvals_tenant_id ON approvals(tenant_id)",
            (),
        )
        self._execsql(
            """
            CREATE TABLE IF NOT EXISTS audit_events (
                event_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at REAL NOT NULL
            )
            """,
            (),
        )
        self._execsql(
            "CREATE INDEX IF NOT EXISTS idx_audit_events_tenant_id ON audit_events(tenant_id)",
            (),
        )

    def _execsql(self, sql: str, params: tuple[Any, ...]) -> list[tuple[Any, ...]]:
        try:
            with self._lock:
                conn = self._require_conn()
                cursor = conn.execute(sql, params)
                conn.commit()
                return cursor.fetchall()
        except sqlite3.Error as exc:
            raise PersistenceError(f"SQLite error: {exc}") from exc

    @staticmethod
    def _ensure_tenant_access(stored_tenant_id: str, caller_tenant_id: str | None) -> None:
        if caller_tenant_id is not None and stored_tenant_id != caller_tenant_id:
            raise TenantIsolationError(
                "Cross-tenant access denied: caller "
                f"'{caller_tenant_id}' attempted to access tenant '{stored_tenant_id}'"
            )

    def create_approval(
        self,
        tenant_id: str,
        action: str,
        action_hash: str,
        requested_by: str,
        reason: str,
        risk_score: float,
        *,
        caller_tenant_id: str | None = None,
    ) -> ApprovalRecord:
        self._ensure_tenant_access(tenant_id, caller_tenant_id)
        approval_id = str(uuid.uuid4())
        sanitized_reason = _sanitize_payload(reason)
        try:
            self._execsql(
                """
                INSERT INTO approvals (
                    approval_id,
                    tenant_id,
                    action,
                    action_hash,
                    requested_by,
                    reason,
                    risk_score,
                    approved,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
                """,
                (
                    approval_id,
                    tenant_id,
                    action,
                    action_hash,
                    requested_by,
                    sanitized_reason,
                    float(risk_score),
                    time.time(),
                ),
            )
        except PersistenceError as exc:
            raise PersistenceError(f"Failed to create approval: {exc}") from exc
        return ApprovalRecord(
            approval_id,
            tenant_id,
            action,
            action_hash,
            requested_by,
            sanitized_reason,
            float(risk_score),
            False,
        )

    def get_approval(
        self,
        approval_id: str,
        *,
        caller_tenant_id: str | None = None,
    ) -> ApprovalRecord | None:
        try:
            rows = self._execsql(
                "SELECT approval_id, tenant_id, action, action_hash, requested_by, "
                "reason, risk_score, approved FROM approvals WHERE approval_id = ?",
                (approval_id,),
            )
        except PersistenceError as exc:
            raise PersistenceError(f"Failed to retrieve approval: {exc}") from exc
        if not rows:
            return None
        row = rows[0]
        self._ensure_tenant_access(str(row[1]), caller_tenant_id)
        return ApprovalRecord(
            str(row[0]),
            str(row[1]),
            str(row[2]),
            str(row[3]),
            str(row[4]),
            str(row[5]),
            float(row[6]),
            bool(row[7]),
        )

    def approve(
        self,
        approval_id: str,
        *,
        caller_tenant_id: str | None = None,
    ) -> ApprovalRecord | None:
        record = self.get_approval(approval_id, caller_tenant_id=caller_tenant_id)
        if record is None:
            return None
        try:
            self._execsql("UPDATE approvals SET approved = 1 WHERE approval_id = ?", (approval_id,))
        except PersistenceError as exc:
            raise PersistenceError(f"Failed to approve {approval_id}: {exc}") from exc
        return ApprovalRecord(
            approval_id=record.approval_id,
            tenant_id=record.tenant_id,
            action=record.action,
            action_hash=record.action_hash,
            requested_by=record.requested_by,
            reason=record.reason,
            risk_score=record.risk_score,
            approved=True,
        )

    def write_audit_event(
        self,
        tenant_id: str,
        event_type: str,
        payload: Any,
        *,
        caller_tenant_id: str | None = None,
    ) -> AuditEvent:
        self._ensure_tenant_access(tenant_id, caller_tenant_id)
        event_id = str(uuid.uuid4())
        sanitized_payload = _sanitize_payload(payload)
        try:
            self._execsql(
                "INSERT INTO audit_events "
                "(event_id, tenant_id, event_type, payload, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (event_id, tenant_id, event_type, sanitized_payload, time.time()),
            )
        except PersistenceError as exc:
            raise PersistenceError(f"Failed to write audit event: {exc}") from exc
        return AuditEvent(
            event_id=event_id,
            tenant_id=tenant_id,
            event_type=event_type,
            payload=sanitized_payload,
        )

    def list_approvals(self, tenant_id: str | None = None) -> list[ApprovalRecord]:
        query = (
            "SELECT approval_id, tenant_id, action, action_hash, requested_by, "
            "reason, risk_score, approved FROM approvals"
        )
        params: tuple[Any, ...] = ()
        if tenant_id:
            query += " WHERE tenant_id = ?"
            params = (tenant_id,)
        query += " ORDER BY created_at DESC"
        rows = self._execsql(query, params)
        return [
            ApprovalRecord(
                str(r[0]),
                str(r[1]),
                str(r[2]),
                str(r[3]),
                str(r[4]),
                str(r[5]),
                float(r[6]),
                bool(r[7]),
            )
            for r in rows
        ]

    def list_audit_events(self, tenant_id: str | None = None, limit: int = 20) -> list[AuditEvent]:
        query = "SELECT event_id, tenant_id, event_type, payload FROM audit_events"
        params: tuple[Any, ...] = ()
        if tenant_id:
            query += " WHERE tenant_id = ?"
            params = (tenant_id,)
        query += " ORDER BY created_at DESC LIMIT ?"
        params = params + (limit,)
        rows = self._execsql(query, params)
        return [AuditEvent(str(r[0]), str(r[1]), str(r[2]), str(r[3])) for r in rows]


class PostgresBackend:
    def __init__(self, dsn: str | None = None) -> None:
        raise NotImplementedError(
            "PostgresBackend is a placeholder and not yet implemented. "
            "Use SQLiteBackend for current deployments."
        )
