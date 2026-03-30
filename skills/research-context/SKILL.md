---
name: research-context
description: Primary umbrella workflow for turning article screenshots, clippings, PDFs, copied text, and scanned documents into polished research outputs. Use when Partha wants one versatile entry point that can route a source into article analysis, investment analysis, combined packs, social drafts, blog-ready content, email packaging, or full publishing outputs.
---

# Research Context

A single versatile skill for turning a source article or clipping into the right research output.

## Quality Standard (Non-Negotiable)

Every output from this skill must meet these standards before delivery:

**Every article analysis must include:**
- Claim-to-evidence table: each key claim paired with exact quote and source location
- Confidence score: High/Medium/Low with justification
- Residual uncertainties: explicit notes on weak or incomplete evidence
- Word count verification: each section within its defined limit

**Evidence Check must be the final section of every deliverable.** If evidence is weak, say so. Do not inflate confidence to sound authoritative.

**No invented facts. No unsupported claims. No generic hedging.**

When Partha provides a processed analysis (with claim-evidence tables, confidence scores, word count checks), treat that as the quality benchmark to match and exceed.

## What this skill accepts

Use this skill for:
- Newspaper screenshots
- Article images and clippings
- PDF articles
- DOCX files
- Scanned pages
- Copied article text
- Mixed-source research notes derived from a single article context

## Intake rule

When Partha shares a source item and the intended output is not already clear, ask:

What would you like me to prepare from this research context, Partha?
1. Article Analysis
2. Investment Analysis
3. Combined Research Pack
4. LinkedIn Draft
5. WhatsApp Summary
6. Blog-Ready Article
7. Email Pack
8. Full Publishing Pack

If the request is already explicit, do not ask again. Route directly.

## TASK OPTIONS

### 1. Article Analysis
Use the article-analysis workflow only.

Deliver: Key Takeaways, Detailed Breakdown, Evidence Check.

### 2. Investment Analysis
Use the investment-analysis workflow only.

Deliver: Article-triggered investment thesis, Sector and company impact mapping, Watchlists by market-cap bucket, Risk view, Mutual fund ideas.

### 3. Combined Research Pack
Run both article analysis and investment analysis from the same source.

Deliver: Article Analysis → Investment Thesis → Watchlists by market-cap bucket → LinkedIn Draft → WhatsApp Summary → Evidence Check.

### 4. LinkedIn Draft
Create only the LinkedIn-ready version grounded in the source context.

### 5. WhatsApp Summary
Create only the forwardable WhatsApp summary grounded in the source context.

### 6. Blog-Ready Article
Create the humanized blog package.

Include: SEO title, Meta description, Suggested slug, Exactly one approved WordPress category, Relevant tags.

Note: Do not include the featured image recommendation unless Partha specifically asks for it.

### 7. Email Pack
Prepare the research email package for the research list.

Rules:
- One personalized email per recipient
- Use simple, clear newspaper-style formatting rather than heavy newsletter formatting
- Start with exactly one short personalized line before the analysis begins
- Use this section order exactly:
  1. Personalized opening line
  2. TL;DR
  3. Key Takeaways
  4. Detailed Breakdown
  5. Investment Ideas
  6. CTA
  7. Signature
- If the email includes any research ideas, stock names, mutual fund ideas, or investment guidance, it must include this exact disclaimer:
  ⚖️ DISCLAIMER: This is only for Educational purposes only. This is not recommendations. Consult your financial advisor before taking any action.
- Attach the original source image or file for newspaper/article workflows
- Do not inline the source image unless Partha explicitly asks
- The CTA must direct the reader to contact Partha Shah by name and mobile number only
- Do not include Partha's email address in the CTA unless he explicitly asks
- Closing offer line ("If you would like, I can convert this into...") is included only when recipient is NOT Partha

### 8. Full Publishing Pack
Produce the complete downstream output suite from one source context.

Default components:
- Combined Article + Investment Analysis
- Blog-Ready Article
- WhatsApp Summary
- Email Pack
- WordPress publishing + client distribution (see full pipeline below)

---

## BLOG PUBLISHING PIPELINE (Partha-First Review)

This pipeline covers the complete lifecycle: Source → Draft → Image → Publish → Distribute.

### WordPress Credentials (already configured)
- Application Password: stored in `/root/.openclaw/workspace/blog_key.md`
- Site URL: `https://admin.primeidea.in`
- Auth: `sneha.primeidea@gmail.com` + app password

