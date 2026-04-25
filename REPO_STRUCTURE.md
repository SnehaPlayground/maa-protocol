# Repo Structure

## Public layout

- `README.md` — project overview and scope
- `INSTALL.md` — installation guide
- `QUICKSTART.md` — fast-start guide
- `FIRST_RUN.md` — first-run walkthrough
- `DEMO.md` — guided demo flow
- `LICENSE` — MIT license
- `CHANGELOG.md` — release notes
- `ops/multi-agent-orchestrator/` — Maa runtime, governance docs, and core policies
- `ops/observability/` — metrics and observability tooling
- `scripts/` — install, setup, doctor, demo, health, security, DR, and operational helpers
- `knowledge/maa-product/` — deployment and packaging support files
- `templates/maa-product/` — sample deployment profiles

## Intended repo boundary

The public repo should contain:
- Maa core runtime
- public deployment documentation
- public sample profiles
- generic operational tooling
- public tests and validation helpers

## Not included in the public repo

The public repo should exclude:
- private workspace control files
- memory and transcript history
- live task state and audit artifacts
- generated outputs and local runtime debris
- one-off backups, scratch files, and local experiments
- operator-specific business workflows mixed into Maa core

## Publishing rule

If a file exists to support a private operator workflow rather than external Maa users, it should be excluded from core, moved to examples, or kept private.