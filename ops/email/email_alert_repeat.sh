#!/bin/bash
set -euo pipefail

STATE_FILE="/root/.openclaw/workspace/data/email/email_failure_alert_state.json"
ALERTER="/root/.openclaw/workspace/ops/email/email_failure_alert.py"

[ -f "$STATE_FILE" ] || exit 0

python3 - <<'PY'
import json
from pathlib import Path
p = Path('/root/.openclaw/workspace/data/email/email_failure_alert_state.json')
try:
    state = json.loads(p.read_text(encoding='utf-8'))
except Exception:
    raise SystemExit(0)
active = state.get('active_alert')
if not active or active.get('acknowledged', False):
    raise SystemExit(0)
print(active.get('error_text', 'Unknown email pipeline failure'))
PY
