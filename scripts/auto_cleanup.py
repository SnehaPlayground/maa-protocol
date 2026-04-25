#!/usr/bin/env python3
"""
Auto Cleanup — Delete aged files in temp/data directories and stale task state.
========================================
Deletes aged files in temp/data directories and stale task state.
Never touches active task state files or control files.

Retention policy:
  - Metrics, task state, and log files: deleted only if older than RETENTION_DAYS (90 days)
  - Completion markers and validation reports: NEVER deleted (audit trail, excluded regardless of age)
  - Temp dirs: deleted if older than --days threshold (default 7, allows fast cleanup of scratch)

Task state files (tasks/*.json) are cleaned when:
  - status is 'exhausted' or 'completed'
  - file is older than RETENTION_DAYS (90 days)
  - NOT cleaned: 'pending', 'running', 'queued', 'needs_revision', 'validated'

Tenant-scoped task state (tenants/{op}/clients/{client}/tasks/*.json) follows the same
retention policy as the legacy tasks/ directory.

Usage:
    python3 auto_cleanup.py                # default cleanup (7-day temp / 90-day state)
    python3 auto_cleanup.py --days 3       # custom age threshold for temp dirs
    python3 auto_cleanup.py --dry-run       # show what would be removed
    python3 auto_cleanup.py --tenant OP001  # clean only a specific operator's tenant dirs
"""

import argparse
import json
import os
import time
from datetime import datetime, UTC
from pathlib import Path

WORKSPACE = Path("/root/.openclaw/workspace")

TEMP_DIRS = [
    WORKSPACE / "temp",
    WORKSPACE / "data" / "email",
    WORKSPACE / "data" / "reports",
    WORKSPACE / "data" / "transcripts",
]

# Legacy unified tasks dir
LEGACY_TASKS_DIR = WORKSPACE / "ops" / "multi-agent-orchestrator" / "tasks"

# Tenant-scoped tasks dirs (discovered at runtime)
TENANTS_ROOT = WORKSPACE / "tenants"

EXCLUDE_DIRS = [
    WORKSPACE / "ops" / "multi-agent-orchestrator" / "logs",
]
RETENTION_DAYS = 90  # Phase 11: 90-day retention for metrics/task/log files

EXCLUDE_FILES = {
    "AGENTS.md", "SOUL.md", "MEMORY.md", "SECURITY.md", "USER.md", "IDENTITY.md"
}

# Task statuses that are SAFE to auto-cleanup (stale terminal states)
CLEANABLE_TASK_STATUSES = {"exhausted", "completed"}

# Task statuses that are ACTIVE and must never be auto-cleaned
ACTIVE_TASK_STATUSES = {
    "pending", "running", "queued", "needs_revision",
    "validated", "circuit_open", "mother_self_executing",
}

LOG_FILE = WORKSPACE / "logs" / "cleanup.log"


def _is_cleanable_task_state(filepath: str) -> bool:
    """Check if a tasks/*.json file is cleanable (exhausted/completed + old enough).

    Returns (is_cleanable: bool, reason: str).
    """
    try:
        with open(filepath) as f:
            task = json.load(f)
        status = task.get("status", "")
        if status in CLEANABLE_TASK_STATUSES:
            return True, f"status={status}"
        elif status in ACTIVE_TASK_STATUSES:
            return False, f"active status={status}"
        else:
            # Unknown status — be conservative, skip it
            return False, f"unknown status={status}"
    except (json.JSONDecodeError, IOError, KeyError):
        # Corrupt or unrecognized file — skip to be safe
        return False, "parse error or missing status"


def should_skip(path: str, days: int = 7) -> tuple[bool, str]:
    """Return (skip: bool, reason: str). False means the file may be cleaned.

    Retention tiers:
      - Completion markers (.completion) and validation reports (.validation): ALWAYS skip
      - Task state files (tasks/*.json or tenants/.../tasks/*.json): only skip active
        statuses; clean terminal states if older than RETENTION_DAYS (90 days)
      - Temp/data files: clean if older than the `days` parameter threshold
    """
    p = Path(path)

    # Exclude specific dirs entirely
    for ex in EXCLUDE_DIRS:
        if str(p).startswith(str(ex)):
            return True, f"excluded dir {ex}"

    # Exclude control files by basename
    if p.name in EXCLUDE_FILES:
        return True, "control file"

    # Completion markers and validation reports are NEVER deleted
    if p.suffix in (".completion", ".validation"):
        return True, "marker/validation file"

    # Handle task state files — only clean stale terminal states older than RETENTION_DAYS
    is_task_file = (
        str(p).startswith(str(LEGACY_TASKS_DIR)) or
        "/tasks/" in str(p)
    ) and p.suffix == ".json"

    if is_task_file:
        cleanable, reason = _is_cleanable_task_state(path)
        if not cleanable:
            return True, reason
        # Task state is cleanable (exhausted/completed) — check against RETENTION_DAYS
        retention_cutoff = time.time() - RETENTION_DAYS * 86400
        try:
            if os.stat(path).st_mtime >= retention_cutoff:
                return True, f"not yet past {RETENTION_DAYS}-day retention threshold"
        except OSError:
            return True, "cannot stat file"
        return False, f"cleanable (status={reason.split('=')[-1]}, older than {RETENTION_DAYS} days)"

    # Temp/data files: use the `days` parameter threshold
    cutoff = time.time() - days * 86400
    try:
        if os.stat(path).st_mtime >= cutoff:
            return True, f"not yet past {days}-day threshold"
    except OSError:
        return True, "cannot stat file"
    return False, ""


