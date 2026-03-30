Email Operations Skill

Purpose

Use the local workspace email pipeline to check Gmail, classify emails, prepare drafts, and send only approved or low-risk replies.

Files

- /root/.openclaw/workspace/email_pipeline.py
- /root/.openclaw/workspace/run_email_pipeline.sh
- /root/.openclaw/workspace/email_pipeline_output/latest_summary.txt
- /root/.openclaw/workspace/email_pipeline_output/latest_email_actions.json
- /root/.openclaw/workspace/email_formatter.py
- /root/.openclaw/workspace/send_email_via_gog.py

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

1. Run /root/.openclaw/workspace/run_email_pipeline.sh
2. Read latest_summary.txt
3. If user asks for details, read latest_email_actions.json
4. If user approves a low-risk send, use send_email_via_gog.py
5. Log and summarize what was done
