# Architecture

## Design goal

Maa Protocol wraps LangGraph workflows with governance primitives. It does not replace orchestration, planning, or tool execution frameworks.

## Core layers

1. **GovernanceWrapper**
   - single integration entry point
   - sync and async execution paths
   - governance metadata injection

2. **Guards**
   - approval
   - cost
   - tenant and RBAC
   - canary routing
   - self-healing

3. **Persistence**
   - approval decision storage
   - audit event storage
   - SQLite default backend
   - Postgres-compatible interface boundary

4. **Observability**
   - counters
   - timings
   - structured event hooks

## Execution flow

1. Resolve tenant context
2. Enforce tenant limits
3. Enforce RBAC
4. Enforce cost controls
5. Select canary/stable route
6. Enforce approval requirements
7. Invoke wrapped app
8. Persist audit event
9. Record metrics

## Scope boundary

Deliberately out of scope:
- multi-agent planning frameworks
- browser control frameworks
- reinforcement learning systems
- general plugin marketplaces
- unrelated ML experimentation inside core package
