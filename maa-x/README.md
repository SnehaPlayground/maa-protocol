# Maa-X

**Maa-X** is an enterprise AI orchestration platform that merges the lightweight governance of **Maa Protocol** with advanced multi-agent capabilities.

> The core stays pure Python — zero-dependency beyond Python stdlib. Every advanced capability is an optional pip extra.

---

## Philosophy

Maa-X is built on a single conviction: governance and capability are not opposites.

The core (`maa_x.core`) is a zero-dependency LangGraph governance wrapper — approval gates, cost controls, tenant isolation, canary routing, self-healing — pure Python, no vendor lock-in.

All the advanced features (swarm orchestration, vector memory, RL-based learning, MCP server, CLI, SPARC execution) are **opt-in extras** installable via pip.

---

## Quickstart

```bash
pip install maa-x                    # core only
pip install maa-x[all]               # everything
pip install maa-x[swarm,mcp,cli]     # pick what you need
```

### Minimal example (core only)

```python
from maa_x import GovernanceWrapper
from maa_x.guards import ApprovalGate, CostGuard, TenantContext
from maa_x.persistence import SQLiteBackend

class MyApp:
    def invoke(self, state, config=None):
        return {"ok": True, "state": state}

backend = SQLiteBackend()
app = GovernanceWrapper(
    app=MyApp(),
    tenant_context=TenantContext(tenant_id="tenant-a", operator_id="ops-1"),
    cost_guard=CostGuard(default_budget_usd=100.0),
    approval_gate=ApprovalGate(risk_threshold=0.8, persistence=backend),
    persistence=backend,
)

result = app.invoke({"messages": ["hello"]}, config={"user_role": "operator"})
```

---

## Package structure

```
maa_x/
├── core/            # GovernanceWrapper (zero-dep, pure Python)
├── guards/           # ApprovalGate, CostGuard, CanaryRouter, SelfHealing, TenantGate
├── persistence/      # SQLiteBackend (default), PostgresBackend (interface-compatible)
├── observability/   # MetricsCollector, TimedBlock
├── swarm/           # SwarmExecutionEngine, AgentSpec, ConsensusStrategy
├── learning/        # QLearningAgent, PolicyGradientAgent, SARSAAgent, RewardShaper, ReasoningBank, EWC
├── memory/          # AgentDB (HNSW vector store), SimpleHNSW, MemoryEntry
├── routing/         # MultiProviderRouter, ModelSpec, RoutingStrategy
├── security/        # ThreatDetector, ThreatLedger, PII redaction
├── plugins/         # PluginRegistry, PluginSpec, lifecycle management
├── workers/         # BackgroundWorker (thread pool)
├── sparc/           # SPARCEngine (Plan→Act→Sense→Reflect→Correct→Coordinate)
├── mcp/             # MCPTool registry, tool groups, preset modes
├── cli/             # maa-x command-line tool
└── compat/          # Backward-compat shim (maps maa_protocol → maa_x, drop-in replacement)
```

---

## Pip extras

| Extra | What it includes |
|---|---|
| `core` | Core only (no extras) |
| `swarm` | Swarm orchestration, consensus algorithms |
| `memory` | AgentDB vector store, HNSW index, SQLite persistence |
| `learning` | QLearningAgent, PolicyGradientAgent, SARSAAgent, RewardShaper, ReasoningBank, EWC |
| `security` | ThreatDetector, PII redaction, audit ledger |
| `plugins` | PluginRegistry, lifecycle hooks, discovery |
| `mcp` | MCP tool registry, tool groups, preset modes |
| `cli` | `maa-x` CLI (click + rich) |
| `sparc` | SPARC execution engine |
| `all` | Everything |

---

## Upgrading from Maa Protocol

Old code:
```python
from maa_protocol import GovernanceWrapper
```

New code (drop-in replacement):
```python
from maa_x.compat import GovernanceWrapper
```

No other changes required. The `maa_x.compat` module re-exports every public name from `maa_protocol` v0.2+.

---

## Core governance features

- **ApprovalGate** — risk-score-based approval with persistence backend
- **CostGuard** — hard/soft budget limits per tenant
- **CanaryRouter** — traffic splitting for safe releases
- **SelfHealing** — bounded retries with circuit breaker
- **TenantContext + AccessControl** — RBAC with role permissions
- **TenantGate** — per-tenant resource limits
- **SQLiteBackend** — audit events and approval records
- **MetricsCollector** — latency and count observability

## Swarm orchestration

Queen-led multi-agent dispatch with four consensus strategies:
- **RAFT** — leader-based
- **MAJORITY** — vote-based
- **VOTING** — weighted voting
- **BROADCAST** — fire-to-all

Three topologies: HIERARCHICAL, MESH, FANOUT.

## Self-learning

- **QLearningAgent** — tabular Q-learning with epsilon-greedy
- **PolicyGradientAgent** — REINFORCE with baseline
- **SARSAAgent** — on-policy TD control
- **RewardShaper** — potential-based reward shaping
- **ReasoningBank** — persistent reasoning pattern store (SQLite)
- **EWC** — Elastic Weight Consolidation for catastrophic forgetting prevention

## Vector memory

- **AgentDB** — SQLite-backed vector store
- **SimpleHNSW** — pure Python HNSW-inspired nearest-neighbour index
- Cosine similarity, namespace isolation, metadata storage

---

## Security

- **ThreatDetector** — scans for SQL injection, prompt injection, XSS, path traversal, cmd injection
- **PII redaction** — email, phone, Aadhar, PAN, credit card, SSN
- **ThreatLedger** — audit log for all security events

---

## CLI

```bash
maa-x swarm init --topology mesh --max-agents 5
maa-x swarm status
maa-x plugin list
maa-x plugin enable maa:security
maa-x mcp tools --group create
maa-x version
```

---

## Status

Pre-1.0. Core is stable. Advanced features are functional with pure-Python fallbacks.

---

## License

MIT