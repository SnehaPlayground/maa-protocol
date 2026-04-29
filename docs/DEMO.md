# Maa Demo

## Minimal package demo

Run this from the repo root after `pip install -e .[dev]`:

```bash
python - <<'PY'
from maa_protocol import GovernanceWrapper, ApprovalGate, CostGuard, SQLiteBackend, TenantContext

class DemoApp:
    def invoke(self, state, config=None, **kwargs):
        return {"ok": True, "state": state, "config": config or {}}

backend = SQLiteBackend()
app = GovernanceWrapper(
    app=DemoApp(),
    tenant_context=TenantContext(tenant_id="demo-tenant", operator_id="demo-operator", client_id="demo-client"),
    cost_guard=CostGuard(default_budget_usd=50.0),
    approval_gate=ApprovalGate(risk_threshold=0.8, persistence=backend),
    persistence=backend,
)

print(app.invoke({"messages": ["demo"]}, config={"user_role": "operator", "approval_id": "demo-approval"}))
PY
```

## Expected outcome

A healthy demo should:
- import `maa_protocol` cleanly
- execute through `GovernanceWrapper`
- return a result dict
- create local persistence artifacts without path errors
