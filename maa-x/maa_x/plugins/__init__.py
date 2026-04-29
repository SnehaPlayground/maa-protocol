"""Plugins module — full lifecycle management, mirroring original maa_protocol/plugins.py."""

from __future__ import annotations

import importlib.util
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from maa_x.persistence.base import SQLiteBackend

PLUGIN_ROOT = Path("/tmp/maa-x-plugins")
MANIFEST_NAME = "manifest.json"


class PluginState(Enum):
    REGISTERED = "registered"
    ENABLED = "enabled"
    DISABLED = "disabled"
    BROKEN = "broken"


class PluginKind(Enum):
    CORE = "core"
    ADDON = "addon"
    DEV = "dev"


@dataclass
class PluginSpec:
    name: str
    version: str
    kind: PluginKind
    author: str = "unknown"
    description: str = ""
    entrypoint: str | None = None
    dependencies: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    exposed_apis: list[str] = field(default_factory=list)
    config_schema: dict[str, Any] = field(default_factory=dict)
    state: PluginState = PluginState.REGISTERED
    loaded_at: float | None = None
    error: str | None = None

    def is_loaded(self) -> bool:
        return self.state == PluginState.ENABLED and self.loaded_at is not None


class PluginRegistry:
    def __init__(self, persistence: SQLiteBackend | None = None) -> None:
        self._plugins: dict[str, PluginSpec] = {}
        self._modules: dict[str, Any] = {}
        self._hooks: dict[str, list[Callable]] = {}
        self._config: dict[str, dict[str, Any]] = {}
        self.persistence = persistence or SQLiteBackend()

    def register_plugin(self, spec: PluginSpec) -> None:
        self._plugins[spec.name] = spec
        self._hooks.setdefault(spec.name, [])

    def get_plugin(self, name: str) -> PluginSpec | None:
        return self._plugins.get(name)

    def list_plugins(self, kind: PluginKind | None = None, state: PluginState | None = None) -> list[PluginSpec]:
        results = list(self._plugins.values())
        if kind:
            results = [p for p in results if p.kind == kind]
        if state:
            results = [p for p in results if p.state == state]
        return results

    def enable_plugin(self, name: str, config: dict[str, Any] | None = None) -> bool:
        spec = self._plugins.get(name)
        if spec is None:
            return False
        for dep in spec.dependencies:
            if not self._plugins.get(dep):
                spec.error = f"missing dependency: {dep}"
                spec.state = PluginState.BROKEN
                return False
        if spec.entrypoint:
            try:
                self._modules[name] = self._load_module(name, spec.entrypoint)
            except Exception as e:
                spec.error = f"load failed: {e}"
                spec.state = PluginState.BROKEN
                return False
        spec.loaded_at = time.time()
        spec.state = PluginState.ENABLED
        if config:
            self._config[name] = config
        return True

    def disable_plugin(self, name: str) -> None:
        spec = self._plugins.get(name)
        if spec is None:
            return
        self._modules.pop(name, None)
        spec.loaded_at = None
        spec.state = PluginState.DISABLED

    def install_plugin(self, name: str) -> bool:
        manifest_path = PLUGIN_ROOT / name / MANIFEST_NAME
        if not manifest_path.exists():
            return False
        try:
            manifest = json.loads(manifest_path.read_text())
            spec = PluginSpec(
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
            )
            self.register_plugin(spec)
            return True
        except Exception:
            return False

    def uninstall_plugin(self, name: str) -> None:
        self.disable_plugin(name)
        self._plugins.pop(name, None)
        self._config.pop(name, None)
        self._hooks.pop(name, None)

    def save_registry(self, path: Path | None = None) -> None:
        path = path or (PLUGIN_ROOT / "registry.json")
        PLUGIN_ROOT.mkdir(parents=True, exist_ok=True)
        data = {
            "plugins": [
                {
                    "name": p.name,
                    "version": p.version,
                    "kind": p.kind.value,
                    "author": p.author,
                    "description": p.description,
                    "entrypoint": p.entrypoint,
                    "dependencies": p.dependencies,
                    "permissions": p.permissions,
                    "exposed_apis": p.exposed_apis,
                    "config_schema": p.config_schema,
                }
                for p in self._plugins.values()
            ],
            "config": self._config,
        }
        path.write_text(json.dumps(data, indent=2))

    def load_registry(self, path: Path | None = None) -> None:
        path = path or (PLUGIN_ROOT / "registry.json")
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text())
            for manifest in data.get("plugins", []):
                self.register_plugin(PluginSpec(
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
                ))
            self._config = data.get("config", {})
        except Exception:
            pass

    def discover_plugins(self) -> list[str]:
        discovered = []
        PLUGIN_ROOT.mkdir(parents=True, exist_ok=True)
        for entry in PLUGIN_ROOT.iterdir():
            if entry.is_dir() and (entry / MANIFEST_NAME).exists() and entry.name not in self._plugins:
                discovered.append(entry.name)
        return discovered

    def _load_module(self, name: str, entrypoint: str) -> Any:
        path = Path(entrypoint)
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load plugin module: {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def register_hook(self, plugin_name: str, callback: Callable) -> None:
        self._hooks.setdefault(plugin_name, []).append(callback)

    def invoke_hook(self, plugin_name: str, hook_name: str, *args: Any, **kwargs: Any) -> list[Any]:
        results = []
        for cb in self._hooks.get(plugin_name, []):
            try:
                results.append(cb(*args, **kwargs))
            except Exception:
                pass
        return results

    def stats(self) -> dict[str, Any]:
        by_state: dict[str, int] = {}
        by_kind: dict[str, int] = {}
        for p in self._plugins.values():
            by_state[p.state.value] = by_state.get(p.state.value, 0) + 1
            by_kind[p.kind.value] = by_kind.get(p.kind.value, 0) + 1
        return {"total": len(self._plugins), "by_state": by_state, "by_kind": by_kind, "loaded": sum(1 for p in self._plugins.values() if p.is_loaded())}


def _register_core_plugins(registry: PluginRegistry) -> None:
    core_plugins = [
        PluginSpec(name="maa:guidance", version="1.0.0", kind=PluginKind.CORE, author="MAA", description="Guidance and enforcement framework", exposed_apis=["compile_guidance", "enforce_guidance"]),
        PluginSpec(name="maa:security", version="1.0.0", kind=PluginKind.CORE, author="MAA", description="Security threat engine", exposed_apis=["scan_content", "redact_pii"]),
        PluginSpec(name="maa:routing", version="1.0.0", kind=PluginKind.CORE, author="MAA", description="Provider routing and cost optimization", exposed_apis=["route_model", "record_call"]),
    ]
    for spec in core_plugins:
        spec.state = PluginState.ENABLED
        spec.loaded_at = time.time()
        registry.register_plugin(spec)


_global_registry = PluginRegistry()
_register_core_plugins(_global_registry)


def get_registry() -> PluginRegistry:
    return _global_registry


def get_plugin(name: str) -> PluginSpec | None:
    return _global_registry.get_plugin(name)


def enable_plugin(name: str, config: dict[str, Any] | None = None) -> bool:
    return _global_registry.enable_plugin(name, config)


def disable_plugin(name: str) -> None:
    _global_registry.disable_plugin(name)


def list_plugins(kind: PluginKind | None = None, state: PluginState | None = None) -> list[PluginSpec]:
    return _global_registry.list_plugins(kind=kind, state=state)


def discover_plugins() -> list[str]:
    return _global_registry.discover_plugins()


def install_plugin(name: str) -> bool:
    return _global_registry.install_plugin(name)


def uninstall_plugin(name: str) -> None:
    _global_registry.uninstall_plugin(name)


def save_registry(path: Path | None = None) -> None:
    _global_registry.save_registry(path)


def load_registry(path: Path | None = None) -> None:
    _global_registry.load_registry(path)


__all__ = [
    "PluginState", "PluginKind", "PluginSpec", "PluginRegistry", "PLUGIN_ROOT", "MANIFEST_NAME",
    "get_registry", "get_plugin", "enable_plugin", "disable_plugin", "list_plugins", "discover_plugins",
    "install_plugin", "uninstall_plugin", "save_registry", "load_registry",
]
