#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

WORKDIR = Path('/root/.openclaw/workspace')
CLASSIFICATION_FILE = WORKDIR / 'data/email/email_classification.json'
THREAD_STATE_FILE = WORKDIR / 'memory/thread-state.json'
OUTPUT_FILE = WORKDIR / 'data/email/client_response_actions.json'
LOG_FILE = WORKDIR / 'logs/email-monitor.log'

ACTION_MAP = {
    'FYI': ('NO_ACTION', 'Informational only'),
    'LOW_RISK': ('DRAFT_REPLY', 'Simple safe response allowed'),
    'NEEDS_APPROVAL': ('ESCALATE_TO_PARTHA', 'Requires approval before response'),
    'NEEDS_RESEARCH': ('PREPARE_RESEARCH_DRAFT', 'Needs research before response'),
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


def sales_emails(thread_state: dict) -> set[str]:
    out: set[str] = set()
    for item in thread_state.get('threads', {}).values():
        state = str(item.get('state', ''))
        email = str(item.get('email', '')).strip().lower()
        if email and state.startswith('STATE_'):
            out.add(email)
    return out


def build_actions(classified: list[dict], thread_state: dict) -> list[dict]:
    sales_contacts = sales_emails(thread_state)
    actions: list[dict] = []

    for item in classified:
        sender = str(item.get('from', ''))
        subject = str(item.get('subject', ''))
        category = str(item.get('category', 'FYI'))
        sender_email = ''
        if '<' in sender and '>' in sender:
            sender_email = sender.split('<', 1)[1].split('>', 1)[0].strip().lower()
        else:
            sender_email = sender.strip().lower()

        if sender_email in sales_contacts:
            continue

        action, reason = ACTION_MAP.get(category, ('ESCALATE_TO_PARTHA', 'Unclear case'))
        actions.append({
            **item,
            'action': action,
            'reason': reason,
            'workflow': 'communication-protocol',
            'generatedAt': now_iso(),
        })

    return actions


def main() -> None:
    classified = load_json(CLASSIFICATION_FILE, [])
    thread_state = load_json(THREAD_STATE_FILE, {'threads': {}, 'lastUpdated': None})
    actions = build_actions(classified, thread_state)
    save_json(OUTPUT_FILE, actions)
    append_log(f'Client response coordinator refreshed: {len(actions)} actionable non-sales threads')
    print('ok')


if __name__ == '__main__':
    main()