### Approved WordPress Categories
Use exactly one:
- Financial Planning (ID: 2)
- Insurance (ID: 3)
- Legacy & Inheritance (ID: 8)
- Mediclaim (ID: 4)
- Retirement Planning (ID: 7)
- Tax Planning (ID: 5)
- Wealth Management (ID: 6)

---

### PIPELINE STEPS

#### STEP 1 — Process Source → Generate Draft
- Accept source (image, PDF, text, clipping)
- Save original to archive location
- Run appropriate analysis task (Article / Investment / Combined)
- Produce: draft content + TL;DR summary + suggested slug/category/tags
- **Send draft to Partha for review — do NOT proceed without confirmation**

#### STEP 2 — Receive Featured Image from Partha
- Partha sends the featured image separately
- Save to workspace
- Do NOT proceed to publish without the image

#### STEP 3 — Publish to WordPress
Upload media → Create post with featured image → Publish → obtain live URL.

**Upload media:**
```bash
WP_CREDS=$(cat /root/.openclaw/workspace/blog_key.md | grep -E "Username|Password" | sed 's/.*: *//' | tr '\n' ':' | sed 's/:$//')
curl -s --max-time 30 \
  -u "$WP_CREDS" \
  -H "Content-Disposition: attachment; filename=featured.jpg" \
  -H "Content-Type: image/jpeg" \
  --data-binary "@/path/to/featured.jpg" \
  "https://admin.primeidea.in/wp-json/wp/v2/media"
```
Response contains `id` and `source_url`.

**Create post:**
```bash
WP_CREDS=$(cat /root/.openclaw/workspace/blog_key.md | grep -E "Username|Password" | sed 's/.*: *//' | tr '\n' ':' | sed 's/:$//')
curl -s --max-time 30 \
  -u "$WP_CREDS" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "<SEO TITLE>",
    "content": "<FULL HTML CONTENT WITH FEATURED IMAGE>",
    "status": "publish",
    "categories": [<CATEGORY_ID>],
    "tags": [<TAG_ID_1>, <TAG_ID_2>],
    "featured_media": <MEDIA_ID>,
    "slug": "<SLUG>"
  }' \
  "https://admin.primeidea.in/wp-json/wp/v2/posts"
```
Response contains `link` (live URL).

**Self-verify after publish:**
- Visit the live URL and confirm it renders correctly
- Confirm featured image displays properly
- Confirm content, category, and tags are correct
- If any issue, unpublish and fix before distributing

#### STEP 4 — Draft Client Distribution Email
Using the live blog URL and TL;DR from Step 1, draft personalized outreach emails for the research list.

**Send draft to Partha for review — wait for confirmation before proceeding to Step 5.**

**Email format for blog distribution:**
```html
<html><body>
<p>[Recipient Name] Ji,</p>

<p>You had asked about / shared interest in [topic reference] — we wrote about it here:</p>

<p><a href="[BLOG URL]"><strong>[Article Headline]</strong></a></p>

<p><strong>TL;DR:</strong> [2-3 sentence summary of key takeaway]</p>

<p>Regards,<br>
Sneha🥷<br>
Primeidea Ventures<br>
<a href="https://Primeidea.in">https://Primeidea.in</a></p>
</body></html>
```

**Quality gates for client distribution email:**
- [ ] Personalized opening line (references their prior interest or context if available)
- [ ] Blog URL is correct and live
- [ ] TL;DR accurately reflects article content
- [ ] Subject line is compelling
- [ ] Sneha identity, not Primeidea Research
- [ ] No investment advice, no directional claims
- [ ] Plain `<p>` format, simple and personal
- [ ] Post-send verify: read sent email back confirms formatting renders correctly

#### STEP 5 — Send to Research List
- Read `research_list.md` for current recipients
- Send one personalized email per recipient
- Partha is already CC'd on all other client-facing and business emails; for blog/research distribution emails (one-way), CC is not required unless Partha specifically requests it
- Send one at a time; verify each before next

#### STEP 6 — Post-Send Verification (MANDATORY)
After every distribution email:
- Run `gog email read <message_id>` to confirm content, formatting, recipient
- Mark as read after verification
- If any issue, send corrected version immediately
- Report completion to Partha only after all sends verified

---

