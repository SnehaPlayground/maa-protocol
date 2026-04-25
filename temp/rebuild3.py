import ast, re

OUT = '/root/.openclaw/workspace/ops/multi-agent-orchestrator/task_orchestrator.py'
with open(OUT) as f:
    content = f.read()

print(f'File length: {len(content.split(chr(10)))} lines')

# ── STEP 8: Update spawn_child_agent ────────────────────────────────────────
# We need to:
# 1. Add harness verification before spawn
# 2. Add write_progress_report call before spawn  
# 3. Add load_template call and template injection in child_prompt
# 4. Add harness_template_version to task state
# 5. Update loop detection to use loop_count from _detect_loop return
# 6. Add skip_child_respawn logic after loop detection
# 7. Add harness spec verification gate before spawn

# Find the loop detection block in spawn_child_agent and update it
old_loop = '''    # 8-Pillar P1/P8: Loop detection — same failure mode on consecutive attempts
    is_loop, loop_reason = _detect_loop(task)
    if is_loop:
        print(f"[Mother Agent] LOOP DETECTED for {task_id}: {loop_reason}")
        record_metric("error", f"maa.{task['task_type']}_loop_detected",
                      details=loop_reason, agent="mother")
        task["status"] = "loop_detected"
        task["loop_reason"] = loop_reason
        task["loop_detected_at"] = now_iso()
        with open(state_file, "w") as f:
            json.dump(task, f, indent=2)
        reflection = _run_reflection(task_id, {"reason": f"loop: {loop_reason}",
                                            "issues": [loop_reason]}, task["attempts"])
        task["reflection_notes"] = reflection
        task["status"] = "retry"
        with open(state_file, "w") as f:
            json.dump(task, f, indent=2)
        print(f"[Mother Agent] Loop analysis done — proceeding with corrected harness")'''

new_loop = '''    # 8-Pillar P1/P8: Loop detection + Phase 2 Step 2.4 runtime loop_count enforcement
    is_loop, loop_reason, loop_count = _detect_loop(task)
    if is_loop:
        task["loop_count"] = loop_count
        print(f"[Mother Agent] LOOP DETECTED for {task_id}: {loop_reason} (loop_count={loop_count})")
        record_metric("error", f"maa.{task['task_type']}_loop_detected",
                      details=f"{loop_reason} loop_count={loop_count}", agent="mother")
        task["status"] = "loop_detected"
        task["loop_reason"] = loop_reason
        task["loop_detected_at"] = now_iso()
        with open(state_file, "w") as f:
            json.dump(task, f, indent=2)
        # Phase 2 Step 2.4: If loop_count >= threshold, skip child respawn
        if loop_count >= LOOP_SAME_FAILURE_THRESHOLD:
            print(f"[Mother Agent] Loop count {loop_count} >= {LOOP_SAME_FAILURE_THRESHOLD} — skipping child respawn")
            task["status"] = "retry"
            task["skip_child_respawn"] = True
            task["child_failure_reason"] = loop_reason
            with open(state_file, "w") as f:
                json.dump(task, f, indent=2)
            return False
        reflection = _run_reflection(task_id, {"reason": f"loop: {loop_reason}",
                                            "issues": [loop_reason]}, task["attempts"])
        task["reflection_notes"] = reflection
        task["status"] = "retry"
        with open(state_file, "w") as f:
            json.dump(task, f, indent=2)
        print(f"[Mother Agent] Loop analysis done — proceeding with corrected harness")'''

if old_loop in content:
    content = content.replace(old_loop, new_loop, 1)
    print("Step 8a: Updated loop detection with loop_count + skip_child_respawn")
else:
    print("Step 8a: Old loop block not found (may already be updated)")

# Update circuit breaker comment
old_circuit = '''    # FIX-3: Circuit breaker — halt if error rate > 5% for this label'''
new_circuit = '''    # FIX-3 / Phase 2: Circuit breaker — halt if error rate > 5% for this label'''
if old_circuit in content:
    content = content.replace(old_circuit, new_circuit, 1)
    print("Step 8b: Updated circuit breaker comment")

