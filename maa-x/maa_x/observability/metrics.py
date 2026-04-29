"""Observability metrics with lightweight persistence and export."""

from __future__ import annotations

import json
import statistics
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

METRICS_FILE = Path("/tmp/maa-x-metrics.json")


@dataclass
class MetricSnapshot:
    counts: dict[str, int]
    latencies: dict[str, list[float]]
    timestamps: dict[str, float]

    def summary(self) -> dict[str, Any]:
        out: dict[str, Any] = {"counts": dict(self.counts), "latency_summary": {}}
        for name, values in self.latencies.items():
            if not values:
                continue
            out["latency_summary"][name] = {
                "count": len(values),
                "min": min(values),
                "max": max(values),
                "avg": statistics.fmean(values),
                "p50": statistics.median(values),
                "p95": sorted(values)[max(0, int(len(values) * 0.95) - 1)],
            }
        return out


class MetricsCollector:
    def __init__(self, persist_path: str | Path | None = None) -> None:
        self._counts: dict[str, int] = {}
        self._latencies: dict[str, list[float]] = {}
        self._timestamps: dict[str, float] = {}
        self._persist_path = Path(persist_path) if persist_path else METRICS_FILE
        self._load()

    def increment(self, name: str, value: int = 1) -> None:
        self._counts[name] = self._counts.get(name, 0) + value
        self._timestamps[name] = time.time()

    def observe_ms(self, name: str, value: float) -> None:
        self.record_latency(name, value)

    def record_latency(self, name: str, duration_ms: float) -> None:
        self._latencies.setdefault(name, []).append(duration_ms)
        self._timestamps[name] = time.time()

    def snapshot(self) -> MetricSnapshot:
        return MetricSnapshot(dict(self._counts), {k: list(v) for k, v in self._latencies.items()}, dict(self._timestamps))

    @property
    def counts(self) -> dict[str, int]:
        return dict(self._counts)

    def save(self) -> None:
        self._persist_path.write_text(json.dumps({"counts": self._counts, "latencies": self._latencies, "timestamps": self._timestamps}, indent=2))

    def _load(self) -> None:
        if not self._persist_path.exists():
            return
        try:
            data = json.loads(self._persist_path.read_text())
            self._counts = {k: int(v) for k, v in data.get("counts", {}).items()}
            self._latencies = {k: [float(x) for x in v] for k, v in data.get("latencies", {}).items()}
            self._timestamps = {k: float(v) for k, v in data.get("timestamps", {}).items()}
        except Exception:
            pass

    def export_json(self) -> dict[str, Any]:
        snap = self.snapshot()
        return {"counts": snap.counts, "latencies": snap.latencies, "timestamps": snap.timestamps, "summary": snap.summary()}

    def dashboard(self) -> str:
        summary = self.snapshot().summary()
        lines = ["Maa-X Metrics Dashboard", "====================="]
        for name, count in summary.get("counts", {}).items():
            lines.append(f"count {name}: {count}")
        for name, data in summary.get("latency_summary", {}).items():
            lines.append(f"latency {name}: avg={data['avg']:.2f}ms p50={data['p50']:.2f}ms p95={data['p95']:.2f}ms")
        return "\n".join(lines)


@contextmanager
def TimedBlock(metrics: MetricsCollector, name: str):
    start = time.perf_counter()
    try:
        yield
    finally:
        duration_ms = (time.perf_counter() - start) * 1000
        metrics.record_latency(name, duration_ms)
        metrics.increment(name)
