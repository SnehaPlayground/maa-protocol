"""Provider routing with Maa Protocol style cost and strategy surfaces."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


@dataclass
class ModelSpec:
    id: str
    provider: str
    name: str
    input_cost_per_mtok: float = 0.0
    output_cost_per_mtok: float = 0.0
    avg_latency_ms: float = 0.0
    supports_tools: bool = True
    supports_stream: bool = True
    context_window: int = 128_000
    provider_tier: str = "standard"

    def cost_for_tokens(self, input_tok: int, output_tok: int) -> float:
        in_cost = (input_tok / 1_000_000) * self.input_cost_per_mtok
        out_cost = (output_tok / 1_000_000) * self.output_cost_per_mtok
        return round(in_cost + out_cost, 6)

    def cost_estimate(self, prompt_chars: int) -> float:
        tok = max(1, prompt_chars // 4)
        return self.cost_for_tokens(tok, tok // 4)


class RoutingStrategy(Enum):
    COST_OPTIMAL = "cost_optimal"
    LATENCY_OPTIMAL = "latency_optimal"
    LOAD_BALANCED = "load_balanced"
    ROUND_ROBIN = "round_robin"
    FALLBACK = "fallback"


class ProviderModels:
    MODELS: dict[str, ModelSpec] = {
        "gpt-5.2": ModelSpec("gpt-5.2", "openai", "GPT-5.2", 1.5, 6.0, 2000),
        "gpt-5.4": ModelSpec("gpt-5.4", "openai", "GPT-5.4", 3.0, 12.0, 2500),
        "gpt-5.4-mini": ModelSpec("gpt-5.4-mini", "openai", "GPT-5.4-mini", 0.15, 0.6, 1500),
        "minimax-m2.7:cloud": ModelSpec("minimax-m2.7:cloud", "ollama", "MiniMax M2.7 (Cloud)", 0.0, 0.0, 800, provider_tier="budget"),
        "llama3:70b": ModelSpec("llama3:70b", "ollama", "Llama3 70B (Local)", 0.0, 0.0, 5000, provider_tier="budget"),
        "claude-sonnet-4": ModelSpec("claude-sonnet-4", "anthropic", "Claude Sonnet 4", 3.0, 15.0, 1800, provider_tier="premium"),
        "claude-3-5-haiku": ModelSpec("claude-3-5-haiku", "anthropic", "Claude 3.5 Haiku", 0.8, 4.0, 1200),
    }

    @classmethod
    def get(cls, model_id: str) -> ModelSpec | None:
        return cls.MODELS.get(model_id)

    @classmethod
    def list_all(cls) -> list[ModelSpec]:
        return list(cls.MODELS.values())


@dataclass
class RouteRequest:
    prompt: str
    requires_tools: bool = True
    requires_stream: bool = False
    max_latency_ms: float = 10_000.0
    max_cost: float | None = None
    preferred_provider: str | None = None
    task_type: str = "general"
    strategy: RoutingStrategy = RoutingStrategy.COST_OPTIMAL


@dataclass
class RouteDecision:
    model_id: str
    provider: str
    strategy_used: RoutingStrategy
    estimated_cost: float
    estimated_latency_ms: float
    alternatives: list[str]
    routing_reason: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class TokenRecord:
    model_id: str
    task_type: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: float
    timestamp: float


class TokenTracker:
    def __init__(self, max_records: int = 5000) -> None:
        self._records: list[TokenRecord] = []
        self._max_records = max_records
        self._totals: dict[str, dict[str, Any]] = {}

    def record(self, model_id: str, task_type: str, input_tok: int, output_tok: int, cost_usd: float, latency_ms: float) -> None:
        self._records.append(TokenRecord(model_id, task_type, input_tok, output_tok, cost_usd, latency_ms, time.time()))
        if len(self._records) > self._max_records:
            self._records.pop(0)
        t = self._totals.setdefault(model_id, {"input_tok": 0, "output_tok": 0, "cost_usd": 0.0, "calls": 0, "total_latency_ms": 0.0})
        t["input_tok"] += input_tok
        t["output_tok"] += output_tok
        t["cost_usd"] += cost_usd
        t["calls"] += 1
        t["total_latency_ms"] += latency_ms

    def stats(self) -> dict[str, Any]:
        return {
            "total_cost": sum(t["cost_usd"] for t in self._totals.values()),
            "total_calls": sum(t["calls"] for t in self._totals.values()),
            "by_model": {mid: {"cost_usd": t["cost_usd"], "calls": t["calls"], "avg_latency_ms": round(t["total_latency_ms"] / t["calls"], 2) if t["calls"] else 0, "input_tok": t["input_tok"], "output_tok": t["output_tok"]} for mid, t in self._totals.items()},
        }


class ProviderRouter:
    def __init__(self) -> None:
        self._tracker = TokenTracker()
        self._round_robin_index: dict[str, int] = {}

    def route(self, request: RouteRequest) -> RouteDecision:
        candidates = self._filter_candidates(request)
        if not candidates:
            fallback = list(ProviderModels.MODELS.values())[0]
            return RouteDecision(fallback.id, fallback.provider, request.strategy, 0.0, fallback.avg_latency_ms, [], "no candidates met requirements; default fallback")
        model_id = self._select_model(candidates, request)
        model = ProviderModels.get(model_id) or candidates[0]
        alternatives = [m.id for m in sorted(candidates, key=lambda m: m.cost_estimate(len(request.prompt))) if m.id != model_id][:3]
        return RouteDecision(model_id, model.provider, request.strategy, model.cost_estimate(len(request.prompt)), model.avg_latency_ms, alternatives, self._routing_reason(model, request))

    def _filter_candidates(self, request: RouteRequest) -> list[ModelSpec]:
        candidates = []
        for model in ProviderModels.MODELS.values():
            if request.requires_tools and not model.supports_tools:
                continue
            if request.requires_stream and not model.supports_stream:
                continue
            if model.avg_latency_ms > request.max_latency_ms:
                continue
            if request.max_cost is not None and model.cost_estimate(len(request.prompt)) > request.max_cost:
                continue
            if request.preferred_provider and model.provider != request.preferred_provider:
                continue
            candidates.append(model)
        return candidates

    def _select_model(self, candidates: list[ModelSpec], request: RouteRequest) -> str:
        strategy = request.strategy
        if strategy == RoutingStrategy.COST_OPTIMAL:
            return min(candidates, key=lambda m: m.cost_estimate(len(request.prompt))).id
        if strategy == RoutingStrategy.LATENCY_OPTIMAL:
            return min(candidates, key=lambda m: m.avg_latency_ms).id
        if strategy == RoutingStrategy.ROUND_ROBIN:
            idx = self._round_robin_index.get(request.task_type, 0)
            self._round_robin_index[request.task_type] = idx + 1
            return candidates[idx % len(candidates)].id
        if strategy == RoutingStrategy.FALLBACK:
            return max(candidates, key=lambda m: (1 if m.provider_tier == "premium" else 0, -m.avg_latency_ms)).id
        if strategy == RoutingStrategy.LOAD_BALANCED:
            stats = self._tracker.stats().get("by_model", {})
            return min(candidates, key=lambda m: stats.get(m.id, {}).get("calls", 0)).id
        return min(candidates, key=lambda m: m.cost_estimate(len(request.prompt))).id

    def _routing_reason(self, model: ModelSpec, request: RouteRequest) -> str:
        return f"strategy={request.strategy.value}, picked {model.id} (${model.cost_estimate(len(request.prompt)):.4f} est., {model.avg_latency_ms:.0f}ms, provider={model.provider})"

    def record_usage(self, model_id: str, task_type: str, input_tok: int, output_tok: int, latency_ms: float) -> None:
        model = ProviderModels.get(model_id)
        cost = model.cost_for_tokens(input_tok, output_tok) if model else 0.0
        self._tracker.record(model_id, task_type, input_tok, output_tok, cost, latency_ms)

    def stats(self) -> dict[str, Any]:
        return self._tracker.stats()


class CostOptimizer:
    def estimate(self, model_id: str, prompt_chars: int) -> float:
        model = ProviderModels.get(model_id)
        return model.cost_estimate(prompt_chars) if model else 0.0

    def cheapest(self, prompt_chars: int, candidates: list[str] | None = None) -> ModelSpec | None:
        models = [ProviderModels.get(c) for c in (candidates or list(ProviderModels.MODELS.keys()))]
        models = [m for m in models if m is not None]
        return min(models, key=lambda m: m.cost_estimate(prompt_chars), default=None)


class RouteLedger:
    def __init__(self, max_entries: int = 1000) -> None:
        self._entries: list[RouteDecision] = []
        self._max_entries = max_entries

    def record(self, decision: RouteDecision) -> None:
        self._entries.append(decision)
        if len(self._entries) > self._max_entries:
            self._entries.pop(0)

    def recent(self, limit: int = 50) -> list[RouteDecision]:
        return self._entries[-limit:]

    def stats(self) -> dict[str, Any]:
        by_strategy: dict[str, int] = {}
        by_model: dict[str, int] = {}
        for e in self._entries:
            by_strategy[e.strategy_used.value] = by_strategy.get(e.strategy_used.value, 0) + 1
            by_model[e.model_id] = by_model.get(e.model_id, 0) + 1
        return {"total": len(self._entries), "by_strategy": by_strategy, "by_model": by_model}


_router = ProviderRouter()
_ledger = RouteLedger()


def route_model(request: RouteRequest) -> RouteDecision:
    decision = _router.route(request)
    _ledger.record(decision)
    return decision


def record_call(model_id: str, task_type: str, input_tok: int, output_tok: int, latency_ms: float) -> None:
    _router.record_usage(model_id, task_type, input_tok, output_tok, latency_ms)


def routing_stats() -> dict[str, Any]:
    return {"tracker": _router.stats(), "ledger": _ledger.stats()}


def list_available_models() -> list[ModelSpec]:
    return ProviderModels.list_all()


def get_model(model_id: str) -> ModelSpec | None:
    return ProviderModels.get(model_id)
