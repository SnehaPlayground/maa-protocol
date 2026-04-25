# WhatsApp Framework Architecture

## Goal
Create a reusable WhatsApp business assistant framework that can be adapted for Primeidea and later reused for other businesses.

## Layers

### 1. Runtime Layer
Handles:
- public DM intake
- group monitoring
- owner command intake
- message classification
- routing and failure suppression

### 2. Business Knowledge Layer
Contains only business-specific facts:
- company overview
- services / products
- CTA paths
- FAQs
- approved claims
- out-of-scope rules

### 3. Lead Operations Layer
Contains:
- intent classification
- qualification prompts
- next-action logic
- lead states (`new`, `qualified`, `warm`, `routed`, `registered`, `closed`, `escalation`)

### 4. Owner Control Layer
Contains:
- authorized owner identity
- commands
- alerting rules
- summaries / exports / pause-resume

## Recommended workspace structure

- `ops/whatsapp-framework/framework.md`
- `ops/whatsapp-framework/knowledge/core-facts.md`
- `ops/whatsapp-framework/knowledge/services.md`
- `ops/whatsapp-framework/knowledge/guardrails.md`
- `ops/whatsapp-framework/knowledge/playbooks.md`
- `ops/whatsapp-framework/knowledge/commands.md`
- `ops/whatsapp-framework/logs/leads.jsonl`
- `ops/whatsapp-framework/logs/activity.log`

## Live activation rule
Do not call the system live until:
1. routing target is confirmed
2. owner authorization is confirmed
3. DM test passes
4. group-tag test passes
5. failure-alert test passes
6. log write test passes