# Update load shedding comment
old_load_shed = '''    # FIX-4: Load shedding — queue if at concurrency limit'''
new_load_shed = '''    # FIX-4 / Phase 2: Load shedding — queue if at concurrency limit'''
if old_load_shed in content:
    content = content.replace(old_load_shed, new_load_shed, 1)
    print("Step 8c: Updated load shedding comment")

# ── STEP 9: Update harness building section in spawn_child_agent ─────────────
# The old harness building section (before my edits) was:
#   # 8-Pillar: Design harness spec before this attempt
#   harness = _design_harness(...)
#   task["harness_spec"] = harness
#   task["active_pillars"] = harness["active_pillars"]
#   pillars_str = ...
#   reminders = ...
#   child_prompt = (f"TASK TYPE: ...\n"
#   f"USER REQUEST: ...\n"
#   f"\n=== 8-PILLAR HARNESS FOR THIS AGENT ===\n" ...)

old_harness_build = '''    # 8-Pillar: Design harness spec before this attempt
    prior_failure = (task.get("attempt_history", [{}])[-1].get("child_failure_reason")
                    if task.get("attempt_history") else None)
    harness = _design_harness(task["task_type"], task["task_prompt"],
                              task["attempts"] + 1, prior_failure)
    task["harness_spec"] = harness
    task["active_pillars"] = harness["active_pillars"]

    pillars_str = ", ".join(harness["active_pillars"])
    reminders = harness.get("dynamic_reminders", [])
    rem_str = "\\n".join([f"  - {r}" for r in reminders]) if reminders else "  (none)"
    success_str = "\\n".join([f"  - {c}" for c in harness["success_criteria"]])
    gates = harness["verification_gates"]

    child_prompt = (
        f"TASK TYPE: {task['task_type']} | TASK ID: {task_id}\\n"
        f"USER REQUEST: {task['task_prompt']}\\n"
        f"\\n=== 8-PILLAR HARNESS FOR THIS AGENT ===\\n"
        f"Active Pillars: {pillars_str}\\n"
        f"Global State Keys: {", ".join(harness['global_state_keys'])}\\n"
        f"Scoped Memory read: {", ".join(harness['scoped_memory']['read'])}\n"
        f"Scoped Memory write: {", ".join(harness['scoped_memory']['write'])}\n"
        f"Dynamic Reminders (from prior failures):\n{rem_str}\n"
        f"Verification Gates:\n"
        f"  1. Completeness: {gates[0]}\n"
        f"  2. Factual Grounding: {gates[1]}\n"
        f"  3. Format Compliance: {gates[2]}\n"
        f"  4. Quality: {gates[3]}\n"
        f"Success Criteria:\n{success_str}\n"
        f"Safety: no external sends without MA pre-approval; no irreversible without sign-off\n"
        f"Escalation: 3+ sources fail->ask MA; irreversible->pause; security->halt+escalate\n"
        f"Progress Reports: write logs/{task_id}.progress at start/progress/near_complete/done\n"
        f"OUTPUT PATH: {task['output_path']}{task.get('output_ext') or '.txt'}\\n"
        f"IMPORTANT: Return only the final output. No commentary. Write progress reports at checkpoints."
    )

    cmd = [
        "openclaw", "agent", "--local",
        "--session-id", task["session_id"],
        "-m", child_prompt,
        "--timeout", str(CHILD_TIMEOUT),
    ]'''

