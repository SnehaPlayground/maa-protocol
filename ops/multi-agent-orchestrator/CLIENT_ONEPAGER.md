# MAA PROTOCOL — CLIENT ONE-PAGER
Version: v1.0
Effective: 2026-04-22
Owner: Maa operator

---

## What Is Maa?

Maa (Mother Agent) Protocol is a multi-agent orchestration system. It receives tasks, routes them through specialized AI agents, validates the output, and delivers a finished result, or tells you honestly what happened.

Think of it as a senior executive assistant backed by a team of specialists. One point of contact, one coherent output, zero dropped threads.

---

## What Maa Does

- **Market research** — Daily briefs, sector analysis, competitor tracking
- **Deep research** — Investment theses, company due diligence, regulatory analysis
- **Email & communication** — Professional drafting, client outreach, follow-ups
- **Growth reporting** — Revenue analysis, pipeline reviews, trend reports
- **Custom research** — Anything you need, scoped and delivered

---

## How Errors Are Handled

Maa has a three-layer error recovery system:

1. **Automatic retry** — If one agent fails, the system automatically tries again with corrected instructions (up to 3 attempts)
2. **Mother execution** — If all agents fail, the Mother Agent handles the task directly using full system resources
3. **Honest escalation** — If Mother execution also cannot complete the task, you receive a specific, honest message explaining what was tried, why it failed, and what is needed to proceed

**You will never receive:** "failed", "timed out", or "please try again later." Only a validated result or a specific next step.

---

## How Long It Takes

| Task Type | Typical Duration |
|---|---|
| Market brief | 3–8 minutes |
| Research | 5–15 minutes |
| Email draft | 1–3 minutes |
| Growth report | 5–10 minutes |

Complex or multi-part tasks may take longer. If your task will exceed the typical window, you will receive a "still working" update.

---

## Privacy & Data Isolation

- **Your data is never shared** with other clients — each client operates in a strictly isolated tenant environment
- **No cross-tenant access** — runtime enforcement prevents any client from accessing another client's tasks, data, or outputs
- **No data used for training** — outputs are never used to train models
- **Retention** — task data is retained for 90 days, audit trails for 7 years per financial-grade standards

---

## What Maa Will Never Do

- Fabricate results or present placeholder content as completed work
- Send outbound messages (email, calendar, public posts) without your explicit approval
- Access another client's data or tasks
- Make domain-critical decisions that require a licensed professional, designated approver, or human owner
- Share your confidential information outside your designated tenant environment

---

## Approval & Control

All external actions (sending emails, booking calendar events, posting publicly) require explicit approval from the authorized human approver before execution. You will always see what is being sent and have the final say.

---

## System Health & Reliability

- **Error rate target:** below 5% per task type — circuit breakers protect against higher rates
- **Availability:** 99% target — planned maintenance windows notified 24 hours in advance
- **Continuous monitoring:** system health checked every 15 minutes
- **Daily regression gate:** automated trust tests run every morning at 6 AM IST

---

## Who Operates This

Maa is operated by the designated system owner or operator. The system remains reachable through the configured interaction surface.

For questions, escalations, or new task requests, use the active support or operator channel configured for your deployment.

---

*Maa Protocol — reliable multi-agent orchestration with explicit human control.*
