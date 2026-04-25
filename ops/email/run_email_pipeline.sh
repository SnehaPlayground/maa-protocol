#!/bin/bash
set -euo pipefail

cd /root/.openclaw/workspace || exit 1

if [ -f /root/.config/sneha/env.sh ]; then
  source /root/.config/sneha/env.sh
fi

if [ -f /root/.openclaw/workspace/.env ]; then
  source /root/.openclaw/workspace/.env
fi

LOG_FILE="/root/.openclaw/workspace/logs/email-pipeline.log"
METRICS_LOG="/root/.openclaw/workspace/logs/maa-metrics-errors.log"
TMP_OUTPUT=$(mktemp)
METRICS="/root/.openclaw/workspace/ops/observability/maa_metrics.py"

record_metric() {
  local kind="$1"
  shift
  if ! python3 "$METRICS" record --type "$kind" "$@" >> "$LOG_FILE" 2>> "$METRICS_LOG"; then
    printf '%s metrics_failure kind=%s args=%s\n' "$(date -Is)" "$kind" "$*" >> "$METRICS_LOG"
    return 1
  fi
}

# ── Observability: task start ─────────────────────────────────────────────────
record_metric task --label "email_ops.pipeline_run" --status start --agent email_ops || true

START_TIME=$(date +%s%3N)   # epoch ms for latency
PIPELINE_OK=true

if ! python3 /root/.openclaw/workspace/ops/email/email_pipeline.py >"$TMP_OUTPUT" 2>&1; then
  PIPELINE_OK=false
  cat "$TMP_OUTPUT" >> "$LOG_FILE"
  ERROR_TEXT=$(tail -20 "$TMP_OUTPUT" | tr '\n' ' ' | sed 's/"/\\"/g')

  # ── Observability: record error ─────────────────────────────────────────────
  record_metric error \
    --label "email_ops.pipeline_failed" \
    --details "pipeline exited non-zero: ${ERROR_TEXT:0:200}" \
    --agent email_ops || true

  python3 /root/.openclaw/workspace/ops/email/email_failure_alert.py "$ERROR_TEXT"
  rm -f "$TMP_OUTPUT"

  # ── Observability: task failed ─────────────────────────────────────────────
  record_metric task --label "email_ops.pipeline_run" \
    --status failed --agent email_ops || true
  exit 1
fi

cat "$TMP_OUTPUT" >> "$LOG_FILE"
if grep -q "Gmail auth/search unavailable" "$TMP_OUTPUT"; then
  ERROR_TEXT=$(grep "Gmail auth/search unavailable" "$TMP_OUTPUT" | tail -1 | sed 's/"/\\"/g')
  python3 /root/.openclaw/workspace/ops/email/email_failure_alert.py "$ERROR_TEXT"

  # ── Observability: record auth warning as error ─────────────────────────────
  record_metric error \
    --label "email_ops.pipeline_auth_unavailable" \
    --details "$ERROR_TEXT" \
    --agent email_ops || true
fi
rm -f "$TMP_OUTPUT"

# ── Observability: task completed + latency ───────────────────────────────────
if [ -n "$START_TIME" ]; then
  END_TIME=$(date +%s%3N)
  DURATION_MS=$((END_TIME - START_TIME))
  record_metric latency \
    --label "email_ops.pipeline_run" \
    --value "$DURATION_MS" \
    --agent email_ops || true
fi

record_metric task --label "email_ops.pipeline_run" \
  --status completed --agent email_ops || true

# ── Maintenance log: record this pipeline run ─────────────────────────────────
python3 /root/.openclaw/workspace/scripts/maintenance_logger.py \
  email_pipeline_run completed \
  "{\"pipeline_ok\": \"$PIPELINE_OK\", \"duration_ms\": \"$DURATION_MS\"}" \
  >> "$LOG_FILE" 2>&1 || true
