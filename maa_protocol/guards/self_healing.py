from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from ..exceptions import CircuitOpenError


@dataclass(slots=True)
class SelfHealingConfig:
    max_attempts: int = 3
    initial_interval: float = 0.1
    max_interval: float = 1.0
    circuit_fail_threshold: int = 5
    circuit_reset_seconds: float = 30.0


@dataclass(slots=True)
class SelfHealing:
    config: SelfHealingConfig = field(default_factory=SelfHealingConfig)
    failure_count: int = 0
    circuit_opened_at: float | None = None

    def invoke_with_healing(self, operation: Callable[[], Any], fallback: Callable[[Exception], Any] | None = None) -> Any:
        if self._circuit_open():
            raise CircuitOpenError("Circuit breaker is open")
        delay = self.config.initial_interval
        last_error: Exception | None = None
        for attempt in range(1, self.config.max_attempts + 1):
            try:
                result = operation()
                self.failure_count = 0
                self.circuit_opened_at = None
                return result
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                self.failure_count += 1
                if self.failure_count >= self.config.circuit_fail_threshold:
                    self.circuit_opened_at = time.time()
                if attempt == self.config.max_attempts:
                    if fallback:
                        return fallback(exc)
                    raise
                time.sleep(delay)
                delay = min(self.config.max_interval, delay * 2 if delay else self.config.max_interval)
        if fallback and last_error:
            return fallback(last_error)
        raise RuntimeError("Self-healing failed without a terminal exception")

    def _circuit_open(self) -> bool:
        if self.circuit_opened_at is None:
            return False
        if (time.time() - self.circuit_opened_at) >= self.config.circuit_reset_seconds:
            self.circuit_opened_at = None
            self.failure_count = 0
            return False
        return True
