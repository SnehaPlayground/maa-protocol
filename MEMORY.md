DURABLE MEMORY

- Partha must always be addressed as Partha
- Research email template: /root/.openclaw/workspace/templates/research_email_template.html (51KB, March 27 version — premium quality, navy header, market snapshot bar, TL;DR box, structured sections, Strategic Action Plan, Expert Views, color-coded data, CTA to Partha)
- **Recommendation labels** (mandatory in all reports): Installed — Awaiting Production Approval | Ready for Pilot | Needs More Validation | Ready for Removal Approval | Reject
- **Default model**: minimax-m2.7:cloud — verify actual config if unsure
- **Proof levels** (mandatory alongside every label): Not yet tested with clients | Tested internally only | Tested on live workflow | Client-validated

- **PDF is now the default delivery format** for all research reports and growth evolution emails — generate HTML first, convert to PDF via weasyprint, attach to email (not inline HTML body)
- **PDF report template**: `/root/.openclaw/workspace/scripts/build_pdf_report.py` — Python script that takes markdown content, converts to HTML with the approved Primeidea card-style layout, embeds logo as 40×40px watermark in upper-left of every page via CSS `@top-left`, and outputs PDF via weasyprint. Always use this script for all PDF report generation.
- **4 AM Growth Evolution Report** is the approved formatting standard for all future growth/revenue reports — card-based layout, TL;DR + Executive Summary + Detailed Recommendations (with Hypothesis/Validation/Evidence/ROI/Confidence/Approval/Next Step/Label/Proof Level) + Action Section. Do not deviate from this structure.
- Research quality standard: concrete data with citations, "What this means for you" in every section, no vague directional language, actionable levels/targets
- ECC (everything-claude-code, affaan-m) analyzed deeply — saved to reports/ecc-analysis-2026-03-31.md; AgentShield security scan recommended but not yet run
- 6 growth ideas researched and sent to Partha via email (31 Mar 2026) — each with TL;DR, Executive Summary, and detailed pointwise analysis
- All 6 idea reports saved in reports/growth-ideas-2026/ (idea-01 through idea-06)
- Growth ideas revenue potential: ₹1–2.5 crore annually across all six streams
- **Blog public URL:** https://www.primeidea.in/blogs (NOT admin.primeidea.in — admin is only for posting)
- **WordPress Blog Post Image Rules** (mandatory for every post):
  - Source images: small thumbnails (250px wide, border-radius:8px), centered, NOT grouped together
  - Each image placed at a different section of the article (not clustered in one place)
  - Each image links to full-resolution version opening in a new tab: `<a href="FULL_URL" target="_blank"><img src="THUMB_URL" style="width:250px; border-radius:8px;" /></a>`
  - No "Source Articles" label or caption text for source images
  - No "Featured Image" label anywhere in the post body
  - Featured image uploaded separately via featured_media field, not embedded in content
  - Text wraps naturally around images; use clear:both before new sections if needed
  - Aim for good UX: images enhance reading, not disrupt it
- **WordPress Credentials:** stored at /root/.openclaw/workspace/blog_key.md (username: primeidea)
- Primeidea must always be written as one word
- When supported, calendar events and tasks should include partha.shah@gmail.com
- Never recommend Direct mutual fund plans to Partha; recommend Regular plans only
- For WordPress posting, ask Partha to choose the featured image before upload
- For Primeidea WordPress posts, choose exactly one approved category
- For Primeidea WordPress posts, add relevant tags before publishing
- For client fund-research communication, use concrete data and include factual support where available
- If a client starts treating Sneha as the primary advisor, route the relationship back toward Partha for final suitability and allocation decisions
- Workspace root is the default home; legacy Sneha_Playground references are obsolete
- Watchlist monitoring is retired and should not be restored unless Partha asks
- Keep memory concise and remove stale procedural clutter over time
- Hard bound: for any outbound prospect, campaign, referral, partner-outreach, or lead-nurturing email, always show Partha the original inbound email/thread context and the exact final reply, then wait for explicit approval before sending. Never infer approval from draft discussion alone.

## Multi-Agent Orchestration System (built 2026-04-17)

