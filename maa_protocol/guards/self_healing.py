"""Retry and circuit-breaker guard."""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..exceptions import CircuitOpenError


class SelfHealingConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    max_attempts: int = Field(default=3, gt=0)
    initial_interval: float = Field(default=0.1, gt=0.0)
    max_interval: float = Field(default=1.0, gt=0.0)
    circuit_fail_threshold: int = Field(default=5, gt=0)
    circuit_reset_seconds: float = Field(default=30.0, gt=0.0)

    def model_post_init(self, __context: Any) -> None:
        if self.max_interval < self.initial_interval:
            raise ValueError("max_interval must be >= initial_interval")


@dataclass(slots=True)
class SelfHealing:
    config: SelfHealingConfig = field(default_factory=SelfHealingConfig)
    failure_count: int = 0
    circuit_opened_at: float | None = None
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.config, SelfHealingConfig):
            try:
                self.config = SelfHealingConfig.model_validate(self.config)
            except ValidationError as exc:
                raise ValueError(str(exc)) from exc

    def invoke_with_healing(
        self,
        operation: Callable[[], Any],
        fallback: Callable[[Exception], Any] | None = None,
    ) -> Any:
        if self._circuit_open():
            raise CircuitOpenError("Circuit breaker is open")
        delay = self.config.initial_interval
        last_error: Exception | None = None
        for attempt in range(1, self.config.max_attempts + 1):
            try:
                result = operation()
                self._reset()
                return result
            except Exception as exc:
                last_error = exc
                self._record_failure()
                if attempt == self.config.max_attempts:
                    break
                time.sleep(delay)
                delay = min(self.config.max_interval, delay * 2)
        if fallback and last_error:
            return fallback(last_error)
        if last_error:
            raise last_error
        raise RuntimeError("Self-healing failed without a terminal exception")

    async def ainvoke_with_healing(
        self,
        operation: Callable[[], Awaitable[Any]],
        fallback: Callable[[Exception], Any] | None = None,
    ) -> Any:
        if self._circuit_open():
            raise CircuitOpenError("Circuit breaker is open")
        delay = self.config.initial_interval
        last_error: Exception | None = None
        for attempt in range(1, self.config.max_attempts + 1):
            try:
                result = await operation()
                self._reset()
                return result
            except Exception as exc:
                last_error = exc
                self._record_failure()
                if attempt == self.config.max_attempts:
                    break
                await asyncio.sleep(delay)
                delay = min(self.config.max_interval, delay * 2)
        if fallback and last_error:
            return fallback(last_error)
        if last_error:
            raise last_error
        raise RuntimeError("Self-healing failed without a terminal exception")

    def _record_failure(self) -> None:
        with self._lock:
            self.failure_count += 1
            if self.failure_count >= self.config.circuit_fail_threshold:
                self.circuit_opened_at = time.time()

    def _reset(self) -> None:
        with self._lock:
            self.failure_count = 0
            self.circuit_opened_at = None

    def _circuit_open(self) -> bool:
        with self._lock:
            if self.circuit_opened_at is None:
                return False
            if (time.time() - self.circuit_opened_at) >= self.config.circuit_reset_seconds:
                self.failure_count = 0
                self.circuit_opened_at = None
                return False
            return True
