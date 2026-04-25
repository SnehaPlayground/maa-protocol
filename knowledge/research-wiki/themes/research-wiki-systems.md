---
title: Research Wiki Systems
page_type: theme
status: active
sensitivity: internal
confidence: medium
last_updated: 2026-04-08
sources:
  - knowledge/research-wiki/sources/2026-04-08-karpathy-llm-wiki.md
---

# Summary

A research wiki system is a persistent, source-backed knowledge layer that sits between raw documents and later analysis. Instead of answering every question directly from raw source retrieval, the system accumulates structured understanding over time through maintained markdown pages.

# Key points

- The main benefit is compounding synthesis. Each new source can improve topic pages instead of living as an isolated summary.
- The core building blocks are raw source storage, generated wiki pages, and an operating schema.
- Basic operating motions are ingest, query, and lint.
- This model is especially useful when a body of knowledge grows over weeks or months and the same entities, themes, and questions recur.
- In Primeidea's environment, the pattern is promising for research use but must be constrained by privacy, citation, and workflow controls.

# Evidence and citations

- A persistent markdown wiki maintained by the LLM is the core proposal. Source: `sources/2026-04-08-karpathy-llm-wiki.md`
- The system gains value because synthesis and contradictions are retained across time. Source: `sources/2026-04-08-karpathy-llm-wiki.md`
- The original note leaves implementation details intentionally open, which means controls must be defined locally. Source: `sources/2026-04-08-karpathy-llm-wiki.md`

# What this means for Primeidea

This can become a durable internal research layer for sectors, companies, themes, and investment implications. It can reduce repeated analysis effort and improve continuity across article-driven research sessions. However, it should remain separate from assistant memory, client communication, email workflows, and any sensitive credentials.

# Open questions

- Should we create standard page families for sectors, companies, and thesis pages before ingesting more material?
- Should all new source pages start as draft and be promoted later, or should simple source summaries go active immediately?
- What should be the trigger for creating a dedicated thesis page versus only updating a theme page?

# Update notes

- 2026-04-08: Initial theme page created from the Karpathy LLM Wiki note.