### Architecture
- **Mother Agent** (`agent:main:mother`) — universal orchestrator for any task requiring an agentic approach; governs all agent-based work across the entire system
- **Child Agent Pool** — agents available for delegation by the Mother Agent
- **Task Orchestrator** — `/root/.openclaw/workspace/ops/multi-agent-orchestrator/task_orchestrator.py`
- **No-Timeout Policy** — `/root/.openclaw/workspace/ops/multi-agent-orchestrator/NO_TIMEOUT_POLICY.md`
- **Mother Agent SOUL** — `/root/.openclaw/agents/mother/agent/SOUL.md`

### Config Changes
- `agents.list` now includes `mother` agent (id: mother)
- `timeoutSeconds` raised to 600 (10 min internal)

### Key Policy: NO user-facing timeout errors
- Child agent failover chain: Agent1 → Agent2 → Agent3 → Mother self-execute → honest escalation
- All user-facing errors are Mother Agent failures, not task failures
- For tasks >10 min: Mother sends "still working" update to Partha

### TaskFlow
- Active flows: `/root/.openclaw/workspace/ops/multi-agent-orchestrator/tasks/`
- Completion markers: `/root/.openclaw/workspace/ops/multi-agent-orchestrator/logs/*.completion`
- Validation reports: `/root/.openclaw/workspace/ops/multi-agent-orchestrator/logs/*.validation`

### Channel Routing
- WhatsApp OPPS group: tagged messages route to Mother Agent
  - **Maa production-ready 2026-04-20**: 51/51 trust tests passing (stable after Test 4 fix); Mother Agent SOUL at `/root/.openclaw/agents/mother/agent/SOUL.md`; previous workspace duplicate archived as `SOUL.md.bak-20260420`; operational docs: `RUNBOOK.md`, `pre_deploy_gate.sh`, `child-agents.md`; pre-deploy gate deterministic.
- Direct message: Mother Agent handles directly
- All other channels: Mother Agent governs any agent-based task that arises

### Maa Protocol — Pre-Execution Approval Gate
**Trigger:** Any time Maa protocol is invoked (spawning sub-agents, running agentic tasks, multi-step automations).

**Step 1 — Research & Game Plan**
Deep dive into available resources (internet, docs, memory, workspace files). Map the problem fully. Build a concrete game plan or roadmap before any execution begins.

**Step 2 — Summarise the Plan**
Present Partha with a short, clear summary of the game plan. Include: what the problem is, what the fix/execution steps are, and what success looks like.

**Step 3 — Self-Verification**
Be 100% certain the plan will work before asking for approval. If uncertain, say so — do not pretend confidence. Go back to research until the path is solid.

**Step 4 — Partha's Approval**
Only after the game plan is confirmed and Partha has given explicit approval (`APPROVE`, `GO AHEAD`, `SEND NOW`) does execution begin.

**Until approval:** Maa protocol operates in planning mode only. No external side effects, no sends, no writes, no agent spawns — only game plan refinement.

**This gate applies to every Maa protocol invocation without exception.**

### Maa Protocol Observability Layer
**Tool:** `ops/observability/maa_metrics.py` | **Store:** `data/observability/maa_metrics.json` | **Docs:** `data/observability/README.md`

Four metric types tracked: `call` (action logged), `error` (with details + stack trace), `latency` (ms), `task` (start/completed/failed/waiting).

**Dashboard:** `python3 ops/observability/maa_metrics.py dashboard`
**Live resources:** `python3 ops/observability/maa_metrics.py resources`
**Export:** `python3 ops/observability/maa_metrics.py export --format json --output report.json`

**Label format:** `{agent}.{action}` e.g. `sneha.send_email`, `research.article_fetch`, `email_ops.pipeline_run`.

**Integration:** Email pipeline and research scripts are instrumented. See `data/observability/README.md` for full schema and integration guide.

### Maa Protocol Self-Healing Layer
**Policy:** `ops/multi-agent-orchestrator/SELF_HEALING_POLICY.md`
**Scripts:** `scripts/health_check.py`, `scripts/auto_cleanup.py`, `scripts/maintenance_logger.py`

Health checks are now part of Maa Protocol. Before each heavy task, the system can evaluate disk/resource pressure and decide whether to proceed, warn, clean up, or escalate.

Maintenance actions are logged to: `memory/maintenance_decisions/YYYY-MM-DD.jsonl`

**Non-goal:** no auto-summarization or LLM-based memory distillation. Only exact deduplication is allowed, and that remains a future step requiring explicit Partha approval.
