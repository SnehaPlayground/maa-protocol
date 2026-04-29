"""Completion tests for remaining Maa-X platform modules."""

from maa_x.guidance import compile_guidance, enforce_guidance, inspect_intent, GateAction
from maa_x.hooks import register, fire_first, HookAction, HookPhase, HookResult, HookContext, list_hooks
from maa_x.marketplace import PluginStore, Review, create_listing, search_plugins
from maa_x.observability import MetricsCollector, TimedBlock
from maa_x.persistence import PostgresBackend


def test_guidance_blocks_destructive_ops():
    bundle, results, approved = enforce_guidance("code-edit", {"command": "rm -rf /tmp/x", "tools_used": ["exec"]})
    assert any(r.action == GateAction.BLOCK for r in results)
    assert approved is False


def test_guidance_inspect_intent():
    info = inspect_intent("please prepare a market outlook")
    assert "intent" in info
    assert "risk" in info


def test_hooks_registration_and_fire():
    def handler(ctx: HookContext) -> HookResult:
        return HookResult(HookAction.MODIFY, ctx.hook_name, "modified", {"x": 1})
    register("pre-task", handler, phase=HookPhase.CORE, priority=0)
    result = fire_first("pre-task", data={"task_prompt": "hello"})
    assert result.action in (HookAction.MODIFY, HookAction.PROCEED)
    assert "pre-task" in list_hooks()


def test_marketplace_listing_and_search():
    store = PluginStore()
    listing = store.get_by_name("alpha-plugin", "1.0.0")
    if listing is None:
        listing = store.create_listing(name="alpha-plugin", version="1.0.0", category="research", description="market research plugin", author="maa")
    store.add_review(listing.id, Review(id="r1", author="maa", rating=5, title="great", body="works"))
    results = store.search("market research")
    assert any(r.id == listing.id for r in results)
    assert search_plugins("market", limit=10)


def test_observability_persistence(tmp_path):
    path = tmp_path / "metrics.json"
    m = MetricsCollector(path)
    with TimedBlock(m, "demo"):
        pass
    m.increment("calls")
    m.save()
    m2 = MetricsCollector(path)
    assert m2.counts.get("calls") == 1
    assert "summary" in m2.export_json()
    assert "Dashboard" in m2.dashboard()


def test_postgres_backend_compat(tmp_path):
    db = PostgresBackend(dsn=str(tmp_path / "pgcompat.db"))
    rec = db.create_approval("t1", "act", "hash", "me", "why", 0.5)
    assert db.get_approval(rec.approval_id) is not None
