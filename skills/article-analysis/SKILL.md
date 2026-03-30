---
name: article-analysis
description: Article-only subworkflow for clean source-grounded interpretation, takeaways, blog-ready writing, LinkedIn drafts, and WhatsApp summaries. Use when Partha wants analysis and communication outputs without investment research. Prefer `research-context` when the output path is not yet decided.
---

# Article Analysis

Use this as the article-only subworkflow beneath `research-context` when Partha wants interpretation, communication, or publishing outputs without market-research layering.

## Input handling

Accept UTF-8 text, PDF, DOCX, image, screenshot, clipping, or scanned PDF.
**MANDATORY FIRST STEP for images:** Run OCR (tesseract) on the image before analyzing or describing its content. Do not describe an image without extracting its text first.
Detect the article language and produce outputs in that language unless Partha asks otherwise.
If OCR quality is weak, body text is incomplete, or contradictions prevent safe analysis, stop and ask for a clearer source.

## Core rules

- Paraphrase all content.
- Allow direct quotes only up to 20 words each, maximum 3 quotes total.
- Omit speculation.
- Flag unclear statistics, unnamed sources, and unresolved ambiguities.
- Normalize names, units, and currency.
- Do not introduce new facts.

## Verification workflow

1. Extract a fact list: names, dates, figures, locations.
2. If article length is greater than 200 words, build a claim-to-evidence check internally by mapping each key assertion to a short supporting quote and paragraph or line reference.
3. If article length is 200 words or less, skip the claim-to-evidence table and expand the fact list with short direct quotes where useful.
4. Confirm that numbers match the article, names are consistent, units and currency are normalized, and tense is consistent.
5. Record LinkedIn word count and hard-stop at 170 words maximum.

## Required outputs

Present outputs in this exact order unless Partha asks for a narrower format.

### 0. Pre-Delivery Quality Checklist (Mandatory)

Before presenting any outputs, complete and verify:
- [ ] All data points cross-checked against source
- [ ] Each section within its defined word count limit
- [ ] Claim-to-evidence table built (for articles >200 words)
- [ ] Confidence score assigned to the analysis
- [ ] Residual uncertainties noted
- [ ] All numbers, names, units normalized
- [ ] No invented facts, no unsupported claims

If any check fails, fix before presenting. Do not deliver substandard output and fix later.

### 1. Key Takeaways (Standard Format)

Include:
- Executive Summary in Markdown bullets
- TL;DR in 1 to 2 sentences

Rules:
- Executive Summary maximum 200 words
- Use 6 to 10 bullets when supported
- If the article cannot support 6 distinct points, allow 4 to 5 bullets
- Cover findings, causes, impacts, and next steps when present

### 2. Key Takeaways (WhatsApp Format)

Put the entire WhatsApp output inside a single Markdown code block.

Rules:
- No leading spaces
- No Markdown headings
- Each bullet starts with an emoji
- Use only *bold* and _italic_ formatting tokens
- Include Executive Summary and TL;DR together in the same code block
- Keep it concise and forwarding-friendly

### 3. Detailed Breakdown

Provide a step-by-step breakdown of the article flow using standard Markdown bullets.
Maximum 400 words.

### 4. Humanized Blog Post

Write as a polished business blog writer.
Keep it human, natural, professional, readable, and grounded only in the source article.

The blog package must include ALL of the following as part of every deliverable:

**SEO Title:** [One compelling title, max 60 characters]
**Meta Description:** [One concise description, max 155 characters]
**Slug:** [URL-friendly slug based on title]
**Category:** [Exact one from approved list — see WordPress rules below]
**Tags:** [4 to 8 relevant tags — see rules below]
**Content:** [Full blog article body]

Rules for the article body:
- Default length: 350 to 700 words unless Partha asks otherwise
- Do not paste keyword lists or hashtag blocks into the article body
- Prefer a strong factual hook in the opening paragraph
- End with a natural concluding paragraph, not a social-media CTA
- Do not sound robotic, list-heavy, or SEO-stuffed
- Maintain source-grounded context only; do not add unsupported outside claims

