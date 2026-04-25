# First Run Guide

This guide is written for a new operator.

## Step 1: confirm the runtime exists

Run:

```bash
openclaw status
```

If this fails, Maa is not ready yet because OpenClaw is the runtime dependency.

## Step 2: create a runtime config

```bash
mkdir -p knowledge/maa-product
cp templates/maa-product/laptop.json knowledge/maa-product/runtime-config.json
```

Open `knowledge/maa-product/runtime-config.json` and update:
- operator label
- alert target

## Step 3: verify the machine

```bash
python3 scripts/health_check.py
```

You want a clean result with no critical disk or runtime warnings.

## Step 4: verify Maa itself

```bash
bash scripts/pre_deploy_gate.sh
```

If this fails, do not continue until the gate passes.

## Step 5: submit your first task

```bash
python3 ops/multi-agent-orchestrator/task_orchestrator.py submit research "test: first run validation" --run
```

## Step 6: inspect the task

```bash
python3 ops/multi-agent-orchestrator/task_orchestrator.py list --limit 5
python3 ops/multi-agent-orchestrator/task_orchestrator.py status <task_id>
```

## Step 7: confirm the install is usable

A usable install should give you all of these:
- task submission works
- status lookup works
- validation runs
- observability dashboard renders
- no permission or path errors block normal operation

## Common first-run blockers

### OpenClaw missing
Install or configure OpenClaw first.

### Runtime config missing
Copy a template from `templates/maa-product/` into `knowledge/maa-product/runtime-config.json`.

### Pre-deploy gate fails
Fix that before trusting the deployment.

### Alert target not configured
The system can still run locally, but operator alerts should be configured before real use.
