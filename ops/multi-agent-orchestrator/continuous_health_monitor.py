#!/usr/bin/env python3
"""
Phase 7 — Continuous Health Monitor
===================================
Lightweight continuous check every 15 minutes that catches trust regressions
before they accumulate.

Checks:
  a. Metrics store is writable (test write + read)
  b. Task state files are not corrupt (parse all *.json in tasks/)
  c. Completion markers exist for all completed tasks
  d. No state_version regressions (monotonic attempt_history; no marker > task_state)
  e. Running children count is accurate (children in running_children.json
     actually have status=running in their task state)

Critical issues → operator alerted via the configured messaging channel
                 + interaction router signal file written
Results → logs/continuous_health_monitor.json

Crontab entry:
  */15 * * * * python3 /root/.openclaw/workspace/scripts/continuous_health_monitor.py

Author: Maa maintainer
Phase: 7 of MAA Protocol Commercial Deployment Action Plan v1.2
"""

import json
import subprocess
import sys
import time
import traceback
from datetime import datetime, UTC
from pathlib import Path

sys.path.insert(0, "/root/.openclaw/workspace/ops")

WORKSPACE = Path("/root/.openclaw/workspace")
TENANTS_ROOT = WORKSPACE / "tenants"
TASKS_DIR = WORKSPACE / "ops/multi-agent-orchestrator" / "tasks"
LOGS_DIR = WORKSPACE / "ops/multi-agent-orchestrator" / "logs"
METRICS_STORE = WORKSPACE / "data" / "observability" / "maa_metrics.json"
RUNNING_CHILDREN_FILE = LOGS_DIR / "running_children.json"
OUTPUT_FILE = LOGS_DIR / "continuous_health_monitor.json"
ALERT_FILE = LOGS_DIR / "continuous_health_monitor_alerts.json"
CONFIG_FILE = WORKSPACE / "knowledge" / "maa-product" / "runtime-config.json"
COOLDOWN_FILE = WORKSPACE / "memory" / "maintenance_decisions" / "continuous_monitor_cooldown.json"
COOLDOWN_SECONDS = 7200


def now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp") if path.suffix else path.with_name(path.name + ".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    tmp.replace(path)


