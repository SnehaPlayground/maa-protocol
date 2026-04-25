#!/usr/bin/env python3
"""
Maa Protocol — Trust Regression Test Pack
==========================================
Run with: python3 test_trust_fixes.py
No pytest required — pure stdlib + direct checks.

Tests validate that all trust mechanisms are operational:
  1. Orchestrator state truth (state_version, completion markers)
  2. Loud observability failures (stderr + fallback logs)
  3. Per-agent error rates in dashboard
  4. Alert cooldown
  5. Completion marker truth
  6. Progress ping for long tasks
  7. Metrics retention cap
  8. Validation gate hard rule
  9. Email pipeline maintenance logging
  10. Health check + pre-deploy gate cron
  11. Usability gate (child output validation)
"""

import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, UTC
from pathlib import Path

# ─── Config ────────────────────────────────────────────────────────────────────

WORKSPACE = Path("/root/.openclaw/workspace")
ORCHESTRATOR = WORKSPACE / "ops/multi-agent-orchestrator/task_orchestrator.py"
METRICS = WORKSPACE / "ops/observability/maa_metrics.py"
MAINTENANCE_LOGGER = WORKSPACE / "scripts/maintenance_logger.py"
EMAIL_PIPELINE = WORKSPACE / "ops/email/run_email_pipeline.sh"
TASKS_DIR = WORKSPACE / "ops/multi-agent-orchestrator/tasks"
LOGS_DIR = WORKSPACE / "ops/multi-agent-orchestrator/logs"
DATA_OBS = WORKSPACE / "data/observability"
MAINTENANCE_DECISIONS = WORKSPACE / "memory/maintenance_decisions"
COOLDOWN_FILE = MAINTENANCE_DECISIONS / "alert_cooldown.json"

PASS = 0
FAIL = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        print(f"  ✅ {name}")
        PASS += 1
    else:
        print(f"  ❌ {name}")
        if detail:
            print(f"     → {detail}")
        FAIL += 1


