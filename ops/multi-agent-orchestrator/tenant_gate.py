#!/usr/bin/env python3
"""
TenantGate — Entry point interceptor for task submission.
- Validates tenant context on every task
- Enforces per-operator and per-client rate limits
- Accepts or rejects before task reaches the orchestrator
- Backward-compatible for the default operator
"""
import json, os, time
from pathlib import Path
from datetime import datetime, UTC
from tenant_context import TenantContext, DEFAULT_TENANT, parse_tenant_context, require_tenant_context
from tenant_paths import TenantPathResolver, TENANTS_ROOT

CONTINUOUS_ALERT_FILE = Path("/root/.openclaw/workspace/ops/multi-agent-orchestrator/logs/continuous_health_monitor_alerts.json")
SPEND_SPIKE_COOLDOWN_S = 2 * 3600

TASKS_DIR = "/root/.openclaw/workspace/ops/multi-agent-orchestrator/tasks"

RATE_LIMIT_WINDOW_S = 3600  # 1-hour rolling window


class RateLimitExceeded(Exception):
    def __init__(self, operator_id: str, client_id: str, limit: int, window_s: int):
        self.operator_id = operator_id
        self.client_id = client_id
        self.limit = limit
        self.window_s = window_s
        super().__init__(f"RATE_LIMIT_EXCEEDED: {operator_id}/{client_id} — {limit} tasks per {window_s}s")


class QuotaExceeded(Exception):
    """Raised when a tenant exceeds a configurable resource quota."""
    def __init__(self, operator_id: str, client_id: str, quota_type: str,
                 limit_value: float, current_value: float,
                 exceed_action: str = "reject"):
        self.operator_id = operator_id
        self.client_id = client_id
        self.quota_type = quota_type
        self.limit_value = limit_value
        self.current_value = current_value
        self.exceed_action = exceed_action
        super().__init__(
            f"QUOTA_EXCEEDED: {operator_id}/{client_id} — {quota_type} "
            f"({current_value:.1f}/{limit_value}) [action={exceed_action}]"
        )


class SpendBudgetExhausted(Exception):
    """Raised when a tenant exceeds daily or monthly spend cap with a defer action."""
    def __init__(self, operator_id: str, client_id: str, quota_type: str,
                 limit_value: float, current_value: float,
                 exceed_action: str = "reject"):
        self.operator_id = operator_id
        self.client_id = client_id
        self.quota_type = quota_type
        self.limit_value = limit_value
        self.current_value = current_value
        self.exceed_action = exceed_action  # "reject" | "queue" | "require_approval"
        super().__init__(
            f"SPEND_EXHAUSTED: {operator_id}/{client_id} — {quota_type} "
            f"({current_value:.2f}/{limit_value:.2f}) [action={exceed_action}]"
        )


# ── Cost Estimation ────────────────────────────────────────────────────────

BASE_COST_PER_MINUTE = {
    "market-brief": 0.05,
    "research": 0.05,
    "email-draft": 0.03,
    "growth-report": 0.05,
    "validation": 0.03,
    "coder": 0.06,
    "executor": 0.05,
}
DEFAULT_COST_PER_MINUTE = 0.04


def estimate_task_cost(task_type: str, runtime_seconds: float | None = None,
                      cost_per_minute_override: float | None = None) -> float:
    """
    Estimate the cost of a task based on type and runtime.

    If runtime_seconds is provided, use actual elapsed time.
    Otherwise fall back to base_runtime_min for the task type.
    cost_per_minute_override uses operator-level override if provided.

    Returns estimated cost in USD.
    """
    cpm = cost_per_minute_override or BASE_COST_PER_MINUTE.get(task_type, DEFAULT_COST_PER_MINUTE)
    if runtime_seconds is not None:
        runtime_min = runtime_seconds / 60.0
    else:
        runtime_min = BASE_RUNTIME_MIN.get(task_type, DEFAULT_RUNTIME_MIN)
    return round(runtime_min * cpm, 4)


# ── Spend accounting ─────────────────────────────────────────────────────────

def _load_quota_data(operator_id: str, client_id: str) -> tuple[Path, dict]:
    store = _quota_store_path(operator_id, client_id)
    quota_data = {}
    if store.exists():
        try:
            with open(store) as f:
                quota_data = json.load(f)
        except Exception:
            quota_data = {}
    return store, quota_data


