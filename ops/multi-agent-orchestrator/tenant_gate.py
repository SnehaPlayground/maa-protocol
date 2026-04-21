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

TASKS_DIR = "/root/.openclaw/workspace/ops/multi-agent-orchestrator/tasks"

RATE_LIMIT_WINDOW_S = 3600  # 1-hour rolling window


class RateLimitExceeded(Exception):
    def __init__(self, operator_id: str, client_id: str, limit: int, window_s: int):
        self.operator_id = operator_id
        self.client_id = client_id
        self.limit = limit
        self.window_s = window_s
        super().__init__(f"RATE_LIMIT_EXCEEDED: {operator_id}/{client_id} — {limit} tasks per {window_s}s")


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
        "rate_limit_window_seconds": RATE_LIMIT_WINDOW_S,
        "clients": {},
    }


def _default_client_config(client_id: str) -> dict:
    return {
        "client_id": client_id,
        "max_concurrent_tasks": 2,
        "max_tasks_per_hour": 50,
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


def submit_task_gate(task_prompt: str, task_type: str,
                     raw_context: dict | None = None,
                     task_id: str | None = None) -> TenantContext:
    """
    Entry gate for task submission.
    
    1. Validates tenant context
    2. Checks rate limits
    3. Returns TenantContext for the task
    
    Raises:
        ValueError — if tenant context is missing/invalid
        RateLimitExceeded — if rate limit is hit
    
    Returns TenantContext to pass to the orchestrator.
    """
    # Step 1: parse and validate context
    tenant = validate_tenant_context(raw_context)

    # Step 2: check rate limits (skip for default tenant in backward-compat mode)
    if not tenant.is_default():
        check_rate_limits(tenant)

    # Step 3: ensure tenant directories exist
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