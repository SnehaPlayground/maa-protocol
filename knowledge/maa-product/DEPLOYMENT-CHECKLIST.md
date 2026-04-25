# Maa Product Deployment Checklist

## Core install
- [ ] Maa core runtime files present under `ops/multi-agent-orchestrator/`
- [ ] Observability files present under `ops/observability/`
- [ ] Self-healing scripts present under `scripts/`
- [ ] Writable directories exist: `logs/`, `data/observability/`, `memory/maintenance_decisions/`, `ops/multi-agent-orchestrator/tasks/`, `ops/multi-agent-orchestrator/logs/`

## Runtime verification
- [ ] `python3 ops/observability/maa_metrics.py summary --since 24`
- [ ] `python3 scripts/health_check.py --json`
- [ ] `python3 scripts/auto_cleanup.py --dry-run --days 30`
- [ ] `python3 -m py_compile ops/multi-agent-orchestrator/task_orchestrator.py ops/observability/maa_metrics.py scripts/maintenance_logger.py ops/email/email_failure_alert.py`
- [ ] `bash -n ops/email/run_email_pipeline.sh`

## Safety verification
- [ ] Validation fails closed on invalid/empty validator output
- [ ] Completion marker required before validated status
- [ ] Metrics failures do not disappear silently
- [ ] Repeated alert spam is cooldown-protected
- [ ] No active WhatsApp voice route in Maa core

## Product boundary verification
- [ ] Maa core uses generic operator language, not client-specific branding
- [ ] Client workflows remain outside Maa core policy/runtime where possible
- [ ] Business-specific prompts/configs are isolated before deployment

## Sign-off
- [ ] Internal test run completed
- [ ] Post-fix certification audit completed
- [ ] Deployment approved for target business
