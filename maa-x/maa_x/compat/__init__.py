"""Compatibility shim — maps the original maa_protocol public API to maa_x.

Existing users of maa_protocol >= 0.2 can upgrade by replacing:
    from maa_protocol import ...
with:
    from maa_x.compat import ...
"""

from maa_x.core.governance import GovernanceWrapper
from maa_x.guards.approval import ApprovalGate, ApprovalRequest
from maa_x.guards.canary import CanaryRouter
from maa_x.guards.cost import CostGuard
from maa_x.guards.self_healing import SelfHealing, SelfHealingConfig
from maa_x.guards.tenant import AccessControl, TenantContext, TenantGate
from maa_x.persistence.base import ApprovalRecord, AuditEvent, PersistenceBackend, PostgresBackend, SQLiteBackend
from maa_x.observability.metrics import MetricsCollector, TimedBlock
from maa_x.exceptions import ApprovalRequiredError, CircuitOpenError, CostLimitExceededError, MaaProtocolError, TenantAccessError
from maa_x.swarm import AgentState, ConsensusStrategy as ConsensusStrategyEnum, SwarmConfig, SwarmExecutionEngine, SwarmMetrics, SwarmPlan, run_swarm
from maa_x.learning import QLearningAgent, PolicyGradientAgent, SARSAAgent, RewardShaper, RLRunner, RLConfig, RLResult, Transition, RoutingEnv, create_q_agent, create_policy_gradient, create_sarsa, create_routing_env
from maa_x.plugins import PluginRegistry, PluginSpec, PluginState, PluginKind, get_registry, get_plugin, enable_plugin, disable_plugin, list_plugins, discover_plugins
from maa_x.mcp import MCPTool, MCPRegistry, list_tools, get_tool, search_tools, mcp_capabilities

# Additional modules from maa_protocol parity
from maa_x.attention import ScaledDotProductAttention, MultiHeadAttention, CrossAttention, CrossAttentionResult, TaskCrossEncoder, MemoryBank, AgentAttentionLayer, scaled_dot_product, cross_attend, create_memory_bank
from maa_x.codex import ModeSelector, CollaborationMode, CodexAgentRole, DualModeTask, TaskSegment, DecomposedTask, DualModeCoordinator
from maa_x.neural import PolicyNetwork, NeuralRouter, AttentionPool, AgentStateEncoder, NeuralRouterResult, create_neural_router, create_policy_network, create_attention_pool
from maa_x.gnn import AgentGraph, GNNMessagePasser, TopologyGNN, SwarnGNN, create_agent_graph, create_topology_gnn
from maa_x.claims import Claim, grant, list_claims, check_claim, clear_claims
from maa_x.providers import ProviderSpec, register_provider, list_providers, get_provider
from maa_x.performance import performance_targets, benchmark_result
from maa_x.self_healing import SelfHealingPolicy, HealingAction, create_self_healing_policy
from maa_x.browser import BrowserSession, FetchResult, FetchResult, browser_capabilities, fetch, get, post
from maa_x.deployment import DeploymentProfile, RuntimeConfig, HealthStatus, HealthCheck, DeploymentState, deployment_profiles, get_runtime_config, run_health_check, rotate_credentials, get_deployment_state
from maa_x.ipfs import IPFSClient, IPFSObject, add_text, add_bytes, cat, cat_text, pin, unpin, list_pins
from maa_x.github_automation import GitHubAutomation, GitHubResult, gh_available, list_issues, list_prs, view_issue, view_pr, workflow_runs
from maa_x.mcp_runtime import MCPRuntime, MCPRequest, MCPResponse
from maa_x.wasm import WasmModule, WasmRunner, WasmAgent, WasmPlugin, WasmSandbox, WasmBundle, ExecutionResult, AgentState, create_sandbox, runtime_name, is_available
from maa_x.rvf import RVFPacker, RVFUnpacker, RVFValidator, RVFRegistry, RVFBundle, RVFManifest, ValidationReport, pack_bundle, unpack_bundle, validate_bundle, install_bundle
from maa_x.embeddings import embed_text, batch_embed, SemanticMemory, SemanticRouter, PatternMemory, score_decision, SearchResult
from maa_x.rl import QLearningAgent as RLQLearningAgent, SARSAAgent as RLSARSAAgent, RewardShaper as RLRewardShaper, RoutingEnv as RLRoutingEnv

