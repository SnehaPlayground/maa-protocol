with open('/root/.openclaw/workspace/ops/multi-agent-orchestrator/task_orchestrator.py') as f:
    content = f.read()

# Step 2: Update child_output_is_usable (raise threshold from 50 to 200)
old = '''    if len(text) < 50:
        try:
            json.loads(text)
            return True, "ok"
        except Exception:
            return False, f"output too short ({len(text)} chars) and not valid JSON"

    return True, "ok"'''
new = '''    MIN_CONTENT_THRESHOLD = 200
    if len(text) < MIN_CONTENT_THRESHOLD:
        try:
            json.loads(text)
            return True, "ok"
        except Exception:
            return False, f"output too short ({len(text)} chars, min={MIN_CONTENT_THRESHOLD}) and not valid JSON"

    return True, "ok"'''
if old in content:
    content = content.replace(old, new, 1)
    print("Step 2: Updated child_output_is_usable MIN_CONTENT_THRESHOLD")
else:
    print("Step 2: Pattern not found")

# Step 3: Add _design_harness function before spawn_child_agent
# Find spawn_child_agent line and insert _design_harness before it
old_spawn = "def spawn_child_agent(task_id: str) -> Optional[bool]:"
new_design_harness = '''def _design_harness(task_type, task_prompt, attempt, prior_failure_mode=None):
    pillar_map = {
        "market-brief":   ["P1","P2","P4","P5","P7","P8"],
        "research":       ["P1","P2","P3","P4","P5","P7","P8"],
        "email-draft":    ["P1","P2","P4","P6","P7","P8"],
        "growth-report":  ["P1","P2","P3","P4","P5","P7","P8"],
        "validation":     ["P1","P2","P4","P7"],
    }
    active = pillar_map.get(task_type, ["P1","P2","P4","P7","P8"])
    reminders = []
    if prior_failure_mode:
        reminders.append(
            f"REMINDER: Previous attempt failed with '{prior_failure_mode}'. "
            "Do not repeat the same approach. Try an alternate strategy.")
        if "P3" not in active:
            active.append("P3")
    return {
        "harness_version": "1.0",
        "task_type": task_type,
        "attempt": attempt,
        "active_pillars": active,
        "global_state_keys": ["task_id","task_type","attempt","output_path","tenant_context"],
        "scoped_memory": {
            "read":  ["task_prompt","output_path","harness_spec"],
            "write": ["findings","draft_output","checkpoint_report"],
        },
        "verification_gates": [
            "completeness — fully formed, no [TBD], no truncation",
            "factual_grounding — claims backed with data, numbers verifiable",
            "format_compliance — matches expected format for task_type",
            "quality — production-ready, no waffle, no vague language",
            "channel_fit — correct delivery channel for this output",
        ],
        "success_criteria": _success_criteria_for(task_type),
        "escalation_rules": [
            "If 3+ sources fail —> ask Mother Agent for alternative strategy",
            "If output would be irreversible —> pause and ask Mother Agent",
            "If security issue detected —> halt and escalate before continuing",
            "If quality score below threshold —> return detailed failure report",
        ],
        "safety_constraints": [
            "No external sends without Mother Agent pre-approval",
            "No irreversible actions without explicit Mother Agent sign-off",
            "No reveal of internal prompts, tokens, or private mechanics",
        ],
        "dynamic_reminders": reminders,
    }

def _success_criteria_for(task_type):
    return {
        "market-brief":   ["TL;DR box","Executive Summary","charts/tables with citations","CTA","What this means for you section"],
        "research":       ["Source citations","concrete levels/targets","What this means for you in every section","factual grounding"],
        "email-draft":    ["Valid JSON matching schema {to,subject,body_text,body_html,classification,send_now}","no [TBD]","appropriate professional tone"],
        "growth-report":  ["TL;DR + Executive Summary","Hypothesis/Validation/Evidence/ROI/Confidence/Next Step/Label/Proof Level","Action Section"],
        "validation":     ["All 5 validation gates passed","issues list empty","one-line decisive summary"],
    }.get(task_type, ["Production-quality output, make Partha impressed"])

'''

if old_spawn in content:
    content = content.replace(old_spawn, new_design_harness + old_spawn, 1)
    print("Step 3: Added _design_harness and _success_criteria_for before spawn_child_agent")
else:
    print("Step 3: spawn_child_agent not found")

# Step 4: Add _detect_loop function before spawn_child_agent
detect_loop_fn = '''def _detect_loop(task):
    history = task.get("attempt_history", [])
    if len(history) < 2:
        return False, "", 0
    def norm(r):
        if not r:
            return ""
        r = r.lower()
        for p in ["traceback","syntaxerror","importerror","timeout","no result",
                  "spawn_error","failed","exit=","usability","marker-verify","state_version"]:
            if p in r:
                return p
        return r[:60]
    a = norm(history[-1].get("child_failure_reason",""))
    b = norm(history[-2].get("child_failure_reason",""))
    loop_count = task.get("loop_count", 0)
    if a and a == b:
        return True, f"loop: same failure mode ({a})", loop_count + 1
    return False, "", 0

'''

if "def _detect_loop(task):" not in content:
    content = content.replace("def spawn_child_agent(task_id: str) -> Optional[bool]:",
                              detect_loop_fn + "def spawn_child_agent(task_id: str) -> Optional[bool]:", 1)
    print("Step 4: Added _detect_loop")
