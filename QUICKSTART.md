# Maa Protocol Quickstart

This guide is for a new operator who wants a fast first run.

## 1. Clone the repo

```bash
git clone https://github.com/SnehaPlayground/maa-protocol.git
cd maa-protocol
```

## 2. Confirm OpenClaw works

```bash
openclaw status
```

## 3. Pick a profile

For most first-time users:

```bash
mkdir -p knowledge/maa-product
cp templates/maa-product/laptop.json knowledge/maa-product/runtime-config.json
```

## 4. Use the guided setup helper (recommended)

```bash
python3 scripts/maa_setup.py
```

## 5. Run the doctor check

```bash
python3 scripts/maa_doctor.py
```

## 6. Run a demo task

```bash
python3 scripts/maa_demo.py
```

## 7. Check the result

```bash
python3 ops/multi-agent-orchestrator/task_orchestrator.py list --limit 5
python3 ops/multi-agent-orchestrator/task_orchestrator.py status <task_id>
```

## What success looks like

You should see:
- a task created
- the task move through running/validated states
- an output path or validation result

## If you only read one thing

Read `INSTALL.md` first if:
- OpenClaw is not already installed
- you want a clean setup
- you are deploying on a VPS
