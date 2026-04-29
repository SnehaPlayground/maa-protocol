"""Tests for maa_x swarm module."""

import pytest
from maa_x.swarm import (
    AgentState,
    ConsensusStrategy,
    SwarmConfig,
    SwarmExecutionEngine,
    Topology,
    run_swarm,
    create_swarm_plan,
)


def test_swarm_engine_create_plan():
    engine = SwarmExecutionEngine()
    plan = engine.create_plan("build REST API")
    assert plan.agent_count() > 0
    assert plan.coordinator_id is not None


def test_swarm_run_default():
    metrics = run_swarm("test task")
    assert metrics.swarm_id.startswith("swarm-")
    assert metrics.outcome in ("success", "partial", "failed", "timeout")
    assert metrics.duration_ms >= 0


def test_swarm_mesh_topology():
    config = SwarmConfig(topology=Topology.MESH, max_agents=4)
    engine = SwarmExecutionEngine()
    plan = engine.create_plan("mesh task", config)
    assert plan.agent_count() == 4


def test_swarm_fanout_topology():
    config = SwarmConfig(topology=Topology.FANOUT, max_agents=6)
    engine = SwarmExecutionEngine()
    plan = engine.create_plan("fanout task", config)
    assert plan.agent_count() == 6


def test_swarm_consensus_raft():
    config = SwarmConfig(consensus=ConsensusStrategy.RAFT)
    engine = SwarmExecutionEngine()
    plan = engine.create_plan("raft task", config)
    metrics = engine.run(plan)
    assert metrics.consensus_steps >= 0


def test_swarm_consensus_majority():
    config = SwarmConfig(consensus=ConsensusStrategy.MAJORITY)
    engine = SwarmExecutionEngine()
    plan = engine.create_plan("majority task", config)
    metrics = engine.run(plan)
    assert metrics.consensus_steps >= 0


def test_swarm_stats():
    engine = SwarmExecutionEngine()
    stats = engine.stats()
    assert "active_plans" in stats
    assert "completed_swarm_count" in stats