def _save_quota_data(store: Path, quota_data: dict) -> None:
    store.parent.mkdir(parents=True, exist_ok=True)
    with open(store, "w") as f:
        json.dump(quota_data, f)


def _apply_quota_rollovers(quota_data: dict, now: float | None = None) -> dict:
    now = now or time.time()
    current_month = int(datetime.fromtimestamp(now).strftime("%Y%m"))
    last_day_reset = quota_data.get("_last_day_reset", quota_data.get("_last_reset", 0))
    if now - last_day_reset >= 86400:
        # reset only daily counters, preserve monthly state and static fields
        quota_data["_tasks_today"] = 0
        quota_data["_runtime_minutes_today"] = 0.0
        quota_data["_spend_today"] = 0.0
        for key in list(quota_data.keys()):
            if key.startswith("_task_class_"):
                quota_data[key] = 0
        quota_data["_last_day_reset"] = now
        quota_data["_last_reset"] = now
    else:
        quota_data.setdefault("_last_day_reset", last_day_reset or now)
        quota_data.setdefault("_last_reset", last_day_reset or now)

    stored_month = quota_data.get("_month_key", current_month)
    if int(stored_month) < current_month:
        quota_data["_spend_this_month"] = 0.0
        quota_data["_last_month_reset"] = now
        quota_data["_month_key"] = current_month
    else:
        quota_data.setdefault("_month_key", current_month)
        quota_data.setdefault("_last_month_reset", now)
    return quota_data


def record_spend(operator_id: str, client_id: str, task_type: str,
                 cost_usd: float) -> None:
    """Record actual task cost against daily and monthly spend buckets."""
    if operator_id == "default":
        return
    store, quota_data = _load_quota_data(operator_id, client_id)
    quota_data = _apply_quota_rollovers(quota_data)
    quota_data["_spend_today"] = round(quota_data.get("_spend_today", 0.0) + cost_usd, 4)
    quota_data["_spend_this_month"] = round(quota_data.get("_spend_this_month", 0.0) + cost_usd, 4)
    try:
        _save_quota_data(store, quota_data)
        print(f"[TenantGate] Spend recorded: {operator_id}/{client_id} "
              f"+${cost_usd:.4f} ({task_type}) → today=${quota_data['_spend_today']:.4f} "
              f"month=${quota_data['_spend_this_month']:.4f}")
    except OSError as e:
        print(f"[TenantGate] WARNING: could not write spend to quota store ({e})")


def _check_spend_quotas(tenant: TenantContext, task_type: str,
                        estimated_cost: float) -> tuple[bool, str, str, float, float]:
    """Check daily and monthly spend caps for a tenant."""
    op_cfg = load_operator_config(tenant.operator_id)
    cl_cfg = load_client_config(tenant.operator_id, tenant.client_id)
    exceed_action = cl_cfg.get("exceed_action", op_cfg.get("exceed_action", "reject"))
    _, quota_data = _load_quota_data(tenant.operator_id, tenant.client_id)
    quota_data = _apply_quota_rollovers(quota_data)

    daily_cap = float(cl_cfg.get("max_daily_spend", op_cfg.get("max_daily_spend", 50.0)))
    spend_today = float(quota_data.get("_spend_today", 0.0))
    if spend_today + estimated_cost > daily_cap:
        return True, exceed_action, "max_daily_spend", daily_cap, spend_today

    monthly_cap = float(cl_cfg.get("max_monthly_spend", op_cfg.get("max_monthly_spend", 500.0)))
    spend_this_month = float(quota_data.get("_spend_this_month", 0.0))
    if spend_this_month + estimated_cost > monthly_cap:
        return True, exceed_action, "max_monthly_spend", monthly_cap, spend_this_month

    return False, "proceed", "", 0.0, 0.0


