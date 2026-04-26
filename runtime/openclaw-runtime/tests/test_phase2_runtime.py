#!/usr/bin/env python3
"""
Phase 2 Runtime Harness Enforcement — Regression Tests
Tests for: harness spec verification, progress file enforcement, loop detection
runtime enforcement, reflection file writing, and template loading.

Run: python3 ops/multi-agent-orchestrator/tests/test_phase2_runtime.py
"""
import json, os, sys, tempfile

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir("/root/.openclaw/workspace")

WORKSPACE = "/root/.openclaw/workspace"
TASKS_DIR = f"{WORKSPACE}/ops/multi-agent-orchestrator/tasks"
LOGS_DIR = f"{WORKSPACE}/ops/multi-agent-orchestrator/logs"
os.makedirs(TASKS_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

# Import the functions we need to test
from task_orchestrator import (
    _verify_harness_spec,
    child_output_is_usable,
    _detect_loop,
    load_template,
    write_progress_report,
    _next_state_version,
    HARNESS_SPEC_MIN_FIELDS,
)

PASS = 0
FAIL = 0

def check(name, condition, details=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS: {name}")
    else:
        FAIL += 1
        print(f"  FAIL: {name}" + (f" — {details}" if details else ""))

def test_verify_harness_spec():
    print("\n[P2.1] Harness Spec Verification")
    
    # Valid harness
    valid = {
        "harness_version": "1.0",
        "active_pillars": ["P1", "P2", "P4"],
        "verification_gates": ["gate1", "gate2", "gate3", "gate4", "gate5"],
        "dynamic_reminders": [],
    }
    ok, reason = _verify_harness_spec(valid, "test-1")
    check("valid harness passes", ok, reason)
    
    # Missing harness_version
    no_ver = {k: v for k, v in valid.items() if k != "harness_version"}
    ok, reason = _verify_harness_spec(no_ver, "test-2")
    check("missing harness_version fails", not ok)
    
    # Empty active_pillars
    empty_pillars = {k: v for k, v in valid.items() if k != "active_pillars"}
    empty_pillars["active_pillars"] = []
    ok, reason = _verify_harness_spec(empty_pillars, "test-3")
    check("empty active_pillars fails", not ok)
    
    # Less than 5 gates
    four_gates = {k: v for k, v in valid.items() if k != "verification_gates"}
    four_gates["verification_gates"] = ["g1","g2","g3","g4"]
    ok, reason = _verify_harness_spec(four_gates, "test-4")
    check("4 gates (need 5) fails", not ok)
    
    # dynamic_reminders is None
    no_dr = {k: v for k, v in valid.items() if k != "dynamic_reminders"}
    no_dr["dynamic_reminders"] = None
    ok, reason = _verify_harness_spec(no_dr, "test-5")
    check("dynamic_reminders=None fails", not ok)
    
    # None harness
    ok, reason = _verify_harness_spec(None, "test-6")
    check("None harness fails", not ok)


def test_child_output_is_usable():
    print("\n[P2.2] Child Output Usability")
    
    # Valid long text
    ok, reason = child_output_is_usable("A" * 300, "")
    check("long text (300 chars) passes", ok)
    
    # Short non-JSON (< 200 chars)
    ok, reason = child_output_is_usable("short", "")
    check("short non-JSON (<200 chars) fails", not ok, reason)
    
    # Short but valid JSON
    ok, reason = child_output_is_usable("{}", "")
    check("short valid JSON passes", ok)
    
    # Stderr traceback
    ok, reason = child_output_is_usable("some output", "Traceback (most recent call last)")
    check("stderr traceback fails", not ok, reason)
    
    # Blocked marker
    ok, reason = child_output_is_usable("Let me think about this...", "")
    check("blocked marker 'Let me' fails", not ok, reason)
    
    # Empty output
    ok, reason = child_output_is_usable("", "")
    check("empty output fails", not ok)


def test_detect_loop():
    print("\n[P2.3] Loop Detection Runtime Enforcement")
    
    # No history
    no_hist = {"attempt_history": []}
    is_loop, reason, count = _detect_loop(no_hist)
    check("no history = no loop", not is_loop)
    
    # Only 1 attempt
    one_hist = {"attempt_history": [{"child_failure_reason": "timeout"}]}
    is_loop, reason, count = _detect_loop(one_hist)
    check("1 attempt = no loop", not is_loop)
    
    # Same failure mode 2x
    same_hist = {
        "attempt_history": [
            {"child_failure_reason": "timeout"},
            {"child_failure_reason": "timeout"},
        ],
        "loop_count": 0,
    }
    is_loop, reason, count = _detect_loop(same_hist)
    check("same failure 2x = loop detected", is_loop)
    check("loop_count incremented to 1", count == 1)
    
    # Different failure modes
    diff_hist = {
        "attempt_history": [
            {"child_failure_reason": "timeout"},
            {"child_failure_reason": "spawn_error"},
        ]
    }
    is_loop, reason, count = _detect_loop(diff_hist)
    check("different failures = no loop", not is_loop)


def test_load_template():
    print("\n[P2.4] Template Loading")
    
    # Templates dir should exist once Phase 1 is done
    templates_dir = f"{WORKSPACE}/agents/templates"
    
    template_types = ["researcher", "executor", "coder", "verifier", "communicator"]
    for tt in template_types:
        path = f"{templates_dir}/{tt}/v1.0.md"
        check(f"template file exists: {tt}/v1.0.md", os.path.exists(path))
    
    # Load all 5
    for task_type in ["market-brief", "research", "email-draft", "growth-report", "validation"]:
        content = load_template(task_type)
        # Template may or may not exist yet (Phase 1 may still be running)
        # But if it exists, it should be non-empty
        if content is not None:
            check(f"load_template({task_type}) returns non-empty", len(content) > 100)
        else:
            print(f"  INFO: template for {task_type} not yet created (Phase 1 still running)")


def test_write_progress_report():
    print("\n[P2.5] Progress Report File Writing")
    import uuid
    task_id = f"test-{uuid.uuid4().hex[:8]}"
    pf = f"{LOGS_DIR}/{task_id}.progress"
    if os.path.exists(pf):
        os.remove(pf)
    
    write_progress_report(task_id, "test-agent", "start", 0,
                         "test action", blockers="", next_step="running")
    
    check("progress file created", os.path.exists(pf))
    if os.path.exists(pf):
        with open(pf) as f:
            data = json.load(f)
        check("progress has task_id", data.get("task_id") == task_id)
        check("progress has checkpoint", data.get("checkpoint") == "start")
        check("progress has harness_reminders_active", "harness_reminders_active" in data)
        os.remove(pf)
    else:
        check("progress has task_id", False, "file not created")
        check("progress has checkpoint", False, "file not created")


def test_reflection_file_writing():
    print("\n[P2.6] Reflection File Writing")
    import uuid
    from task_orchestrator import _run_reflection
    
    # Create a minimal task state
    task_id = f"test-{uuid.uuid4().hex[:8]}"
    state_file = f"{TASKS_DIR}/{task_id}.json"
    with open(state_file, "w") as f:
        json.dump({
            "task_id": task_id,
            "task_type": "research",
            "status": "running",
        }, f)
    
    reflection_file = f"{LOGS_DIR}/{task_id}.reflection"
    if os.path.exists(reflection_file):
        os.remove(reflection_file)
    
    result = _run_reflection(task_id, {"issues": ["test issue"]}, 1)
    
    check("reflection returned dict", isinstance(result, dict))
    check("reflection has failed_gate", "failed_gate" in result)
    check("reflection has correction_directive", "correction_directive" in result)
    check("reflection file created", os.path.exists(reflection_file))
    
    if os.path.exists(reflection_file):
        with open(reflection_file) as f:
            rf = json.load(f)
        check("reflection file has at", "at" in rf)
        check("reflection file has attempt", "attempt" in rf)
        os.remove(reflection_file)
    else:
        for check_name in ["reflection file has at", "reflection file has attempt"]:
            check(check_name, False, "file not created")
    
    os.remove(state_file)


def test_min_content_threshold():
    print("\n[P2.7] Minimum Content Threshold (50 chars — Phase 4)")
    
    # Exactly 49 chars — should fail (below 50-char threshold)
    text_49 = "X" * 49
    ok, reason = child_output_is_usable(text_49, "")
    check("49 chars fails (below 50 threshold)", not ok)
    
    # Exactly 50 chars — should pass (at threshold)
    text_50 = "X" * 50
    ok, reason = child_output_is_usable(text_50, "")
    check("50 chars passes (at threshold)", ok)
    
    # Valid JSON at 14 chars — should pass regardless of threshold
    json_14 = '{"key": "value"}'
    ok, reason = child_output_is_usable(json_14, "")
    check("short valid JSON (14 chars) passes regardless of threshold", ok)
    
    # 199 chars — should pass (well above 50-char Phase 4 threshold)
    text_199 = "X" * 199
    ok, reason = child_output_is_usable(text_199, "")
    check("199 chars passes (Phase 4 threshold is 50)", ok)


def test_next_state_version():
    print("\n[P2.8] State Version Monotonicity")
    
    task = {"state_version": 0}
    task["state_version"] = _next_state_version(task)
    v1 = task["state_version"]
    task["state_version"] = _next_state_version(task)
    v2 = task["state_version"]
    task["state_version"] = _next_state_version(task)
    v3 = task["state_version"]
    check("state_version increments 1,2,3", v1 == 1 and v2 == 2 and v3 == 3)
    
    # Non-int current
    task2 = {"state_version": "not_a_number"}
    v1b = _next_state_version(task2)
    check("non-int state_version treated as 0", v1b == 1)


def main():
    print("=" * 60)
    print("MAA PHASE 2 RUNTIME ENFORCEMENT — REGRESSION TESTS")
    print("=" * 60)
    
    test_verify_harness_spec()
    test_child_output_is_usable()
    test_detect_loop()
    test_load_template()
    test_write_progress_report()
    test_reflection_file_writing()
    test_min_content_threshold()
    test_next_state_version()
    
    print("\n" + "=" * 60)
    print(f"SUMMARY: {PASS} passed, {FAIL} failed")
    print("=" * 60)
    return FAIL == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
