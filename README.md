# Maa Protocol

**Maa Protocol adds operator controls to agent workflows, without replacing your runtime.**

🚀 Maa Protocol is an open-source governance layer for AI agents. It solves the frustrating problem of agent timeouts, lost state, and operational risk in production—adding approval gates, cost controls, and self-healing retries to any LangGraph app.

A lightweight, self-hosted governance layer for LangGraph workflows, with an optional OpenClaw runtime path for operators who need a fuller single-node control plane.

---

## Who this is for

**Maa Protocol is for you if you:**
- are running LangGraph or OpenClaw-based agent workflows
- need approval gates, cost controls, tenant isolation, or canary routing without rebuilding your runtime
- want self-healing, idempotency, and observability as first-class primitives
- are deploying on a laptop, workstation, or small VPS

**Maa Protocol is not for you if you:**
- need a distributed cluster scheduler or managed SaaS
- want a drop-in replacement for LangGraph, CrewAI, or AutoGen
- need Kubernetes-native orchestration
- require a battle-tested production platform today

---

## Core features

| Feature | What it does |
|---|---|
| **Approval Gate** | Blocks high-risk actions until explicitly authorized |
| **Tenant Isolation** | Adds RBAC and per-tenant controls |
| **Cost Guard** | Tracks and limits spend per tenant or operation |
| **Canary Router** | Safely routes a percentage of traffic to a new version |
| **Idempotency** | Prevents duplicate task execution |
| **Self-Healing** | Retries failures with bounded recovery hooks |
| **Observability** | Supports metrics, logs, and progress tracking |

---

## Quick start

### Try the package

```bash
pip install -e .[test]
pytest tests/test_maa_protocol.py
```

For the LangGraph example:

```bash
pip install -e .[langgraph]
python3 examples/langgraph_governance_full_example.py
```

### Explore the optional runtime

```bash
pip install openclaw
python3 scripts/maa_setup.py
python3 scripts/maa_doctor.py
python3 scripts/maa_demo.py
```

See [INSTALL.md](INSTALL.md) and [QUICKSTART.md](QUICKSTART.md) for setup details.

---

## Example: Governance wrapper

```python
from langgraph.graph import StateGraph
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
```

See [examples/](examples/) for more.

---

## Project structure

```text
maa_protocol/         primary lightweight governance package
examples/             runnable examples
tests/                package tests
docs/                 supporting documentation
runtime/              optional OpenClaw runtime
```

The **package path** is the recommended entry point. The **runtime path** is optional and more opinionated.

---

## Current maturity

Maa Protocol is an **early-stage prototype with production-oriented goals**.

- the `maa_protocol/` package is lightweight, tested, and runnable
- the runtime path is broader and still evolving
- approval persistence, audit storage, stronger cost accounting, and deeper observability are still ahead
- versioning remains pre-1.0 until those foundations are in place

---

## Documentation

| File | What it covers |
|---|---|
| [INSTALL.md](INSTALL.md) | Installation guide |
| [QUICKSTART.md](QUICKSTART.md) | Getting started fast |
| [docs/WHAT_MAA_IS_NOT.md](docs/WHAT_MAA_IS_NOT.md) | Scope boundaries |
| [docs/USE_CASES.md](docs/USE_CASES.md) | Common use cases |
| [docs/COMPARISONS.md](docs/COMPARISONS.md) | How Maa differs from alternatives |

---

## License

MIT
