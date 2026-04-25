#!/usr/bin/env python3
"""
Maa Protocol Observability — Core Metric Collection CLI
=======================================================
Log-structured event store for multi-agent orchestration metrics.
Stores to: /root/.openclaw/workspace/data/observability/maa_metrics.json

Usage:
    python maa_metrics.py record --type call     --label "sneha.send_email" --session-id "abc"
    python maa_metrics.py record --type error     --label "research.fetch_failed" --details "404"
    python maa_metrics.py record --type latency   --label "sneha.send_email" --value 1342
    python maa_metrics.py record --type task      --label "market_brief.generate" --session-id "abc" --status "completed"
    python maa_metrics.py dashboard
    python maa_metrics.py summary --since 24
    python maa_metrics.py resources
    python maa_metrics.py export --format json --output report.json
    python maa_metrics.py reset --confirm
"""

import argparse
import json
import os
import sys
import traceback
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

# psutil is the only external dependency
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

# ─── Paths ────────────────────────────────────────────────────────────────────

BASE_DIR = Path("/root/.openclaw/workspace")
DATA_DIR = BASE_DIR / "data" / "observability"
STORE_FILE = DATA_DIR / "maa_metrics.json"
LOG_DIR = BASE_DIR / "logs"
MAX_ITEMS_PER_BUCKET = 2000

DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ─── JSON Store Helpers ────────────────────────────────────────────────────────

