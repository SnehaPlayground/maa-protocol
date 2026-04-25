# Child Agent Pool — Specifications

## Overview

The Mother Agent governs a pool of specialist child agents. Each is a constrained, single-purpose agent — fast to spawn, stateless, and output-verified by the Mother Agent's validation gate.

All child agents receive a full **8-Pillar Harness Definition** on spawn (see below). The harness is designed by Mother Agent before every spawn attempt using `_design_harness()`, adjusted based on prior failure modes, and passed to the child agent in the spawn prompt.

All child agents:
- Receive a complete 8-pillar mini-harness on every spawn (role, scoped tools, scoped memory, verification rules, reporting format, success criteria, escalation rules)
- Write structured progress reports to `logs/{task_id}.progress` at defined checkpoints
- Are subject to loop detection — same failure mode on consecutive attempts triggers Mother Agent reflection before respawn
- Use the workspace default model (configured in OpenClaw agents config)
- Have a hard internal timeout (Mother Agent never surfaces this to the end user)
- Write output to a defined path
- Must produce a completion marker
- Are subject to the `child_output_is_usable` gate — no planning narration, no partial output
- Are subject to the circuit breaker — if error rate > 5% in 1h window, spawning halts for that label

---

## 8-Pillar Harness Definition Format

Every child agent is spawned with a full 8-pillar harness spec passed in the prompt. The spec covers:

| Pillar | What It Means for a Child Agent |
|---|---|
| **P1: State & Memory** | Agent knows global state keys (task_id, task_type, attempt, output_path) and scoped memory (read: task_prompt, write: findings/draft_output) |
| **P2: Tool Output Protocol** | Structured output with JSON + human summary; reminders and next-step guidance attached |
| **P3: System Reminders** | Dynamic reminders from prior failures attached to harness; activated if a prior failure mode is detected |
| **P4: Verification & Feedback** | 5 verification gates (completeness, factual grounding, format, quality, channel fit); self-correction after each major action |
| **P5: Orchestration** | Parallelism hints; checkpoint progress reports; non-blocking execution |
| **P6: Safety** | No external sends without pre-approval; no irreversible actions without sign-off; no internal mechanics revealed |
| **P7: Observability** | Structured progress reports at start/progress/near_complete/done; all significant actions logged |
| **P8: Resilience** | Fallback plans on source failure; graceful degradation; loop detection + correction |

---

## Pre-Harnessed Sub-Agent Templates

These are the reusable 8-pillar harness templates used when spawning. The template is selected based on task type and complexity, then customized with task-specific parameters before every spawn.

### Researcher Sub-Agent
**Used for:** market-brief, research, growth-report
**Active Pillars:** P1, P2, P3 (if prior failure), P4, P5, P7, P8
**Scoped Tools:** web search, web fetch, file read, memory search
**Verification:** Source citations required; "What this means for you" in every section; concrete levels/targets (no vague language)
**Success Criteria:** Comprehensive findings, source citations, no [TBD], production-ready quality
**Escalation Rules:**
- If 3+ sources fail → ask Mother Agent for alternative source strategy
- If security issue detected → halt and escalate before continuing
- If quality score below threshold → return detailed failure report

### Executor Sub-Agent
**Used for:** email-draft, calendar actions, file operations
**Active Pillars:** P1, P2, P4, P6, P7, P8
**Scoped Tools:** file read, file write, exec (sandboxed), send/notify
**Verification:** Output check against specification; rollback plan on file
**Success Criteria:** Action completed, verification passed, rollback plan filed
**Escalation Rules:**
- If output would be irreversible → pause and ask Mother Agent
- If action would affect client data → confirm with Mother Agent before proceeding

### Coder Sub-Agent
**Used for:** code generation, testing, script automation
**Active Pillars:** P1, P2, P4, P6, P7, P8
**Scoped Tools:** file read, file write, exec (test runner only — no arbitrary shell)
**Verification:** Code compiles, tests pass, no security issues flagged
**Success Criteria:** Clean code, passing tests, no exposed secrets
**Escalation Rules:**
- If security issue detected → halt and escalate to Mother Agent before continuing

### Verifier Sub-Agent
**Used for:** validation (quality gate for all outputs)
**Active Pillars:** P1, P2, P4, P7
**Scoped Tools:** file read, validation scripts
**Verification:** Multi-gate check; disagreement resolution via re-run
**Success Criteria:** All 5 validation gates passed, issues list empty or minimal, one-line decisive summary
**Escalation Rules:**
- If quality score below threshold → return detailed failure report with specific issues

### Communicator Sub-Agent
**Used for:** user-facing summaries, clarifications, email drafting
**Active Pillars:** P1, P2, P4, P6, P7
**Scoped Tools:** memory search, draft preparation, send/notify (with approval)
**Verification:** The user can understand the output; no confusion; no misrepresentation; no internal details leaked
**Success Criteria:** Clear, accurate, appropriately scoped message
**Escalation Rules:**
- If message involves sensitive context → verify with Mother Agent before sending

