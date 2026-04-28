"""
MAA Protocol — MCP-style Tool Plane
===================================
Practical tool registry and execution metadata plane for MAA.

This is not a full external MCP server. It is a real internal capability layer that:
- registers tools with categories and runtime metadata
- supports tool groups and preset modes
- exposes stdio/http transport declarations as capability metadata
- resolves tool sets for development/review/ops workflows
- provides search/filter/inspection APIs

This moves MAA beyond a flat stub list and gives it an honest, usable MCP-style surface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class MCPTool:
    name: str
    category: str
    description: str
    requires_network: bool = False
    requires_state: bool = False
    status: str = "active"  # active | experimental
    transports: tuple[str, ...] = ("stdio",)
    tags: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "requires_network": self.requires_network,
            "requires_state": self.requires_state,
            "status": self.status,
            "transports": list(self.transports),
            "tags": list(self.tags),
        }


TOOLS: dict[str, MCPTool] = {
    "swarm_init": MCPTool(
        name="swarm_init",
        category="coordination",
        description="Initialize a swarm plan with topology, strategy, and consensus settings",
        requires_state=True,
        tags=("swarm", "init"),
    ),
    "swarm_status": MCPTool(
        name="swarm_status",
        category="monitoring",
        description="Inspect swarm plan and execution summary",
        requires_state=True,
        tags=("swarm", "status"),
    ),
    "agent_spawn": MCPTool(
        name="agent_spawn",
        category="coordination",
        description="Spawn or allocate a child agent role for a managed task",
        requires_state=True,
        tags=("agent", "spawn"),
    ),
    "agent_list": MCPTool(
        name="agent_list",
        category="monitoring",
        description="List active or planned agents in the current coordination context",
        requires_state=True,
        tags=("agent", "list"),
    ),
    "agent_metrics": MCPTool(
        name="agent_metrics",
        category="monitoring",
        description="Return agent-level metrics and participation summaries",
        requires_state=True,
        tags=("agent", "metrics"),
    ),
    "task_orchestrate": MCPTool(
        name="task_orchestrate",
        category="coordination",
        description="Run a multi-step orchestrated task with governance-aware execution",
        requires_state=True,
        tags=("task", "orchestration"),
    ),
    "task_status": MCPTool(
        name="task_status",
        category="monitoring",
        description="Return status snapshot for a managed task",
        requires_state=True,
        tags=("task", "status"),
    ),
    "memory_search": MCPTool(
        name="memory_search",
        category="memory",
        description="Search stored execution patterns or semantic memory",
        requires_state=True,
        tags=("memory", "search"),
    ),
    "memory_store": MCPTool(
        name="memory_store",
        category="memory",
        description="Store a reusable pattern or semantic artifact",
        requires_state=True,
        tags=("memory", "store"),
    ),
    "memory_usage": MCPTool(
        name="memory_usage",
        category="memory",
        description="Inspect memory counts, storage stats, and retention status",
        requires_state=True,
        tags=("memory", "stats"),
    ),
    "hooks_route": MCPTool(
        name="hooks_route",
        category="hooks",
        description="Dispatch routing hooks into the lifecycle system",
        requires_state=True,
        tags=("hooks", "route"),
    ),
    "provider_list": MCPTool(
        name="provider_list",
        category="providers",
        description="List available models/providers with routing metadata",
        tags=("providers", "models"),
    ),
    "provider_route": MCPTool(
        name="provider_route",
        category="providers",
        description="Resolve the best model/provider for a request",
        requires_state=True,
        tags=("providers", "routing"),
    ),
    "plugin_list": MCPTool(
        name="plugin_list",
        category="plugins",
        description="List registered plugins and current state",
        tags=("plugins", "registry"),
    ),
    "claims_list": MCPTool(
        name="claims_list",
        category="claims",
        description="List current claims-based authorization records",
        requires_state=True,
        tags=("claims", "auth"),
    ),
    "security_scan": MCPTool(
        name="security_scan",
        category="security",
        description="Scan content using the MAA threat engine",
        requires_state=True,
        tags=("security", "scan"),
    ),
}


TOOL_GROUPS: dict[str, list[str]] = {
    "create": ["swarm_init", "agent_spawn", "task_orchestrate", "memory_store"],
    "issue": ["task_orchestrate", "task_status", "security_scan"],
    "branch": ["provider_list", "provider_route", "plugin_list"],
    "implement": ["swarm_init", "agent_spawn", "task_orchestrate", "memory_search", "memory_store"],
    "test": ["task_status", "agent_metrics", "security_scan"],
    "fix": ["task_orchestrate", "memory_search", "security_scan"],
    "optimize": ["provider_route", "agent_metrics", "memory_usage"],
    "monitor": ["swarm_status", "agent_list", "agent_metrics", "task_status", "memory_usage"],
    "security": ["security_scan", "claims_list", "task_status"],
    "memory": ["memory_search", "memory_store", "memory_usage"],
    "all": list(TOOLS.keys()),
    "minimal": ["task_orchestrate", "task_status", "memory_search", "provider_route"],
}


PRESET_MODES: dict[str, list[str]] = {
    "develop": ["create", "implement", "test", "fix", "memory"],
    "pr-review": ["branch", "fix", "monitor", "security"],
    "devops": ["create", "monitor", "optimize", "security"],
    "triage": ["issue", "monitor", "fix"],
}


SUPPORTED_TRANSPORTS = ("stdio", "http")


class MCPRegistry:
    def __init__(self) -> None:
        self._tools = dict(TOOLS)
        self._tool_groups = {k: list(v) for k, v in TOOL_GROUPS.items()}
        self._preset_modes = {k: list(v) for k, v in PRESET_MODES.items()}

    def list_tools(self) -> list[str]:
        return sorted(self._tools.keys())

    def get_tool(self, name: str) -> MCPTool | None:
        return self._tools.get(name)

    def list_tool_objects(self) -> list[MCPTool]:
        return [self._tools[k] for k in sorted(self._tools.keys())]

    def list_groups(self) -> list[str]:
        return sorted(self._tool_groups.keys())

    def list_modes(self) -> list[str]:
        return sorted(self._preset_modes.keys())

    def group_tools(self, group: str) -> list[str]:
        return list(self._tool_groups.get(group, []))

    def mode_tools(self, mode: str) -> list[str]:
        groups = self._preset_modes.get(mode, [])
        resolved: list[str] = []
        seen: set[str] = set()
        for group in groups:
            for tool in self.group_tools(group):
                if tool not in seen:
                    resolved.append(tool)
                    seen.add(tool)
        return resolved

    def search(self, query: str, limit: int = 20) -> list[MCPTool]:
        q = query.lower().strip()
        if not q:
            return self.list_tool_objects()[:limit]
        matches = []
        for tool in self._tools.values():
            hay = " ".join([
                tool.name,
                tool.category,
                tool.description,
                " ".join(tool.tags),
                " ".join(tool.transports),
            ]).lower()
            if q in hay:
                matches.append(tool)
        matches.sort(key=lambda t: (t.category, t.name))
        return matches[:limit]

    def capabilities(self) -> dict[str, Any]:
        categories: dict[str, int] = {}
        for tool in self._tools.values():
            categories[tool.category] = categories.get(tool.category, 0) + 1
        return {
            "tool_count": len(self._tools),
            "group_count": len(self._tool_groups),
            "mode_count": len(self._preset_modes),
            "categories": categories,
            "transports": list(SUPPORTED_TRANSPORTS),
        }


_registry = MCPRegistry()


def list_tools() -> list[str]:
    return _registry.list_tools()


def list_tool_objects() -> list[MCPTool]:
    return _registry.list_tool_objects()


def get_tool(name: str) -> MCPTool | None:
    return _registry.get_tool(name)


def list_tool_groups() -> list[str]:
    return _registry.list_groups()


def get_tool_group(name: str) -> list[str]:
    return _registry.group_tools(name)


def list_preset_modes() -> list[str]:
    return _registry.list_modes()


def get_preset_mode(name: str) -> list[str]:
    return _registry.mode_tools(name)


def search_tools(query: str, limit: int = 20) -> list[MCPTool]:
    return _registry.search(query, limit=limit)


def transport_modes() -> list[str]:
    return list(SUPPORTED_TRANSPORTS)


def mcp_capabilities() -> dict[str, Any]:
    return _registry.capabilities()
