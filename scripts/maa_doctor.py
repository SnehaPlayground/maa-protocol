#!/usr/bin/env python3
"""Basic Maa installation and runtime preflight."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

WORKSPACE = Path("/root/.openclaw/workspace")
RUNTIME_CONFIG = WORKSPACE / "knowledge" / "maa-product" / "runtime-config.json"
PREDEPLOY = WORKSPACE / "scripts" / "pre_deploy_gate.sh"
HEALTH = WORKSPACE / "scripts" / "health_check.py"


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"[{'OK' if ok else 'FAIL'}] {label}" + (f" - {detail}" if detail else ""))
    return ok


def main() -> None:
    ok_all = True

    ok_all &= check("Python 3 available", sys.version_info >= (3, 10), sys.version.split()[0])
    ok_all &= check("OpenClaw installed", shutil.which("openclaw") is not None)
    ok_all &= check("Runtime config exists", RUNTIME_CONFIG.exists(), str(RUNTIME_CONFIG))
    ok_all &= check("Pre-deploy gate exists", PREDEPLOY.exists())
    ok_all &= check("Health check exists", HEALTH.exists())

    try:
        proc = subprocess.run([sys.executable, str(HEALTH), "--json"], capture_output=True, text=True, timeout=20)
        ok_all &= check("Health check runnable", proc.returncode == 0)
    except Exception as exc:
        ok_all &= check("Health check runnable", False, str(exc))

    try:
        proc = subprocess.run(["openclaw", "status"], capture_output=True, text=True, timeout=20)
        ok_all &= check("OpenClaw status reachable", proc.returncode == 0)
    except Exception as exc:
        ok_all &= check("OpenClaw status reachable", False, str(exc))

    if ok_all:
        print("\nMaa doctor passed.")
        sys.exit(0)
    print("\nMaa doctor found issues.")
    sys.exit(1)


if __name__ == "__main__":
    main()
