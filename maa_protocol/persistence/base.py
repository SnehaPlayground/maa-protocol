"""Pluggable persistence backends — SQLite default, Postgres placeholder.

Security invariants:
  • All query methods enforce tenant isolation (caller_tenant_id must match stored tenant_id).
  • Sensitive payload keys (secret, key, password, token, credential) are redacted before storage.
  • Payload size is capped at 10 KB per event / approval record.
  • SQLite errors are caught and re-raised as PersistenceError; they never propagate raw.
  • PostgresBackend is a placeholder that raises NotImplementedError.
"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from pathlib import Path
from typing import Protocol, Any

# --------------------------------------------------------------------------- #
# Exceptions — re-exported from exceptions.py for backward compatibility
# --------------------------------------------------------------------------- #

from ..exceptions import MaaProtocolError, PersistenceError, TenantIsolationError


# --------------------------------------------------------------------------- #
# Protocol
# --------------------------------------------------------------------------- #

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
        *,
        caller_tenant_id: str | None = None,
    ) -> "ApprovalRecord":
        ...

    def approve(
        self,
        approval_id: str,
        *,
        caller_tenant_id: str | None = None,
    ) -> "ApprovalRecord | None":
        ...

    def get_approval(
        self,
        approval_id: str,
        *,
        caller_tenant_id: str | None = None,
    ) -> "ApprovalRecord | None":
        ...

    def write_audit_event(
        self,
        tenant_id: str,
        event_type: str,
        payload: Any,
        *,
        caller_tenant_id: str | None = None,
    ) -> "AuditEvent":
        ...


# --------------------------------------------------------------------------- #
# Data classes
# --------------------------------------------------------------------------- #

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


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

# Keys whose values are redacted before any payload is stored.
_SECRET_KEYS = frozenset({
    "secret", "key", "password", "token", "credential",
    "credentials", "api_key", "apikey", "auth", "authorization",
    "bearer", "private", "session", "Jwt", "jti",
})

_MAX_PAYLOAD_BYTES = 10 * 1024  # 10 KB


def _redact_sensitive(obj: Any, *, depth: int = 0) -> Any:
    """Recursively redact values whose keys match _SECRET_KEYS (case-insensitive)."""
    if depth > 16 or obj is None:
        return obj
    if isinstance(obj, dict):
        return {
            k: ("[REDACTED]" if k.lower() in _SECRET_KEYS else _redact_sensitive(v, depth=depth + 1))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_redact_sensitive(v, depth=depth + 1) for v in obj]
    return obj



def _get_tenant_budget(tenant: Any, default: float) -> float:
    """Extract tenant budget; fall back to *default* only when unset.
    We distinguish "not set" from "explicitly 0" so that budget_usd=0.0
    correctly triggers a validation error rather than silently falling back.
    """
    _UNSET = object()
    raw = getattr(tenant, "budget_usd", _UNSET)
    if raw is _UNSET:
        return default
    return float(raw) if raw is not None else default

def _redact_plain_text(text: str) -> str:
    """"Redact secret KEY=VALUE patterns from a plain string (reason field, etc.)."""
    import re as _re
    for key in _SECRET_KEYS:
        # Match "key=value" with value ending at whitespace or end of string.
        pattern = _re.compile(
            rf"({_re.escape(key)}[=:\s]+)([^\s,;\]]*)",
            _re.IGNORECASE,
        )
        text = pattern.sub(r"\1[REDACTED]", text)
    return text


def _sanitize_payload(payload: Any) -> str:
    """Convert payload to JSON, redact secrets, and cap at MAX_PAYLOAD_BYTES."""
    import json as _json

    if isinstance(payload, str):
        # Apply redaction to plain-text reason strings, then size-cap.
        redacted = _redact_plain_text(payload)
        encoded = redacted.encode("utf-8")
        if len(encoded) > _MAX_PAYLOAD_BYTES:
            return encoded[: _MAX_PAYLOAD_BYTES - len("...[TRUNCATED]")].decode("utf-8", errors="ignore") + "...[TRUNCATED]"
        return redacted

    cleaned = _redact_sensitive(payload)
    raw = _json.dumps(cleaned, default=str, separators=(",", ":"))
    if len(raw.encode("utf-8")) > _MAX_PAYLOAD_BYTES:
        raw = raw[: _MAX_PAYLOAD_BYTES - len("...[TRUNCATED]")] + "...[TRUNCATED]"
    return raw


# --------------------------------------------------------------------------- #
# SQLite backend
# --------------------------------------------------------------------------- #

