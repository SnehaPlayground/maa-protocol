"""maa_x package — Enterprise AI orchestration platform."""

from .core.governance import GovernanceWrapper
from .mcp import MCPRegistry, MCPTool
from .memory import AgentDB, PatternMemory, SemanticMemory
from .plugins import PluginRegistry
from .provider_router import ProviderRouter, RouteRequest, RoutingStrategy, route_model
from .security import ThreatDetector

__version__ = "0.1.0"

__all__ = [
    "GovernanceWrapper",
    "AgentDB",
    "PatternMemory",
    "SemanticMemory",
    "PluginRegistry",
    "ProviderRouter",
    "RouteRequest",
    "RoutingStrategy",
    "route_model",
    "ThreatDetector",
    "MCPRegistry",
    "MCPTool",
    "__version__",
]