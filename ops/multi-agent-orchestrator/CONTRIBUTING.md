# Contributing to MAA Protocol
**Version:** v1.0 | **Scope:** Community contributors and operators

---

## Coding Standards

### Style
- Python 3.10+ (no type-comment syntax; use real type hints)
- Line length: 100 characters max
- Indent: 4 spaces (no tabs)
- Module-level docstrings required for all `.py` files
- `python3 -m py_compile <file>` must pass before submission

### Naming
- Functions: `snake_case`
- Classes: `PascalCase`
- Constants: `SCREAMING_SNAKE_CASE`
- Internal helpers: prefix with `_`

### File Structure
```
ops/multi-agent-orchestrator/      ← core runtime
agents/templates/                 ← child agent templates
scripts/                         ← operational scripts
ops/observability/               ← metrics and monitoring
```

---

## Test Requirements (Before PR Merge)

Every PR must pass all tests in the pre-deploy gate:

```bash
# Required before any PR merge
python3 ops/multi-agent-orchestrator/tests/test_trust_fixes.py        # 72/72
python3 ops/multi-agent-orchestrator/tests/test_phase2_runtime.py     # 43/43
python3 ops/multi-agent-orchestrator/tests/test_template_load.py      #  7/7
python3 ops/multi-agent-orchestrator/tests/test_access_control.py     # 33/33
python3 ops/multi-agent-orchestrator/tests/test_phase13_cost_control.py # 46/46
python3 scripts/tenant_isolation_test.py                             #  6/6
python3 scripts/secrets_scanner.py                                   # clean
bash scripts/pre_deploy_gate.sh                                      # PASS
```

**If any test fails, the PR cannot be merged.**

### New Feature Tests
- Every new Phase 1–13 feature must include a deterministic test in the appropriate test pack
- Tests must use `pytest`-free stdlib (pure `unittest` or `assert` statements)
- Tests must be self-contained (no external dependencies beyond stdlib)
- Tests must clean up after themselves (no leftover state files)

---

## Security Policy

### No Secrets in Code
- **Never** commit credentials, tokens, API keys, or passwords to the workspace
- Use environment variables or `secrets.env` (excluded from git)
- Workspace `.gitignore` must cover: `*.token`, `*.key`, `secrets.env`, `.env`
- Run `python3 scripts/secrets_scanner.py` before submission

### Responsible Disclosure
- Security vulnerabilities must be reported privately before public disclosure
- Do **not** file public issues for security bugs — contact the project maintainer directly
- Give a reasonable disclosure window (30 days minimum) before public filing

### Access Control
- All mutating operations require OPERATOR or SYSTEM role
- Child agents must never be spawnable by AGENT or CLIENT roles
- Approval gate must be enforced at runtime, not just in prompting

---

## Release Process

### Version Numbering
- Format: `vMAJOR.MINOR` (semver)
- `MAJOR` = breaking changes (runtime API change, RBAC model change)
- `MINOR` = additive changes (new Phase, new templates, new script)
- `PATCH` = bug fixes, test additions, docs corrections

### Release Checklist
See `RELEASE_CHECKLIST.md` for the full pre-publish checklist.

### Canary Deployment (Required for Minor/Major)
1. Deploy new version as canary: `python3 canary_router.py deploy vX.Y`
2. Monitor for 24 hours: `python3 canary_router.py status`
3. If error rate < 5% → promote: `python3 canary_router.py check`
4. If error rate ≥ 5% → revert: `python3 canary_router.py revert`

### Changelog Requirements
- Every public tag must include a `CHANGELOG.md` entry
- Entry must list: new features, bug fixes, breaking changes
- Entries must be human-readable by non-developers

---

## Issue Reporting Standards

### Bug Reports (use this template)
```
## Bug Description
[One sentence clear description]

## Steps to Reproduce
1.
2.
3.

## Expected Behavior
[What should happen]

## Actual Behavior
[What happens instead]

## Environment
- OS:
- Python version:
- Profile: laptop | small-vps | single-tenant | community-server

## Verification
python3 scripts/pre_deploy_gate.sh output:
[paste output here]
```

### Feature Requests
- Feature requests must state the problem being solved
- Must include expected behavior
- Must note any backwards-compatibility considerations

### Security Bugs
- **Do not** file publicly
- Contact the project maintainer directly via a private channel
- Provide steps to reproduce privately
- Allow 30-day disclosure window

---

## Commit Message Format

```
<type>(<scope>): <description>

<optional body>

<optional footer>
```

Types: `fix`, `feat`, `docs`, `test`, `refactor`, `security`
Scope: `task-orchestrator`, `tenant-gate`, `dashboard`, `templates`, `docs`

Example:
```
feat(templates): add Researcher v1.1 template with web search pillar

Adds search_tools: [web_search, web_fetch] to the Researcher template
and updates the 8-pillar harness to include the search pillar.
```

---

## No Fabrications Policy

MAA Protocol has a strict no-fabrication rule. Any contribution that:
- Mocks task completion without real output
- Returns placeholder results
- Claims validation passed without actual verification

...is a **breaking security incident**. Report immediately.

---

*Last updated: v1.0 — Phase 14 initial release*
