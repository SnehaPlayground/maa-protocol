# OpenClaw Runtime (optional)

This directory contains the broader OpenClaw-oriented runtime layer for Maa Protocol.

Use this path if you need:
- operator-facing runbooks
- OpenClaw-specific orchestration
- tenant/runtime management helpers
- single-node operational controls beyond the lightweight package

This runtime is **optional** and more opinionated than the core `maa_protocol/` package.

## Recommended entry points
- `RUNBOOK.md`
- `OPERATOR_RUNBOOK.md`
- `SECURITY.md`
- `RELEASE_CHECKLIST.md`
- `task_orchestrator.py`

## Notes
- The main public package remains `maa_protocol/`
- Archived lower-priority runtime policy docs were moved to `docs/archive-runtime/`
- This runtime path is still evolving and should be treated as secondary to the package-first surface
