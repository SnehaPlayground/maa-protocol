# Changelog

All notable changes to Maa Protocol are documented here.

Maa Protocol follows pre-1.0 semantic versioning for public releases.

---

## v0.1.0 — Public package-first cleanup

**Released:** 2026-04-26
**Status:** Initial pre-1.0 public release

### Highlights

- Repositioned Maa Protocol as a lightweight governance layer rather than a production-grade orchestrator
- Made the `maa_protocol/` package the primary public entry point
- Moved supporting reference material into `docs/`
- Moved the broader OpenClaw-specific runtime into `runtime/openclaw-runtime/`
- Tightened README messaging around scope, audience, and maturity
- Downgraded versioning to pre-1.0 to better reflect current maturity

### Current scope

- Lightweight governance wrapper for LangGraph-style workflows
- Optional OpenClaw runtime path for operator-heavy single-node deployments
- Early-stage prototype with production-oriented controls, not yet a production platform

---

## Historical note

Earlier internal/runtime release notes were removed from the public changelog because they overstated current public maturity and mixed internal operational milestones with the package-facing release story.
