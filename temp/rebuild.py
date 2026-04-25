import re, os, sys, ast

WORKSPACE = "/root/.openclaw/workspace"
ORCH_DIR = f"{WORKSPACE}/ops/multi-agent-orchestrator"
BACKUP = f"{ORCH_DIR}/task_orchestrator.py.orig"
OUT = f"{ORCH_DIR}/task_orchestrator.py"

with open(BACKUP) as f:
    content = f.read()

# Find the PROGRESS_PING_AT line
lines = content.split('\n')
for i, l in enumerate(lines):
    if 'PROGRESS_PING_AT' in l:
        insert_after = i
        print(f"PROGRESS_PING_AT found at line {i+1}: {l[:60]}")
        break

# New Phase 2 constants block
new_block = """

# ── Phase 2: Runtime Harness Enforcement ─────────────────────────────────────
TEMPLATES_DIR = f"{WORKSPACE}/agents/templates"
LOOP_SAME_FAILURE_THRESHOLD = 2
HARNESS_SPEC_MIN_FIELDS = ["harness_version", "active_pillars", "verification_gates", "dynamic_reminders"]
REFLECTION_MIN_LENGTH = 5
MAX_CONCURRENT_CHILDREN = 4
CIRCUIT_BREAKER_WINDOW_S = 3600
CIRCUIT_BREAKER_THRESHOLD = 0.05

# ── Phase 1: Template loading ─────────────────────────────────────────────────
def load_template(task_type: str, version: str = "v1.0") -> str | None:
    type_to_template = {
        "market-brief": "researcher",
        "research": "researcher",
        "email-draft": "communicator",
        "growth-report": "researcher",
        "validation": "verifier",
        "coder": "coder",
        "executor": "executor",
    }
    template_name = type_to_template.get(task_type, "researcher")
    path = f"{TEMPLATES_DIR}/{template_name}/{version}.md"
    try:
        with open(path) as f:
            c = f.read()
        print(f"[Mother Agent] Loaded template: {path} ({len(c)} bytes)")
        return c
    except FileNotFoundError:
        print(f"[Mother Agent] Template not found: {path}, using inline harness")
        return None

# ── Phase 2 Step 2.2: Harness spec runtime verification ───────────────────────
def _verify_harness_spec(harness: dict, task_id: str) -> tuple[bool, str]:
    if harness is None:
        return False, "harness_spec is None"
    for field in HARNESS_SPEC_MIN_FIELDS:
        if field not in harness:
            return False, f"harness_spec missing required field: {field}"
    active_pillars = harness.get("active_pillars", [])
    if not active_pillars:
        return False, "active_pillars is empty"
    gates = harness.get("verification_gates", [])
    if len(gates) < 5:
        return False, f"verification_gates has {len(gates)} gates, need 5"
    dr = harness.get("dynamic_reminders")
    if dr is None:
        return False, "dynamic_reminders is None (must be list, even if empty)"
    print(f"[Mother Agent] Harness spec verified OK for {task_id} (pillars={active_pillars}, gates={len(gates)})")
    return True, "ok"

"""

new_content = "\n".join(lines[:insert_after+1]) + new_block + "\n".join(lines[insert_after+1:])

try:
    ast.parse(new_content)
    print("SYNTAX OK after step 1")
except SyntaxError as e:
    print(f"SYNTAX ERROR at line {e.lineno}: {e.msg}")
    lines2 = new_content.split('\n')
    for i in range(max(0, e.lineno-3), min(len(lines2), e.lineno+3)):
        print(f"{i+1}: {repr(lines2[i])}")
    sys.exit(1)

with open(OUT, "w") as f:
    f.write(new_content)
print(f"Written step 1: {OUT}")
