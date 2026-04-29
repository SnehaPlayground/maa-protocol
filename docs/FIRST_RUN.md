# First Run Guide

This guide is for a new developer trying Maa Protocol for the first time.

## Step 1: install the package

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

## Step 2: verify the package imports

```bash
python -c "import maa_protocol; print('ok')"
```

## Step 3: run tests

```bash
pytest -q
```

## Step 4: run a minimal governed app

Use the example from `README.md` to confirm:
- `GovernanceWrapper` wraps your app
- `TenantContext` resolves
- `ApprovalGate` and `CostGuard` load cleanly
- `SQLiteBackend` persists approvals and audits locally

## Step 5: inspect the repo shape

Key areas:
- `maa_protocol/governance.py`
- `maa_protocol/guards/`
- `maa_protocol/persistence/`
- `maa_protocol/observability/`

## Common first-run blockers

### Virtualenv not active
Activate `.venv` before running tests or examples.

### Dev dependencies missing
Re-run:

```bash
pip install -e .[dev]
```

### Scope confusion
Maa Protocol is the focused governance package.
`maa-x/` is included as a sibling experimental package, not the core public API.
