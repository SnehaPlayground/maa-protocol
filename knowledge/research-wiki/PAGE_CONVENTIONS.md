# Research Wiki Page Conventions

Purpose

This file defines standard conventions for creating and maintaining pages in the Primeidea Research Wiki. Follow these when ingesting sources, creating topic pages, or updating existing content.

---

## General frontmatter

Every substantive page must include this frontmatter block at the top:

```yaml
---
title: <Page title>
page_type: <source | company | sector | theme | comparison | thesis>
status: <draft | active | superseded>
sensitivity: <public | internal | confidential | client-sensitive>
confidence: <low | medium | high>
last_updated: <YYYY-MM-DD>
sources:
  - <relative/path/or/url>
---
```

Rules:
- `title` must match the filename conceptually but can be more readable
- `page_type` determines which folder the page lives in
- `status` defaults to draft for new pages unless explicitly promoted
- `sensitivity` must be set before the page goes active
- `confidence` reflects the strength of evidence, not the importance of the topic
- `sources` must list every source that contributed material to this page

---

## Source page conventions

Filename format: `YYYY-MM-DD-<short-slug>.md`
Location: `knowledge/research-wiki/sources/`

Required sections:
1. Summary — what this source is and why it matters
2. Key points — numbered or bulleted, plain language
3. Evidence and citations — direct quotes or paraphrases with source location
4. What this means for Primeidea — operational or research relevance
5. Open questions — what is unresolved or uncertain
6. Update notes — chronological record of changes

Confidence guidance:
- High: direct, verifiable, multi-source, recent
- Medium: single source, plausible, some age, not contradicted
- Low: indirect, unverified, old, or disputed

---

## Company page conventions

Filename format: `<company-name>.md` in lowercase kebab-case
Examples: `hdfc-bank.md`, `icici-prudential-amc.md`, `tata-motors.md`
Location: `knowledge/research-wiki/companies/`

Required sections:
1. Summary — what the company does, market position, key facts
2. Business snapshot — revenue scale, key segments, ownership structure
3. Key points — 5 to 8 important facts or observations
4. Evidence and citations — with source links
5. What this means for Primeidea — relevance to research, clients, or sectors
6. Open questions — unresolved items, areas needing more evidence
7. Update notes — chronological record

Style:
- Factual and concise
- No investment advice or suitability claims
- Prefer quantitative facts with dates
- Flag estimates clearly as estimates

---

## Sector page conventions

Filename format: `<sector-name>.md` in lowercase kebab-case
Examples: `asset-management.md`, `private-banking.md`, `pharmaceuticals.md`
Location: `knowledge/research-wiki/sectors/`

Required sections:
1. Summary — sector definition, size, structure
2. Sector structure — key segments, regulatory framework, major players
3. Key points — 5 to 10 important facts or trends
4. Evidence and citations — with source links
5. What this means for Primeidea — implications for research, distribution, advice
6. Open questions — what is uncertain or developing
7. Update notes — chronological record

Style:
- Structural clarity is more important than length
- Include regulatory context for regulated sectors
- Flag emerging risks or opportunities explicitly

---

## Theme page conventions

Filename format: `<theme-name>.md` in lowercase kebab-case
Examples: `nps-reform.md`, `esm-provisions.md`, `insurance-distribution.md`
Location: `knowledge/research-wiki/themes/`

Required sections:
1. Summary — what the theme is and why it is significant
2. Key points — 5 to 10 important facts or developments
3. Evidence and citations — with source links
4. What this means for Primeidea — business, research, or client implications
5. Open questions — unresolved or developing aspects
6. Update notes — chronological record

Style:
- Themes should be broad enough to be useful across multiple sources
- Avoid creating a new theme page for a single isolated development
- Promote a topic to theme page when it appears in at least two sources

---

## Comparison page conventions

Filename format: `<items-compared>.md` in lowercase kebab-case
Examples: `nps-vs-apy.md`, `ulip-vs-term-insurance.md`, `hdfc-vs-icici-pvtbank.md`
Location: `knowledge/research-wiki/comparisons/`

Required sections:
1. Summary — what is being compared and why
2. Comparison framework — criteria used
3. Key points — point-by-point comparison
4. Evidence and citations — with source links
5. What this means for Primeidea — which option is more relevant and under what conditions
6. Open questions — what needs more evidence
7. Update notes — chronological record

Style:
- Be precise about the basis of comparison
- Do not draw conclusions on behalf of clients
- Present trade-offs clearly

---

## Thesis page conventions

Filename format: `<thesis-name>.md` in lowercase kebab-case
Examples: `it-services-global-demand.md`, `india-capex-cycle.md`, `bFSI-inclusion.md`
Location: `knowledge/research-wiki/theses/`

Required sections:
1. Summary — the core thesis in one to two sentences
2. Thesis — the full argument with reasoning
3. Supporting evidence — specific facts, data points, citations
4. Risks and counters — what could challenge or undermine the thesis
5. What this means for Primeidea — research direction, client relevance, opportunity
6. Open questions — what remains to be validated
7. Update notes — chronological record

Status rules:
- thesis pages should almost always start as draft
- promote to active only after at least two corroborating sources and Partha review
- supersede rather than delete when a thesis is overturned

Style:
- Be explicit about assumptions
- Distinguish between evidence and interpretation
- Flag confidence level honestly

---

## Cross-referencing

When one wiki page references another, use a relative markdown link:

```
See [Theme page](themes/research-wiki-systems.md)
```

When referencing a source, include the source page link:

```
Source: [LLM Wiki source](sources/2026-04-08-karpathy-llm-wiki.md)
```

---

## Naming rules

- Always use lowercase kebab-case filenames
- Dates in filenames use YYYY-MM-DD format
- Do not use spaces, special characters, or uppercase in filenames
- Keep filenames short but descriptive

---

## Writing style

- Simple English throughout
- Short to medium sentences
- Plain words over jargon
- Warm and professional tone
- No unsubstantiated claims
- No dramatic language
- No marketing language

---

## Updating existing pages

When updating a page:
1. Add a note in Update Notes with date and what changed
2. Update `last_updated` in frontmatter
3. If confidence or status changes, update those fields
4. If new sources are involved, add them to the sources list
5. Preserve the prior content in Update Notes rather than overwriting silently
6. If the new view directly contradicts the old view, preserve both and label the contradiction explicitly

---

## Orphan page rule

A page with no inbound links from any other page is an orphan. If a page is orphaned:
- either it should be linked from a relevant parent page, or
- it should be flagged in the log as potentially stale, or
- it should be removed

The log should be checked for orphan flags during lint.

---

## Draft threshold

A page should move from draft to active only when:
- at least one credible source is cited
- key sections are populated with real content
- the page has been reviewed or Partha has approved it
- confidence is assessed as at least medium

---

## Sensitivity rules

- Public: suitable for any distribution
- Internal: for Primeidea internal use only
- Confidential: restricted to Partha and direct team
- Client-sensitive: contains information that could affect client portfolios or relationships; requires Partha review before any use in communication

---

## Citation format

For web sources:
```
- <claim or observation>. Source: <page title> (<URL>) — retrieved YYYY-MM-DD
```

For internal sources:
```
- <claim or observation>. Source: <source page path>
```

For derived synthesis:
```
- <synthesized claim>. Synthesized from: <source 1>, <source 2>
```

---

## Logo and branding

Do not embed images in wiki pages unless Partha specifically requests it. Text-based descriptions are preferred for portability and auditability.
