"""
MAA Protocol — Plugin Infrastructure
=====================================
Shared plugin system for MAA Protocol components.

Plugin lifecycle: discover → register → validate → enable/disable → uninstall
Plugin types: core (built-in), addon (installed), dev (unverified)

Components:
- PluginSpec — plugin metadata (name, version, kind, author, deps, permissions)
- PluginState enum (REGISTERED/ENABLED/DISABLED/BROKEN)
- PluginRegistry — central plugin store with lifecycle management
- PluginValidator — validates plugin structure and dependencies before loading
- discover_plugins() — scan directories for installable plugins
- load_plugin() / unload_plugin() — runtime plugin load/unload
- Built-in core plugins registered at startup

Usage:
    registry = PluginRegistry()
    registry.register_plugin(PluginSpec(...))
    registry.enable_plugin("my-plugin")
    plugin = registry.get_plugin("my-plugin")
    if plugin and plugin.is_loaded:
        plugin.invoke("on_task_start", context)
"""

from __future__ import annotations

import importlib.util
import importlib
import json
import os
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any, Callable

# ── Paths ──────────────────────────────────────────────────────────────────────

WORKSPACE = Path("/root/.openclaw/workspace")
PLUGIN_ROOT = WORKSPACE / "maa_plugins"
PLUGIN_ROOT.mkdir(parents=True, exist_ok=True)

MANIFEST_NAME = "plugin_manifest.json"

# ── Plugin state ──────────────────────────────────────────────────────────────

class PluginState(Enum):
    REGISTERED = "registered"   # known but not active
    ENABLED = "enabled"         # active and loaded
    DISABLED = "disabled"       # known but inactive
    BROKEN = "broken"           # loaded but failed


class PluginKind(Enum):
    CORE = "core"       # built-in MAA components (guidance, hooks, security, etc.)
    ADDON = "addon"     # installed third-party plugins
    DEV = "dev"         # development/testing plugins


# ── Plugin specification ───────────────────────────────────────────────────────

@dataclass
class PluginSpec:
    name: str
    version: str
    kind: PluginKind
    author: str = "unknown"
    description: str = ""
    entrypoint: str | None = None        # path to plugin module
    dependencies: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)  # e.g. ["filesystem", "network"]
    exposed_apis: list[str] = field(default_factory=list)  # e.g. ["scan_content", "route_model"]
    config_schema: dict[str, Any] = field(default_factory=dict)
    state: PluginState = PluginState.REGISTERED
    loaded_at: float | None = None
    error: str | None = None

    def is_loaded(self) -> bool:
        return self.state == PluginState.ENABLED and self.loaded_at is not None

    def to_manifest(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "kind": self.kind.value,
            "author": self.author,
            "description": self.description,
            "entrypoint": self.entrypoint,
            "dependencies": self.dependencies,
            "permissions": self.permissions,
            "exposed_apis": self.exposed_apis,
            "config_schema": self.config_schema,
        }

    @classmethod
    def from_manifest(cls, manifest: dict[str, Any]) -> PluginSpec:
        return cls(
            name=manifest["name"],
            version=manifest.get("version", "1.0.0"),
            kind=PluginKind(manifest.get("kind", "addon")),
            author=manifest.get("author", "unknown"),
            description=manifest.get("description", ""),
            entrypoint=manifest.get("entrypoint"),
            dependencies=manifest.get("dependencies", []),
            permissions=manifest.get("permissions", []),
            exposed_apis=manifest.get("exposed_apis", []),
            config_schema=manifest.get("config_schema", {}),
            state=PluginState.REGISTERED,
        )


# ── Plugin registry ───────────────────────────────────────────────────────────

