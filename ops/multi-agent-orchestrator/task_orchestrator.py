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
from access_control import require_spawn_child_agent, require_operator_role, assert_operator
from tenant_gate import submit_task_gate, task_accepted, task_rejected, RateLimitExceeded, record_runtime_minutes, record_spend, estimate_task_cost, SpendBudgetExhausted
from tenant_paths import TenantPathResolver
from approval_gate import load_state as _load_approval_state, save_state as _save_approval_state, _action_hash as _approval_action_hash, _expiry as _approval_expiry, _now as _approval_now
from idempotency import submit_task_dedup, register_task_submission, update_task_dedup_status
from canary_router import route_to_canary, is_canary_deployed, get_canary_version

VERSION = "v1.0"
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
PROGRESS_PING_AT = 300  # seconds — send first "still working" update after 5 min of child run
PROGRESS_PING_2_AT = 600  # seconds — send second update only if still running after 10 min

# ── Phase 2: Runtime Harness Enforcement ─────────────────────────────────────
TEMPLATES_DIR = f"{WORKSPACE}/agents/templates"
LOOP_SAME_FAILURE_THRESHOLD = 2
HARNESS_SPEC_MIN_FIELDS = ["harness_version", "active_pillars", "verification_gates", "dynamic_reminders"]
REFLECTION_MIN_LENGTH = 5
MAX_CONCURRENT_CHILDREN = 4
CIRCUIT_BREAKER_WINDOW_S = 3600
CIRCUIT_BREAKER_THRESHOLD = 0.05

# ── Phase 13: Runtime-minute accounting ──────────────────────────────────────
# Tracks wall-clock start time per task so we can compute actual runtime
# on task termination and record it against the daily runtime quota.
_task_start_times: dict[str, float] = {}

# ── Phase 1: Template loading (with Phase 12 canary variant support) ─────────────
def load_template(task_type: str, version: str = "v1.0") -> str | None:
    """Load a sub-agent template for the given task type and version.

    version="canary" loads the canary template variant when a canary build
    is deployed and that task has been routed to the canary path.
    """
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

def _progress_log_path(task_id: str, tenant_context: Optional[dict] = None) -> str:
    """Tenant-aware progress signal path.

    Uses the same resolve_log_file() mechanism as _completion_file_path() so that
    channel routers always find the signal file in the right place regardless of
    which tenant a task belongs to.
    """
    tc = parse_tenant_context(tenant_context)
    if tc.is_default():
        return f"{LOGS_DIR}/{task_id}.progress"
    resolver = TenantPathResolver(tc)
    return str(resolver.resolve_log_file(task_id, "progress"))


def _deliver_progress_update(task_id: str, task_type: str, attempt: int,
                                elapsed_seconds: int, current_action: str = "",
                                next_expected_step: str = "",
                                tenant_context: Optional[dict] = None) -> None:
    """Write a canonical progress payload to the signal file.

    This is the single delivery point for all progress pings. The payload is
    transport-agnostic — any channel (Telegram, WhatsApp, etc.) reads this file
    via the runtime interaction router and surfaces the update to the requester or operator.

    Canonical fields (Phase 3 spec):
      task_id, task_type, attempt_number, progress_summary,
      current_action, elapsed_seconds, next_expected_step

    Deduplication rules:
      - Initial ping: sent once per task attempt (tracked via progress_ping_sent_at)
      - Second ping: sent only if task is still running after 10 min (progress_ping_2_sent_at)
      - No hard-coded channel or provider logic in this function
    """
    # Load task to read state for deduplication checks — tenant-aware path
    state_file = _task_state_path(task_id, tenant_context)
    if not os.path.exists(state_file):
        # Task may have completed — skip silently
        return
    try:
        with open(state_file) as f:
            task = json.load(f)
    except Exception:
        return

    # ── Deduplication: initial ping only once per attempt ─────────────────────
    second_key = f"progress_ping_2_sent_at_{attempt}"
    second_already_sent = bool(task.get(second_key))
    initial_key = f"progress_ping_sent_at_{attempt}"
    initial_already_sent = bool(task.get(initial_key))

    if initial_already_sent:
        # Already sent initial ping for this attempt — skip unless 2nd threshold reached
        if second_already_sent:
            return  # both pings sent, nothing more to do
        if elapsed_seconds < PROGRESS_PING_2_AT:
            return  # not yet time for second ping
    else:
        # First time we're sending any ping for this attempt — mark initial sent
        task[initial_key] = now_iso()

    # ── Build canonical progress payload ─────────────────────────────────────
    # Determine ping_number before we mutate task state
    # (ping_number reflects the delivery we're about to make, not what's already set)
    ping_number = 2 if (second_already_sent or elapsed_seconds >= PROGRESS_PING_2_AT) else 1

    progress_summary = (
        f"Task {task_id} running for {elapsed_seconds}s "
        f"(attempt {attempt}/{MAX_RETRIES}). "
        f"Type: {task_type}. Child agent is active."
    )
    pf = _progress_log_path(task_id, tenant_context)
    try:
        os.makedirs(os.path.dirname(pf), exist_ok=True)
        with open(pf, "w") as f:
            json.dump({
                # Canonical fields (Phase 3 spec)
                "task_id": task_id,
                "task_type": task_type,
                "attempt_number": attempt,
                "progress_summary": progress_summary,
                "current_action": current_action or "child_agent_executing",
                "elapsed_seconds": elapsed_seconds,
                "next_expected_step": next_expected_step or "completion_marker_or_next_retry",
                # Metadata
                "ping_number": ping_number,
                "delivered_at": now_iso(),
                "delivered_by": "mother_agent_progress_poller",
            }, f, indent=2)
        print(f"[Mother Agent] Progress update delivered for {task_id} "
              f"(~{elapsed_seconds}s elapsed, attempt {attempt}, ping={ping_number})")

        # Mark second ping done if we've crossed that threshold — BEFORE state rewrite
        if elapsed_seconds >= PROGRESS_PING_2_AT:
            task[second_key] = now_iso()

        with open(state_file, "w") as f:
            json.dump(task, f, indent=2)
    except Exception as e:
        print(f"[Mother Agent] Could not write progress file: {e}", file=sys.stderr)


