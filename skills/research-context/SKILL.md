---
name: research-context
description: Primary umbrella workflow for turning article screenshots, clippings, PDFs, copied text, and scanned documents into polished research outputs. Use when Partha wants one versatile entry point that can route a source into article analysis, investment analysis, combined packs, social drafts, blog-ready content, email packaging, or full publishing outputs.
---

# Research Context

A clean routing skill for turning a source article or clipping into one of three outcomes only:
1. Analysis
2. Analysis + Investment Recommendation
3. Blog Posting

## Purpose

Use this skill to choose the right research workflow from one source context and return clear, high-quality writing.

Apply the Humanization Filter to every output in every mode.

Do not use this skill for email drafting, WhatsApp summaries, LinkedIn drafts, distribution workflows, or broad publishing packs.

## Quality Standard (Non-Negotiable)

Every output from this skill must meet these standards before delivery.
Apply the Humanization Filter before final delivery.

- Claim-to-evidence table: each key claim paired with exact quote and source location
- Confidence score: High / Medium / Low with justification
- Residual uncertainties: explicit notes on weak or incomplete evidence
- Evidence Check must be the final section of every deliverable

Do not invent facts. Do not make unsupported claims. Do not inflate confidence.

## Accepted Inputs

Use this skill for:
- Newspaper screenshots
- Article images and clippings
- PDF articles
- DOCX files
- Scanned pages
- Copied article text
- Mixed-source research notes derived from a single article context

## Intake Rule

If Partha has not specified the intended output, ask:

What would you like me to prepare from this research context, Partha?
1. Analysis
2. Analysis + Investment Recommendation
3. Blog Posting

If the request is already explicit, do not ask again.

## Routing

### 1. Analysis
Route to the article-analysis workflow only.

Deliver:
- Key Takeaways written in clear natural language
- Detailed Breakdown written in simple English
- Claim-to-Evidence Table
- Confidence Score
- Residual Uncertainties
- Evidence Check

### 2. Analysis + Investment Recommendation
Route to both article-analysis and investment-analysis workflows.

Deliver:
- Article Analysis written in clear natural language
- Investment Thesis written in simple English
- Sector and Company Impact Mapping
- Watchlists by market-cap bucket where relevant
- Risk View
- Mutual Fund or scheme-level ideas where appropriate
- Claim-to-Evidence Table
- Confidence Score
- Residual Uncertainties
- Evidence Check

### 3. Blog Posting
Prepare the article for blog publishing.

**Text Content Chronology — mandatory for every blog post:**
1. TL;DR
2. Key Takeaways
3. Detailed Breakdown
4. Conclusions

Deliver:
- Blog-ready article draft written in simple, human language
- SEO title
- Meta description
- Suggested slug
- Exactly one approved WordPress category
- Relevant tags
- Evidence Check

Do not publish until Partha has reviewed the draft and provided the featured image.

## Humanization Filter

Apply this filter to all writing created through this skill.

Goals
- Use simple English
- Sound like a thoughtful human, not a machine
- Keep the writing clear, calm, and easy to read
- Prefer natural flow over rigid report language

Rules
- Use short to medium sentences
- Use plain words instead of heavy jargon when possible
- Explain ideas in a natural way
- Keep transitions smooth so the writing feels connected
- Make the meaning easy for a normal reader to follow on first read
- Remove robotic phrasing, stiff openings, and template-heavy wording
- Do not use unnecessary symbols such as colon, semicolon, exclamation mark, or long dash unless truly required
- Avoid stacked bullets when a short natural paragraph works better
- Do not sound dramatic, salesy, or artificial
- Do not overstate confidence
- Retest and recheck the language before final delivery until it reads naturally

Quick self-check before final output
- Does this sound like a real person wrote it
- Is the English simple and clean
- Can this be understood quickly without rereading
- Did I remove robotic phrases and unnecessary punctuation
- Is the tone warm, clear, and professional

## Blog Posting Rules

### WordPress Credentials
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

### Blog Workflow

#### Step 1 — Process Source
- Accept source
- Save original to archive location
- Generate draft content with title, slug, category, and tags
- Rewrite until the language feels human, smooth, and easy to read
- Send draft to Partha for review
- Do not proceed without confirmation

#### Step 2 — Receive Featured Image and Media
- Wait for Partha to provide the featured image
- If Partha sends an audio or video file, extract audio using ffmpeg before upload (video files contain audio track; extract with `-vn -acodec libmp3lame`)
- Do not publish without the featured image

#### Step 3 — Publish to WordPress
- Upload media (source image, featured image, AND any audio/video) using multipart form upload (`-F` flag with curl) — this bypasses ModSecurity restrictions on the REST API
- Extract audio from video files using ffmpeg before uploading
- Create post with full content following the mandatory chronology (TL;DR → Key Takeaways → Detailed Breakdown → Conclusions)
- **Embed source image into the post body** as the first element after the audio/video (if any):
  - Width: 250px
  - Float: right with `margin:0 0 15px 20px`
  - Border-radius: 8px
  - Text wraps around it naturally
  - Link to full-resolution version opening in a new tab
- **Embed audio at the very top of the post** before any text or image:
  - Use `<audio controls>` with style `width:100%;margin-bottom:20px;border-radius:8px;`
  - Include exactly one `<source src="..." type="audio/mpeg">` inside
  - **Never** include the text "Your browser does not support the audio element." inside the audio tag
  - **Never** include a "Listen to this article" link or any other text inside the audio tag
  - The audio element must be self-contained and clean
  - Correct example:
    ```html
    <audio controls style="width:100%;margin-bottom:20px;border-radius:8px;"><source src="https://admin.primeidea.in/wp-content/uploads/YYYY/MM/filename.mp3" type="audio/mpeg"></audio>
    ```
- Set featured media (thumbnail image provided by Partha)
- Publish
- Capture live URL

#### Step 4 — Self-Verify
- Confirm live URL works
- Confirm featured image renders correctly
- Confirm audio element (if added) is embedded at the top of the post and is clean — no fallback text, no "Listen to this article" link inside
- Confirm source image is embedded in the content body — small (250px), right-floated, with text wrapping
- Confirm content follows the mandatory chronology: TL;DR first, then Key Takeaways, then Detailed Breakdown, then Conclusions
- Confirm content, category, and tags are correct
- Confirm the writing feels natural and not robotic
- If any issue is found, fix before reporting completion

## Fixing Existing Posts with Audio

If a published post has audio issues, check for these two problems:
1. **Fallback text** — "Your browser does not support the audio element." inside the `<audio>` tag. Remove it.
2. **"Listen to this article" link** — an `<a>` tag with link text "Listen to this article" nested inside the `<audio>` element. Remove it.

Both problems make the theme show unwanted labels. The audio element must always be self-contained and clean.

## Preference Override

When this skill routes into investment analysis or investor-facing output:
- Never use "Direct Plan" or "Regular Plan" — use scheme names only
- Maintain an India-positive, opportunity-forward tone
- Never recommend Direct mutual fund plans
- Keep recommendations aligned with Primeidea style and Partha's workflow rules

## Delivery States

Every run must end in one of these states:
- Delivered in chat
- Draft ready
- Awaiting Partha approval
- Blocked by missing input

## Failure Handling

- Weak OCR: ask for a clearer image
- Partial article: identify what is missing before analysis
- Missing featured image: do not publish
- WordPress publish fails: retry once, then alert Partha
- Broken live URL after publish: fix before reporting done
- Unclear task intent: ask Partha to choose one of the three modes only
