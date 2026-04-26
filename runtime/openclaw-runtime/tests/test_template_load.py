"""
Regression tests for sub-agent template loading.
Phase 1: Verify all 5 template files load correctly and contain required sections.
"""
import os
import sys

# Ensure workspace is on path
WORKSPACE = "/root/.openclaw/workspace"
TEMPLATES_DIR = f"{WORKSPACE}/agents/templates"
sys.path.insert(0, WORKSPACE)

AGENT_TYPES = ["researcher", "executor", "coder", "verifier", "communicator"]
REQUIRED_SECTIONS = [
    "## Active Pillars",
    "## Global State Keys",
    "## Scoped Memory",
    "## Dynamic Reminders Slot",
    "## Verification Gates",
    "## Success Criteria",
    "## Safety Constraints",
    "## Escalation Rules",
    "## Progress Report Format",
    "## Tool Permissions",
]


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
            return f.read()
    except FileNotFoundError:
        return None


def test_all_templates_exist():
    """All 5 template files must exist on disk."""
    missing = []
    for agent_type in AGENT_TYPES:
        path = f"{TEMPLATES_DIR}/{agent_type}/v1.0.md"
        if not os.path.exists(path):
            missing.append(path)
    assert not missing, f"Missing template files: {missing}"


def test_all_templates_load_without_error():
    """load_template() returns non-empty string for all 5 agent types."""
    failed = []
    for task_type, template_name in [
        ("market-brief", "researcher"),
        ("research", "researcher"),
        ("email-draft", "communicator"),
        ("validation", "verifier"),
        ("coder", "coder"),
        ("executor", "executor"),
    ]:
        content = load_template(task_type)
        if not content:
            failed.append(f"load_template('{task_type}') returned None or empty")
    assert not failed, "\n".join(failed)


def test_template_has_required_sections():
    """Each template contains all required sections."""
    failed = []
    for agent_type in AGENT_TYPES:
        path = f"{TEMPLATES_DIR}/{agent_type}/v1.0.md"
        with open(path) as f:
            content = f.read()
        for section in REQUIRED_SECTIONS:
            if section not in content:
                failed.append(f"{agent_type}/v1.0.md missing: {section}")
    assert not failed, "\n".join(failed)


def test_templates_have_version_tag():
    """Each template has a Version: v1.0 tag."""
    failed = []
    for agent_type in AGENT_TYPES:
        path = f"{TEMPLATES_DIR}/{agent_type}/v1.0.md"
        with open(path) as f:
            content = f.read()
        if "Version: v1.0" not in content:
            failed.append(f"{agent_type}/v1.0.md missing 'Version: v1.0'")
    assert not failed, "\n".join(failed)


def test_dynamic_reminders_slot_is_populated_at_spawn_time():
    """Each template's Dynamic Reminders Slot section says 'POPULATED AT SPAWN TIME'."""
    failed = []
    for agent_type in AGENT_TYPES:
        path = f"{TEMPLATES_DIR}/{agent_type}/v1.0.md"
        with open(path) as f:
            content = f.read()
        marker = "POPULATED AT SPAWN TIME"
        if marker not in content:
            failed.append(f"{agent_type}/v1.0.md: Dynamic Reminders Slot does not say '{marker}'")
    assert not failed, "\n".join(failed)


def test_verification_gates_not_empty():
    """Each template has at least 3 verification gates defined."""
    failed = []
    for agent_type in AGENT_TYPES:
        path = f"{TEMPLATES_DIR}/{agent_type}/v1.0.md"
        with open(path) as f:
            content = f.read()
        # Count numbered gates (e.g., "1. Completeness:")
        import re
        gates = re.findall(r"\d+\.\s+\w+", content)
        if len(gates) < 3:
            failed.append(f"{agent_type}/v1.0.md has only {len(gates)} verification gates (need ≥3)")
    assert not failed, "\n".join(failed)


def test_tool_permissions_are_specific():
    """Each template's Tool Permissions section is not empty."""
    failed = []
    for agent_type in AGENT_TYPES:
        path = f"{TEMPLATES_DIR}/{agent_type}/v1.0.md"
        with open(path) as f:
            content = f.read()
        # Extract the Tool Permissions section
        import re
        match = re.search(r"## Tool Permissions\s*\n(.*?)(?=\n##|\Z)", content, re.DOTALL | re.IGNORECASE)
        if not match:
            failed.append(f"{agent_type}/v1.0.md: no Tool Permissions section found")
            continue
        tool_section = match.group(1).strip()
        if not tool_section or len(tool_section) < 10:
            failed.append(f"{agent_type}/v1.0.md: Tool Permissions section is too short or empty")
    assert not failed, "\n".join(failed)


if __name__ == "__main__":
    print("Running template loading regression tests...\n")

    tests = [
        ("test_all_templates_exist", test_all_templates_exist),
        ("test_all_templates_load_without_error", test_all_templates_load_without_error),
        ("test_template_has_required_sections", test_template_has_required_sections),
        ("test_templates_have_version_tag", test_templates_have_version_tag),
        ("test_dynamic_reminders_slot_is_populated_at_spawn_time", test_dynamic_reminders_slot_is_populated_at_spawn_time),
        ("test_verification_gates_not_empty", test_verification_gates_not_empty),
        ("test_tool_permissions_are_specific", test_tool_permissions_are_specific),
    ]

    passed = 0
    failed = []

    for name, fn in tests:
        try:
            fn()
            print(f"  ✓ {name}")
            passed += 1
        except AssertionError as e:
            print(f"  ✗ {name}: {e}")
            failed.append(name)
        except Exception as e:
            print(f"  ✗ {name}: unexpected error: {e}")
            failed.append(name)

    print(f"\n{passed}/{len(tests)} passed")
    if failed:
        print(f"FAILED: {', '.join(failed)}")
        sys.exit(1)
    else:
        print("All regression tests passed.")