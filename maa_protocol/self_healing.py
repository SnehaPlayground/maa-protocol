from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping


class SelfHealingError(RuntimeError):
    pass


@dataclass
class SelfHealingConfig:
    max_attempts: int = 3
    initial_interval: float = 1.0
    backoff_factor: float = 2.0
    max_interval: float = 30.0
    retry_on: tuple[type[Exception], ...] = (Exception,)
    escalate_on: tuple[type[Exception], ...] = ()
    escalation_handler: Callable[[Exception, Mapping[str, Any], Mapping[str, Any]], Any] | None = None

    def next_interval(self, attempt: int) -> float:
        interval = self.initial_interval * (self.backoff_factor ** (attempt - 1))
        return min(interval, self.max_interval)


@dataclass
class SelfHealing:
    """Automatic retry + escalation handler for governed invocations.

    Implements a policy-driven retry loop with exponential backoff.
    If all retries are exhausted, optionally escalates to a configured handler
    (e.g., Mother Agent fallback, external notification).
    """

    config: SelfHealingConfig = field(default_factory=SelfHealingConfig)
    _attempt: int = field(default=0, init=False, repr=False)

    def retry(self, fn: Callable[[], Any]) -> Any:
        self._attempt = 0
        last_exc: Exception | None = None

        while self._attempt < self.config.max_attempts:
            try:
                result = fn()
                self._attempt = 0
                return result
            except self.config.retry_on as exc:
                last_exc = exc
                self._attempt += 1
                if self._attempt >= self.config.max_attempts:
                    break
                interval = self.config.next_interval(self._attempt)
                time.sleep(interval)

        # All retries exhausted
        if self.config.escalation_handler and last_exc is not None:
            return self.config.escalation_handler(last_exc, {}, {})

        if last_exc is not None:
            raise SelfHealingError(
                f"Self-healing exhausted after {self.config.max_attempts} attempts"
            ) from last_exc

        raise SelfHealingError("Self-healing exhausted but no exception to re-raise")

    def invoke_with_healing(
        self,
        fn: Callable[[], Any],
        on_retry: Callable[[Exception, int], None] | None = None,
    ) -> Any:
        self._attempt = 0
        last_exc: Exception | None = None

        while self._attempt < self.config.max_attempts:
            try:
                result = fn()
                self._attempt = 0
                return result
            except self.config.retry_on as exc:
                last_exc = exc
                self._attempt += 1
                attempt = self._attempt
                interval = self.config.next_interval(attempt)

                if on_retry:
                    try:
                        on_retry(exc, attempt)
                    except Exception:
                        pass

                if self._attempt >= self.config.max_attempts:
                    break

                time.sleep(interval)

        # Escalation
        if self.config.escalation_handler and last_exc is not None:
            try:
                return self.config.escalation_handler(last_exc, {}, {})
            except Exception:
                pass

        if last_exc is not None:
            raise SelfHealingError(
                f"Self-healing exhausted after {self.config.max_attempts} attempts"
            ) from last_exc

        raise SelfHealingError("Self-healing exhausted: no exception recorded")