def _send_progress_update(task_id: str, task_type: str, attempt: int, channel: str = "telegram") -> None:
    """Legacy single-shot progress ping for inline use within _run_with_progress_tracking.

    This function is kept for backward compatibility with the existing inline ping
    that fires inside _run_with_progress_tracking. For the background poller, use
    _deliver_progress_update() instead — it uses the canonical payload and has proper
    deduplication.
    """
    # Delegate to the canonical deliver function
    _deliver_progress_update(task_id, task_type, attempt, PROGRESS_PING_AT,
                             current_action="child_agent_executing",
                             next_expected_step="completion_marker")


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


APPROVAL_REQUIRED_TYPES = {"email_send", "calendar_write", "web_post", "file_external", "api_write", "client_data_delete"}


def _approval_required_for_task(task: dict) -> tuple[bool, str, str, str]:
    """Return (required, action_type, target, body_summary) for approval-gated tasks.

    Phase 9 runtime scope: email-draft tasks that clearly request immediate send/outbound action
    are treated as approval-required before child spawn.
    """
    task_type = task.get("task_type", "")
    prompt = (task.get("task_prompt") or "").strip()
    if task_type == "email-draft":
        lowered = prompt.lower()
        if any(token in lowered for token in ["send now", "send this", "email this", "outbound", "reply to", "compose and send"]):
            return True, "email_send", "email-recipient-unspecified", prompt[:80]
    return False, "", "", ""


def _check_approval_gate(task: dict) -> tuple[bool, str]:
    required, action_type, target, body_summary = _approval_required_for_task(task)
    if not required:
        return True, "not_required"
    tc = parse_tenant_context(task.get("tenant_context"))
    action_hash = _approval_action_hash(action_type, target, body_summary, tc.operator_id)
    state = _load_approval_state()
    entry = state.get("approvals", {}).get(action_hash)
    if entry is None:
        return False, f"approval required for {action_type}, no approval_state entry for hash={action_hash}"
    status = entry.get("status")
    if status == "approved":
        return True, "approved"
    if status == "pending":
        return False, f"approval pending for hash={action_hash}"
    if status == "expired":
        return False, f"approval expired for hash={action_hash}"
    return False, f"approval status={status} for hash={action_hash}"


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
    if len(text) < 50:
        try:
            json.loads(text)
            return True, "ok"
        except Exception:
            return False, f"suspiciously short output ({len(text)} chars) and not valid JSON"

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


def _create_budget_approval(task_id: str, tenant: TenantContext, task_type: str, task_prompt: str) -> str:
    tenant_id = f"{tenant.operator_id}:{tenant.client_id}"
    target = f"{tenant.operator_id}/{tenant.client_id}"
    summary = f"budget approval for {task_type}: {task_prompt[:80]}"
    action_hash = _approval_action_hash("api_write", target, summary, tenant_id)
    state = _load_approval_state()
    state.setdefault("approvals", {})
    if action_hash not in state["approvals"]:
        state["approvals"][action_hash] = {
            "action_hash": action_hash,
            "requested_by": "mother",
            "task_id": task_id,
            "action_type": "api_write",
            "target": target,
            "body_summary": summary,
            "status": "pending",
            "approved_by": None,
            "approved_at": None,
            "approver_token": None,
            "expires_at": _approval_expiry(),
            "created_at": _approval_now(),
            "approval_reason": "spend_budget_exceeded",
        }
        _save_approval_state(state)
    return action_hash


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

    # ── Phase 10 RBAC: require OPERATOR or SYSTEM for task submission ────────────
    assert_operator("submit_task")

    tc = parse_tenant_context(tenant_context)
    tenant = tc
    tenant_id = f"{tc.operator_id}:{tc.client_id}"
    task_id = f"{task_type}-{int(time.time())}-{uuid.uuid4().hex[:6]}"

    # ── GAP 1 FIX: Gate every task through tenant enforcement ─────────────────
    try:
        tenant = submit_task_gate(task_prompt, task_type, tenant_context)
    except RateLimitExceeded as e:
        print(f"[Mother Agent] RATE LIMIT EXCEEDED: {e.operator_id}/{e.client_id} "
              f"— max {e.limit} tasks per {e.window_s}s")
        raise
    except SpendBudgetExhausted as sbe:
        print(f"[Mother Agent] SPEND BUDGET EXHAUSTED: {sbe.operator_id}/{sbe.client_id} "
              f"— action={sbe.exceed_action}")
        resolver = TenantPathResolver(tc)
        resolver.ensure_dirs()
        output_dir = output_dir or str(resolver.resolve("outputs"))
        os.makedirs(output_dir, exist_ok=True)
        output_path = f"{output_dir}/{task_id}"
        task_config = TASK_TYPES[task_type]
        task_state = {
            "task_id": task_id,
            "task_type": task_type,
            "task_prompt": task_prompt,
            "output_path": output_path,
            "output_dir": output_dir,
            "child_label": task_config["child_label"],
            "model": task_config["model"],
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
            "budget_limit_name": sbe.quota_type,
            "budget_limit_value": sbe.limit_value,
            "budget_current_value": sbe.current_value,
            "budget_action": sbe.exceed_action,
        }
        state_file = str(resolver.resolve_task_file(task_id))
        if sbe.exceed_action == "require_approval":
            action_hash = _create_budget_approval(task_id, tc, task_type, task_prompt)
            task_state["status"] = "waiting_approval"
            task_state["approval_hash"] = action_hash
            with open(state_file, "w") as f:
                json.dump(task_state, f, indent=2)
            return task_id
        if sbe.exceed_action == "queue":
            task_state["status"] = "queued_budget"
            task_state["queued_reason"] = "budget_exceeded"
            task_state["queued_at"] = now_iso()
            with open(state_file, "w") as f:
                json.dump(task_state, f, indent=2)
            return task_id
        raise RuntimeError(
            f"Spend budget exceeded for {sbe.operator_id}/{sbe.client_id}. "
            f"Action: {sbe.exceed_action}. Task rejected."
        ) from sbe
    except ValueError as e:
        print(f"[Mother Agent] TENANT GATE REJECTED: {e}")
        raise

    # ── Phase 11 DEDUP: reuse active duplicate instead of double-submitting ──
    tenant_id = f"{tenant.operator_id}:{tenant.client_id}"
    dup_task_id = submit_task_dedup(task_type, task_prompt, tenant_id)
    if dup_task_id:
        print(f"[Mother Agent] DUPLICATE REUSED: {task_type}/{tenant.operator_id}/{tenant.client_id} "
              f"→ {dup_task_id}")
        return dup_task_id

    task_config = TASK_TYPES[task_type]

    # ── GAP 1 FIX: Use TenantPathResolver for all tenant-scoped paths ─────────
    resolver = TenantPathResolver(tenant)
    resolver.ensure_dirs()


    # output_dir: allow override only for non-default output types
    # Tenant-scoped output dir (GAP 5 fix: use resolver not task_config fallback)
    if output_dir is None:
        output_dir = str(resolver.resolve("outputs"))
    os.makedirs(output_dir, exist_ok=True)

    output_path = f"{output_dir}/{task_id}"

    # Build the child agent prompt
    prompt = task_config["default_prompt"].format(
        task_prompt=task_prompt,
        output_path=output_path
    )

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

    # ── Phase 11 DEDUP: register so future duplicates are caught ────────────────
    try:
        register_task_submission(task_id, task_type, task_prompt, tenant_id, status="pending")
    except Exception as ex:
        print(f"[Mother Agent] Warning: dedup registry not updated: {ex}")

    # ── Phase 12 CANARY: record routing decision in task state for observability ─
    try:
        with open(state_file) as f:
            current_state = json.load(f)
        current_state["canary_routed"] = route_to_canary(task_id)
        current_state["canary_version"] = None
        if current_state["canary_routed"]:
            current_state["canary_version"] = get_canary_version() or None
        with open(state_file, "w") as f:
            json.dump(current_state, f, indent=2)
    except Exception as ex:
        print(f"[Mother Agent] Warning: canary routing state not recorded: {ex}")

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


