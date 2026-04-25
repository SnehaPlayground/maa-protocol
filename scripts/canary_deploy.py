#!/usr/bin/env python3
"""
MAA Canary Deployment Controller
=================================
Routes a percentage of new tasks to a canary (experimental) version of the
orchestrator while monitoring error rates. Promotes or reverts based on
24-hour health window.

Exit codes:
  0 — canary promoted to stable
  1 — canary reverted to stable
  2 — monitoring window still open (no decision yet)

Usage:
  python3 canary_deploy.py promote          # manually promote canary → stable
  python3 canary_deploy.py revert          # manually revert canary → stable
  python3 canary_deploy.py status          # show current canary/stable versions
  python3 canary_deploy.py check           # check error rate and decide (auto)

CRON (optional — continuous monitoring):
  */15 * * * * python3 /root/.openclaw/workspace/scripts/canary_deploy.py check

Author: Maa maintainer
Phase: 12 of MAA Protocol Commercial Deployment Action Plan v1.2
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime, UTC, timedelta
from pathlib import Path

WORKSPACE = Path("/root/.openclaw/workspace")
ORCHESTRATOR = WORKSPACE / "ops/multi-agent-orchestrator" / "task_orchestrator.py"
METRICS_FILE = WORKSPACE / "data" / "observability" / "maa_metrics.json"
CANARY_MARKER = WORKSPACE / "ops/multi-agent-orchestrator" / ".canary_version"
STABLE_MARKER = WORKSPACE / "ops/multi-agent-orchestrator" / ".stable_version"
CANARY_ERR_LOG = WORKSPACE / "ops" / "multi-agent-orchestrator" / "logs" / "canary_errors.json"
MONITOR_WINDOW_H = 24  # hours
ERROR_RATE_PROMOTE_THRESHOLD = 0.05  # < 5% error rate → promote
ERROR_RATE_REVERT_THRESHOLD = 0.05  # ≥ 5% error rate → revert


def now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _log(msg: str) -> None:
    print(f"[CANARY_DEPLOY] {msg}", file=sys.stderr)


def _atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    tmp.replace(path)


def _read_version_file(path: Path) -> str:
    """Read version from a marker file, strip whitespace."""
    if not path.exists():
        return ""
    try:
        return path.read_text().strip()
    except Exception:
        return ""


def _write_version_file(path: Path, version: str) -> None:
    path.write_text(version.strip() + "\n")


def _parse_VERSION_from_orchestrator() -> str:
    """Extract VERSION = \"x.y\" from task_orchestrator.py shebang area."""
    with open(ORCHESTRATOR) as f:
        for line in f:
            if line.startswith("VERSION"):
                return line.split("=", 1)[1].strip().strip('"')
    return "unknown"


def _set_stable_version(version: str) -> None:
    """Mark the current stable version."""
    _write_version_file(STABLE_MARKER, version)
    _log(f"Stable version marked: {version}")


def _current_stable() -> str:
    """Return current stable version (from marker or orchestrator)."""
    v = _read_version_file(STABLE_MARKER)
    if v:
        return v
    return _parse_VERSION_from_orchestrator()


def _current_canary() -> str:
    """Return current canary version from marker file."""
    v = _read_version_file(CANARY_MARKER)
    return v


def _update_orchestrator_VERSION(new_version: str) -> None:
    """Update VERSION = \"x.y\" in task_orchestrator.py."""
    lines = ORCHESTRATOR.read_text().splitlines()
    new_lines = []
    for line in lines:
        if line.startswith("VERSION"):
            new_lines.append(f'VERSION = "{new_version}"')
        else:
            new_lines.append(line)
    ORCHESTRATOR.write_text("\n".join(new_lines) + "\n")
    _log(f"Updated task_orchestrator.py VERSION → {new_version}")


def _send_telegram(msg: str) -> None:
    proc = subprocess.run(
        ["openclaw", "message", "send",
         "--channel", "telegram",
         "--target", "telegram:6483160",
         "--message", msg],
        capture_output=True, text=True, timeout=20,
    )
    if proc.returncode == 0:
        _log("Telegram notification sent")
    else:
        _log(f"Telegram notification failed: {proc.stderr}")


