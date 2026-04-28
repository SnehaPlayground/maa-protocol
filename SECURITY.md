# Security

## Principles

- Fail closed for high-risk governed actions
- Validate inputs at guard boundaries
- Persist approval and audit state for traceability
- Keep secret handling outside repository defaults
- Treat prompt injection as an application-layer risk that governance can reduce, not eliminate

## Current controls

- approval gate for risky actions
- tenant-aware RBAC checks
- hard and soft cost limits
- audit event persistence
- bounded retry and circuit-breaker behavior

## Known limitations

- SQLite is suitable for local and small deployment testing, not all shared or multi-node cases
- Prompt-injection detection is not solved by this package alone
- Approval UX is backend-capability dependent

## Recommended deployment posture

- Use Postgres-backed persistence for shared environments
- Feed metrics into your existing observability stack
- Pair governance with application-specific allowlists and output validation
- Keep credentials in environment variables or dedicated secret stores