### Orchestrator Sub-Agent
**Used for:** very large decomposed tasks requiring multiple sub-agents
**Active Pillars:** All 8 (full coordination harness)
**Scoped Tools:** task orchestration, spawn request, metric record, progress tracking
**Verification:** All sub-tasks completed, results aggregated, no conflicts
**Success Criteria:** All sub-agent results merged coherently, final output ready for delivery
**Escalation Rules:**
- If sub-task conflict detected → escalate to Mother Agent with conflict report
- If any sub-task exhausts → alert Mother Agent immediately

---

## Pool Registry

### market-brief
| Field | Value |
|---|---|
| Spawn label | `market-brief` |
| Internal timeout | 600s |
| Output dir | `data/reports/` |
| Output format | HTML + PDF |
| Completion marker | Required (`{task_id}.completion`) |
| Validation criteria | TL;DR, Executive Summary, charts/tables, data citations, CTA |

### research
| Field | Value |
|---|---|
| Spawn label | `research` |
| Internal timeout | 600s |
| Output dir | `data/reports/` |
| Output format | Markdown → HTML → PDF |
| Completion marker | Required |
| Validation criteria | Source citations, factual grounding, "What this means for you" section, no vague language |

### email-draft
| Field | Value |
|---|---|
| Spawn label | `email-draft` |
| Internal timeout | 300s |
| Output dir | `data/email/drafts/` |
| Output format | JSON (`{to, subject, body_text, body_html, classification, send_now}`) |
| Completion marker | Required |
| Validation criteria | Valid JSON, correct schema fields, no placeholder [TBD] values, appropriate tone |

### growth-report
| Field | Value |
|---|---|
| Spawn label | `growth-report` |
| Internal timeout | 600s |
| Output dir | `data/reports/` |
| Output format | Markdown → PDF |
| Completion marker | Required |
| Validation criteria | 4 AM Growth Evolution Report format — TL;DR + Executive Summary + Detailed Recommendations (with Hypothesis/Validation/Evidence/ROI/Confidence/Approval/Next Step/Label/Proof Level) + Action Section |

### validate
| Field | Value |
|---|---|
| Spawn label | `validate` |
| Purpose | Quality gate — Mother Agent spawns this to validate child output |
| Internal timeout | 120s |
| Output | `.validation` JSON file written to `logs/` |
| Validation criteria | Completeness, factual grounding, format compliance, quality, channel fit |

---

## Agent Spawn Protocol

When the Mother Agent spawns a child agent:

1. **Submit task** → writes `tasks/{task_id}.json`
2. **Increment attempts** → updates `task.json`
3. **Circuit breaker check** → halt if error rate > 5% for this label in 1h window
4. **Load shed check** → queue if 4 children already running
5. **Run health check** → pre-task self-heal
6. **Spawn child agent** → `openclaw agent --local --session-id {session_id} -m {prompt} --timeout {timeout}`
7. **Collect output** → pipe stdout to output file
8. **Run usability gate** → `child_output_is_usable()` — rejects partial output
9. **Write completion marker** → `logs/{task_id}.completion` with state_version, attempt, timestamp
10. **Read-your-own-write** → verify marker persisted correctly
11. **Run validation agent** → quality gate on the output file
12. **Update task state** → `status: completed | validated | needs_revision | exhausted | circuit_open`
13. **Queue drain** → after child completes, start next queued task if any

---

## Output File Naming Convention

```
{output_dir}/{task_type}-{unix_ts}-{short_uuid}.{ext}
```

Examples:
```
data/reports/market-brief-1713600000-a1b2c3.html
data/reports/research-1713600001-d4e5f6.md
data/email/drafts/email-draft-1713600002-g7h8i9.json
```

Completion markers always go to `logs/{task_id}.completion`.
Validation reports always go to `logs/{task_id}.validation`.

---

## Error Classification

| Error Type | Child Response | Mother Agent Response |
|---|---|---|
| Subprocess failed (exit ≠ 0) | Retry up to 3x | Self-execute if all children fail |
| Usable-output gate failed | Retry with same child | Respawn with fix directive |
| Hard timeout (600s) | Treat as unusable output | Retry |
| Validation file missing | Fail validation | Retry or escalate |
| Validation JSON invalid | Fail validation | Retry or escalate |
| Circuit open (>5% error rate) | Abort spawn | Mark task circuit_open, alert the operator |
| Disk critical pre-task | Abort spawn | Alert the operator, pause new tasks |

---

## Adding a New Child Agent Type

To add a new agent type to the pool:

1. **Define task type** in `TASK_TYPES` dict in `task_orchestrator.py`
2. **Add to child-agents.md pool registry** (this file)
3. **Create output spec** in the pool registry above
4. **Add validation criteria** — specify what "complete and valid" means
5. **Register in SOUL.md** under "Task Types I Govern"
6. **Add regression test** if applicable
