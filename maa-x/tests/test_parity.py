"""Parity smoke tests against key Maa Protocol surfaces."""

from maa_x.memory import PatternMemory, embed_text, search_patterns, store_pattern, SemanticRouter
from maa_x.provider_router import RouteRequest, RoutingStrategy, route_model, routing_stats, list_available_models
from maa_x.plugins import discover_plugins, save_registry, load_registry, get_registry
from maa_x.mcp import list_tools, list_preset_modes, get_tool_group, get_tool


def test_memory_semantic_pattern_store_and_search(tmp_path):
    path = store_pattern("research", "alpha", "This is an Indian equities research memo")
    assert path.exists()
    results = search_patterns("equities research", task_type="research", top_k=3)
    assert len(results) >= 1
    assert results[0].task_type == "research"


def test_semantic_router():
    router = SemanticRouter()
    router.register("market-brief", "generate market brief for trading day")
    router.register("research", "perform deep research on topic")
    result = router.route("I need a market outlook for tomorrow")
    assert result.decision in ("reuse", "adapt", "fresh")


def test_provider_router_parity():
    decision = route_model(RouteRequest(prompt="research Indian markets", strategy=RoutingStrategy.COST_OPTIMAL))
    assert decision.model_id
    assert decision.provider
    stats = routing_stats()
    assert "tracker" in stats
    assert len(list_available_models()) >= 1


def test_plugin_registry_persistence(tmp_path):
    path = tmp_path / "registry.json"
    save_registry(path)
    assert path.exists()
    load_registry(path)
    assert get_registry().stats()["total"] >= 3
    assert isinstance(discover_plugins(), list)


def test_mcp_parity_exports():
    assert len(list_tools()) >= 1
    assert len(list_preset_modes()) >= 1
    assert isinstance(get_tool_group("develop"), list)
    assert get_tool("swarm_init") is not None
