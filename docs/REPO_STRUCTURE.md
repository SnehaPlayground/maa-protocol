# Repo Structure

## Public layout

Core public docs:
- `README.md` — project overview and scope
- `INSTALL.md` — installation guide
- `QUICKSTART.md` — fast-start guide
- `ARCHITECTURE.md` — design summary
- `SECURITY.md` — security posture
- `ROADMAP.md` — planned direction
- `CHANGELOG.md` — release notes
- `CONTRIBUTING.md` — contributor workflow
- `docs/FIRST_RUN.md` — first-run walkthrough
- `docs/DEMO.md` — runnable demo
- `docs/WHAT_MAA_IS_NOT.md` — scope boundary
- `docs/USE_CASES.md` — best-fit usage guidance
- `docs/COMPARISONS.md` — positioning

Core package:
- `maa_protocol/` — focused governance package
  - `governance.py`
  - `guards/`
  - `persistence/`
  - `observability/`
  - `exceptions.py`

Tests and examples:
- `tests/` — package validation
- `examples/` — small usage examples

Related sibling package in this repo:
- `maa-x/` — broader experimental package that extends Maa Protocol while preserving a compatibility shim

## Intended repo boundary

The public repo should contain:
- Maa Protocol core runtime
- honest public documentation
- public examples and tests
- clearly separated experimental work

## Not included in the public core package

The public core package should not depend on:
- private operator memory
- local transcripts and generated artifacts
- one-off business workflows
- unrelated orchestration systems mixed into `maa_protocol/`

## Publishing rule

If something is experimental or broader than the Maa Protocol scope, keep it clearly separated, for example under `maa-x/`, rather than blurring the core package boundary.