def load_metrics() -> dict:
    """Load existing metrics store, or return fresh template."""
    if STORE_FILE.exists():
        try:
            with open(STORE_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            # Corrupt file — start fresh
            pass
    return {
        "version": "1.0",
        "start_time": datetime.now(timezone.utc).timestamp(),
        "calls": [],
        "errors": [],
        "latency": [],
        "tasks": []
    }

RETENTION_LOG = LOG_DIR / "retention.log"

def save_metrics(metrics: dict) -> None:
    """Atomically write metrics store.

    Retention: each bucket capped at MAX_ITEMS_PER_BUCKET (2000).
    SER-2 fix: Before silently dropping oldest entries, write a retention log line
    so there's an audit trail of what was lost and when.
    """
    for key in ("calls", "errors", "latency", "tasks"):
        if key in metrics and isinstance(metrics[key], list) and len(metrics[key]) > MAX_ITEMS_PER_BUCKET:
            excess = len(metrics[key]) - MAX_ITEMS_PER_BUCKET
            # Log before dropping so we know what was lost
            _write_retention_log(key, excess, metrics[key])
            metrics[key] = metrics[key][-MAX_ITEMS_PER_BUCKET:]
    tmp = STORE_FILE.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(metrics, f, indent=2)
    tmp.rename(STORE_FILE)


def _write_retention_log(bucket: str, count: int, items: list) -> None:
    """Write a retention log line before oldest entries are dropped."""
    if count <= 0:
        return
    oldest_ts = items[0].get("timestamp", "unknown") if items else "unknown"
    newest_ts = items[-1].get("timestamp", "unknown") if items else "unknown"
    try:
        with open(RETENTION_LOG, "a") as f:
            f.write(f"[{datetime.now(timezone.utc).isoformat()}] "
                     f"dropped {count} oldest {bucket} entries "
                     f"(range: {oldest_ts} → {newest_ts})\n")
    except Exception:
        pass  # Never fail the caller

def _emergency_log(bucket: str, entry: dict, err: Exception) -> None:
    """CRIT-3 fix: Third-tier emergency log — appends a single line to a plain text file.
    This is the last resort before silently dropping an error. It NEVER fails because
    it only appends one line and the file is created with os.O_WRONLY|os.O_CREAT|os.O_APPEND.
    """
    import os
    emergency_path = DATA_DIR / "record_emergencies.log"
    try:
        fd = os.open(str(emergency_path), os.O_WRONLY | os.O_CREAT | os.O_APPEND)
        try:
            line = f"[{datetime.now(timezone.utc).isoformat()}] bucket={bucket} label={entry.get('label','?')} err={err}\n"
            os.write(fd, line.encode("utf-8"))
        finally:
            os.close(fd)
    except Exception:
        # If even this fails (truly impossible), print to stdout as absolute last resort
        print(f"[MAA METRICS EMERGENCY] could not write emergency log: bucket={bucket} label={entry.get('label','?')} err={err}",
              flush=True)


def _record_with_fallback(metrics: dict, key: str, entry: dict) -> bool:
    """Best-effort record with HARD internal failure reporting.

    Three-tier failure handling:
      1. Write to primary metrics store → on failure:
      2. Write to fallback error log   → on failure:
      3. Write to emergency single-line log (last resort, NEVER silently drops)

    In all failure cases, also print to stderr.
    Returns True on success, False on complete failure.
    """
    try:
        metrics[key].append(entry)
        save_metrics(metrics)
        return True
    except Exception as record_err:
        err_msg = f"primary store failed key={key}: {record_err}"
        print(f"[MAA METRICS ERROR] {err_msg}", file=sys.stderr)
        # Fallback: write to a local error log file
        try:
            err_log = DATA_DIR / "record_errors.log"
            with open(err_log, "a") as f:
                f.write(f"[{datetime.now(timezone.utc).isoformat()}] "
                        f"record failed key={key}: {record_err}\n"
                        f"{traceback.format_exc()}\n")
        except Exception as fallback_err:
            # Third tier — emergency single-line log (append-only, never throws)
            _emergency_log(key, entry, fallback_err)
        # Print to stderr so it shows up in process output
        print(f"[MAA METRICS ERROR] Failed to record {key}: {record_err}", file=sys.stderr)
        return False

# ─── Record Commands ───────────────────────────────────────────────────────────

def record_call(label: str, session_id: Optional[str] = None,
                agent: Optional[str] = None,
                operator_id: Optional[str] = None,
                client_id: Optional[str] = None) -> None:
    # Guard test labels from polluting production metrics
    if label.startswith("test."):
        return
    metrics = load_metrics()
    entry = {
        "label": label,
        "session_id": session_id or "",
        "agent": agent or "unknown",
        "operator_id": operator_id or "",
        "client_id": client_id or "",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    _record_with_fallback(metrics, "calls", entry)
    print(f"[call] {label}")

def record_error(label: str, details: str = "",
                 session_id: Optional[str] = None,
                 agent: Optional[str] = None,
                 operator_id: Optional[str] = None,
                 client_id: Optional[str] = None) -> None:
    # Guard test labels from polluting production error rates
    if label.startswith("test."):
        return
    # Always print errors to stderr — never lose an error silently
    print(f"[MAA ERROR] {label} — {details}", file=sys.stderr)
    metrics = load_metrics()
    tb = traceback.format_exc()
    entry = {
        "label": label,
        "details": details or "No details",
        "stack_trace": tb[:2000] if tb else "",
        "session_id": session_id or "",
        "agent": agent or "unknown",
        "operator_id": operator_id or "",
        "client_id": client_id or "",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    _record_with_fallback(metrics, "errors", entry)
    print(f"[error] {label} — {details}")

def record_latency(label: str, value_ms: float,
                   session_id: Optional[str] = None,
                   agent: Optional[str] = None,
                   operator_id: Optional[str] = None,
                   client_id: Optional[str] = None) -> None:
    # FIX-5: Guard test labels from polluting production error rates
    # Skip recording if label starts with "test." (regression test noise)
    if label.startswith("test."):
        return
    metrics = load_metrics()
    entry = {
        "label": label,
        "value_ms": round(value_ms, 2),
        "session_id": session_id or "",
        "agent": agent or "unknown",
        "operator_id": operator_id or "",
        "client_id": client_id or "",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    _record_with_fallback(metrics, "latency", entry)
    print(f"[latency] {label} — {round(value_ms, 1)}ms")

def record_task(label: str, status: str = "completed",
                session_id: Optional[str] = None,
                agent: Optional[str] = None,
                operator_id: Optional[str] = None,
                client_id: Optional[str] = None) -> None:
    """Record task-level event: start / completed / failed / waiting."""
    if label.startswith("test."):
        return
    metrics = load_metrics()
    entry = {
        "label": label,
        "status": status,
        "session_id": session_id or "",
        "agent": agent or "unknown",
        "operator_id": operator_id or "",
        "client_id": client_id or "",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    _record_with_fallback(metrics, "tasks", entry)
    print(f"[task] {label} — {status}")

# ─── Dashboard ─────────────────────────────────────────────────────────────────

def _load_recent_maintenance(limit: int = 5):
    decisions_dir = BASE_DIR / "memory" / "maintenance_decisions"
    if not decisions_dir.exists():
        return []
    entries = []
    for path in sorted(decisions_dir.glob("*.jsonl")):
        try:
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except IOError:
            continue
    entries.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return entries[:limit]


def _ago(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)}s ago"
    elif seconds < 3600:
        return f"{int(seconds//60)}m ago"
    elif seconds < 86400:
        return f"{int(seconds//3600)}h ago"
    else:
        return f"{int(seconds//86400)}d ago"


def print_dashboard(since_hours: Optional[int] = None, tenant_filter: Optional[str] = None) -> None:
    """
    Print an ASCII dashboard of aggregated metrics.
    Error rate is shown per-agent (not globally blended) to avoid misleading totals.
    
    tenant_filter: format "operator_id" or "operator_id/client_id".
    """
    metrics = load_metrics()
    now = datetime.now(timezone.utc).timestamp()
    start = metrics.get("start_time") or now
    uptime_s = now - start
    uptime_h = int(uptime_s // 3600)
    uptime_m = int((uptime_s % 3600) // 60)

    # Time window filter
    cutoff = None
    if since_hours:
        cutoff = (datetime.fromtimestamp(now, tz=timezone.utc)
                  - timedelta(hours=since_hours)).timestamp()

    def window(items):
        if cutoff is None:
            filtered = items
        else:
            filtered = [i for i in items
                        if datetime.fromisoformat(i["timestamp"]).timestamp() >= cutoff]
        # Tenant filter: match operator/client if present in entry
        if tenant_filter:
            parts = tenant_filter.split("/")
            op_filter = parts[0]
            cl_filter = parts[1] if len(parts) > 1 else None
            def tenant_match(item):
                return item.get("operator_id") == op_filter and                        (cl_filter is None or item.get("client_id") == cl_filter)
            filtered = [i for i in filtered if tenant_match(i)]
        return filtered

    calls = window(metrics["calls"])
    errors = window(metrics["errors"])
    latencies = window(metrics["latency"])
    tasks = window(metrics["tasks"])

    total_calls = len(calls)
    total_errors = len(errors)
    total_tasks = len(tasks)

    # Per-agent breakdown: each agent's own error rate
    # This replaces the old misleading blended global error rate
    # FIX: use completed task count (not start+completed), since each successful task
    # appears twice in the raw tasks bucket (start + completed), and counting both
    # halves the apparent error rate.
    agent_ops = {}  # agent -> {calls: 0, tasks_completed: 0, tasks_total: 0, errors: 0}
    for c in calls:
        a = c.get("agent") or "unknown"
        agent_ops.setdefault(a, {"calls": 0, "tasks_completed": 0, "tasks_total": 0, "errors": 0})["calls"] += 1
    for t in tasks:
        a = t.get("agent") or "unknown"
        agent_ops.setdefault(a, {"calls": 0, "tasks_completed": 0, "tasks_total": 0, "errors": 0})["tasks_total"] += 1
        if t.get("status") == "completed":
            agent_ops[a]["tasks_completed"] += 1
    for e in errors:
        a = e.get("agent") or "unknown"
        agent_ops.setdefault(a, {"calls": 0, "tasks_completed": 0, "tasks_total": 0, "errors": 0})["errors"] += 1

    lat_vals = [l["value_ms"] for l in latencies if "value_ms" in l]
    avg_latency = sum(lat_vals) / len(lat_vals) if lat_vals else 0.0

    # Top agents sorted by total ops volume
    top_agents = sorted(agent_ops.items(), key=lambda x: -(x[1]["calls"] + x[1]["tasks_total"]))[:5]
    active_agents = len(agent_ops)

    # Recent errors (last 5)
    recent_errors = sorted(errors, key=lambda x: x["timestamp"], reverse=True)[:5]
    recent_maintenance = _load_recent_maintenance(limit=5)

    # Print
    width = 58
    h = "═" * width

    print()
    print(f"╔{h}╗")
    print(f"║{'MAA PROTOCOL OBSERVABILITY':^{width}}║")
    print(f"╠{h}╣")

    row1 = (f"  Total Tasks:  {total_tasks:<5}  │  "
            f"Active Agents:  {active_agents:<5}")
    print(f"║{row1:^{width}}║")
    row2 = (f"  Total Calls:  {total_calls:<5}  │  "
            f"Total Errors:  {total_errors:<5}")
    print(f"║{row2:^{width}}║")
    row3 = (f"  Avg Latency: {avg_latency:>7.0f}ms  │  "
            f"Uptime:        {uptime_h}h {uptime_m:>2}m")
    print(f"║{row3:^{width}}║")
    print(f"╠{h}╣")

    # Agent breakdown — per-agent error rates (the correct view)
    if top_agents:
        header = "  AGENT BREAKDOWN (per-agent error rates):"
        print(f"║{header:^{width}}║")
        for ag, ops in top_agents:
            # FIX: denominator is calls + completed_tasks + errors.
            # This correctly shows 100% error rate for an agent whose only events are errors,
            # and shows the true blended rate when an agent has a mix of successes and failures.
            completed_tasks = ops.get("tasks_completed", 0)
            errs = ops["errors"]
            total_ops = completed_tasks + ops["calls"] + errs
            err_rate = (errs / total_ops * 100) if total_ops > 0 else 0.0
            calls_s = ops["calls"]
            tasks_s = completed_tasks
            if err_rate == 0 and errs == 0:
                err_str = "clean"
            else:
                err_str = f"{errs}err/{err_rate:.1f}%"
            row = (f"    {ag:<16} c={calls_s:<3} t={tasks_s:<3}"
                   f"  │  {err_str:>20}")
            print(f"║{row:^{width}}║")
    else:
        print(f"║{'  No operational data yet':^{width}}║")

    print(f"╠{h}╣")

    if recent_errors:
        header = "  RECENT ERRORS (most recent first):"
        print(f"║{header:^{width}}║")
        now_ts = datetime.now(timezone.utc).timestamp()
        for err in recent_errors:
            err_ts = datetime.fromisoformat(err["timestamp"]).timestamp()
            ago_s = now_ts - err_ts
            ago_str = _ago(ago_s)
            details = err.get('details', '') or ''
            if len(details) > 22:
                details = details[:22] + "…"
            row = (f"    {err['label']:<32} [{ago_str:>8}]  {details}")
            print(f"║{row:^{width}}║")
    else:
        print(f"║{'  No errors — system healthy':^{width}}║")

    print(f"╠{h}╣")
    if recent_maintenance:
        header = "  RECENT MAINTENANCE:"
        print(f"║{header:^{width}}║")
        for m in recent_maintenance:
            row = (f"    {m.get('action',''):<18} {m.get('outcome',''):<10} "
                   f"{str(m.get('details', {}))[:24]}")
            print(f"║{row:^{width}}║")
    else:
        print(f"║{'  No maintenance actions logged yet':^{width}}║")

    print(f"╚{h}╝")
    print()

# ─── Summary ──────────────────────────────────────────────────────────────────

def print_summary(since_hours: Optional[int] = None, tenant_filter: Optional[str] = None) -> None:
    """Human-readable summary without ASCII art.
    
    tenant_filter: format "operator_id" or "operator_id/client_id".
    """
    metrics = load_metrics()
    now = datetime.now(timezone.utc).timestamp()

    cutoff = None
    if since_hours:
        cutoff = (datetime.fromtimestamp(now, tz=timezone.utc)
                  - timedelta(hours=since_hours)).timestamp()

    def window(items):
        if cutoff is None:
            filtered = items
        else:
            filtered = [i for i in items
                        if datetime.fromisoformat(i["timestamp"]).timestamp() >= cutoff]
        if tenant_filter:
            parts = tenant_filter.split("/")
            op_filter = parts[0]
            cl_filter = parts[1] if len(parts) > 1 else None
            def tenant_match(item):
                return item.get("operator_id") == op_filter and                        (cl_filter is None or item.get("client_id") == cl_filter)
            filtered = [i for i in filtered if tenant_match(i)]
        return filtered

    calls = window(metrics["calls"])
    errors = window(metrics["errors"])
    latencies = window(metrics.get("latency", []))
    tasks = window(metrics.get("tasks", []))

    total_calls = len(calls)
    total_errors = len(errors)
    total_tasks = len(tasks)

    lat_vals = [l["value_ms"] for l in latencies if "value_ms" in l]
    avg_latency = sum(lat_vals) / len(lat_vals) if lat_vals else 0.0
    min_lat = min(lat_vals) if lat_vals else 0
    max_lat = max(lat_vals) if lat_vals else 0

    # Per-agent breakdown — same fix: completed tasks only
    agent_ops = {}
    for c in calls:
        a = c.get("agent") or "unknown"
        agent_ops.setdefault(a, {"calls": 0, "tasks_completed": 0, "tasks_total": 0, "errors": 0})["calls"] += 1
    for t in tasks:
        a = t.get("agent") or "unknown"
        agent_ops.setdefault(a, {"calls": 0, "tasks_completed": 0, "tasks_total": 0, "errors": 0})["tasks_total"] += 1
        if t.get("status") == "completed":
            agent_ops[a]["tasks_completed"] += 1
    for e in errors:
        a = e.get("agent") or "unknown"
        agent_ops.setdefault(a, {"calls": 0, "tasks_completed": 0, "tasks_total": 0, "errors": 0})["errors"] += 1

    print()
    print(f"  MAA PROTOCOL — METRIC SUMMARY")
    if since_hours:
        print(f"  Window: last {since_hours}h")
    print(f"  ─────────────────────────────────")
    print(f"  Tasks:       {total_tasks}")
    print(f"  Calls:       {total_calls}")
    print(f"  Errors:      {total_errors}")
    print(f"  Latency:    avg={avg_latency:.0f}ms  min={min_lat:.0f}ms  max={max_lat:.0f}ms")
    print()

    if agent_ops:
        print(f"  Per-agent breakdown:")
        for ag, ops in sorted(agent_ops.items(), key=lambda x: -(x[1]["calls"] + x[1]["tasks_total"])):
            completed_tasks = ops.get("tasks_completed", 0)
            errs = ops["errors"]
            total_ops = completed_tasks + ops["calls"] + errs
            err_rate = (errs / total_ops * 100) if total_ops > 0 else 0.0
            print(f"    {ag}: calls={ops['calls']} tasks_completed={completed_tasks} errors={errs} ({err_rate:.1f}%)")
    print()

    if errors:
        print(f"  Last 5 errors:")
        for err in sorted(errors, key=lambda x: x["timestamp"], reverse=True)[:5]:
            print(f"    [{err['timestamp']}] {err['label']} — {err.get('details', '')}")
    else:
        print(f"  No errors recorded.")
    print()

# ─── Resource Snapshot ─────────────────────────────────────────────────────────

def print_resources() -> None:
    """Live system resource snapshot using psutil."""
    if not PSUTIL_AVAILABLE:
        print("psutil not installed — install with: pip install psutil")
        return

    cpu = psutil.cpu_percent(interval=0.5)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")

    print()
    print(f"  MAA PROTOCOL — SYSTEM RESOURCES")
    print(f"  ─────────────────────────────────")
    print(f"  CPU:       {cpu:>5.1f}%")
    print(f"  Memory:    {mem.percent:>5.1f}%  ({mem.used/(1024**3):.1f}GB / {mem.total/(1024**3):.1f}GB)")
    print(f"  Disk:      {disk.percent:>5.1f}%  ({disk.used/(1024**3):.1f}GB / {disk.total/(1024**3):.1f}GB)  "
          f"free: {disk.free/(1024**3):.1f}GB")
    print()

# ─── Export ────────────────────────────────────────────────────────────────────

def export_metrics(fmt: str, output: str, tenant_filter: Optional[str] = None) -> None:
    """Export metrics to JSON or CSV.
    
    tenant_filter: format "operator_id" or "operator_id/client_id".
    """
    metrics = load_metrics()

    # Apply tenant filter if specified
    if tenant_filter:
        parts = tenant_filter.split("/")
        op_filter = parts[0]
        cl_filter = parts[1] if len(parts) > 1 else None
        def tenant_match(item):
            return item.get("operator_id") == op_filter and                    (cl_filter is None or item.get("client_id") == cl_filter)
        filtered = {}
        for key in ("calls", "errors", "latency", "tasks"):
            items = metrics.get(key, [])
            filtered[key] = [i for i in items if tenant_match(i)]
        metrics = filtered

    if fmt == "json":
        with open(output, "w") as f:
            json.dump(metrics, f, indent=2)
        print(f"Exported JSON → {output}")

    elif fmt == "csv":
        import csv
        with open(output, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["type", "label", "agent", "session_id", "timestamp", "value_ms", "details"])
            for c in metrics.get("calls", []):
                w.writerow(["call", c["label"], c.get("agent",""), c.get("session_id",""),
                            c["timestamp"], "", ""])
            for e in metrics.get("errors", []):
                w.writerow(["error", e["label"], e.get("agent",""), e.get("session_id",""),
                            e["timestamp"], "", e.get("details","")])
            for l in metrics.get("latency", []):
                w.writerow(["latency", l["label"], l.get("agent",""), l.get("session_id",""),
                            l["timestamp"], l.get("value_ms",""), ""])
        print(f"Exported CSV → {output}")


def main():
    parser = argparse.ArgumentParser(description="Maa Protocol Observability CLI")
    sub = parser.add_subparsers(dest="cmd")

    # record
    r = sub.add_parser("record", help="Record a metric event")
    r.add_argument("--type", choices=["call", "error", "latency", "task"],
                   required=True)
    r.add_argument("--label", required=True)
    r.add_argument("--details", default="")
    r.add_argument("--value", type=float, help="Latency value in ms")
    r.add_argument("--status", default="completed",
                   help="Task status: start/completed/failed/waiting")
    r.add_argument("--session-id", default=None)
    r.add_argument("--agent", default=None)
    r.add_argument("--operator-id", default=None,
                   help="Operator ID for tenant-scoped metrics")
    r.add_argument("--client-id", default=None,
                   help="Client ID for tenant-scoped metrics")

    # dashboard
    dash = sub.add_parser("dashboard", help="Print ASCII dashboard")
    dash.add_argument("--tenant", default=None,
                      help="Scope to operator/client (format: operator_id or operator_id/client_id)")
    dash.add_argument("--since", type=int, default=None,
                      help="Filter to last N hours")

    # summary
    smry = sub.add_parser("summary", help="Print plain summary")
    smry.add_argument("--since", type=int, default=None,
                      help="Filter to last N hours")
    smry.add_argument("--tenant", default=None,
                      help="Scope to operator/client (format: operator_id or operator_id/client_id)")

    # resources
    sub.add_parser("resources", help="Live resource snapshot")

    # export
    e = sub.add_parser("export", help="Export metrics")
    e.add_argument("--format", choices=["json", "csv"], required=True)
    e.add_argument("--output", required=True)
    e.add_argument("--tenant", default=None,
                  help="Scope to operator/client (format: operator_id or operator_id/client_id)")

    # reset
    rst = sub.add_parser("reset", help="Reset all metrics")
    rst.add_argument("--confirm", action="store_true",
                      help="Must be set to actually reset")

    args = parser.parse_args()

    if args.cmd == "record":
        t = args.type
        if t == "call":
            record_call(args.label, session_id=args.session_id, agent=args.agent,
                        operator_id=args.operator_id, client_id=args.client_id)
        elif t == "error":
            record_error(args.label, details=args.details,
                         session_id=args.session_id, agent=args.agent,
                         operator_id=args.operator_id, client_id=args.client_id)
        elif t == "latency":
            if args.value is None:
                print("Error: --value required for latency type", file=sys.stderr)
                sys.exit(1)
            record_latency(args.label, args.value,
                           session_id=args.session_id, agent=args.agent,
                           operator_id=args.operator_id, client_id=args.client_id)
        elif t == "task":
            record_task(args.label, status=args.status,
                        session_id=args.session_id, agent=args.agent,
                        operator_id=args.operator_id, client_id=args.client_id)

    elif args.cmd == "dashboard":
        print_dashboard(since_hours=args.since, tenant_filter=args.tenant)

    elif args.cmd == "summary":
        print_summary(since_hours=args.since, tenant_filter=args.tenant)

    elif args.cmd == "resources":
        print_resources()

    elif args.cmd == "export":
        export_metrics(args.format, args.output, tenant_filter=args.tenant)

    elif args.cmd == "reset":
        if not args.confirm:
            print("Use --confirm to actually reset.")
            sys.exit(1)
        save_metrics({
            "version": "1.0",
            "start_time": datetime.now(timezone.utc).timestamp(),
            "calls": [], "errors": [], "latency": [], "tasks": []
        })
        print("Metrics reset.")

    else:
        parser.print_help()

if __name__ == "__main__":
    main()
