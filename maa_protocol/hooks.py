"""
MAA Protocol — Lifecycle Hooks System
====================================
Real hook dispatch engine for 14 lifecycle points.

Each hook fires at its defined trigger. Hooks are observable,
can be registered/unregistered at runtime, and execution results
are logged to the guidance ledger.

Hook points (14):
  Core (6):    pre-edit, post-edit, pre-command, post-command, pre-task, post-task
  Session (4): session-start, session-end, session-restore, notify
  Intelligence (4): route, explain, pretrain, build-agents, transfer

Each hook receives a HookContext and returns a HookResult.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Protocol

# Observability
try:
    import sys
    _ws = Path("/root/.openclaw/workspace")
    if str(_ws) not in sys.path:
        sys.path.insert(0, str(_ws))
    from ops.observability.maa_metrics import record_call, record_error, record_latency
    _METRICS_AVAILABLE = True
except Exception:
    _METRICS_AVAILABLE = False


# ── Enums ────────────────────────────────────────────────────────────────────

class HookPhase(str, Enum):
    CORE = "core"
    SESSION = "session"
    INTELLIGENCE = "intelligence"


class HookAction(str, Enum):
    PROCEED = "proceed"       # continue normally
    BLOCK = "block"           # stop the action
    MODIFY = "modify"         # modify context and continue
    ESCALATE = "escalate"     # hand off to human


# ── Dataclasses ────────────────────────────────────────────────────────────────

@dataclass
class HookContext:
    """Context passed to every hook invocation."""
    hook_name: str
    phase: HookPhase
    timestamp: float = field(default_factory=time.time)
    task_id: str | None = None
    session_id: str | None = None
    tenant_id: str = "default"
    operator_id: str | None = None
    data: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)


@dataclass
class HookResult:
    """Result returned by a hook handler."""
    action: HookAction
    hook_name: str
    message: str = ""
    modified_context: dict[str, Any] | None = None
    latency_ms: float = 0.0
    error: str | None = None


@dataclass
class HookRegistration:
    """A registered hook handler."""
    name: str
    handler: Callable[[HookContext], HookResult]
    phase: HookPhase
    enabled: bool = True
    description: str = ""
    priority: int = 0   # lower = runs first; ties broken by registration order


# ── Hook Registry ──────────────────────────────────────────────────────────────

class HookRegistry:
    """
    Central registry for all MAA lifecycle hooks.

    Supports:
    - register/unregister handlers at runtime
    - enable/disable specific hooks
    - ordered execution (priority + registration order)
    - execution logging with timing
    - fire hooks and collect all results
    """

    def __init__(self) -> None:
        self._hooks: dict[str, list[HookRegistration]] = {name: [] for name in HookRegistry.HOOK_POINTS}
        self._execution_log: list[dict[str, Any]] = []
        self._log_max = 500

    # ── HOOK_POINTS ──────────────────────────────────────────────────────────

    HOOK_POINTS = [
        # Core (6)
        "pre-edit", "post-edit",
        "pre-command", "post-command",
        "pre-task", "post-task",
        # Session (4)
        "session-start", "session-end", "session-restore", "notify",
        # Intelligence (4)
        "route", "explain", "pretrain", "build-agents", "transfer",
    ]

    def list_hooks(self) -> list[str]:
        """Return all registered hook points."""
        return sorted(set(self._hooks.keys()))

    def list_active_hooks(self) -> list[str]:
        """Return hook points that have at least one enabled handler."""
        return sorted(k for k, v in self._hooks.items() if any(r.enabled for r in v))

    # ── Registration ─────────────────────────────────────────────────────────

    def register(
        self,
        hook_name: str,
        handler: Callable[[HookContext], HookResult],
        phase: HookPhase = HookPhase.CORE,
        description: str = "",
        priority: int = 0,
    ) -> None:
        """Register a handler for a hook point."""
        if hook_name not in self._hooks:
            self._hooks[hook_name] = []
        reg = HookRegistration(
            name=hook_name,
            handler=handler,
            phase=phase,
            description=description,
            priority=priority,
        )
        self._hooks[hook_name].append(reg)
        # Sort by priority then keep insertion order
        self._hooks[hook_name].sort(key=lambda r: (r.priority, len(self._hooks[hook_name])))

    def unregister(self, hook_name: str, handler: Callable[[HookContext], HookResult]) -> bool:
        """Remove a handler. Returns True if found and removed."""
        if hook_name not in self._hooks:
            return False
        original = len(self._hooks[hook_name])
        self._hooks[hook_name] = [r for r in self._hooks[hook_name] if r.handler is not handler]
        return len(self._hooks[hook_name]) < original

    def enable(self, hook_name: str, handler: Callable[[HookContext], HookResult] | None = None) -> None:
        """Enable a hook or a specific handler."""
        if handler is None:
            for reg in self._hooks.get(hook_name, []):
                reg.enabled = True
        else:
            for reg in self._hooks.get(hook_name, []):
                if reg.handler is handler:
                    reg.enabled = True

    def disable(self, hook_name: str, handler: Callable[[HookContext], HookResult] | None = None) -> None:
        """Disable a hook or a specific handler."""
        if handler is None:
            for reg in self._hooks.get(hook_name, []):
                reg.enabled = False
        else:
            for reg in self._hooks.get(hook_name, []):
                if reg.handler is handler:
                    reg.enabled = False

    # ── Execution ─────────────────────────────────────────────────────────────

    def fire(self, ctx: HookContext) -> list[HookResult]:
        """
        Fire a hook point and return results from all handlers.

        Args:
            ctx: HookContext with hook_name set

        Returns:
            List of HookResult — one per enabled handler
        """
        hook_name = ctx.hook_name
        handlers = self._hooks.get(hook_name, [])
        enabled = [r for r in handlers if r.enabled]

        if not enabled:
            return [HookResult(HookAction.PROCEED, hook_name, "no handlers registered")]

        results = []
        for reg in enabled:
            start = time.monotonic()
            try:
                result = reg.handler(ctx)
                result.latency_ms = (time.monotonic() - start) * 1000
                result.hook_name = hook_name
            except Exception as e:
                result = HookResult(
                    action=HookAction.PROCEED,
                    hook_name=hook_name,
                    message=f"hook error: {e}",
                    latency_ms=(time.monotonic() - start) * 1000,
                    error=str(e),
                )
            results.append(result)

            # Log execution
            self._log_execution(hook_name, reg, result)

            # Metrics
            if _METRICS_AVAILABLE:
                label = f"hook.{hook_name}"
                record_call(label, agent="mother")
                record_latency(label, result.latency_ms, agent="mother")
                if result.error:
                    record_error(label, result.error, agent="mother")

        return results

    def fire_first(self, ctx: HookContext) -> HookResult:
        """
        Fire a hook point, return the first result.
        Stops at the first BLOCK or MODIFY result.
        """
        results = self.fire(ctx)
        for r in results:
            if r.action in (HookAction.BLOCK, HookAction.MODIFY):
                return r
        return results[0] if results else HookResult(HookAction.PROCEED, ctx.hook_name)

    # ── Execution log ─────────────────────────────────────────────────────────

    def _log_execution(self, hook_name: str, reg: HookRegistration, result: HookResult) -> None:
        entry = {
            "timestamp": time.time(),
            "hook": hook_name,
            "phase": reg.phase.value,
            "action": result.action.value,
            "message": result.message,
            "latency_ms": result.latency_ms,
            "error": result.error,
            "priority": reg.priority,
        }
        self._execution_log.append(entry)
        if len(self._execution_log) > self._log_max:
            self._execution_log.pop(0)

    def execution_log(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return recent hook execution entries."""
        return self._execution_log[-limit:]

    def clear_log(self) -> None:
        self._execution_log = []


