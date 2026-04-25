#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

WORKDIR = Path('/root/.openclaw/workspace')
STATE_DIR = WORKDIR / 'agents/email-monitor/state'
STATE_FILE = STATE_DIR / 'email-monitor-state.json'
THREAD_STATE_FILE = WORKDIR / 'memory/thread-state.json'
OUTPUT_FILE = STATE_DIR / 'revenue-followup-summary.json'
LOG_FILE = WORKDIR / 'logs/email-monitor.log'

SALES_STATES = {
    'STATE_0_NEW_LEAD',
    'STATE_1_PROSPECT_REPLIED',
    'STATE_2_FOLLOW_UP',
    'STATE_3_ESCALATED',
    'STATE_3_ESCALATED_OR_WON',
}


def now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def append_log(message: str) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open('a', encoding='utf-8') as f:
        f.write(f'[{datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z")}] {message}\n')


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default


def save_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding='utf-8')


def classify_sales_threads(thread_state: dict) -> dict:
    threads = thread_state.get('threads', {})
    sales_threads = []
    escalations = []
    followups = []

    for key, data in threads.items():
        state = str(data.get('state', '')).strip()
        if state not in SALES_STATES:
            continue
        item = {
            'key': key,
            'email': data.get('email', ''),
            'subject': data.get('subject', ''),
            'state': state,
            'lastContact': data.get('lastContact', ''),
            'summary': data.get('summary', ''),
            'action': data.get('action', ''),
            'escalate': bool(data.get('escalate', False)),
        }
        sales_threads.append(item)
        if item['escalate'] or state in {'STATE_3_ESCALATED', 'STATE_3_ESCALATED_OR_WON'}:
            escalations.append(item)
        elif state == 'STATE_2_FOLLOW_UP':
            followups.append(item)

    return {
        'sales_threads': sales_threads,
        'escalations': escalations,
        'followups': followups,
    }


def update_monitor_state(summary: dict) -> None:
    state = load_json(STATE_FILE, {
        'last_run': None,
        'last_mode': None,
        'status': 'initialized',
        'notes': []
    })
    state.update({
        'last_run': now_iso(),
        'last_mode': 'revenue-followup',
        'status': 'ok',
        'notes': [
            'Revenue follow-up coordinator executed successfully',
            f"Sales threads tracked: {len(summary['sales_threads'])}",
            f"Escalations pending: {len(summary['escalations'])}",
            f"Follow-up candidates: {len(summary['followups'])}",
        ]
    })
    save_json(STATE_FILE, state)


def main() -> None:
    thread_state = load_json(THREAD_STATE_FILE, {'threads': {}, 'lastUpdated': None})
    summary = classify_sales_threads(thread_state)
    summary['generatedAt'] = now_iso()
    summary['threadStateLastUpdated'] = thread_state.get('lastUpdated')
    save_json(OUTPUT_FILE, summary)
    update_monitor_state(summary)
    append_log(
        f"Revenue follow-up coordinator refreshed: {len(summary['sales_threads'])} tracked, "
        f"{len(summary['followups'])} follow-up candidates, {len(summary['escalations'])} escalations"
    )
    print('ok')


if __name__ == '__main__':
    main()