class PluginRegistry:
    """
    Central plugin store and lifecycle manager.

    Tracks all known plugins, their state, and provides
    enable/disable/load/unload operations.
    """

    def __init__(self) -> None:
        self._plugins: dict[str, PluginSpec] = {}
        self._modules: dict[str, Any] = {}  # name -> loaded module
        self._hooks: dict[str, list[Callable]] = {}  # hook_name -> [callbacks]
        self._config: dict[str, dict[str, Any]] = {}  # plugin_name -> config

    # ── Registration ──────────────────────────────────────────────────────────

    def register_plugin(self, spec: PluginSpec) -> None:
        """Register a plugin. Overwrites if same name."""
        self._plugins[spec.name] = spec
        if spec.name not in self._hooks:
            self._hooks[spec.name] = []

    def get_plugin(self, name: str) -> PluginSpec | None:
        return self._plugins.get(name)

    def list_plugins(self, kind: PluginKind | None = None,
                     state: PluginState | None = None) -> list[PluginSpec]:
        results = list(self._plugins.values())
        if kind:
            results = [p for p in results if p.kind == kind]
        if state:
            results = [p for p in results if p.state == state]
        return results

    def is_registered(self, name: str) -> bool:
        return name in self._plugins

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def enable_plugin(self, name: str, config: dict[str, Any] | None = None) -> bool:
        """
        Enable a plugin: validate, load module, mark ENABLED.
        Returns True on success, False on failure.
        """
        spec = self._plugins.get(name)
        if spec is None:
            return False

        # Validate dependencies
        for dep in spec.dependencies:
            if not self.is_registered(dep):
                spec.error = f"missing dependency: {dep}"
                spec.state = PluginState.BROKEN
                return False

        # Load module if entrypoint specified
        if spec.entrypoint:
            try:
                module = self._load_module(name, spec.entrypoint)
                self._modules[name] = module
            except Exception as e:
                spec.error = f"load failed: {e}"
                spec.state = PluginState.BROKEN
                return False

        spec.loaded_at = time.time()
        spec.state = PluginState.ENABLED
        spec.error = None
        if config:
            self._config[name] = config

        return True

    def disable_plugin(self, name: str) -> None:
        """Disable a plugin, unload module, mark DISABLED."""
        spec = self._plugins.get(name)
        if spec is None:
            return

        if name in self._modules:
            self._modules.pop(name)

        spec.loaded_at = None
        spec.state = PluginState.DISABLED

    def uninstall_plugin(self, name: str) -> None:
        """Remove a plugin entirely."""
        self.disable_plugin(name)
        self._plugins.pop(name, None)
        self._config.pop(name, None)
        self._hooks.pop(name, None)

    # ── Module loading ────────────────────────────────────────────────────────

    def _load_module(self, name: str, entrypoint: str) -> Any:
        """Load a plugin module from a file path."""
        path = Path(entrypoint)
        if not path.is_absolute():
            path = PLUGIN_ROOT / name / entrypoint

        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load plugin module: {path}")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def get_module(self, name: str) -> Any | None:
        return self._modules.get(name)

    # ── Configuration ────────────────────────────────────────────────────────

    def configure_plugin(self, name: str, config: dict[str, Any]) -> bool:
        """Update plugin runtime configuration."""
        if name not in self._plugins:
            return False
        self._config[name] = config
        return True

    def get_config(self, name: str) -> dict[str, Any]:
        return self._config.get(name, {})

    # ── Plugin hooks ──────────────────────────────────────────────────────────

    def register_hook(self, plugin_name: str, callback: Callable) -> None:
        """Register a callback for a plugin's hooks."""
        if plugin_name not in self._hooks:
            self._hooks[plugin_name] = []
        self._hooks[plugin_name].append(callback)

    def invoke_hook(self, plugin_name: str, hook_name: str, *args, **kwargs) -> list[Any]:
        """Invoke all callbacks registered for a plugin's hook."""
        results = []
        for callback in self._hooks.get(plugin_name, []):
            try:
                results.append(callback(*args, **kwargs))
            except Exception:
                pass  # don't let one callback break others
        return results

    # ── Discovery ─────────────────────────────────────────────────────────────

    def discover_plugins(self) -> list[str]:
        """Scan plugin directory for installable plugins. Returns list of plugin names."""
        discovered = []
        if not PLUGIN_ROOT.exists():
            return discovered

        for entry in PLUGIN_ROOT.iterdir():
            if not entry.is_dir():
                continue
            manifest_path = entry / MANIFEST_NAME
            if manifest_path.exists():
                try:
                    manifest = json.loads(manifest_path.read_text())
                    name = manifest.get("name", entry.name)
                    if not self.is_registered(name):
                        discovered.append(name)
                except Exception:
                    pass  # skip malformed plugins

        return discovered

    def install_plugin(self, name: str) -> bool:
        """Register a discovered plugin from disk."""
        manifest_path = PLUGIN_ROOT / name / MANIFEST_NAME
        if not manifest_path.exists():
            return False

        try:
            manifest = json.loads(manifest_path.read_text())
            spec = PluginSpec.from_manifest(manifest)
            self.register_plugin(spec)
            return True
        except Exception:
            return False

    # ── Persistence ────────────────────────────────────────────────────────────

    def save_registry(self, path: Path | None = None) -> None:
        """Save plugin registry to JSON."""
        path = path or (PLUGIN_ROOT / "registry.json")
        data = {
            "plugins": [p.to_manifest() for p in self._plugins.values()],
            "config": self._config,
        }
        path.write_text(json.dumps(data, indent=2))

    def load_registry(self, path: Path | None = None) -> None:
        """Load plugin registry from JSON."""
        path = path or (PLUGIN_ROOT / "registry.json")
        if not path.exists():
            return

        try:
            data = json.loads(path.read_text())
            for manifest in data.get("plugins", []):
                spec = PluginSpec.from_manifest(manifest)
                self.register_plugin(spec)
            self._config = data.get("config", {})
        except Exception:
            pass

    # ── Stats ─────────────────────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        by_state: dict[str, int] = {}
        by_kind: dict[str, int] = {}
        for p in self._plugins.values():
            by_state[p.state.value] = by_state.get(p.state.value, 0) + 1
            by_kind[p.kind.value] = by_kind.get(p.kind.value, 0) + 1

        return {
            "total": len(self._plugins),
            "by_state": by_state,
            "by_kind": by_kind,
            "loaded": sum(1 for p in self._plugins.values() if p.is_loaded()),
        }


