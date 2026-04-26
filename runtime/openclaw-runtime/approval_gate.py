#!/usr/bin/env python3
"""
MAA PROTOCOL — RUNTIME APPROVAL GATE
Version: 1.0
Manages approval_state.json for external action enforcement.

Usage:
  python3 approval_gate.py create --agent mother --task-id X --action-type email_send \\
    --target recipient@example.com --body-summary "Summary" --tenant-id default
  python3 approval_gate.py check --hash <hash>
  python3 approval_gate.py approve --hash <hash> --token APPROVE_TO_SEND
  python3 approval_gate.py reject --hash <hash>
  python3 approval_gate.py list-pending
"""

import hashlib
import json
import os
import sys
import time
import argparse
from pathlib import Path
from datetime import datetime, timezone, timedelta

# ── paths ─────────────────────────────────────────────────────────────────────
WORKSPACE       = Path("/root/.openclaw/workspace")
OPS_DIR         = WORKSPACE / "ops/multi-agent-orchestrator"
EMAIL_DATA_DIR  = WORKSPACE / "data/email"
APPROVAL_STATE  = EMAIL_DATA_DIR / "approval_state.json"
AUDIT_LOG       = EMAIL_DATA_DIR / "approval_audit.jsonl"
EXPIRY_HOURS    = 2

# ── helpers ───────────────────────────────────────────────────────────────────
def load_state():
    if APPROVAL_STATE.exists():
        with open(APPROVAL_STATE) as f:
            return json.load(f)
    return {"approvals": {}}

def save_state(state):
    EMAIL_DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = str(APPROVAL_STATE) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, APPROVAL_STATE)

def _action_hash(action_type, target, body_summary, tenant_id):
    raw = f"{action_type}|{target}|{body_summary}|{tenant_id}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]

def _now():
    return datetime.now(timezone.utc).isoformat()

def _expiry():
    exp = datetime.now(timezone.utc) + timedelta(hours=EXPIRY_HOURS)
    return exp.isoformat()

APPROVAL_REQUIRED_TYPES = {
    "email_send", "calendar_write", "web_post",
    "file_external", "api_write", "client_data_delete"
}

VALID_TOKENS = {"approve to send", "send now", "approved"}

