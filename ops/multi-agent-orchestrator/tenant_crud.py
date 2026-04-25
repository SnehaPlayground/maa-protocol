#!/usr/bin/env python3
"""
Tenant CRUD — Operator and Client lifecycle management.

Usage:
    # Operator management
    python3 tenant_crud.py create-operator <operator_id> <label>
    python3 tenant_crud.py get-operator <operator_id>
    python3 tenant_crud.py list-operators
    python3 tenant_crud.py update-operator <operator_id> [--max-tasks-per-hour N] [--max-concurrent N]

    # Client management
    python3 tenant_crud.py create-client <operator_id> <client_id> <label>
    python3 tenant_crud.py get-client <operator_id> <client_id>
    python3 tenant_crud.py list-clients <operator_id>
    python3 tenant_crud.py update-client <operator_id> <client_id> [--max-tasks-per-hour N] [--rate-limit-window N]
    python3 tenant_crud.py deactivate-client <operator_id> <client_id>

    # Tenant onboarding (all-in-one)
    python3 tenant_crud.py onboard <operator_id> <client_id> <operator_label> <client_label> [--max-tasks-per-hour N]

    # Usage report
    python3 tenant_crud.py usage <operator_id> [<client_id>] [--since 24]

Examples:
    python3 tenant_crud.py create-operator default_operator "Default Operator"
    python3 tenant_crud.py create-client default_operator acme "ACME Corp" --max-tasks-per-hour 50
    python3 tenant_crud.py usage default_operator acme --since 48
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, UTC
from pathlib import Path

# Add orchestrator path for imports
sys.path.insert(0, str(Path(__file__).parent))
from tenant_gate import (
    load_operator_config, load_client_config,
    save_operator_config, save_client_config,
    _default_operator_config, _default_client_config,
    TENANTS_ROOT,
)
from tenant_paths import TenantPathResolver
from tenant_context import parse_tenant_context, DEFAULT_TENANT


# ── Output helpers ─────────────────────────────────────────────────────────────

def green(msg: str) -> str:  return f"\033[92m{msg}\033[0m"
def red(msg: str)   -> str:  return f"\033[91m{msg}\033[0m"
def yellow(msg: str) -> str: return f"\033[93m{msg}\033[0m"
def bold(msg: str)  -> str:  return f"\033[1m{msg}\033[0m"


def exit_err(msg: str) -> None:
    print(red(f"ERROR: {msg}"), file=sys.stderr)
    sys.exit(1)


def exit_ok(msg: str) -> None:
    print(green(msg))


# ── RBAC helper ────────────────────────────────────────────────────────────────

def _require_operator():
    """Enforce OPERATOR role for all mutating command invocations."""
    from access_control import assert_operator
    assert_operator("tenant_crud.mutation")


# ── Operator CRUD ──────────────────────────────────────────────────────────────

def cmd_create_operator(operator_id: str, label: str) -> None:
    _require_operator()
    if operator_id == "default":
        exit_err("Cannot create operator 'default' — reserved for system")
    if not operator_id or not label:
        exit_err("operator_id and label are required")

    op_path = TENANTS_ROOT / operator_id
    if op_path.exists():
        exit_err(f"Operator '{operator_id}' already exists at {op_path}")

    config = _default_operator_config(operator_id)
    config["label"] = label
    config["created_at"] = datetime.now(UTC).isoformat()
    config["status"] = "active"

    ok = save_operator_config(operator_id, config)
    if not ok:
        exit_err(f"Failed to write operator config")

    # Bootstrap tenant directory structure
    resolver = parse_tenant_context({"operator_id": operator_id, "client_id": operator_id})
    path_resolver = TenantPathResolver(resolver)
    path_resolver.ensure_dirs()

    exit_ok(f"Created operator '{operator_id}' ({label}) at {op_path}")


def cmd_get_operator(operator_id: str) -> None:
    cfg = load_operator_config(operator_id)
    print(json.dumps(cfg, indent=2))


def cmd_list_operators() -> None:
    if not TENANTS_ROOT.exists():
        print("[]")
        return
    operators = []
    for op_dir in sorted(TENANTS_ROOT.iterdir()):
        if not op_dir.is_dir():
            continue
        # Skip the 'clients' subdir (partha has both partha/ and partha/clients/ — show partha only)
        if (op_dir / "clients").is_dir() or (op_dir / "tasks").is_dir():
            # This is an operator root — get its config
            cfg = load_operator_config(op_dir.name)
            operators.append(cfg)
        else:
            # Subdirectory, not an operator
            continue
    print(f"\n{bold('Operators')}")
    print("-" * 60)
    for op in operators:
        status_flag = green("●") if op.get("status") == "active" else red("○")
        print(f"  {status_flag} {bold(op['operator_id'])} — {op.get('label', '(no label)')}")
        print(f"      max_tasks/hr: {op.get('max_tasks_per_hour', '?')}"
              f"  |  max_concurrent: {op.get('max_concurrent_tasks', '?')}"
              f"  |  created: {op.get('created_at', '?')[:10]}")
        clients = op.get("clients", {}) or {}
        if clients:
            print(f"      clients: {', '.join(clients.keys())}")
        print()
    print(f"Total: {len(operators)} operator(s)")


def cmd_update_operator(operator_id: str, **kwargs) -> None:
    _require_operator()
    if operator_id == "default":
        exit_err("Cannot update operator 'default'")
    cfg = load_operator_config(operator_id)
    for key, value in kwargs.items():
        if value is not None:
            cfg[key] = value
    ok = save_operator_config(operator_id, cfg)
    if ok:
        exit_ok(f"Updated operator '{operator_id}'")


# ── Client CRUD ───────────────────────────────────────────────────────────────

def cmd_create_client(operator_id: str, client_id: str, label: str, **kwargs) -> None:
    _require_operator()
    if operator_id == "default":
        exit_err("Cannot add clients to operator 'default'")
    if not client_id or not label:
        exit_err("client_id and label are required")

    op_path = TENANTS_ROOT / operator_id
    if not op_path.exists():
        exit_err(f"Operator '{operator_id}' does not exist — create it first")

    cl_path = TENANTS_ROOT / operator_id / "clients" / client_id
    if cl_path.exists():
        exit_err(f"Client '{client_id}' already exists at {cl_path}")

    config = _default_client_config(client_id)
    config["label"] = label
    config["created_at"] = datetime.now(UTC).isoformat()
    config["status"] = "active"
    if kwargs.get("max_tasks_per_hour"):
        config["max_tasks_per_hour"] = int(kwargs["max_tasks_per_hour"])

    ok = save_client_config(operator_id, client_id, config)
    if not ok:
        exit_err("Failed to write client config")

    # Bootstrap client tenant path structure
    resolver = parse_tenant_context({"operator_id": operator_id, "client_id": client_id})
    path_resolver = TenantPathResolver(resolver)
    path_resolver.ensure_dirs()

    # Register client in operator config
    op_cfg = load_operator_config(operator_id)
    if "clients" not in op_cfg or op_cfg["clients"] is None:
        op_cfg["clients"] = {}
    op_cfg["clients"][client_id] = {"label": label, "status": "active"}
    save_operator_config(operator_id, op_cfg)

    exit_ok(f"Created client '{client_id}' under operator '{operator_id}' ({label})")


def cmd_get_client(operator_id: str, client_id: str) -> None:
    cfg = load_client_config(operator_id, client_id)
    print(json.dumps(cfg, indent=2))


def cmd_list_clients(operator_id: str) -> None:
    op_path = TENANTS_ROOT / operator_id
    if not op_path.exists():
        exit_err(f"Operator '{operator_id}' does not exist")

    op_cfg = load_operator_config(operator_id)
    clients_meta = op_cfg.get("clients", {}) or {}

    clients_dir = op_path / "clients"
    client_ids = []
    if clients_dir.is_dir():
        client_ids = [d.name for d in clients_dir.iterdir() if d.is_dir()]

    print(f"\n{bold(f'Clients of {operator_id}')}")
    print("-" * 60)
    for cl_id in sorted(client_ids):
        cfg = load_client_config(operator_id, cl_id)
        meta = clients_meta.get(cl_id, {})
        status_flag = green("●") if cfg.get("status") == "active" else red("○")
        print(f"  {status_flag} {bold(cl_id)} — {cfg.get('label', '(no label)')}")
        print(f"      max_tasks/hr: {cfg.get('max_tasks_per_hour', '?')}"
              f"  |  max_concurrent: {cfg.get('max_concurrent_tasks', '?')}"
              f"  |  status: {cfg.get('status', '?')}")
        print()
    print(f"Total: {len(client_ids)} client(s)")


def cmd_update_client(operator_id: str, client_id: str, **kwargs) -> None:
    _require_operator()
    if operator_id == "default":
        exit_err("Cannot update clients under operator 'default'")
    cfg = load_client_config(operator_id, client_id)
    for key, value in kwargs.items():
        if value is not None:
            cfg[key] = value
    ok = save_client_config(operator_id, client_id, cfg)
    if ok:
        exit_ok(f"Updated client '{client_id}' under operator '{operator_id}'")


def cmd_deactivate_client(operator_id: str, client_id: str) -> None:
    _require_operator()
    cfg = load_client_config(operator_id, client_id)
    cfg["status"] = "deactivated"
    cfg["deactivated_at"] = datetime.now(UTC).isoformat()
    save_client_config(operator_id, client_id, cfg)
    exit_ok(f"Deactivated client '{client_id}' under operator '{operator_id}'")


# ── Onboarding ────────────────────────────────────────────────────────────────

def cmd_onboard(operator_id: str, client_id: str, operator_label: str,
                client_label: str, **kwargs) -> None:
    """Create operator (if needed) + client in one shot."""
    _require_operator()
    # 1. Create or update operator
    op_path = TENANTS_ROOT / operator_id
    if not op_path.exists():
        print(f"[1/3] Creating operator '{operator_id}'...")
        cmd_create_operator(operator_id, operator_label)
    else:
        print(f"[1/3] Operator '{operator_id}' already exists — skipping")

    # 2. Create client
    print(f"[2/3] Creating client '{client_id}'...")
    # Check if already exists
    cl_path = TENANTS_ROOT / operator_id / "clients" / client_id
    if cl_path.exists():
        print(f"  Client '{client_id}' already exists — skipping creation")
    else:
        cmd_create_client(operator_id, client_id, client_label, **kwargs)

    # 3. Verify paths
    print(f"[3/3] Verifying tenant isolation...")
    resolver = parse_tenant_context({"operator_id": operator_id, "client_id": client_id})
    path_resolver = TenantPathResolver(resolver)
    path_resolver.ensure_dirs()
    tasks_dir = path_resolver.resolve("tasks")
    logs_dir = path_resolver.resolve("logs")
    outputs_dir = path_resolver.resolve("outputs")
    audit_dir = path_resolver.resolve("audit")
    print(f"  tasks/  → {tasks_dir}  [{'OK' if tasks_dir.exists() else 'MISSING'}]")
    print(f"  logs/   → {logs_dir}   [{'OK' if logs_dir.exists() else 'MISSING'}]")
    print(f"  outputs/→ {outputs_dir} [{'OK' if outputs_dir.exists() else 'MISSING'}]")
    print(f"  audit/  → {audit_dir}  [{'OK' if audit_dir.exists() else 'MISSING'}]")

    print(f"\n{bold('Onboarding complete!')}")
    print(f"  Tenant: {operator_id}/{client_id}")
    print(f"  Test: python3 tenant_crud.py usage {operator_id} {client_id}")


# ── Tenant usage report ───────────────────────────────────────────────────────

def _task_state_files(operator_id: str, client_id: str | None = None) -> list[Path]:
    """Find all task state files for a tenant."""
    files = []
    if client_id:
        base = TENANTS_ROOT / operator_id / "clients" / client_id / "tasks"
        if base.exists():
            files.extend(base.glob("*.json"))
        return files
    # Operator-level: all client tasks + operator-level tasks
    op_base = TENANTS_ROOT / operator_id
    for sub in ("tasks",):
        p = op_base / sub
        if p.exists():
            files.extend(p.glob("*.json"))
    clients_dir = op_base / "clients"
    if clients_dir.is_dir():
        for cl_dir in clients_dir.iterdir():
            if not cl_dir.is_dir():
                continue
            tasks_dir = cl_dir / "tasks"
            if tasks_dir.exists():
                files.extend(tasks_dir.glob("*.json"))
    return files


def _completion_files(operator_id: str, client_id: str | None = None) -> list[Path]:
    """Find all completion files for a tenant."""
    files = []
    if client_id:
        base = TENANTS_ROOT / operator_id / "clients" / client_id / "logs"
        if base.exists():
            files.extend(base.glob("*.completion"))
        return files
    op_base = TENANTS_ROOT / operator_id
    for sub in ("logs",):
        p = op_base / sub
        if p.exists():
            files.extend(p.glob("*.completion"))
    clients_dir = op_base / "clients"
    if clients_dir.is_dir():
        for cl_dir in clients_dir.iterdir():
            if not cl_dir.is_dir():
                continue
            logs_dir = cl_dir / "logs"
            if logs_dir.exists():
                files.extend(logs_dir.glob("*.completion"))
    return files


def cmd_usage(operator_id: str, client_id: str | None = None, since_hours: int = 24) -> None:
    """Print a tenant usage report."""
    now = time.time()
    cutoff = now - (since_hours * 3600)

    task_files = _task_state_files(operator_id, client_id)
    comp_files = _completion_files(operator_id, client_id)

    submitted = 0
    completed = 0
    failed = 0
    exhausted = 0
    running = 0
    pending = 0
    status_counts = {}
    task_types = {}
    failure_reasons: dict[str, int] = {}
    recent = []

    for tf in task_files:
        try:
            state = json.loads(tf.read_text())
        except Exception:
            continue
        ts = state.get("created_at", "")
        try:
            ts_epoch = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
        except Exception:
            continue
        if ts_epoch < cutoff:
            continue

        submitted += 1
        s = state.get("status", "?")
        status_counts[s] = status_counts.get(s, 0) + 1
        tt = state.get("task_type", "?")
        task_types[tt] = task_types.get(tt, 0) + 1
        if s == "completed":
            completed += 1
        elif s == "exhausted":
            exhausted += 1
        elif s == "running":
            running += 1
        elif s == "pending":
            pending += 1

        # FIX: collect failure reasons inside the same loop, respecting the time cutoff
        if s in ("exhausted", "needs_revision"):
            reason = state.get("child_failure_reason") or state.get("last_error") or "unknown"
            reason = reason[:60]
            failure_reasons[reason] = failure_reasons.get(reason, 0) + 1

    for cf in comp_files:
        # completion files have their own timestamp in filename — approximate
        try:
            stat = cf.stat()
            if stat.st_mtime < cutoff:
                continue
        except Exception:
            continue
        # Could cross-check against state files but approximate is fine for report

    error_files = [f for f in task_files if f.exists()]
    # Re-scan for failed (exhausted + needs_revision as failure proxy)
    failed = status_counts.get("exhausted", 0)
    needs_rev = status_counts.get("needs_revision", 0)

    # Top failure reasons
    top_failures = sorted(failure_reasons.items(), key=lambda x: -x[1])[:5]

    print(f"\n{'='*60}")
    print(f"{bold(f'Tenant Usage Report')}")
    print(f"  Operator: {operator_id} | Client: {client_id or '(operator-level)'}")
    print(f"  Window: last {since_hours}h | Generated: {datetime.now(UTC).isoformat()[:19]}Z")
    print(f"{'='*60}")
    print(f"\n  {bold('Task Summary')}")
    print(f"  {'─'*40}")
    print(f"  Submitted:  {submitted}")
    print(f"  Completed: {green(str(completed))}  |  Failed: {red(str(failed + needs_rev))}")
    print(f"  Running:   {running}  |  Pending: {pending}")
    print(f"  Exhausted: {exhausted}")

    if status_counts:
        print(f"\n  {bold('Status Breakdown')}")
        print(f"  {'─'*40}")
        for s, cnt in sorted(status_counts.items()):
            flag = green("●") if s == "completed" else red("●") if s in ("exhausted", "needs_revision") else yellow("●")
            print(f"  {flag} {s}: {cnt}")

    if task_types:
        print(f"\n  {bold('Task Types')}")
        print(f"  {'─'*40}")
        for tt, cnt in sorted(task_types.items(), key=lambda x: -x[1]):
            print(f"  {tt}: {cnt}")

    if top_failures:
        print(f"\n  {bold('Top Failure Reasons')}")
        print(f"  {'─'*40}")
        for reason, cnt in top_failures:
            print(f"  {red('✗')} {reason}: {cnt}")

    total_done = completed + failed + needs_rev
    error_rate = (failed + needs_rev) / submitted * 100 if submitted > 0 else 0
    print(f"\n  {bold('Error Rate')}: {red(f'{error_rate:.1f}%') if error_rate > 5 else green(f'{error_rate:.1f}%')}")
    print(f"{'='*60}\n")


# ── CLI entry point ────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Tenant CRUD — Operator and Client lifecycle management",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # Operator commands
    co = sub.add_parser("create-operator", help="Create a new operator")
    co.add_argument("operator_id")
    co.add_argument("label")

    go = sub.add_parser("get-operator", help="Get operator config")
    go.add_argument("operator_id")

    sub.add_parser("list-operators", help="List all operators")

    upd_op = sub.add_parser("update-operator", help="Update operator config")
    upd_op.add_argument("operator_id")
    upd_op.add_argument("--max-tasks-per-hour", type=int)
    upd_op.add_argument("--max-concurrent", type=int)

    # Client commands
    add_cl = sub.add_parser("create-client", help="Create a new client")
    add_cl.add_argument("operator_id")
    add_cl.add_argument("client_id")
    add_cl.add_argument("label")
    add_cl.add_argument("--max-tasks-per-hour", type=int)

    gc = sub.add_parser("get-client", help="Get client config")
    gc.add_argument("operator_id")
    gc.add_argument("client_id")

    lc = sub.add_parser("list-clients", help="List clients for an operator")
    lc.add_argument("operator_id")

    upd_cl = sub.add_parser("update-client", help="Update client config")
    upd_cl.add_argument("operator_id")
    upd_cl.add_argument("client_id")
    upd_cl.add_argument("--max-tasks-per-hour", type=int)
    upd_cl.add_argument("--rate-limit-window", type=int)

    del_cl = sub.add_parser("deactivate-client", help="Deactivate a client")
    del_cl.add_argument("operator_id")
    del_cl.add_argument("client_id")

    # Onboarding
    onb = sub.add_parser("onboard", help="Full operator + client onboarding")
    onb.add_argument("operator_id")
    onb.add_argument("client_id")
    onb.add_argument("operator_label")
    onb.add_argument("client_label")
    onb.add_argument("--max-tasks-per-hour", type=int)

    # Usage
    usg = sub.add_parser("usage", help="Tenant usage report")
    usg.add_argument("operator_id")
    usg.add_argument("client_id", nargs="?", default=None)
    usg.add_argument("--since", type=int, default=24, help="Hours to look back (default: 24)")

    # Aliases
    sub.add_parser("list-tenants", help="Alias for list-operators")
    get_usg = sub.add_parser("get-usage", help="Alias for usage")
    get_usg.add_argument("operator_id")
    get_usg.add_argument("client_id", nargs="?", default=None)
    get_usg.add_argument("--since", type=int, default=24)

    args = parser.parse_args()

    match args.cmd:
        case "create-operator":
            cmd_create_operator(args.operator_id, args.label)
        case "get-operator":
            cmd_get_operator(args.operator_id)
        case "list-operators":
            cmd_list_operators()
        case "update-operator":
            cmd_update_operator(args.operator_id,
                                max_tasks_per_hour=args.max_tasks_per_hour,
                                max_concurrent=args.max_concurrent)
        case "create-client":
            cmd_create_client(args.operator_id, args.client_id, args.label,
                              max_tasks_per_hour=args.max_tasks_per_hour)
        case "get-client":
            cmd_get_client(args.operator_id, args.client_id)
        case "list-clients":
            cmd_list_clients(args.operator_id)
        case "update-client":
            cmd_update_client(args.operator_id, args.client_id,
                               max_tasks_per_hour=args.max_tasks_per_hour,
                               rate_limit_window=args.rate_limit_window)
        case "deactivate-client":
            cmd_deactivate_client(args.operator_id, args.client_id)
        case "onboard":
            cmd_onboard(args.operator_id, args.client_id,
                        args.operator_label, args.client_label,
                        max_tasks_per_hour=args.max_tasks_per_hour)
        case "usage":
            cmd_usage(args.operator_id, args.client_id, args.since)
        case "list-tenants":
            cmd_list_operators()
        case "get-usage":
            cmd_usage(args.operator_id, args.client_id, args.since)


if __name__ == "__main__":
    # ── Phase 10 RBAC: all CLI commands require OPERATOR role ─────────────────
    from access_control import require_operator_role
    try:
        require_operator_role()
    except PermissionError as e:
        print(f"RBAC: {e}", file=sys.stderr)
        sys.exit(1)
    except SystemExit:
        raise
    main()
