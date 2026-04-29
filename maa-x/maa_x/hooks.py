"""Lifecycle hooks system."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class HookPhase(str, Enum):
    CORE = "core"
    SESSION = "session"
    INTELLIGENCE = "intelligence"


class HookAction(str, Enum):
    PROCEED = "proceed"
    BLOCK = "block"
    MODIFY = "modify"
    ESCALATE = "escalate"


@dataclass
class HookContext:
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
    action: HookAction
    hook_name: str
    message: str = ""
    modified_context: dict[str, Any] | None = None
    latency_ms: float = 0.0
    error: str | None = None


@dataclass
class HookRegistration:
    name: str
    handler: Callable[[HookContext], HookResult]
    phase: HookPhase
    enabled: bool = True
    description: str = ""
    priority: int = 0


class HookRegistry:
    HOOK_POINTS = ["pre-edit", "post-edit", "pre-command", "post-command", "pre-task", "post-task", "session-start", "session-end", "session-restore", "notify", "route", "explain", "pretrain", "build-agents", "transfer"]

    def __init__(self) -> None:
        self._hooks: dict[str, list[HookRegistration]] = {name: [] for name in HookRegistry.HOOK_POINTS}
        self._execution_log: list[dict[str, Any]] = []
        self._log_max = 500

    def list_hooks(self) -> list[str]:
        return sorted(set(self._hooks.keys()))

    def list_active_hooks(self) -> list[str]:
        return sorted(k for k, v in self._hooks.items() if any(r.enabled for r in v))

    def register(self, hook_name: str, handler: Callable[[HookContext], HookResult], phase: HookPhase = HookPhase.CORE, description: str = "", priority: int = 0) -> None:
        self._hooks.setdefault(hook_name, []).append(HookRegistration(hook_name, handler, phase, True, description, priority))
        self._hooks[hook_name].sort(key=lambda r: r.priority)

    def unregister(self, hook_name: str, handler: Callable[[HookContext], HookResult]) -> bool:
        original = len(self._hooks.get(hook_name, []))
        self._hooks[hook_name] = [r for r in self._hooks.get(hook_name, []) if r.handler is not handler]
        return len(self._hooks[hook_name]) < original

    def enable(self, hook_name: str, handler: Callable[[HookContext], HookResult] | None = None) -> None:
        for reg in self._hooks.get(hook_name, []):
            if handler is None or reg.handler is handler:
                reg.enabled = True

    def disable(self, hook_name: str, handler: Callable[[HookContext], HookResult] | None = None) -> None:
        for reg in self._hooks.get(hook_name, []):
            if handler is None or reg.handler is handler:
                reg.enabled = False

    def fire(self, ctx: HookContext) -> list[HookResult]:
        enabled = [r for r in self._hooks.get(ctx.hook_name, []) if r.enabled]
        if not enabled:
            return [HookResult(HookAction.PROCEED, ctx.hook_name, "no handlers registered")]
        results = []
        for reg in enabled:
            start = time.monotonic()
            try:
                result = reg.handler(ctx)
                result.latency_ms = (time.monotonic() - start) * 1000
                result.hook_name = ctx.hook_name
            except Exception as e:
                result = HookResult(HookAction.PROCEED, ctx.hook_name, f"hook error: {e}", latency_ms=(time.monotonic() - start) * 1000, error=str(e))
            results.append(result)
            self._execution_log.append({"timestamp": time.time(), "hook": ctx.hook_name, "phase": reg.phase.value, "action": result.action.value, "message": result.message, "latency_ms": result.latency_ms, "error": result.error, "priority": reg.priority})
            if len(self._execution_log) > self._log_max:
                self._execution_log.pop(0)
        return results

    def fire_first(self, ctx: HookContext) -> HookResult:
        results = self.fire(ctx)
        for r in results:
            if r.action in (HookAction.BLOCK, HookAction.MODIFY):
                return r
        return results[0] if results else HookResult(HookAction.PROCEED, ctx.hook_name)

    def execution_log(self, limit: int = 50) -> list[dict[str, Any]]:
        return self._execution_log[-limit:]

    def clear_log(self) -> None:
        self._execution_log = []


def _phase_for_hook(name: str) -> HookPhase:
    core = {"pre-edit", "post-edit", "pre-command", "post-command", "pre-task", "post-task"}
    session = {"session-start", "session-end", "session-restore", "notify"}
    if name in core:
        return HookPhase.CORE
    if name in session:
        return HookPhase.SESSION
    return HookPhase.INTELLIGENCE


def _register_default_hooks(registry: HookRegistry) -> None:
    def make_proceed_handler(name: str):
        def handler(ctx: HookContext) -> HookResult:
            return HookResult(HookAction.PROCEED, name, f"{name} completed")
        return handler
    for name in HookRegistry.HOOK_POINTS:
        registry.register(name, make_proceed_handler(name), phase=_phase_for_hook(name), description=f"default {name} handler", priority=9999)


_global_registry: HookRegistry | None = None


def get_registry() -> HookRegistry:
    global _global_registry
    if _global_registry is None:
        _global_registry = HookRegistry()
        _register_default_hooks(_global_registry)
    return _global_registry


def list_hooks() -> list[str]:
    return get_registry().list_hooks()


def list_active_hooks() -> list[str]:
    return get_registry().list_active_hooks()


def register(hook_name: str, handler: Callable[[HookContext], HookResult], phase: HookPhase = HookPhase.CORE, description: str = "", priority: int = 0) -> None:
    get_registry().register(hook_name, handler, phase, description, priority)


def unregister(hook_name: str, handler: Callable[[HookContext], HookResult]) -> bool:
    return get_registry().unregister(hook_name, handler)


def fire(hook_name: str, **ctx_kwargs):
    return get_registry().fire(HookContext(hook_name=hook_name, phase=_phase_for_hook(hook_name), **ctx_kwargs))


def fire_first(hook_name: str, **ctx_kwargs) -> HookResult:
    return get_registry().fire_first(HookContext(hook_name=hook_name, phase=_phase_for_hook(hook_name), **ctx_kwargs))


def execution_log(limit: int = 50) -> list[dict[str, Any]]:
    return get_registry().execution_log(limit)


def hook_dispatch(hook_name: str, context: dict[str, Any]) -> HookResult:
    return get_registry().fire_first(HookContext(hook_name=hook_name, phase=_phase_for_hook(hook_name), task_id=context.get('task_id'), session_id=context.get('session_id'), tenant_id=context.get('tenant_id', 'default'), operator_id=context.get('operator_id'), data=context.get('data', {})))


def pre_task_handler(ctx: HookContext) -> HookResult:
    task_prompt = ctx.get('task_prompt', '') or ctx.get('prompt', '')
    if not task_prompt and not ctx.data.get('task_id'):
        return HookResult(HookAction.BLOCK, 'pre-task', 'empty task prompt')
    return HookResult(HookAction.PROCEED, 'pre-task', 'task validated')


def post_task_handler(ctx: HookContext) -> HookResult:
    return HookResult(HookAction.PROCEED, 'post-task', f"task {ctx.task_id or 'unknown'} completed")


def pre_edit_handler(ctx: HookContext) -> HookResult:
    path = ctx.get('path', '')
    if not path:
        return HookResult(HookAction.BLOCK, 'pre-edit', 'no path specified')
    return HookResult(HookAction.PROCEED, 'pre-edit', f'edit path validated: {path}')


def post_edit_handler(ctx: HookContext) -> HookResult:
    return HookResult(HookAction.PROCEED, 'post-edit', 'edit completed')


def route_handler(ctx: HookContext) -> HookResult:
    prompt = ctx.get('task_prompt', '') or ctx.get('prompt', '')
    if not prompt:
        return HookResult(HookAction.ESCALATE, 'route', 'no prompt to classify')
    return HookResult(HookAction.PROCEED, 'route', 'task routed')


def notify_handler(ctx: HookContext) -> HookResult:
    message = ctx.get('message', '') or ctx.get('data', {}).get('message', '')
    return HookResult(HookAction.PROCEED, 'notify', f'notification: {message}')
