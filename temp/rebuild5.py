import ast, sys

OUT = '/root/.openclaw/workspace/ops/multi-agent-orchestrator/task_orchestrator.py'
with open(OUT) as f:
    lines = f.readlines()

spawn_start = None
run_chain_line = None
for i, l in enumerate(lines):
    if l.startswith('def spawn_child_agent('):
        spawn_start = i
    elif l.startswith('def run_task_chain(') and spawn_start is not None:
        run_chain_line = i
        break

print(f"spawn: line {spawn_start+1}, run_task_chain: line {run_chain_line+1}")

# Phase 2 updated spawn_child_agent with all Phase 1+2 features
NEW_SPAWN_BODY = '''def spawn_child_agent(task_id: str) -> Optional[bool]:
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
    write_progress_report(task_id, "child-" + str(task["attempts"]), "start", 0,
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
    rem_str = "\\n".join(["  - " + r for r in reminders]) if reminders else "  (none)"
    success_str = "\\n".join(["  - " + c for c in harness["success_criteria"]])
    gates = harness["verification_gates"]

    child_prompt_parts = [
        "TASK TYPE: " + task["task_type"] + " | TASK ID: " + task_id + "\\n"
        "USER REQUEST: " + task["task_prompt"] + "\\n",
    ]

    # Phase 1: If template loaded, inject it as full context before harness spec
    if template_content:
        child_prompt_parts.append(
            "\\n" + ("=" * 60) + "\\n"
            "SUB-AGENT TEMPLATE (loaded from " + harness_template_version + ")\\n"
            + ("=" * 60) + "\\n"
            + template_content + "\\n"
            + ("=" * 60) + "\\n"
            "TASK HARNESS SPEC\\n"
            + ("=" * 60) + "\\n"
        )

    child_prompt_parts.append(
        "Active Pillars: " + pillars_str + "\\n"
        "Global State Keys: " + ", ".join(harness["global_state_keys"]) + "\\n"
        "Scoped Memory read: " + ", ".join(harness["scoped_memory"]["read"]) + "\\n"
        "Scoped Memory write: " + ", ".join(harness["scoped_memory"]["write"]) + "\\n"
        "Dynamic Reminders (from prior failures):\\n" + rem_str + "\\n"
        "Verification Gates:\\n"
        "  1. Completeness: " + gates[0] + "\\n"
        "  2. Factual Grounding: " + gates[1] + "\\n"
        "  3. Format Compliance: " + gates[2] + "\\n"
        "  4. Quality: " + gates[3] + "\\n"
        "Success Criteria:\\n" + success_str + "\\n"
        "Safety: no external sends without MA pre-approval; no irreversible without sign-off\\n"
        "Escalation: 3+ sources fail->ask MA; irreversible->pause; security->halt+escalate\\n"
        "Progress Reports: write logs/" + task_id + ".progress at start/progress/near_complete/done\\n"
        "OUTPUT PATH: " + task["output_path"] + (task.get("output_ext") or ".txt") + "\\n"
        "IMPORTANT: Return only the final output. No commentary. Write progress reports at checkpoints."
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
            print("[Mother Agent] Child agent produced no result for " + task_id + " (attempt " + str(task["attempts"]) + ")")
            task["status"] = "retry"
            task["updated_at"] = now_iso()
            task["last_error"] = "subprocess-produced-no-result"
            record_metric("error", "maa." + task["task_type"] + "_no_result", details="subprocess returned None status", agent="mother")
            with open(state_file, "w") as f:
                json.dump(task, f, indent=2)
            return False

        if child_status == "done":
            result = result
        elif child_status == "timeout":
            print("[Mother Agent] Child agent hard timeout for " + task_id + " (attempt " + str(task["attempts"]) + ")")
            task["status"] = "retry"
            task["updated_at"] = now_iso()
            task["last_error"] = "subprocess-hard-timeout"
            record_metric("error", "maa." + task["task_type"] + "_timeout", details="child hard timed out", agent="mother")
            with open(state_file, "w") as f:
                json.dump(task, f, indent=2)
            return False
        elif child_status == "error":
            print("[Mother Agent] Child agent error for " + task_id + ": " + str(result))
            task["status"] = "retry"
            task["updated_at"] = now_iso()
            task["last_error"] = str(result)[:200]
            record_metric("error", "maa." + task["task_type"] + "_spawn_error", details=str(result)[:200], agent="mother")
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
                task["child_failure_reason"] = "completion-marker-verify-failed: " + marker_reason
                record_metric("error", "maa." + task["task_type"] + "_marker_verify_failed",
                              details=marker_reason, agent="mother")
                with open(state_file, "w") as f:
                    json.dump(task, f, indent=2)
                return False

            with open(completion_file) as f:
                marker_read = json.load(f)
            if marker_read.get("state_version") != sv:
                task["status"] = "retry"
                task["child_failure_reason"] = (
                    "state_version mismatch: wrote " + str(sv) + ", read " + str(marker_read.get("state_version"))
                )
                record_metric("error", "maa." + task["task_type"] + "_sv_mismatch",
                              details="wrote=" + str(sv) + " read=" + str(marker_read.get("state_version")), agent="mother")
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
            record_metric("task", "maa." + task["task_type"], status="completed", agent="mother")
        else:
            task["status"] = "retry"
            task["child_failure_reason"] = usability_reason or ("exit=" + str(result.returncode))
            record_metric(
                "error",
                "maa." + task["task_type"] + "_child_failed",
                details=(result.stderr or usability_reason or "child returned unusable output")[:200],
                agent="mother",
            )

    except Exception as e:
        print("[Mother Agent] Child agent spawn error for " + task_id + ": " + str(e))
        task["status"] = "retry"
        task["updated_at"] = now_iso()
        task["last_error"] = str(e)[:200]
        record_metric("error", "maa." + task["task_type"] + "_spawn_error", details=str(e)[:200], agent="mother")

    with open(state_file, "w") as f:
        json.dump(task, f, indent=2)

    return usable


'''

new_spawn_lines = [l + "\n" for l in NEW_SPAWN_BODY.rstrip("\n").split("\n")]
new_lines = lines[:spawn_start] + new_spawn_lines + lines[run_chain_line:]
new_content = "".join(new_lines)

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
print(f"Written to {OUT}")
print(f"Total lines: {len(new_lines)}")