def _check_spend_spike_suppression(tenant: TenantContext, task_type: str) -> None:
    """Block expensive tasks for tenants under active spend-spike alert cooldown."""
    expensive_types = {"market-brief", "research", "growth-report", "coder", "executor"}
    if task_type not in expensive_types or not CONTINUOUS_ALERT_FILE.exists():
        return
    try:
        with open(CONTINUOUS_ALERT_FILE) as f:
            alert = json.load(f)
    except Exception:
        return
    if alert.get("check") != "spend_spike":
        return
    try:
        ts = datetime.fromisoformat(str(alert.get("timestamp", "")).replace("Z", "+00:00")).timestamp()
    except Exception:
        return
    if time.time() - ts > SPEND_SPIKE_COOLDOWN_S:
        return
    tenant_key = f"{tenant.operator_id}:{tenant.client_id}"
    for failure in alert.get("failures", []):
        if str(failure.get("tenant", "")) == tenant_key:
            current = float(failure.get("cost_1h", 0.0))
            limit = float(failure.get("daily_avg", 0.0) * 2 or current)
            raise QuotaExceeded(
                tenant.operator_id,
                tenant.client_id,
                "spend_spike_cooldown",
                limit,
                current,
            )


def _load_config_file(path: Path) -> dict | None:
    """Load a JSON config file, return None if missing or invalid.
    
    Logs a warning on JSON decode errors. Swallows file-not-found silently.
    """
    if not path.exists():
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"[TenantGate] WARNING: {path} contains invalid JSON ({e}) — ignoring, using defaults")
        return None
    except OSError as e:
        print(f"[TenantGate] WARNING: could not read {path} ({e}) — ignoring, using defaults")
        return None


def _default_operator_config(operator_id: str) -> dict:
    return {
        "operator_id": operator_id,
        "max_concurrent_tasks": 8,
        "max_tasks_per_hour": 200,
        "max_tasks_per_day": 500,
        "max_concurrent_tasks": 8,
        "max_expensive_task_class_per_day": {},
        "max_runtime_minutes_per_day": 480,
        "max_daily_spend": 50.0,
        "max_monthly_spend": 5000.0,
        "exceed_action": "reject",  # "reject" | "queue" | "require_approval"
        "cost_per_minute_override": None,
        "rate_limit_window_seconds": RATE_LIMIT_WINDOW_S,
        "clients": {},
    }


def _default_client_config(client_id: str) -> dict:
    return {
        "client_id": client_id,
        "max_concurrent_tasks": 2,
        "max_tasks_per_hour": 50,
        "max_tasks_per_day": 100,
        "max_concurrent_tasks": 2,
        "max_expensive_task_class_per_day": {},
        "max_runtime_minutes_per_day": 480,
        "max_daily_spend": 50.0,
        "max_monthly_spend": 500.0,
        "exceed_action": "reject",  # "reject" | "queue" | "require_approval"
        "cost_per_minute_override": None,
        "rate_limit_window_seconds": RATE_LIMIT_WINDOW_S,
    }


def load_operator_config(operator_id: str) -> dict:
    """Load operator config, merged with defaults for missing fields.
    
    GAP 3 FIX: Old config files may be missing new fields (e.g. max_concurrent_tasks
    added after initial deployment). Merge with defaults so all callers get safe values,
    never None for a field that existed before the schema was extended.
    """
    defaults = _default_operator_config(operator_id)
    if operator_id == "default":
        return defaults
    config_path = TENANTS_ROOT / operator_id / "config" / "operator.json"
    stored = _load_config_file(config_path)
    if stored is None:
        return defaults
    # Merge: fill in any missing fields from defaults
    merged = {**defaults, **stored}
    # Preserve nested 'clients' dict even if old config had it as None
    if stored.get("clients") is not None:
        merged["clients"] = stored["clients"]
    return merged


def load_client_config(operator_id: str, client_id: str) -> dict:
    """Load client config, merged with defaults for missing fields.
    
    GAP 3 FIX: Same as load_operator_config — older config files may be missing
    fields added in later schema versions.
    """
    defaults = _default_client_config(client_id)
    if operator_id == "default":
        return defaults
    config_path = TENANTS_ROOT / operator_id / "clients" / client_id / "config" / "client.json"
    stored = _load_config_file(config_path)
    if stored is None:
        return defaults
    merged = {**defaults, **stored}
    return merged


