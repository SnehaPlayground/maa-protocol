# Maa Protocol Quickstart

## 1. Clone and enter the repo

```bash
git clone https://github.com/SnehaPlayground/maa-protocol.git
cd maa-protocol
```

## 2. Create a virtual environment and install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

## 3. Run validation

```bash
ruff check .
mypy maa_protocol
pytest -q
```

## 4. Check the CLI

```bash
maa-x version
maa-x governance audit
maa-x swarm init
```

## What success looks like

- editable install works
- `maa_protocol` imports cleanly
- governance tests pass with coverage >= 80%
- the CLI runs without `maa_x` import errors
