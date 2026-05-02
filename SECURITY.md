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
- NaN/Infinity rejection in CostGuard to prevent arithmetic edge cases

## Known limitations

- SQLite is suitable for local and small deployment testing, not all shared or multi-node cases
- Prompt-injection detection is not solved by this package alone
- Approval UX is backend-capability dependent
- **This package has not undergone a third-party external security audit.** Treat accordingly for high-stakes deployments.

## Recommended deployment posture

- Use Postgres-backed persistence for shared environments (not yet implemented — see ROADMAP.md)
- Feed metrics into your existing observability stack
- Pair governance with application-specific allowlists and output validation
- Keep credentials in environment variables or dedicated secret stores

## Responsible Disclosure

If you discover a security vulnerability in maa-protocol, please report it via:
**[GitHub Security Advisories](https://github.com/SnehaPlayground/maa-protocol/security/advisories)**

Do not open public issues for security vulnerabilities. Please allow reasonable time for a fix before disclosure.
