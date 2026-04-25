#!/usr/bin/env python3
"""
MAA Canary Router — Phase 12 Integration
==========================================
Provides deterministic canary routing for new task submissions.
10% of tasks are routed to the canary version, determined by hashing task_id.

This module is imported by task_orchestrator.py and called at task submission time
(after dedup, before spawn) to decide which version the task runs on.

Exit codes from canary_deploy.py:
  0 — canary promoted to stable
  1 — canary reverted to stable
  2 — monitoring window still open (no decision yet)

Author: Maa maintainer
Phase: 12 of MAA Protocol Commercial Deployment Action Plan v1.2
"""

import hashlib
import json
import subprocess
import sys
from datetime import datetime, UTC, timedelta
from pathlib import Path

WORKSPACE = Path("/root/.openclaw/workspace")
ORCHESTRATOR = WORKSPACE / "ops/multi-agent-orchestrator" / "task_orchestrator.py"
CANARY_MARKER = WORKSPACE / "ops/multi-agent-orchestrator" / ".canary_version"
STABLE_MARKER = WORKSPACE / "ops/multi-agent-orchestrator" / ".stable_version"
METRICS_FILE = WORKSPACE / "data" / "observability" / "maa_metrics.json"
CANARY_ERR_LOG = WORKSPACE / "ops/multi-agent-orchestrator" / "logs" / "canary_errors.json"
MONITOR_WINDOW_H = 24
ERROR_RATE_PROMOTE_THRESHOLD = 0.05
ERROR_RATE_REVERT_THRESHOLD = 0.05


def _alert_target() -> str:
    """Return the configured operator alert target, or a safe default."""
    config_file = WORKSPACE / "knowledge" / "maa-product" / "runtime-config.json"
    try:
        if config_file.exists():
            config = json.loads(config_file.read_text())
            return str(config.get("alert_target", "telegram:6483160"))
    except Exception:
        pass
    return "telegram:6483160"


def is_canary_deployed() -> bool:
    """Return True if a canary version is currently active."""
    return CANARY_MARKER.exists()


def get_canary_version() -> str:
    """Return the current canary version string, or empty string if none."""
    if not CANARY_MARKER.exists():
        return ""
    try:
        return CANARY_MARKER.read_text().strip()
    except Exception:
        return ""


def get_stable_version() -> str:
    """Return the stable version (from marker or orchestrator VERSION constant)."""
    if STABLE_MARKER.exists():
        try:
            return STABLE_MARKER.read_text().strip()
        except Exception:
            pass
    # Fall back to orchestrator VERSION
    for line in ORCHESTRATOR.read_text().splitlines():
        if line.startswith("VERSION"):
            return line.split("=", 1)[1].strip().strip('"')
    return "v1.0"


def route_to_canary(task_id: str) -> bool:
    """
    Decide whether a new task should be routed to the canary version.

    Deterministic: hash(task_id) mod 10 == 0 → canary (10% sample).
    No canary deployed → always returns False.
    """
    if not is_canary_deployed():
        return False
    h = int(hashlib.md5(task_id.encode()).hexdigest(), 16)
    return (h % 10) == 0


def canary_error_rate(window_h: int = MONITOR_WINDOW_H) -> tuple[float, dict]:
    """
    Compute canary task error rate over the last `window_h` hours.

    Returns (error_rate: float, stats: dict with total/errors/window_h/error_rate_pct).
    This must count ONLY canary-routed tasks, not all tasks system-wide.
    We derive this from task state files because metrics buckets do not currently
    carry a dedicated canary flag.
    """
    stats = {"total": 0, "errors": 0, "window_h": window_h, "error_rate_pct": 0.0}
    cutoff = datetime.now(UTC) - timedelta(hours=window_h)

    try:
        from task_orchestrator import _iter_all_task_state_files
    except Exception:
        return 0.0, stats

    total = 0
    errors = 0
    for state_file in _iter_all_task_state_files():
        try:
            task = json.loads(Path(state_file).read_text())
        except Exception:
            continue
        if not task.get("canary_routed"):
            continue
        created_at = task.get("created_at") or task.get("updated_at")
        if not created_at:
            continue
        try:
            created_dt = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
        except Exception:
            continue
        if created_dt < cutoff:
            continue
        total += 1
        status = str(task.get("status", ""))
        if status in ("exhausted", "failed"):
            errors += 1

    error_rate = (errors / total) if total > 0 else 0.0
    stats = {
        "total": total,
        "errors": errors,
        "window_h": window_h,
        "error_rate_pct": round(error_rate * 100, 2),
    }
    return error_rate, stats


