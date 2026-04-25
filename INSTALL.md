# Install Maa Protocol

Maa Protocol is a self-hosted, operator-first, single-node multi-agent orchestration framework.

## Before you start

You need:
- Linux or macOS
- Python 3.10+
- Git
- OpenClaw installed and working

## What OpenClaw does

Maa Protocol depends on OpenClaw for:
- agent session runtime
- channel/message routing
- session orchestration

Without OpenClaw, Maa cannot run fully.

## 1. Clone the repository

```bash
git clone https://github.com/SnehaPlayground/maa-protocol.git
cd maa-protocol
```

## 2. Verify Python

```bash
python3 --version
```

Expected: Python 3.10 or newer.

## 3. Verify OpenClaw

```bash
openclaw status
```

If OpenClaw is not installed or not configured, stop here and install/configure it first.

## 4. Choose a deployment profile

Available profiles:
- `templates/maa-product/laptop.json`
- `templates/maa-product/small-vps.json`
- `templates/maa-product/single-tenant.json`
- `templates/maa-product/community-server.json`

Recommended:
- laptop or personal workstation → `laptop.json`
- small server or VPS → `small-vps.json`
- one operator, one business deployment → `single-tenant.json`
- multi-tenant community server → `community-server.json`

## 5. Copy a profile to runtime config

```bash
mkdir -p knowledge/maa-product
cp templates/maa-product/laptop.json knowledge/maa-product/runtime-config.json
```

Replace `laptop.json` with the profile you want.

## 6. Edit the runtime config

At minimum, update:
- operator label
- alert target
- any spend/runtime limits you want to override

## 7. Run the health and setup checks

```bash
python3 scripts/health_check.py
python3 ops/observability/maa_metrics.py dashboard
bash scripts/pre_deploy_gate.sh
```

Expected:
- health check completes
- dashboard renders
- pre-deploy gate passes

## 8. Submit a test task

```bash
python3 ops/multi-agent-orchestrator/task_orchestrator.py submit research "test: confirm Maa install works" --run
```

Then check status:

```bash
python3 ops/multi-agent-orchestrator/task_orchestrator.py list --limit 5
python3 ops/multi-agent-orchestrator/task_orchestrator.py status <task_id>
```

## 9. If something fails

Check these first:

```bash
python3 scripts/health_check.py
python3 ops/observability/maa_metrics.py summary --since 1
python3 ops/multi-agent-orchestrator/task_orchestrator.py gate-status
```

## Current deployment model

Maa is currently designed for:
- single laptop deployment
- single VPS deployment
- single-node operator-managed environments

It is not currently packaged as a distributed cluster runtime.
