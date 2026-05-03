# Changelog

## v0.3.1 (May 3 2026)

Cross-reference: follows the May 2 2026 root-cleanup chore commit reviewed in the audit update.

### Changed
- locked `maa_protocol` back to the governance-only product definition
- bumped package metadata from `0.3.0` to `0.3.1`
- replaced explicit package lists with package discovery plus install exclusions for non-governance subpackages and tests

### Fixed
- removed broken `maa_x.*` imports from the installable `maa-x` CLI
- stabilized `maa-x version`, `maa-x governance audit`, and `maa-x swarm init`
- replaced silent tenant fallbacks with validated tenant resolution and explicit errors
- hardened approval, cost, self-healing, and persistence flows with validated inputs and clearer failure paths
- moved smoke-test concerns out of the package surface and stopped shipping them in the governance distribution

### Added
- Pydantic validation for `TenantContext`, `ApprovalRequest`, `CostGuardConfig`, and runtime config handling
- expanded governance, persistence, and CLI tests with enforced 80% coverage

## v0.3.0 (May 2 2026)

### Fixed
- Governance audit timing: `_audit` call moved inside `TimedBlock` in `ainvoke`, matching `invoke` so audit latency is measured consistently
- Governance timing consistency: `_prepare` called inside `TimedBlock` in `ainvoke`; preparation time now included in governance metrics
- Tenant ID string safety: `_audit` tenant extraction rewritten to avoid producing the literal string `"None"` when governance data is absent; falls back cleanly to `"default"`
- ApprovalPersistenceError wired: `ApprovalGate.create_request` now raises `ApprovalPersistenceError` (not `ApprovalRequiredError`) when the persistence backend is absent; exception exported from top-level `__init__.py`
- Approval requested_by safety: `assess` method replaced the deep nested `.get` chain with explicit `isinstance` guards; no `AttributeError` possible on malformed state
- Persistence cleanup: `SQLiteBackend` now implements `close()`, `__enter__`, and `__exit__` for proper connection lifecycle management via context manager; `PostgresBackend` raises `NotImplementedError` on all methods instead of silently inheriting from SQLite

### Added
- Guard range validation for canary, approval, cost, and self-healing configuration
- SelfHealing thread safety with `threading.RLock`
- Async self-healing variant
- ApprovalPersistenceError test coverage
- GovernanceWrapper hasattr guard for approval persistence injection

## v0.2.0

### Changed
- repositioned Maa Protocol around a single product definition: lightweight governance for LangGraph workflows
- restructured the package into guards, persistence, observability, and explicit exceptions
- rewrote README and core docs to remove platform/orchestrator ambiguity

## v0.1.0
- initial public prototype release
