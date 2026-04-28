from maa_protocol.providers import list_providers
from maa_protocol.embeddings import embed_text, batch_embed
from maa_protocol.memory import store_pattern, search_patterns
from maa_protocol.swarm import build_swarm
from maa_protocol.hooks import list_hooks
from maa_protocol.plugins import list_plugins
from maa_protocol.claims import grant, list_claims
from maa_protocol.neural import decide
from maa_protocol.guidance import compile_guidance
from maa_protocol.codex import feature_template
from maa_protocol.browser import browser_capabilities
from maa_protocol.deployment import deployment_profiles
from maa_protocol.performance import performance_targets
from maa_protocol.security import security_capabilities
from maa_protocol.mcp import (
    list_tools,
    list_tool_groups,
    list_preset_modes,
    get_tool_group,
    get_preset_mode,
    mcp_capabilities,
)

assert len(list_providers()) >= 3
assert embed_text('x').dims == 384
assert len(batch_embed(['a', 'b'])) == 2
p = store_pattern('research', 'smoke-test', 'hello')
assert p.exists()
assert search_patterns('hello')
assert build_swarm(3).roles
assert 'pre-task' in list_hooks()
assert list_plugins()
grant('mother', 'task', 'spawn')
assert list_claims()
assert decide('q', 0.8).action == 'reuse'
assert compile_guidance('test').intent == 'test'
assert feature_template()
assert browser_capabilities()['fetch'] is True
assert deployment_profiles()
assert performance_targets()['max_concurrent_children'] == 4
assert security_capabilities()['approval_gate'] is True
assert 'swarm_init' in list_tools()
assert 'monitor' in list_tool_groups()
assert 'develop' in list_preset_modes()
assert 'task_status' in get_tool_group('monitor')
assert 'task_orchestrate' in get_preset_mode('develop')
assert mcp_capabilities()['tool_count'] >= 10
print('MAA_PROTOCOL_SMOKE_OK')
