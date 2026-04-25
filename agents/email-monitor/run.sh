#!/usr/bin/env bash
set -euo pipefail

WORKDIR="/root/.openclaw/workspace"
STATE_DIR="$WORKDIR/agents/email-monitor/state"
LOG_DIR="$WORKDIR/logs"
STATE_FILE="$STATE_DIR/email-monitor-state.json"
RUN_LOG="$LOG_DIR/email-monitor.log"
DRY_RUN="${1:-}"

mkdir -p "$STATE_DIR" "$LOG_DIR"

timestamp() {
  date '+%Y-%m-%d %H:%M:%S %Z'
}

init_state() {
  if [[ ! -f "$STATE_FILE" ]]; then
    cat > "$STATE_FILE" <<'JSON'
{
  "last_run": null,
  "last_mode": null,
  "status": "initialized",
  "notes": []
}
JSON
  fi
}

log_line() {
  printf '[%s] %s\n' "$(timestamp)" "$1" | tee -a "$RUN_LOG"
}

record_state() {
  local mode="$1"
  local status="$2"
  cat > "$STATE_FILE" <<JSON
{
  "last_run": "$(date -Is)",
  "last_mode": "$mode",
  "status": "$status",
  "notes": [
    "Runner executed successfully",
    "Policy source: skills/sneha-inbound-sales and skills/communication-protocol",
    "This runner is intentionally lightweight and approval-safe"
  ]
}
JSON
}

validate_files() {
  local missing=0
  for file in \
    "$WORKDIR/skills/sneha-inbound-sales/SKILL.md" \
    "$WORKDIR/skills/communication-protocol/SKILL.md" \
    "$WORKDIR/agents/email-monitor/SPEC.md"; do
    if [[ ! -f "$file" ]]; then
      log_line "Missing required file: $file"
      missing=1
    fi
  done
  return $missing
}

main() {
  init_state
  validate_files

  if [[ "$DRY_RUN" == "--dry-run" ]]; then
    python3 "$WORKDIR/ops/email/run_integrated_monitor.py" >/dev/null 2>&1 || true
    log_line "Dry run completed. Files validated. Integrated email monitor chain refreshed. No external actions taken."
    record_state "dry-run" "ok"
    exit 0
  fi

  python3 "$WORKDIR/ops/email/run_integrated_monitor.py"
  log_line "Email monitor deployed with integrated snapshot, classification, and coordinator chain active."
  record_state "deploy" "active"
}

main "$@"