def save_operator_config(operator_id: str, config: dict) -> bool:
    """Write operator config file. Returns True on success."""
    if operator_id == "default":
        return False  # default tenant config is not writable
    config_path = TENANTS_ROOT / operator_id / "config" / "operator.json"
    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)
        return True
    except OSError as e:
        print(f"[TenantGate] ERROR: could not write operator config ({e})")
        return False


def save_client_config(operator_id: str, client_id: str, config: dict) -> bool:
    """Write client config file. Returns True on success."""
    if operator_id == "default":
        return False
    config_path = TENANTS_ROOT / operator_id / "clients" / client_id / "config" / "client.json"
    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)
        return True
    except OSError as e:
        print(f"[TenantGate] ERROR: could not write client config ({e})")
        return False


def _rate_limit_store_path(operator_id: str, client_id: str) -> Path:
    if operator_id == "default":
        return Path(TASKS_DIR) / f".rate_limit_{client_id}.json"
    return TENANTS_ROOT / operator_id / "clients" / client_id / ".rate_limit.json"


def _check_rate_limit(operator_id: str, client_id: str, limit: int, window_s: int) -> None:
    """Raise RateLimitExceeded if limit is exceeded, else record this event."""
    store = _rate_limit_store_path(operator_id, client_id)
    events = []
    now = time.time()
    cutoff = now - window_s

    if store.exists():
        try:
            with open(store) as f:
                events = json.load(f)
        except Exception:
            events = []

    # Filter to window
    events = [e for e in events if e >= cutoff]

    if len(events) >= limit:
        raise RateLimitExceeded(operator_id, client_id, limit, window_s)

    # Record this event
    events.append(now)
    store.parent.mkdir(parents=True, exist_ok=True)
    with open(store, "w") as f:
        json.dump(events, f)


# ── Runtime-minute accounting ───────────────────────────────────────────────

BASE_RUNTIME_MIN = {
    "market-brief": 8,
    "research": 10,
    "email-draft": 3,
    "growth-report": 12,
    "validation": 5,
    "coder": 15,
    "executor": 10,
}
DEFAULT_RUNTIME_MIN = 5


def record_runtime_minutes(operator_id: str, client_id: str, task_type: str,
                           actual_runtime_seconds: float) -> None:
    """Record actual task runtime against the daily runtime quota."""
    if operator_id == "default":
        return
    store, quota_data = _load_quota_data(operator_id, client_id)
    quota_data = _apply_quota_rollovers(quota_data)
    runtime_min = round(actual_runtime_seconds / 60.0, 2)
    quota_data["_runtime_minutes_today"] = round(quota_data.get("_runtime_minutes_today", 0.0) + runtime_min, 2)
    try:
        _save_quota_data(store, quota_data)
        print(f"[TenantGate] Runtime accounting: {operator_id}/{client_id} "
              f"+{runtime_min} min ({task_type}) → total today: "
              f"{quota_data['_runtime_minutes_today']:.1f} min")
    except OSError as e:
        print(f"[TenantGate] WARNING: could not write runtime to quota store ({e})")


def validate_tenant_context(raw_context: dict | None) -> TenantContext:
    """
    Validate and return a TenantContext.
    For backward compat: raw_context=None is accepted for the default operator
    and returns DEFAULT_TENANT. Only raises for non-default operators.
    """
    return parse_tenant_context(raw_context)


def check_rate_limits(tenant: TenantContext) -> None:
    """Check per-client and per-operator rate limits. Raises RateLimitExceeded."""
    client_cfg = load_client_config(tenant.operator_id, tenant.client_id)
    _check_rate_limit(
        tenant.operator_id, tenant.client_id,
        client_cfg.get("max_tasks_per_hour", 50),
        client_cfg.get("rate_limit_window_seconds", RATE_LIMIT_WINDOW_S),
    )
    op_cfg = load_operator_config(tenant.operator_id)
    _check_rate_limit(
        tenant.operator_id, "operator",
        op_cfg.get("max_tasks_per_hour", 200),
        op_cfg.get("rate_limit_window_seconds", RATE_LIMIT_WINDOW_S),
    )


def _quota_store_path(operator_id: str, client_id: str) -> Path:
    """Path for daily quota counters."""
    if operator_id == "default":
        return Path(TASKS_DIR) / f".quota_{client_id}.json"
    return TENANTS_ROOT / operator_id / "clients" / client_id / ".quota.json"



