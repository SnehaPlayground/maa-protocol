# Research Wiki Lint Checklist

Purpose

This checklist is used to periodically audit the Primeidea Research Wiki for health, accuracy, and completeness. Run it when the wiki reaches 10 or more pages, or when Partha asks for a health check.

---

## When to run

- After adding 10 or more new pages
- Monthly for active wikis
- Before a major research deliverable that relies on wiki content
- When Partha asks for a wiki review

---

## How to run

1. Read this checklist
2. Go through each section
3. Note findings in the log
4. Fix what is within scope
5. Flag what needs Partha review
6. Update the log with the lint date and outcomes

---

## Section 1: Source integrity

### Check 1.1 — Raw sources exist

For every active or draft page, verify that the raw source files still exist in `ops/research/raw/`.

If a source is missing:
- flag the page as having a missing source
- do not delete the page; move it to draft and note the gap

### Check 1.2 — Source links are valid

If wiki pages reference web URLs, verify those URLs are still accessible.

If a URL is broken:
- note it in the relevant source page
- try to find an archived or replacement version
- if not recoverable, mark confidence as low and note the gap

---

## Section 2: Citation health

### Check 2.1 — Every substantive claim has a source

Go through active pages and verify that every non-trivial claim is backed by a citation.

If a claim is unsourced:
- add a citation if you can identify the source
- if you cannot, mark the claim as needing citation or lower the confidence

### Check 2.2 — Cross-references are functional

Verify that all internal wiki links point to real existing pages.

If a link is broken:
- fix the link to point to the correct page
- if the target page no longer exists, remove the link and note it

---

## Section 3: Staleness detection

### Check 3.1 — Pages older than 90 days

List all pages where `last_updated` is more than 90 days old.

For each stale page:
- review whether the content is still current
- if superseded by newer evidence, update status to superseded
- if still current, add an update note confirming review and refresh the date
- if uncertain, flag for Partha review

### Check 3.2 — Draft pages older than 30 days

List all draft pages older than 30 days.

For each old draft:
- assess whether it should be promoted, merged, or removed
- if content is thin, consider merging into a related page
- if the topic is no longer relevant, archive the draft

---

## Section 4: Contradiction check

### Check 4.1 — Contradictory claims across pages

Look for pages that cover overlapping topics and check for contradictory claims.

Common areas to check:
- sector pages vs company pages (are size estimates consistent)
- thesis pages vs theme pages (do they align)
- older sources vs newer sources (has newer evidence changed the view)

If a contradiction is found:
- preserve both views
- add a contradiction note to both pages
- mark the page with lower confidence as needing review
- flag for Partha if it affects investment research

---

## Section 5: Completeness check

### Check 5.1 — Orphan pages

Identify any pages with no inbound links from other wiki pages.

For each orphan:
- link it from a relevant parent page, or
- add it to a comparison or theme page, or
- if it is no longer relevant, mark it for archival

### Check 5.2 — Missing topic coverage

Review the index and ask: what important sector, company, or theme is missing from the wiki?

List the top 3 gaps and note them in the log.

### Check 5.3 — Empty template pages

Identify any pages that still use only the template with no real content.

Options:
- fill in the content
- merge with a related page
- remove the empty page

---

## Section 6: Sensitivity and access check

### Check 6.1 — Sensitive pages reviewed

Verify that pages marked confidential or client-sensitive are still appropriately restricted.

If a page has been inappropriately categorized:
- recategorize it
- if it contains sensitive content that should not be in the wiki, remove it and flag to Partha

### Check 6.2 — No secrets in the wiki

Search wiki pages for common secret patterns:
- passwords, tokens, API keys, Bearer tokens, auth strings
- app passwords, email credentials, cloud credentials

If found:
- remove immediately
- note in the log what was removed and when
- do not rely on the wiki for storing any credentials

---

## Section 7: Confidence calibration

### Check 7.1 — Overconfident pages

Pages marked high confidence with only one weak source should be downgraded.

If confidence is disproportionate to evidence:
- lower the confidence rating
- add a note explaining why
- add the claim to open questions if it is material

### Check 7.2 — Underconfident pages

Pages that have strong multi-source backing but are still marked low or medium should be upgraded.

---

## Output format

After running the lint, append to `log.md`:

```markdown
## [YYYY-MM-DD] lint | Wiki health check
- Pages reviewed: N
- Issues found: N
- Issues fixed: N
- Issues flagged for Partha: N
- Orphan pages: N
- Stale pages: N
- Contradictions noted: N
```

---

## Fixable without Partha review

- broken internal links
- outdated last_updated dates
- missing cross-references
- orphan page linking
- empty template cleanup
- secret removal
- citation formatting

## Always flag for Partha

- contradictions in investment or thesis pages
- missing or broken critical sources
- sensitivity miscategorization involving client data
- any page that needs to be removed for compliance or privacy reasons
- promotion of thesis pages from draft to active
