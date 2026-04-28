# Contributing

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
pre-commit install
```

## Before opening a PR

- run `ruff check .`
- run `mypy maa_protocol`
- run `pytest`
- update docs when behavior changes
- add or update tests for guard logic and persistence behavior

## Contribution guidelines

- Keep scope aligned to governance and control concerns
- Prefer small, composable modules
- Avoid reintroducing unrelated agent-platform features into the core package
- Write honest docs and changelog entries
