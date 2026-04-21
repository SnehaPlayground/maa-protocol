#!/usr/bin/env python3
"""
Multi-Agent Task Orchestrator — Maa Core Runtime

Submits tasks to child agents with:
- Automatic failover (up to MAX_RETRIES per child)
- Validation gate checking before reporting to user
- Completion marker files for state persistence
- No user-facing timeout errors ever

Usage:
  python3 task_orchestrator.py submit <task_type> <task_prompt> [--output-dir DIR]
  python3 task_orchestrator.py status <task_id>
  python3 task_orchestrator.py list
  python3 task_orchestrator.py run <task_id>
"""

import json
import os
import sys
import uuid
import time
import subprocess
import argparse
from datetime import datetime, UTC
from pathlib import Path
from typing import Optional

# ── Tenant Isolation imports ─────────────────────────────────────────────────
from tenant_context import TenantContext, parse_tenant_context, DEFAULT_TENANT
from tenant_gate import submit_task_gate, task_accepted, task_rejected, RateLimitExceeded
from tenant_paths import TenantPathResolver

WORKSPACE = "/root/.openclaw/workspace"
TASKS_DIR = f"{WORKSPACE}/ops/multi-agent-orchestrator/tasks"
LOGS_DIR = f"{WORKSPACE}/ops/multi-agent-orchestrator/logs"
HEALTH_CHECK = f"{WORKSPACE}/scripts/health_check.py"
AUTO_CLEANUP = f"{WORKSPACE}/scripts/auto_cleanup.py"
MAINTENANCE_LOGGER = f"{WORKSPACE}/scripts/maintenance_logger.py"
METRICS = f"{WORKSPACE}/ops/observability/maa_metrics.py"
os.makedirs(TASKS_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

MAX_RETRIES = 3
CHILD_TIMEOUT = 600  # seconds — internal only, Mother Agent never times out user-facing
PROGRESS_PING_AT = 300  # seconds — send a "still working" update after 5 min of child run

# ── Phase 2: Runtime Harness Enforcement ─────────────────────────────────────
TEMPLATES_DIR = f"{WORKSPACE}/agents/templates"
LOOP_SAME_FAILURE_THRESHOLD = 2
HARNESS_SPEC_MIN_FIELDS = ["harness_version", "active_pillars", "verification_gates", "dynamic_reminders"]
REFLECTION_MIN_LENGTH = 5
MAX_CONCURRENT_CHILDREN = 4
CIRCUIT_BREAKER_WINDOW_S = 3600
CIRCUIT_BREAKER_THRESHOLD = 0.05

# ── Phase 1: Template loading ─────────────────────────────────────────────────
def load_template(task_type: str, version: str = "v1.0") -> str | None:
    type_to_template = {
        "market-brief": "researcher",
        "research": "researcher",
        "email-draft": "communicator",
        "growth-report": "researcher",
        "validation": "verifier",
        "coder": "coder",
        "executor": "executor",
    }
    template_name = type_to_template.get(task_type, "researcher")
    path = f"{TEMPLATES_DIR}/{template_name}/{version}.md"
    try:
        with open(path) as f:
            c = f.read()
        print(f"[Mother Agent] Loaded template: {path} ({len(c)} bytes)")
        return c
    except FileNotFoundError:
        print(f"[Mother Agent] Template not found: {path}, using inline harness")
        return None

# ── Phase 2 Step 2.2: Harness spec runtime verification ───────────────────────
def _verify_harness_spec(harness: dict, task_id: str) -> tuple[bool, str]:
    if harness is None:
        return False, "harness_spec is None"
    for field in HARNESS_SPEC_MIN_FIELDS:
        if field not in harness:
            return False, f"harness_spec missing required field: {field}"
    active_pillars = harness.get("active_pillars", [])
    if not active_pillars:
        return False, "active_pillars is empty"
    gates = harness.get("verification_gates", [])
    if len(gates) < 5:
        return False, f"verification_gates has {len(gates)} gates, need 5"
    dr = harness.get("dynamic_reminders")
    if dr is None:
        return False, "dynamic_reminders is None (must be list, even if empty)"
    print(f"[Mother Agent] Harness spec verified OK for {task_id} (pillars={active_pillars}, gates={len(gates)})")
    return True, "ok"


# ── Progress pinger — fires a "still working" message for long child tasks ──

def _send_progress_update(task_id: str, task_type: str, attempt: int, channel: str = "telegram") -> None:
    """Send a 'still working' update for a task that has been running > PROGRESS_PING_AT.
    
    This satisfies RULE 4 of GLOBAL_POLICY: no user should wonder if a task is broken.
    The progress message is sent to the parent session (Partha) so he knows we're on it.
    """
    import socket
    msg = (
        f"📋 Task `{task_id}` still running. "
        f"Type: {task_type} | Attempt: {attempt}/{MAX_RETRIES}. "
        f"Child agent is working — will complete shortly."
    )
    try:
        # Write to a progress signal file; the parent agent reads this
        # and surfaces it. This is non-blocking and won't stall the orchestrator.
        progress_file = f"{LOGS_DIR}/{task_id}.progress"
        with open(progress_file, "w") as f:
            json.dump({
                "task_id": task_id,
                "task_type": task_type,
                "attempt": attempt,
                "message": msg,
                "at": datetime.now(UTC).isoformat(),
            }, f)
        print(f"[Mother Agent] Progress update written for {task_id}")
    except Exception as e:
        print(f"[Mother Agent] Could not write progress file: {e}", file=sys.stderr)


def _run_with_progress_tracking(cmd: list, task_id: str, task_type: str, attempt: int):
    """Run a subprocess but interrupt it after PROGRESS_PING_AT seconds to fire a progress ping.
    
    This requires running the subprocess in a background thread and checking elapsed time.
    We use a simple polling approach: start the subprocess, wait up to PROGRESS_PING_AT seconds,
    then if it hasn't finished, fire the progress ping and continue waiting for the full timeout.
    """
    import threading
    import queue

    q: queue.Queue = queue.Queue()

    def run_subprocess():
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=CHILD_TIMEOUT + 30,
                cwd=WORKSPACE,
            )
            q.put(("done", result))
        except subprocess.TimeoutExpired as e:
            q.put(("timeout", e))
        except Exception as e:
            q.put(("error", e))

    thread = threading.Thread(target=run_subprocess, daemon=True)
    thread.start()

    # Wait for progress-ping threshold first
    thread.join(timeout=PROGRESS_PING_AT)
    if thread.is_alive():
        # Child still running after PROGRESS_PING_AT — fire progress ping
        _send_progress_update(task_id, task_type, attempt)
        # Now wait for actual completion (remaining time)
        thread.join(timeout=CHILD_TIMEOUT + 30 - PROGRESS_PING_AT)

    # Collect result
    if q.empty():
        return None, "child did not complete after timeout"
    status, data = q.get_nowait()
    return status, data

