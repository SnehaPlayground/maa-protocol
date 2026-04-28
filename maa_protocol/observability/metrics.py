from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any


logger = logging.getLogger("maa_protocol")


@dataclass(slots=True)
class MetricsCollector:
    counters: dict[str, int] = field(default_factory=dict)
    timings_ms: dict[str, list[float]] = field(default_factory=dict)

    def increment(self, name: str, value: int = 1) -> None:
        self.counters[name] = self.counters.get(name, 0) + value

    def observe_ms(self, name: str, value: float) -> None:
        self.timings_ms.setdefault(name, []).append(value)

    def snapshot(self) -> dict[str, Any]:
        return {
            "counters": dict(self.counters),
            "timings_ms": {k: list(v) for k, v in self.timings_ms.items()},
        }


class TimedBlock:
    def __init__(self, collector: MetricsCollector, label: str) -> None:
        self.collector = collector
        self.label = label
        self.started = 0.0

    def __enter__(self) -> "TimedBlock":
        self.started = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        elapsed = (time.perf_counter() - self.started) * 1000
        self.collector.observe_ms(self.label, elapsed)
        if exc:
            self.collector.increment(f"{self.label}.errors")
            logger.exception("Timed block failed", extra={"label": self.label})