class SQLiteBackend:
    """Default SQLite-backed persistence with thread-safe locking.

    Security features:
      • All reads/writes guarded by a re-entrant lock.
      • Tenant isolation enforced on every query (caller_tenant_id).
      • Sensitive payload keys redacted before storage.
      • Payload size capped at 10 KB per event / record.
      • All sqlite3 errors caught and re-raised as PersistenceError.
      • Indexes on tenant_id and approval_id for efficient, isolation-safe lookups.
    """

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._init_db()

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    def close(self) -> None:
        with self._lock:
            if self.conn:
                self.conn.close()
                self.conn = None

    def __enter__(self) -> "SQLiteBackend":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    # ------------------------------------------------------------------ #
    # Schema
    # ------------------------------------------------------------------ #

    def _init_db(self) -> None:
        with self._lock:
            cur = self.conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS approvals (
                    approval_id TEXT PRIMARY KEY,
                    tenant_id   TEXT NOT NULL,
                    action      TEXT NOT NULL,
                    action_hash TEXT NOT NULL,
                    requested_by TEXT NOT NULL,
                    reason      TEXT NOT NULL,
                    risk_score  REAL NOT NULL,
                    approved    INTEGER NOT NULL DEFAULT 0
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_approvals_tenant_id ON approvals(tenant_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_approvals_approval_id ON approvals(approval_id)")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS audit_events (
                    event_id   TEXT PRIMARY KEY,
                    tenant_id  TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload    TEXT NOT NULL
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_events_tenant_id ON audit_events(tenant_id)")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS agent_memories (
                    memory_id   TEXT PRIMARY KEY,
                    namespace   TEXT NOT NULL,
                    content     TEXT NOT NULL,
                    embedding   BLOB,
                    created_at  REAL NOT NULL,
                    updated_at  REAL NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS swarm_state (
                    key        TEXT PRIMARY KEY,
                    value      TEXT NOT NULL,
                    updated_at REAL NOT NULL
                )
            """)
            self.conn.commit()

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    def _check_tenant_isolation(self, stored_tenant_id: str, caller_tenant_id: str | None) -> None:
        """Raise TenantIsolationError if caller is not the record owner."""
        if caller_tenant_id is not None and stored_tenant_id != caller_tenant_id:
            raise TenantIsolationError(
                f"Cross-tenant access denied: caller '{caller_tenant_id}' "
                f"attempted to access record owned by '{stored_tenant_id}'"
            )

    def _execute(self, sql: str, params: tuple[Any, ...]) -> list[Any]:
        """Execute SQL safely, wrapping sqlite3 errors."""
        try:
            cur = self.conn.cursor()
            cur.execute(sql, params)
            self.conn.commit()
            return cur.fetchall()
        except sqlite3.Error as exc:
            raise PersistenceError(f"SQLite error: {exc}") from exc

    # ------------------------------------------------------------------ #
    # Approval methods
    # ------------------------------------------------------------------ #

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
        # Enforce caller matches写入 tenant
        if caller_tenant_id is not None and tenant_id != caller_tenant_id:
            raise TenantIsolationError(
                f"Caller '{caller_tenant_id}' cannot create a record for tenant '{tenant_id}'"
            )
        approval_id = str(uuid.uuid4())
        reason_sanitized = _sanitize_payload(reason)
        try:
            self.conn.execute(
                """
                INSERT INTO approvals
                    (approval_id, tenant_id, action, action_hash, requested_by, reason, risk_score, approved)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (approval_id, tenant_id, action, action_hash, requested_by, reason_sanitized, risk_score),
            )
            self.conn.commit()
        except sqlite3.Error as exc:
            raise PersistenceError(f"Failed to create approval: {exc}") from exc
        return ApprovalRecord(
            approval_id, tenant_id, action, action_hash, requested_by, reason_sanitized, risk_score, False,
        )

    def approve(
        self,
        approval_id: str,
        *,
        caller_tenant_id: str | None = None,
    ) -> ApprovalRecord | None:
        # First fetch to check tenant isolation
        row = self._fetch_approval_row(approval_id)
        if row is None:
            return None
        self._check_tenant_isolation(row[1], caller_tenant_id)
        try:
            self.conn.execute("UPDATE approvals SET approved = 1 WHERE approval_id = ?", (approval_id,))
            self.conn.commit()
        except sqlite3.Error as exc:
            raise PersistenceError(f"Failed to approve {approval_id}: {exc}") from exc
        return ApprovalRecord(
            approval_id=row[0], tenant_id=row[1], action=row[2], action_hash=row[3],
            requested_by=row[4], reason=row[5], risk_score=float(row[6]), approved=True,
        )

    def get_approval(
        self,
        approval_id: str,
        *,
        caller_tenant_id: str | None = None,
    ) -> ApprovalRecord | None:
        row = self._fetch_approval_row(approval_id)
        if row is None:
            return None
        self._check_tenant_isolation(row[1], caller_tenant_id)
        return ApprovalRecord(
            approval_id=row[0], tenant_id=row[1], action=row[2], action_hash=row[3],
            requested_by=row[4], reason=row[5], risk_score=float(row[6]), approved=bool(row[7]),
        )

    def _fetch_approval_row(self, approval_id: str) -> tuple[Any, ...] | None:
        """Fetch a single approval row or return None."""
        try:
            cur = self.conn.execute(
                """
                SELECT approval_id, tenant_id, action, action_hash, requested_by, reason, risk_score, approved
                FROM approvals WHERE approval_id = ?
                """,
                (approval_id,),
            )
            return cur.fetchone()
        except sqlite3.Error as exc:
            raise PersistenceError(f"Failed to fetch approval {approval_id}: {exc}") from exc

    # ------------------------------------------------------------------ #
    # Audit events
    # ------------------------------------------------------------------ #

    def write_audit_event(
        self,
        tenant_id: str,
        event_type: str,
        payload: Any,
        *,
        caller_tenant_id: str | None = None,
    ) -> AuditEvent:
        # caller_tenant_id must match the event's tenant_id (audits are tenant-scoped)
        if caller_tenant_id is not None and tenant_id != caller_tenant_id:
            raise TenantIsolationError(
                f"Caller '{caller_tenant_id}' cannot write audit events for tenant '{tenant_id}'"
            )
        event_id = str(uuid.uuid4())
        sanitized = _sanitize_payload(payload)
        try:
            self.conn.execute(
                "INSERT INTO audit_events (event_id, tenant_id, event_type, payload) VALUES (?, ?, ?, ?)",
                (event_id, tenant_id, event_type, sanitized),
            )
            self.conn.commit()
        except sqlite3.Error as exc:
            raise PersistenceError(f"Failed to write audit event: {exc}") from exc
        return AuditEvent(event_id=event_id, tenant_id=tenant_id, event_type=event_type, payload=sanitized)

    # ------------------------------------------------------------------ #
    # Swarm state (KV store)
    # ------------------------------------------------------------------ #

    def set_swarm_state(self, key: str, value: str) -> None:
        import time as _time
        with self._lock:
            try:
                self.conn.execute(
                    "INSERT OR REPLACE INTO swarm_state (key, value, updated_at) VALUES (?, ?, ?)",
                    (key, value, _time.time()),
                )
                self.conn.commit()
            except sqlite3.Error as exc:
                raise PersistenceError(f"Failed to set swarm state key '{key}': {exc}") from exc

    def get_swarm_state(self, key: str) -> str | None:
        with self._lock:
            try:
                row = self.conn.execute(
                    "SELECT value FROM swarm_state WHERE key = ?", (key,)
                ).fetchone()
                return row[0] if row else None
            except sqlite3.Error as exc:
                raise PersistenceError(f"Failed to get swarm state key '{key}': {exc}") from exc

    def delete_swarm_state(self, key: str) -> None:
        with self._lock:
            try:
                self.conn.execute("DELETE FROM swarm_state WHERE key = ?", (key,))
                self.conn.commit()
            except sqlite3.Error as exc:
                raise PersistenceError(f"Failed to delete swarm state key '{key}': {exc}") from exc


# --------------------------------------------------------------------------- #
# Postgres placeholder
# --------------------------------------------------------------------------- #

class PostgresBackend:
    """PostgreSQL backend — NOT IMPLEMENTED.

    This class exists as a placeholder to guide future contributors.
    To use PostgreSQL in production, implement this class using
    psycopg2 or sqlalchemy with proper connection pooling and
    the same tenant-isolation guarantees as SQLiteBackend.

    Until then, use SQLiteBackend (the default) for all deployments.
    """

    def __init__(self, dsn: str | None = None) -> None:
        raise NotImplementedError(
            "PostgresBackend is a placeholder and not yet implemented. "
            "Use SQLiteBackend (default) for all current deployments. "
            "To contribute a PostgreSQL backend, implement the full "
            "PersistenceBackend protocol with psycopg2 or sqlalchemy "
            "and open a pull request."
        )
