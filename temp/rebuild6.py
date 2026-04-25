"""Insert missing Phase 2 functions before spawn_child_agent."""
import ast, sys

OUT = '/root/.openclaw/workspace/ops/multi-agent-orchestrator/task_orchestrator.py'
with open(OUT) as f:
    content = f.read()

# Find spawn_child_agent line
idx = content.find('def spawn_child_agent(task_id: str)')
if idx < 0:
    print("ERROR: spawn_child_agent not found")
    sys.exit(1)

# All missing functions to insert
NEW_FUNCTIONS = '''

def _design_harness(task_type, task_prompt, attempt, prior_failure_mode=None):
    """Design the 8-pillar harness for a task attempt. Called before every spawn."""
    pillar_map = {
        "market-brief":   ["P1","P2","P4","P5","P7","P8"],
        "research":       ["P1","P2","P3","P4","P5","P7","P8"],
        "email-draft":    ["P1","P2","P4","P6","P7","P8"],
        "growth-report":  ["P1","P2","P3","P4","P5","P7","P8"],
        "validation":     ["P1","P2","P4","P7"],
        "coder":          ["P1","P2","P4","P7","P8"],
        "executor":       ["P1","P2","P4","P7"],
    }
    active = pillar_map.get(task_type, ["P1","P2","P4","P7","P8"])
    reminders = []
    if prior_failure_mode:
        reminders.append(
            "REMINDER: Previous attempt failed with \\'" + prior_failure_mode + "\\'. "
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
        "coder":          ["Code compiles","tests pass","no security issues flagged","production quality"],
        "executor":       ["Action completed","verification passed","rollback plan on file"],
    }.get(task_type, ["Production-quality output, make Partha impressed"])


def _detect_loop(task):
    """Return (is_loop, loop_reason, loop_count) — loop_count is 0 if no loop."""
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
        return True, "loop: same failure mode (" + a + ")", loop_count + 1
    return False, "", 0


def _run_reflection(task_id, validation, attempt):
    """Write reflection findings for this attempt. Phase 2 Step 2.5."""
    sf = f"{TASKS_DIR}/{task_id}.json"
    with open(sf) as f:
        task = json.load(f)
    issues = validation.get("issues", [])
    failed_gate = (validation.get("completeness") or validation.get("factual_grounding")
                   or validation.get("format_compliance") or validation.get("quality")
                   or validation.get("reason", "unknown"))
    correction = ("Review the failed gate. Do not repeat the same approach."
                  if not issues else
                  "Address these specific issues: " + "; ".join(issues[:3]) + ". "
                  "Revised output must fix all of them.")
    reflection = {
        "at": now_iso(),
        "attempt": attempt,
        "failed_gate": failed_gate,
        "issues_found": issues[:3],
        "correction_directive": correction,
    }
    print("[Mother Agent] Reflection " + task_id + " (attempt " + str(attempt) + "): gate=" + str(failed_gate))
    record_metric("reflection", "maa." + task.get("task_type","unknown") + "_validation_failure",
                  gate=str(failed_gate), attempt=attempt,
                  issues=str(issues[:3]), agent="mother")
    # Phase 2 Step 2.5: Write to dedicated .reflection file for immutable audit trail
    reflection_file = f"{LOGS_DIR}/{task_id}.reflection"
    try:
        with open(reflection_file, "w") as f:
            json.dump(reflection, f, indent=2)
        print("[Mother Agent] Reflection written to " + reflection_file)
    except Exception as e:
        print("[Mother Agent] Could not write reflection file: " + str(e), file=sys.stderr)
    return reflection


def write_progress_report(task_id, agent_label, checkpoint, progress_pct,
                          current_action, findings="", blockers="", next_step="",
                          harness_reminders=None):
    """Write a structured progress report JSON file for this task."""
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
        print("[Mother Agent] Progress report write failed: " + str(e), file=sys.stderr)


'''

# Insert before spawn_child_agent
new_content = content[:idx] + NEW_FUNCTIONS + content[idx:]

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
