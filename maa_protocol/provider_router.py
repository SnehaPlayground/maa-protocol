"""
MAA Protocol — Provider Routing and Cost Optimization
======================================================
Policy-driven model/provider selection with real cost tracking.

Components:
- ModelSpec — per-model capability and cost metadata
- ProviderModels — registry of available models per provider
- RoutingStrategy enum (COST_OPTIMAL/LATENCY_OPTIMAL/LOAD_BALANCED/ROUND_ROBIN/FALLBACK)
- RouteRequest / RouteDecision — routing API
- ProviderRouter — core routing engine with strategy selection
- TokenTracker — tracks token usage per model/task
- CostOptimizer — estimates and optimizes route cost
- RouteLedger — logs all routing decisions for observability

All monetary values in USD. Token counts are input+output combined.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# ── Model capability catalog ──────────────────────────────────────────────────

@dataclass
class ModelSpec:
    id: str                    # e.g. "gpt-5.4" or "local:llama3"
    provider: str              # e.g. "openai", "ollama", "anthropic"
    name: str                  # display name
    input_cost_per_mtok: float = 0.0   # USD per million input tokens
    output_cost_per_mtok: float = 0.0  # USD per million output tokens
    avg_latency_ms: float = 0.0        # typical round-trip latency
    supports_tools: bool = True
    supports_stream: bool = True
    context_window: int = 128_000      # max context tokens
    provider_tier: str = "standard"    # "budget" | "standard" | "premium"

    def cost_for_tokens(self, input_tok: int, output_tok: int) -> float:
        """Compute cost in USD for a given token count."""
        in_cost = (input_tok / 1_000_000) * self.input_cost_per_mtok
        out_cost = (output_tok / 1_000_000) * self.output_cost_per_mtok
        return round(in_cost + out_cost, 6)

    def cost_estimate(self, prompt_chars: int) -> float:
        """Estimate cost from character count (rough: 4 chars/token)."""
        tok = max(1, prompt_chars // 4)
        return self.cost_for_tokens(tok, tok // 4)  # assume output ~25% of input


# ── Provider model registry ───────────────────────────────────────────────────

class ProviderModels:
    """
    Registry of available models per provider.
    Default catalog covers MAA's known provider setup.
    """

    MODELS: dict[str, ModelSpec] = {
        # OpenAI Codex models
        "gpt-5.2": ModelSpec(
            id="gpt-5.2", provider="openai", name="GPT-5.2",
            input_cost_per_mtok=1.5, output_cost_per_mtok=6.0,
            avg_latency_ms=2000, supports_tools=True, supports_stream=True,
        ),
        "gpt-5.4": ModelSpec(
            id="gpt-5.4", provider="openai", name="GPT-5.4",
            input_cost_per_mtok=3.0, output_cost_per_mtok=12.0,
            avg_latency_ms=2500, supports_tools=True, supports_stream=True,
        ),
        "gpt-5.4-mini": ModelSpec(
            id="gpt-5.4-mini", provider="openai", name="GPT-5.4-mini",
            input_cost_per_mtok=0.15, output_cost_per_mtok=0.6,
            avg_latency_ms=1500, supports_tools=True, supports_stream=True,
        ),
        # Ollama (local) — near-zero cost
        "minimax-m2.7:cloud": ModelSpec(
            id="minimax-m2.7:cloud", provider="ollama", name="MiniMax M2.7 (Cloud)",
            input_cost_per_mtok=0.0, output_cost_per_mtok=0.0,
            avg_latency_ms=800, supports_tools=True, supports_stream=True,
            provider_tier="budget",
        ),
        "llama3:70b": ModelSpec(
            id="llama3:70b", provider="ollama", name="Llama3 70B (Local)",
            input_cost_per_mtok=0.0, output_cost_per_mtok=0.0,
            avg_latency_ms=5000, supports_tools=True, supports_stream=True,
            provider_tier="budget",
        ),
        # Anthropic
        "claude-sonnet-4": ModelSpec(
            id="claude-sonnet-4", provider="anthropic", name="Claude Sonnet 4",
            input_cost_per_mtok=3.0, output_cost_per_mtok=15.0,
            avg_latency_ms=1800, supports_tools=True, supports_stream=True,
            provider_tier="premium",
        ),
        "claude-3-5-haiku": ModelSpec(
            id="claude-3-5-haiku", provider="anthropic", name="Claude 3.5 Haiku",
            input_cost_per_mtok=0.8, output_cost_per_mtok=4.0,
            avg_latency_ms=1200, supports_tools=True, supports_stream=True,
        ),
    }

    # Strategy-specific preferences
    COST_OPTIMAL_FIRST = ["minimax-m2.7:cloud", "llama3:70b", "gpt-5.4-mini"]
    LATENCY_OPTIMAL_FIRST = ["minimax-m2.7:cloud", "claude-3-5-haiku", "gpt-5.2"]
    PREMIUM_FIRST = ["claude-sonnet-4", "gpt-5.4", "gpt-5.2"]

    @classmethod
    def get(cls, model_id: str) -> ModelSpec | None:
        return cls.MODELS.get(model_id)

    @classmethod
    def list_all(cls) -> list[ModelSpec]:
        return list(cls.MODELS.values())

    @classmethod
    def list_by_provider(cls, provider: str) -> list[ModelSpec]:
        return [m for m in cls.MODELS.values() if m.provider == provider]

    @classmethod
    def for_strategy(cls, strategy: RoutingStrategy) -> list[str]:
        if strategy == RoutingStrategy.COST_OPTIMAL:
            return cls.COST_OPTIMAL_FIRST
        if strategy == RoutingStrategy.LATENCY_OPTIMAL:
            return cls.LATENCY_OPTIMAL_FIRST
        if strategy == RoutingStrategy.FALLBACK:
            return cls.PREMIUM_FIRST  # fallback to best quality
        return list(cls.MODELS.keys())


# ── Routing strategy ──────────────────────────────────────────────────────────

class RoutingStrategy(Enum):
    COST_OPTIMAL = "cost_optimal"      # cheapest that meets requirements
    LATENCY_OPTIMAL = "latency_optimal" # fastest response
    LOAD_BALANCED = "load_balanced"     # distribute load across providers
    ROUND_ROBIN = "round_robin"         # simple rotation
    FALLBACK = "fallback"               # highest capability, last resort


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
    alternatives: list[str]  # ordered list of fallback model IDs
    routing_reason: str
    timestamp: float = field(default_factory=time.time)


# ── Token tracker ─────────────────────────────────────────────────────────────

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
    """
    Tracks token usage and cost per model/task.
    Retention: last 5000 records.
    """

    def __init__(self, max_records: int = 5000) -> None:
        self._records: list[TokenRecord] = []
        self._max_records = max_records
        self._totals: dict[str, dict[str, Any]] = {}  # model_id -> {input_tok, output_tok, cost, calls}

    def record(self, model_id: str, task_type: str,
               input_tok: int, output_tok: int,
               cost_usd: float, latency_ms: float) -> None:
        rec = TokenRecord(model_id, task_type, input_tok, output_tok, cost_usd, latency_ms, time.time())
        self._records.append(rec)
        if len(self._records) > self._max_records:
            self._records.pop(0)

        # Update totals
        if model_id not in self._totals:
            self._totals[model_id] = {"input_tok": 0, "output_tok": 0, "cost_usd": 0.0, "calls": 0, "total_latency_ms": 0.0}
        t = self._totals[model_id]
        t["input_tok"] += input_tok
        t["output_tok"] += output_tok
        t["cost_usd"] += cost_usd
        t["calls"] += 1
        t["total_latency_ms"] += latency_ms

    def total_cost(self, model_id: str | None = None) -> float:
        if model_id:
            return self._totals.get(model_id, {}).get("cost_usd", 0.0)
        return sum(t["cost_usd"] for t in self._totals.values())

    def total_tokens(self, model_id: str | None = None) -> tuple[int, int]:
        if model_id:
            t = self._totals.get(model_id, {})
            return t.get("input_tok", 0), t.get("output_tok", 0)
        in_tot = sum(t["input_tok"] for t in self._totals.values())
        out_tot = sum(t["output_tok"] for t in self._totals.values())
        return in_tot, out_tot

    def stats(self) -> dict[str, Any]:
        if not self._totals:
            return {"total_cost": 0.0, "total_calls": 0, "by_model": {}}
        return {
            "total_cost": sum(t["cost_usd"] for t in self._totals.values()),
            "total_calls": sum(t["calls"] for t in self._totals.values()),
            "by_model": {
                mid: {
                    "cost_usd": t["cost_usd"],
                    "calls": t["calls"],
                    "avg_latency_ms": round(t["total_latency_ms"] / t["calls"], 2) if t["calls"] else 0,
                    "input_tok": t["input_tok"],
                    "output_tok": t["output_tok"],
                }
                for mid, t in self._totals.items()
            }
        }


# ── Provider Router ───────────────────────────────────────────────────────────

class ProviderRouter:
    """
    Routes model requests using configurable strategies.

    Usage:
        router = ProviderRouter()
        decision = router.route(RouteRequest(
            prompt="research query about Indian stocks",
            requires_tools=True,
            strategy=RoutingStrategy.COST_OPTIMAL
        ))
        print(f"Use {decision.model_id} (est. cost: ${decision.estimated_cost:.4f})")
    """

    def __init__(self) -> None:
        self._tracker = TokenTracker()
        self._round_robin_index: dict[str, int] = {}

    def route(self, request: RouteRequest) -> RouteDecision:
        """Select best model for a request using the specified strategy."""
        candidates = self._filter_candidates(request)

        if not candidates:
            # No candidate meets requirements — fall back to cheapest available
            fallback = list(ProviderModels.MODELS.values())[0]
            return RouteDecision(
                model_id=fallback.id,
                provider=fallback.provider,
                strategy_used=request.strategy,
                estimated_cost=0.0,
                estimated_latency_ms=fallback.avg_latency_ms,
                alternatives=[],
                routing_reason="no candidates met requirements; default fallback",
            )

        model_id = self._select_model(candidates, request)
        model = ProviderModels.get(model_id)
        if model is None:
            model = list(ProviderModels.MODELS.values())[0]

        # Build alternatives list (remaining candidates in cost order)
        alternatives = [m.id for m in sorted(candidates, key=lambda m: m.cost_for_tokens(1000, 250))
                       if m.id != model_id][:3]

        reason = self._routing_reason(model, request)

        return RouteDecision(
            model_id=model_id,
            provider=model.provider,
            strategy_used=request.strategy,
            estimated_cost=model.cost_estimate(len(request.prompt)),
            estimated_latency_ms=model.avg_latency_ms,
            alternatives=alternatives,
            routing_reason=reason,
        )

    def _filter_candidates(self, request: RouteRequest) -> list[ModelSpec]:
        """Filter models that meet requirements."""
        candidates = []
        for model in ProviderModels.MODELS.values():
            if request.requires_tools and not model.supports_tools:
                continue
            if request.requires_stream and not model.supports_stream:
                continue
            if model.avg_latency_ms > request.max_latency_ms:
                continue
            if request.max_cost is not None:
                est = model.cost_estimate(len(request.prompt))
                if est > request.max_cost:
                    continue
            if request.preferred_provider and model.provider != request.preferred_provider:
                continue
            candidates.append(model)
        return candidates

    def _select_model(self, candidates: list[ModelSpec], request: RouteRequest) -> str:
        """Apply routing strategy to select from candidates."""
        strategy = request.strategy

        if strategy == RoutingStrategy.COST_OPTIMAL:
            return min(candidates, key=lambda m: m.cost_estimate(len(request.prompt))).id

        if strategy == RoutingStrategy.LATENCY_OPTIMAL:
            return min(candidates, key=lambda m: m.avg_latency_ms).id

        if strategy == RoutingStrategy.ROUND_ROBIN:
            # Simple round-robin across candidates
            key = request.task_type
            idx = self._round_robin_index.get(key, 0)
            selected = candidates[idx % len(candidates)].id
            self._round_robin_index[key] = idx + 1
            return selected

        if strategy == RoutingStrategy.FALLBACK:
            # Best quality first
            return max(candidates, key=lambda m: (
                0 if m.provider_tier == "premium" else 1,
                m.input_cost_per_mtok,
            )).id

        if strategy == RoutingStrategy.LOAD_BALANCED:
            # Pick least-used model by call count
            stats = self._tracker.stats()
            return min(candidates, key=lambda m: stats.get("by_model", {}).get(m.id, {}).get("calls", 0)).id

        # Default: cost optimal
        return min(candidates, key=lambda m: m.cost_estimate(len(request.prompt))).id

    def _routing_reason(self, model: ModelSpec, request: RouteRequest) -> str:
        s = request.strategy.value
        cost = model.cost_estimate(len(request.prompt))
        return (
            f"strategy={s}, picked {model.id} (${cost:.4f} est., "
            f"{model.avg_latency_ms:.0f}ms, provider={model.provider})"
        )

    def record_usage(self, model_id: str, task_type: str,
                     input_tok: int, output_tok: int,
                     latency_ms: float) -> None:
        model = ProviderModels.get(model_id)
        cost = model.cost_for_tokens(input_tok, output_tok) if model else 0.0
        self._tracker.record(model_id, task_type, input_tok, output_tok, cost, latency_ms)

    def stats(self) -> dict[str, Any]:
        return self._tracker.stats()


# ── Route ledger ──────────────────────────────────────────────────────────────

class RouteLedger:
    """
    Audit log of all routing decisions.
    Retention: last 1000 entries.
    """

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
        if not self._entries:
            return {"total": 0, "by_strategy": {}, "by_model": {}}
        by_strategy: dict[str, int] = {}
        by_model: dict[str, int] = {}
        for e in self._entries:
            by_strategy[e.strategy_used.value] = by_strategy.get(e.strategy_used.value, 0) + 1
            by_model[e.model_id] = by_model.get(e.model_id, 0) + 1
        return {"total": len(self._entries), "by_strategy": by_strategy, "by_model": by_model}


# ── Convenience API ───────────────────────────────────────────────────────────

_router = ProviderRouter()
_ledger = RouteLedger()


def route_model(request: RouteRequest) -> RouteDecision:
    """Top-level routing API."""
    decision = _router.route(request)
    _ledger.record(decision)
    return decision


def record_call(model_id: str, task_type: str,
               input_tok: int, output_tok: int,
               latency_ms: float) -> None:
    """Record actual usage for cost tracking."""
    _router.record_usage(model_id, task_type, input_tok, output_tok, latency_ms)


def routing_stats() -> dict[str, Any]:
    """Return routing + cost statistics."""
    return {
        "tracker": _router.stats(),
        "ledger": _ledger.stats(),
    }


def list_available_models() -> list[ModelSpec]:
    """Return all registered models."""
    return ProviderModels.list_all()


def get_model(model_id: str) -> ModelSpec | None:
    return ProviderModels.get(model_id)