"""Tests for maa_x.plugins module."""

import pytest
from maa_x.plugins import (
    PluginRegistry,
    PluginSpec,
    PluginState,
    PluginKind,
    get_registry,
)


def test_plugin_registry_register():
    registry = PluginRegistry()
    spec = PluginSpec(name="test-plugin", version="1.0.0", kind=PluginKind.ADDON)
    registry.register_plugin(spec)
    assert registry.get_plugin("test-plugin") is not None


def test_plugin_registry_enable_disable():
    registry = PluginRegistry()
    spec = PluginSpec(
        name="test-enable", version="1.0.0", kind=PluginKind.CORE,
        entrypoint=None,  # no file, just in-memory
    )
    registry.register_plugin(spec)
    ok = registry.enable_plugin("test-enable")
    assert ok
    assert registry.get_plugin("test-enable").is_loaded()

    registry.disable_plugin("test-enable")
    assert not registry.get_plugin("test-enable").is_loaded()


def test_plugin_registry_list_filtered():
    registry = PluginRegistry()
    registry.register_plugin(PluginSpec(name="p1", version="1.0", kind=PluginKind.CORE))
    registry.register_plugin(PluginSpec(name="p2", version="1.0", kind=PluginKind.ADDON))
    all_plugins = registry.list_plugins()
    assert len(all_plugins) >= 2
    core = registry.list_plugins(kind=PluginKind.CORE)
    assert all(p.kind == PluginKind.CORE for p in core)


def test_plugin_registry_stats():
    registry = PluginRegistry()
    registry.register_plugin(PluginSpec(name="stat-test", version="1.0", kind=PluginKind.ADDON))
    stats = registry.stats()
    assert "total" in stats
    assert "by_state" in stats
    assert "loaded" in stats


def test_global_registry_has_core_plugins():
    registry = get_registry()
    core = registry.list_plugins(kind=PluginKind.CORE)
    assert len(core) >= 3  # guidance, security, routing