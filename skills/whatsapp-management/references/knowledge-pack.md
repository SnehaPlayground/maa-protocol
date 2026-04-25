# Business Knowledge Pack

## Purpose
Keep business-specific knowledge separate from the reusable WhatsApp engine.

## Required files

### core-facts.md
Use for verified company facts only:
- name
- location
- leadership
- trust signals that can be defended
- app / portal / contact links

### services.md
Use for clear service summaries and product categories.

### guardrails.md
Use for:
- what the assistant may discuss
- what it must not discuss
- escalation cases
- compliance-style boundaries

### playbooks.md
Use for:
- intent handling
- qualification prompts
- CTA transitions
- objection handling

### commands.md
Use for owner commands and expected outputs.

## Quality rules
- Prefer verified facts over marketing claims.
- If a claim comes from testimonials, label it as testimonial language rather than objective fact.
- Keep answers concise and sales-helpful.
- Do not let business knowledge drift into runtime wiring instructions.