__all__ = [
    'GovernanceWrapper',
    'ApprovalGate', 'ApprovalRequest', 'CanaryRouter', 'CostGuard',
    'SelfHealing', 'SelfHealingConfig',
    'AccessControl', 'TenantContext', 'TenantGate',
    'ApprovalRecord', 'AuditEvent', 'PersistenceBackend', 'PostgresBackend', 'SQLiteBackend',
    'MetricsCollector', 'TimedBlock',
    'ApprovalRequiredError', 'CircuitOpenError', 'CostLimitExceededError', 'MaaProtocolError', 'TenantAccessError',
    'AgentState', 'ConsensusStrategyEnum', 'SwarmConfig', 'SwarmExecutionEngine', 'SwarmMetrics', 'SwarmPlan', 'run_swarm',
    'QLearningAgent', 'PolicyGradientAgent', 'SARSAAgent', 'RewardShaper', 'RLRunner', 'RLConfig', 'RLResult', 'Transition', 'RoutingEnv', 'create_q_agent', 'create_policy_gradient', 'create_sarsa', 'create_routing_env',
    'PluginRegistry', 'PluginSpec', 'PluginState', 'PluginKind', 'get_registry', 'get_plugin', 'enable_plugin', 'disable_plugin', 'list_plugins', 'discover_plugins',
    'MCPTool', 'MCPRegistry', 'list_tools', 'get_tool', 'search_tools', 'mcp_capabilities',
    'ScaledDotProductAttention', 'MultiHeadAttention', 'CrossAttention', 'CrossAttentionResult', 'TaskCrossEncoder', 'MemoryBank', 'AgentAttentionLayer', 'scaled_dot_product', 'cross_attend', 'create_memory_bank',
    'ModeSelector', 'CollaborationMode', 'CodexAgentRole', 'DualModeTask', 'TaskSegment', 'DecomposedTask', 'DualModeCoordinator',
    'PolicyNetwork', 'NeuralRouter', 'AttentionPool', 'AgentStateEncoder', 'NeuralRouterResult', 'create_neural_router', 'create_policy_network', 'create_attention_pool',
    'AgentGraph', 'GNNMessagePasser', 'TopologyGNN', 'SwarnGNN', 'create_agent_graph', 'create_topology_gnn',
    'Claim', 'grant', 'list_claims', 'check_claim', 'clear_claims',
    'ProviderSpec', 'register_provider', 'list_providers', 'get_provider',
    'performance_targets', 'benchmark_result',
    'SelfHealingPolicy', 'HealingAction', 'create_self_healing_policy',
    'BrowserSession', 'FetchResult', 'browser_capabilities', 'fetch', 'get', 'post',
    'DeploymentProfile', 'RuntimeConfig', 'HealthStatus', 'HealthCheck', 'DeploymentState', 'deployment_profiles', 'get_runtime_config', 'run_health_check', 'rotate_credentials', 'get_deployment_state',
    'IPFSClient', 'IPFSObject', 'add_text', 'add_bytes', 'cat', 'cat_text', 'pin', 'unpin', 'list_pins',
    'GitHubAutomation', 'GitHubResult', 'gh_available', 'list_issues', 'list_prs', 'view_issue', 'view_pr', 'workflow_runs',
    'MCPRuntime', 'MCPRequest', 'MCPResponse',
    'WasmModule', 'WasmRunner', 'WasmAgent', 'WasmPlugin', 'WasmSandbox', 'WasmBundle', 'ExecutionResult', 'AgentState', 'create_sandbox', 'runtime_name', 'is_available',
    'RVFPacker', 'RVFUnpacker', 'RVFValidator', 'RVFRegistry', 'RVFBundle', 'RVFManifest', 'ValidationReport', 'pack_bundle', 'unpack_bundle', 'validate_bundle', 'install_bundle',
    'embed_text', 'batch_embed', 'SemanticMemory', 'SemanticRouter', 'PatternMemory', 'score_decision', 'SearchResult',
]