def _verify_completion_marker(task_id: str, expected_attempt: int,
                             tenant_context: Optional[dict] = None) -> tuple[bool, str]:
    """Read-your-own-write: confirm the completion marker was actually persisted
    and its fields match what the orchestrator wrote.

    tenant_context enables tenant-scoped path resolution.
    Returns (is_valid, reason).
    """
    path = _completion_file_path(task_id, tenant_context)
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
    }.get(task_type, ["Production-quality output that would satisfy a careful operator"])


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
    sf = _find_task_state_file(task_id)
    if not sf:
        raise FileNotFoundError(f"Task state not found for reflection: {task_id}")
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
    tc = parse_tenant_context(task.get("tenant_context"))
    if tc.is_default():
        reflection_file = f"{LOGS_DIR}/{task_id}.reflection"
    else:
        resolver = TenantPathResolver(tc)
        reflection_file = str(resolver.resolve_log_file(task_id, "reflection"))
    try:
        with open(reflection_file, "w") as f:
            json.dump(reflection, f, indent=2)
        print("[Mother Agent] Reflection written to " + reflection_file)
    except Exception as e:
        print("[Mother Agent] Could not write reflection file: " + str(e), file=sys.stderr)
    return reflection


def write_progress_report(task_id: str, agent_label: str, checkpoint: str, progress_pct: int,
                          current_action: str, findings: str = "", blockers: str = "",
                          next_step: str = "", harness_reminders=None,
                          tenant_context: Optional[dict] = None) -> None:
    """Write a structured progress report JSON file for this task.

    tenant-scoped: writes to tenant logs dir if tenant_context is non-default.
    """
    tc = parse_tenant_context(tenant_context)
    if not tc.is_default():
        resolver = TenantPathResolver(tc)
        pf = str(resolver.resolve_log_file(task_id, "progress"))
    else:
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


# ── Phase 4: Load Shedding Queue ──────────────────────────────────────────────
_task_queue: list[str] = []          # queue of task_ids waiting for a slot

def queue_task(task_id: str, task: dict) -> None:
    """Add a task to the load-shedding queue when MAX_CONCURRENT_CHILDREN is reached."""
    task["status"] = "queued"
    task["queued_at"] = now_iso()
    task["updated_at"] = now_iso()
    state_file = _task_state_path(task_id, task.get("tenant_context"))
    with open(state_file, "w") as f:
        json.dump(task, f, indent=2)
    _task_queue.append(task_id)
    print(f"[Mother Agent] Task {task_id} queued (concurrency limit reached)")

def _process_queue() -> None:
    """Drain the load-shedding queue, starting tasks as slots become available."""
    while _task_queue:
        if _get_running_count() >= MAX_CONCURRENT_CHILDREN:
            break
        next_task_id = _task_queue.pop(0)
        # Verify task still exists and is still queued
        state_file = _find_task_state_file(next_task_id)
        if not state_file:
            continue
        with open(state_file) as f:
            task = json.load(f)
        if task.get("status") != "queued":
            continue
        print(f"[Mother Agent] Queue drain: starting queued task {next_task_id}")
        task["status"] = "pending"
        task["dequeued_at"] = now_iso()
        task["updated_at"] = now_iso()
        with open(state_file, "w") as f:
            json.dump(task, f, indent=2)
        # Start the task chain (runs async in background thread)
        import threading
        t = threading.Thread(target=_run_task_chain_bg, args=(next_task_id,), daemon=True, name=f"queue-drain-{next_task_id}")
        t.start()

def _drain_queue_if_ready() -> None:
    """Alias for _process_queue()."""
    _process_queue()

def _run_task_chain_bg(task_id: str) -> None:
    """Background runner for queued tasks."""
    try:
        run_task_chain(task_id)
    finally:
        _remove_running(task_id)
        _drain_queue_if_ready()

