# Maa Protocol

**Maa Protocol adds operator controls to agent workflows — without replacing your runtime.**

A self-hosted governance layer for LangGraph and OpenClaw-backed agentic systems. Built for single-node laptop, workstation, and small VPS deployments.

---

## Who this is for

**Maa Protocol is for you if you:**
- are running LangGraph or OpenClaw-based multi-agent workflows
- need approval gates, cost controls, tenant isolation, or canary routing without rebuilding your runtime
- want self-healing, idempotency, and observability as first-class primitives
- are building on a laptop or small VPS and cannot or do not want to adopt Kubernetes

**Maa Protocol is NOT for you if you:**
- need a distributed cluster scheduler or managed SaaS
- want a drop-in replacement for LangGraph, CrewAI, or AutoGen
- are looking for a battle-tested, community-backed production library today
- need Kubernetes-native orchestration

---

## Core Features

| Feature | What it does |
|---|---|
| **Approval Gate** | Blocks high-risk actions until explicitly authorized |
| **Tenant Isolation** | RBAC and data isolation across multiple tenants or users |
| **Cost Guard** | Tracks and limits spend per tenant or operation |
| **Canary Router** | Safely route a percentage of traffic to a new version |
| **Circuit Breaker** | Stops cascading failures before they propagate |
| **Idempotency** | Prevents duplicate task execution |
| **Self-Healing** | Automatic recovery and retry with validation |
| **Observability** | Structured logging, metrics, and progress tracking |

---

## Quick Start

### Try the package (fastest path)

```bash
pip install -e .[test]
pytest tests/test_maa_protocol.py
```

LangGraph full example:

```bash
pip install -e .[langgraph]
python3 examples/langgraph_governance_full_example.py
```

### Explore the OpenClaw runtime

```bash
pip install openclaw
python3 scripts/maa_setup.py
python3 scripts/maa_doctor.py
python3 scripts/maa_demo.py
```

See [INSTALL.md](docs/INSTALL.md) and [QUICKSTART.md](docs/QUICKSTART.md) for full setup instructions.

---

## Example: Governance Wrapper

```python
from langgraph.graph import StateGraph, END
from maa_protocol import (
    TenantContext, CostGuard, CanaryRouter, ApprovalGate, GovernanceWrapper
)

class AgentState(dict):
    pass

workflow = StateGraph(AgentState)
app = workflow.compile()

governed_app = GovernanceWrapper(
    app=app,
    tenant_context=TenantContext(),
    cost_guard=CostGuard(default_budget=50.0),
    canary_router=CanaryRouter(stable_version="v1.0", canary_version="v1.1"),
    approval_gate=ApprovalGate(risk_threshold=0.7),
)

result = governed_app.invoke({"query": "your request"})
```

See [examples/](examples/) for more.

---

## Project structure

```
maa_protocol/         ← Lightweight Python governance package (primary)
examples/            ← Runnable examples (package + LangGraph)
tests/               ← Package tests
docs/                ← Documentation
runtime/             ← OpenClaw runtime (secondary path)
  openclaw-runtime/  ← Full operator runtime with scripts and policies
```

The **package path** is the recommended entry point. The **runtime path** is for operators running the full OpenClaw backend.

---

## Current maturity

Maa Protocol is an **early-stage v1 prototype**.

- The `maa_protocol/` package is tested and runnable
- Examples execute and targeted checks pass
- Approval persistence, stronger test coverage, and clearer package/runtime boundaries are still being improved
- A proper `0.1.0` release will be tagged after the current cleanup pass

---

## Documentation

| File | What it covers |
|---|---|
| [README.md](README.md) | This file |
| [INSTALL.md](docs/INSTALL.md) | Full installation guide |
| [QUICKSTART.md](docs/QUICKSTART.md) | 5-minute getting started |
| [WHAT_MAA_IS_NOT.md](docs/WHAT_MAA_IS_NOT.md) | Scope boundaries |
| [USE_CASES.md](docs/USE_CASES.md) | Common use cases |
| [COMPARISONS.md](docs/COMPARISONS.md) | How Maa differs from alternatives |

Full documentation in [docs/](docs/).

---

## Contributing

See [CONTRIBUTING.md](docs/CONTRIBUTING.md) for guidelines.

---

## License

MIT