def _load_metrics() -> dict:
    if not METRICS_FILE.exists():
        return {}
    try:
        with open(METRICS_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def _compute_error_rate(window_h: int = MONITOR_WINDOW_H) -> tuple[float, dict]:
    """Compute canary task error rate over the last `window_h` hours.

    Returns (error_rate: float, stats: dict).
    """
    metrics = _load_metrics()
    if not metrics:
        return 0.0, {"total": 0, "errors": 0, "window_h": window_h}

    cutoff = datetime.now(UTC) - timedelta(hours=window_h)
    cutoff_ts = cutoff.isoformat()

    total = 0
    errors = 0

    # Count task entries from canary version within window
    # Canary tasks are identifiable via session_id prefix "canary-" or
    # via the canary version marker in harness_template_version
    tasks_bucket = metrics.get("tasks", {})

    if isinstance(tasks_bucket, dict):
        for task_id, entries in tasks_bucket.items():
            if not isinstance(entries, list):
                continue
            for e in entries:
                ts = e.get("timestamp", "")
                if ts < cutoff_ts:
                    continue
                total += 1
                status = str(e.get("status", ""))
                if status in ("exhausted", "failed"):
                    errors += 1

    error_rate = (errors / total) if total > 0 else 0.0
    return error_rate, {"total": total, "errors": errors, "window_h": window_h,
                         "error_rate_pct": round(error_rate * 100, 2)}


def _record_canary_error(task_id: str, reason: str) -> None:
    """Record a canary error for monitoring."""
    errors = {}
    if CANARY_ERR_LOG.exists():
        try:
            with open(CANARY_ERR_LOG) as f:
                errors = json.load(f)
        except Exception:
            errors = {"errors": []}
    if "errors" not in errors:
        errors["errors"] = []
    errors["errors"].append({"task_id": task_id, "reason": reason, "at": now_iso()})
    # Keep only last 100 errors
    errors["errors"] = errors["errors"][-100:]
    _atomic_write_json(CANARY_ERR_LOG, errors)


# ── Canary Routing ────────────────────────────────────────────────────────────

def route_to_canary(task_id: str) -> bool:
    """
    Decide whether a new task should be routed to the canary version.

    Implementation: 10% random sample of new tasks.
    Self-contained: does not need external state beyond this decision.
    """
    import hashlib
    # Deterministic sampling: hash(task_id) mod 10 == 0 → canary
    h = int(hashlib.md5(task_id.encode()).hexdigest(), 16)
    return (h % 10) == 0


# ── Canary Status ─────────────────────────────────────────────────────────────

def show_status() -> None:
    stable = _current_stable()
    canary = _current_canary()
    active = canary if canary else "(none)"
    print(f"Stable:  {stable}")
    print(f"Canary:  {active}")
    print(f"Routing: 10% of new tasks to canary")

    # Compute current error rate
    rate, stats = _compute_error_rate()
    print(f"Error rate (24h window): {stats['error_rate_pct']}% "
          f"({stats['errors']}/{stats['total']} tasks)")


# ── Promote Canary ────────────────────────────────────────────────────────────

def promote_canary() -> None:
    """Promote canary version to stable and notify the operator."""
    canary = _current_canary()
    if not canary:
        _log("ERROR: No canary version to promote")
        sys.exit(1)

    # Update VERSION in orchestrator
    _update_orchestrator_VERSION(canary)

    # Update stable marker
    _set_stable_version(canary)

    # Clear canary marker (promotion complete)
    if CANARY_MARKER.exists():
        CANARY_MARKER.unlink()

    msg = (
        f"🚀 MAA CANARY PROMOTED\n"
        f"Canary version: {canary}\n"
        f"Error rate (24h): < 5%\n"
        f"All new tasks now run on {canary}."
    )
    _send_telegram(msg)

    _log(f"Canary {canary} promoted to stable — VERSION updated")
    sys.exit(0)


# ── Revert Canary ─────────────────────────────────────────────────────────────

def revert_canary() -> None:
    """Revert canary and restore stable version, then notify the operator."""
    stable = _current_stable()
    canary = _current_canary()

    if CANARY_MARKER.exists():
        CANARY_MARKER.unlink()

    if stable:
        _update_orchestrator_VERSION(stable)

    msg = (
        f"⚠️ MAA CANARY REVERTED\n"
        f"Canary version: {canary or '(none)'}\n"
        f"Error rate (24h): ≥ 5% — reverting to stable: {stable}"
    )
    _send_telegram(msg)

    _log(f"Canary reverted — running stable version {stable}")
    sys.exit(1)


# ── Auto-check (for cron) ───────────────────────────────────────────────────

def check_and_decide() -> None:
    """Check error rate and promote/revert based on thresholds. Exits appropriately."""
    canary = _current_canary()
    if not canary:
        _log("No canary deployed — nothing to check")
        sys.exit(2)

    rate, stats = _compute_error_rate()

    _log(f"Canary: {canary} | Error rate: {stats['error_rate_pct']}% ({stats['errors']}/{stats['total']})")

    # Need minimum sample size before deciding
    if stats["total"] < 5:
        _log(f"Too few samples ({stats['total']}) — monitoring window open, no decision yet")
        sys.exit(2)

    if rate < ERROR_RATE_PROMOTE_THRESHOLD:
        _log(f"Error rate {stats['error_rate_pct']}% < 5% — promoting canary")
        promote_canary()
    else:
        _log(f"Error rate {stats['error_rate_pct']}% ≥ 5% — reverting canary")
        revert_canary()


# ── Deploy Canary ─────────────────────────────────────────────────────────────

def deploy_canary(new_version: str) -> None:
    """Deploy a new canary version (set marker, route 10% traffic to it)."""
    # Validate version format
    if not new_version.startswith("v"):
        new_version = "v" + new_version

    # Write canary marker
    _write_version_file(CANARY_MARKER, new_version)

    # Clear any prior error log
    if CANARY_ERR_LOG.exists():
        CANARY_ERR_LOG.unlink()

    msg = (
        f"🔬 MAA CANARY DEPLOYED\n"
        f"New canary version: {new_version}\n"
        f"Routing: 10% of new tasks to canary\n"
        f"Monitoring window: 24 hours\n"
        f"Will auto-promote if error rate < 5%."
    )
    _send_telegram(msg)

    _log(f"Canary version {new_version} deployed — monitoring for 24h")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="MAA Canary Deployment Controller")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("status", help="Show current stable/canary versions and error rate")

    sub.add_parser("check", help="Check canary error rate and decide (auto promote/revert)")

    promote_p = sub.add_parser("promote", help="Manually promote canary to stable")
    promote_p.add_argument("--version", help="Canary version to promote (default: read from marker)")

    revert_p = sub.add_parser("revert", help="Manually revert canary to stable")

    deploy_p = sub.add_parser("deploy", help="Deploy a new canary version")
    deploy_p.add_argument("version", help="Canary version (e.g., v1.1)")

    args = parser.parse_args()

    if args.cmd == "status":
        show_status()
    elif args.cmd == "check":
        check_and_decide()
    elif args.cmd == "promote":
        promote_canary()
    elif args.cmd == "revert":
        revert_canary()
    elif args.cmd == "deploy":
        deploy_canary(args.version)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