# ── Phase 4: Circuit Breaker ─────────────────────────────────────────────────
# Per-task-type error rate tracking with rolling 1-hour window
_circuit_state: dict[str, dict] = {}  # task_type -> {failures, total, window_start}


def _record_circuit_attempt(task_type: str, failed: bool) -> None:
    """Record an attempt in the rolling circuit-breaker window."""
    now = time.time()
    state = _circuit_state.get(task_type)
    if not state or now - state["window_start"] >= CIRCUIT_BREAKER_WINDOW_S:
        state = {"failures": 0, "total": 0, "window_start": now}
        _circuit_state[task_type] = state
    state["total"] += 1
    if failed:
        state["failures"] += 1


def _is_circuit_open(task_type: str) -> bool:
    """Check if error rate for task_type exceeds 5%% in rolling 1-hour window."""
    now = time.time()
    state = _circuit_state.get(task_type)
    if not state:
        return False
    if now - state["window_start"] >= CIRCUIT_BREAKER_WINDOW_S:
        _circuit_breaker_reset(task_type)
        return False
    if state["total"] == 0:
        return False
    return (state["failures"] / state["total"]) >= CIRCUIT_BREAKER_THRESHOLD


def _record_failure(task_type: str) -> None:
    """Record a child failure for circuit breaker tracking."""
    _record_circuit_attempt(task_type, failed=True)
    state = _circuit_state[task_type]
    record_metric("error", f"maa.{task_type}_circuit_break",
                  details=f"cb_failures={state['failures']} cb_total={state['total']}",
                  agent="mother")


def _record_success(task_type: str) -> None:
    """Record a successful attempt so the breaker uses a real error rate."""
    _record_circuit_attempt(task_type, failed=False)
    if not _is_circuit_open(task_type):
        _circuit_breaker_reset(task_type)


def _circuit_breaker_reset(task_type: str) -> None:
    """Reset circuit breaker state for a task type."""
    now = time.time()
    _circuit_state[task_type] = {"failures": 0, "total": 0, "window_start": now}
    print(f"[Mother Agent] Circuit breaker reset for task_type={task_type}")

# ── Phase 4: Mother Self-Execution ──────────────────────────────────────────
def _mother_self_execute(task_id: str, task: dict) -> dict:
    """Mother Agent handles the task directly when all children are exhausted.
    
    Returns dict with keys: validated (bool), output (str), reason (str)
    """
    task_type = task.get("task_type", "unknown")
    task_prompt = task.get("task_prompt", "")
    output_file = _output_file_for_task(task)
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    # Set task state to mother_self_executing
    state_file = _task_state_path(task_id, task.get("tenant_context"))
    task["status"] = "mother_self_executing"
    task["current_action"] = "mother_self_executing"
    task["mother_self_exec_at"] = now_iso()
    task["updated_at"] = now_iso()
    task["state_version"] = _next_state_version(task)
    with open(state_file, "w") as f:
        json.dump(task, f, indent=2)

    print(f"[Mother Agent] Mother self-executing for {task_id} ({task_type}) after child exhaustion")
    record_metric("call", f"maa.{task_type}_mother_self_exec", agent="mother")

    # Build Mother execution prompt
    pillars_str = ", ".join(task.get("active_pillars", ["P1","P2","P4","P7"]))
    success_criteria = _success_criteria_for(task_type)
    gates = task.get("harness_spec", {}).get("verification_gates", [
        "completeness — fully formed, no [TBD]",
        "factual_grounding — claims backed with data",
        "format_compliance — matches expected format",
        "quality — production-ready, no waffle",
        "channel_fit — correct delivery channel",
    ])
    success_str = "\n".join(["  - " + c for c in success_criteria])
    gates_str = "\n".join([f"  {i+1}. {g}" for i, g in enumerate(gates)])

    mother_prompt = (
        f"TASK TYPE: {task_type} | TASK ID: {task_id}\n"
        f"USER REQUEST: {task_prompt}\n\n"
        f"VERIFICATION GATES:\n{gates_str}\n\n"
        f"SUCCESS CRITERIA:\n{success_str}\n\n"
        f"OUTPUT PATH: {output_file}\n\n"
        f"IMPORTANT: Produce the complete final output directly. Write it to {output_file}.\n"
        f"Return only the final output. No commentary or step-by-step narration."
    )

    try:
        result = subprocess.run(
            ["openclaw", "agent", "--local",
             "--session-id", f"mother-self-{task_id}",
             "-m", mother_prompt,
             "--timeout", "600"],
            capture_output=True, text=True, timeout=630, cwd=WORKSPACE
        )
        output = result.stdout.strip() if result.stdout else ""

        if result.returncode == 0 and output:
            # Write output to file
            with open(output_file, "w") as f:
                f.write(output + "\n")

            # Mother self-exec must write its own completion marker before verification
            sv = _next_state_version(task)
            completion_data = {
                "task_id": task_id,
                "status": "completed",
                "output_path": output_file,
                "attempt": task.get("attempts", 1),
                "completed_at": now_iso(),
                "state_version": sv,
                "written_by": "mother_self_execute",
            }
            completion_file = _completion_file_path(task_id, task.get("tenant_context"))
            with open(completion_file, "w") as f:
                json.dump(completion_data, f, indent=2)

            # Verify completion marker (tenant-aware)
            marker_ok, marker_reason = _verify_completion_marker(
                task_id, task.get("attempts", 1), task.get("tenant_context")
            )
            if marker_ok:
                task["status"] = "validated"
                task["validated_at"] = now_iso()
                task["state_version"] = _next_state_version(task)
                task["mother_self_exec_success"] = True
                task["mother_validation"] = {
                    "passed": True,
                    "reason": "Mother self-execution succeeded",
                    "output_length": len(output),
                    "source": "mother_self_execute",
                }
                with open(state_file, "w") as f:
                    json.dump(task, f, indent=2)
                print(f"[Mother Agent] Mother self-execution succeeded for {task_id}")
                return {"validated": True, "output": output, "reason": "ok"}
            else:
                return {"validated": False, "output": output,
                        "reason": f"completion-marker-verify-failed: {marker_reason}"}
        else:
            reason = result.stderr[:200] if result.stderr else "non-zero exit or empty output"
            print(f"[Mother Agent] Mother self-execution failed for {task_id}: {reason}")
            return {"validated": False, "output": output, "reason": reason[:200]}
    except subprocess.TimeoutExpired:
        return {"validated": False, "output": "", "reason": "mother-self-execution-timeout"}
    except Exception as e:
        return {"validated": False, "output": "", "reason": str(e)[:200]}