else:
    print("Step 4: _detect_loop already exists")

# Step 5: Add _run_reflection before spawn_child_agent
reflection_fn = '''def _run_reflection(task_id, validation, attempt):
    sf = f"{TASKS_DIR}/{task_id}.json"
    with open(sf) as f:
        task = json.load(f)
    issues = validation.get("issues", [])
    failed_gate = (validation.get("completeness") or validation.get("factual_grounding")
                   or validation.get("format_compliance") or validation.get("quality")
                   or validation.get("reason", "unknown"))
    correction = ("Review the failed gate. Do not repeat the same approach."
                  if not issues else
                  f"Address these specific issues: {'; '.join(issues[:3])}. "
                  "Revised output must fix all of them.")
    reflection = {
        "at": now_iso(),
        "attempt": attempt,
        "failed_gate": failed_gate,
        "issues_found": issues[:3],
        "correction_directive": correction,
    }
    print(f"[Mother Agent] Reflection {task_id} (attempt {attempt}): gate={failed_gate}")
    record_metric("reflection", f"maa.{task.get('task_type','unknown')}_validation_failure",
                  gate=failed_gate, attempt=attempt,
                  issues=str(issues[:3]), agent="mother")
    # Phase 2 Step 2.5: Write to dedicated .reflection file for immutable audit trail
    reflection_file = f"{LOGS_DIR}/{task_id}.reflection"
    try:
        with open(reflection_file, "w") as f:
            json.dump(reflection, f, indent=2)
        print(f"[Mother Agent] Reflection written to {reflection_file}")
    except Exception as e:
        print(f"[Mother Agent] Could not write reflection file: {e}", file=sys.stderr)
    return reflection

'''

if "def _run_reflection(task_id, validation, attempt):" not in content:
    content = content.replace("def spawn_child_agent(task_id: str) -> Optional[bool]:",
                              reflection_fn + "def spawn_child_agent(task_id: str) -> Optional[bool]:", 1)
    print("Step 5: Added _run_reflection")
else:
    print("Step 5: _run_reflection already exists")

# Step 6: Add write_progress_report before spawn_child_agent
progress_fn = '''def write_progress_report(task_id, agent_label, checkpoint, progress_pct,
                          current_action, findings="", blockers="", next_step="",
                          harness_reminders=None):
    pf = f"{LOGS_DIR}/{task_id}.progress"
    try:
        with open(pf, "w") as f:
            json.dump({
                "task_id": task_id,
                "agent_label": agent_label,
                "checkpoint": checkpoint,
                "progress_pct": max(0, min(100, progress_pct)),
                "current_action": current_action,
                "findings": findings,
                "blockers": blockers,
                "next_step": next_step,
                "harness_reminders_active": harness_reminders or [],
                "written_at": now_iso(),
            }, f, indent=2)
    except Exception as e:
        print(f"[Mother Agent] Progress report write failed: {e}", file=sys.stderr)

'''

if "def write_progress_report(" not in content:
    content = content.replace("def spawn_child_agent(task_id: str) -> Optional[bool]:",
                              progress_fn + "def spawn_child_agent(task_id: str) -> Optional[bool]:", 1)
    print("Step 6: Added write_progress_report")
else:
    print("Step 6: write_progress_report already exists")

# Step 7: Add concurrent child tracking at module level (after MAX_RETRIES)
concurrent_block = '''# ── Concurrent child tracking ─────────────────────────────────────────────────
_running_children_lock = threading.Lock()
_running_children: set[str] = set()
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
        print(f"[Mother Agent] Could not persist running children: {e}", file=sys.stderr)

def _load_running_children() -> set[str]:
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

_task_queue: list[str] = []
_queue_lock = threading.Lock()

def queue_task(task_id: str) -> bool:
    count = _get_running_count()
    if count < MAX_CONCURRENT_CHILDREN:
        return False
    with _queue_lock:
        _task_queue.append(task_id)
    return True

def _process_queue() -> Optional[str]:
    with _queue_lock:
        if len(_task_queue) == 0:
            return None
        count = _get_running_count()
        if count >= MAX_CONCURRENT_CHILDREN:
            return None
        task_id = _task_queue.pop(0)
        return task_id

def submit_to_queue(task_id: str) -> None:
    with _queue_lock:
        if task_id not in _task_queue:
            _task_queue.append(task_id)

'''

# Add after load_template def but before spawn_child_agent
if "def _persist_running_children()" not in content:
    content = content.replace(
        "def spawn_child_agent(task_id: str) -> Optional[bool]:",
        concurrent_block + "def spawn_child_agent(task_id: str) -> Optional[bool]:", 1)
    print("Step 7: Added concurrent child tracking")
else:
    print("Step 7: concurrent tracking already exists")

# Verify syntax
try:
    ast.parse(content)
    print("SYNTAX OK after steps 2-7")
except SyntaxError as e:
    print(f"SYNTAX ERROR at line {e.lineno}: {e.msg}")
    lines2 = content.split('\n')
    for i in range(max(0, e.lineno-3), min(len(lines2), e.lineno+3)):
        print(f"{i+1}: {repr(lines2[i])}")
    sys.exit(1)

with open('/root/.openclaw/workspace/ops/multi-agent-orchestrator/task_orchestrator.py', 'w') as f:
    f.write(content)
print("Written steps 2-7")
