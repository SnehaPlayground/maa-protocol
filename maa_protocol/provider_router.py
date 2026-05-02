"""Maa Protocol parity wrapper for provider routing."""

from maa_x.routing.provider_router import (
    CostOptimizer,
    ModelSpec,
    ProviderModels,
    ProviderRouter,
    RouteDecision,
    RouteLedger,
    RouteRequest,
    RoutingStrategy,
    TokenRecord,
    TokenTracker,
    get_model,
    list_available_models,
    record_call,
    route_model,
    routing_stats,
)

__all__ = [
    "CostOptimizer",
    "ModelSpec",
    "ProviderModels",
    "ProviderRouter",
    "RouteDecision",
    "RouteLedger",
    "RouteRequest",
    "RoutingStrategy",
    "TokenRecord",
    "TokenTracker",
    "get_model",
    "list_available_models",
    "record_call",
    "route_model",
    "routing_stats",
]