def spawn_child_agent(task_id: str) -> Optional[bool]:
    """Spawn a child agent for the given task using the real OpenClaw CLI.

    Phase 2 features:
    - _design_harness() builds task-specific harness spec
    - _verify_harness_spec() verifies harness before spawn (Step 2.2)
    - load_template() injects template context (Phase 1)
    - Loop detection with loop_count and skip_child_respawn (Step 2.4)
    - Progress report at spawn time (Step 2.1)
    """

    state_file = _find_task_state_file(task_id)
    if not state_file:
        raise FileNotFoundError(f"Task state not found for {task_id}")
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

    # ── Phase 9: Runtime approval gate check before spawn ───────────────────
    approval_ok, approval_reason = _check_approval_gate(task)
    if not approval_ok:
        print(f"[Mother Agent] Approval gate blocked spawn for {task_id}: {approval_reason}")
        task["status"] = "blocked"
        task["updated_at"] = now_iso()
        task["approval_gate_reason"] = approval_reason
        with open(state_file, "w") as f:
            json.dump(task, f, indent=2)
        return False

    # ── Phase 4: Circuit breaker check before spawn ──────────────────────────
    task_type = task["task_type"]
    if _is_circuit_open(task_type):
        print(f"[Mother Agent] Circuit breaker OPEN for {task_type} — task {task_id} will not spawn child")
        task["status"] = "circuit_open"
        task["circuit_open_at"] = now_iso()
        task["updated_at"] = now_iso()
        with open(state_file, "w") as f:
            json.dump(task, f, indent=2)
        return False

    # ── Phase 10: RBAC — only SYSTEM can spawn child agents ─────────────────
    # Mother Agent is SYSTEM. The TRUSTED CALLER must wrap in SystemRole() before
    # calling this. We do NOT self-elevate here — that was the defect.
    # Direct import+call by lower-privilege callers (CLIENT, AGENT) must block.
    try:
        require_spawn_child_agent(task_id)
    except PermissionError as e:
        print(f"[Mother Agent] RBAC blocked spawn for {task_id}: {e}")
        task["status"] = "blocked"
        task["rbac_reason"] = str(e)
        task["updated_at"] = now_iso()
        with open(state_file, "w") as f:
            json.dump(task, f, indent=2)
        return False

    # ── Phase 4: Load-shedding check before spawn ───────────────────────────
    if _get_running_count() >= MAX_CONCURRENT_CHILDREN:
        print(f"[Mother Agent] Concurrency limit reached ({MAX_CONCURRENT_CHILDREN}) — queueing task {task_id}")
        queue_task(task_id, task)
        return False

    # Track this child as running
    _add_running(task_id)

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
                         harness_reminders=harness.get("dynamic_reminders", []),
                         tenant_context=task.get("tenant_context"))
    task["has_progress_update"] = False
    task["last_progress_at"] = now_iso()

    # Phase 1: Load template (fall back to inline harness if not found)
    # ── Phase 12 CANARY RUNTIME BRANCHING ─────────────────────────────────────────
    # If canary is deployed AND this task was routed to canary, load the canary
    # template variant instead of the stable template. This switches the child
    # agent's execution context to the canary version at spawn time — not just
    # metadata observation but actual template-level isolation.
    canary_routed = task.get("canary_routed", False)
    canary_active = is_canary_deployed()
    use_canary = canary_routed and canary_active

    if use_canary:
        template_content = load_template(task["task_type"], version="canary")
        harness_template_version = "canary-v1"
        canary_v = get_canary_version() or "unknown"
        print(f"[Mother Agent] CANARY ROUTING ACTIVE for {task_id} — canary build {canary_v}")
    else:
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

    # ── Phase 12 CANARY BUILD MARKER ─────────────────────────────────────────────
    # If canary routing is active, prepend an explicit canary build marker so
    # the child agent knows it is running on the experimental canary version.
    if use_canary:
        canary_v = get_canary_version() or "unknown"
        child_prompt_parts.append(
            f"\n{'=' * 60}\n"
            f"CANARY BUILD {canary_v}\n"
            f"{'=' * 60}\n"
            f">>> CANARY VARIANT: This task is running on canary build {canary_v}.\n"
            f">>> Report any anomalies or unexpected behavior in your completion notes.\n"
            f"\n"
        )

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
        "Progress Reports: write the tenant-scoped progress file for this task at start/progress/near_complete/done\n"
        "OUTPUT PATH: " + task["output_path"] + (task.get("output_ext") or ".txt") + "\n"
        "IMPORTANT: Return only the final output. No commentary. Write progress reports at checkpoints."
    )

    child_prompt = "".join(child_prompt_parts)
    task["harness_template_version"] = harness_template_version
    # ── Phase 12: record canary version in task state metadata ─────────────────
    if use_canary:
        task["canary_version"] = get_canary_version() or "unknown"
        task["canary_routed"] = True
    else:
        task["canary_version"] = task.get("canary_version")  # preserve existing

    cmd = [
        "openclaw", "agent", "--local",
        "--session-id", task["session_id"],
        "-m", child_prompt,
        "--timeout", str(CHILD_TIMEOUT),
    ]

    usable, usability_reason = False, "not attempted"
    result = None
    child_status = None
    # ── Phase 13: record wall-clock start for runtime-minute accounting ─────────
    _task_start_times[task_id] = time.time()
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
            _record_failure(task["task_type"])
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
            _record_failure(task["task_type"])
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
            _record_failure(task["task_type"])
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
            _record_success(task["task_type"])

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

            marker_ok, marker_reason = _verify_completion_marker(
                task_id, task["attempts"], task.get("tenant_context")
            )
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
            _record_failure(task["task_type"])

    except Exception as e:
        print("[Mother Agent] Child agent spawn error for " + task_id + ": " + str(e))
        task["status"] = "retry"
        task["updated_at"] = now_iso()
        task["last_error"] = str(e)[:200]
        op_id, cl_id = _tenant_ids_from_task(task)
        record_metric("error", "maa." + task["task_type"] + "_spawn_error",
                      details=str(e)[:200], agent="mother",
                      operator_id=op_id, client_id=cl_id)
        _record_failure(task["task_type"])

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

    # ── Phase 10 RBAC: require OPERATOR or SYSTEM for task execution ───────────
    assert_operator("run_task_chain")

    state_file = _find_task_state_file(task_id)
    if not state_file:
        return {"error": f"Task not found: {task_id}"}
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
            print(f"[Mother Agent] skip_child_respawn=True — jumping to Mother self-execution")
            break

        print(f"[Mother Agent] Attempt {attempt}/{MAX_RETRIES} for {task_id}")
        from access_control import SystemRole
        with SystemRole():
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
                # ── Phase 13: record actual runtime against daily quota ─────────────
                try:
                    start_ts = _task_start_times.pop(task_id, None)
                    if start_ts is not None:
                        elapsed = time.time() - start_ts
                        op_id = task.get("tenant_context", {}).get("operator_id", "default")
                        cl_id = task.get("tenant_context", {}).get("client_id", "default")
                        record_runtime_minutes(op_id, cl_id, task.get("task_type", ""), elapsed)
                        # Also record actual spend (Phase 13)
                        cost = estimate_task_cost(task.get("task_type", ""), elapsed)
                        record_spend(op_id, cl_id, task.get("task_type", ""), cost)
                except Exception as ex:
                    print(f"[Mother Agent] Warning: runtime accounting failed ({ex})")
                # ── Phase 11 DEDUP: mark as completed ─────────────────────────────
                try:
                    update_task_dedup_status(task_id, "completed")
                except Exception as ex:
                    print(f"[Mother Agent] Warning: dedup status not updated on success: {ex}")
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

    # All attempts exhausted (or skipped) — Mother Agent tries to self-execute
    # child_exhausted: all child agents have returned unusable output or failed
    with open(state_file) as f:
        task = json.load(f)
    task_type = task.get("task_type", "unknown")
    task["status"] = "exhausted"
    task["exhausted_at"] = now_iso()
    task["state_version"] = _next_state_version(task)
    task["mother_validation"] = {
        "passed": False,
        "reason": f"All {MAX_RETRIES} child agents failed; Mother self-execution attempted",
        "action": "escalate_to_mother",
    }
    with open(state_file, "w") as f:
        json.dump(task, f, indent=2)
    # Keep _task_start_times intact here so Mother self-execution time is included
    # in total runtime/spend accounting. Final accounting happens only on terminal
    # completion after the MSE path resolves.
    # ── Phase 11 DEDUP: mark as exhausted ──────────────────────────────────────
    try:
        update_task_dedup_status(task_id, "exhausted")
    except Exception as ex:
        print(f"[Mother Agent] Warning: dedup status not updated on exhaustion: {ex}")
    print(f"[Mother Agent] All attempts exhausted for {task_id} — Mother self-executing")
    record_metric("call", f"maa.{task_type}_mother_self_exec", agent="mother")
    mse_result = _mother_self_execute(task_id, task)
    if mse_result["validated"]:
        with open(state_file) as f:
            task = json.load(f)
        task["status"] = "validated"
        task["validated_at"] = now_iso()
        task["state_version"] = _next_state_version(task)
        task["mother_self_exec_success"] = True
        task["mother_validation"] = {
            "passed": True,
            "reason": "Mother self-execution succeeded after child exhaustion",
            "output_length": len(mse_result.get("output", "")),
            "source": "mother_self_execute",
        }
        with open(state_file, "w") as f:
            json.dump(task, f, indent=2)
        print(f"[Mother Agent] Mother self-execution succeeded for {task_id} — status=validated")
        # ── Phase 13: record runtime for full chain including MSE success ─────────
        try:
            start_ts = _task_start_times.pop(task_id, None)
            if start_ts is not None:
                elapsed = time.time() - start_ts
                op_id = task.get("tenant_context", {}).get("operator_id", "default")
                cl_id = task.get("tenant_context", {}).get("client_id", "default")
                record_runtime_minutes(op_id, cl_id, task_type, elapsed)
                record_spend(op_id, cl_id, task_type, estimate_task_cost(task_type, elapsed))
        except Exception as ex:
            print(f"[Mother Agent] Warning: runtime accounting failed on MSE success ({ex})")
        return task
    else:
        with open(state_file) as f:
            task = json.load(f)
        task["status"] = "exhausted"
        task["mother_self_exec_success"] = False
        task["mother_self_exec_failure_reason"] = mse_result["reason"]
        task["mother_validation"] = {
            "passed": False,
            "reason": f"All child agents failed. Mother self-execution also failed: {mse_result['reason']}",
            "action": "escalate_to_operator",
        }
        task["state_version"] = _next_state_version(task)
        with open(state_file, "w") as f:
            json.dump(task, f, indent=2)
        print(f"[Mother Agent] Mother self-execution failed for {task_id}: {mse_result['reason']} — escalating to operator")
        # ── Phase 13: record runtime for full chain including MSE failure ─────────
        try:
            start_ts = _task_start_times.pop(task_id, None)
            if start_ts is not None:
                elapsed = time.time() - start_ts
                op_id = task.get("tenant_context", {}).get("operator_id", "default")
                cl_id = task.get("tenant_context", {}).get("client_id", "default")
                record_runtime_minutes(op_id, cl_id, task_type, elapsed)
                record_spend(op_id, cl_id, task_type, estimate_task_cost(task_type, elapsed))
        except Exception as ex:
            print(f"[Mother Agent] Warning: runtime accounting failed on MSE failure ({ex})")
        return task
    
    return task