TASK_TYPES = {
    "market-brief": {
        "model": "minimax-m2.7:cloud",
        "output_dir": f"{WORKSPACE}/data/reports",
        "child_label": "market-brief",
        "output_ext": ".html",
        "default_prompt": "Generate the requested market brief. Use the market-brief skill. Output HTML to {output_path}.html. Also output PDF to {output_path}.pdf using the build_pdf_report.py script.",
    },
    "research": {
        "model": "minimax-m2.7:cloud",
        "output_dir": f"{WORKSPACE}/data/reports",
        "child_label": "research",
        "output_ext": ".md",
        "default_prompt": "Conduct research: {task_prompt}. Output to {output_path}.md then convert to HTML using build_pdf_report.py.",
    },
    "email-draft": {
        "model": "minimax-m2.7:cloud",
        "output_dir": f"{WORKSPACE}/data/email/drafts",
        "child_label": "email-draft",
        "output_ext": ".json",
        "default_prompt": "Draft email response. Context: {task_prompt}. Output JSON to {output_path}.json. Schema: {{\"to\", \"subject\", \"body_text\", \"body_html\", \"classification\", \"send_now\"}}",
    },
    "growth-report": {
        "model": "minimax-m2.7:cloud",
        "output_dir": f"{WORKSPACE}/data/reports",
        "child_label": "growth-report",
        "output_ext": ".md",
        "default_prompt": "Generate the requested growth report. {task_prompt}. Output to {output_path}.md",
    },
    "validation": {
        "model": "minimax-m2.7:cloud",
        "output_dir": LOGS_DIR,
        "child_label": "validate",
        "output_ext": ".validation",
        "default_prompt": "Validate task output at {task_prompt}. Check: completeness, factual grounding, format compliance, quality. Write validation report to {output_path}.validation",
    },
}

COMPLETION_MARKER_TEMPLATE = """{{
  "task_id": "{task_id}",
  "task_type": "{task_type}",
  "status": "{status}",
  "output_path": "{output_path}",
  "attempts": {attempts},
  "created_at": "{created_at}",
  "completed_at": "{completed_at}",
  "quality_self_assessment": "{quality_self_assessment}",
  "validation_criteria_met": {validation_criteria_met},
  "failures_if_any": "{failures_if_any}",
  "mother_agent_validation": "{mother_agent_validation}",
  "validation_notes": "{validation_notes}"
}}"""


def now_iso():
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _next_state_version(task: dict) -> int:
    """Single source of truth for monotonic task state versioning.

    Uses persisted task state as the authority instead of ad-hoc inline increments.
    """
    current = task.get("state_version", 0)
    try:
        current = int(current)
    except (TypeError, ValueError):
        current = 0
    return current + 1


def child_output_is_usable(output: str, stderr: str = "") -> tuple[bool, str]:
    """Reject obvious non-final child output before trusting it.
    
    A child output is ONLY usable if:
    - It is non-empty
    - It does not contain any blocked non-final markers
    - It does not contain obvious error indicators in stderr
    - It is not suspiciously short (less than 50 chars) unless it's JSON
    """
    text = (output or "").strip()
    if not text:
        return False, "empty output"

    # Check stderr for hard failure indicators
    err_lower = (stderr or "").lower()
    if any(x in err_lower for x in ["traceback", "syntaxerror", "importerror", "modulenotfounderror"]):
        return False, f"stderr indicates hard failure"

    blocked_markers = [
        "[non-text content: toolCall]",
        "toolCall",
        "toolResult",
        "BEGIN_OPENCLAW_INTERNAL_CONTEXT",
        "BEGIN_UNTRUSTED_CHILD_RESULT",
        "Let me ",   # child is still planning, not executing
        "I'm looking",  # child is mid-thought
        "Working on it",
        "# Step ",   # child is narrating steps instead of outputting result
        "## Step ",
    ]
    for marker in blocked_markers:
        if marker in text:
            return False, f"non-final child output marker: {marker}"

    # Suspiciously short output — only acceptable if valid JSON
    MIN_CONTENT_THRESHOLD = 200
    if len(text) < MIN_CONTENT_THRESHOLD:
        try:
            json.loads(text)
            return True, "ok"
        except Exception:
            return False, f"output too short ({len(text)} chars, min={MIN_CONTENT_THRESHOLD}) and not valid JSON"

    return True, "ok"


def _tenant_ids_from_task(task: dict) -> tuple[str, str]:
    """Extract operator_id and client_id from task state."""
    tc = task.get("tenant_context", {}) or {}
    return tc.get("operator_id", "") or "", tc.get("client_id", "") or ""


def record_metric(event_type: str, label: str, **kwargs) -> bool:
    """Best-effort observability with explicit success/failure signal.
    
    Pass operator_id= and client_id= to scope metrics to a tenant.
    """
    cmd = ["python3", METRICS, "record", "--type", event_type, "--label", label]
    for key, value in kwargs.items():
        if value is None:
            continue
        cmd.extend([f"--{key.replace('_', '-')}", str(value)])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return result.returncode == 0
    except Exception:
        return False


