# Maa Protocol

Maa Protocol is a self-hosted, operator-first, single-node multi-agent orchestration framework with built-in governance controls such as approval gates, tenant isolation, RBAC, idempotency, canary routing, circuit breakers, cost controls, and self-healing.

## What Maa is

Maa is:
- a self-hosted orchestration layer for agentic work
- designed for operator oversight and runtime governance
- suitable for laptop, workstation, and small VPS deployments
- built around validation, approval, durability, and recovery controls

## What Maa is not

Maa is not:
- a managed SaaS
- a distributed scheduler or cluster runtime
- a Kubernetes-native orchestration platform
- a no-dependency framework

## Dependency: OpenClaw

Maa depends on OpenClaw for:
- agent session runtime
- session and channel orchestration
- message routing

Without OpenClaw, Maa cannot run fully.

## Quick start

1. Clone the repository
2. Install and verify OpenClaw
3. Copy a deployment profile from `templates/maa-product/`
4. Run `bash scripts/pre_deploy_gate.sh`
5. Submit a test task through `task_orchestrator.py`

Detailed guides:
- `INSTALL.md`
- `QUICKSTART.md`
- `FIRST_RUN.md`
- `DEMO.md`
- `WHAT_MAA_IS_NOT.md`
- `USE_CASES.md`
- `COMPARISONS.md`
- `ops/multi-agent-orchestrator/COMMUNITY_RUNBOOK.md`

Helper scripts:
- `python3 scripts/maa_setup.py`
- `python3 scripts/maa_doctor.py`
- `python3 scripts/maa_demo.py`

## What this repo contains

Core product surfaces:
- `ops/multi-agent-orchestrator/` — orchestration runtime, policies, tests, and operator docs
- `ops/observability/` — metrics store and observability tooling
- `scripts/` — health checks, DR, cleanup, security, and deployment helpers
- `knowledge/maa-product/` — runtime packaging and deployment docs
- `templates/maa-product/` — sample deployment profiles

## Repo scope

This public repository is intended to contain the Maa Protocol core and public-facing documentation.

It should not contain:
- private workspace control files
- historical task state or runtime debris
- personal business workflows mixed into Maa core
- private memory, transcripts, or operator-specific secrets

Operator-specific or domain-specific implementations should live under `examples/` or in private repositories, not inside Maa core paths.

## License

MIT