def _check_resource_quotas(tenant: TenantContext, task_type: str) -> None:
    """Check configurable resource quotas for a tenant.


    Enforces:
      - max_tasks_per_day (hard task count cap)
      - max_concurrent_tasks (parallelism limit)
      - max_expensive_task_class_per_day (per task type daily cap)
      - max_runtime_minutes_per_day (daily runtime cap)


    Raises QuotaExceeded on any breach.
    """
    from pathlib import Path as P

    op_cfg = load_operator_config(tenant.operator_id)
    cl_cfg = load_client_config(tenant.operator_id, tenant.client_id)


    store = _quota_store_path(tenant.operator_id, tenant.client_id)
    quota_data = {}
    now = time.time()
    day_start = now - 86400

    if store.exists():
        try:
            with open(store) as f:
                quota_data = json.load(f)
        except Exception:
            quota_data = {}


    # Reset daily counters if day has rolled over
    last_reset = quota_data.get("_last_reset", 0)
    if now - last_reset >= 86400:
        quota_data = {"_last_reset": now}

    # ── max_concurrent_tasks (global parallelism) ─────────────────────────────
    concurrent_limit = cl_cfg.get("max_concurrent_tasks", 2)
    # Active tasks for this tenant: count running children tracked in metrics
    # We approximate via the running_children.json if available
    # A more precise count would come from the orchestrator state
    # For quota enforcement at gate time: check if there's a running children file
    running_path = P("/root/.openclaw/workspace/ops/multi-agent-orchestrator/logs/running_children.json")
    active_count = 0
    if running_path.exists():
        try:
            with open(running_path) as f:
                rc = json.load(f)
            active_count = len(rc.get("task_ids", []))
        except Exception:
            pass
    if active_count >= concurrent_limit:
        raise QuotaExceeded(
            tenant.operator_id, tenant.client_id,
            "max_concurrent_tasks",
            concurrent_limit, active_count,
        )

    # ── max_tasks_per_day ─────────────────────────────────────────────────────
    daily_task_limit = cl_cfg.get("max_tasks_per_day", 100)
    daily_tasks = quota_data.get("_tasks_today", 0)
    if daily_tasks >= daily_task_limit:
        raise QuotaExceeded(
            tenant.operator_id, tenant.client_id,
            "max_tasks_per_day",
            daily_task_limit, daily_tasks,
        )

    # ── max_expensive_task_class_per_day ─────────────────────────────────────
    expensive_map = cl_cfg.get("max_expensive_task_class_per_day", {})
    if expensive_map:
        task_count_today = quota_data.get(f"_task_class_{task_type}", 0)
        class_limit = expensive_map.get(task_type)
        if class_limit is not None and task_count_today >= class_limit:
            raise QuotaExceeded(
                tenant.operator_id, tenant.client_id,
                f"max_expensive_task_class_per_day:{task_type}",
                float(class_limit), float(task_count_today),
            )

    # ── max_runtime_minutes_per_day ───────────────────────────────────────────
    runtime_limit_min = cl_cfg.get("max_runtime_minutes_per_day", 480)
    runtime_used_min = quota_data.get("_runtime_minutes_today", 0)
    if runtime_used_min >= runtime_limit_min:
        raise QuotaExceeded(
            tenant.operator_id, tenant.client_id,
            "max_runtime_minutes_per_day",
            runtime_limit_min, runtime_used_min,
        )

    # ── Spend caps ────────────────────────────────────────────────────────
    cost_per_min_override = cl_cfg.get("cost_per_minute_override") or op_cfg.get("cost_per_minute_override")
    estimated_cost = estimate_task_cost(task_type, None, cost_per_min_override)
    blocked, action, limit_name, limit_value, current_value = _check_spend_quotas(tenant, task_type, estimated_cost)
    if blocked:
        raise SpendBudgetExhausted(
            tenant.operator_id, tenant.client_id,
            limit_name,
            limit_value, current_value,
            exceed_action=action,
        )

    # Record this task submission (increment counters)
    quota_data["_tasks_today"] = daily_tasks + 1
    quota_data[f"_task_class_{task_type}"] = quota_data.get(f"_task_class_{task_type}", 0) + 1
    quota_data["_last_reset"] = quota_data.get("_last_reset", now)
    try:
        store.parent.mkdir(parents=True, exist_ok=True)
        with open(store, "w") as f:
            json.dump(quota_data, f)
    except OSError as e:
        print(f"[TenantGate] WARNING: could not write quota store ({e}) — allowing task")


