#!/usr/bin/env python3
"""
Mother Agent Self-Healing — Disk & Resource Health Check
========================================================
Checks disk usage, memory, and CPU before tasks or on a schedule.
Returns JSON status and can optionally trigger alerts (future integration).

Usage:
    python3 health_check.py                # print summary
    python3 health_check.py --json         # machine-readable JSON
    python3 health_check.py --threshold 85 # custom warning threshold
"""

import argparse
import json
import shutil
from datetime import datetime, UTC

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


def check_disk_health(threshold=85):
    usage = shutil.disk_usage("/")
    usage_pct = (usage.used / usage.total) * 100

    if usage_pct >= threshold:
        status = "critical"
    elif usage_pct >= 75:
        status = "warn"
    else:
        status = "ok"

    return {
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "usage_pct": round(usage_pct, 1),
        "status": status,
        "free_gb": round(usage.free / (1024**3), 1),
        "used_gb": round(usage.used / (1024**3), 1),
        "total_gb": round(usage.total / (1024**3), 1),
    }


def check_system_resources():
    if not PSUTIL_AVAILABLE:
        return None

    return {
        "cpu_pct": round(psutil.cpu_percent(interval=0.5), 1),
        "memory_pct": round(psutil.virtual_memory().percent, 1),
        "memory_used_gb": round(psutil.virtual_memory().used / (1024**3), 1),
        "memory_total_gb": round(psutil.virtual_memory().total / (1024**3), 1),
    }


def main():
    parser = argparse.ArgumentParser(description="Mother Agent health check")
    parser.add_argument("--threshold", type=int, default=85,
                        help="Disk usage percentage to consider critical")
    parser.add_argument("--json", action="store_true",
                        help="Print JSON only")
    args = parser.parse_args()

    disk = check_disk_health(threshold=args.threshold)
    resources = check_system_resources()

    result = {
        "disk": disk,
        "resources": resources,
        "psutil_available": PSUTIL_AVAILABLE,
    }

    if args.json:
        print(json.dumps(result, indent=2))
        return

    print()
    print("MOTHER AGENT — HEALTH CHECK")
    print("────────────────────────────")
    print(f"Disk:      {disk['usage_pct']:>5.1f}%  ({disk['used_gb']:.1f}GB / {disk['total_gb']:.1f}GB)  free: {disk['free_gb']:.1f}GB  status: {disk['status'].upper()}")
    if resources:
        print(f"CPU:       {resources['cpu_pct']:>5.1f}%")
        print(f"Memory:    {resources['memory_pct']:>5.1f}%  ({resources['memory_used_gb']:.1f}GB / {resources['memory_total_gb']:.1f}GB)")
    else:
        print("Memory:    psutil not installed")
    print()


if __name__ == "__main__":
    main()
