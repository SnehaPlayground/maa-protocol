"""Self-healing guard — bounded retries with circuit-breaker support."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from ..exceptions import CircuitOpenError


@dataclass(slots=True)
class SelfHealingConfig:
    max_retries: int = 3
    base_delay: float = 0.5
    backoff_multiplier: float = 2.0
    max_delay: float = 30.0
    circuit_threshold: int = 5
    circuit_window: float = 60.0


@dataclass(slots=True)
class SelfHealing:
    config: SelfHealingConfig = field(default_factory=SelfHealingConfig)
    _failure_counts: dict[str, int] = field(default_factory=dict)
    _circuit_opens: dict[str, float] = field(default_factory=dict)

    def invoke_with_healing(self, operation: Callable[[], Any]) -> Any:
        key = "default"
        now = time.time()
        if key in self._circuit_opens:
            if now - self._circuit_opens[key] < self.config.circuit_window:
                raise CircuitOpenError("Circuit breaker is open")
            del self._circuit_opens[key]
            self._failure_counts[key] = 0

        for attempt in range(self.config.max_retries + 1):
            try:
                return operation()
            except Exception as exc:
                if attempt == self.config.max_retries:
                    self._failure_counts[key] = self._failure_counts.get(key, 0) + 1
                    if self._failure_counts[key] >= self.config.circuit_threshold:
                        self._circuit_opens[key] = now
                    raise
                delay = min(
                    self.config.base_delay * (self.config.backoff_multiplier ** attempt),
                    self.config.max_delay,
                )
                time.sleep(delay)
        raise RuntimeError("Unexpected exit from retry loop")