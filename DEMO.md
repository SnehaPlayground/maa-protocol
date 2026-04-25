# Maa Demo

## Guided demo path

### 1. Run setup

```bash
python3 scripts/maa_setup.py
```

### 2. Run doctor

```bash
python3 scripts/maa_doctor.py
```

### 3. Run demo

```bash
python3 scripts/maa_demo.py
```

## Manual demo path

```bash
python3 ops/multi-agent-orchestrator/task_orchestrator.py submit research "demo: explain this Maa deployment" --run
```

Then inspect:

```bash
python3 ops/multi-agent-orchestrator/task_orchestrator.py list --limit 5
python3 ops/multi-agent-orchestrator/task_orchestrator.py status <task_id>
```

## Expected outcome

A healthy demo should:
- create a task
- run it through Maa
- show status or output details without path/permission failures