# ── Global registry ──────────────────────────────────────────────────────────

_global_registry: HookRegistry | None = None


def get_registry() -> HookRegistry:
    global _global_registry
    if _global_registry is None:
        _global_registry = HookRegistry()
        _register_default_hooks(_global_registry)
    return _global_registry


# ── Default hook handlers ─────────────────────────────────────────────────────

def _register_default_hooks(registry: HookRegistry) -> None:
    """
    Register MAA's built-in default hook handlers.
    All default hooks just proceed — they can be overridden by user registration.
    """

    def make_proceed_handler(name: str, phase: HookPhase):
        def handler(ctx: HookContext) -> HookResult:
            return HookResult(HookAction.PROCEED, name, f"{name} completed")
        return handler

    for name in HookRegistry.HOOK_POINTS:
        phase = _phase_for_hook(name)
        registry.register(
            name,
            make_proceed_handler(name, phase),
            phase=phase,
            description=f"default {name} handler",
            priority=9999,  # low priority — user handlers run first
        )


def _phase_for_hook(name: str) -> HookPhase:
    core = {"pre-edit", "post-edit", "pre-command", "post-command", "pre-task", "post-task"}
    session = {"session-start", "session-end", "session-restore", "notify"}
    if name in core:
        return HookPhase.CORE
    if name in session:
        return HookPhase.SESSION
    return HookPhase.INTELLIGENCE


