from maa_protocol import CostGuard, GovernanceWrapper, TenantContext


class App:
    def invoke(self, state, config=None, **kwargs):
        return {"ok": True, "state": state}


wrapper = GovernanceWrapper(
    app=App(),
    tenant_context=TenantContext(tenant_id="tenant-a", operator_id="ops-1", client_id="client-1", budget_usd=10.0),
    cost_guard=CostGuard(default_budget_usd=10.0, hard_limit_usd=10.0),
)

print(wrapper.invoke({"messages": ["hello"]}, config={"cost_usd": 2.5, "user_role": "analyst"}))
