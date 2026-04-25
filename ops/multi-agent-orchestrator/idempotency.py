#!/usr/bin/env python3
"""
Idempotency & Duplicate Protection Layer
========================================
Provides deduplication for task submissions, side-effect operations, and
approval decisions across the multi-agent orchestrator.

Three dedup namespaces:
  task  — prevents double-submission of identical tasks by same tenant
  side_effect — prevents double-send of email/calendar/web actions (24h window)
  approval — prevents double-approval of the same action hash

Registry files:
  data/observability/task_dedup_registry.json   — task dedup store
  data/email/send_audit/send_registry.json      — email send dedup store
  data/email/approval_state.json                — approval dedup (shared with approval_gate)

All reads/writes are atomic (write to .tmp, then rename).

Author: Maa maintainer
Phase: 11 of MAA Protocol Commercial Deployment Action Plan v1.2
"""

import hashlib
import json
import os
import time
from datetime import datetime, UTC
from pathlib import Path
from typing import Optional

# ── Constants ─────────────────────────────────────────────────────────────────

DEDUP_REGISTRY_DIR = Path("/root/.openclaw/workspace/data/observability")
EMAIL_SEND_REGISTRY = Path("/root/.openclaw/workspace/data/email/send_audit/send_registry.json")
APPROVAL_STATE_FILE = Path("/root/.openclaw/workspace/data/email/approval_state.json")

TASK_DEDUP_REGISTRY = DEDUP_REGISTRY_DIR / "task_dedup_registry.json"
EMAIL_SEND_WINDOW_S = 86400  # 24 hours
TASK_EXHAUSTED_STATUSES = {"exhausted", "completed", "validated", "circuit_open"}


# ── Atomic JSON helpers ───────────────────────────────────────────────────────