new_harness_build = '''    # 8-Pillar: Design harness spec before this attempt
    prior_failure = (task.get("attempt_history", [{}])[-1].get("child_failure_reason")
                    if task.get("attempt_history") else None)
    harness = _design_harness(task["task_type"], task["task_prompt"],
                              task["attempts"] + 1, prior_failure)
    task["harness_spec"] = harness
    task["active_pillars"] = harness["active_pillars"]

    # Phase 2 Step 2.2: Runtime harness spec verification BEFORE spawn
    harness_ok, harness_reason = _verify_harness_spec(harness, task_id)
    if not harness_ok:
        print(f"[Mother Agent] HARNESS SPEC VERIFICATION FAILED for {task_id}: {harness_reason}")
        record_metric("error", f"maa.{task['task_type']}_harness_verify_failed",
                      details=harness_reason, agent="mother")
        task["status"] = "retry"
        task["updated_at"] = now_iso()
        task["child_failure_reason"] = f"harness-spec-verify-failed: {harness_reason}"
        task["loop_count"] = task.get("loop_count", 0)
        with open(state_file, "w") as f:
            json.dump(task, f, indent=2)
        return False

    # Phase 2 Step 2.1: Write initial progress file before child runs
    write_progress_report(task_id, f"child-{task['attempts']}", "start", 0,
                         "Child agent spawning — harness verified, starting work",
                         blockers="", next_step="running",
                         harness_reminders=harness.get("dynamic_reminders", []))
    task["has_progress_update"] = False
    task["last_progress_at"] = now_iso()

    # Phase 1: Load template (fall back to inline harness if not found)
    template_content = load_template(task["task_type"])
    harness_template_version = "inline"
    if template_content:
        harness_template_version = "v1.0"

    pillars_str = ", ".join(harness["active_pillars"])
    reminders = harness.get("dynamic_reminders", [])
    rem_str = "\\n".join([f"  - {r}" for r in reminders]) if reminders else "  (none)"
    success_str = "\\n".join([f"  - {c}" for c in harness["success_criteria"]])
    gates = harness["verification_gates"]

    child_prompt = (
        f"TASK TYPE: {task['task_type']} | TASK ID: {task_id}\\n"
        f"USER REQUEST: {task['task_prompt']}\\n"
    )

    # Phase 1: If template loaded, inject it as full context before harness spec
    if template_content:
        child_prompt += (
            f"\\n{'='*60}\\n"
            f"SUB-AGENT TEMPLATE (loaded from {harness_template_version})\\n"
            f"{'='*60}\\n"
            f"{template_content}\\n"
            f"{'='*60}\\n"
            f"TASK HARNESS SPEC\\n"
            f"{'='*60}\\n"
        )

    child_prompt += (
        f"Active Pillars: {pillars_str}\\n"
        f"Global State Keys: {', '.join(harness['global_state_keys'])}\\n"
        f"Scoped Memory read: {', '.join(harness['scoped_memory']['read'])}\\n"
        f"Scoped Memory write: {', '.join(harness['scoped_memory']['write'])}\\n"
        f"Dynamic Reminders (from prior failures):\\n{rem_str}\\n"
        f"Verification Gates:\\n"
        f"  1. Completeness: {gates[0]}\\n"
        f"  2. Factual Grounding: {gates[1]}\\n"
        f"  3. Format Compliance: {gates[2]}\\n"
        f"  4. Quality: {gates[3]}\\n"
        f"Success Criteria:\\n{success_str}\\n"
        f"Safety: no external sends without MA pre-approval; no irreversible without sign-off\\n"
        f"Escalation: 3+ sources fail->ask MA; irreversible->pause; security->halt+escalate\\n"
        f"Progress Reports: write logs/{task_id}.progress at start/progress/near_complete/done\\n"
        f"OUTPUT PATH: {task['output_path']}{task.get('output_ext') or '.txt'}\\n"
        f"IMPORTANT: Return only the final output. No commentary. Write progress reports at checkpoints."
    )

    # Record template version in task state
    task["harness_template_version"] = harness_template_version

    cmd = [
        "openclaw", "agent", "--local",
        "--session-id", task["session_id"],
        "-m", child_prompt,
        "--timeout", str(CHILD_TIMEOUT),
    ]'''

if old_harness_build in content:
    content = content.replace(old_harness_build, new_harness_build, 1)
    print("Step 9: Updated harness build in spawn_child_agent")
