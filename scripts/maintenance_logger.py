#!/usr/bin/env python3
"""
Mother Agent Self-Healing — Maintenance Decision Logger
======================================================
Append-only JSONL logger for every health check, cleanup, or maintenance action.

Usage:
    python3 maintenance_logger.py "disk_check" "warn" '{"disk_pct": 78.2}'
    python3 maintenance_logger.py "cleanup" "removed" '{"files": ["/tmp/a.txt"]}'
"""

import json
import os
import sys
import time
from datetime import datetime, UTC
from pathlib import Path

DECISIONS_DIR = Path("/root/.openclaw/workspace/memory/maintenance_decisions")
ALERT_COOLDOWN_FILE = DECISIONS_DIR / "alert_cooldown.json"
COOLDOWN_SECONDS = 7200  # 2 hours — same alert won't fire twice within this window

os.makedirs(DECISIONS_DIR, exist_ok=True)


def _load_cooldown() -> dict:
    """Load alert cooldown state. Returns dict: alert_key -> last_alert_timestamp."""
    if ALERT_COOLDOWN_FILE.exists():
        try:
            with open(ALERT_COOLDOWN_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def _save_cooldown(state: dict) -> None:
    """Persist cooldown state atomically."""
    tmp = ALERT_COOLDOWN_FILE.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    tmp.rename(ALERT_COOLDOWN_FILE)


def _is_in_cooldown(action: str, outcome: str) -> tuple[bool, int]:
    """Check if this (action, outcome) alert is in cooldown.
    
    Returns (is_cooldown, seconds_remaining).
    """
    key = f"{action}:{outcome}"
    state = _load_cooldown()
    last = state.get(key, 0)
    elapsed = time.time() - last
    if elapsed < COOLDOWN_SECONDS:
        return True, int(COOLDOWN_SECONDS - elapsed)
    return False, 0


def _touch_cooldown(action: str, outcome: str) -> None:
    """Record that an alert was just fired for (action, outcome)."""
    key = f"{action}:{outcome}"
    state = _load_cooldown()
    state[key] = time.time()
    _save_cooldown(state)


def log_decision(action: str, outcome: str, details=None):
    """Append a maintenance decision log entry.
    
    If outcome is 'critical' or 'warn', checks alert cooldown before logging
    the alert-worthy entry. Cooldown is 2 hours per (action, outcome) pair.
    """
    entry = {
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "action": action,
        "outcome": outcome,
        "details": details or {},
    }
    
    # Check cooldown for alert-worthy outcomes
    if outcome in ("critical", "warn"):
        in_cooldown, remaining = _is_in_cooldown(action, outcome)
        if in_cooldown:
            entry["_cooldown_suppressed"] = True
            entry["_cooldown_remaining_s"] = remaining
            # SER-4 fix: operator must know an alert was raised but suppressed
            print(f"[MAA MAINTENANCE SUPPRESSED — cooldown {remaining}s remaining] {action} — {outcome} — {details}")
        else:
            _touch_cooldown(action, outcome)
    
    filename = os.path.join(DECISIONS_DIR, f"{datetime.now(UTC).strftime('%Y-%m-%d')}.jsonl")
    with open(filename, "a") as f:
        f.write(json.dumps(entry) + "\n")
    
    # Print alert-worthy entries to stderr so they are never silently dropped
    if outcome == "critical":
        print(f"[MAA MAINTENANCE CRITICAL] {action} — {outcome} — {details}", file=sys.stderr)
    elif outcome == "warn":
        print(f"[MAA MAINTENANCE WARN] {action} — {outcome} — {details}", file=sys.stderr)
    else:
        print(f"Logged maintenance decision: {action} — {outcome}")


def main():
    if len(sys.argv) < 3:
        print("Usage: maintenance_logger.py <action> <outcome> [json-details]")
        sys.exit(1)

    action = sys.argv[1]
    outcome = sys.argv[2]
    details = None
    if len(sys.argv) > 3:
        try:
            details = json.loads(sys.argv[3])
        except json.JSONDecodeError:
            details = {"raw": sys.argv[3]}

    log_decision(action, outcome, details)
    print(f"Logged maintenance decision: {action} — {outcome}")


if __name__ == "__main__":
    main()
