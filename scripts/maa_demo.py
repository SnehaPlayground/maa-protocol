#!/usr/bin/env python3
"""Run a simple demo submission for Maa."""

import subprocess
import sys
from pathlib import Path

WORKSPACE = Path("/root/.openclaw/workspace")
ORCH = WORKSPACE / "ops" / "multi-agent-orchestrator" / "task_orchestrator.py"


def main() -> None:
    cmd = [
        sys.executable,
        str(ORCH),
        "submit",
        "research",
        "demo: explain what this Maa installation is configured to do",
        "--run",
    ]
    print("Running demo task...")
    proc = subprocess.run(cmd, cwd=str(WORKSPACE))
    raise SystemExit(proc.returncode)


if __name__ == "__main__":
    main()