def _discover_tasks_dirs(tenant_op: str = None) -> list[Path]:
    """Discover all task directories under both legacy and tenant-scoped locations."""
    dirs = []
    # Legacy
    if LEGACY_TASKS_DIR.exists():
        dirs.append(LEGACY_TASKS_DIR)
    # Tenant-scoped: tenants/{op}/clients/{client}/tasks/
    if TENANTS_ROOT.exists():
        for op_dir in sorted(TENANTS_ROOT.iterdir()):
            if not op_dir.is_dir():
                continue
            if tenant_op and op_dir.name != tenant_op:
                continue
            clients_dir = op_dir / "clients"
            if not clients_dir.exists():
                continue
            for client_dir in sorted(clients_dir.iterdir()):
                if not client_dir.is_dir():
                    continue
                tasks_dir = client_dir / "tasks"
                if tasks_dir.exists():
                    dirs.append(tasks_dir)
    return dirs


def cleanup_aged_files(days=7, dry_run=False, tenant_op: str = None):
    retention_cutoff = time.time() - RETENTION_DAYS * 86400
    cutoff = time.time() - days * 86400
    removed = []
    skipped = []

    # Clean temp/data dirs — use the `days` threshold (scratch space cleanup)
    for d in TEMP_DIRS:
        if not d.exists():
            continue
        for root, _, files in os.walk(d):
            for f in files:
                fp = os.path.join(root, f)
                skip, reason = should_skip(fp, days=days)
                if skip:
                    skipped.append((fp, reason))
                    continue
                try:
                    if os.stat(fp).st_mtime < cutoff:
                        if not dry_run:
                            os.remove(fp)
                        removed.append(fp)
                except (FileNotFoundError, PermissionError, OSError):
                    continue

    # Clean stale task state files from ALL discovered task directories
    # (legacy + all tenant-scoped)
    for tasks_dir in _discover_tasks_dirs(tenant_op):
        if not tasks_dir.exists():
            continue
        for f in os.listdir(tasks_dir):
            if not f.endswith(".json"):
                continue
            fp = os.path.join(tasks_dir, f)
            skip, reason = should_skip(fp, days=days)
            if skip:
                skipped.append((fp, reason))
                continue
            # Cleanable task state — remove only if past RETENTION_DAYS
            try:
                if os.stat(fp).st_mtime < retention_cutoff:
                    if not dry_run:
                        os.remove(fp)
                    removed.append(fp)
            except (FileNotFoundError, PermissionError, OSError):
                continue

    return removed, skipped


def log_cleanup(removed, dry_run=False):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        mode = "DRY_RUN" if dry_run else "CLEANUP"
        for fp in removed:
            f.write(f"[{ts}] {mode}: {fp}\n")


def main():
    parser = argparse.ArgumentParser(description="Mother Agent auto-cleanup")
    parser.add_argument("--days", type=int, default=7,
                        help="Delete temp/data files older than N days")
    parser.add_argument("--dry-run", action="store_true",
                        help="Do not delete, just list what would be removed")
    parser.add_argument("--tenant", type=str, default=None,
                        help="Only clean tasks for a specific operator (e.g. OP001)")
    args = parser.parse_args()

    removed, skipped = cleanup_aged_files(
        days=args.days, dry_run=args.dry_run, tenant_op=args.tenant
    )
    log_cleanup(removed, dry_run=args.dry_run)

    mode = "would remove" if args.dry_run else "removed"
    scope = f" tenant={args.tenant}" if args.tenant else " (all tenants)"
    print(f"Auto-cleanup {mode} {len(removed)} file(s){scope}. "
          f"Temp/data threshold: {args.days} days | Task/log retention: {RETENTION_DAYS} days.")
    if removed:
        for fp in removed[:10]:
            print(f"  - {fp}")
        if len(removed) > 10:
            print(f"  ... and {len(removed) - 10} more")
    if skipped:
        active = [(fp, r) for fp, r in skipped
                  if r.startswith("active") or r.startswith("unknown")]
        stale = [(fp, r) for fp, r in skipped
                 if r not in ["control file", "marker/validation file", "excluded dir"]]
        if active:
            print(f"  (skipped {len(active)} active task files — not cleaning active state)")
        if stale:
            print(f"  (skipped {len(stale)} stale terminal task files — not yet past age threshold)")


if __name__ == "__main__":
    main()