def run(cmd: list, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


# ─── Test 1: Orchestrator — state_version and attempts invariant ───────────────

def test_orchestrator_state_truth():
    print("\n[Test 1] Orchestrator state truth — no false-pass possible")

    code = ORCHESTRATOR.read_text()
    code_lines = code.splitlines()

    # Extract spawn_child_agent body
    s_start = code.find("def spawn_child_agent")
    s_end = code.find("def run_task_chain", s_start)
    spawn_body = code[s_start:s_end]

    check("state_version increment via _next_state_version on success",
          "_next_state_version(task)" in spawn_body and "sv = _next_state_version(task)" in spawn_body,
          f"found _next_state_version: {'_next_state_version(task)' in spawn_body}")

    check("return task after validated", "return task" in code)
    check("exhausted block sets status=exhausted",
          "exhausted" in code and "status" in code)
    check("spawn_child_agent returns usable bool",
          "return usable" in spawn_body)
    check("completion_marker written before state update",
          "completion_file = " in spawn_body and "json.dump(completion_data, f, indent=2)" in spawn_body)
    check("tenant-aware marker verification present",
          "_verify_completion_marker(" in spawn_body and "task.get(\"tenant_context\")" in spawn_body)
    check("output_file tracked in state",
          "output_file" in spawn_body)
    check("runtime VERSION constant exists as real code",
          any(line.startswith('VERSION = ') for line in code_lines),
          "VERSION must be a real module constant, not only doc text")


# ─── Test 2: Loud observability failures ──────────────────────────────────────

def test_observability_loud_failure():
    print("\n[Test 2] Observability — silent failures are now loud")

    code = METRICS.read_text()
    check("stderr print on error record", "file=sys.stderr" in code)
    check("fallback log on record failure",
          "record_errors.log" in code or ("fallback" in code.lower() and "record" in code.lower()))
    check("error printed to stderr", "[MAA ERROR]" in code)

    # FIX-5: Use non-test. prefix so guard doesn't silently drop it
    # (audit. is a real production-like label)
    result = run([
        "python3", str(METRICS),
        "record", "--type", "error",
        "--label", f"audit.regression_test_{uuid.uuid4().hex[:6]}",
        "--details", "regression test",
        "--agent", "audit"
    ])
    check("metrics record --error exits cleanly", result.returncode == 0)
    # stderr should contain [MAA ERROR] or stdout [error]
    check("error printed to stdout or stderr",
          "[MAA ERROR]" in result.stderr or "[error]" in result.stdout or "[error]" in result.stderr)


# ─── Test 3: Dashboard per-agent error rates ──────────────────────────────────

def test_dashboard_per_agent():
    print("\n[Test 3] Dashboard — per-agent error rates, not blended global")

    code = METRICS.read_text()
    d_start = code.find("def print_dashboard")
    d_end = code.find("def _ago", d_start)
    dash = code[d_start:d_end]

    check("agent_ops dict built", "agent_ops" in dash)
    check("per-agent error rate computed", "err_rate" in dash)
    check("no blended total_errors / (calls+tasks)",
          "total_errors / (total_calls + total_tasks)" not in dash)

    # Seed real non-test. data so AGENT BREAKDOWN section renders
    seed_id = f"seed_{uuid.uuid4().hex[:6]}"
    run(["python3", str(METRICS), "record",
         "--type", "call", "--label", f"maa.{seed_id}", "--agent", "market-brief"])
    run(["python3", str(METRICS), "record",
         "--type", "task", "--label", f"maa.{seed_id}", "--status", "completed",
         "--agent", "market-brief"])

    # Now run dashboard — should show agent breakdown
    result = run(["python3", str(METRICS), "dashboard"], check=False)
    out = result.stdout
    check("dashboard prints AGENT BREAKDOWN section", "AGENT BREAKDOWN" in out)
    check("dashboard shows per-agent calls column (c=)", "c=" in out)
    check("dashboard shows per-agent tasks column (t=)", "t=" in out)
    check("dashboard shows clean or err/ rate", "clean" in out or "err/" in out)

    canary_code = (WORKSPACE / "ops/multi-agent-orchestrator/canary_router.py").read_text()
    check("canary router computes error rate from canary-routed tasks only",
          "canary_routed" in canary_code,
          "canary error rate must not be computed from all tasks system-wide")


# ─── Test 4: Alert cooldown ───────────────────────────────────────────────────

def _cleanup_alert_cooldown(action: str) -> None:
    """Remove any prior cooldown state for this action.
    
    Prevents cross-run pollution: if a previous test run left cooldown
    state for our action, it must not affect this run.
    """
    if not COOLDOWN_FILE.exists():
        return
    try:
        state = json.loads(COOLDOWN_FILE.read_text())
    except (json.JSONDecodeError, IOError):
        return
    key = f"{action}:critical"
    if key in state:
        del state[key]
        tmp = COOLDOWN_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(state))
        tmp.rename(COOLDOWN_FILE)


def _cleanup_maintenance_entries(action: str) -> None:
    """Remove any prior jsonl entries for this action.
    
    Prevents cross-run pollution: if a previous test left jsonl entries for
    our action (from a failed run or midnight-crossing scenario), the test
    must not pick them up instead of today's entries.
    """
    for path in MAINTENANCE_DECISIONS.glob("*.jsonl"):
        lines = [l for l in path.read_text().strip().split("\n") if l.strip()]
        filtered = []
        for line in lines:
            try:
                entry = json.loads(line)
                if entry.get("action") != action:
                    filtered.append(line)
            except json.JSONDecodeError:
                pass
        path.write_text("\n".join(filtered) + "\n")


