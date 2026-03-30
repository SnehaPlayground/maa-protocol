# Evolution Protocol — Skill Upgrade System (Partha-First)

## Purpose
Sneha scouts and evaluates new skills to improve her capabilities — but installs only after Partha's explicit approval.

## Core Principles
- **Partha decides** — Never install a skill without asking first
- **Fit first** — Only propose skills that genuinely serve Partha's work
- **No bloat** — Better one well-chosen skill than five half-integrated ones
- **Transparent** — Always show the full approval list with reasons

## The Process

### PHASE 1 — SCOUT (On instruction only)
1. Run `clawhub explore` and `clawhub search` for relevant keywords
2. Log findings to `memory/evolution-log.md`
3. Prepare approval list for Partha

### PHASE 2 — EVALUATE
For each candidate, assess:
- **Relevance:** Does it solve a real gap in current skill set?
- **Quality:** License, active maintenance, reviews
- **Dependencies:** API keys, system packages, cost
- **Integration effort:** How hard to wire into existing workflows?
- **Duplication:** Already covered by something existing?

### PHASE 3 — APPROVAL LIST
Present to Partha with:
- Skill name
- What it does (one line)
- Why it would help Partha
- Cost/dependencies
- Await explicit yes before installing

### PHASE 4 — INSTALL (Only after approval)
1. `clawhub install <slug> --workdir /root/.openclaw/workspace --dir skills`
2. Read SKILL.md fully
3. Update TOOLS.md with new capability
4. Log to `memory/evolution-log.md`
5. Report completion to Partha

## Keywords to Scout (On Partha's Instruction)
- financial analysis, Indian market, NSE BSE, equity research
- content writing, blog, SEO, publishing
- productivity, email, calendar
- PDF generation, document, report generation

## Running the Protocol
- **On-demand only** — When Partha says "evolve", "check for upgrades", or "scout skills"
- **No autonomous scouting** — Always present list before any action
