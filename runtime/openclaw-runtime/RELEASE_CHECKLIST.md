# MAA Protocol Release Checklist
**Version:** v1.0 | **Applies to:** Every public release tag

---

## Pre-Release Gates (All Must Pass)

### 1. Pre-Deploy Gate — Full Pass
```bash
bash scripts/pre_deploy_gate.sh
```
**Must exit 0** — all 72/72 trust tests must pass.

### 2. All Test Packs — Green
```bash
python3 ops/multi-agent-orchestrator/tests/test_trust_fixes.py        # 72/72 ✅
python3 ops/multi-agent-orchestrator/tests/test_phase2_runtime.py     # 43/43 ✅
python3 ops/multi-agent-orchestrator/tests/test_template_load.py    #  7/7 ✅
python3 ops/multi-agent-orchestrator/tests/test_access_control.py   # 33/33 ✅
python3 ops/multi-agent-orchestrator/tests/test_phase13_cost_control.py # 46/46 ✅
python3 scripts/tenant_isolation_test.py                             #  6/6 ✅
python3 scripts/secrets_scanner.py                                   # clean ✅
```
**Must all show 100% pass.** Any regression blocks the release.

### 3. py_compile — All Files Clean
```bash
python3 -m py_compile \
  ops/multi-agent-orchestrator/task_orchestrator.py \
  ops/multi-agent-orchestrator/tenant_gate.py \
  ops/multi-agent-orchestrator/idempotency.py \
  ops/multi-agent-orchestrator/canary_router.py \
  ops/multi-agent-orchestrator/access_control.py \
  ops/multi-agent-orchestrator/approval_gate.py
```

### 4. Secrets Scanner — Zero Flagged
```bash
python3 scripts/secrets_scanner.py
```
**Must return clean (0 flagged).** Any secret-like pattern blocks the release.

### 5. Gate Status — CONFIRMED PASS
```bash
python3 ops/multi-agent-orchestrator/task_orchestrator.py gate-status
```
Must print `status: pass` with correct pass count.

---

## Version Checks

### 6. VERSION Constant — Updated
```bash
grep "^VERSION = " ops/multi-agent-orchestrator/task_orchestrator.py
```
Must reflect the version being released (`vX.Y`).

### 7. Policy Version Headers — Updated
Every modified policy file must have an updated version header:
```bash
grep "^<!-- Version:" \
  ops/multi-agent-orchestrator/SECURITY.md \
  ops/multi-agent-orchestrator/APPROVAL_GATE.md \
  ops/multi-agent-orchestrator/DATA_PRIVACY.md \
  ops/multi-agent-orchestrator/COST_CONTROL.md \
  ops/multi-agent-orchestrator/SLA.md \
  ops/multi-agent-orchestrator/ACCESS_CONTROL.md \
  ops/multi-agent-orchestrator/DISASTER_RECOVERY.md \
  ops/multi-agent-orchestrator/VERSIONING.md
```

### 8. Template Versions — Updated
Every modified template must have an updated version header:
```bash
grep "^<!-- Version:" agents/templates/*/v*.md
```

---

## Documentation

### 9. CHANGELOG.md — Created / Updated (required before public tag)
```bash
cat CHANGELOG.md
```
Must exist before public release and include entry for this release:
- New features (with Phase number)
- Bug fixes (with issue reference if applicable)
- Breaking changes (if any)
- Upgrade notes (if any)

### 10. COMMUNITY_RUNBOOK.md — Verified Present
```bash
ls ops/multi-agent-orchestrator/COMMUNITY_RUNBOOK.md
```
Must exist and be complete.

### 11. CONTRIBUTING.md — Verified Present
```bash
ls ops/multi-agent-orchestrator/CONTRIBUTING.md
```

---

## Sample Config Validation

### 12. All 4 Sample Configs — Valid JSON
```bash
python3 -c "import json; ...
[json.load(open(f)) for f in [
  'templates/maa-product/laptop.json',
  'templates/maa-product/small-vps.json',
  'templates/maa-product/single-tenant.json',
  'templates/maa-product/community-server.json'
]]"
```

### 13. Sample Config Structure — Complete
Each config must have all required fields:
```bash
python3 -c "
import json, sys
required = ['_meta', 'operator', 'client', 'defaults', 'runtime', 'notifications']
for f in ['laptop', 'small-vps', 'single-tenant', 'community-server']:
    path = f'templates/maa-product/{f}.json'
    with open(path) as fh:
        cfg = json.load(fh)
    missing = [r for r in required if r not in cfg]
    if missing:
        print(f'{f}: MISSING {missing}')
        sys.exit(1)
print('All configs structurally valid')
"
```

---

## Canary Readiness (Minor/Major Releases Only)

### 14. Canary Version — Defined
```bash
python3 ops/multi-agent-orchestrator/canary_router.py status
```
Must show a stable version. Canary must be clean before deploy.

### 15. Canary Script — Working
```bash
python3 ops/multi-agent-orchestrator/canary_router.py status
python3 ops/multi-agent-orchestrator/canary_router.py deploy vX.Y
```
Use `status` first, then deploy the canary version explicitly.

### 16. Rollback Plan — Documented
The `VERSIONING.md` rollback section must be current and accurate.

---

## Operational Verification

### 17. Continuous Health Monitor — Installed
```bash
crontab -l | grep continuous_health_monitor
```
Must show the 15-minute cron entry.

### 18. Pre-Deploy Gate Cron — Installed
```bash
crontab -l | grep pre_deploy_gate
```
Must show the daily 6 AM IST entry.

### 19. Backup Cron — Installed
```bash
crontab -l | grep disaster_recovery_backup
```
Must show the daily backup entry.

---

## Community-Specific Checks

### 20. COMMUNITY_RUNBOOK.md — Quick Start Works
```bash
# Simulate quick-start on a clean config load
python3 -c "
import json
cfg = json.load(open('templates/maa-product/laptop.json'))
assert cfg['defaults']['multi_tenant_mode'] == False
assert cfg['defaults']['approval_gate_enforced'] == True
assert cfg['defaults']['public_write_integrations'] == False
print('laptop.json defaults: SAFE')
"
```

### 21. Runtime Config Template — Valid
```bash
python3 -c "import json; json.load(open('templates/maa-product/runtime-config.template.json'))"
```

### 22. No Credentials in Configs
```bash
python3 scripts/secrets_scanner.py
```
Sample configs must not contain real credentials.

---

## Pre-Tag Final Checks

### 23. Upgrade Notes — Written (if non-patch release)
If this is a MINOR or MAJOR release, the CHANGELOG entry must include:
- What changed that requires operator attention
- Any manual migration steps
- Estimated downtime (if any)

### 24. Rollback Note — Present (if non-patch release)
Must be able to revert to the previous stable version via:
```bash
python3 canary_router.py revert
# OR
git revert HEAD
```

### 25. Operator Approval — Obtained
**No public tag may be created without explicit operator approval.**
```
Approved: [ ] Yes — ready for vX.Y release
Signed: Operator / [date]
```

---

## Post-Release (After Tag)

- [ ] Release notification sent to the operator
- [ ] CHANGELOG.md committed
- [ ] Git tag created: `vX.Y`
- [ ] Git tag pushed (if applicable)
- [ ] Release notes published (if applicable)

---

*Checklist version: v1.0 | Last reviewed: 2026-04-23*
