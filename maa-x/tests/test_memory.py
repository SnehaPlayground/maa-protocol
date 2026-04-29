"""Tests for maa_x.memory — correct AgentDB search semantics."""

import pytest
from maa_x.memory import AgentDB, SimpleHNSW


def test_hnsw_insert_search():
    index = SimpleHNSW(dim=4, m=2)
    index.insert(0, [0.1, 0.2, 0.3, 0.4])
    index.insert(1, [0.9, 0.8, 0.7, 0.6])
    index.insert(2, [0.05, 0.15, 0.25, 0.35])  # close to id=0

    results = index.search([0.12, 0.22, 0.32, 0.42], k=2)
    assert len(results) == 2
    ids = [r[0] for r in results]
    assert 0 in ids  # should find similar to 0
    assert all(isinstance(r[0], int) and isinstance(r[1], float) for r in results)


def test_hnsw_empty():
    index = SimpleHNSW(dim=4)
    assert index.search([0.1]*4, k=3) == []


def test_agentdb_store_and_search_returns_real_memory_ids():
    db = AgentDB(":memory:", dim=4)
    v1 = [0.1, 0.2, 0.3, 0.4]
    v2 = [0.9, 0.8, 0.7, 0.6]

    mid1 = db.store("content A", v1)
    mid2 = db.store("content B", v2)
    mid3 = db.store("content C", v1)  # same vector as A

    # Query closer to v1 -> should return A and C first
    results = db.search(v1, k=3, namespace="default")

    assert len(results) > 0
    # Every result must have a real UUID memory_id
    assert all("memory_id" in r for r in results)
    # memory_ids must be actual stored UUIDs, not fake mem_0, mem_1
    assert all(len(r["memory_id"]) == 36 for r in results)  # UUID format
    assert mid1 in [r["memory_id"] for r in results]
    assert mid3 in [r["memory_id"] for r in results]


def test_agentdb_search_ignores_other_namespace():
    db = AgentDB(":memory:", dim=4)
    v1 = [0.1, 0.2, 0.3, 0.4]
    v2 = [0.9, 0.8, 0.7, 0.6]

    db.store("ns1 content", v1, namespace="ns1")
    db.store("ns2 content", v2, namespace="ns2")

    results_ns1 = db.search(v1, k=5, namespace="ns1")
    assert all(r["memory_id"] is not None for r in results_ns1)
    # Should not contain ns2 content
    assert not any("ns2 content" in r.get("content", "") for r in results_ns1)


def test_agentdb_get():
    db = AgentDB(":memory:", dim=4)
    v = [0.1]*4
    mid = db.store("test content", v)

    entry = db.get(mid)
    assert entry is not None
    assert entry["memory_id"] == mid
    assert entry["content"] == "test content"


def test_agentdb_update():
    db = AgentDB(":memory:", dim=4)
    mid = db.store("original", [0.1, 0.2, 0.3, 0.4])

    ok = db.update(mid, content="updated", metadata={"key": "value"})
    assert ok

    entry = db.get(mid)
    assert entry["content"] == "updated"
    assert entry["metadata"]["key"] == "value"


def test_agentdb_delete():
    db = AgentDB(":memory:", dim=4)
    mid = db.store("to delete", [0.1, 0.2, 0.3, 0.4])
    ok = db.delete(mid)
    assert ok
    assert db.get(mid) is None


def test_agentdb_namespace_list():
    db = AgentDB(":memory:", dim=4)
    db.store("a", [0.1]*4, namespace="alpha")
    db.store("b", [0.2]*4, namespace="beta")
    db.store("c", [0.3]*4, namespace="alpha")

    namespaces = db.list_namespaces()
    assert "alpha" in namespaces
    assert "beta" in namespaces
    assert "gamma" not in namespaces


def test_agentdb_count():
    db = AgentDB(":memory:", dim=4)
    db.store("a", [0.1]*4, namespace="x")
    db.store("b", [0.2]*4, namespace="x")
    db.store("c", [0.3]*4, namespace="y")

    assert db.count() == 3
    assert db.count(namespace="x") == 2
    assert db.count(namespace="y") == 1