def run_validation(task_id: str, validator_prompt: str) -> dict:
    """Mother Agent validates child output via a validation child agent.
    
    HARD RULE: No validation file = validation FAILED.
    Validation must produce a real .validation JSON file or it doesn't count.
    """
    
    state_file = _find_task_state_file(task_id)
    if not state_file:
        return {"passed": False, "reason": f"Task state not found: {task_id}"}
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
    
    tc = parse_tenant_context(task.get("tenant_context"))
    if tc.is_default():
        validation_file = f"{LOGS_DIR}/{task_id}.validation"
    else:
        resolver = TenantPathResolver(tc)
        validation_file = str(resolver.resolve_log_file(task_id, "validation"))
    
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
    if not TENANTS_ROOT.exists():
        return {"error": "Task not found"}
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
    """List all tasks across default and tenant-scoped task directories."""
    tasks = []
    seen = set()

    # Scan default tasks dir
    if os.path.isdir(TASKS_DIR):
        for f in os.listdir(TASKS_DIR):
            if f.endswith(".json"):
                with open(os.path.join(TASKS_DIR, f)) as fh:
                    tasks.append(json.load(fh))
                seen.add(f)

    # Scan tenant-scoped task directories
    from tenant_paths import TENANTS_ROOT
    if TENANTS_ROOT.exists():
        for op_dir in TENANTS_ROOT.iterdir():
            if not op_dir.is_dir():
                continue
            op_tasks = op_dir / "tasks"
            if op_tasks.is_dir():
                for f in op_tasks.iterdir():
                    if f.name.endswith(".json") and f.name not in seen:
                        try:
                            tasks.append(json.loads(f.read_text()))
                            seen.add(f.name)
                        except Exception:
                            continue
            clients_dir = op_dir / "clients"
            if not clients_dir.is_dir():
                continue
            for cl_dir in clients_dir.iterdir():
                if not cl_dir.is_dir():
                    continue
                cl_tasks = cl_dir / "tasks"
                if not cl_tasks.is_dir():
                    continue
                for f in cl_tasks.iterdir():
                    if f.name.endswith(".json") and f.name not in seen:
                        try:
                            tasks.append(json.loads(f.read_text()))
                            seen.add(f.name)
                        except Exception:
                            continue

    return sorted(tasks, key=lambda x: x.get("updated_at", ""), reverse=True)


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


