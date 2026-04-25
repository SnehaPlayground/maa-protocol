# 2026-04-08 — Primeidea Research Wiki Built

## What happened

Partha reviewed the Karpathy LLM Wiki pattern (gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) and asked me to implement it as a controlled research subsystem.

## What was built

A complete Phase 1 Primeidea Research Wiki at `knowledge/research-wiki/`.

### Core files
- `AGENTS.md` — operating rules and hard boundaries
- `README.md` — overview and usage guide
- `index.md` — navigation index
- `log.md` — append-only activity log
- `PAGE_CONVENTIONS.md` — conventions for all 6 page types (source, company, sector, theme, comparison, thesis)
- `LINT_CHECKLIST.md` — periodic wiki health audit guide
- `INGEST_WORKFLOW.md` — step-by-step source ingest procedure

### Folders created
- `knowledge/research-wiki/sources/`
- `knowledge/research-wiki/companies/`
- `knowledge/research-wiki/sectors/`
- `knowledge/research-wiki/themes/`
- `knowledge/research-wiki/comparisons/`
- `knowledge/research-wiki/theses/`
- `knowledge/research-wiki/templates/`
- `ops/research/raw/` — immutable raw source storage

### Seed content
- First raw source: `ops/research/raw/2026-04-08-karpathy-llm-wiki.md`
- First source page: `sources/2026-04-08-karpathy-llm-wiki.md`
- First theme page: `themes/research-wiki-systems.md`

## Key design decisions
- Hard separation between raw sources, wiki pages, and assistant memory
- All external content treated as data, never instructions
- No secrets, tokens, passwords, or client PII in the wiki
- Wiki pages must never be used to directly trigger external actions
- No autonomous publish or send from wiki content
- Page conventions specify frontmatter, required sections, citation format, and sensitivity rules
- Lint checklist covers: source integrity, citation health, staleness, contradictions, orphans, sensitivity, and secret detection

## Phase 1B complete
- Page conventions written
- Lint checklist written
- Ingest workflow documented
- Log and index updated

## Next steps (Phase 1C ideas, not yet executed)
- Create starter sector pages for asset management, insurance, banking
- Create starter company pages for top AMC, private bank, and insurance names
- Automated lint run when wiki reaches 10+ pages
- Source coverage tracker
- Thesis promotion workflow

---

## 2026-04-08 continued — Phase 1C executed

Phase 1C completed. Added:
- 2 sector pages: asset-management, private-banking
- 4 company pages: HDFC AMC, ICICI Prudential AMC, Nippon India AMC, SBI Mutual Fund
- All pages marked draft, confidence low — require Partha input to promote
- Wiki now at 9 total pages (1 source, 1 theme, 2 sector, 4 company, 0 comparison, 0 thesis)
- Next natural step: Phase 1D or start ingesting real articles to build the wiki
