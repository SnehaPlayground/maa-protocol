# Maa Protocol

Maa Protocol is a self-hosted, operator-first governance layer for agentic workflows. It adds approval gates, tenant-aware controls, RBAC, canary routing, cost controls, and self-healing around existing agent runtimes instead of replacing them.

## What this repo currently contains

This repository currently has two related surfaces:

1. `maa_protocol/`
   - a lightweight Python governance wrapper package for LangGraph-style workflows
   - useful for wrapping an existing graph with governance checks

2. the broader Maa runtime in `ops/`, `scripts/`, and related docs
   - a larger operator runtime intended for OpenClaw-backed deployments
   - this is the orchestration and operational side of Maa

That distinction matters. The package can be reviewed and tested on its own. The full runtime story depends on OpenClaw and the wider repo structure.

## What Maa is

Maa is:
- a governance layer for agentic work
- operator-first by design
- built around approval, validation, observability, recovery, and control
- suitable for single-node laptop, workstation, and small VPS deployments

## What Maa is not

Maa is not:
- a managed SaaS
- a distributed cluster scheduler
- a Kubernetes-native orchestration platform
- a no-dependency framework
- a replacement for LangGraph, OpenClaw, or a full workflow engine

## Dependency model

### Package-level `maa_protocol/`
The `maa_protocol` package is intentionally dependency-light.

- `pip install -e .` installs the local package
- `pip install -e .[langgraph]` adds the optional LangGraph dependency for the full example
- `pip install -e .[test]` adds test dependencies

### Full Maa runtime
The broader Maa runtime depends on OpenClaw for:
- agent session runtime
- session and channel orchestration
- message routing

Without OpenClaw, the full Maa runtime cannot run fully.

## Quick paths

### A. Try the package only

```bash
pip install -e .[test]
pytest tests/test_maa_protocol.py
python3 examples/langgraph_governance_example.py
```

For the full LangGraph example:

```bash
pip install -e .[langgraph]
python3 examples/langgraph_governance_full_example.py
```

### B. Explore the full Maa runtime

1. Install and verify OpenClaw
2. Run `python3 scripts/maa_setup.py`
3. Run `python3 scripts/maa_doctor.py`
4. Run `python3 scripts/maa_demo.py`

Detailed runtime guides:
- `INSTALL.md`
- `QUICKSTART.md`
- `FIRST_RUN.md`
- `DEMO.md`
- `WHAT_MAA_IS_NOT.md`
- `USE_CASES.md`
- `COMPARISONS.md`
- `ops/multi-agent-orchestrator/COMMUNITY_RUNBOOK.md`

## LangGraph governance wrapper example

```python
from langgraph.graph import StateGraph, END
from maa_protocol import TenantContext, CostGuard, CanaryRouter, ApprovalGate, GovernanceWrapper

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

Examples:
- `examples/langgraph_governance_example.py`
- `examples/langgraph_governance_full_example.py`

## Current maturity

Honest current status:
- the package is a credible internal v1 prototype
- targeted checks and example execution pass
- it is not yet fully production-grade
- approval persistence, stronger tests, and clearer package/runtime boundaries still need work

## Repo scope

This repo should contain Maa core and public-facing documentation.

It should not contain:
- private workspace control files
- historical task state or runtime debris
- personal business workflows mixed into Maa core
- private memory, transcripts, or operator-specific secrets

Operator-specific or domain-specific implementations should live under `examples/` or in private repositories, not inside Maa core paths.

## License

MIT