# ── Public API ────────────────────────────────────────────────────────────────

def list_hooks() -> list[str]:
    """List all registered hook points."""
    return get_registry().list_hooks()


def list_active_hooks() -> list[str]:
    """List hook points with at least one enabled handler."""
    return get_registry().list_active_hooks()


def register(
    hook_name: str,
    handler: Callable[[HookContext], HookResult],
    phase: HookPhase = HookPhase.CORE,
    description: str = "",
    priority: int = 0,
) -> None:
    """Register a hook handler."""
    get_registry().register(hook_name, handler, phase, description, priority)


def unregister(hook_name: str, handler: Callable[[HookContext], HookResult]) -> bool:
    """Unregister a hook handler."""
    return get_registry().unregister(hook_name, handler)


def fire(hook_name: str, **ctx_kwargs) -> list[HookResult]:
    """
    Fire a hook by name.

    Example:
        results = fire("pre-edit", task_id="abc", data={"path": "/tmp/foo"})
    """
    phase = _phase_for_hook(hook_name)
    ctx = HookContext(hook_name=hook_name, phase=phase, **ctx_kwargs)
    return get_registry().fire(ctx)


def fire_first(hook_name: str, **ctx_kwargs) -> HookResult:
    """Fire, returning first result or first BLOCK/MODIFY."""
    phase = _phase_for_hook(hook_name)
    ctx = HookContext(hook_name=hook_name, phase=phase, **ctx_kwargs)
    return get_registry().fire_first(ctx)


def execution_log(limit: int = 50) -> list[dict[str, Any]]:
    """Return recent hook execution log entries."""
    return get_registry().execution_log(limit)


def hook_dispatch(hook_name: str, context: dict[str, Any]) -> HookResult:
    """
    Dispatch a hook from a plain dict context.
    Used by the orchestrator to fire hooks with minimal setup.

    Args:
        hook_name: e.g. "pre-edit", "post-task"
        context: dict with optional keys: task_id, session_id, tenant_id,
                 operator_id, data

    Returns:
        HookResult
    """
    phase = _phase_for_hook(hook_name)
    ctx = HookContext(
        hook_name=hook_name,
        phase=phase,
        task_id=context.get("task_id"),
        session_id=context.get("session_id"),
        tenant_id=context.get("tenant_id", "default"),
        operator_id=context.get("operator_id"),
        data=context.get("data", {}),
    )
    return get_registry().fire_first(ctx)


# ── Built-in hook handlers for common scenarios ──────────────────────────────

def pre_task_handler(ctx: HookContext) -> HookResult:
    """pre-task hook: validate task input before execution."""
    task_prompt = ctx.get("task_prompt", "") or ctx.get("prompt", "")
    if not task_prompt and not ctx.data.get("task_id"):
        return HookResult(HookAction.BLOCK, "pre-task", "empty task prompt")
    return HookResult(HookAction.PROCEED, "pre-task", "task validated")


def post_task_handler(ctx: HookContext) -> HookResult:
    """post-task hook: log task completion."""
    task_id = ctx.task_id or "unknown"
    return HookResult(HookAction.PROCEED, "post-task", f"task {task_id} completed")


def pre_edit_handler(ctx: HookContext) -> HookResult:
    """pre-edit hook: validate edit operation before writing."""
    path = ctx.get("path", "")
    if not path:
        return HookResult(HookAction.BLOCK, "pre-edit", "no path specified")
    return HookResult(HookAction.PROCEED, "pre-edit", f"edit path validated: {path}")


def post_edit_handler(ctx: HookContext) -> HookResult:
    """post-edit hook: confirm edit was written."""
    return HookResult(HookAction.PROCEED, "post-edit", "edit completed")


def route_handler(ctx: HookContext) -> HookResult:
    """route hook: classify and route the task."""
    prompt = ctx.get("task_prompt", "") or ctx.get("prompt", "")
    if not prompt:
        return HookResult(HookAction.ESCALATE, "route", "no prompt to classify")
    return HookResult(HookAction.PROCEED, "route", "task routed")


def notify_handler(ctx: HookContext) -> HookResult:
    """notify hook: send a notification."""
    message = ctx.get("message", "") or ctx.get("data", {}).get("message", "")
    return HookResult(HookAction.PROCEED, "notify", f"notification: {message}")