"""Performance targets and benchmarks."""

from __future__ import annotations

from typing import Any


def performance_targets() -> dict[str, Any]:
    return {
        'progress_ping_s': 300,
        'max_concurrent_children': 4,
        'circuit_breaker_threshold': 0.05,
    }


def benchmark_result(name: str, latency_ms: float, throughput: float, cost: float) -> dict[str, Any]:
    return {'name': name, 'latency_ms': latency_ms, 'throughput': throughput, 'cost': cost}
