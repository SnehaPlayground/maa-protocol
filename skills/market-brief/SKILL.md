---
name: market-brief
description: Generate, package, and distribute Primeidea live market briefs in premium HTML format. Use when Partha asks for a market brief, live market outlook, intraday market summary, market view, trading day outlook, or wants a Primeidea HTML research note prepared and optionally sent by email or Telegram.
---

# Market Brief

Create Primeidea live market briefs as premium HTML reports, then prepare them for controlled distribution.

## Read these files when needed

- Read `references/market_brief.md` for the full production prompt and section contract.
- Read `references/research_list.md` for the default recipient list.
- Read `assets/research_email_template.html` to preserve the approved Primeidea HTML design language.

## Use this workflow

1. Gather fresh market data from primary or reliable current sources.
2. Build the report as a complete HTML document that follows the production prompt and the approved Primeidea styling.
3. Save generated output under `/root/.openclaw/workspace/data/reports/`.
4. If email delivery is requested, route through the workspace email workflow:
   - use the email-ops skill rules
   - prepare the final HTML file
   - send via `/root/.openclaw/workspace/ops/email/send_email_via_gog.py`
5. If Telegram delivery is requested, send a concise message plus the generated HTML file path or rendered output through the `message` tool.

## Distribution rules

- Treat this as draft-first by default.
- Do not send email without Partha's explicit approval unless it clearly qualifies as routine low-risk communication under workspace policy.
- Before any outbound email send, follow the email-ops workflow and duplicate-send checks.
- Use `references/research_list.md` only as the default distribution list. Confirm overrides from Partha when recipients differ.
- For Telegram delivery, prefer sending a short summary in the message body and attach the generated HTML file when useful.

## File rules

- Keep prompts and recipient lists inside this skill only.
- Keep generated reports out of the skill folder.
- Update the shared template in `assets/research_email_template.html` only when the Primeidea report design itself changes.

## Runner

Use:

```bash
python3 /root/.openclaw/workspace/skills/market-brief/scripts/run_market_brief.py --help
```

Useful modes:

```bash
python3 /root/.openclaw/workspace/skills/market-brief/scripts/run_market_brief.py --review-mode --print-email-command --print-telegram-note
```

This creates:
- an HTML report scaffold in `/root/.openclaw/workspace/data/reports/`
- a review bundle in `/root/.openclaw/workspace/data/email/`
- a prepared email-send command
- a Telegram delivery note

Keep this as a generate + review + send workflow. External sending still requires the workspace approval rules.