Rules for SEO elements — ALL MANDATORY for every blog package:
- SEO title, meta description, slug, category, and tags are never optional — always include them
- Do not include the featured image concept prompt unless Partha specifically asks for it

## WordPress category and tag rules

For every blog post prepared for WordPress publishing, choose exactly one primary category from this approved list only:
- Financial Planning
- Insurance
- Legacy & Inheritance
- Mediclaim
- Retirement Planning
- Tax Planning
- Wealth Management

Category selection rules:
- Pick the single best-fit category based on the article's main reader intent, not every side topic mentioned.
- If the article is primarily about investments, markets, asset allocation, portfolio positioning, savings growth, or wealth creation, use Wealth Management.
- If the article is primarily about retirement corpus, retirement income, pension planning, or post-retirement lifestyle funding, use Retirement Planning.
- If the article is primarily about tax-saving, deductions, exemptions, tax treatment, or tax-efficient planning, use Tax Planning.
- If the article is primarily about life cover, general insurance, protection products, or risk cover, use Insurance.
- If the article is primarily about health insurance, hospitalization cover, claim structure, or medical protection, use Mediclaim.
- If the article is primarily about succession, wills, nominees, estate transfer, family settlement, or inheritance continuity, use Legacy & Inheritance.
- If the article is primarily about budgeting, long-term financial goals, cash-flow planning, debt discipline, or broad personal finance decision-making, use Financial Planning.
- Do not assign multiple categories.
- Do not leave the post uncategorized.

Tag rules:
- Add relevant tags to every post.
- Use 4 to 8 tags by default.
- Tags should reflect the article's topic, audience intent, products, risks, and important named concepts when clearly supported by the article.
- Prefer short, clean tag phrases.
- Avoid duplicate tags, vague filler tags, and tags unsupported by the source article.

### 4. LinkedIn Post

Write as a seasoned content writer.
Keep it human, conversational, professional, and easy to scan.

Rules:
- Maximum 170 words
- No emojis
- No hashtags in the body
- Put 3 to 5 hashtags on the last line only
- Ban clichés including: game-changer, fast-paced world, paradigm shift, unlock, leverage, cutting-edge
- Prefer a concrete stat or quote as the hook; otherwise use a thought-provoking question
- End with one open-ended question

## Append after the main outputs

Add an appendix titled `Evidence Check` with ALL of the following:

### A. Claim-Evidence Table
For each key claim, record:
| Claim | Supporting Evidence (exact quote) | Source location (paragraph/section) |

Sources must be traceable to specific article text. No generalisations.

### B. Confidence Score
Assign an explicit score (e.g., High 95%, Medium 80%) based on:
- Text legibility and completeness
- Number consistency
- Named sources vs. unnamed
- Unresolved ambiguities

### C. Residual Uncertainties
Note any claims where evidence is weak, contradictory, or incomplete. Be specific.

### D. Word Count Limits — Verified
Confirm each section is within its defined limit before delivery:
- Executive Summary (Standard): ≤200 words
- Detailed Breakdown: ≤400 words  
- LinkedIn Post: ≤170 words
- Blog body: 350–700 words

### E. Format Checklist
- [ ] Standard KT includes TL;DR + Executive Summary + Key Takeaways bullets
- [ ] WhatsApp KT in single code block, emoji-prefixed, no headings
- [ ] LinkedIn ≤170 words, no emojis in body, 3-5 hashtags at end, ends with question
- [ ] Blog includes SEO title, meta description, slug, category, tags, full body
- [ ] All images sourced from article included in blog
- [ ] No buzzwords, no list-heavy structure, no robotic tone

## Delivery guidance

- Prefer `research-context` when intake routing is still undecided.
- Use this workflow directly when Partha clearly wants article-only analysis.
- For blog workflows, category and tags are mandatory.
- For publishing workflows, ask Partha for the featured image first and use only the image he selects.
- Do not assume investment implications unless that path is specifically requested.