# ── Phase 3: Background Progress Poller ─────────────────────────────────────────
# Runs every 60 seconds, scans all running/mother_self_executing tasks,
# fires canonical progress delivery for any task past PROGRESS_PING_AT threshold.

_progress_poller_lock = __import__("threading").Lock()
_progress_poller_running = False

def _run_progress_poller(interval_seconds: int = 60) -> None:
    """Background thread: scan all running tasks and deliver progress updates.

    This is a transport-agnostic poller — it writes canonical progress payloads
    to signal files. The runtime interaction router (channel-specific) reads these
    files and surfaces updates to the requester or operator. No hard-coded Telegram/WhatsApp logic.

    Scan scope: all tasks with status in {running, mother_self_executing}.
    Delivery: exactly one initial ping per task attempt (after PROGRESS_PING_AT);
              optionally a second ping if still running after PROGRESS_PING_2_AT (10 min).
    """
    global _progress_poller_running
    import threading

    def _poller_loop():
        global _progress_poller_running
        while _progress_poller_running:
            try:
                _scan_and_ping()
            except Exception as e:
                print(f"[Mother Agent] Progress poller error: {e}", file=sys.stderr)
            time.sleep(interval_seconds)

    poller_thread = threading.Thread(target=_poller_loop, daemon=True, name="progress-poller")
    poller_thread.start()
    print(f"[Mother Agent] Background progress poller started (interval={interval_seconds}s)")


def _scan_and_ping_dir(tasks_dir: str, now_ts: float) -> None:
    """Scan a single task directory (helper for tenant-scoped polling)."""
    try:
        task_files = [f for f in os.listdir(tasks_dir) if f.endswith(".json")]
    except Exception:
        return
    for fname in task_files:
        state_path = os.path.join(tasks_dir, fname)
        try:
            with open(state_path) as f:
                task = json.load(f)
        except Exception:
            continue
        if task.get("status") not in {"running", "mother_self_executing"}:
            continue
        task_id = task.get("task_id") or fname[:-5]
        task_type = task.get("task_type", "unknown")
        attempt = task.get("attempts", 0)
        if attempt == 0:
            attempt = 1
        updated_at = (
            task.get("updated_at") or
            task.get("mother_self_exec_at") or
            task.get("created_at") or
            now_iso()
        )
        try:
            created_ts = datetime.strptime(updated_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC).timestamp()
        except Exception:
            created_ts = now_ts
        elapsed = int(now_ts - created_ts)
        if elapsed < PROGRESS_PING_AT:
            continue
        _deliver_progress_update(
            task_id=task_id,
            task_type=task_type,
            attempt=attempt,
            elapsed_seconds=elapsed,
            current_action=task.get("current_action", "child_agent_executing"),
            next_expected_step=task.get("next_expected_step", "completion_marker_or_next_retry"),
            tenant_context=task.get("tenant_context"),
        )