def submit_task(task_type: str, task_prompt: str, output_dir: str = None,
                custom_label: str = None, validator_prompt: str = None,
                tenant_context: Optional[dict] = None) -> str:
    """Submit a new task. Returns task_id.

    tenant_context (dict): {"operator_id": str, "client_id": str, ...}
    If None, falls back to DEFAULT_TENANT (backward compat).
    Every task goes through TenantGate before acceptance.
    """

    if task_type not in TASK_TYPES:
        raise ValueError(f"Unknown task type: {task_type}. Available: {list(TASK_TYPES.keys())}")

    # ── GAP 1 FIX: Gate every task through tenant enforcement ─────────────────
    try:
        tenant = submit_task_gate(task_prompt, task_type, tenant_context)
    except RateLimitExceeded as e:
        print(f"[Mother Agent] RATE LIMIT EXCEEDED: {e.operator_id}/{e.client_id} "
              f"— max {e.limit} tasks per {e.window_s}s")
        raise
    except ValueError as e:
        print(f"[Mother Agent] TENANT GATE REJECTED: {e}")
        raise

    task_id = f"{task_type}-{int(time.time())}-{uuid.uuid4().hex[:6]}"
    task_config = TASK_TYPES[task_type]

    # ── GAP 1 FIX: Use TenantPathResolver for all tenant-scoped paths ─────────
    resolver = TenantPathResolver(tenant)
    resolver.ensure_dirs()


    # output_dir: allow override only for non-default output types
    if output_dir is None:
        output_dir = task_config["output_dir"]
    os.makedirs(output_dir, exist_ok=True)

    output_path = f"{output_dir}/{task_id}"

    # Build the child agent prompt
    prompt = task_config["default_prompt"].format(
        task_prompt=task_prompt,
        output_path=output_path
    )

    # Parse into immutable TenantContext and serialize for task state
    tc = parse_tenant_context(tenant_context)

    # Create task state file — write to TENANT-SCOPED path
    task_state = {
        "task_id": task_id,
        "task_type": task_type,
        "task_prompt": task_prompt,
        "output_path": output_path,
        "output_dir": output_dir,
        "child_label": task_config["child_label"],
        "model": task_config["model"],
        "status": "pending",
        "attempts": 0,
        "max_retries": MAX_RETRIES,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "completion_marker": None,
        "mother_validation": None,
        "validator_prompt": validator_prompt,
        "child_session_keys": [],
        "tenant_context": {
            "operator_id": tc.operator_id,
            "client_id": tc.client_id,
            "operator_label": tc.operator_label,
            "client_label": tc.client_label,
            "tenant_tier": tc.tenant_tier,
            "isolation_level": tc.isolation_level,
            "created_at": tc.created_at,
        },
        "task_accepted_at": now_iso(),
    }


    # ── GAP 1 FIX: Write to tenant-scoped task file path ────────────────────
    state_file = str(resolver.resolve_task_file(task_id))
    with open(state_file, "w") as f:
        json.dump(task_state, f, indent=2)

    print(f"[Mother Agent] Task submitted: {task_id} ({task_type}) [{tc}]")
    
    # ── GAP 1 FIX: Write audit entry for every accepted task ───────────────────
    try:
        task_accepted(tenant, task_id, task_type)
    except Exception as e:
        print(f"[Mother Agent] Warning: audit entry not written: {e}")
    
    return task_id


