---
title: LLM Wiki
page_type: source
status: active
sensitivity: internal
confidence: high
last_updated: 2026-04-08
sources:
  - /root/.openclaw/workspace/ops/research/raw/2026-04-08-karpathy-llm-wiki.md
  - https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f
---

# Summary

Andrej Karpathy outlines a pattern where an LLM maintains a persistent markdown wiki that sits between raw source material and later question answering. The key claim is that this creates compounding research value because synthesis, cross-references, and contradictions are maintained over time instead of being rediscovered from scratch during every query.

# Key points

- The central distinction from standard RAG is persistence. Knowledge is compiled into maintained pages instead of being reassembled at query time.
- The proposed system has three layers: immutable raw sources, LLM-maintained wiki pages, and a schema that governs structure and workflow.
- Core operations are ingest, query, and lint.
- `index.md` and `log.md` are presented as lightweight scaling mechanisms before more advanced retrieval tooling is needed.
- The document is intentionally abstract and expects adaptation to local workflow, domain, and risk tolerance.

# Evidence and citations

- The note explicitly contrasts standard RAG with a persistent wiki that is incrementally updated as new sources arrive. Source: raw note section "The core idea".
- It defines a three-layer architecture of raw sources, wiki, and schema. Source: raw note section "Architecture".
- It describes ingest, query, and lint as the core operating motions. Source: raw note section "Operations".
- It identifies `index.md` as content-oriented and `log.md` as chronological. Source: raw note section "Indexing and logging".
- It says the document is only a pattern description and not a concrete implementation. Source: raw note section "Note".

# What this means for Primeidea

This is a strong design pattern for building a compounding research system inside the workspace, especially for article analysis, sector tracking, company pages, and evolving investment themes. It should be used with stricter controls than the note describes, especially around prompt injection, source trust, citation discipline, client sensitivity, and separation from assistant memory.

# Open questions

- Which research domains should be included first: sectors, companies, funds, macros, or business systems?
- How much of the ingest process should be automated versus reviewed each time?
- Should thesis pages remain internal drafts unless explicitly promoted?
- Do we want a periodic lint workflow in phase 2?

# Update notes

- 2026-04-08: Seed source page created as the first entry in the Primeidea Research Wiki.
