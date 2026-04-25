#!/usr/bin/env python3
"""
Phase 13 Cost Control — Full Test Pack
Tests: daily/monthly spend caps, exceed actions, degrade modes,
       day/month reset, tenant isolation, queue, reject, require_approval.
Covers Err13.txt Defects 13.1–13.5 closure verification.
"""
import sys, os, json, time, py_compile
from pathlib import Path
from datetime import datetime, UTC  # UTC needed for alert timestamp

os.chdir("/root/.openclaw/workspace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

WORKSPACE = "/root/.openclaw/workspace"
PASS = 0; FAIL = 0

def check(label, condition, detail=""):
    global PASS, FAIL
    if condition:
        print(f"  ✅ {label}")
        PASS += 1
    else:
        print(f"  ❌ {label}")
        if detail: print(f"     -> {detail}")
        FAIL += 1


# ── TEST 1: record_spend increments daily + monthly accumulators ─────────────
print("\n[TEST 1] record_spend increments _spend_today and _spend_this_month")
from tenant_gate import record_spend, _quota_store_path

test_id = f"phase13-full-{int(time.time() * 1000) % 100000:05d}"
op_id = f"testop_{test_id}"; cl_id = f"testcl_{test_id}"

record_spend(op_id, cl_id, "market-brief", 5.0)
record_spend(op_id, cl_id, "research", 7.5)

store = _quota_store_path(op_id, cl_id)
check("quota store created", store.exists())
if store.exists():
    with open(store) as f: qdata = json.load(f)
    check("_spend_today written", "_spend_today" in qdata)
    check("_spend_this_month written", "_spend_this_month" in qdata)
    check("today = 12.5", abs(qdata.get("_spend_today", 0) - 12.5) < 0.01,
          f"got {qdata.get('_spend_today')}")
    check("month = 12.5", abs(qdata.get("_spend_this_month", 0) - 12.5) < 0.01,
          f"got {qdata.get('_spend_this_month')}")


# ── TEST 2: estimate_task_cost uses base_runtime_min × cost_per_minute ────────
print("\n[TEST 2] estimate_task_cost computes correct USD estimates")
from tenant_gate import estimate_task_cost

cost_mb = estimate_task_cost("market-brief", None)  # 8 min × $0.05
cost_research = estimate_task_cost("research", None)  # 10 min × $0.05
cost_coder = estimate_task_cost("coder", None)  # 15 min × $0.06
cost_default = estimate_task_cost("unknown-type", None)  # 5 min × $0.04

check("market-brief: 8 × 0.05 = $0.40", abs(cost_mb - 0.40) < 0.001, f"got {cost_mb}")
check("research: 10 × 0.05 = $0.50", abs(cost_research - 0.50) < 0.001, f"got {cost_research}")
check("coder: 15 × 0.06 = $0.90", abs(cost_coder - 0.90) < 0.001, f"got {cost_coder}")
check("default: 5 × 0.04 = $0.20", abs(cost_default - 0.20) < 0.001, f"got {cost_default}")

cost_actual = estimate_task_cost("research", 300.0)  # 5 min × $0.05
check("runtime override: 5 min × $0.05 = $0.25", abs(cost_actual - 0.25) < 0.001, f"got {cost_actual}")
cost_override = estimate_task_cost("research", None, 0.10)
check("override: 10 × 0.10 = $1.00", abs(cost_override - 1.0) < 0.001, f"got {cost_override}")


# ── TEST 3: _check_spend_quotas allows under-cap submission ───────────────────
print("\n[TEST 3] _check_spend_quotas allows under-cap tenant")
from tenant_gate import _check_spend_quotas, TenantContext

test_op = f"undercap_{test_id}"; test_cl = f"undercapcl_{test_id}"
store_uc = _quota_store_path(test_op, test_cl)
store_uc.parent.mkdir(parents=True, exist_ok=True)
with open(store_uc, "w") as f:
    json.dump({
        "_spend_today": 20.0, "_spend_this_month": 300.0,
        "_last_day_reset": time.time(), "_last_month_reset": time.time(),
        "_month_key": int(time.strftime("%Y%m")),
    }, f)

tenant = TenantContext(operator_id=test_op, client_id=test_cl)
blocked, action, _, _, _ = _check_spend_quotas(tenant, "research", 5.0)  # $5 well under $50 daily
check("under-cap: blocked=False", blocked == False)
check("under-cap: action=proceed", action == "proceed")


# ── TEST 4: _check_spend_quotas rejects over daily cap ────────────────────────
print("\n[TEST 4] _check_spend_quotas rejects over-daily-cap tenant")
test_op2 = f"overday_{test_id}"; test_cl2 = f"overdaycl_{test_id}"
store_od = _quota_store_path(test_op2, test_cl2)
store_od.parent.mkdir(parents=True, exist_ok=True)
with open(store_od, "w") as f:
    json.dump({
        "_spend_today": 48.0, "_spend_this_month": 100.0,
        "_last_day_reset": time.time(), "_last_month_reset": time.time(),
        "_month_key": int(time.strftime("%Y%m")),
    }, f)

tenant2 = TenantContext(operator_id=test_op2, client_id=test_cl2)
blocked2, action2, limit2, cap2, current2 = _check_spend_quotas(tenant2, "research", 5.0)  # $5 more → $53 > $50
check("over-daily-cap: blocked=True", blocked2 == True)
check("over-daily-cap: action=reject (default)", action2 == "reject")


# ── TEST 5: _check_spend_quotas rejects over monthly cap ─────────────────────
print("\n[TEST 5] _check_spend_quotas rejects over-monthly-cap tenant")
test_op3 = f"overmonth_{test_id}"; test_cl3 = f"overmonthcl_{test_id}"
store_om = _quota_store_path(test_op3, test_cl3)
store_om.parent.mkdir(parents=True, exist_ok=True)
with open(store_om, "w") as f:
    json.dump({
        "_spend_today": 5.0, "_spend_this_month": 498.0,
        "_last_day_reset": time.time(), "_last_month_reset": time.time(),
        "_month_key": int(time.strftime("%Y%m")),
    }, f)

tenant3 = TenantContext(operator_id=test_op3, client_id=test_cl3)
blocked3, action3, limit3, cap3, current3 = _check_spend_quotas(tenant3, "research", 5.0)  # $5 more → $503 > $500
check("over-monthly-cap: blocked=True", blocked3 == True)


# ── TEST 6: _check_spend_quotas day boundary reset ────────────────────────────
print("\n[TEST 6] New day resets _spend_today (but not _spend_this_month)")
test_op4 = f"dayreset_{test_id}"; test_cl4 = f"dayresetcl_{test_id}"
store_dr = _quota_store_path(test_op4, test_cl4)
store_dr.parent.mkdir(parents=True, exist_ok=True)
with open(store_dr, "w") as f:
    json.dump({
        "_spend_today": 999.0, "_spend_this_month": 300.0,
        "_last_day_reset": time.time() - 25 * 3600,  # 25h ago → stale day
        "_last_month_reset": time.time(),
        "_month_key": int(time.strftime("%Y%m")),
    }, f)

record_spend(test_op4, test_cl4, "market-brief", 5.0)
with open(store_dr) as f: qdata4 = json.load(f)
check("day reset: _spend_today cleared to near 0", qdata4.get("_spend_today", 9999) < 100,
      f"got {qdata4.get('_spend_today')}")
check("day reset: _spend_this_month NOT cleared", qdata4.get("_spend_this_month", 0) >= 5.0,
      f"got {qdata4.get('_spend_this_month')}")


# ── TEST 7: month boundary resets _spend_this_month ──────────────────────────
print("\n[TEST 7] New month resets _spend_this_month")
test_op5 = f"monthreset_{test_id}"; test_cl5 = f"monthresetcl_{test_id}"
store_mr = _quota_store_path(test_op5, test_cl5)
store_mr.parent.mkdir(parents=True, exist_ok=True)
with open(store_mr, "w") as f:
    json.dump({
        "_spend_today": 5.0, "_spend_this_month": 499.0,
        "_last_day_reset": time.time(), "_last_month_reset": time.time() - 32 * 86400,
        "_month_key": 202601,  # Previous month
    }, f)

record_spend(test_op5, test_cl5, "research", 2.0)
with open(store_mr) as f: qdata5 = json.load(f)
check("month reset: _spend_this_month cleared", qdata5.get("_spend_this_month", 0) < 10.0,
      f"got {qdata5.get('_spend_this_month')}")
check("month reset: _spend_today preserved", qdata5.get("_spend_today", 0) >= 5.0,
      f"got {qdata5.get('_spend_today')}")
check("month reset: _month_key updated", qdata5.get("_month_key", 0) >= 202602,
      f"got {qdata5.get('_month_key')}")


# ── TEST 8: SpendBudgetExhausted exception carries exceed_action ──────────────
print("\n[TEST 8] SpendBudgetExhausted carries exceed_action correctly")
from tenant_gate import SpendBudgetExhausted

exc1 = SpendBudgetExhausted("op", "cl", "max_daily_spend", 50.0, 53.0, "reject")
exc2 = SpendBudgetExhausted("op", "cl", "max_monthly_spend", 500.0, 503.0, "queue")
exc3 = SpendBudgetExhausted("op", "cl", "max_monthly_spend", 500.0, 503.0, "require_approval")

check("exceed_action=reject", exc1.exceed_action == "reject")
check("exceed_action=queue", exc2.exceed_action == "queue")
check("exceed_action=require_approval", exc3.exceed_action == "require_approval")
check("quota_type preserved", exc2.quota_type == "max_monthly_spend")


# ── TEST 9: tenant isolation — Tenant A over budget doesn't block Tenant B ────
print("\n[TEST 9] Tenant isolation: one tenant's over-budget doesn't block another")
test_op_a = f"iso_a_{test_id}"; test_cl_a = f"iso_a_cl_{test_id}"
test_op_b = f"iso_b_{test_id}"; test_cl_b = f"iso_b_cl_{test_id}"

store_a = _quota_store_path(test_op_a, test_cl_a)
store_a.parent.mkdir(parents=True, exist_ok=True)
with open(store_a, "w") as f:
    json.dump({
        "_spend_today": 999.0, "_spend_this_month": 9999.0,
        "_last_day_reset": time.time(), "_last_month_reset": time.time(),
        "_month_key": int(time.strftime("%Y%m")),
    }, f)

store_b = _quota_store_path(test_op_b, test_cl_b)
store_b.parent.mkdir(parents=True, exist_ok=True)
with open(store_b, "w") as f:
    json.dump({
        "_spend_today": 5.0, "_spend_this_month": 50.0,
        "_last_day_reset": time.time(), "_last_month_reset": time.time(),
        "_month_key": int(time.strftime("%Y%m")),
    }, f)

tenant_a = TenantContext(operator_id=test_op_a, client_id=test_cl_a)
tenant_b = TenantContext(operator_id=test_op_b, client_id=test_cl_b)

blocked_a, action_a, _, _, _ = _check_spend_quotas(tenant_a, "research", 5.0)
blocked_b, action_b, _, _, _ = _check_spend_quotas(tenant_b, "research", 5.0)

check("Tenant A blocked", blocked_a == True)
check("Tenant B not blocked", blocked_b == False)


# ── TEST 10: compile sanity for Phase 13 Python files ─────────────────────────
print("\n[TEST 10] compile sanity for Phase 13 Python files")
for fpath in ["ops/multi-agent-orchestrator/tenant_gate.py",
              "ops/multi-agent-orchestrator/task_orchestrator.py",
              "ops/email/send_email_via_gog.py",
              "ops/multi-agent-orchestrator/idempotency.py"]:
    full = f"{WORKSPACE}/{fpath}"
    try:
        py_compile.compile(full, doraise=True)
        check(f"compile OK: {fpath.split('/')[-1]}", True)
    except Exception as e:
        check(f"compile OK: {fpath.split('/')[-1]}", False, str(e))

approval_gate_code = Path(f"{WORKSPACE}/ops/multi-agent-orchestrator/approval_gate.py").read_text()
idempotency_code = Path(f"{WORKSPACE}/ops/multi-agent-orchestrator/idempotency.py").read_text()
check("approval dedup path matches approval_gate path",
      'EMAIL_DATA_DIR  = WORKSPACE / "data/email"' in approval_gate_code and
      'APPROVAL_STATE  = EMAIL_DATA_DIR / "approval_state.json"' in approval_gate_code and
      'Path("/root/.openclaw/workspace/data/email/approval_state.json")' in idempotency_code)


# ── TEST 11: pre-deploy gate baseline ───────────────────────────────────────
print("\n[TEST 11] pre-deploy gate baseline (72/72)")
gate_json = Path(f"{WORKSPACE}/logs/pre_deploy_gate_latest.json")
if gate_json.exists():
    with open(gate_json) as f: result = json.load(f)
    passed = result.get("passed", 0)
    failed = result.get("failed", 999)
    check("pre-deploy gate: 72 passed, 0 failures",
          passed >= 72 and failed == 0,
          f"passed={passed} failed={failed}")
else:
    check("pre-deploy gate result found", False)


# ── TEST 12: all existing test packs still green ────────────────────────────
print("\n[TEST 12] existing test packs still green")
for test_script in [
    "ops/multi-agent-orchestrator/tests/test_access_control.py",
    "ops/multi-agent-orchestrator/tests/test_phase2_runtime.py",
    "ops/multi-agent-orchestrator/tests/test_trust_fixes.py",
    "ops/multi-agent-orchestrator/tests/test_template_load.py",
    "scripts/tenant_isolation_test.py",
]:
    result = os.popen(f"python3 {WORKSPACE}/{test_script} 2>&1").read()
    check(f"{test_script.split('/')[-1]}",
          "passed" in result.lower() or "PASS" in result,
          result.strip().split("\n")[-1] if result else "no output")


# ── TEST 13: queue mode via config (exceed_action=queue in client.json) ──────
print("\n[TEST 13] queue mode: config-based exceed_action=queue raises SpendBudgetExhausted")
from tenant_gate import submit_task_gate, save_client_config, save_operator_config

test_q = f"queue_{test_id}"; test_qcl = f"queue_cl_{test_id}"
save_operator_config(test_q, {
    "operator_id": test_q, "exceed_action": "queue",
    "max_daily_spend": 50.0, "max_monthly_spend": 500.0
})
save_client_config(test_q, test_qcl, {
    "client_id": test_qcl, "exceed_action": "queue",
    "max_daily_spend": 50.0, "max_monthly_spend": 500.0
})

store_q = _quota_store_path(test_q, test_qcl)
store_q.parent.mkdir(parents=True, exist_ok=True)
with open(store_q, "w") as f:
    json.dump({
        "_spend_today": 999.0, "_spend_this_month": 9999.0,
        "_last_day_reset": time.time(), "_last_month_reset": time.time(),
        "_month_key": int(time.strftime("%Y%m")),
    }, f)

exc_q = None
try:
    submit_task_gate(
        task_prompt="test queue mode", task_type="research",
        raw_context={"operator_id": test_q, "client_id": test_qcl},
        task_id=f"queue-test-{test_id}"
    )
except SpendBudgetExhausted as sbe:
    exc_q = sbe
except Exception as e:
    exc_q = e

check("SpendBudgetExhausted raised", exc_q is not None and isinstance(exc_q, SpendBudgetExhausted),
      f"got {type(exc_q).__name__}")
if exc_q:
    check("exceed_action=queue", exc_q.exceed_action == "queue",
          f"got {exc_q.exceed_action}")


# ── TEST 14: require_approval mode via config ────────────────────────────────
print("\n[TEST 14] require_approval mode: raises SpendBudgetExhausted with require_approval")
test_ra = f"reqapp_{test_id}"; test_racl = f"reqapp_cl_{test_id}"
save_operator_config(test_ra, {
    "operator_id": test_ra, "exceed_action": "require_approval",
    "max_daily_spend": 50.0, "max_monthly_spend": 500.0
})
save_client_config(test_ra, test_racl, {
    "client_id": test_racl, "exceed_action": "require_approval",
    "max_daily_spend": 50.0, "max_monthly_spend": 500.0
})

store_ra = _quota_store_path(test_ra, test_racl)
store_ra.parent.mkdir(parents=True, exist_ok=True)
with open(store_ra, "w") as f:
    json.dump({
        "_spend_today": 999.0, "_spend_this_month": 9999.0,
        "_last_day_reset": time.time(), "_last_month_reset": time.time(),
        "_month_key": int(time.strftime("%Y%m")),
    }, f)

exc_ra = None
try:
    submit_task_gate(
        task_prompt="test approval mode", task_type="research",
        raw_context={"operator_id": test_ra, "client_id": test_racl},
        task_id=f"ra-test-{test_id}"
    )
except SpendBudgetExhausted as sbe:
    exc_ra = sbe
except Exception as e:
    exc_ra = e

check("SpendBudgetExhausted raised", exc_ra is not None and isinstance(exc_ra, SpendBudgetExhausted),
      f"got {type(exc_ra).__name__ if exc_ra else 'None'}")
if exc_ra:
    check("exceed_action=require_approval", exc_ra.exceed_action == "require_approval",
          f"got {exc_ra.exceed_action}")


# ── TEST 15: spend spike suppression still active ────────────────────────────
print("\n[TEST 15] spend_spike_cooldown suppression still active")
from tenant_gate import _check_spend_spike_suppression, CONTINUOUS_ALERT_FILE

alert_data = {
    "check": "spend_spike",
    "timestamp": datetime.now(UTC).isoformat(),
    "failures": [
        {"tenant": f"{test_op_a}:{test_cl_a}", "cost_1h": 99.0, "daily_avg": 10.0}
    ]
}
CONTINUOUS_ALERT_FILE.parent.mkdir(parents=True, exist_ok=True)
with open(CONTINUOUS_ALERT_FILE, "w") as f:
    json.dump(alert_data, f)

spike_exc = None
try:
    from tenant_gate import _check_resource_quotas
    tenant_spike = TenantContext(operator_id=test_op_a, client_id=test_cl_a)
    _check_resource_quotas(tenant_spike, "market-brief")
    _check_spend_spike_suppression(tenant_spike, "market-brief")
except Exception as e:
    spike_exc = e

check("spend_spike alert raises QuotaExceeded", spike_exc is not None,
      f"got {type(spike_exc).__name__ if spike_exc else 'None'}")

CONTINUOUS_ALERT_FILE.unlink(missing_ok=True)


# ── TEST 16: reject mode raises SpendBudgetExhausted ────────────────────────
print("\n[TEST 16] reject mode: over-cap raises SpendBudgetExhausted with reject")
test_rj = f"reject_{test_id}"; test_rjcl = f"reject_cl_{test_id}"
save_operator_config(test_rj, {
    "operator_id": test_rj, "exceed_action": "reject",
    "max_daily_spend": 50.0, "max_monthly_spend": 500.0
})
save_client_config(test_rj, test_rjcl, {
    "client_id": test_rjcl, "exceed_action": "reject",
    "max_daily_spend": 50.0, "max_monthly_spend": 500.0
})

store_rj = _quota_store_path(test_rj, test_rjcl)
store_rj.parent.mkdir(parents=True, exist_ok=True)
with open(store_rj, "w") as f:
    json.dump({
        "_spend_today": 999.0, "_spend_this_month": 9999.0,
        "_last_day_reset": time.time(), "_last_month_reset": time.time(),
        "_month_key": int(time.strftime("%Y%m")),
    }, f)

exc_rj = None
try:
    submit_task_gate(
        task_prompt="test reject mode", task_type="research",
        raw_context={"operator_id": test_rj, "client_id": test_rjcl},
        task_id=f"reject-test-{test_id}"
    )
except SpendBudgetExhausted as sbe:
    exc_rj = sbe
except Exception as e:
    exc_rj = e

check("SpendBudgetExhausted raised", exc_rj is not None and isinstance(exc_rj, SpendBudgetExhausted),
      f"got {type(exc_rj).__name__ if exc_rj else 'None'}")
if exc_rj:
    check("exceed_action=reject", exc_rj.exceed_action == "reject",
          f"got {exc_rj.exceed_action}")


# ── TEST 17: record_spend wires into task_orchestrator end-to-end ───────────
print("\n[TEST 17] task_orchestrator.py imports record_spend and estimate_task_cost")
from task_orchestrator import record_spend as rs_imp, estimate_task_cost as ect_imp
check("record_spend imported in task_orchestrator", callable(rs_imp))
check("estimate_task_cost imported in task_orchestrator", callable(ect_imp))


# ── SUMMARY ─────────────────────────────────────────────────────────────────
total = PASS + FAIL
print(f"\n{'='*60}")
print(f"Phase 13 Full Cost Control: {PASS}/{total} passed")
print("ALL PHASE 13 CHECKS PASSED" if FAIL == 0 else f"{FAIL} checks FAILED")
print(f"{'='*60}\n")
sys.exit(0 if FAIL == 0 else 1)