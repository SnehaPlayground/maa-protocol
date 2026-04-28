#!/usr/bin/env python3
import sys, os
sys.path.insert(0, '/root/.openclaw/workspace')

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

print('[smoke] providers:', len(list_providers()))
print('[smoke] embeddings dims:', embed_text('x').dims)
print('[smoke] batch_embed:', len(batch_embed(['a','b'])))
p = store_pattern('research', 'smoke-test', 'hello world')
print('[smoke] pattern stored:', p.exists())
print('[smoke] pattern search:', len(search_patterns('hello')))
print('[smoke] swarm roles:', build_swarm(3).roles)
print('[smoke] hooks:', len(list_hooks()))
print('[smoke] plugins:', len(list_plugins()))
grant('mother', 'task', 'spawn')
print('[smoke] claims:', len(list_claims()))
print('[smoke] neural decide:', decide('q', 0.8).action)
print('[smoke] guidance:', compile_guidance('test').intent)
print('[smoke] codex templates:', len(feature_template()))
print('[smoke] browser:', browser_capabilities()['fetch'])
print('[smoke] deployment profiles:', len(deployment_profiles()))
print('[smoke] perf targets:', performance_targets()['max_concurrent_children'])
print('[smoke] security:', security_capabilities()['approval_gate'])
print('[smoke] mcp tools:', len(list_tools()))
print('[smoke] mcp groups:', len(list_tool_groups()))
print('[smoke] mcp modes:', len(list_preset_modes()))
print('[smoke] monitor group size:', len(get_tool_group('monitor')))
print('[smoke] develop mode size:', len(get_preset_mode('develop')))
print('[smoke] mcp capability transports:', mcp_capabilities()['transports'])
print('SMOKE_ALL_OK')
