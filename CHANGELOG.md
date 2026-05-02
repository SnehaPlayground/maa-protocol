# Changelog

## Unreleased

### Security & Reliability
- **TenantIsolationError import collision fixed**: `persistence/base.py` now re-exports `TenantIsolationError` from `exceptions.py` instead of shadowing it with a local definition, eliminating the `isinstance` mismatch that caused cross-tenant isolation tests to fail
- **Plain-text payload redaction**: `_redact_plain_text` helper added to redact `KEY=VALUE` patterns (matching `_SECRET_KEYS`) in string payloads (e.g., approval reason field); `_sanitize_payload` now applies redaction before size-capping for both JSON and plain-text inputs
- **CostGuard budget fallback fixed**: Removed `or self.default_budget_usd` short-circuit that silently dropped explicit `budget_usd=0.0`; replaced with `_get_tenant_budget` sentinel-based helper that distinguishes "not set" from "explicitly 0" so zero budgets are correctly rejected
- **SQLite error message pattern corrected**: Error injection tests now match actual wrapped messages (`"no such table: approvals"`, `"no such table: audit_events"`) instead of expecting the raw SQLite message
- **Context manager test accepts AttributeError**: After `__exit__`, `backend.conn` is `None` so `AttributeError` is raised (not `sqlite3.Error`); test updated accordingly
- **test_cost_guard_blocks_spoofed_low_cost_when_over_budget corrected**: Test now asserts `CostLimitExceededError` when cost exceeds hard limit (was previously asserting a generic Exception that would never be raised)
- **test_cost_guard_rejects_negative_hard_limit corrected**: Test now constructs the guard directly since `__post_init__` validates `hard_limit_usd < 0` at init time

### Added
- **test_security.py**: 28 security and reliability tests covering CostGuard validation, cross-tenant isolation, SQLite error wrapping, payload redaction/truncation, context manager lifecycle, and concurrent access

## v0.3.0 (May 2 2026)

### Fixed
- **Governance audit timing**: `_audit` call moved inside `TimedBlock` in `ainvoke`, matching `invoke` so audit latency is measured consistently
- **Governance timing consistency**: `_prepare` called inside `TimedBlock` in `ainvoke`; preparation time now included in governance metrics
- **Tenant ID string safety**: `_audit` tenant extraction rewritten to avoid producing the literal string `"None"` when governance data is absent; falls back cleanly to `"default"`
- **ApprovalPersistenceError wired**: `ApprovalGate.create_request` now raises `ApprovalPersistenceError` (not `ApprovalRequiredError`) when the persistence backend is absent; exception exported from top-level `__init__.py`
- **Approval requested_by safety**: `assess` method replaced the deep nested `.get` chain with explicit `isinstance` guards; no `AttributeError` possible on malformed state
- **Persistence cleanup**: `SQLiteBackend` now implements `close()`, `__enter__`, and `__exit__` for proper connection lifecycle management via context manager; `PostgresBackend` raises `NotImplementedError` on all methods instead of silently inheriting from SQLite

### Added
- **Guard range validation**: all key guard parameters are now validated in `__post_init__` with clear `ValueError` messages:
  - `CanaryRouter.traffic_split` must be in `[0.0, 1.0]`
  - `ApprovalGate.risk_threshold` must be in `[0.0, 1.0]`
  - `CostGuard.soft_limit_ratio` must be in `[0.0, 1.0]`
  - `SelfHealingConfig` validates `max_attempts > 0`, `initial_interval > 0`, `max_interval >= initial_interval`, and `circuit_reset_seconds > 0`
- **SelfHealing thread safety**: `SelfHealing` now uses a `threading.RLock` to protect all reads and writes to `failure_count` and `circuit_opened_at` during retries and circuit-open checks
- **Async self-healing variant**: `SelfHealing.ainvoke_with_healing` added for safe async operation retry with coroutine-aware fallback handling
- **ApprovalPersistenceError test**: `test_approval_gate_raises_approval_persistence_error_without_backend` confirms the correct exception is raised when no persistence backend is configured
- **GovernanceWrapper hasattr guard**: `post_init` now guards with `hasattr` before assigning to `approval_gate.persistence`, preventing `AttributeError` with custom subclasses

### Changed
- **Fallback single-invocation**: `invoke_with_healing` restructured so the fallback function executes at most once when all retry attempts are exhausted (previously called twice)
- **Exception safety**: retry loop now uses bare `except Exception` to ensure `KeyboardInterrupt` and `SystemExit` are never suppressed

## v0.2.0

### Changed
- repositioned Maa Protocol around a single product definition: lightweight governance for LangGraph workflows
- restructured the package into guards, persistence, observability, and explicit exceptions
- rewrote README and core docs to remove platform/orchestrator ambiguity

### Added
- SQLite-backed approval persistence
- audit event persistence
- sync and async governance wrapper paths
- structured metrics collector
- architecture, security, roadmap, and contributing docs
- richer examples and expanded tests

### Notes
- Maa Protocol remains pre-1.0
- the goal of this release is clarity, discipline, and concept-testing implementation foundations, not inflated scope

## v0.1.0
- initial public prototype release
