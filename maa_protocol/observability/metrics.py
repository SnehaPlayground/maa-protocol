"""Lightweight metrics collector for governance operations."""

from __future__ import annotations

import json
import statistics
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

METRICS_FILE = Path("/tmp/maa-protocol-metrics.json")


@dataclass(slots=True)
class MetricSnapshot:
    counts: dict[str, int]
    latencies: dict[str, list[float]]
    timestamps: dict[str, float]

    def summary(self) -> dict[str, Any]:
        latency_summary: dict[str, Any] = {}
        for name, values in self.latencies.items():
            if not values:
                continue
            ordered = sorted(values)
            latency_summary[name] = {
                "count": len(values),
                "min": min(values),
                "max": max(values),
                "avg": statistics.fmean(values),
                "p50": statistics.median(values),
                "p95": ordered[max(0, int(len(values) * 0.95) - 1)],
            }
        return {"counts": dict(self.counts), "latency_summary": latency_summary}


class MetricsCollector:
    def __init__(self, persist_path: str | Path | None = None) -> None:
        self._persist_path = Path(persist_path) if persist_path else METRICS_FILE
        self._counts: dict[str, int] = {}
        self._latencies: dict[str, list[float]] = {}
        self._timestamps: dict[str, float] = {}
        self._load()

    def increment(self, name: str, value: int = 1) -> None:
        self._counts[name] = self._counts.get(name, 0) + value
        self._timestamps[name] = time.time()

    def record_latency(self, name: str, duration_ms: float) -> None:
        self._latencies.setdefault(name, []).append(duration_ms)
        self._timestamps[name] = time.time()

    def observe_ms(self, name: str, duration_ms: float) -> None:
        self.record_latency(name, duration_ms)

    def snapshot(self) -> MetricSnapshot:
        return MetricSnapshot(
            dict(self._counts),
            {key: list(value) for key, value in self._latencies.items()},
            dict(self._timestamps),
        )

    def export_json(self) -> dict[str, Any]:
        snap = self.snapshot()
        return {
            "counts": snap.counts,
            "latencies": snap.latencies,
            "timestamps": snap.timestamps,
            "summary": snap.summary(),
        }

    def save(self) -> None:
        self._persist_path.write_text(json.dumps(self.export_json(), indent=2))

    def _load(self) -> None:
        if not self._persist_path.exists():
            return
        try:
            data = json.loads(self._persist_path.read_text())
        except Exception:
            return
        self._counts = {key: int(value) for key, value in data.get("counts", {}).items()}
        self._latencies = {
            key: [float(item) for item in value]
            for key, value in data.get("latencies", {}).items()
        }
        self._timestamps = {key: float(value) for key, value in data.get("timestamps", {}).items()}


@contextmanager
def TimedBlock(metrics: MetricsCollector, name: str) -> Iterator[None]:
    start = time.perf_counter()
    try:
        yield
    finally:
        duration_ms = (time.perf_counter() - start) * 1000
        metrics.record_latency(name, duration_ms)
        metrics.increment(name)