def append_audit(action_hash, from_status, to_status, by, task_id):
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "at": _now(),
        "action_hash": action_hash,
        "from_status": from_status,
        "to_status": to_status,
        "by": by,
        "task_id": task_id
    }
    with open(AUDIT_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")

# ── commands ──────────────────────────────────────────────────────────────────

def _require_operator():
    """Enforce OPERATOR role for all command invocations (CLI and direct import)."""
    from access_control import assert_operator
    assert_operator("approval_gate.command")


def cmd_create(args):
    _require_operator()
    if args.action_type not in APPROVAL_REQUIRED_TYPES:
        print(f"Note: {args.action_type} does not require approval (not in required types)")
        print(f"  Required types: {sorted(APPROVAL_REQUIRED_TYPES)}")

    ahash = _action_hash(args.action_type, args.target, args.body_summary, args.tenant_id)
    state = load_state()

    # Idempotent: return existing if same hash is still pending
    if ahash in state["approvals"]:
        entry = state["approvals"][ahash]
        print(f"Existing approval entry found:")
        print(f"  hash:    {ahash}")
        print(f"  status:  {entry['status']}")
        print(f"  target:  {entry['target']}")
        return

    entry = {
        "action_hash": ahash,
        "requested_by": args.agent,
        "task_id": args.task_id,
        "action_type": args.action_type,
        "target": args.target,
        "body_summary": args.body_summary[:80],
        "status": "pending",
        "approved_by": None,
        "approved_at": None,
        "approver_token": None,
        "expires_at": _expiry(),
        "created_at": _now()
    }
    state["approvals"][ahash] = entry
    save_state(state)

    print(f"Approval pending:")
    print(f"  hash:      {ahash}")
    print(f"  type:      {args.action_type}")
    print(f"  target:    {args.target}")
    print(f"  task:      {args.task_id}")
    print(f"  expires:   {entry['expires_at']}")

def cmd_check(args):
    # Read-only: no RBAC required
    state = load_state()
    entry = state["approvals"].get(args.hash)
    if not entry:
        print(f"No approval found for hash: {args.hash}")
        return 1

    # Check expiry
    status = entry["status"]
    if status == "pending":
        expires_at = datetime.fromisoformat(entry["expires_at"])
        if datetime.now(timezone.utc) > expires_at:
            entry["status"] = "expired"
            save_state(state)
            status = "expired"

    print(f"Status: {status}")
    print(f"  type:    {entry['action_type']}")
    print(f"  target:  {entry['target']}")
    print(f"  by:      {entry['requested_by']}")
    print(f"  expires: {entry['expires_at']}")
    return 0

def cmd_approve(args):
    _require_operator()
    token = args.token.lower().strip()
    if token not in VALID_TOKENS:
        print(f"Invalid approval token: {args.token!r}")
        print(f"Valid tokens: {sorted(VALID_TOKENS)}")
        return 1

    state = load_state()
    entry = state["approvals"].get(args.hash)
    if not entry:
        print(f"No approval found for hash: {args.hash}")
        return 1

    if entry["status"] == "approved":
        print(f"Already approved at {entry['approved_at']}")
        return 0

    entry["status"]      = "approved"
    entry["approved_by"] = "partha"
    entry["approved_at"] = _now()
    entry["approver_token"] = args.token.upper()
    save_state(state)
    append_audit(args.hash, "pending", "approved", "partha", entry.get("task_id",""))
    print(f"Approved: {args.hash}")
    return 0

def cmd_reject(args):
    _require_operator()
    state = load_state()
    entry = state["approvals"].get(args.hash)
    if not entry:
        print(f"No approval found for hash: {args.hash}")
        return 1

    prev = entry["status"]
    entry["status"]      = "rejected"
    entry["approved_by"] = "partha"
    entry["approved_at"] = _now()
    save_state(state)
    append_audit(args.hash, prev, "rejected", "partha", entry.get("task_id",""))
    print(f"Rejected: {args.hash}")
    return 0

def cmd_list_pending(args):
    # Read-only: no RBAC required
    state = load_state()
    pending = [
        (h, e) for h, e in state["approvals"].items()
        if e["status"] == "pending"
    ]
    if not pending:
        print("No pending approvals.")
        return 0

    print(f"{len(pending)} pending approval(s):")
    for h, e in pending:
        expires = e["expires_at"]
        print(f"  {h}")
        print(f"    type:    {e['action_type']}")
        print(f"    target:  {e['target']}")
        print(f"    task:    {e.get('task_id','—')}")
        print(f"    by:      {e['requested_by']}")
        print(f"    expires: {expires}")
        print()
    return 0

# ── main ───────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(prog="approval_gate.py")
    sub = parser.add_subparsers()

    p_create = sub.add_parser("create")
    p_create.add_argument("--agent", required=True)
    p_create.add_argument("--task-id", required=True)
    p_create.add_argument("--action-type", required=True)
    p_create.add_argument("--target", required=True)
    p_create.add_argument("--body-summary", required=True)
    p_create.add_argument("--tenant-id", default="default")
    p_create.set_defaults(func=cmd_create)

    p_check = sub.add_parser("check")
    p_check.add_argument("--hash", required=True)
    p_check.set_defaults(func=cmd_check)

    p_approve = sub.add_parser("approve")
    p_approve.add_argument("--hash", required=True)
    p_approve.add_argument("--token", required=True)
    p_approve.set_defaults(func=cmd_approve)

    p_reject = sub.add_parser("reject")
    p_reject.add_argument("--hash", required=True)
    p_reject.set_defaults(func=cmd_reject)

    p_list = sub.add_parser("list-pending")
    p_list.set_defaults(func=cmd_list_pending)

    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        return 0

    try:
        return args.func(args) or 0
    except Exception as e:
        print(f"Error: {e}")
        return 1

if __name__ == "__main__":
    # ── Phase 10 RBAC: all CLI commands require OPERATOR role ─────────────────
    sys.path.insert(0, str(Path(__file__).parent))
    from access_control import require_operator_role
    try:
        require_operator_role()
    except PermissionError as e:
        print(f"RBAC: {e}", file=sys.stderr)
        sys.exit(1)
    except SystemExit:
        raise
    sys.exit(main())
