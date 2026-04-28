from maa_protocol import ApprovalGate, GovernanceWrapper, SQLiteBackend, TenantContext


class App:
    def invoke(self, state, config=None, **kwargs):
        return {"approved": True, "state": state, "config": config or {}}


backend = SQLiteBackend()
wrapper = GovernanceWrapper(
    app=App(),
    tenant_context=TenantContext(tenant_id="tenant-a", operator_id="ops-1", client_id="client-1"),
    approval_gate=ApprovalGate(risk_threshold=0.7, persistence=backend),
    persistence=backend,
)

try:
    wrapper.invoke({"action": "send_email"}, config={"risk_score": 0.9, "user_role": "operator"})
except Exception as exc:  # noqa: BLE001
    print(f"Blocked as expected: {exc}")
