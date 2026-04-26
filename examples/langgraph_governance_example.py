from typing import TypedDict

from maa_protocol import (
    AccessControl,
    ApprovalGate,
    CanaryRouter,
    CostGuard,
    GovernanceWrapper,
    TenantContext,
)


class AgentState(TypedDict, total=False):
    messages: list[str]
    tenant_id: str
    user_role: str
    total_cost: float
    approved: bool
    governance: dict


class FakeCompiledGraph:
    """Stand-in for a compiled LangGraph app when langgraph isn't installed."""

    def invoke(self, state, config=None, **kwargs):
        return {
            "messages": ["Research completed", "Report written", "Review completed"],
            "governance": state.get("governance", {}),
            "config": config or {},
        }


if __name__ == "__main__":
    app = FakeCompiledGraph()

    governed_workflow = GovernanceWrapper(
        app=app,
        tenant_context=TenantContext(),
        cost_guard=CostGuard(default_budget=50.0, alert_threshold=0.8),
        canary_router=CanaryRouter(stable_version="v1.0", canary_version="v1.1", traffic_split=0.2),
        approval_gate=ApprovalGate(risk_threshold=0.7),
        access_control=AccessControl(),
        enable_self_healing=False,
    )

    result = governed_workflow.invoke(
        {
            "messages": ["Analyze Q3 sales trends for enterprise clients"],
            "tenant_id": "acme_enterprise",
            "user_role": "senior_analyst",
            "total_cost": 12.5,
            "approved": False,
        },
        config={
            "tenant_id": "acme_enterprise",
            "user_role": "senior_analyst",
            "max_cost": 45.0,
            "risk_flags": ["high_risk"],
            "approval_token": "APPROVED",
        },
    )

    print(result)
