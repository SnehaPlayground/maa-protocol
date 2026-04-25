#!/usr/bin/env bash
set -euo pipefail

WORKDIR="/root/.openclaw/workspace"
AGENT_DIR="$WORKDIR/agents/whatsapp-assistant"
STATE_DIR="$AGENT_DIR/state"
LOG_DIR="$WORKDIR/logs"
STATE_FILE="$STATE_DIR/whatsapp-assistant-state.json"
RUN_LOG="$LOG_DIR/whatsapp-assistant.log"
EMP_FILE="$WORKDIR/agents/whatsapp-assistant/emp_team.txt"
mkdir -p "$STATE_DIR" "$LOG_DIR"

timestamp() {
  date '+%Y-%m-%d %H:%M:%S %Z'
}

init_state() {
  if [[ ! -f "$STATE_FILE" ]]; then
    cat > "$STATE_FILE" <<'JSON'
{
  "initialized": false,
  "initialization_notice_emitted": false,
  "last_run": null,
  "last_sender": null,
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

validate_files() {
  local missing=0
  for file in \
    "$AGENT_DIR/SPEC.md" \
    "$AGENT_DIR/router.py"; do
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

  python3 "$AGENT_DIR/router.py" --init --emp-file "$EMP_FILE"
  log_line "WhatsApp assistant initialized. Dependency check completed."
}

main "$@"
