Email Operations Skill

Purpose

Use the local workspace email pipeline to check Gmail, classify emails, prepare drafts, and send only approved or low-risk replies.

Files

- /root/.openclaw/workspace/ops/email/email_pipeline.py
- /root/.openclaw/workspace/ops/email/run_email_pipeline.sh
- /root/.openclaw/workspace/data/email/email_pipeline_output/latest_summary.txt
- /root/.openclaw/workspace/data/email/email_pipeline_output/latest_email_actions.json
- /root/.openclaw/workspace/ops/email/email_formatter.py
- /root/.openclaw/workspace/ops/email/send_email_via_gog.py

Rules

- Always run the pipeline before answering a "check email" request
- Read latest_summary.txt first
- Read latest_email_actions.json when details are needed
- Never auto-send advice, investment views, suitability, research emails, or campaign/prospect/outreach emails
- Only clearly low-risk emails may be sent without approval
- Use send_email_via_gog.py for all outgoing emails
- Never use raw gog gmail send directly for structured emails
- Never use raw gog email send directly for business email
- HTML emails must go through email_formatter.py via send_email_via_gog.py
- For any prospect, campaign, referral, partner-outreach, or lead-nurturing email: always show Partha the original inbound email/thread context and the exact final draft before send
- Before any outbound send, always check sent items to confirm no identical email has been sent to the same recipient recently
- After every external send, verify the sent item for recipient, CC, subject, thread continuity, and readable formatting before confirming success

Allowed low-risk examples

- thanks
- acknowledgement
- received, will review
- meeting confirmation
- simple document request

Needs approval

- Mutual Funds Schemes
- Direct Equity Stocks
- SIP advice
- PMS
- allocation
- suitability
- insurance recommendations

Typical workflow

1. Run /root/.openclaw/workspace/ops/email/run_email_pipeline.sh
2. Read latest_summary.txt
3. If user asks for details, read latest_email_actions.json
4. If user approves a send, use send_email_via_gog.py at /root/.openclaw/workspace/ops/email/send_email_via_gog.py
5. Verify the sent item after send
6. Log and summarize what was done

Name etiquette

- Use "Ji" after the name, never before
- Correct: Dear Rrajal Ji
- Incorrect: Dear Ji Rrajal

- If name unclear, do not use Ji
- If formal unknown, use: Respected

Signature rules

- Never include any sign-off name or signature block in body if formatter adds signature
- Only one signature allowed
- Canonical signature for active system paths: `Sneha | Primeidea.in`
- Do not force decorative signature style when Partha prefers a simpler human draft
- If the formatter adds signature, do not duplicate it

When extracting contact:
- remove prefixes like Mr, Mrs, Shri, Ji
- normalize name
- apply Ji only at output stage

MANDATORY EMAIL WORKFLOW

This skill is the only allowed workflow for email operations.

Do not bypass this skill by using raw gog send commands.

For any email task, follow this order:

1. Resolve recipient using contacts or Gmail history
2. Draft body only
3. Validate body
4. Format body
5. Send using /root/.openclaw/workspace/ops/email/send_email_via_gog.py
6. Before sending, check sent items to confirm no identical email has already been sent to this recipient recently
7. Log action

HARD BAN

The following direct actions are not allowed:
- raw `gog gmail send`
- raw `gog email send`

If the assistant is about to use either raw send path, stop and route through this skill instead.

CONTACT RULES

- Use Google Contacts only to resolve recipient details
- Do not send immediately after contact lookup
- After contact resolution, continue through validation and formatting

DEFAULT SEND POLICY

- Draft first by default
- Do not send immediately unless user explicitly says "send now"
- Even when user says "send now", still validate and format before send
- For anything emotional, unusual, personal, promotional, factual, advisory, prospecting, or campaign-related, prefer draft-first unless clearly low-risk
- For campaign/prospect/outreach replies, do not send until Partha has seen both the original thread context and the exact final draft
