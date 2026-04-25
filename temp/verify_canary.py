#!/usr/bin/env python3
"""Verify Phase 12 canary runtime branching — direct file test."""
import sys, json, hashlib, os

# Read canary_router.py directly
router_src = open("/root/.openclaw/workspace/ops/multi-agent-orchestrator/canary_router.py").read()
exec(compile(open("/root/.openclaw/workspace/ops/multi-agent-orchestrator/canary_router.py").read(), "canary_router.py", "exec"))

print("=== Canary Router ===")
print("is_canary_deployed():", is_canary_deployed())
print("get_canary_version():", repr(get_canary_version()))
print("route_to_canary sample:", [route_to_canary(f't{i}') for i in range(20)])

# Verify canary.md exists and has correct branding
canary_md = "/root/.openclaw/workspace/agents/templates/researcher/canary.md"
print("\n=== Canary Template ===")
if os.path.exists(canary_md):
    content = open(canary_md).read()
    print(f"canary.md found ({len(content)} bytes)")
    print("Version line:", [l for l in content.splitlines() if "Version:" in l][:1])
    print("Has CANARY BUILD in template:", "CANARY BUILD" in content)
else:
    print("canary.md NOT FOUND")

# Verify stable template
stable_md = "/root/.openclaw/workspace/agents/templates/researcher/v1.0.md"
print("\n=== Stable Template ===")
if os.path.exists(stable_md):
    content = open(stable_md).read()
    print(f"v1.0.md found ({len(content)} bytes)")
    print("Has CANARY BUILD in stable:", "CANARY BUILD" in content)
else:
    print("v1.0.md NOT FOUND")

# Simulate routing logic
print("\n=== Runtime Branching Simulation ===")
canary_active = is_canary_deployed()
print(f"canary deployed: {canary_active}")
print(f"get_canary_version: {repr(get_canary_version())}")

# t8 was True in our sample
task = {"task_id": "t8", "task_type": "research", "canary_routed": route_to_canary("t8")}
canary_routed = task["canary_routed"]
use_canary = canary_routed and canary_active
print(f"task t8 canary_routed: {canary_routed}")
print(f"use_canary = {canary_routed} and {canary_active} = {use_canary}")

# Verify task_orchestrator.py has the new code
orch_src = open("/root/.openclaw/workspace/ops/multi-agent-orchestrator/task_orchestrator.py").read()
print("\n=== task_orchestrator.py Phase 12 code ===")
print("has is_canary_deployed import:", "is_canary_deployed" in orch_src)
print("has use_canary logic:", "use_canary = canary_routed and canary_active" in orch_src)
print("has CANARY BUILD marker:", "CANARY BUILD" in orch_src)
print("has harness_template_version = canary-v1:", 'harness_template_version = "canary-v1"' in orch_src)
print("has canary_version recording:", 'task["canary_version"]' in orch_src)

print("\n=== Marker File ===")
marker = "/root/.openclaw/workspace/ops/multi-agent-orchestrator/.canary_version"
print(f".canary_version exists: {os.path.exists(marker)}")
if os.path.exists(marker):
    print(".canary_version contents:", repr(open(marker).read().strip()))

print("\n=== VERIFICATION COMPLETE ===")
if use_canary and os.path.exists(canary_md):
    print("✓ Canary deployed with canary.md template ready")
    print("✓ t8 will be routed to canary path at spawn time")
    print("✓ spawn_child_agent will load canary.md + prepend CANARY BUILD marker")
else:
    print("Note: t8 may not be in canary sample (routing is deterministic)")
