#!/usr/bin/env python3
"""
MAA Tenant Usage & Governance Report
=====================================
Generates monthly cost and usage governance reports per tenant.

Input: operator_id, client_id, month (YYYY-MM)
Output:
  data/reports/tenant-usage-{operator}-{client}-{month}.csv
  data/reports/tenant-usage-{operator}-{client}-{month}.json

Fields:
  tasks_submitted, tasks_completed, tasks_failed, runtime_minutes,
  estimated_cost, resource_saturation (disk%, mem%)

Uses TenantPathResolver for tenant-scoped path resolution.

Usage:
  python3 tenant_usage_governance_report.py --operator OP001 --client CL001 --month 2026-04
  python3 tenant_usage_governance_report.py --operator OP001 --month 2026-04   # all clients

Author: Sneha (Mother Agent)
Phase: 13 of MAA Protocol Commercial Deployment Action Plan v1.2
"""

import argparse
import csv
import json
import os
import psutil
import subprocess
import sys
import time
from datetime import datetime, UTC
from pathlib import Path

WORKSPACE = Path("/root/.openclaw/workspace")
TENANTS_ROOT = WORKSPACE / "tenants"
METRICS_FILE = WORKSPACE / "data" / "observability" / "maa_metrics.json"
REPORTS_DIR = WORKSPACE / "data" / "reports"


# ── Cost estimation ─────────────────────────────────────────────────────────

COST_PER_MINUTE = {
    "market-brief": 0.05,
    "research": 0.05,
    "email-draft": 0.03,
    "growth-report": 0.05,
    "validation": 0.03,
    "coder": 0.06,
    "executor": 0.05,
}
DEFAULT_COST_PER_MINUTE = 0.04
BASE_RUNTIME_MIN = {
    "market-brief": 8,
    "research": 10,
    "email-draft": 3,
    "growth-report": 12,
    "validation": 5,
    "coder": 15,
    "executor": 10,
}


def _estimate_task_cost(task_type: str) -> float:
    runtime = BASE_RUNTIME_MIN.get(task_type, 5)
    cost_per_min = COST_PER_MINUTE.get(task_type, DEFAULT_COST_PER_MINUTE)
    return round(runtime * cost_per_min, 4)


# ── Tenant path resolver (inline, no circular import) ────────────────────────

def _resolve_tenant_tasks_dir(operator_id: str, client_id: str | None = None) -> Path:
    if client_id is None or operator_id == "default":
        return WORKSPACE / "ops/multi-agent-orchestrator" / "tasks"
    return TENANTS_ROOT / operator_id / "clients" / client_id / "tasks"


def _resolve_tenant_logs_dir(operator_id: str, client_id: str | None = None) -> Path:
    if client_id is None or operator_id == "default":
        return WORKSPACE / "ops/multi-agent-orchestrator" / "logs"
    return TENANTS_ROOT / operator_id / "clients" / client_id / "logs"


# ── Resource saturation ──────────────────────────────────────────────────────

def _get_resource_saturation() -> dict:
    try:
        disk = psutil.disk_usage("/")
        mem = psutil.virtual_memory()
        return {
            "disk_pct": round(disk.percent, 1),
            "mem_pct": round(mem.percent, 1),
        }
    except Exception:
        return {"disk_pct": None, "mem_pct": None}


# ── Data collection ──────────────────────────────────────────────────────────