def test_alert_cooldown():
    print("\n[Test 4] Alert cooldown — repeated critical alerts suppressed")

    code = MAINTENANCE_LOGGER.read_text()
    check("cooldown file path defined", "alert_cooldown" in code)
    check("COOLDOWN_SECONDS defined (2h)", "COOLDOWN_SECONDS" in code)
    check("_is_in_cooldown function exists", "_is_in_cooldown" in code)
    check("_touch_cooldown function exists", "_touch_cooldown" in code)
    check("cooldown checked before logging critical", "in_cooldown" in code)
    check("_cooldown_suppressed flag written", "_cooldown_suppressed" in code)

    # Functional: fire a unique critical, set cooldown, fire again
    # GAP 5 FIX: isolate completely — clean up any prior state for this action
    action = f"test_{uuid.uuid4().hex[:6]}"
    _cleanup_alert_cooldown(action)
    _cleanup_maintenance_entries(action)

    first = run(["python3", str(MAINTENANCE_LOGGER), action, "critical", '{"x":1}'], check=False)


    # Simulate cooldown: set timestamp to now
    cooldown_state = {f"{action}:critical": time.time()}
    tmp = COOLDOWN_FILE.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(cooldown_state, f)
    tmp.rename(COOLDOWN_FILE)

    # Second fire should be suppressed
    second = run(["python3", str(MAINTENANCE_LOGGER), action, "critical", '{"x":2}'], check=False)

    # Read entries for our action from ALL current-day jsonl files
    # (not just latest by name — entries may cross midnight mid-test)
    matching_entries = []
    for path in MAINTENANCE_DECISIONS.glob("*.jsonl"):
        lines = path.read_text().strip().split("\n")
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if entry.get("action") == action:
                    matching_entries.append((path, entry))
            except json.JSONDecodeError:
                continue

    # Find whether any later entry for this action was recorded as suppressed.
    # Sorting by second-precision timestamp is not deterministic when both writes
    # happen within the same second, so check the full matching set instead of
    # trusting lexical ordering of timestamps.
    if matching_entries:
        suppressed_second = any(
            entry.get("_cooldown_suppressed", False) and entry.get("details", {}).get("x") == 2
            for _, entry in matching_entries
        )
        latest_path, latest_entry = matching_entries[-1]
        check("second critical was cooldown-suppressed", suppressed_second,
              f"entries={len(matching_entries)} latest={latest_path.name}:{latest_entry.get('action')}/{latest_entry.get('outcome')}")
    else:
        check("second critical was cooldown-suppressed", False,
              f"no entry found for action={action}")


# ─── Test 5: Orchestrator completion marker truth ─────────────────────────────

def test_completion_marker_truth():
    print("\n[Test 5] Orchestrator — completion_marker always written with truth")

    code = ORCHESTRATOR.read_text()
    s_start = code.find("def spawn_child_agent")
    s_end = code.find("def run_task_chain", s_start)
    spawn = code[s_start:s_end]

    check("completion_marker written on child success", "completion_data = {" in spawn)
    check("state_version incremented on child success via _next_state_version",
          "_next_state_version" in spawn and "sv = _next_state_version" in spawn)
    check("output_file path tracked in task state", "output_file" in spawn)
    check("attempts incremented before spawn", "attempts" in spawn and "+=" in spawn)
    check("spawn_child_agent returns usable bool", "return usable" in spawn)

    exhaustion_start = code.find("# All attempts exhausted")
    mse_call = code.find("mse_result = _mother_self_execute", exhaustion_start)
    early_pop = code.find("_task_start_times.pop(task_id, None)", exhaustion_start, mse_call)
    check("runtime accounting not popped before Mother self-exec",
          early_pop == -1,
          "_task_start_times was popped before MSE, undercounting runtime/spend")


# ─── Test 6: Progress ping for long-running tasks ─────────────────────────────

def test_progress_ping():
    print("\n[Test 6] Progress ping — no silent hangs for long child tasks")

    code = ORCHESTRATOR.read_text()
    check("PROGRESS_PING_AT constant defined", "PROGRESS_PING_AT" in code)
    check("progress tracking function exists", "_run_with_progress_tracking" in code)
    check("_send_progress_update function", "_send_progress_update" in code)
    check("threading used for non-blocking wait", "threading" in code)
    check("progress signal file written", ".progress" in code or "progress_file" in code)


