# Install Maa Protocol

Maa Protocol is a lightweight governance layer for LangGraph workflows.

## Requirements

- Python 3.10+
- Git
- Linux or macOS recommended

OpenClaw is **not required** for the focused governance package in this repo.

## 1. Clone the repository

```bash
git clone https://github.com/SnehaPlayground/maa-protocol.git
cd maa-protocol
```

## 2. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

## 3. Install Maa Protocol

```bash
pip install -e .[dev]
```

## 4. Run checks

```bash
ruff check .
mypy maa_protocol
pytest
```

## 5. Run a minimal example

```bash
python - <<'PY'
from maa_protocol import GovernanceWrapper, ApprovalGate, CostGuard, TenantContext, SQLiteBackend

class DemoApp:
    def invoke(self, state, config=None, **kwargs):
        return {"ok": True, "state": state}

backend = SQLiteBackend()
app = GovernanceWrapper(
    app=DemoApp(),
    tenant_context=TenantContext(tenant_id="tenant-a", operator_id="ops-1", client_id="client-1"),
    cost_guard=CostGuard(default_budget_usd=100.0),
    approval_gate=ApprovalGate(risk_threshold=0.8, persistence=backend),
    persistence=backend,
)
print(app.invoke({"messages": ["hello"]}, config={"user_role": "operator", "approval_id": "pre-approved-id"}))
PY
```

## Optional: review Maa-X

This repository also contains `maa-x/`, an experimental sibling package that extends Maa Protocol with broader orchestration capabilities while keeping a compatibility shim.

## If something fails

Check these first:

```bash
python3 --version
pip --version
pytest -q
```

Then review:
- `README.md`
- `ARCHITECTURE.md`
- `SECURITY.md`
- `CONTRIBUTING.md`
