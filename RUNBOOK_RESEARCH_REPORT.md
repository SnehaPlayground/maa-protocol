# RUNBOOK: Morning Research Report + Voice Note Protocol
**Effective: 2 April 2026**
**Owner: Sneha / Partha**

---

## Voice Note Pipeline
- Tool: `node /usr/lib/node_modules/openclaw/node_modules/node-edge-tts/bin.js`
- Voice: `en-IN-NeerjaNeural` (Indian English Female, Microsoft Edge TTS)
- Wrapper script: `/root/.openclaw/workspace/scripts/voice_edge.js`
- Always use `--timeout 120000` (2 minutes)
- Output: `/root/.openclaw/workspace/data/reports/report_YYYY-MM-DD.pdf`
- Identity: "Hi, I am Sneha from Primeidea, here with today's key market update."

---

## Identity & Opening
Always introduce at the start:
> "Hi, I am Sneha from Primeidea, here with today's key market update."

---

## Core Objective
- Focus on **why** it matters, not just what happened
- Explain why news, moves, flows, macro, and global events matter for investors
- Tone: calm, confident, practical, encouraging

---

## Primary Content Priority
1. Key important news updates
2. Why these updates matters
3. Executive summary
4. Advisory section
5. Final punch / TL;DR close

---

## Mandatory Text Structure
1. Opening line
2. Executive summary in simple language
3. Top market-moving news and why each one matters
4. Important global and domestic triggers
5. Investor advisory section
6. Final punch close

---

## Writing Rules
- Simple English only, no jargon
- Less "what happened" and "how to trade"
- More "why this matters" for investors
- Motivate disciplined investing; reinforce asset allocation
- Do not sound preachy or like a trading alert
- Ask: *"What is the 20% of information that gives 80% of investor value today?"*

---

## Approval Workflow (Current)
- Weekday 7 AM morning report currently runs in pre-approved scheduled mode
- Live flow: generate HTML report, validate it, generate the local voice briefing, email both the HTML file and audio briefing through the approved sender, and send the same HTML file to Partha on Telegram
- Keep all sends inside the existing approved workflow only
- Any change to recipients, send behavior, or approval mode must be updated here first

---

## Compliance Check (Mandatory Each Day)
- Any missing major news?
- Any unsuitable claim?
- Any internal-only wording left in client version?
- Any disclaimer needed?
- Two versions: Internal vs Client-facing?

---

## Client Safety Rules
- No "For Internal Circulation only" in client version
- Stock/product-specific recommendations → add disclaimer
- Generic market commentary ≠ personal advice
- No speculative trading alert tone

---

## End-of-Report Advisory (Standard)
Remind investors to:
- Stay disciplined
- Follow asset allocation
- Avoid emotional reactions
- Focus on long-term goals
- Review decisions in context, not in panic
