# MAA PROTOCOL — SERVICE LEVEL AGREEMENT
Version: v1.0
Effective: 2026-04-22
Owner: Maa operator / Mother Agent

---

## 1. SERVICE OVERVIEW

Maa (Mother Agent) Protocol is a self-hosted multi-agent orchestration framework. It receives tasks from users or operators, routes them through validated child agents, enforces quality gates, and delivers finished output or an honest escalation.

**Service commitment:** End users never see a timeout, a failure, or a placeholder as the final state. They receive either a validated result or a clear escalation with a next step.

---

## 2. TASK TYPE LATENCY TARGETS

| Task Type | Expected Duration | Notes |
|---|---|---|
| `market-brief` | 3–8 minutes | Daily market report; DL-20 compliant |
| `research` | 5–15 minutes | Deep research; scope-dependent |
| `email-draft` | 1–3 minutes | Professional drafting |
| `growth-report` | 5–10 minutes | Revenue/growth analysis |
| `custom` | Variable | Defined at submission time |

Latency is measured from task submission to validated output reaching the requester.

**Degraded mode:** If error rate exceeds 5% on any label, that label enters degraded mode. New tasks of that type are queued until the circuit breaker resets (rolling 1-hour window).

---

## 3. ERROR RATE TOLERANCE

- **Threshold:** 5% per task type label, per rolling 1-hour window
- **Circuit breaker:** If error rate exceeds 5%, spawning halts for that task type automatically
- **Auto-reset:** When the rolling window expires and error rate drops below 5%, spawning resumes automatically
- **Operator alert:** Circuit breaker trips are surfaced to the operator within 5 minutes

**Error rate formula:**
```
error_rate = failures_in_rolling_window / total_tasks_in_rolling_window
```
Failures include: no result, unusable output, validation failure after all retries, spawn error, timeout.

---

## 4. AVAILABILITY

- **Target:** 99% uptime, measured monthly
- **Planned maintenance windows:** Sundays 2–4 AM IST (if required), notified 24h in advance
- **Unplanned downtime:** Hardware failure, disk full, metrics store corruption — addressed immediately with escalation if recovery exceeds 30 minutes

Availability is calculated as:
```
(total_minutes_in_month - downtime_minutes) / total_minutes_in_month × 100
```

---

## 5. RECOVERY PROCEDURE

### If all child agents fail on a task:

**Step 1 — Automatic retry:** Up to 3 child agents attempt the task with escalating rules

**Step 2 — Mother self-execution:** If all child attempts fail, the Mother Agent executes the task directly with full harness

**Step 3 — Honest escalation to requester/operator:** If Mother self-execution also fails, the requester or operator receives a specific message containing:
- Task description
- What was tried (child agents × 3 + Mother self-execution)
- Why each attempt failed
- What the system needs to proceed (if fixable)
- Estimated time to resolution

**Requesters never receive:** "failed", "timed out", "please try again later."

---

## 6. ESCALATION PATH

| Failure Mode | Response | SLA |
|---|---|---|
| Single task exhausted | Honest escalation with specific reason | Within 1 hour of failure |
| Circuit breaker trip | Operator alerted with affected label | Within 5 minutes of trip |
| Pre-deploy gate failure | Alert with failure names + action required | By next morning |
| Continuous monitor critical | Alert to operator | Within 15 minutes |
| Metrics store unwritable | Alert + pause spawning if sustained | Immediate |
| Disk ≥ 90% | Alert + halt new heavy tasks | Immediate |

---

## 7. DATA RETENTION

| Data Type | Retention Period | Notes |
|---|---|---|
| Metrics store (maa_metrics.json) | 30 days | Rolling window |
| Task state files | 90 days after completion | Then auto-cleaned |
| Completion markers | 90 days after completion | Then auto-cleaned |
| Validation reports | 90 days after completion | Then auto-cleaned |
| Audit trail (jsonl) | 7 years | Financial-grade |
| Email send records | 7 years | Financial-grade |
| Secrets | Rotation-triggered | Not time-based |

---

## 8. TASK OUTCOMES — DEFINITIONS

| Outcome | Meaning |
|---|---|
| `validated` | Task passed all gates, output delivered to the requester |
| `needs_revision` | Validation failed — correction in progress |
| `circuit_open` | Label exceeded 5% error rate — spawning paused |
| `exhausted` | All attempts + Mother self-execution failed — escalated |
| `queued` | Concurrency limit reached — waiting for slot |

---

## 9. CONCURRENCY & THROTTLING

- **Max concurrent child agents:** 4 per operator
- **Queue:** Overflow tasks are queued, not rejected, and processed when slots open
- **Per-tenant rate limits:** Enforced at tenant gate
- **Load shedding:** Tasks exceeding per-tenant quota are rejected with `RateLimitExceeded`

---

## 10. SECURITY & ISOLATION

- **Tenant isolation:** Every client tenant has isolated task paths, logs, and outputs (Option C hierarchical tenancy)
- **Multi-client readiness:** Yes — tenant CRUD and security hardening complete
- **No cross-tenant data access:** Runtime-enforced via TenantPathResolver
- **Approval gate:** All external side-effecting actions (email send, calendar write, public post) require explicit approval from the authorized human approver before execution

---

## 11. OPERATOR RESPONSIBILITIES

The system operator is responsible for:
- Reviewing pre-deploy gate failures (run daily at 6 AM IST)
- Responding to escalation messages within 1 business hour
- Approving external actions flagged by the approval gate
- Running periodic disaster recovery drills (recommended: quarterly)

---

## 12. LIMITATIONS & EXCLUSIONS

- Maa does not guarantee output quality beyond what the validation gates define
- Maa does not make domain-critical human decisions that must remain with the designated operator or licensed professional
- Maa does not access external systems without explicit task scope
- Maa does not fabricate completions — exhausted tasks always escalate honestly
- This SLA does not cover third-party systems (Gmail API, WordPress, etc.) that depend on external uptime

---

## 13. SLA REVIEW

This SLA is reviewed and updated with each major version release (Phase 12 release management). The current version is v1.0, effective 2026-04-22.

Next scheduled review: Before the next major community release or at the operator's request.

---

*Document owner: Mother Agent | Maa deployment*
