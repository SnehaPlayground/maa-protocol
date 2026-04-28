from maa_protocol import AccessControl, GovernanceWrapper, TenantContext


class App:
    def invoke(self, state, config=None, **kwargs):
        return {"ok": True, "state": state}


wrapper = GovernanceWrapper(
    app=App(),
    tenant_context=TenantContext(tenant_id="tenant-b", operator_id="ops-2", client_id="client-9", user_role="operator"),
    access_control=AccessControl(),
)

print(wrapper.invoke({"messages": ["hello"]}, config={"required_permission": "invoke", "user_role": "operator"}))
