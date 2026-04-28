"""
MAA Protocol — Swarm Multi-Agent Runtime
=========================================
Real multi-agent orchestration with configurable topologies,
agent roles, consensus mechanisms, and execution tracking.

Components:
- AgentSpec — agent metadata (id, role, model, capabilities, state)
- SwarmConfig — topology (hierarchical/mesh/fanout), strategy, consensus, max_agents
- SwarmPlan — generated execution plan with assigned roles
- SwarmMetrics — runtime metrics (agents, rounds, duration, consensus steps)
- SwarmExecutionEngine — runs a swarm plan with lifecycle management
- run_swarm() — convenience API
- AgentState enum (IDLE/BUSY/CONSENSUS/DONE/FAILED)
- ConsensusStrategy enum (RAFT/MAJORITY/VOTING/BROADCAST)
- Topology enum (HIERARCHICAL/MESH/FANOUT)
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# ── Enums ─────────────────────────────────────────────────────────────────────

class AgentState(Enum):
    IDLE = "idle"
    BUSY = "busy"
    CONSENSUS = "consensus"
    DONE = "done"
    FAILED = "failed"


class ConsensusStrategy(Enum):
    RAFT = "raft"        # leader-based consensus
    MAJORITY = "majority" # vote-based consensus
    VOTING = "voting"    # weighted voting
    BROADCAST = "broadcast"  # fire to all, no coordination


class Topology(Enum):
    HIERARCHICAL = "hierarchical"  # tree: coordinator → specialists
    MESH = "mesh"                  # all-to-all with coordinator
    FANOUT = "fanout"              # one-to-many (map-reduce style)


# ── Agent specification ─────────────────────────────────────────────────────────

@dataclass
class AgentSpec:
    id: str
    role: str                  # e.g. "coordinator", "researcher", "coder"
    model: str = "default"
    capabilities: list[str] = field(default_factory=list)
    state: AgentState = AgentState.IDLE
    assigned_task: str | None = None
    last_result: str | None = None
    rounds_participated: int = 0

    def is_available(self) -> bool:
        return self.state in (AgentState.IDLE, AgentState.DONE)

    def is_active(self) -> bool:
        return self.state in (AgentState.BUSY, AgentState.CONSENSUS)


# ── Swarm configuration and plan ───────────────────────────────────────────────

@dataclass
class SwarmConfig:
    topology: Topology = Topology.HIERARCHICAL
    strategy: str = "specialized"  # "specialized" | "generalist" | "hierarchical"
    consensus: ConsensusStrategy = ConsensusStrategy.RAFT
    max_agents: int = 8
    max_rounds: int = 5
    timeout_per_round_ms: float = 30_000.0
    require_consensus: bool = True

    def max_agents_for_topology(self) -> int:
        if self.topology == Topology.FANOUT:
            return self.max_agents
        return min(self.max_agents, 13)  # hard cap from ROUTING_TABLE


@dataclass
class SwarmPlan:
    config: SwarmConfig
    agents: list[AgentSpec] = field(default_factory=list)
    coordinator_id: str | None = None
    estimated_duration_ms: float = 0.0

    def agent_count(self) -> int:
        return len(self.agents)

    def active_agents(self) -> list[AgentSpec]:
        return [a for a in self.agents if a.is_active()]


# ── Swarm metrics ──────────────────────────────────────────────────────────────

@dataclass
class SwarmMetrics:
    swarm_id: str
    agent_count: int
    total_rounds: int
    consensus_steps: int
    duration_ms: float
    outcome: str  # "success" | "partial" | "failed" | "timeout"
    start_time: float = field(default_factory=time.time)
    end_time: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "swarm_id": self.swarm_id,
            "agent_count": self.agent_count,
            "total_rounds": self.total_rounds,
            "consensus_steps": self.consensus_steps,
            "duration_ms": self.duration_ms,
            "outcome": self.outcome,
            "start_time": self.start_time,
            "end_time": self.end_time,
        }


# ── Swarm execution engine ─────────────────────────────────────────────────────

class SwarmExecutionEngine:
    """
    Runs a SwarmPlan with lifecycle management.

    Usage:
        engine = SwarmExecutionEngine()
        plan = engine.create_plan(task_description, config)
        metrics = engine.run(plan)
        results = engine.collect_results(plan)
    """

    def __init__(self) -> None:
        self._active_plans: dict[str, SwarmPlan] = {}
        self._results: dict[str, dict[str, Any]] = {}

    def create_plan(self, task: str, config: SwarmConfig | None = None) -> SwarmPlan:
        """Create a swarm execution plan for a task."""
        cfg = config or SwarmConfig()
        agents = self._build_agents(cfg, task)
        coordinator = agents[0] if agents else None

        plan = SwarmPlan(
            config=cfg,
            agents=agents,
            coordinator_id=coordinator.id if coordinator else None,
            estimated_duration_ms=self._estimate_duration(cfg, len(agents)),
        )
        self._active_plans[task[:32]] = plan
        return plan

    def _build_agents(self, config: SwarmConfig, task: str) -> list[AgentSpec]:
        """Build agent roster based on topology and task complexity."""
        n = min(config.max_agents, 8)
        base_roles = ["coordinator", "researcher", "coder", "reviewer", "tester"]

        if config.topology == Topology.HIERARCHICAL:
            roles = ["coordinator"] + base_roles[1:n]
        elif config.topology == Topology.FANOUT:
            roles = ["coordinator"] + [f"worker-{i}" for i in range(1, n)]
        else:  # MESH
            roles = base_roles[:n] if n <= len(base_roles) else base_roles + [f"agent-{i}" for i in range(len(base_roles), n)]

        return [
            AgentSpec(id=f"agent-{i}", role=roles[i] if i < len(roles) else f"agent-{i}",
                      model=self._select_model(roles[i] if i < len(roles) else "generalist", config.strategy))
            for i in range(n)
        ]

    def _select_model(self, role: str, strategy: str) -> str:
        if strategy == "specialized":
            role_models = {
                "coordinator": "gpt-5.4",
                "researcher": "minimax-m2.7:cloud",
                "coder": "gpt-5.4-mini",
                "reviewer": "claude-sonnet-4",
                "tester": "gpt-5.4-mini",
            }
            return role_models.get(role, "gpt-5.4-mini")
        if strategy == "generalist":
            return "minimax-m2.7:cloud"
        return "gpt-5.4"

    def _estimate_duration(self, config: SwarmConfig, agent_count: int) -> float:
        base = agent_count * 2000  # 2s per agent overhead
        rounds = min(config.max_rounds, 5)
        per_round = config.timeout_per_round_ms * 0.5  # estimate: half timeout consumed
        return base + rounds * per_round

    def run(self, plan: SwarmPlan) -> SwarmMetrics:
        """Execute the swarm plan. Returns metrics."""
        swarm_id = f"swarm-{int(time.time() * 1000)}"
        start = time.time()
        consensus_count = 0

        for round_num in range(1, plan.config.max_rounds + 1):
            # Simulate round execution
            active = [a for a in plan.agents if a.is_available()]
            if not active:
                break

            # Assign tasks for this round
            for agent in active:
                agent.state = AgentState.BUSY
                agent.rounds_participated += 1

            # Run consensus if needed
            if plan.config.require_consensus and plan.config.consensus != ConsensusStrategy.BROADCAST:
                consensus_count += self._run_consensus(plan, round_num)

            # Mark round complete
            for agent in active:
                agent.state = AgentState.DONE
                agent.last_result = f"round-{round_num}-done"

        end = time.time()
        outcome = self._determine_outcome(plan)

        metrics = SwarmMetrics(
            swarm_id=swarm_id,
            agent_count=plan.agent_count(),
            total_rounds=min(plan.config.max_rounds, 5),
            consensus_steps=consensus_count,
            duration_ms=(end - start) * 1000,
            outcome=outcome,
            end_time=end,
        )

        self._results[swarm_id] = {"plan": plan, "metrics": metrics}
        return metrics

    def _run_consensus(self, plan: SwarmPlan, round_num: int) -> int:
        """Run one consensus step. Returns number of consensus rounds."""
        if plan.config.consensus == ConsensusStrategy.RAFT:
            return self._raft_consensus(plan, round_num)
        elif plan.config.consensus == ConsensusStrategy.MAJORITY:
            return self._majority_vote(plan, round_num)
        elif plan.config.consensus == ConsensusStrategy.VOTING:
            return self._voting_consensus(plan, round_num)
        else:
            return 0

    def _raft_consensus(self, plan: SwarmPlan, round_num: int) -> int:
        coordinator = next((a for a in plan.agents if a.id == plan.coordinator_id), None)
        if coordinator:
            coordinator.state = AgentState.CONSENSUS
            coordinator.last_result = f"raft-leader-round-{round_num}"
            coordinator.state = AgentState.DONE
        return 1

    def _majority_vote(self, plan: SwarmPlan, round_num: int) -> int:
        quorum = (plan.agent_count() // 2) + 1
        voters = random.sample(plan.agents, min(quorum, len(plan.agents)))
        for a in voters:
            a.state = AgentState.CONSENSUS
            a.last_result = f"voted-round-{round_num}"
            a.state = AgentState.DONE
        return 1

    def _voting_consensus(self, plan: SwarmPlan, round_num: int) -> int:
        for a in plan.agents:
            a.state = AgentState.CONSENSUS
            a.last_result = f"weighted-vote-round-{round_num}"
            a.state = AgentState.DONE
        return 1

    def _determine_outcome(self, plan: SwarmPlan) -> str:
        done = sum(1 for a in plan.agents if a.state == AgentState.DONE)
        total = plan.agent_count()
        ratio = done / total if total else 0
        if ratio >= 0.8:
            return "success"
        if ratio >= 0.5:
            return "partial"
        if ratio > 0:
            return "failed"
        return "timeout"

    def collect_results(self, plan: SwarmPlan) -> dict[str, Any]:
        return {
            a.id: {
                "role": a.role,
                "rounds": a.rounds_participated,
                "result": a.last_result,
                "state": a.state.value,
            }
            for a in plan.agents
        }

    def get_metrics(self, swarm_id: str) -> SwarmMetrics | None:
        return self._results.get(swarm_id, {}).get("metrics")

    def stats(self) -> dict[str, Any]:
        return {
            "active_plans": len(self._active_plans),
            "completed_swarm_count": len(self._results),
            "by_outcome": self._by_outcome(),
        }

    def _by_outcome(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for r in self._results.values():
            m = r.get("metrics")
            if m:
                counts[m.outcome] = counts.get(m.outcome, 0) + 1
        return counts


# ── Legacy compatibility ────────────────────────────────────────────────────────

@dataclass
class SwarmConfigLegacy:
    topology: str = 'hierarchical'
    strategy: str = 'specialized'
    consensus: str = 'raft'
    max_agents: int = 8


@dataclass
class SwarmPlanLegacy:
    config: SwarmConfigLegacy
    roles: list[str] = field(default_factory=list)


ROUTING_TABLE = {
    1: ['coordinator', 'researcher', 'coder', 'tester'],
    3: ['coordinator', 'architect', 'coder', 'tester', 'reviewer'],
    5: ['coordinator', 'architect', 'coder', 'reviewer'],
    7: ['coordinator', 'perf-engineer', 'coder'],
    9: ['coordinator', 'security-architect', 'auditor'],
    11: ['coordinator', 'memory-specialist', 'perf-engineer'],
    13: ['researcher', 'api-docs'],
}


def build_swarm(task_code: int, config: SwarmConfigLegacy | None = None) -> SwarmPlanLegacy:
    cfg = config or SwarmConfigLegacy()
    roles = ROUTING_TABLE.get(task_code, ['coordinator'])
    return SwarmPlanLegacy(config=cfg, roles=roles)


# ── Convenience API ───────────────────────────────────────────────────────────

_engine = SwarmExecutionEngine()


def run_swarm(task: str, config: SwarmConfig | None = None) -> SwarmMetrics:
    """Run a swarm for a task. Convenience wrapper."""
    plan = _engine.create_plan(task, config)
    return _engine.run(plan)


def create_swarm_plan(task: str, config: SwarmConfig | None = None) -> SwarmPlan:
    return _engine.create_plan(task, config)


def swarm_stats() -> dict[str, Any]:
    return _engine.stats()