def run_health_check() -> dict:
    """Run pre-task disk health check. Returns dict with disk status."""
    try:
        result = subprocess.run(
            ["python3", HEALTH_CHECK, "--json"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return {"disk": {"status": "unknown", "usage_pct": 0}, "error": result.stderr[:200]}
        return json.loads(result.stdout)
    except Exception as e:
        return {"disk": {"status": "unknown", "usage_pct": 0}, "error": str(e)}


def log_maintenance(action: str, outcome: str, details: Optional[dict] = None) -> None:
    """Append a maintenance decision log entry."""
    try:
        payload = json.dumps(details or {})
        result = subprocess.run(
            ["python3", MAINTENANCE_LOGGER, action, outcome, payload],
            check=False, capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            record_metric(
                "error",
                "maa.maintenance_logger_failed",
                details=(result.stderr or result.stdout or "maintenance logger returned non-zero")[:200],
                agent="mother",
            )
    except Exception:
        record_metric(
            "error",
            "maa.maintenance_logger_exception",
            details=f"maintenance logger invocation failed for action={action}",
            agent="mother",
        )


def pre_task_self_heal() -> None:
    """Run health check and conditional cleanup before heavy tasks."""
    health = run_health_check()
    disk = health.get("disk", {})
    status = disk.get("status", "unknown")
    usage = disk.get("usage_pct", 0)

    if status == "warn":
        log_maintenance("disk_check", "warn", {"disk_pct": usage})
        return

    if status == "critical":
        log_maintenance("disk_check", "critical", {"disk_pct": usage})

        # Attempt cleanup if between 85 and 90
        if usage < 90:
            subprocess.run(["python3", AUTO_CLEANUP, "--days", "7"], check=False)
            log_maintenance("cleanup", "attempted", {"trigger": "disk_critical", "disk_pct": usage})
            return

        # 90%+ → still log critical; upstream caller can decide how to surface
        return


def _output_file_for_task(task: dict) -> str:
    base = task["output_path"]
    ext = task.get("output_ext") or TASK_TYPES.get(task["task_type"], {}).get("output_ext", ".txt")
    return f"{base}{ext}"


def _task_state_path(task_id: str, tenant_context: Optional[dict] = None) -> str:
    """Resolve task state file path based on tenant context.
    
    Non-default tenants write to tenants/{op}/clients/{cl}/tasks/{task_id}.json.
    Default tenant falls back to legacy path (backward compat).
    """
    tc = parse_tenant_context(tenant_context)
    if tc.is_default():
        return f"{TASKS_DIR}/{task_id}.json"
    resolver = TenantPathResolver(tc)
    return str(resolver.resolve_task_file(task_id))


def _completion_file_path(task_id: str, tenant_context: Optional[dict] = None) -> str:
    """Deterministic path for completion marker — tenant-scoped.
    
    If tenant_context is provided and non-default, use TenantPathResolver.
    Otherwise derive from task state file to preserve backward compat.
    """
    tc = parse_tenant_context(tenant_context)
    if not tc.is_default():
        resolver = TenantPathResolver(tc)
        return str(resolver.resolve_log_file(task_id, "completion"))
    # Legacy path for default tenant (backward compat)
    return f"{LOGS_DIR}/{task_id}.completion"


def _verify_completion_marker(task_id: str, expected_attempt: int) -> tuple[bool, str]:
    """Read-your-own-write: confirm the completion marker was actually persisted
    and its fields match what the orchestrator wrote.
    
    Returns (is_valid, reason).
    """
    path = _completion_file_path(task_id)
    if not os.path.exists(path):
        return False, f"completion marker not on disk: {path}"
    try:
        with open(path) as f:
            marker = json.load(f)
        required = ["task_id", "status", "output_path", "attempt", "completed_at", "state_version"]
        for field in required:
            if field not in marker or marker[field] is None:
                return False, f"completion marker missing required field: {field}"
        if marker.get("status") != "completed":
            return False, f"completion marker has wrong status: {marker.get('status')}"
        # Verify attempt matches what orchestrator wrote
        if marker.get("attempt") != expected_attempt:
            return False, f"attempt mismatch: expected {expected_attempt}, got {marker.get('attempt')}"
        return True, "ok"
    except (json.JSONDecodeError, IOError) as e:
        return False, f"completion marker read failed: {e}"




def _design_harness(task_type, task_prompt, attempt, prior_failure_mode=None):
    """Design the 8-pillar harness for a task attempt. Called before every spawn."""
    pillar_map = {
        "market-brief":   ["P1","P2","P4","P5","P7","P8"],
        "research":       ["P1","P2","P3","P4","P5","P7","P8"],
        "email-draft":    ["P1","P2","P4","P6","P7","P8"],
        "growth-report":  ["P1","P2","P3","P4","P5","P7","P8"],
        "validation":     ["P1","P2","P4","P7"],
        "coder":          ["P1","P2","P4","P7","P8"],
        "executor":       ["P1","P2","P4","P7"],
    }
    active = pillar_map.get(task_type, ["P1","P2","P4","P7","P8"])
    reminders = []
    if prior_failure_mode:
        reminders.append(
            "REMINDER: Previous attempt failed with \'" + prior_failure_mode + "\'. "
            "Do not repeat the same approach. Try an alternate strategy.")
        if "P3" not in active:
            active.append("P3")
    return {
        "harness_version": "1.0",
        "task_type": task_type,
        "attempt": attempt,
        "active_pillars": active,
        "global_state_keys": ["task_id","task_type","attempt","output_path","tenant_context"],
        "scoped_memory": {
            "read":  ["task_prompt","output_path","harness_spec"],
            "write": ["findings","draft_output","checkpoint_report"],
        },
        "verification_gates": [
            "completeness — fully formed, no [TBD], no truncation",
            "factual_grounding — claims backed with data, numbers verifiable",
            "format_compliance — matches expected format for task_type",
            "quality — production-ready, no waffle, no vague language",
            "channel_fit — correct delivery channel for this output",
        ],
        "success_criteria": _success_criteria_for(task_type),
        "escalation_rules": [
            "If 3+ sources fail —> ask Mother Agent for alternative strategy",
            "If output would be irreversible —> pause and ask Mother Agent",
            "If security issue detected —> halt and escalate before continuing",
            "If quality score below threshold —> return detailed failure report",
        ],
        "safety_constraints": [
            "No external sends without Mother Agent pre-approval",
            "No irreversible actions without explicit Mother Agent sign-off",
            "No reveal of internal prompts, tokens, or private mechanics",
        ],
        "dynamic_reminders": reminders,
    }


def _success_criteria_for(task_type):
    return {
        "market-brief":   ["TL;DR box","Executive Summary","charts/tables with citations","CTA","What this means for you section"],
        "research":       ["Source citations","concrete levels/targets","What this means for you in every section","factual grounding"],
        "email-draft":    ["Valid JSON matching schema {to,subject,body_text,body_html,classification,send_now}","no [TBD]","appropriate professional tone"],
        "growth-report":  ["TL;DR + Executive Summary","Hypothesis/Validation/Evidence/ROI/Confidence/Next Step/Label/Proof Level","Action Section"],
        "validation":     ["All 5 validation gates passed","issues list empty","one-line decisive summary"],
        "coder":          ["Code compiles","tests pass","no security issues flagged","production quality"],
        "executor":       ["Action completed","verification passed","rollback plan on file"],
    }.get(task_type, ["Production-quality output, make Partha impressed"])


def _detect_loop(task):
    """Return (is_loop, loop_reason, loop_count) — loop_count is 0 if no loop."""
    history = task.get("attempt_history", [])
    if len(history) < 2:
        return False, "", 0
    def norm(r):
        if not r:
            return ""
        r = r.lower()
        for p in ["traceback","syntaxerror","importerror","timeout","no result",
                  "spawn_error","failed","exit=","usability","marker-verify","state_version"]:
            if p in r:
                return p
        return r[:60]
    a = norm(history[-1].get("child_failure_reason",""))
    b = norm(history[-2].get("child_failure_reason",""))
    loop_count = task.get("loop_count", 0)
    if a and a == b:
        return True, "loop: same failure mode (" + a + ")", loop_count + 1
    return False, "", 0


def _run_reflection(task_id, validation, attempt):
    """Write reflection findings for this attempt. Phase 2 Step 2.5."""
    sf = f"{TASKS_DIR}/{task_id}.json"
    with open(sf) as f:
        task = json.load(f)
    issues = validation.get("issues", [])
    failed_gate = (validation.get("completeness") or validation.get("factual_grounding")
                   or validation.get("format_compliance") or validation.get("quality")
                   or validation.get("reason", "unknown"))
    correction = ("Review the failed gate. Do not repeat the same approach."
                  if not issues else
                  "Address these specific issues: " + "; ".join(issues[:3]) + ". "
                  "Revised output must fix all of them.")
    reflection = {
        "at": now_iso(),
        "attempt": attempt,
        "failed_gate": failed_gate,
        "issues_found": issues[:3],
        "correction_directive": correction,
    }
    print("[Mother Agent] Reflection " + task_id + " (attempt " + str(attempt) + "): gate=" + str(failed_gate))
    op_id, cl_id = _tenant_ids_from_task(task)
    record_metric("reflection", "maa." + task.get("task_type","unknown") + "_validation_failure",
                  gate=str(failed_gate), attempt=attempt,
                  issues=str(issues[:3]), agent="mother",
                  operator_id=op_id, client_id=cl_id)
    # Phase 2 Step 2.5: Write to dedicated .reflection file for immutable audit trail
    reflection_file = f"{LOGS_DIR}/{task_id}.reflection"
    try:
        with open(reflection_file, "w") as f:
            json.dump(reflection, f, indent=2)
        print("[Mother Agent] Reflection written to " + reflection_file)
    except Exception as e:
        print("[Mother Agent] Could not write reflection file: " + str(e), file=sys.stderr)
    return reflection


def write_progress_report(task_id, agent_label, checkpoint, progress_pct,
                          current_action, findings="", blockers="", next_step="",
                          harness_reminders=None):
    """Write a structured progress report JSON file for this task."""
    pf = f"{LOGS_DIR}/{task_id}.progress"
    try:
        with open(pf, "w") as f:
            json.dump({
                "task_id": task_id,
                "agent_label": agent_label,
                "checkpoint": checkpoint,
                "progress_pct": max(0, min(100, progress_pct)),
                "current_action": current_action,
                "findings": findings,
                "blockers": blockers,
                "next_step": next_step,
                "harness_reminders_active": harness_reminders or [],
                "written_at": now_iso(),
            }, f, indent=2)
    except Exception as e:
        print("[Mother Agent] Progress report write failed: " + str(e), file=sys.stderr)


def spawn_child_agent(task_id: str) -> Optional[bool]:
    """Spawn a child agent for the given task using the real OpenClaw CLI.

    Phase 2 features:
    - _design_harness() builds task-specific harness spec
    - _verify_harness_spec() verifies harness before spawn (Step 2.2)
    - load_template() injects template context (Phase 1)
    - Loop detection with loop_count and skip_child_respawn (Step 2.4)
    - Progress report at spawn time (Step 2.1)
    """

    state_file = f"{TASKS_DIR}/{task_id}.json"
    with open(state_file) as f:
        task = json.load(f)

    if task["attempts"] >= MAX_RETRIES:
        print(f"[Mother Agent] Max retries reached for {task_id}")
        return None

    pre_task_self_heal()

    task["attempts"] += 1
    task["status"] = "running"
    task["updated_at"] = now_iso()
    task["session_id"] = f"{task_id}-attempt-{task['attempts']}"

    with open(state_file, "w") as f:
        json.dump(task, f, indent=2)

    output_file = _output_file_for_task(task)
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    # 8-Pillar: Design harness spec before this attempt
    prior_failure = (task.get("attempt_history", [{}])[-1].get("child_failure_reason")
                    if task.get("attempt_history") else None)
    harness = _design_harness(task["task_type"], task["task_prompt"],
                              task["attempts"], prior_failure)
    task["harness_spec"] = harness
    task["active_pillars"] = harness["active_pillars"]

    # Phase 2 Step 2.2: Runtime harness spec verification BEFORE spawn
    harness_ok, harness_reason = _verify_harness_spec(harness, task_id)
    if not harness_ok:
        print(f"[Mother Agent] HARNESS SPEC VERIFICATION FAILED for {task_id}: {harness_reason}")
        op_id, cl_id = _tenant_ids_from_task(task)
        record_metric("error", f"maa.{task['task_type']}_harness_verify_failed",
                      details=harness_reason, agent="mother",
                      operator_id=op_id, client_id=cl_id)
        task["status"] = "retry"
        task["updated_at"] = now_iso()
        task["child_failure_reason"] = f"harness-spec-verify-failed: {harness_reason}"
        task["loop_count"] = task.get("loop_count", 0)
        with open(state_file, "w") as f:
            json.dump(task, f, indent=2)
        return False

    # Phase 2 Step 2.1: Write initial progress file before child runs
    write_progress_report(task_id, "child-" + str(task["attempts"]), "start", 0,
                         "Child agent spawning — harness verified, starting work",
                         blockers="", next_step="running",
                         harness_reminders=harness.get("dynamic_reminders", []))
    task["has_progress_update"] = False
    task["last_progress_at"] = now_iso()

    # Phase 1: Load template (fall back to inline harness if not found)
    template_content = load_template(task["task_type"])
    harness_template_version = "inline"
    if template_content:
        harness_template_version = "v1.0"

    pillars_str = ", ".join(harness["active_pillars"])
    reminders = harness.get("dynamic_reminders", [])
    rem_str = "\n".join(["  - " + r for r in reminders]) if reminders else "  (none)"
    success_str = "\n".join(["  - " + c for c in harness["success_criteria"]])
    gates = harness["verification_gates"]

    child_prompt_parts = [
        "TASK TYPE: " + task["task_type"] + " | TASK ID: " + task_id + "\n"
        "USER REQUEST: " + task["task_prompt"] + "\n",
    ]

    # Phase 1: If template loaded, inject it as full context before harness spec
    if template_content:
        child_prompt_parts.append(
            "\n" + ("=" * 60) + "\n"
            "SUB-AGENT TEMPLATE (loaded from " + harness_template_version + ")\n"
            + ("=" * 60) + "\n"
            + template_content + "\n"
            + ("=" * 60) + "\n"
            "TASK HARNESS SPEC\n"
            + ("=" * 60) + "\n"
        )

    child_prompt_parts.append(
        "Active Pillars: " + pillars_str + "\n"
        "Global State Keys: " + ", ".join(harness["global_state_keys"]) + "\n"
        "Scoped Memory read: " + ", ".join(harness["scoped_memory"]["read"]) + "\n"
        "Scoped Memory write: " + ", ".join(harness["scoped_memory"]["write"]) + "\n"
        "Dynamic Reminders (from prior failures):\n" + rem_str + "\n"
        "Verification Gates:\n"
        "  1. Completeness: " + gates[0] + "\n"
        "  2. Factual Grounding: " + gates[1] + "\n"
        "  3. Format Compliance: " + gates[2] + "\n"
        "  4. Quality: " + gates[3] + "\n"
        "Success Criteria:\n" + success_str + "\n"
        "Safety: no external sends without MA pre-approval; no irreversible without sign-off\n"
        "Escalation: 3+ sources fail->ask MA; irreversible->pause; security->halt+escalate\n"
        "Progress Reports: write logs/" + task_id + ".progress at start/progress/near_complete/done\n"
        "OUTPUT PATH: " + task["output_path"] + (task.get("output_ext") or ".txt") + "\n"
        "IMPORTANT: Return only the final output. No commentary. Write progress reports at checkpoints."
    )

    child_prompt = "".join(child_prompt_parts)
    task["harness_template_version"] = harness_template_version

    cmd = [
        "openclaw", "agent", "--local",
        "--session-id", task["session_id"],
        "-m", child_prompt,
        "--timeout", str(CHILD_TIMEOUT),
    ]

    usable, usability_reason = False, "not attempted"
    result = None
    child_status = None
    try:
        child_status, result = _run_with_progress_tracking(cmd, task_id, task["task_type"], task["attempts"])

        if child_status is None:
            print("[Mother Agent] Child agent produced no result for " + task_id + " (attempt " + str(task["attempts"]) + ")")
            task["status"] = "retry"
            task["updated_at"] = now_iso()
            task["last_error"] = "subprocess-produced-no-result"
            op_id, cl_id = _tenant_ids_from_task(task)
            record_metric("error", "maa." + task["task_type"] + "_no_result",
                          details="subprocess returned None status", agent="mother",
                          operator_id=op_id, client_id=cl_id)
            with open(state_file, "w") as f:
                json.dump(task, f, indent=2)
            return False

        if child_status == "done":
            result = result
        elif child_status == "timeout":
            print("[Mother Agent] Child agent hard timeout for " + task_id + " (attempt " + str(task["attempts"]) + ")")
            task["status"] = "retry"
            task["updated_at"] = now_iso()
            task["last_error"] = "subprocess-hard-timeout"
            op_id, cl_id = _tenant_ids_from_task(task)
            record_metric("error", "maa." + task["task_type"] + "_timeout",
                          details="child hard timed out", agent="mother",
                          operator_id=op_id, client_id=cl_id)
            with open(state_file, "w") as f:
                json.dump(task, f, indent=2)
            return False
        elif child_status == "error":
            print("[Mother Agent] Child agent error for " + task_id + ": " + str(result))
            task["status"] = "retry"
            task["updated_at"] = now_iso()
            task["last_error"] = str(result)[:200]
            op_id, cl_id = _tenant_ids_from_task(task)
            record_metric("error", "maa." + task["task_type"] + "_spawn_error",
                          details=str(result)[:200], agent="mother",
                          operator_id=op_id, client_id=cl_id)
            with open(state_file, "w") as f:
                json.dump(task, f, indent=2)
            return False

        task["updated_at"] = now_iso()
        task["last_exit_code"] = result.returncode
        task["last_stderr"] = result.stderr[:500] if result.stderr else ""
        task["last_stdout_preview"] = result.stdout[:200] if result.stdout else ""

        usable, usability_reason = child_output_is_usable(result.stdout, result.stderr)

        if result.returncode == 0 and usable:
            with open(output_file, "w") as f:
                f.write(result.stdout.strip() + "\n")

            sv = _next_state_version(task)
            completion_data = {
                "task_id": task_id,
                "status": "completed",
                "output_path": output_file,
                "attempt": task["attempts"],
                "completed_at": now_iso(),
                "state_version": sv,
                "written_by": "spawn_child_agent",
            }

            completion_file = _completion_file_path(task_id, task.get("tenant_context"))
            with open(completion_file, "w") as f:
                json.dump(completion_data, f, indent=2)

            marker_ok, marker_reason = _verify_completion_marker(task_id, task["attempts"])
            if not marker_ok:
                task["status"] = "retry"
                task["child_failure_reason"] = "completion-marker-verify-failed: " + marker_reason
                op_id, cl_id = _tenant_ids_from_task(task)
                record_metric("error", "maa." + task["task_type"] + "_marker_verify_failed",
                              details=marker_reason, agent="mother",
                              operator_id=op_id, client_id=cl_id)
                with open(state_file, "w") as f:
                    json.dump(task, f, indent=2)
                return False

            with open(completion_file) as f:
                marker_read = json.load(f)
            if marker_read.get("state_version") != sv:
                task["status"] = "retry"
                task["child_failure_reason"] = (
                    "state_version mismatch: wrote " + str(sv) + ", read " + str(marker_read.get("state_version"))
                )
                op_id, cl_id = _tenant_ids_from_task(task)
                record_metric("error", "maa." + task["task_type"] + "_sv_mismatch",
                              details="wrote=" + str(sv) + " read=" + str(marker_read.get("state_version")), agent="mother",
                              operator_id=op_id, client_id=cl_id)
                with open(state_file, "w") as f:
                    json.dump(task, f, indent=2)
                return False

            if "attempt_history" not in task:
                task["attempt_history"] = []
            task["attempt_history"].append({
                "attempt": task["attempts"],
                "at": now_iso(),
                "output_file": output_file,
                "marker_verified": True,
            })

            task["status"] = "completed"
            task["output_file"] = output_file
            task["state_version"] = sv
            task["child_success_at"] = now_iso()
            op_id, cl_id = _tenant_ids_from_task(task)
            record_metric("task", "maa." + task["task_type"], status="completed",
                          agent="mother", operator_id=op_id, client_id=cl_id)
        else:
            task["status"] = "retry"
            task["child_failure_reason"] = usability_reason or ("exit=" + str(result.returncode))
            op_id, cl_id = _tenant_ids_from_task(task)
            record_metric(
                "error",
                "maa." + task["task_type"] + "_child_failed",
                details=(result.stderr or usability_reason or "child returned unusable output")[:200],
                agent="mother",
                operator_id=op_id, client_id=cl_id,
            )

    except Exception as e:
        print("[Mother Agent] Child agent spawn error for " + task_id + ": " + str(e))
        task["status"] = "retry"
        task["updated_at"] = now_iso()
        task["last_error"] = str(e)[:200]
        op_id, cl_id = _tenant_ids_from_task(task)
        record_metric("error", "maa." + task["task_type"] + "_spawn_error",
                      details=str(e)[:200], agent="mother",
                      operator_id=op_id, client_id=cl_id)

    with open(state_file, "w") as f:
        json.dump(task, f, indent=2)

    return usable
def run_task_chain(task_id: str) -> dict:
    """Run the full failover chain for a task. Mother Agent orchestrates.
    
    State transitions:
      pending → running → completed → validated
                           └→ needs_revision → pending (retry)
      pending → exhausted (all attempts failed)
    
    Key invariants enforced:
    - status=validated only when output_file + completion_marker + passed validation all exist
    - status=needs_revision when any of those three is missing
    - status=exhausted when all MAX_RETRIES attempts returned unusable/failed output
    - state_version increments on every state transition
    """

    state_file = _task_state_path(task_id, task.get("tenant_context"))
    with open(state_file) as f:
        task = json.load(f)

    print(f"[Mother Agent] Starting task chain for {task_id} (max {MAX_RETRIES} attempts)")

    chain_fully_exhausted = False

    for attempt in range(1, MAX_RETRIES + 1):
        with open(state_file) as f:
            task = json.load(f)
        task["current_attempt"] = attempt
        task["state_version"] = _next_state_version(task)
        with open(state_file, "w") as f:
            json.dump(task, f, indent=2)

        # Phase 2 Step 2.4: If skip_child_respawn, jump to Mother self-execution
        with open(state_file) as f:
            task = json.load(f)
        if task.get("skip_child_respawn"):
            print(f"[Mother Agent] skip_child_respawn=True — looping to Mother self-execution")
            break

        print(f"[Mother Agent] Attempt {attempt}/{MAX_RETRIES} for {task_id}")
        success = spawn_child_agent(task_id)

        with open(state_file) as f:
            task = json.load(f)

        if success:
            print(f"[Mother Agent] Attempt {attempt} succeeded for {task_id}")
            validation = run_validation(task_id, task.get("validator_prompt") or "")

            with open(state_file) as f:
                task = json.load(f)

            # CRIT-2 FIX: Verify completion marker by independent filesystem check, not task state
            # Use deterministic path — the completion marker is always at this path
            marker_path = _completion_file_path(task_id, task.get("tenant_context"))
            marker_ok = os.path.exists(marker_path)

            # Also verify the task state fields
            validation_passed = validation.get("passed", False)

            # CRIT-2: Verify output file independently (not from task state)
            output_file = _output_file_for_task(task)
            output_ok = os.path.exists(output_file)
            
            if validation_passed and marker_ok and output_ok:
                task["status"] = "validated"
                task["validated_at"] = now_iso()
                task["state_version"] = _next_state_version(task)
                task["mother_validation"] = validation
                print(f"[Mother Agent] Task {task_id} PASSED — status=validated")
            else:
                task["status"] = "needs_revision"
                task["revision_needed_at"] = now_iso()
                task["mother_validation"] = validation
                reasons = []
                if not validation_passed:
                    reasons.append(f"validation: {validation.get('reason', 'unknown')}")
                if not marker_ok:
                    reasons.append("completion marker missing")
                if not output_ok:
                    reasons.append("output file missing")
                task["revision_reasons"] = reasons
                print(f"[Mother Agent] Task {task_id} needs_revision: {'; '.join(reasons)}")
            
            with open(state_file, "w") as f:
                json.dump(task, f, indent=2)
            return task
        else:
            print(f"[Mother Agent] Attempt {attempt} failed for {task_id}, retrying...")
            chain_fully_exhausted = True

    # All attempts exhausted — mark as exhausted with full audit trail
    if chain_fully_exhausted:
        with open(state_file) as f:
            task = json.load(f)
        task["status"] = "exhausted"
        task["exhausted_at"] = now_iso()
        task["state_version"] = _next_state_version(task)
        task["mother_validation"] = {
            "passed": False,
            "reason": f"All {MAX_RETRIES} child agents failed or returned unusable output",
            "action": "escalate_to_mother",
        }
        with open(state_file, "w") as f:
            json.dump(task, f, indent=2)
        print(f"[Mother Agent] All attempts exhausted for {task_id} — status=exhausted")
        return task
    
    return task


def run_validation(task_id: str, validator_prompt: str) -> dict:
    """Mother Agent validates child output via a validation child agent.
    
    HARD RULE: No validation file = validation FAILED.
    Validation must produce a real .validation JSON file or it doesn't count.
    """
    
    state_file = f"{TASKS_DIR}/{task_id}.json"
    with open(state_file) as f:
        task = json.load(f)
    
    output_path = task.get("output_path")
    if not output_path:
        return {"passed": False, "reason": "No output path in task state"}
    
    output_ext = task.get("output_ext") or TASK_TYPES.get(task["task_type"], {}).get("output_ext", ".txt")
    actual_output = f"{output_path}{output_ext}"
    
    if not os.path.exists(actual_output):
        return {"passed": False, "reason": f"Output file not found: {actual_output}"}
    
    # Read output to validate
    try:
        with open(actual_output) as f:
            output_content = f.read()
    except Exception as e:
        return {"passed": False, "reason": f"Cannot read output file: {e}"}
    
    validation_file = f"{LOGS_DIR}/{task_id}.validation"
    
    val_prompt = f"""VALIDATE this task output:

Task type: {task['task_type']}
Task prompt: {task['task_prompt']}
Output file: {actual_output}
Validation file to write: {validation_file}

Your job:
1. Read {actual_output} — the actual child agent output
2. Evaluate against ALL of these criteria:
   - COMPLETENESS: Is it fully formed? No [TBD], no truncation, no placeholder sections
   - FACTUAL GROUNDING: Are claims backed with data/sources? Numbers named and verifiable?
   - FORMAT COMPLIANCE: Does it match the expected format for type={task['task_type']}?
   - QUALITY: Is it production-ready? No waffle, no vague language
   - SPECIFIC CRITERIA: {validator_prompt or 'Default validation'}

3. Write a JSON validation report to: {validation_file}
   Format:
   {{
     "task_id": "{task_id}",
     "output_file": "{actual_output}",
     "output_length_chars": {len(output_content)},
     "passed": true or false,
     "completeness": "pass|fail + 1-line note",
     "factual_grounding": "pass|fail + 1-line note",
     "format_compliance": "pass|fail + 1-line note",
     "quality": "pass|fail + 1-line note",
     "issues": ["specific issue 1", "specific issue 2"],
     "summary": "one-line overall assessment"
   }}

CRITICAL: Write the validation JSON to {validation_file}. Do not just describe — actually write the file.
"""
    
    if not validator_prompt:
        validator_prompt = "Standard Maa validation criteria"

    try:
        result = subprocess.run(
            [
                "openclaw", "agent", "--local",
                "--session-id", f"validate-{task_id}",
                "-m", val_prompt,
                "--timeout", "300",   # 5 min — aligns with no-timeout philosophy; Python timeout is 330s
            ],
            capture_output=True,
            text=True,
            timeout=330,   # 30s buffer above agent timeout
            cwd=WORKSPACE,
        )
        
        # HARD RULE: validation file must exist and be valid JSON
        if not os.path.exists(validation_file):
            task["mother_validation"] = {
                "passed": False,
                "reason": "Validation agent did not write validation file",
                "output_verified": actual_output,
                "stderr": (result.stderr or "")[:300],
            }
            with open(state_file, "w") as f:
                json.dump(task, f, indent=2)
            return task["mother_validation"]
        
        try:
            with open(validation_file) as f:
                validation_data = json.load(f)
        except json.JSONDecodeError:
            task["mother_validation"] = {
                "passed": False,
                "reason": "Validation file is not valid JSON",
                "output_verified": actual_output,
            }
            with open(state_file, "w") as f:
                json.dump(task, f, indent=2)
            return task["mother_validation"]
        
        task["mother_validation"] = validation_data
        task["mother_validation"]["output_verified"] = actual_output
        
    except subprocess.TimeoutExpired:
        task["mother_validation"] = {
            "passed": False,
            "reason": "Validation agent timed out",
            "output_verified": actual_output,
        }
    except Exception as e:
        task["mother_validation"] = {
            "passed": False,
            "reason": f"Validation error: {str(e)[:100]}",
            "output_verified": actual_output,
        }
    
    with open(state_file, "w") as f:
        json.dump(task, f, indent=2)
    
    return task.get("mother_validation", {})


def get_task_status(task_id: str) -> dict:
    """Get current status of a task."""
    # Try legacy path first (backward compat for default tenant)
    state_file = f"{TASKS_DIR}/{task_id}.json"
    if os.path.exists(state_file):
        with open(state_file) as f:
            return json.load(f)
    # Try tenant-scoped paths: tenants/{op}/tasks/{task_id}.json
    from tenant_paths import TENANTS_ROOT
    for op_dir in TENANTS_ROOT.iterdir():
        if not op_dir.is_dir():
            continue
        candidate = op_dir / "tasks" / f"{task_id}.json"
        if candidate.exists():
            with open(candidate) as f:
                return json.load(f)
        # Also check clients subdir
        clients_dir = op_dir / "clients"
        if clients_dir.is_dir():
            for cl_dir in clients_dir.iterdir():
                if not cl_dir.is_dir():
                    continue
                candidate = cl_dir / "tasks" / f"{task_id}.json"
                if candidate.exists():
                    with open(candidate) as f:
                        return json.load(f)
    return {"error": "Task not found"}


def list_tasks() -> list:
    """List all tasks."""
    tasks = []
    for f in os.listdir(TASKS_DIR):
        if f.endswith(".json"):
            with open(os.path.join(TASKS_DIR, f)) as fh:
                tasks.append(json.load(fh))
    return sorted(tasks, key=lambda x: x.get("updated_at", ""), reverse=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Maa Core Multi-Agent Orchestrator")
    subparsers = parser.add_subparsers(dest="command")
    
    submit_p = subparsers.add_parser("submit", help="Submit a new task")
    submit_p.add_argument("task_type", help=f"Task type: {list(TASK_TYPES.keys())}")
    submit_p.add_argument("task_prompt", help="Task description/prompt")
    submit_p.add_argument("--output-dir", help="Override output directory")
    submit_p.add_argument("--run", action="store_true", help="Run the task chain immediately")
    submit_p.add_argument("--validator-prompt", help="Additional validation criteria")
    submit_p.add_argument("--operator", default=None, help="Operator ID (required for non-default tenancy)")
    submit_p.add_argument("--client", default=None, help="Client ID (required for client-level tenancy)")
    submit_p.add_argument("--tenant-json", default=None,
                          help="Full tenant context as JSON")
    
    status_p = subparsers.add_parser("status", help="Get task status")
    status_p.add_argument("task_id", help="Task ID")
    
    list_p = subparsers.add_parser("list", help="List all tasks")
    list_p.add_argument("--limit", type=int, default=20, help="Max tasks to show")
    
    run_p = subparsers.add_parser("run", help="Run task chain for submitted task")
    run_p.add_argument("task_id", help="Task ID")
    
    args = parser.parse_args()
    
    if args.command == "submit":
        raw_context = None
        if args.tenant_json:
            try:
                raw_context = json.loads(args.tenant_json)
            except json.JSONDecodeError as e:
                print(f"ERROR: --tenant-json is not valid JSON: {e}")
                sys.exit(1)
        elif args.operator:
            raw_context = {
                "operator_id": args.operator,
                "client_id": args.client or args.operator,
            }
        try:
            tenant = submit_task_gate(args.task_prompt, args.task_type, raw_context)
        except RateLimitExceeded as e:
            print(f"RATE LIMIT EXCEEDED: {e.operator_id}/{e.client_id} - max {e.limit} tasks per {e.window_s}s")
            sys.exit(1)
        except ValueError as e:
            print(f"ERROR: {e}")
            sys.exit(1)
        task_id = submit_task(
            args.task_type,
            args.task_prompt,
            args.output_dir,
            None,
            args.validator_prompt,
            tenant_context=raw_context,
        )
        # NOTE: task_accepted() is already called inside submit_task().
        # Do not call it here again — that would double-log to the audit trail.
        print(f"Task ID: {task_id} [{tenant}]")
        if args.run:
            result = run_task_chain(task_id)
            print(f"Final status: {result['status']}")
            if result.get("mother_validation"):
                print(f"Validation: {json.dumps(result['mother_validation'], indent=2)}")
    
    elif args.command == "status":
        status = get_task_status(args.task_id)
        print(json.dumps(status, indent=2))
    
    elif args.command == "list":
        tasks = list_tasks()
        for t in tasks[:args.limit]:
            print(f"{t['task_id']} | {t['task_type']} | {t['status']} | attempts={t['attempts']} | {t['updated_at']}")
    
    elif args.command == "run":
        result = run_task_chain(args.task_id)
        print(f"Final status: {result['status']}")
    
    else:
        parser.print_help()


# ── Concurrent child tracking ─────────────────────────────────────────────────
_running_children_lock = __import__("threading").Lock()
_running_children: set = set()
RUNNING_CHILDREN_FILE = f"{LOGS_DIR}/running_children.json"
STALE_RUNNING_SECONDS = CHILD_TIMEOUT * 2

def _persist_running_children() -> None:
    try:
        os.makedirs(LOGS_DIR, exist_ok=True)
        with _running_children_lock:
            payload = {"updated_at": now_iso(), "task_ids": sorted(_running_children)}
        with open(RUNNING_CHILDREN_FILE, "w") as f:
            json.dump(payload, f, indent=2)
    except Exception as e:
        print("[Mother Agent] Could not persist running children: " + str(e), file=sys.stderr)

def _load_running_children() -> set:
    if not os.path.exists(RUNNING_CHILDREN_FILE):
        return set()
    try:
        with open(RUNNING_CHILDREN_FILE) as f:
            payload = json.load(f)
        return set(payload.get("task_ids", []))
    except Exception:
        return set()

def _get_running_count() -> int:
    with _running_children_lock:
        return len(_running_children)

def _add_running(task_id: str) -> None:
    with _running_children_lock:
        _running_children.add(task_id)
    _persist_running_children()

def _remove_running(task_id: str) -> None:
    with _running_children_lock:
        _running_children.discard(task_id)
    _persist_running_children()


# ── Startup reconciliation for restart/resume safety ──────────────────────────
def _reconcile_running_children() -> None:
    persisted = _load_running_children()
    live = set()
    for task_id in persisted:
        state_file = f"{TASKS_DIR}/{task_id}.json"
        if not os.path.exists(state_file):
            continue
        try:
            with open(state_file) as f:
                task = json.load(f)
            if task.get("status") in {"running", "mother_self_executing"}:
                live.add(task_id)
        except Exception:
            continue
    with _running_children_lock:
        _running_children.clear()
        _running_children.update(live)
    _persist_running_children()

def _mark_stale_running_tasks() -> None:
    now_ts = time.time()
    for name in os.listdir(TASKS_DIR):
        if not name.endswith(".json"):
            continue
        state_file = os.path.join(TASKS_DIR, name)
        try:
            with open(state_file) as f:
                task = json.load(f)
        except Exception:
            continue
        if task.get("status") not in {"running", "mother_self_executing"}:
            continue
        updated_at = task.get("updated_at") or task.get("mother_self_exec_at") or task.get("created_at")
        try:
            updated_ts = datetime.strptime(updated_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC).timestamp()
        except Exception:
            continue
        if now_ts - updated_ts <= STALE_RUNNING_SECONDS:
            continue
        task["status"] = "retry"
        task["stale_running_detected_at"] = now_iso()
        task["child_failure_reason"] = "stale running task after restart/recovery"
        if "attempt_history" not in task:
            task["attempt_history"] = []
        task["attempt_history"].append({
            "attempt": task.get("attempts", 0),
            "at": now_iso(),
            "child_failure_reason": task["child_failure_reason"],
            "status": "stale_recovered",
        })
        with open(state_file, "w") as f:
            json.dump(task, f, indent=2)

_reconcile_running_children()
_mark_stale_running_tasks()