def _atomic_write_json(path: Path, data: dict) -> None:
    """Write dict to path atomically: write to .tmp, then atomic rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    tmp.replace(path)


def _atomic_read_json(path: Path) -> dict:
    """Read dict from path. Returns empty dict if file missing."""
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


# ── Task dedup ────────────────────────────────────────────────────────────────

def _make_task_hash(task_type: str, input_summary: str, tenant_id: str) -> str:
    """SHA256 hash of the dedup key tuple."""
    raw = f"{task_type}::::{input_summary}::::{tenant_id}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _get_task_dedup_registry() -> dict:
    """Load the task dedup registry, creating it if absent."""
    if not DEDUP_REGISTRY_DIR.exists():
        DEDUP_REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
    registry = _atomic_read_json(TASK_DEDUP_REGISTRY)
    # Garbage-collect entries older than 30 days (safe window beyond any retry)
    cutoff = time.time() - (30 * 86400)
    cleaned = {}
    for k, v in registry.items():
        submitted_at = v.get("submitted_at", "")
        try:
            ts = datetime.fromisoformat(submitted_at.replace("Z", "+00:00")).timestamp()
        except Exception:
            ts = 0
        if ts >= cutoff:
            cleaned[k] = v
    if len(cleaned) < len(registry):
        _atomic_write_json(TASK_DEDUP_REGISTRY, cleaned)
        registry = cleaned
    return registry


def _save_task_dedup_registry(registry: dict) -> None:
    """Save the task dedup registry atomically."""
    _atomic_write_json(TASK_DEDUP_REGISTRY, registry)


def submit_task_dedup(task_type: str, input_summary: str, tenant_id: str) -> Optional[str]:
    """
    Check if an identical task (same task_type + input_summary + tenant_id) was
    already submitted and has NOT been exhausted.

    Returns existing task_id if found and still active, else None.
    The caller is responsible for acting on the returned task_id.

    Deduplication key: SHA256(task_type || input_summary || tenant_id)
    """
    key_hash = _make_task_hash(task_type, input_summary, tenant_id)
    registry = _get_task_dedup_registry()
    entry_key = f"task:{key_hash}"
    entry = registry.get(entry_key)

    if entry is not None:
        existing_task_id = entry.get("task_id", "")
        status = entry.get("status", "")
        if existing_task_id and status not in TASK_EXHAUSTED_STATUSES:
            # Active task already exists for this input — return it for caller to reuse
            return existing_task_id

    # No active duplicate found — caller should proceed with submission
    # (the submitting function will register the new entry)
    return None


def register_task_submission(task_id: str, task_type: str,
                             input_summary: str, tenant_id: str,
                             status: str = "pending") -> None:
    """
    Register a new task submission in the dedup registry.
    Called by the orchestrator after task state file is written.
    """
    key_hash = _make_task_hash(task_type, input_summary, tenant_id)
    registry = _get_task_dedup_registry()
    entry_key = f"task:{key_hash}"
    registry[entry_key] = {
        "task_id": task_id,
        "task_type": task_type,
        "input_summary": input_summary[:200] if input_summary else "",
        "tenant_id": tenant_id,
        "submitted_at": datetime.now(UTC).isoformat(),
        "status": status,
    }
    _save_task_dedup_registry(registry)


def update_task_dedup_status(task_id: str, status: str) -> None:
    """
    Update the dedup registry status for a task.
    Called when task transitions to terminal states (completed, exhausted, etc.).
    """
    registry = _get_task_dedup_registry()
    changed = False
    for entry in registry.values():
        if entry.get("task_id") == task_id:
            entry["status"] = status
            changed = True
    if changed:
        _save_task_dedup_registry(registry)


# ── Side-effect (email/send) dedup ────────────────────────────────────────────

def _make_email_key(action_type: str, target: str, body_hash: str) -> str:
    return f"{action_type}:{target}:{body_hash}"


def _body_to_hash(body: str) -> str:
    """Normalize and hash email body for dedup comparison."""
    normalized = " ".join(body.split()).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _get_email_send_registry() -> dict:
    """Load the email send dedup registry, creating it if absent."""
    if not EMAIL_SEND_REGISTRY.parent.exists():
        EMAIL_SEND_REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    registry = _atomic_read_json(EMAIL_SEND_REGISTRY)
    # Prune entries older than EMAIL_SEND_WINDOW_S
    cutoff = time.time() - EMAIL_SEND_WINDOW_S
    cleaned = {}
    for k, v in registry.items():
        sent_at = v.get("sent_at", "")
        try:
            ts = datetime.fromisoformat(sent_at.replace("Z", "+00:00")).timestamp()
        except Exception:
            ts = 0
        if ts >= cutoff:
            cleaned[k] = v
    if len(cleaned) < len(registry):
        _atomic_write_json(EMAIL_SEND_REGISTRY, cleaned)
        registry = cleaned
    return registry


def _save_email_send_registry(registry: dict) -> None:
    """Save the email send registry atomically."""
    _atomic_write_json(EMAIL_SEND_REGISTRY, registry)


def side_effect_dedup(action_type: str, target: str, body: str) -> bool:
    """
    Check if an identical side-effect action (same type + target + body hash)
    was already sent within the last 24 hours.

    Returns True  — duplicate found, caller should SKIP the send
    Returns False — not a duplicate, caller may proceed
    """
    body_hash = _body_to_hash(body)
    registry = _get_email_send_registry()
    key = _make_email_key(action_type, target, body_hash)
    return key in registry


def register_side_effect(action_type: str, target: str, body: str) -> None:
    """
    Register a side-effect action in the send registry.
    Called after successful send.
    """
    body_hash = _body_to_hash(body)
    registry = _get_email_send_registry()
    key = _make_email_key(action_type, target, body_hash)
    registry[key] = {
        "action_type": action_type,
        "target": target,
        "body_hash": body_hash,
        "sent_at": datetime.now(UTC).isoformat(),
        "skip": True,
    }
    _save_email_send_registry(registry)


# ── Approval dedup ────────────────────────────────────────────────────────────

def _get_approval_state() -> dict:
    """Load approval state, creating it if absent."""
    if not APPROVAL_STATE_FILE.parent.exists():
        APPROVAL_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    return _atomic_read_json(APPROVAL_STATE_FILE)


def _save_approval_state(state: dict) -> None:
    """Save approval state atomically."""
    _atomic_write_json(APPROVAL_STATE_FILE, state)


def approval_dedup(action_hash: str) -> bool:
    """
    Check if an action_hash already has an entry in the approval state store.

    Returns True  — entry exists (approved/pending/expired), caller should NOT re-approve
    Returns False — no prior entry, caller may proceed with fresh approval request
    """
    state = _get_approval_state()
    approvals = state.get("approvals", {})
    return action_hash in approvals


# ── CLI for testing / maintenance ─────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Idempotency layer CLI")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("task-check", help="Check task dedup")
    p.add_argument("--task-type", required=True)
    p.add_argument("--input-summary", required=True)
    p.add_argument("--tenant-id", required=True)

    p = sub.add_parser("email-check", help="Check email send dedup")
    p.add_argument("--action-type", required=True)
    p.add_argument("--target", required=True)
    p.add_argument("--body", required=True)

    p = sub.add_parser("approval-check", help="Check approval dedup")
    p.add_argument("--action-hash", required=True)

    p = sub.add_parser("task-register", help="Register task submission")
    p.add_argument("--task-id", required=True)
    p.add_argument("--task-type", required=True)
    p.add_argument("--input-summary", required=True)
    p.add_argument("--tenant-id", required=True)

    p = sub.add_parser("email-register", help="Register email send")
    p.add_argument("--action-type", required=True)
    p.add_argument("--target", required=True)
    p.add_argument("--body", required=True)

    args = parser.parse_args()

    if args.cmd == "task-check":
        result = submit_task_dedup(args.task_type, args.input_summary, args.tenant_id)
        if result:
            print(f"DUPLICATE FOUND — existing task_id: {result}")
        else:
            print("No duplicate — clear to submit")

    elif args.cmd == "email-check":
        dup = side_effect_dedup(args.action_type, args.target, args.body)
        if dup:
            print("DUPLICATE SEND — would skip")
        else:
            print("No duplicate — clear to send")

    elif args.cmd == "approval-check":
        dup = approval_dedup(args.action_hash)
        if dup:
            print("APPROVAL EXISTS — would skip")
        else:
            print("No prior approval — clear to request")

    elif args.cmd == "task-register":
        register_task_submission(args.task_id, args.task_type,
                                 args.input_summary, args.tenant_id)
        print(f"Registered: {args.task_id}")

    elif args.cmd == "email-register":
        register_side_effect(args.action_type, args.target, args.body)
        print("Registered send")


if __name__ == "__main__":
    main()