def load_json(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def _load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return load_json(CONFIG_FILE)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _load_cooldown() -> dict:
    if COOLDOWN_FILE.exists():
        try:
            return load_json(COOLDOWN_FILE)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_cooldown(state: dict) -> None:
    atomic_write_json(COOLDOWN_FILE, state)


def _is_in_cooldown(check_name: str) -> tuple[bool, int]:
    state = _load_cooldown()
    last = state.get(check_name, 0)
    elapsed = time.time() - last
    if elapsed < COOLDOWN_SECONDS:
        return True, int(COOLDOWN_SECONDS - elapsed)
    return False, 0


def _touch_cooldown(check_name: str) -> None:
    state = _load_cooldown()
    state[check_name] = time.time()
    _save_cooldown(state)


def _iter_tenant_state_files() -> list[Path]:
    """Yield task state file paths across default + all tenant directories."""
    # Default
    if TASKS_DIR.exists():
        for f in sorted(TASKS_DIR.glob("*.json")):
            if f.name != "README.md":
                yield f
    # Tenant-scoped
    if not TENANTS_ROOT.exists():
        return
    for op_dir in TENANTS_ROOT.iterdir():
        if not op_dir.is_dir():
            continue
        for sub in (op_dir / "tasks",):
            if sub.is_dir():
                for f in sorted(sub.glob("*.json")):
                    yield f
        clients = op_dir / "clients"
        if not clients.is_dir():
            continue
        for cl_dir in clients.iterdir():
            if not cl_dir.is_dir():
                continue
            cl_tasks = cl_dir / "tasks"
            if cl_tasks.is_dir():
                for f in sorted(cl_tasks.glob("*.json")):
                    yield f


# ── Alert delivery ────────────────────────────────────────────────────────────

def _deliver_telegram_alert(check_name: str, failures: list[dict], count: int) -> bool:
    """Send an alert to the configured operator target via openclaw message send.

    Returns True if sent or suppressed-by-cooldown, False on hard failure.
    """
    failure_lines = []
    for f in failures:
        reason = f.get("reason", str(f))
        task_id = f.get("task_id", "")
        failure_lines.append(f"  [{task_id}] {reason}" if task_id else f"  {reason}")

    failures_text = "\n".join(failure_lines)
    message = (
        f"🚨 MAA Health Monitor — CRITICAL ALERT\n"
        f"Check: {check_name}\n"
        f"Failures: {count}\n\n"
        f"{failures_text}\n\n"
        f"See: logs/continuous_health_monitor.json"
    )

    config = _load_config()
    alert_target = config.get("alert_target", "telegram:6483160")

    proc = subprocess.run(
        ["openclaw", "message", "send",
         "--channel", "telegram",
         "--target", alert_target,
         "--message", message],
        capture_output=True,
        text=True,
        timeout=20,
    )
    if proc.returncode != 0:
        print(
            f"[CONTINUOUS MONITOR] openclaw message send failed: {proc.stderr}",
            file=sys.stderr,
        )
        return False
    print(f"[CONTINUOUS MONITOR] Operator alert sent for {check_name}", file=sys.stderr)
    return True


def _fire_alert(check_name: str, failures: list[dict]) -> bool:
    """Write signal file and send operator alert with 2h cooldown per check.

    Returns True if an alert was fired (new or cooldown-expired),
    False if suppressed by cooldown.
    """
    in_cooldown, remaining = _is_in_cooldown(check_name)
    if in_cooldown:
        print(
            f"[CONTINUOUS MONITOR — cooldown {remaining}s, alert suppressed for {check_name}]",
            file=sys.stderr,
        )
        return False

    _touch_cooldown(check_name)

    alert = {
        "timestamp": now_iso(),
        "check": check_name,
        "count": len(failures),
        "failures": failures,
        "source": "continuous_health_monitor",
    }
    atomic_write_json(ALERT_FILE, alert)

    print(
        f"[CONTINUOUS MONITOR — CRITICAL ALERT] {check_name} — {len(failures)} failure(s):",
        file=sys.stderr,
    )
    for failure in failures:
        print(f"  → {failure}", file=sys.stderr)

    telegram_ok = _deliver_telegram_alert(check_name, failures, len(failures))
    return True


# ── Health checks ──────────────────────────────────────────────────────────────

def check_metrics_writable() -> dict:
    result = {"name": "metrics_writable", "status": "pass", "details": "", "failures": []}

    if not METRICS_STORE.exists():
        result["status"] = "critical"
        result["details"] = f"Metrics store not found: {METRICS_STORE}"
        result["failures"].append({"type": "not_found", "path": str(METRICS_STORE)})
        return result

    try:
        original = load_json(METRICS_STORE)
        if not isinstance(original, dict):
            result["status"] = "critical"
            result["details"] = "Metrics store is not a valid JSON object"
            result["failures"].append({"type": "invalid_structure", "path": str(METRICS_STORE)})
            return result
    except json.JSONDecodeError as e:
        result["status"] = "critical"
        result["details"] = f"Metrics store is corrupt: {e}"
        result["failures"].append({"type": "json_corrupt", "path": str(METRICS_STORE), "error": str(e)})
        return result
    except OSError as e:
        result["status"] = "critical"
        result["details"] = f"Cannot read metrics store: {e}"
        result["failures"].append({"type": "read_error", "path": str(METRICS_STORE), "error": str(e)})
        return result

    test_label = f"_health_monitor_test_{int(time.time())}"
    # Use 'call' type so the entry lands in the calls bucket which has no required
    # extra fields (unlike 'task' entries which require value_ms in latency checks)
    test_entry = {
        "timestamp": now_iso(),
        "type": "call",
        "label": test_label,
        "session_id": "continuous_health_monitor_test",
        "agent": "_health_monitor",
    }

    mutated = False
    try:
        candidate = json.loads(json.dumps(original))
        for bucket in ["calls", "errors"]:  # plural — matches metrics store keys; task/latency have required extra fields
            if bucket not in candidate:
                continue
            if isinstance(candidate[bucket], list) and len(candidate[bucket]) < 2000:
                candidate[bucket].append(test_entry)
                mutated = True
                break
            if isinstance(candidate[bucket], dict):
                for _, val in candidate[bucket].items():
                    if isinstance(val, list) and len(val) < 2000:
                        val.append(test_entry)
                        mutated = True
                        break
                if mutated:
                    break

        if not mutated:
            result["status"] = "warn"
            result["details"] = "No writable bucket had capacity for test-write"
            result["failures"].append({"type": "no_capacity", "path": str(METRICS_STORE)})
            return result

        atomic_write_json(METRICS_STORE, candidate)
        verified = load_json(METRICS_STORE)

        found = False
        for bucket in ["calls", "errors"]:  # only call/error — task/latency have required extra fields
            if bucket not in verified:
                continue
            if isinstance(verified[bucket], list):
                found = any(isinstance(v, dict) and v.get("label") == test_label for v in verified[bucket])
            elif isinstance(verified[bucket], dict):
                found = any(
                    isinstance(v, list) and any(isinstance(x, dict) and x.get("label") == test_label for x in v)
                    for v in verified[bucket].values()
                )
            if found:
                break

        if not found:
            result["status"] = "critical"
            result["details"] = "Write succeeded but read-back verification failed"
            result["failures"].append({"type": "write_verify_failed", "path": str(METRICS_STORE)})
            return result

        result["details"] = f"Metrics store writable and readable ({METRICS_STORE})"
    except PermissionError:
        result["status"] = "critical"
        result["details"] = f"Permission denied writing to metrics store: {METRICS_STORE}"
        result["failures"].append({"type": "permission_denied", "path": str(METRICS_STORE)})
    except Exception as e:
        result["status"] = "critical"
        result["details"] = f"Error testing metrics store write: {e}"
        result["failures"].append({"type": "write_error", "path": str(METRICS_STORE), "error": str(e)})

    return result


def check_task_states_valid() -> dict:
    result = {"name": "task_states_valid", "status": "pass", "details": "", "failures": []}

    if not TASKS_DIR.exists():
        result["status"] = "critical"
        result["details"] = f"Tasks directory not found: {TASKS_DIR}"
        result["failures"].append({"type": "dir_not_found", "path": str(TASKS_DIR)})
        return result

    corrupt = []
    for sf in _iter_tenant_state_files():
        try:
            task = load_json(sf)
            if not isinstance(task, dict):
                corrupt.append({"file": sf.name, "reason": "not a JSON object"})
            elif "task_id" not in task:
                corrupt.append({"file": sf.name, "reason": "missing task_id field"})
        except json.JSONDecodeError as e:
            corrupt.append({"file": sf.name, "reason": f"JSON decode error: {e}"})
        except OSError as e:
            corrupt.append({"file": sf.name, "reason": f"read error: {e}"})

    if corrupt:
        result["status"] = "critical"
        result["details"] = f"{len(corrupt)} corrupt or invalid task state file(s)"
        result["failures"] = corrupt

    return result


def check_completion_markers() -> dict:
    result = {"name": "completion_markers", "status": "pass", "details": "", "failures": []}
    missing = []

    for sf in _iter_tenant_state_files():
        try:
            task = load_json(sf)
        except Exception:
            continue

        status = task.get("status", "")
        if status in ("completed", "validated"):
            task_id = task.get("task_id", sf.stem)
            tc = task.get("tenant_context")
            if tc:
                # Tenant-scoped: use operator-level logs path for backward compat
                # (parse_tenant_context returns TenantContext; we just need op_id here)
                op_id = tc.get("operator_id", "default")
                cl_id = tc.get("client_id", op_id)
                if op_id == "default":
                    marker_path = LOGS_DIR / f"{task_id}.completion"
                else:
                    # Mirror TenantPathResolver._base_path("logs") logic
                    if tc.get("tenant_tier") == "operator":
                        marker_path = TENANTS_ROOT / op_id / "logs" / f"{task_id}.completion"
                    else:
                        marker_path = TENANTS_ROOT / op_id / "clients" / cl_id / "logs" / f"{task_id}.completion"
            else:
                marker_path = LOGS_DIR / f"{task_id}.completion"
            if not marker_path.exists():
                missing.append(
                    {
                        "task_id": task_id,
                        "status": status,
                        "marker_missing": str(marker_path),
                    }
                )

    if missing:
        result["status"] = "critical"
        result["details"] = f"{len(missing)} completed/validated task(s) without completion marker"
        result["failures"] = missing

    return result


def check_state_version_integrity() -> dict:
    """Detect state_version anomalies without false positives.

    Allowed: task_state state_version >= completion marker state_version.
    Critical (real regression): attempt_history decreases, OR marker > task_state.
    """
    result = {"name": "state_version_integrity", "status": "pass", "details": "", "failures": []}
    regressions = []

    for sf in _iter_tenant_state_files():
        try:
            task = load_json(sf)
        except Exception:
            continue

        task_id = task.get("task_id", sf.stem)
        state_version = task.get("state_version")
        attempt_history = task.get("attempt_history", [])

        history_versions = [
            entry.get("state_version")
            for entry in attempt_history
            if entry.get("state_version") is not None
        ]
        for i in range(1, len(history_versions)):
            if history_versions[i] < history_versions[i - 1]:
                regressions.append(
                    {
                        "task_id": task_id,
                        "reason": (
                            f"attempt_history state_version regression: "
                            f"{history_versions[i - 1]} → {history_versions[i]}"
                        ),
                        "attempt_history_versions": history_versions,
                    }
                )
                break

        if state_version is not None:
            tc = task.get("tenant_context")
            if tc:
                op_id = tc.get("operator_id", "default")
                cl_id = tc.get("client_id", op_id)
                if op_id == "default":
                    marker_path = LOGS_DIR / f"{task_id}.completion"
                else:
                    if tc.get("tenant_tier") == "operator":
                        marker_path = TENANTS_ROOT / op_id / "logs" / f"{task_id}.completion"
                    else:
                        marker_path = TENANTS_ROOT / op_id / "clients" / cl_id / "logs" / f"{task_id}.completion"
            else:
                marker_path = LOGS_DIR / f"{task_id}.completion"
            if marker_path.exists():
                try:
                    marker = load_json(marker_path)
                    marker_sv = marker.get("state_version")
                    if marker_sv is not None and marker_sv > state_version:
                        regressions.append(
                            {
                                "task_id": task_id,
                                "reason": (
                                    f"completion marker state_version ({marker_sv}) > "
                                    f"task state state_version ({state_version})"
                                ),
                            }
                        )
                except Exception as e:
                    regressions.append(
                        {
                            "task_id": task_id,
                            "reason": f"completion marker unreadable during check: {e}",
                        }
                    )

    if regressions:
        result["status"] = "critical"
        result["details"] = f"{len(regressions)} state_version anomaly(ies) detected"
        result["failures"] = regressions

    return result


def check_running_children_accurate() -> dict:
    result = {"name": "running_children_accurate", "status": "pass", "details": "", "failures": []}

    if not RUNNING_CHILDREN_FILE.exists():
        result["status"] = "warn"
        result["details"] = "running_children.json does not exist yet (first run may be normal)"
        return result

    try:
        rc_data = load_json(RUNNING_CHILDREN_FILE)
    except json.JSONDecodeError as e:
        result["status"] = "critical"
        result["details"] = f"running_children.json is corrupt: {e}"
        result["failures"].append({"type": "corrupt_json", "file": str(RUNNING_CHILDREN_FILE), "error": str(e)})
        return result
    except OSError as e:
        result["status"] = "critical"
        result["details"] = f"running_children.json read error: {e}"
        result["failures"].append({"type": "read_error", "file": str(RUNNING_CHILDREN_FILE), "error": str(e)})
        return result

    stale = []
    for task_id in rc_data.get("task_ids", []):
        found_state = False

        state_path = TASKS_DIR / f"{task_id}.json"
        if state_path.exists():
            found_state = True
            try:
                task = load_json(state_path)
            except Exception as e:
                stale.append({"task_id": task_id, "reason": f"cannot read task state: {e}"})
                continue
            if task.get("status") != "running":
                stale.append(
                    {
                        "task_id": task_id,
                        "reason": f"status is '{task.get('status')}', not 'running'",
                        "current_status": task.get("status"),
                        "action": "will_remove_from_running_children",
                    }
                )
                continue
            else:
                continue

        if TENANTS_ROOT.exists():
            for op_dir in TENANTS_ROOT.iterdir():
                if not op_dir.is_dir() or found_state:
                    continue
                op_task = op_dir / "tasks" / f"{task_id}.json"
                if op_task.exists():
                    found_state = True
                    try:
                        task = load_json(op_task)
                    except Exception as e:
                        stale.append({"task_id": task_id, "reason": f"cannot read task state: {e}"})
                        break
                    if task.get("status") != "running":
                        stale.append(
                            {
                                "task_id": task_id,
                                "reason": f"status is '{task.get('status')}', not 'running'",
                                "current_status": task.get("status"),
                                "action": "will_remove_from_running_children",
                            }
                        )
                    break
                clients_dir = op_dir / "clients"
                if not clients_dir.is_dir():
                    continue
                for cl_dir in clients_dir.iterdir():
                    if not cl_dir.is_dir():
                        continue
                    cl_task = cl_dir / "tasks" / f"{task_id}.json"
                    if cl_task.exists():
                        found_state = True
                        try:
                            task = load_json(cl_task)
                        except Exception as e:
                            stale.append({"task_id": task_id, "reason": f"cannot read task state: {e}"})
                            break
                        if task.get("status") != "running":
                            stale.append(
                                {
                                    "task_id": task_id,
                                    "reason": f"status is '{task.get('status')}', not 'running'",
                                    "current_status": task.get("status"),
                                    "action": "will_remove_from_running_children",
                                }
                            )
                        break
                if found_state:
                    break

        if not found_state:
            stale.append(
                {
                    "task_id": task_id,
                    "reason": "in running_children.json but task state file does not exist",
                    "action": "will_remove_from_running_children",
                }
            )

    if stale:
        result["status"] = "warn"
        result["details"] = f"{len(stale)} stale entry(ies) in running_children.json"
        result["failures"] = stale

    return result


def _reconcile_running_children() -> None:
    if not RUNNING_CHILDREN_FILE.exists():
        return

    try:
        rc_data = load_json(RUNNING_CHILDREN_FILE)
    except Exception:
        return

    live = []
    seen_ids: set[str] = set()

    for task_id in rc_data.get("task_ids", []):
        if task_id in seen_ids:
            continue
        # Default path
        state_path = TASKS_DIR / f"{task_id}.json"
        if state_path.exists():
            try:
                task = load_json(state_path)
                if task.get("status") == "running":
                    live.append(task_id)
                    seen_ids.add(task_id)
                    continue
            except Exception:
                pass
        # Tenant-scoped paths (mirror _iter_tenant_state_files structure)
        found = False
        if TENANTS_ROOT.exists():
            for op_dir in TENANTS_ROOT.iterdir():
                if not op_dir.is_dir() or found:
                    continue
                for sub in (op_dir / "tasks",):
                    tp = sub / f"{task_id}.json"
                    if sub.is_dir() and tp.exists():
                        try:
                            task = load_json(tp)
                            if task.get("status") == "running":
                                live.append(task_id)
                                seen_ids.add(task_id)
                                found = True
                        except Exception:
                            pass
                        break
                if found:
                    break

    atomic_write_json(
        RUNNING_CHILDREN_FILE,
        {"updated_at": now_iso(), "task_ids": sorted(live)},
    )


def run_health_checks() -> dict:
    checks = [
        check_metrics_writable(),
        check_task_states_valid(),
        check_completion_markers(),
        check_state_version_integrity(),
        check_running_children_accurate(),
    ]

    statuses = [c["status"] for c in checks]
    overall = "critical" if "critical" in statuses else "warn" if "warn" in statuses else "ok"

    alert_sent = False
    for check in checks:
        if check["status"] == "critical" and check["failures"]:
            fired = _fire_alert(check["name"], check["failures"])
            if fired:
                alert_sent = True

    if checks[4]["status"] in ("warn", "critical"):
        _reconcile_running_children()

    return {
        "at": now_iso(),
        "status": overall,
        "checks": checks,
        "alert_sent": alert_sent,
    }


def main() -> None:
    try:
        report = run_health_checks()
    except Exception as e:
        report = {
            "at": now_iso(),
            "status": "critical",
            "error": f"Monitor itself crashed: {e}",
            "traceback": traceback.format_exc(),
            "checks": [],
            "alert_sent": True,
        }
        print(f"[CONTINUOUS MONITOR — CRASH] {e}\n{traceback.format_exc()}", file=sys.stderr)

    atomic_write_json(OUTPUT_FILE, report)

    status_icon = {"ok": "✅", "warn": "⚠️", "critical": "🚨"}[report["status"]]
    print(f"{status_icon} Continuous Health Monitor — {report['at']} — {report['status'].upper()}")
    for check in report.get("checks", []):
        icon = {"pass": "✅", "warn": "⚠️", "critical": "🚨", "fail": "❌"}.get(check["status"], "❓")
        print(f"  {icon} {check['name']}: {check['status']} — {check['details']}")

    sys.exit(1 if report["status"] == "critical" else 0)


if __name__ == "__main__":
    main()