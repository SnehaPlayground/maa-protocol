"""Tests for maa_x.compat module — backward-compat shim."""

import pytest
from maa_x.compat import (
    GovernanceWrapper,
    ApprovalGate,
    CostGuard,
    TenantContext,
    SQLiteBackend,
    QLearningAgent,
    SwarmExecutionEngine,
    MCPTool,
    list_plugins,
    mcp_capabilities,
)


def test_governance_wrapper_from_compat():
    """Verify compat re-exports work as drop-in replacement."""
    backend = SQLiteBackend()
    wrapper = GovernanceWrapper(app=lambda s, **kw: s)
    result = wrapper.invoke({"test": "compat"}, config={"user_role": "operator"})
    assert result["test"] == "compat"


def test_approval_gate_from_compat():
    gate = ApprovalGate(risk_threshold=0.5)
    result = gate.assess({}, {"risk_score": 0.3})
    assert not result["needs_approval"]


def test_q_agent_from_compat():
    agent = QLearningAgent(actions=["x", "y", "z"])
    assert len(agent.actions) == 3
    action = agent.select_action("state_x")
    assert action in ["x", "y", "z"]


def test_swarm_from_compat():
    engine = SwarmExecutionEngine()
    plan = engine.create_plan("compat swarm test")
    assert plan.agent_count() > 0


def test_mcp_capabilities_from_compat():
    caps = mcp_capabilities()
    assert caps["tool_count"] > 0