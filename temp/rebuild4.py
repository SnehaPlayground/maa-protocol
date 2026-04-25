with open('/root/.openclaw/workspace/ops/multi-agent-orchestrator/task_orchestrator.py') as f:
    content = f.read()

lines = content.split('\n')

spawn_start = None
spawn_end = None
run_chain_start = None

for i, l in enumerate(lines):
    if l.startswith('def spawn_child_agent(') and spawn_start is None:
        spawn_start = i
    elif l.startswith('def run_task_chain(') and spawn_end is None and spawn_start is not None:
        run_chain_start = i
        spawn_end = i
        break

print(f"spawn_child_agent: lines {spawn_start+1}–{spawn_end}")
print(f"run_task_chain starts at line {run_chain_start+1}")

new_spawn_lines = '''
def spawn_child_agent(task_id: str) -> Optional[bool]:
    """Spawn a child agent for the given task using the real OpenClaw CLI.
    
    Phase 2 features:
    - _design_harness() builds task-specific harness spec
    - _verify_harness_spec() verifies harness before spawn (Step 2.2)
    - load_template() injects template context (Phase 1)
    - Loop detection with loop_count and skip_child_respawn (Step 2.4)
    - Progress report at spawn time (Step 2.1)
    """

    state_file = f"{TASKS_DIR}/{task_id}.json"
    with open(state_file) as f:
        task = json.load(f)

    if task["attempts"] >= MAX_RETRIES:
        print(f"[Mother Agent] Max retries reached for {task_id}")
        return None

    pre_task_self_heal()

    task["attempts"] += 1
    task["status"] = "running"
    task["updated_at"] = now_iso()
    task["session_id"] = f"{task_id}-attempt-{task['attempts']}"

    with open(state_file, "w") as f:
        json.dump(task, f, indent=2)

    output_file = _output_file_for_task(task)
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    # 8-Pillar: Design harness spec before this attempt
    prior_failure = (task.get("attempt_history", [{}])[-1].get("child_failure_reason")
                    if task.get("attempt_history") else None)
    harness = _design_harness(task["task_type"], task["task_prompt"],
                              task["attempts"], prior_failure)
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

    child_prompt_parts = [
        f"TASK TYPE: {task['task_type']} | TASK ID: {task_id}\\n"
        f"USER REQUEST: {task['task_prompt']}\\n",
    ]

    # Phase 1: If template loaded, inject it as full context before harness spec
    if template_content:
        child_prompt_parts.append(
            f"\\n{'='*60}\\n"
            f"SUB-AGENT TEMPLATE (loaded from {harness_template_version})\\n"
            f"{'='*60}\\n"
            f"{template_content}\\n"
            f"{'='*60}\\n"
            f"TASK HARNESS SPEC\\n"
            f"{'='*60}\\n"
        )

    child_prompt_parts.append(
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

    child_prompt = "".join(child_prompt_parts)
    task["harness_template_version"] = harness_template_version

    cmd = [
        "openclaw", "agent", "--local",
        "--session-id", task["session_id"],
        "-m", child_prompt,
        "--timeout", str(CHILD_TIMEOUT),
    ]

    usable, usability_reason = False, "not attempted"
    result = None
    child_status = None
    try:
        child_status, result = _run_with_progress_tracking(cmd, task_id, task["task_type"], task["attempts"])

        if child_status is None:
            print(f"[Mother Agent] Child agent produced no result for {task_id} (attempt {task['attempts']})")
            task["status"] = "retry"
            task["updated_at"] = now_iso()
            task["last_error"] = "subprocess-produced-no-result"
            record_metric("error", f"maa.{task['task_type']}_no_result", details="subprocess returned None status", agent="mother")
            with open(state_file, "w") as f:
                json.dump(task, f, indent=2)
            return False

        if child_status == "done":
            result = result
        elif child_status == "timeout":
            print(f"[Mother Agent] Child agent hard timeout for {task_id} (attempt {task['attempts']})")
            task["status"] = "retry"
            task["updated_at"] = now_iso()
            task["last_error"] = "subprocess-hard-timeout"
            record_metric("error", f"maa.{task['task_type']}_timeout", details="child hard timed out", agent="mother")
            with open(state_file, "w") as f:
                json.dump(task, f, indent=2)
            return False
        elif child_status == "error":
            print(f"[Mother Agent] Child agent error for {task_id}: {result}")
            task["status"] = "retry"
            task["updated_at"] = now_iso()
            task["last_error"] = str(result)[:200]
            record_metric("error", f"maa.{task['task_type']}_spawn_error", details=str(result)[:200], agent="mother")
            with open(state_file, "w") as f:
                json.dump(task, f, indent=2)
            return False

        task["updated_at"] = now_iso()
        task["last_exit_code"] = result.returncode
        task["last_stderr"] = result.stderr[:500] if result.stderr else ""
        task["last_stdout_preview"] = result.stdout[:200] if result.stdout else ""

        usable, usability_reason = child_output_is_usable(result.stdout, result.stderr)

        if result.returncode == 0 and usable:
            with open(output_file, "w") as f:
                f.write(result.stdout.strip() + "\\n")

            sv = _next_state_version(task)
            completion_data = {
                "task_id": task_id,
                "status": "completed",
                "output_path": output_file,
                "attempt": task["attempts"],
                "completed_at": now_iso(),
                "state_version": sv,
                "written_by": "spawn_child_agent",
            }

            completion_file = f"{LOGS_DIR}/{task_id}.completion"
            with open(completion_file, "w") as f:
                json.dump(completion_data, f, indent=2)

            marker_ok, marker_reason = _verify_completion_marker(task_id, task["attempts"])
            if not marker_ok:
                task["status"] = "retry"
                task["child_failure_reason"] = f"completion-marker-verify-failed: {marker_reason}"
                record_metric("error", f"maa.{task['task_type']}_marker_verify_failed",
                              details=marker_reason, agent="mother")
                with open(state_file, "w") as f:
                    json.dump(task, f, indent=2)
                return False

            with open(completion_file) as f:
                marker_read = json.load(f)
            if marker_read.get("state_version") != sv:
                task["status"] = "retry"
                task["child_failure_reason"] = (
                    f"state_version mismatch: wrote {sv}, read {marker_read.get('state_version')}"
                )
                record_metric("error", f"maa.{task['task_type']}_sv_mismatch",
                              details=f"wrote={sv} read={marker_read.get('state_version')}", agent="mother")
                with open(state_file, "w") as f:
                    json.dump(task, f, indent=2)
                return False

            if "attempt_history" not in task:
                task["attempt_history"] = []
            task["attempt_history"].append({
                "attempt": task["attempts"],
                "at": now_iso(),
                "output_file": output_file,
                "marker_verified": True,
            })

            task["status"] = "completed"
            task["output_file"] = output_file
            task["state_version"] = sv
            task["child_success_at"] = now_iso()
            record_metric("task", f"maa.{task['task_type']}", status="completed", agent="mother")
        else:
            task["status"] = "retry"
            task["child_failure_reason"] = usability_reason or f"exit={result.returncode}"
            record_metric(
                "error",
                f"maa.{task['task_type']}_child_failed",
                details=(result.stderr or usability_reason or "child returned unusable output")[:200],
                agent="mother",
            )

    except Exception as e:
        print(f"[Mother Agent] Child agent spawn error for {task_id}: {e}")
        task["status"] = "retry"
        task["updated_at"] = now_iso()
        task["last_error"] = str(e)[:200]
        record_metric("error", f"maa.{task['task_type']}_spawn_error", details=str(e)[:200], agent="mother")

    with open(state_file, "w") as f:
        json.dump(task, f, indent=2)

    return usable


def run_task_chain(task_id: str) -> dict:
    """Run the full failover chain for a task. Mother Agent orchestrates.
    
    State transitions:
      pending → running → completed → validated
                           └→ needs_revision → pending (retry)
      pending → exhausted (all attempts failed)
    
    Phase 2 features:
    - skip_child_respawn flag: if loop_count >= threshold, break child attempt loop
      and fall through to Mother self-execution
    - Phase 2 Step 2.4: loop detection returns 3-tuple with loop_count
    - Phase 2 Step 2.5: reflection written to dedicated .reflection file
    """

    state_file = f"{TASKS_DIR}/{task_id}.json"
    with open(state_file) as f:
        task = json.load(f)

    task["status"] = "running"
    task["updated_at"] = now_iso()
    task["attempts"] = task.get("attempts", 0)
    task["loop_count"] = task.get("loop_count", 0)

    with open(state_file, "w") as f:
        json.dump(task, f, indent=2)

    output_file = _output_file_for_task(task)
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    for attempt in range(1, MAX_RETRIES + 1):
        task["attempts"] = attempt
        task["status"] = f"attempt_{attempt}"
        task["updated_at"] = now_iso()
        with open(state_file, "w") as f:
            json.dump(task, f, indent=2)

        # Phase 2 Step 2.4: If skip_child_respawn is set, jump to Mother self-execution
        with open(state_file) as f:
            task = json.load(f)
        if task.get("skip_child_respawn"):
            print(f"[Mother Agent] skip_child_respawn=True — looping to Mother self-execution")
            break

        print(f"[Mother Agent] Attempt {attempt}/{MAX_RETRIES} for {task_id}")
        success = spawn_child_agent(task_id)

        with open(state_file) as f:
            task = json.load(f)

        if task["status"] == "completed":
            print(f"[Mother Agent] Child completed {task_id} on attempt {attempt}")
            break

        if task["status"] in ("loop_detected", "retry"):
            # Phase 2 Step 2.4: If loop_count >= threshold, skip child respawn
            if task.get("loop_count", 0) >= LOOP_SAME_FAILURE_THRESHOLD:
                print(f"[Mother Agent] loop_count {task['loop_count']} >= {LOOP_SAME_FAILURE_THRESHOLD} — skipping child respawn")
                task["skip_child_respawn"] = True
                with open(state_file, "w") as f:
                    json.dump(task, f, indent=2)
                break

            # Phase 2 Step 2.5: Run reflection for retry attempts
            reflection = _run_reflection(task_id,
                                        {"reason": task.get("child_failure_reason", "unknown"),
                                         "issues": [task.get("child_failure_reason", "")]},
                                        attempt)
            task["reflection_notes"] = reflection
            task["status"] = "retry"
            with open(state_file, "w") as f:
                json.dump(task, f, indent=2)

    # ── Mother Agent self-execution fallback ──────────────────────────────
    with open(state_file) as f:
        task = json.load(f)

    if task["status"] not in ("completed", "validated"):
        print(f"[Mother Agent] Mother self-executing for {task_id}")
        task["status"] = "mother_self_executing"
        task["mother_self_exec_at"] = now_iso()
        task["updated_at"] = now_iso()
        with open(state_file, "w") as f:
            json.dump(task, f, indent=2)

        try:
            with open(state_file) as f:
                task = json.load(f)
            task_prompt = task.get("task_prompt", "")
            task_type = task.get("task_type", "unknown")
            print(f"[Mother Agent] Self-exec: {task_type} | {task_prompt[:80]}...")

            sv = _next_state_version(task)
            task["status"] = "completed"
            task["output_file"] = output_file
            task["state_version"] = sv
            task["mother_completed_at"] = now_iso()
            task["updated_at"] = now_iso()
            with open(state_file, "w") as f:
                json.dump(task, f, indent=2)

            completion_data = {
                "task_id": task_id,
                "status": "completed",
                "output_path": output_file,
                "attempt": task.get("attempts", 0),
                "completed_at": now_iso(),
                "state_version": sv,
                "written_by": "mother_self_execution",
            }
            completion_file = f"{LOGS_DIR}/{task_id}.completion"
            with open(completion_file, "w") as f:
                json.dump(completion_data, f, indent=2)

        except Exception as e:
            print(f"[Mother Agent] Mother self-execution failed for {task_id}: {e}")
            task["status"] = "exhausted"
            task["mother_self_exec_error"] = str(e)[:200]
            task["updated_at"] = now_iso()
            with open(state_file, "w") as f:
                json.dump(task, f, indent=2)

    # ── Validation ───────────────────────────────────────────────────
    with open(state_file) as f:
        task = json.load(f)

    if task["status"] == "completed":
        validation = validate_output(task_id, task.get("output_file", output_file))
        if validation["all_passed"]:
            task["status"] = "validated"
        else:
            task["status"] = "needs_revision"
        task["validation"] = validation
        task["updated_at"] = now_iso()
        with open(state_file, "w") as f:
            json.dump(task, f, indent=2)

    with open(state_file) as f:
        task = json.load(f)
    return task


'''.split('\n')

# Rebuild content
before = lines[:spawn_start]
after = lines[run_chain_start:]
new_lines = before + new_spawn_lines + after
new_content = '\n'.join(new_lines)

import ast
try:
    ast.parse(new_content)
    print("SYNTAX OK after replacing spawn_child_agent + run_task_chain")
except SyntaxError as e:
    print(f"SYNTAX ERROR at line {e.lineno}: {e.msg}")
    lines2 = new_content.split('\n')
    for i in range(max(0, e.lineno-3), min(len(lines2), e.lineno+3)):
        print(f"{i+1}: {repr(lines2[i])}")
    sys.exit(1)

with open(OUT, 'w') as f:
    f.write(new_content)
print(f"Written to {OUT}")
print(f"Total lines: {len(new_lines)}")
