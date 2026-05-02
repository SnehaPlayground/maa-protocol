# Roadmap

## v0.2.0
- package restructure around governance primitives
- SQLite-backed approvals and audit events
- improved docs and examples
- stronger tests and CI baseline

## v0.3.0
- **COMPLETED** deeper LangGraph integration patterns
- **COMPLETED** SQLite error wrapping and tenant isolation hardening
- **COMPLETED** CostGuard NaN/Infinity rejection, comprehensive validation
- **COMPLETED** PostgresBackend placeholder with NotImplementedError
- **COMPLETED** pytest-cov and bandit added to CI and dev dependencies
- **COMPLETED** Responsible Disclosure section in SECURITY.md
- **COMPLETED** 50-test suite (28 security + 22 functional) covering all critical paths
- **IN PROGRESS** benchmark publication
- **IN PROGRESS** OpenTelemetry adapter improvements

## v0.4.0
- tenant-isolated persistence with real PostgresBackend (psycopg2/sqlalchemy)
- robust multi-tenant error handling and concurrency testing
- comprehensive test suite completion (>80% coverage target)
- migration helpers for existing LangGraph apps
- richer audit query surface
- approval lifecycle tooling

## Non-goals
- replacing LangGraph
- becoming a general multi-agent platform
- bundling unrelated experimental ML systems into the core package
