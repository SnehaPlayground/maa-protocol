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
- Never auto-send advice, investment views, suitability, or research emails
- Only low-risk emails may be sent without approval
- Use send_email_via_gog.py for all outgoing emails
- Never use raw gog gmail send directly for structured emails
- HTML emails must go through email_formatter.py via send_email_via_gog.py

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
4. If user approves a low-risk send, use send_email_via_gog.py at /root/.openclaw/workspace/ops/email/send_email_via_gog.py
5. Log and summarize what was done

Name etiquette

- Use "Ji" after the name, never before
- Correct: Dear Rrajal Ji
- Incorrect: Dear Ji Rrajal

- If name unclear, do not use Ji
- If formal unknown, use: Respected

Signature rules

- Never include name in body if formatter adds signature
- Only one closing allowed
- Always end with:
  Warm regards,
  Sneha🥷 | https://Primeidea.in

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
6. Log action

HARD BAN

The following direct action is not allowed:
- raw `gog gmail send`

If the assistant is about to use raw `gog gmail send`, stop and route through this skill instead.

CONTACT RULES

- Use Google Contacts only to resolve recipient details
- Do not send immediately after contact lookup
- After contact resolution, continue through validation and formatting

DEFAULT SEND POLICY

- Draft first by default
- Do not send immediately unless user explicitly says "send now"
- Even when user says "send now", still validate and format before send
- For anything emotional, unusual, personal, promotional, or factual, prefer draft-first unless clearly low-risk
