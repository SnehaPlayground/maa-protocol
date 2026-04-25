# Maa Product Packaging Structure

## Maa core
- `ops/multi-agent-orchestrator/`
  - core orchestration runtime
  - global policy
  - no-timeout policy
  - self-healing policy
- `ops/observability/`
  - metrics CLI
  - event logging hooks
- `scripts/`
  - health check
  - cleanup
  - maintenance logger

## Business-specific layer
Keep outside Maa core where possible:
- market brief workflows
- email business rules
- business-specific prompts/templates
- client-specific escalation wording
- report formats tied to one business

## Per-client configurable surface
- runtime alert target
- model choices
- alert targets
- task catalog
- output formats
- thresholds
- business branding
- approval wording

## Minimal config file
- `knowledge/maa-product/runtime-config.json`
- ship `templates/maa-product/runtime-config.template.json` as the handoff template

## Product rule
Maa core should be reusable without editing core runtime code for each client. Client adaptation should happen through configuration, wrappers, and workflow modules around the core.