def _load_metrics() -> dict:
    if not METRICS_FILE.exists():
        return {}
    try:
        with open(METRICS_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def _collect_from_metrics(month: str, operator_id: str,
                           client_id: str | None) -> dict:
    """Collect task stats from metrics store for the given month."""
    metrics = _load_metrics()
    prefix = f"{operator_id}:{client_id}" if client_id else None
    month_prefix = f"{month}T"

    stats = {
        "tasks_submitted": 0,
        "tasks_completed": 0,
        "tasks_failed": 0,
        "runtime_minutes": 0.0,
        "estimated_cost": 0.0,
    }

    task_bucket = metrics.get("tasks", {})
    if not isinstance(task_bucket, dict):
        return stats

    for task_id, entries in task_bucket.items():
        if not isinstance(entries, list):
            continue
        for e in entries:
            ts = e.get("timestamp", "")
            if not ts.startswith(month_prefix):
                continue

            # Filter by tenant if specified
            op = e.get("operator_id", "")
            cl = e.get("client_id", "")
            if prefix and f"{op}:{cl}" != prefix:
                continue

            task_type = e.get("task_type", e.get("label", "unknown"))
            status = str(e.get("status", ""))

            stats["tasks_submitted"] += 1

            if status in ("completed", "validated"):
                stats["tasks_completed"] += 1
                cost = _estimate_task_cost(task_type)
                # Estimate runtime for cost (use base runtime)
                runtime_min = BASE_RUNTIME_MIN.get(task_type, 5)
                stats["runtime_minutes"] += runtime_min
                stats["estimated_cost"] += cost

            elif status in ("exhausted", "failed"):
                stats["tasks_failed"] += 1

    return stats


def _collect_from_task_files(month: str, operator_id: str,
                               client_id: str | None) -> dict:
    """Collect task stats from task state files for the given month."""
    tasks_dir = _resolve_tenant_tasks_dir(operator_id, client_id)
    month_prefix = f"{month}"

    stats = {
        "tasks_submitted": 0,
        "tasks_completed": 0,
        "tasks_failed": 0,
        "runtime_minutes": 0.0,
        "estimated_cost": 0.0,
    }

    if not tasks_dir.exists():
        return stats

    for f in tasks_dir.glob("*.json"):
        try:
            with open(f) as fh:
                task = json.load(fh)
        except Exception:
            continue

        created_at = task.get("created_at", "")
        if not created_at.startswith(month_prefix):
            continue

        task_type = task.get("task_type", "unknown")
        status = task.get("status", "")

        stats["tasks_submitted"] += 1

        if status in ("completed", "validated"):
            stats["tasks_completed"] += 1
            runtime_min = BASE_RUNTIME_MIN.get(task_type, 5)
            stats["runtime_minutes"] += runtime_min
            stats["estimated_cost"] += _estimate_task_cost(task_type)
        elif status in ("exhausted", "failed"):
            stats["tasks_failed"] += 1

    return stats


# ── Report generation ────────────────────────────────────────────────────────

def generate_report(operator_id: str, client_id: str | None,
                    month: str) -> tuple[Path, Path]:
    """Generate CSV and JSON reports. Returns (csv_path, json_path)."""

    # Collect stats — prefer metrics store, fall back to task files
    metrics_stats = _collect_from_metrics(month, operator_id, client_id)
    file_stats = _collect_from_task_files(month, operator_id, client_id)

    # Merge: use metrics if available, else files
    def _merge(a: dict, b: dict) -> dict:
        merged = {}
        for k in a:
            val = a[k] if a[k] != 0 else b.get(k, 0)
            merged[k] = val
        for k in b:
            if k not in merged:
                merged[k] = b[k]
        return merged

    stats = _merge(metrics_stats, file_stats)
    resources = _get_resource_saturation()

    report = {
        "report_month": month,
        "operator_id": operator_id,
        "client_id": client_id or "(all)",
        "generated_at": datetime.now(UTC).isoformat(),
        "tasks_submitted": stats["tasks_submitted"],
        "tasks_completed": stats["tasks_completed"],
        "tasks_failed": stats["tasks_failed"],
        "runtime_minutes": round(stats["runtime_minutes"], 1),
        "estimated_cost": round(stats["estimated_cost"], 4),
        "resource_saturation": resources,
    }

    # CSV
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    client_str = client_id or "all"
    csv_path = REPORTS_DIR / f"tenant-usage-{operator_id}-{client_str}-{month}.csv"
    json_path = REPORTS_DIR / f"tenant-usage-{operator_id}-{client_str}-{month}.json"

    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "report_month", "operator_id", "client_id",
            "tasks_submitted", "tasks_completed", "tasks_failed",
            "runtime_minutes", "estimated_cost",
            "disk_pct", "mem_pct",
        ])
        writer.writeheader()
        writer.writerow({
            "report_month": report["report_month"],
            "operator_id": report["operator_id"],
            "client_id": report["client_id"],
            "tasks_submitted": report["tasks_submitted"],
            "tasks_completed": report["tasks_completed"],
            "tasks_failed": report["tasks_failed"],
            "runtime_minutes": report["runtime_minutes"],
            "estimated_cost": report["estimated_cost"],
            "disk_pct": resources["disk_pct"],
            "mem_pct": resources["mem_pct"],
        })

    with open(json_path, "w") as f:
        json.dump(report, f, indent=2)

    return csv_path, json_path


def main():
    parser = argparse.ArgumentParser(description="MAA Tenant Usage & Governance Report")
    parser.add_argument("--operator", required=True, help="Operator ID")
    parser.add_argument("--client", default=None, help="Client ID (optional — all clients)")
    parser.add_argument("--month", required=True, help="Month in YYYY-MM format")
    args = parser.parse_args()

    # Validate month format
    try:
        datetime.strptime(args.month, "%Y-%m")
    except ValueError:
        print(f"ERROR: --month must be YYYY-MM, got: {args.month}")
        sys.exit(1)

    csv_path, json_path = generate_report(args.operator, args.client, args.month)

    print(f"Report generated:")
    print(f"  CSV:  {csv_path}")
    print(f"  JSON: {json_path}")

    # Quick summary
    with open(json_path) as f:
        report = json.load(f)
    print()
    print(f"Summary for {args.operator}/{args.client or 'all'} — {args.month}:")
    print(f"  Tasks submitted: {report['tasks_submitted']}")
    print(f"  Tasks completed: {report['tasks_completed']}")
    print(f"  Tasks failed:   {report['tasks_failed']}")
    print(f"  Runtime:        {report['runtime_minutes']} min")
    print(f"  Est. cost:      ${report['estimated_cost']:.4f}")
    print(f"  Disk usage:     {report['resource_saturation']['disk_pct']}%")
    print(f"  Mem usage:      {report['resource_saturation']['mem_pct']}%")


if __name__ == "__main__":
    main()
