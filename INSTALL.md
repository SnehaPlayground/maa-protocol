# Install Maa Protocol

Maa Protocol is a governance layer for LangGraph workflows.

## Requirements

- Python 3.10+
- Git

## Install

```bash
git clone https://github.com/SnehaPlayground/maa-protocol.git
cd maa-protocol
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

## Validate

```bash
ruff check .
mypy maa_protocol
pytest
```

## Smoke the CLI

```bash
maa-x version
maa-x governance audit
maa-x swarm init
```

## Notes

- the installable surface is governance-only
- broader orchestration experiments are intentionally outside the focused governance distribution
