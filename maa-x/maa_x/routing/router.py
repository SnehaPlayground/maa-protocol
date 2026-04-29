"""Routing module — model selection, MoE-style routing, multi-provider."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ModelSpec:
    name: str
    provider: str
    context_window: int = 128_000
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0
    max_rpm: int = 1000
    latency_ms_estimate: float = 0.0
    capabilities: list[str] = field(default_factory=list)


class RoutingStrategy:
    """Base routing strategy."""

    def select(self, request: dict, models: list[ModelSpec]) -> ModelSpec | None:
        raise NotImplementedError


class LatencyRouting(RoutingStrategy):
    """Route to lowest-latency model."""

    def select(self, request: dict, models: list[ModelSpec]) -> ModelSpec | None:
        return min(models, key=lambda m: m.latency_ms_estimate, default=None)


class CostRouting(RoutingStrategy):
    """Route to cheapest model that fits the request."""

    def select(self, request: dict, models: list[ModelSpec]) -> ModelSpec | None:
        # Simple: pick lowest total cost
        def cost(m: ModelSpec) -> float:
            return m.cost_per_1k_input + m.cost_per_1k_output
        return min(models, key=cost, default=None)


class CapabilityRouting(RoutingStrategy):
    """Route based on required capabilities."""

    def select(self, request: dict, models: list[ModelSpec]) -> ModelSpec | None:
        needs = set(request.get("required_capabilities", []))
        for m in models:
            if needs.issubset(set(m.capabilities)):
                return m
        return None


@dataclass
class RouteLedger:
    """Tracks routing decisions for audit."""

    entries: list[dict] = field(default_factory=list)

    def record(self, request: dict, selected: ModelSpec, strategy: str) -> None:
        self.entries.append({
            "strategy": strategy,
            "model": selected.name,
            "provider": selected.provider,
            "timestamp": __import__("time").time(),
        })


class MultiProviderRouter:
    """
    Routes requests across multiple model providers using configurable strategy.

    Parameters
    ----------
    models
        Available model specs.
    strategy
        Routing strategy name or instance.
    ledger
        Optional audit ledger.
    """

    DEFAULT_MODELS: list[ModelSpec] = [
        ModelSpec(name="gpt-5.4", provider="openai", latency_ms_estimate=800.0,
                  cost_per_1k_input=0.01, cost_per_1k_output=0.03,
                  capabilities=["chat", "function_calling", "vision"]),
        ModelSpec(name="gpt-5.4-mini", provider="openai", latency_ms_estimate=400.0,
                  cost_per_1k_input=0.003, cost_per_1k_output=0.012,
                  capabilities=["chat", "function_calling"]),
        ModelSpec(name="minimax-m2.7", provider="ollama", latency_ms_estimate=600.0,
                  cost_per_1k_input=0.0, cost_per_1k_output=0.0,
                  capabilities=["chat", "coding"]),
        ModelSpec(name="claude-sonnet-4", provider="anthropic", latency_ms_estimate=900.0,
                  cost_per_1k_input=0.008, cost_per_1k_output=0.024,
                  capabilities=["chat", "long_context", "analysis"]),
    ]

    def __init__(
        self,
        models: list[ModelSpec] | None = None,
        strategy: str | RoutingStrategy = "latency",
        ledger: RouteLedger | None = None,
    ) -> None:
        self.models = models or list(self.DEFAULT_MODELS)
        self.ledger = ledger or RouteLedger()
        if isinstance(strategy, str):
            self.strategy = self._build_strategy(strategy)
        else:
            self.strategy = strategy

    def _build_strategy(self, name: str) -> RoutingStrategy:
        return {
            "latency": LatencyRouting(),
            "cost": CostRouting(),
            "capability": CapabilityRouting(),
        }.get(name, LatencyRouting())

    def route(self, request: dict) -> ModelSpec | None:
        model = self.strategy.select(request, self.models)
        if model:
            self.ledger.record(request, model, type(self.strategy).__name__)
        return model

    def list_models(self) -> list[ModelSpec]:
        return list(self.models)