#!/usr/bin/env python3
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

STATE_PATH = Path('/root/.openclaw/workspace/data/email/email_failure_alert_state.json')
CONFIG_PATH = Path('/root/.openclaw/workspace/knowledge/maa-product/runtime-config.json')
COOLDOWN_SECONDS = 1800


def now_str():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def now_ts():
    return int(datetime.now().timestamp())


def load_state():
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding='utf-8'))
    except Exception:
        return {}


def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding='utf-8')


def load_config():
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
        except Exception:
            return {}
    return {}


def main():
    error_text = sys.argv[1] if len(sys.argv) > 1 else 'Unknown email pipeline failure'
    config = load_config()
    alert_target = os.environ.get('MAA_ALERT_TARGET') or config.get('alert_target') or ''
    if not alert_target:
        sys.exit('Missing alert target: set MAA_ALERT_TARGET or knowledge/maa-product/runtime-config.json')
    state = load_state()
    active = state.get('active_alert')
    current_ts = now_ts()

    if active and active.get('error_text') == error_text and not active.get('acknowledged', False):
        count = int(active.get('count', 1)) + 1
    else:
        count = 1

    if active and active.get('error_text') == error_text and not active.get('acknowledged', False):
        last_sent_ts = int(active.get('last_sent_ts', 0) or 0)
        if current_ts - last_sent_ts < COOLDOWN_SECONDS:
            state['active_alert'] = {
                **active,
                'count': count,
                'last_seen_at': now_str(),
                'last_seen_ts': current_ts,
                'suppressed_by_cooldown': True
            }
            save_state(state)
            return

    message = (
        f"Email pipeline failure alert\n"
        f"Time: {now_str()}\n"
        f"Issue: {error_text}\n"
        f"Alert count: {count}\n\n"
        f"Please acknowledge with: ACK EMAIL ALERT"
    )

    subprocess.run([
        'openclaw', 'message', 'send',
        '--channel', 'telegram',
        '--target', alert_target,
        '--message', message
    ], check=False)

    state['active_alert'] = {
        'error_text': error_text,
        'count': count,
        'last_sent_at': now_str(),
        'last_sent_ts': current_ts,
        'last_seen_at': now_str(),
        'last_seen_ts': current_ts,
        'acknowledged': False
    }
    save_state(state)


if __name__ == '__main__':
    main()
