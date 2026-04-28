from maa_protocol import CanaryRouter, GovernanceWrapper, TenantContext


class App:
    def invoke(self, state, config=None, **kwargs):
        return {"ok": True, "selected": state.get("agent_version")}


wrapper = GovernanceWrapper(
    app=App(),
    tenant_context=TenantContext(tenant_id="tenant-c", operator_id="ops-3", client_id="client-2"),
    canary_router=CanaryRouter(stable_version="v1", canary_version="v2", traffic_split=0.5),
)

print(wrapper.invoke({"messages": ["hello"]}, config={"routing_key": "tenant-c", "user_role": "analyst"}))
