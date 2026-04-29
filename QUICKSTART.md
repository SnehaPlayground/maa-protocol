# Maa Protocol Quickstart

Fastest path to a working local install.

## 1. Clone and enter the repo

```bash
git clone https://github.com/SnehaPlayground/maa-protocol.git
cd maa-protocol
```

## 2. Create a venv and install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

## 3. Run the test suite

```bash
pytest -q
```

## 4. Try the core wrapper

```python
from maa_protocol import GovernanceWrapper, SQLiteBackend, TenantContext, CostGuard, ApprovalGate
```

For a full runnable example, copy the one in `README.md`.

## What success looks like

You should have:
- editable install working
- tests passing
- importable `maa_protocol` package
- a clear scope boundary: governance for LangGraph workflows

## If you only read one thing

Read `INSTALL.md` for the clean setup path.