def submit_task_gate(task_prompt: str, task_type: str,
                     raw_context: dict | None = None,
                     task_id: str | None = None) -> TenantContext:
    """
    Entry gate for task submission.
    
    1. Validates tenant context
    2. Checks rate limits
    3. Checks resource quotas
    4. Returns TenantContext for the task
    
    Raises:
        ValueError — if tenant context is missing/invalid
        RateLimitExceeded — if rate limit is hit
        QuotaExceeded — if a resource quota is exceeded (hard block: reject)
        SpendBudgetExhausted — if daily/monthly spend cap exceeded with
            exceed_action=reject|queue|require_approval
    
    Returns TenantContext to pass to the orchestrator.
    """
    # Step 1: parse and validate context
    tenant = validate_tenant_context(raw_context)

    # Step 2: check rate limits (skip for default tenant in backward-compat mode)
    if not tenant.is_default():
        check_rate_limits(tenant)

    # Step 3: check resource quotas
    if not tenant.is_default():
        try:
            _check_resource_quotas(tenant, task_type)
            _check_spend_spike_suppression(tenant, task_type)
        except SpendBudgetExhausted as sbe:
            if sbe.exceed_action == "require_approval":
                # Surface to the operator for explicit approval before proceeding
                print(f"[TenantGate] SPEND CAP NEEDS APPROVAL: {tenant.operator_id}/{tenant.client_id} "
                      f"— task_type={task_type}, action={sbe.exceed_action}")
                # Re-raise so the orchestrator can pause and request approval
                raise
            elif sbe.exceed_action == "queue":
                # Handled upstream — re-raise with queue signal
                raise
            else:
                # reject
                raise

    # Step 4: ensure tenant directories exist
    resolver = TenantPathResolver(tenant)
    resolver.ensure_dirs()

    return tenant


def task_accepted(tenant: TenantContext, task_id: str, task_type: str) -> None:
    """Log task acceptance to audit trail."""
    audit_entry = {
        "timestamp": datetime.now(UTC).isoformat(),
        "action": "task.accepted",
        "task_id": task_id,
        "task_type": task_type,
        "operator_id": tenant.operator_id,
        "client_id": tenant.client_id,
        "result": "accepted",
    }
    audit_path = TenantPathResolver(tenant).resolve("audit")
    audit_path.mkdir(parents=True, exist_ok=True)
    month = datetime.now(UTC).strftime("%Y-%m")
    audit_file = audit_path / f"{month}.jsonl"
    with open(audit_file, "a") as f:
        f.write(json.dumps(audit_entry) + "\n")


def task_rejected(tenant: TenantContext, task_id: str | None,
                  reason: str, task_type: str | None = None) -> dict:
    """
    Log task rejection and return error response.
    Used both for UNAUTHORIZED (missing context) and RATE_LIMIT_EXCEEDED.
    """
    audit_entry = {
        "timestamp": datetime.now(UTC).isoformat(),
        "action": "task.rejected",
        "task_id": task_id or "(none)",
        "task_type": task_type or "(none)",
        "operator_id": tenant.operator_id if tenant else "(none)",
        "client_id": tenant.client_id if tenant else "(none)",
        "result": "rejected",
        "reason": reason,
    }
    # Try to write audit even for rejected tasks
    try:
        if tenant and not tenant.is_default():
            audit_path = TenantPathResolver(tenant).resolve("audit")
            audit_path.mkdir(parents=True, exist_ok=True)
            month = datetime.now(UTC).strftime("%Y-%m")
            audit_file = audit_path / f"{month}.jsonl"
            with open(audit_file, "a") as f:
                f.write(json.dumps(audit_entry) + "\n")
    except Exception:
        pass

    return {
        "status": "error",
        "error": reason,
        "task_id": task_id,
    }