else:
    print("Step 9: Old harness build not found")
    # Try to find what's there now
    idx = content.find('# 8-Pillar: Design harness spec before this attempt')
    if idx >= 0:
        print("  Current harness build start found at:", idx)

# ── STEP 10: Update run_task_chain loop ──────────────────────────────────────
old_chain_loop = '''        print(f"[Mother Agent] Attempt {attempt}/{MAX_RETRIES} for {task_id}")
        success = spawn_child_agent(task_id)

        with open(state_file) as f:
            task = json.load(f)'''

new_chain_loop = '''        # Phase 2 Step 2.4: If skip_child_respawn, jump to Mother self-execution
        with open(state_file) as f:
            task = json.load(f)
        if task.get("skip_child_respawn"):
            print(f"[Mother Agent] skip_child_respawn=True — looping to Mother self-execution")
            break

        print(f"[Mother Agent] Attempt {attempt}/{MAX_RETRIES} for {task_id}")
        success = spawn_child_agent(task_id)

        with open(state_file) as f:
            task = json.load(f)'''

if old_chain_loop in content:
    content = content.replace(old_chain_loop, new_chain_loop, 1)
    print("Step 10: Updated run_task_chain with skip_child_respawn check")
else:
    print("Step 10: Old chain loop not found")

# ── STEP 11: Add _reconcile_running_children + _mark_stale_running_tasks at end ──
startup_block = '''

# ── Startup reconciliation for restart/resume safety ──────────────────────────
def _reconcile_running_children() -> None:
    persisted = _load_running_children()
    live = set()
    for task_id in persisted:
        state_file = f"{TASKS_DIR}/{task_id}.json"
        if not os.path.exists(state_file):
            continue
        try:
            with open(state_file) as f:
                task = json.load(f)
            if task.get("status") in {"running", "mother_self_executing"}:
                live.add(task_id)
        except Exception:
            continue
    with _running_children_lock:
        _running_children.clear()
        _running_children.update(live)
    _persist_running_children()

def _mark_stale_running_tasks() -> None:
    now_ts = time.time()
    for name in os.listdir(TASKS_DIR):
        if not name.endswith(".json"):
            continue
        state_file = os.path.join(TASKS_DIR, name)
        try:
            with open(state_file) as f:
                task = json.load(f)
        except Exception:
            continue
        if task.get("status") not in {"running", "mother_self_executing"}:
            continue
        updated_at = task.get("updated_at") or task.get("mother_self_exec_at") or task.get("created_at")
        try:
            updated_ts = datetime.strptime(updated_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC).timestamp()
        except Exception:
            continue
        if now_ts - updated_ts <= STALE_RUNNING_SECONDS:
            continue
        task["status"] = "retry"
        task["stale_running_detected_at"] = now_iso()
        task["child_failure_reason"] = "stale running task after restart/recovery"
        if "attempt_history" not in task:
            task["attempt_history"] = []
        task["attempt_history"].append({
            "attempt": task.get("attempts", 0),
            "at": now_iso(),
            "child_failure_reason": task["child_failure_reason"],
            "status": "stale_recovered",
        })
        with open(state_file, "w") as f:
            json.dump(task, f, indent=2)

_reconcile_running_children()
_mark_stale_running_tasks()
'''

if "_reconcile_running_children()" not in content:
    content += startup_block
    print("Step 11: Added _reconcile_running_children, _mark_stale_running_tasks, and startup calls")
else:
    print("Step 11: Already exists")

# Verify
try:
    ast.parse(content)
    print("SYNTAX OK after steps 8-11")
except SyntaxError as e:
    print(f"SYNTAX ERROR at line {e.lineno}: {e.msg}")
    lines2 = content.split('\n')
    for i in range(max(0, e.lineno-3), min(len(lines2), e.lineno+3)):
        print(f"{i+1}: {repr(lines2[i])}")
    sys.exit(1)

with open(OUT, 'w') as f:
    f.write(content)
print(f"Written steps 8-11 to {OUT}")
