---
name: communication-protocol
description: Single unified entry point for all professional communication operations (email today, WhatsApp/SMS/Signal tomorrow): inbox triage, thread tracking, follow-up detection, sent item review, CC/BCC compliance, and outbound action. Deduplicates processing via memory/thread-state.json. Use when reviewing mailbox activity, monitoring conversations, drafting emails, or converting email handling into repeatable operations. Handles all professional email — for sales-specific workflows, also check sneha-inbound-sales skill and route appropriately.
---

# Communication Protocol — Unified Skill

Treat the mailbox as an active working queue assigned to Sneha. This is the **single entry point** for all email operations — no separate cron should fire email tasks independently.

## Unified Monitoring Schedule

**Monday to Saturday IST:**
- 9:00 AM – 7:00 PM: check every 15 minutes
- 7:00 PM – 9:00 AM: check every hour

**Respect quiet hours:** 10 PM – 7 AM IST unless something is urgent.

---

## Deduplication Protocol (MANDATORY)

Before doing anything else in each email check pass, load `~/.openclaw/workspace/memory/thread-state.json` and compare against current mailbox state.

**State file format:**
```json
{
  "last_run": "ISO timestamp",
  "processed_threads": {
    "<thread_id>": {
      "state": "waiting|drafted|escalated|closed",
      "last_update": "ISO timestamp",
      "action_taken": "string"
    }
  },
  "recent_threads": ["<thread_id>", ...]
}
```

**Deduplication rules:**
1. If a thread has not changed since last check → skip it (no re-processing)
2. If a thread was already escalated/drafted → do not escalate/draft again unless Partha responds
3. If a thread has moved to a new state (e.g., new reply came in) → process only the new state change
4. Always update `memory/thread-state.json` after each pass with new thread states

**How to detect thread changes:**
- Use `gog email search "in:inbox newer_than:2h"` to get threads modified recently
- Compare thread IDs against `processed_threads` in state file
- A thread with a newer `last_update` than our last run = changed

**On each pass:**
1. Read current state from `memory/thread-state.json`
2. Query recent threads from Gmail
3. For each thread: if already processed and unchanged → skip; if new or changed → process
4. After processing, update `memory/thread-state.json` with new thread states
5. Log what was done

---

## Routing: communication-protocol vs sneha-inbound-sales

**Use communication-protocol (this skill) for:**
- Client research requests
- Fund-related queries
- Meeting-setting for existing clients
- Internal coordination
- Follow-up management
- General professional mail triage
- Escalations and alerts

**Use sneha-inbound-sales additionally when:**
- A new inbound lead arrives (prospect not yet qualified)
- Thread is in active sales qualification flow
- Meeting-setting with a new/unqualified prospect

**Rule:** A thread should only be processed by ONE active workflow at a time. If a thread is in sales qualification, let sneha-inbound-sales handle it. If it escalates to a general question, switch to communication-protocol and close the sales thread state.

---

## CC/BCC Rules (Non-Negotiable)

**ALL emails from sneha.primeidea@gmail.com must CC:**
- `partha@primeidea.in` — client-facing and business emails
- `partha.shah@gmail.com` — external and high-priority emails

**Required CC applies to:** client research, fund-related, meeting-setting, advice/suitability, and any email committing Primeidea to a position.

**CC optional:** routine acknowledgments, internal coordination, low-risk follow-ups.

**BCC:** rarely used; only when workflow/compliance requires. Never use BCC to hide anything from Partha.

---

## Outbound Tracking Log

Maintain `~/.openclaw/workspace/data/email/communication-log.md` for all sent emails. This file is generated operational output and should be treated as a log, not as a policy source.

**Format per entry:**
```
[YYYY-MM-DD HH:MM IST] FROM: <account> | TO: <recipient> | CC: <cc> | SUBJECT: <subject> | ACTION: <reply/new/forward> | SUMMARY: <brief>
```

Keep top 50 entries. Archive older ones to `communication-log-archive.md`.

Query sent items: `gog email search "in:sent" --account=sneha.primeidea@gmail.com --limit=N`

---

## Core Responsibilities

### 1. Inbox Triage
Classify threads:
- Reply now
- Draft for approval
- Waiting on other party
- Waiting on Partha
- Archive / no action
- Track for follow-up
- Escalate immediately

By type:
- Routine service / acknowledgment
- Client research request
- Client advice / suitability
- Meeting-setting / relationship
- Follow-up / chase
- Sensitive / risk / complaint
- Internal coordination
- Marketing / newsletter

### 2. Thread-State Awareness
Before drafting:
- Read full thread including sent history
- Identify last meaningful outbound/inbound
- Check if reply already pending
- Check if Partha already answered elsewhere
- Avoid duplicate/contradictory replies
- Do not escalate if Sneha already replied

### 3. Follow-Up Management
Track when:
- Message sent, no reply within expected window
- Someone promised document/action not received
- Thread important to business progress

For closure cases: if resolution claimed but proof pending → waiting, not closed.

---

## Approval Protocol

**ALWAYS confirm with Partha before:**
- Sending any external email (unless standing rule below applies)
- Making calendar commitments
- Giving advice/opinions/promises on his behalf
- Communicating anything sensitive, legal, or financial-advisory

**Standing rules — Partha's pre-approved actions (no confirmation needed):**
- Routine courtesy acknowledgments (one-liners thanking, confirming receipt)
- Simple follow-up emails (status check, document request)
- Internal coordination emails with no external impact
- Re-sending something already Partha-approved

Exception: these standing rules do not override the hard-bound approval rule for prospect, campaign, outreach, referral, partner, or lead-nurturing email. Those always require Partha to see the original thread context and the exact final draft before send.

**For everything else:** Prepare draft, confirm with Partha, wait for go-ahead.

**On Telegram alerts:** Keep concise — who, what, why, recommended next action.

---

## Drafting Rules

- Short, clear, professional, specific about next step
- CC Partha at partha@primeidea.in and/or partha.shah@gmail.com per CC rules
- For client research/fund emails: include data points, performance context, holdings
- Use AMC factsheet URLs when available
- Give directional research view directly
- Tactfully route clients to Partha for suitability/allocation decisions
- Never invent facts, fake actions, overcommit timelines
- No gendered honorifics; use Ji for salutations

---

## Sending Email

All production outbound email must go through:
`/root/.openclaw/workspace/ops/email/send_email_via_gog.py`

Never use raw `gog email send` or raw `gog gmail send` directly for business email.

Mandatory send order:
1. Read full original thread
2. Show Partha the original inbound email or exact thread context when replying externally
3. Show Partha the exact final outbound draft
4. Wait for explicit approval when required
5. Send only through `send_email_via_gog.py`
6. Check sent items before sending to confirm no identical email has already been sent to this recipient recently
7. Verify the sent item for recipient, subject, thread continuity, CC, and readable formatting
8. Log to data/email/communication-log.md

If thread continuity is uncertain, do not send.
If formatting is uncertain, do not send.

---

## Escalation Rules

Notify Partha on Telegram when:
- Email needs his direct attention or decision
- Reply carries material business risk
- Email is urgent, sensitive, or high-stakes
- Someone is waiting specifically on him
- Thread blocked and needs his intervention

---

## Output Modes

Depending on what the situation needs:
- triage summary
- recommended action list
- single best draft
- escalation note for Partha
- follow-up tracker update
- outbound log entry

Prefer the smallest useful output.
