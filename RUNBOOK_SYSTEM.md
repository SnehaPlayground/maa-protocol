SYSTEM RUNBOOK

PURPOSE

Maintain reliable, read-mostly oversight of workspace health, automation health, and operational readiness.

DAILY CHECKS

Daily read-only system scan at 1:00 AM IST covering:
- disk state
- basic security posture
- OpenClaw status
- updates and package health
- overall system functionality

AUTOMATIONS

- Daily Prime Research Outlook at 7:00 AM IST
- Daily Castle healthcheck at 2:00 AM IST if this automation remains desired

MONITORING RULES

- Proactively identify issues that are safe to diagnose internally
- Alert Partha when action, approval, or meaningful attention is required
- Do not escalate minor technical friction unless it affects outcomes, security, or reliability

SAFE SELF-SERVICE ACTIONS

Allowed without approval:
- read-only checks
- diagnostics
- non-destructive investigation
- documentation updates
- drafting remediation plans

APPROVAL REQUIRED

Ask before:
- destructive maintenance
- deleting files
- changing live system behavior
- rotating credentials
- modifying public-facing services
- making external notifications unless already part of a standing approved workflow

INCIDENT HANDLING

When something breaks:
1. identify scope
2. check whether it is local, credential, network, dependency, or service related
3. attempt safe diagnosis
4. document findings
5. notify Partha only when there is a real decision, risk, or impact

RETIREMENT RULE

Do not resurrect retired systems such as watchlist monitoring unless Partha explicitly requests it.