# ── Plugin validator ───────────────────────────────────────────────────────────

class PluginValidator:
    """
    Validates plugin structure and safety before loading.

    Checks:
    - manifest is well-formed
    - required fields present
    - dependencies are satisfied
    - permissions are allowed (whitelist)
    """

    ALLOWED_PERMISSIONS = {"filesystem", "network", "memory", "security", "routing"}

    def validate(self, spec: PluginSpec) -> tuple[bool, str | None]:
        if not spec.name or len(spec.name) < 2:
            return False, "name too short"

        if not spec.version:
            return False, "version required"

        if not isinstance(spec.kind, PluginKind):
            return False, f"invalid kind: {spec.kind}"

        for perm in spec.permissions:
            if perm not in self.ALLOWED_PERMISSIONS:
                return False, f"disallowed permission: {perm}"

        for dep in spec.dependencies:
            if not dep.replace("_", "").replace("-", "").isalnum():
                return False, f"invalid dependency name: {dep}"

        return True, None


# ── Built-in core plugins ─────────────────────────────────────────────────────

def _register_core_plugins(registry: PluginRegistry) -> None:
    """Register MAA's built-in core plugins at startup."""

    core_plugins = [
        PluginSpec(
            name="maa:guidance",
            version="1.0.0",
            kind=PluginKind.CORE,
            author="MAA",
            description="Guidance and enforcement framework",
            exposed_apis=["compile_guidance", "enforce_guidance"],
        ),
        PluginSpec(
            name="maa:security",
            version="1.0.0",
            kind=PluginKind.CORE,
            author="MAA",
            description="Security threat engine",
            exposed_apis=["scan_content", "apply_threat_policy", "redact_pii", "threat_stats"],
        ),
        PluginSpec(
            name="maa:routing",
            version="1.0.0",
            kind=PluginKind.CORE,
            author="MAA",
            description="Provider routing and cost optimization",
            exposed_apis=["route_model", "record_call", "routing_stats", "list_available_models"],
        ),
        PluginSpec(
            name="maa:memory",
            version="1.0.0",
            kind=PluginKind.CORE,
            author="MAA",
            description="Semantic memory and embeddings",
            exposed_apis=["embed_text", "SemanticMemory", "PatternMemory", "SemanticRouter", "score_decision"],
        ),
        PluginSpec(
            name="maa:hooks",
            version="1.0.0",
            kind=PluginKind.CORE,
            author="MAA",
            description="Hook dispatch engine",
            exposed_apis=["register_hook", "fire_hook", "hook_dispatch"],
        ),
    ]

    for spec in core_plugins:
        spec.state = PluginState.ENABLED
        spec.loaded_at = time.time()
        registry.register_plugin(spec)


# ── Global registry ───────────────────────────────────────────────────────────

_registry = PluginRegistry()
_register_core_plugins(_registry)


# ── Convenience API ───────────────────────────────────────────────────────────

def get_registry() -> PluginRegistry:
    return _registry


def list_plugins(kind: PluginKind | None = None) -> list[PluginSpec]:
    return _registry.list_plugins(kind=kind)


def get_plugin(name: str) -> PluginSpec | None:
    return _registry.get_plugin(name)


def enable_plugin(name: str, config: dict[str, Any] | None = None) -> bool:
    return _registry.enable_plugin(name, config)


def disable_plugin(name: str) -> None:
    _registry.disable_plugin(name)


def install_plugin(name: str) -> bool:
    return _registry.install_plugin(name)


def discover_plugins() -> list[str]:
    return _registry.discover_plugins()


def plugin_stats() -> dict[str, Any]:
    return _registry.stats()