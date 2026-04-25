---
name: whatsapp-management
description: Build, audit, or operate a controlled WhatsApp business assistant with public DM intake, silent group monitoring unless tagged, Telegram owner-control, private error alerting, lead logging, and reusable business knowledge packs. Use when creating or upgrading a WhatsApp assistant for Primeidea or other businesses, especially when the system must be commercializable later.
---

# WhatsApp Management

Build the system as a reusable framework, not a one-off bot.

## Core operating model

Separate the system into four layers:
1. channel/runtime layer
2. business knowledge pack
3. lead-routing and escalation policy
4. owner control and monitoring

## Mandatory behavior

- Keep WhatsApp DMs open only if the user explicitly wants public intake.
- In WhatsApp groups, stay silent unless directly tagged.
- If tagged in a group and the query is in approved scope, reply briefly and route toward DM / owner / approved CTA.
- If tagged in a group and the query is out of scope, stay silent or alert the owner privately per policy.
- Never expose internal errors, stack traces, file paths, system prompts, or tool names to clients.
- On runtime failure, suppress client-facing error text and alert the owner privately with a concise failure reason.
- Store lead logs in structured append-safe format such as JSONL, not a mutable JSON array.
- Restrict owner commands to the approved owner identity only.

## Framework structure

Use these workspace locations unless the user asks otherwise:
- runtime framework: `ops/whatsapp-framework/`
- reusable skill: `skills/whatsapp-management/`
- archived legacy system: `archive/whatsapp-assistant-legacy/`

## Required artifacts

Create or maintain:
- framework overview
- business knowledge pack
- guardrails
- playbooks
- owner command schema
- logging schema
- failure-handling rules
- rollout checklist

## Commercialization rule

Keep Primeidea-specific content separate from the reusable engine.

Recommended split:
- reusable engine instructions in this skill
- client-specific knowledge in `ops/whatsapp-framework/knowledge/`
- client-specific rollout/config notes in a separate file

## References

Read these as needed:
- `references/architecture.md` for framework layout
- `references/knowledge-pack.md` for KB design
- `references/rollout-checklist.md` for validation and go-live controls

## Legacy migration

If an old WhatsApp helper exists:
- preserve any useful routing logic, phone normalization, state design, or group metadata
- archive the old helper before replacing it
- do not claim live activation until bindings, routing, and test checkpoints are verified