def _scan_and_ping() -> None:
    """Scan all task state files (default + tenant-scoped), fire progress pings."""
    now_ts = time.time()
    try:
        task_files = [f for f in os.listdir(TASKS_DIR) if f.endswith(".json")]
    except Exception:
        return

    for fname in task_files:
        state_path = os.path.join(TASKS_DIR, fname)
        try:
            with open(state_path) as f:
                task = json.load(f)
        except Exception:
            continue

        if task.get("status") not in {"running", "mother_self_executing"}:
            continue

        task_id = task.get("task_id") or fname[:-5]
        task_type = task.get("task_type", "unknown")
        attempt = task.get("attempts", 0)
        if attempt == 0:
            attempt = 1

        # Compute elapsed seconds
        updated_at = (
            task.get("updated_at") or
            task.get("mother_self_exec_at") or
            task.get("created_at") or
            now_iso()
        )
        try:
            created_ts = datetime.strptime(updated_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC).timestamp()
        except Exception:
            created_ts = now_ts
        elapsed = int(now_ts - created_ts)

        if elapsed < PROGRESS_PING_AT:
            continue

        # Delegate to canonical deliver (handles dedup + payload)
        _deliver_progress_update(
            task_id=task_id,
            task_type=task_type,
            attempt=attempt,
            elapsed_seconds=elapsed,
            current_action=task.get("current_action", "child_agent_executing"),
            next_expected_step=task.get("next_expected_step", "completion_marker_or_next_retry"),
            tenant_context=task.get("tenant_context"),
        )

    # ── Also scan tenant-scoped task directories ──────────────────────────────
    from tenant_paths import TENANTS_ROOT
    try:
        for op_dir in TENANTS_ROOT.iterdir():
            if not op_dir.is_dir():
                continue
            # operator-level tasks
            op_tasks = op_dir / "tasks"
            if op_tasks.is_dir():
                _scan_and_ping_dir(op_tasks, now_ts)
            # client-level tasks
            clients_dir = op_dir / "clients"
            if not clients_dir.is_dir():
                continue
            for cl_dir in clients_dir.iterdir():
                if not cl_dir.is_dir():
                    continue
                cl_tasks = cl_dir / "tasks"
                if cl_tasks.is_dir():
                    _scan_and_ping_dir(cl_tasks, now_ts)
    except Exception:
        pass  # scans non-existent tenant root are harmless


def start_progress_poller(interval_seconds: int = 60) -> None:
    """Start the background progress poller. Idempotent — only one poller runs."""
    global _progress_poller_running
    with _progress_poller_lock:
        if _progress_poller_running:
            print("[Mother Agent] Progress poller already running, skipping start.")
            return
        _progress_poller_running = True
    _run_progress_poller(interval_seconds)


# ── Startup reconciliation for restart/resume safety ──────────────────────────
def _iter_all_task_state_files() -> list[str]:
    """Return all known task state files across default and tenant-scoped paths."""
    state_files: list[str] = []
    if os.path.isdir(TASKS_DIR):
        state_files.extend(
            os.path.join(TASKS_DIR, name)
            for name in os.listdir(TASKS_DIR)
            if name.endswith(".json")
        )
    from tenant_paths import TENANTS_ROOT
    if not TENANTS_ROOT.exists():
        return state_files
    for op_dir in TENANTS_ROOT.iterdir():
        if not op_dir.is_dir():
            continue
        op_tasks = op_dir / "tasks"
        if op_tasks.is_dir():
            state_files.extend(str(p) for p in op_tasks.glob("*.json"))
        clients_dir = op_dir / "clients"
        if not clients_dir.is_dir():
            continue
        for cl_dir in clients_dir.iterdir():
            if not cl_dir.is_dir():
                continue
            cl_tasks = cl_dir / "tasks"
            if cl_tasks.is_dir():
                state_files.extend(str(p) for p in cl_tasks.glob("*.json"))
    return state_files


def _find_task_state_file(task_id: str) -> str | None:
    """Locate a task state file by task_id across default and tenant paths."""
    default_path = f"{TASKS_DIR}/{task_id}.json"
    if os.path.exists(default_path):
        return default_path
    for state_file in _iter_all_task_state_files():
        if os.path.basename(state_file) == f"{task_id}.json":
            return state_file
    return None


def _reconcile_running_children() -> None:
    persisted = _load_running_children()
    live = set()
    for task_id in persisted:
        state_file = _find_task_state_file(task_id)
        if not state_file:
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
    for state_file in _iter_all_task_state_files():
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


def initialize_runtime_services(interval_seconds: int = 60) -> None:
    """Explicit runtime startup hook.

    Safe to call multiple times. Keeps import side effects out of tests and utility imports.
    """
    _reconcile_running_children()
    _mark_stale_running_tasks()
    start_progress_poller(interval_seconds=interval_seconds)

if __name__ == "__main__":
    initialize_runtime_services(interval_seconds=60)

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
    
    gate_p = subparsers.add_parser("gate-status", help="Show last pre-deploy gate result")
    
    args = parser.parse_args()

    # ── Phase 10: RBAC — all CLI commands require OPERATOR role ───────────────
    try:
        require_operator_role()
    except PermissionError as e:
        print(f"RBAC: {e}")
        sys.exit(1)
    except SystemExit:
        raise  # preserve exit(1) from require_operator_role()

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
    
    elif args.command == "gate-status":
        import pathlib
        latest = pathlib.Path(WORKSPACE) / "logs" / "pre_deploy_gate_latest.json"
        if not latest.exists():
            print("No pre-deploy gate result found. Run pre_deploy_gate.sh to generate one.")
            sys.exit(1)
        import json
        with open(latest) as f:
            data = json.load(f)
        status_icon = "\033[92m✅\033[0m" if data.get("status") == "pass" else "\033[91m❌\033[0m"
        print()
        print(f"  Pre-Deploy Gate Result")
        print(f"  ─────────────────────")
        print(f"  Status:     {status_icon} {data.get('status', 'unknown').upper()}")
        print(f"  Passed:     {data.get('passed', '?')}/{data.get('passed', 0) + data.get('failed', 0)}")
        print(f"  Failed:     {data.get('failed', '?')}")
        print(f"  Run at:     {data.get('run_at', 'unknown')}")
        print(f"  Alert sent: {'Yes' if data.get('alert_sent') else 'No'}")
        failures = data.get("failures", [])
        if failures:
            print(f"  \n  Failures:")
            for f in failures:
                print(f"    • [{f.get('test','?')}] {f.get('reason','?')}")
        print()
    else:
        parser.print_help()


