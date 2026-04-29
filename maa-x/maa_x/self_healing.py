"""Self-healing runtime policies."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from maa_x.exceptions import CircuitOpenError


@dataclass
class HealingAction:
    action: str
    target: str
    timestamp: float = field(default_factory=time.time)
    success: bool = False
    message: str = ''


class SelfHealingPolicy:
    def __init__(self) -> None:
        self._healing_log: list[HealingAction] = []
        self._circuit_open: bool = False
        self._failure_count: dict[str, int] = {}

    def record_failure(self, component: str, error: str) -> None:
        self._failure_count[component] = self._failure_count.get(component, 0) + 1
        if self._failure_count[component] >= 5:
            self._circuit_open = True

    def record_healing(self, action: str, target: str, success: bool, message: str = '') -> None:
        self._healing_log.append(HealingAction(action, target, success=success, message=message))
        if success:
            self._failure_count.pop(target, None)
            if self._circuit_open and self._failure_count.get(target, 0) == 0:
                self._circuit_open = False

    def is_circuit_open(self, component: str | None = None) -> bool:
        if component:
            return self._failure_count.get(component, 0) >= 5
        return self._circuit_open

    def heal(self, component: str) -> HealingAction:
        action = HealingAction('restart', component)
        self.record_healing('restart', component, True, 'Self-healed')
        return action

    def get_status(self) -> dict[str, Any]:
        return {'circuit_open': self._circuit_open, 'failure_counts': dict(self._failure_count), 'healing_log_len': len(self._healing_log)}


def create_self_healing_policy() -> SelfHealingPolicy:
    return SelfHealingPolicy()