## QUALITY RULES (Non-Negotiable)

1. **Never publish without the featured image** — Partha must provide it first
2. **Verify live URL before distributing** — a broken link damages Primeidea credibility
3. **TL;DR must match article content** — do not exaggerate or add unsupported claims
4. **No investment advice in client emails** — distribute article only, no directional calls
5. **Post-send verification is mandatory** — read every sent email back before reporting done
6. **HTML format for all client emails** — never plain text
7. **Partha reviews drafts first** — send draft to Partha for confirmation before publishing or distributing

---

## PREFERENCE OVERRIDE

When this skill routes into investment analysis or any investor-facing output:
- Never use "Direct Plan" or "Regular Plan" — use scheme names only
- Always maintain an India-positive, opportunity-forward tone — motivate investors to participate in India's structural growth story
- Never recommend Direct mutual fund plans — use Regular plan framing only (already in MEMORY.md but reinforce here)
- Keep recommendations aligned with Primeidea style and Partha's workflow rules

## EMAIL GUARDRAIL

Before any external email is sent, verify against the full pre-send checklist. Do not send a broken draft. Do not fake sending.

---

## DELIVERY PATTERNS

### Chat delivery
Use in-chat delivery for summaries, LinkedIn drafts, WhatsApp summaries, and working research notes.

### Email delivery
Use personalized research emails when Partha asks for email packaging or explicitly approves sending.
For newspaper/article research:
- Use HTML format: `<ul>` for bullets, `<strong>` for section headers, plain text signature
- Keep the body simple, clear, and easy to scan
- Include exactly one brief personalized opening line before the analytical sections
- Follow this accepted order exactly: Personalized opening line → TL;DR → Key Takeaways → Detailed Breakdown → [Investment Ideas if applicable] → CTA → Signature
- Disclaimer is ONLY needed when stock names, mutual fund names, or investment recommendations are included — omit otherwise
- Closing offer line ("If you would like, I can convert this into...") is included only when recipient is NOT Partha

### Blog delivery
When Partha asks for blog-ready output or publishing, prepare the full WordPress-ready package and enforce category and tag rules.
For blog posts:
- use the primary newspaper article image inside the blog body as the source article image
- use the full-resolution original upload
- display it at small visual size by default
- wrap text properly around the image
- make the image clickable so it opens the full high-resolution original image in a new tab

---

## PRE-SEND REVIEW CHECKLIST

### For blog publishing:
- [ ] Featured image received from Partha
- [ ] Content verified — no factual errors, no unsupported claims
- [ ] Category is exactly one from approved list
- [ ] Tags are relevant and appropriate
- [ ] Slug is clean and descriptive
- [ ] Live URL verified after publish
- [ ] Featured image renders on live post

### For client distribution emails:
- [ ] Blog URL is live and correct
- [ ] TL;DR accurately reflects article
- [ ] Personalized opening line present
- [ ] Email uses HTML format (simple `<p>` structure)
- [ ] Sneha identity, not Primeidea Research
- [ ] No investment advice, no directional claims
- [ ] Post-send: read sent email back, confirm formatting renders
- [ ] Marked as read after verification

### For research emails (non-blog):
- [ ] Email uses HTML format (`<ul>` bullets, `<strong>` headers, plain text signature)
- [ ] Source image/file is attached, NOT inlined
- [ ] Exactly one short personalized opening line before TL;DR
- [ ] Chronology: Personalized opening → TL;DR → Key Takeaways → Detailed Breakdown → [Investment Ideas if applicable] → CTA → Signature
- [ ] If NO investment ideas → NO disclaimer needed
- [ ] If investment ideas ARE present → disclaimer MUST be included
- [ ] CTA points to Partha Shah by name and mobile number only
- [ ] Post-send: read sent email back, confirm formatting renders

**If ANY check fails, revise before sending. Do not send a broken draft.**

---

## FAILURE HANDLING

- Weak OCR: ask for a clearer image.
- Partial article: identify the missing part before analysis.
- Missing delivery target: prepare drafts and ask for the missing detail.
- Missing featured image: do not publish; wait for Partha to send it.
- WordPress publish fails: retry once; if still failing, alert Partha on Telegram.
- Broken live URL after publish: unpublish immediately, fix, republish.
- If draft does not satisfy the pre-send review checklist: revise first.
- Unclear task intent: show the task menu and let Partha choose.
