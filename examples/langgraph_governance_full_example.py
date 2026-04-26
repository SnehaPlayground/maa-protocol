from typing import TypedDict, Annotated

try:
    from langgraph.graph import StateGraph, END
except Exception as exc:  # pragma: no cover
    raise SystemExit(
        "This example requires langgraph. Install it with: pip install langgraph"
    ) from exc

from maa_protocol import (
    TenantContext,
    CostGuard,
    CanaryRouter,
    ApprovalGate,
    AccessControl,
    GovernanceWrapper,
    TenantGate,
    SelfHealing,
    SelfHealingConfig,
)


# 1. Define your state (same as normal LangGraph)
class AgentState(TypedDict):
    messages: Annotated[list, "add_messages"]
    tenant_id: str
    user_role: str
    total_cost: float
    approved: bool


# 2. Your normal LangGraph nodes (unchanged)
def research_node(state: AgentState):
    existing = list(state.get("messages", []))
    return {
        "messages": existing + ["Research completed"],
        "tenant_id": state.get("tenant_id", "default"),
        "user_role": state.get("user_role", "analyst"),
        "total_cost": float(state.get("total_cost", 0.0)) + 12.5,
        "approved": state.get("approved", False),
    }


def write_node(state: AgentState):
    existing = list(state.get("messages", []))
    return {
        "messages": existing + ["Report written"],
        "tenant_id": state.get("tenant_id", "default"),
        "user_role": state.get("user_role", "analyst"),
        "total_cost": float(state.get("total_cost", 0.0)) + 8.0,
        "approved": state.get("approved", False),
    }


def review_node(state: AgentState):
    existing = list(state.get("messages", []))
    return {
        "messages": existing + ["Review completed"],
        "tenant_id": state.get("tenant_id", "default"),
        "user_role": state.get("user_role", "analyst"),
        "total_cost": float(state.get("total_cost", 0.0)) + 4.0,
        "approved": state.get("approved", False),
    }


# 3. Build normal LangGraph workflow
workflow = StateGraph(AgentState)
workflow.add_node("research", research_node)
workflow.add_node("write", write_node)
workflow.add_node("review", review_node)

workflow.set_entry_point("research")
workflow.add_edge("research", "write")
workflow.add_edge("write", "review")
workflow.add_edge("review", END)

langgraph_app = workflow.compile()


# 4. Create all governance components
tenant_ctx = TenantContext(tenant_id="acme_enterprise", operator_id="acme", client_id="enterprise")
cost_guard = CostGuard(
    default_budget=50.0,
    alert_threshold=0.8,
)
canary = CanaryRouter(stable_version="v1.0", canary_version="v1.1")
approval = ApprovalGate(risk_threshold=0.7, require_approval_for={"high_risk", "external_api_call"})
rbac = AccessControl()
tenant_gate = TenantGate(max_cost_per_invoke=30.0, max_concurrent_tasks=10)
self_healing = SelfHealing(config=SelfHealingConfig(max_attempts=3, initial_interval=1.0))


# 5. Wrap LangGraph with full maa-protocol governance
governed_workflow = GovernanceWrapper(
    app=langgraph_app,
    tenant_context=tenant_ctx,
    cost_guard=cost_guard,
    canary_router=canary,
    approval_gate=approval,
    access_control=rbac,
    tenant_gate=tenant_gate,
    self_healing=self_healing,
    enable_self_healing=True,
)


# 6. Run with full governance (approved via token — see approval_gate CLI)
result = governed_workflow.invoke(
    {
        "messages": ["Analyze Q3 sales trends for enterprise clients"],
        "tenant_id": "acme_enterprise",
        "user_role": "senior_analyst",
        "total_cost": 0.0,
        "approved": False,  # still false — token in config is what matters
    },
    config={
        "tenant_id": "acme_enterprise",
        "user_role": "senior_analyst",
        "max_cost": 45.0,
        "approval_token": "APPROVE_TO_SEND",  # real token from Partha's approval
        "risk_flags": ["external_api_call"],
    },
)

print("Result governance:", result.get("governance", {}))


# ── 8. Advanced Usage ───────────────────────────────────────────────────────────

# Per-Tenant Budget Enforcement
advanced_cost_guard = CostGuard(
    tenant_budgets={
        "acme_enterprise": 200.0,
        "startup_xyz": 30.0,
    }
)

# Canary Deployment (20% traffic to canary)
advanced_canary = CanaryRouter(
    stable_version="v1.0",
    canary_version="v1.1",
    traffic_split=0.2,
)

# Human-in-the-Loop Approval with custom flags
advanced_approval = ApprovalGate(
    require_approval_for={"high_risk", "external_api_call"},
    approval_timeout=300,
    risk_threshold=0.7,
)

# TenantGate isolation
advanced_tenant_gate = TenantGate(
    max_concurrent_tasks=5,
    max_cost_per_invoke=20.0,
    block_on_isolation_violation=True,
)

print("All advanced components configured.")
