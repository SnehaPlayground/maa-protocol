# Changelog

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
