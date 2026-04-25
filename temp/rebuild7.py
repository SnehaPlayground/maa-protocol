"""Add missing concurrent child tracking functions."""
import ast, sys

OUT = '/root/.openclaw/workspace/ops/multi-agent-orchestrator/task_orchestrator.py'
with open(OUT) as f:
    content = f.read()

idx = content.find('# ── Startup reconciliation for restart/resume safety')
if idx < 0:
    print("ERROR: startup reconciliation marker not found")
    sys.exit(1)

CONCURRENT_BLOCK = '''# ── Concurrent child tracking ─────────────────────────────────────────────────
_running_children_lock = __import__("threading").Lock()
_running_children: set = set()
RUNNING_CHILDREN_FILE = f"{LOGS_DIR}/running_children.json"
STALE_RUNNING_SECONDS = CHILD_TIMEOUT * 2

def _persist_running_children() -> None:
    try:
        os.makedirs(LOGS_DIR, exist_ok=True)
        with _running_children_lock:
            payload = {"updated_at": now_iso(), "task_ids": sorted(_running_children)}
        with open(RUNNING_CHILDREN_FILE, "w") as f:
            json.dump(payload, f, indent=2)
    except Exception as e:
        print("[Mother Agent] Could not persist running children: " + str(e), file=sys.stderr)

def _load_running_children() -> set:
    if not os.path.exists(RUNNING_CHILDREN_FILE):
        return set()
    try:
        with open(RUNNING_CHILDREN_FILE) as f:
            payload = json.load(f)
        return set(payload.get("task_ids", []))
    except Exception:
        return set()

def _get_running_count() -> int:
    with _running_children_lock:
        return len(_running_children)

def _add_running(task_id: str) -> None:
    with _running_children_lock:
        _running_children.add(task_id)
    _persist_running_children()

def _remove_running(task_id: str) -> None:
    with _running_children_lock:
        _running_children.discard(task_id)
    _persist_running_children()


'''

new_content = content[:idx] + CONCURRENT_BLOCK + content[idx:]

try:
    ast.parse(new_content)
    print("SYNTAX OK")
except SyntaxError as e:
    print(f"SYNTAX ERROR at line {e.lineno}: {e.msg}")
    lines2 = new_content.split("\n")
    for i in range(max(0, e.lineno-3), min(len(lines2), e.lineno+3)):
        print(f"{i+1}: {repr(lines2[i])}")
    sys.exit(1)

with open(OUT, "w") as f:
    f.write(new_content)
print(f"Written. Total lines: {len(new_content.split(chr(10)))}")