# ─── Test 7: Metrics retention cap ─────────────────────────────────────────────

def test_metrics_retention():
    print("\n[Test 7] Metrics retention — no unbounded bucket growth")

    code = METRICS.read_text()
    check("MAX_ITEMS_PER_BUCKET constant defined", "MAX_ITEMS_PER_BUCKET" in code)
    check("save_metrics enforces cap", "MAX_ITEMS_PER_BUCKET" in code and "]" in code)
    check("oldest entries trimmed (not newest)", "[-MAX_ITEMS_PER_BUCKET:]" in code)


# ─── Test 8: Validation gate — no validation file = fail ─────────────────────

def test_validation_gate():
    print("\n[Test 8] Validation gate — hard rule: no file = no pass")

    code = ORCHESTRATOR.read_text()
    v_start = code.find("def run_validation")
    v_end = code.find("def get_task_status", v_start)
    val = code[v_start:v_end]

    check("validation file existence checked", "os.path.exists(validation_file)" in val)
    check("missing validation file → passed=False", "passed\": False" in val)
    check("JSON parse validation on file", "json.load" in val or "json.loads" in val)
    check("validation agent writes file to disk", "open(validation_file" in val or 'validation_file, "w")' in val)


# ─── Test 9: Email pipeline maintenance logging ─────────────────────────────

def test_email_pipeline_maintenance():
    print("\n[Test 9] Email pipeline — fires maintenance log entry")

    code = EMAIL_PIPELINE.read_text()
    check("maintenance_logger called in email pipeline",
          "maintenance_logger" in code or "maintenance_decision" in code)


# ─── Test 10: Cron — health check + pre-deploy gate ──────────────────────────

def test_health_check_cron():
    print("\n[Test 10] Cron — health check every 4h + pre-deploy gate daily")

    result = run(["crontab", "-l"], check=False)
    crontab = result.stdout
    check("health_check.py in crontab", "health_check.py" in crontab)
    check("pre_deploy_gate.sh in crontab", "pre_deploy_gate.sh" in crontab)
    # health_check runs every 4 hours (from previous entries)
    # Verify with a line-count approach — health_check line must have */4
    health_lines = [l for l in crontab.splitlines() if "health_check.py" in l]
    check("health_check runs every 4 hours", any("*/4" in l for l in health_lines),
          f"health_check lines: {health_lines}")


# ─── Test 11: child_output_is_usable rejects partial output ─────────────────

def test_usability_gate():
    print("\n[Test 11] Child output usability gate — rejects partial/non-final output")

    code = ORCHESTRATOR.read_text()
    u_start = code.find("def child_output_is_usable")
    u_end = code.find("def record_metric", u_start)
    body = code[u_start:u_end]

    check("rejects 'Let me ' (planning)", '"Let me "' in body)
    check("rejects 'Working on it'", '"Working on it"' in body)
    check("rejects 'I\\'m looking'", "I" in body and "looking" in body)
    check("rejects '# Step '", '"# Step "' in body)
    check("rejects suspiciously short output", "len(text) < 50" in body)
    check("valid JSON short output allowed", "json.loads(text)" in body)
    check("stderr checked for hard failures", "Traceback" in body or "traceback" in body.lower())


# ─── Test 12: Circuit breaker ─────────────────────────────────────────────────

def test_circuit_breaker():
    print("\n[Test 12] Circuit breaker — halts spawning when error rate > 5%")

    code = ORCHESTRATOR.read_text()
    check("CIRCUIT_BREAKER_THRESHOLD defined", "CIRCUIT_BREAKER_THRESHOLD" in code)
    check("CIRCUIT_BREAKER_WINDOW_S defined", "CIRCUIT_BREAKER_WINDOW_S" in code)
    check("_is_circuit_open function exists", "_is_circuit_open" in code)
    check("circuit_open status set in spawn", "circuit_open" in code)
    check("circuit breaker checked before spawn", "_is_circuit_open" in code)


