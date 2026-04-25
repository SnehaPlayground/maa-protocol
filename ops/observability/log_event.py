#!/usr/bin/env python3
"""
Lightweight event logger — callable from shell scripts.
Wraps maa_metrics.py record commands for shell-script integration.

Usage (from shell):
    python3 log_event.py call "sneha.send_email"
    python3 log_event.py error "research.fetch_failed" "HTTP 404"
    python3 log_event.py latency "sneha.send_email" 1342
    python3 log_event.py task "market_brief.generate" "completed"

Environment overrides:
    MAA_AGENT=research    python3 log_event.py call "article.fetch"  # sets agent
    MAA_SESSION=abc123    python3 log_event.py call "article.fetch"  # sets session-id
"""

import subprocess
import sys
import os

METRICS_CLI = "/root/.openclaw/workspace/ops/observability/maa_metrics.py"

def main():
    if len(sys.argv) < 2:
        print("Usage: log_event.py <call|error|latency|task> <label> [details|value|status]")
        sys.exit(1)

    cmd = [sys.executable, METRICS_CLI, "record", "--type", sys.argv[1], "--label", sys.argv[2]]

    agent = os.environ.get("MAA_AGENT", "")
    session = os.environ.get("MAA_SESSION", "")
    if agent:
        cmd += ["--agent", agent]
    if session:
        cmd += ["--session-id", session]

    if sys.argv[1] == "error":
        if len(sys.argv) < 3:
            print("Error: details required for error type", file=sys.stderr)
            sys.exit(1)
        cmd += ["--details", sys.argv[3]]

    elif sys.argv[1] == "latency":
        if len(sys.argv) < 3:
            print("Error: value (ms) required for latency type", file=sys.stderr)
            sys.exit(1)
        cmd += ["--value", sys.argv[3]]

    elif sys.argv[1] == "task":
        status = sys.argv[3] if len(sys.argv) > 3 else "completed"
        cmd += ["--status", status]

    # Suppress stdout from subprocess — log_event is silent on success
    result = subprocess.run(cmd, capture_output=True)
    sys.exit(result.returncode)

if __name__ == "__main__":
    main()
