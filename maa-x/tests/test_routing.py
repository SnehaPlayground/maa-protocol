"""Tests for maa_x routing module."""

import pytest
from maa_x.routing import (
    CapabilityRouting,
    CostRouting,
    LatencyRouting,
    ModelSpec,
    MultiProviderRouter,
    RouteLedger,
)


def test_model_spec_defaults():
    model = ModelSpec(name="test", provider="test-provider")
    assert model.name == "test"
    assert model.context_window == 128_000


def test_latency_routing():
    router = MultiProviderRouter(strategy="latency")
    result = router.route({})
    assert result is not None
    assert result.name in [m.name for m in router.models]


def test_cost_routing():
    router = MultiProviderRouter(strategy="cost")
    result = router.route({})
    assert result is not None


def test_capability_routing():
    router = MultiProviderRouter(strategy="capability")
    result = router.route({"required_capabilities": ["chat"]})
    assert result is not None


def test_route_ledger_records():
    ledger = RouteLedger()
    model = ModelSpec(name="test", provider="test")
    ledger.record({}, model, "LatencyRouting")
    assert len(ledger.entries) == 1


def test_multi_provider_list_models():
    router = MultiProviderRouter()
    models = router.list_models()
    assert len(models) >= 1


def test_unknown_strategy_defaults_to_latency():
    router = MultiProviderRouter(strategy="unknown_strategy")
    result = router.route({})
    assert result is not None  # should fall back to latency