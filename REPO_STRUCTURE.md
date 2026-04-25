# Repo Structure

## Public layout

- `README.md` — project overview
- `LICENSE` — MIT license
- `CHANGELOG.md` — release notes
- `ops/multi-agent-orchestrator/` — runtime, docs, tests, policies
- `ops/observability/` — observability and metrics tooling
- `scripts/` — operational support scripts
- `knowledge/maa-product/` — product packaging and deployment docs
- `templates/maa-product/` — sample configs

## Not included in the public repo

The public repo should exclude:
- private workspace control files
- memory and transcript history
- live task state and audit artifacts
- internal business automations unrelated to Maa Protocol
- private tenant data and generated operational logs
- one-off audit notes, backups, and scratch outputs

## Publishing rule

If a file exists to support internal operations rather than external users of Maa Protocol, it should stay out of the public repository.