def check_and_decide() -> int:
    """
    Check error rate and promote/revert canary based on thresholds.

    Exits: 0=promoted, 1=reverted, 2=monitoring window open (no decision yet)
    """
    if not is_canary_deployed():
        return 2

    rate, stats = canary_error_rate()

    if stats["total"] < 5:
        return 2  # too few samples

    canary_version = get_canary_version()

    if rate < ERROR_RATE_PROMOTE_THRESHOLD:
        _promote(canary_version)
        return 0
    else:
        _revert(canary_version)
        return 1


def _update_orchestrator_version(new_version: str) -> None:
    """Update VERSION = \"x.y\" in task_orchestrator.py."""
    lines = ORCHESTRATOR.read_text().splitlines()
    new_lines = []
    for line in lines:
        if line.startswith("VERSION"):
            new_lines.append(f'VERSION = "{new_version}"')
        else:
            new_lines.append(line)
    ORCHESTRATOR.write_text("\n".join(new_lines) + "\n")


def _write_marker(path: Path, version: str) -> None:
    path.write_text(version.strip() + "\n")


def _promote(canary_version: str) -> None:
    """Promote canary: update VERSION to canary, clear marker, notify the operator."""
    _update_orchestrator_version(canary_version)
    _write_marker(STABLE_MARKER, canary_version)
    if CANARY_MARKER.exists():
        CANARY_MARKER.unlink()
    _notify(f"🚀 MAA CANARY PROMOTED\nCanary: {canary_version}\nError rate < 5%.\nAll tasks now run on {canary_version}.")


def _revert(canary_version: str) -> None:
    """Revert canary: restore stable version, clear marker, notify the operator."""
    stable = get_stable_version()
    _update_orchestrator_version(stable)
    if CANARY_MARKER.exists():
        CANARY_MARKER.unlink()
    _notify(f"⚠️ MAA CANARY REVERTED\nCanary: {canary_version}\nError rate ≥ 5% — reverting to stable: {stable}")


def _notify(msg: str) -> None:
    subprocess.run(
        ["openclaw", "message", "send",
         "--channel", "telegram",
         "--target", _alert_target(),
         "--message", msg],
        capture_output=True, text=True, timeout=20,
    )


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="MAA Canary Router CLI")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("status", help="Show stable/canary versions and error rate")

    sub.add_parser("check", help="Check error rate and decide (auto promote/revert)")

    deploy_p = sub.add_parser("deploy", help="Deploy a new canary version")
    deploy_p.add_argument("version", help="Canary version (e.g., v1.1)")

    promote_p = sub.add_parser("promote", help="Manually promote canary")
    revert_p = sub.add_parser("revert", help="Manually revert canary")

    args = parser.parse_args()

    if args.cmd == "status":
        stable = get_stable_version()
        canary = get_canary_version()
        rate, stats = canary_error_rate()
        print(f"Stable:  {stable}")
        print(f"Canary:  {canary or '(none)'}")
        print(f"Routing: 10% of new tasks to canary")
        print(f"Error rate (24h window): {stats['error_rate_pct']}% ({stats['errors']}/{stats['total']} tasks)")

    elif args.cmd == "check":
        rc = check_and_decide()
        print({0: "PROMOTED", 1: "REVERTED", 2: "MONITORING WINDOW OPEN"}.get(rc, f"exit={rc}"))
        sys.exit(rc)

    elif args.cmd == "deploy":
        v = args.version
        if not v.startswith("v"):
            v = "v" + v
        _write_marker(CANARY_MARKER, v)
        if CANARY_ERR_LOG.exists():
            CANARY_ERR_LOG.unlink()
        _notify(f"🔬 MAA CANARY DEPLOYED\nNew canary: {v}\nRouting: 10% of new tasks\nMonitoring window: 24h")
        print(f"Canary {v} deployed")

    elif args.cmd == "promote":
        canary = get_canary_version()
        if not canary:
            print("No canary to promote")
            sys.exit(1)
        _promote(canary)
        print(f"Canary {canary} promoted to stable")

    elif args.cmd == "revert":
        canary = get_canary_version()
        _revert(canary)
        print(f"Canary reverted")

    else:
        parser.print_help()