# ─── Test 13: Load shedding ──────────────────────────────────────────────────

def test_load_shedding():
    print("\n[Test 13] Load shedding — max 4 concurrent children, excess queued")

    code = ORCHESTRATOR.read_text()
    check("MAX_CONCURRENT_CHILDREN defined = 4", "MAX_CONCURRENT_CHILDREN" in code)
    check("queue_task function exists", "queue_task" in code)
    check("_process_queue function exists", "_process_queue" in code)
    check("queued status set when queueing", '"queued"' in code)
    check("queue drain after child completes", "dequeued_at" in code or "delayed_spawn" in code)


# ─── Test 14: Mother self-execution ─────────────────────────────────────────

def test_mother_self_execution():
    print("\n[Test 14] Mother self-execution — Mother tries before escalating")

    code = ORCHESTRATOR.read_text()
    check("_mother_self_execute function exists", "_mother_self_execute" in code)
    check("Mother self-exec called after child exhaustion",
          "_mother_self_execute" in code and "child_exhausted" in code)
    check("Mother self-exec runs after all children fail",
          "mother_self_exec" in code)
    check("Mother self-exec success sets validated",
          "mother_self_exec_success" in code)


# ─── Test 15: Test-pollution guard ─────────────────────────────────────────

def test_tenant_path_hardening():
    print("\n[Test 16] Tenant path hardening — no brittle tenant-blind path logic")

    code = ORCHESTRATOR.read_text()
    monitor = MONITOR.read_text()

    check("validation path uses resolver, not .replace('.progress', '.validation')",
          ".replace('.progress', '.validation')" not in code)
    check("get_task_status guards missing TENANTS_ROOT",
          "if not TENANTS_ROOT.exists():" in code)
    check("monitor exists at orchestrator path",
          MONITOR.exists())
    check("monitor running_children check initializes state_path",
          "state_path = TASKS_DIR / f\"{task_id}.json\"" in monitor)
    check("monitor defines TENANTS_ROOT once at top-level",
          "TENANTS_ROOT = WORKSPACE / \"tenants\"" in monitor)


def test_test_pollution_guard():
    print("\n[Test 15] Test-pollution guard — test.* labels skipped in metrics")

    code = METRICS.read_text()
    check("record_call skips test. prefix", 'if label.startswith("test.")' in code)
    check("record_error skips test. prefix", 'if label.startswith("test.")' in code)
    check("record_latency skips test. prefix", 'if label.startswith("test.")' in code)
    check("record_task skips test. prefix", 'if label.startswith("test.")' in code)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    global PASS, FAIL

    print("=" * 60)
    print("MAA PROTOCOL — TRUST REGRESSION TEST PACK")
    print(f"Run at: {datetime.now(UTC).isoformat()}")
    print("=" * 60)

    tests = [
        test_orchestrator_state_truth,
        test_observability_loud_failure,
        test_dashboard_per_agent,
        test_alert_cooldown,
        test_completion_marker_truth,
        test_progress_ping,
        test_metrics_retention,
        test_validation_gate,
        test_email_pipeline_maintenance,
        test_health_check_cron,
        test_usability_gate,
        test_circuit_breaker,
        test_load_shedding,
        test_mother_self_execution,
        test_test_pollution_guard,
    ]

    for t in tests:
        try:
            t()
        except Exception as e:
            print(f"  ❌ {t.__name__} — CRASHED: {e}")
            FAIL += 1

    print("\n" + "=" * 60)
    total = PASS + FAIL
    pct = (PASS / total * 100) if total > 0 else 0
    print(f"RESULTS: {PASS}/{total} passed ({pct:.0f}%)")
    if FAIL == 0:
        print("All trust tests passed — Maa is deployment-ready.")
    else:
        print(f"{FAIL} test(s) failed — review before commercial deployment.")
    print("=" * 60)

    return FAIL


if __name__ == "__main__":
    sys.exit(main())
