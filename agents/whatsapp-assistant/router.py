#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

WORKDIR = Path('/root/.openclaw/workspace')
AGENT_DIR = WORKDIR / 'agents' / 'whatsapp-assistant'
STATE_DIR = AGENT_DIR / 'state'
STATE_FILE = STATE_DIR / 'whatsapp-assistant-state.json'
INIT_MESSAGE = "Initialization complete. Please ensure 'emp_team.txt' is loaded and provide me with the incoming phone numbers so I can apply the correct routing protocols."


def now_iso() -> str:
    return datetime.now().astimezone().isoformat()


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


def normalize_phone(raw: str) -> str:
    digits = re.sub(r'\D+', '', raw or '')
    if not digits:
        return ''
    if len(digits) == 10:
        digits = '91' + digits
    if not digits.startswith('91') and len(digits) > 10:
        return '+' + digits
    return '+' + digits


def load_emp_numbers(emp_file: Path) -> dict[str, dict]:
    if not emp_file.exists():
        return {}
    values: dict[str, dict] = {}
    for raw_line in emp_file.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#'):
            continue
        parts = [part.strip() for part in line.split('|')]
        if len(parts) >= 2:
            name = parts[0]
            phone = normalize_phone(parts[1])
            notes = parts[2] if len(parts) >= 3 else ''
        else:
            name = ''
            phone = normalize_phone(line)
            notes = ''
        if phone:
            values[phone] = {'name': name, 'notes': notes}
    return values


def classify(sender: str, emp_numbers: dict[str, dict]) -> tuple[str, dict]:
    normalized = normalize_phone(sender)
    profile = emp_numbers.get(normalized, {})
    mode = 'employee_assistance' if normalized in emp_numbers else 'sales_representative'
    return mode, profile


def build_response(mode: str, profile: dict | None = None) -> dict:
    profile = profile or {}
    if mode == 'employee_assistance':
        payload = {
            'mode': mode,
            'role': 'Internal Support Assistant',
            'tone': 'short, polite, highly professional',
            'guidance': 'Assist with Primeidea work queries, document retrieval, and task support.'
        }
        if profile:
            payload['employee_profile'] = profile
            if 'treat-with-extra-care' in profile.get('notes', ''):
                payload['guidance'] = 'Assist with extra care, high respect, and concise professionalism.'
        return payload
    return {
        'mode': mode,
        'role': 'Expert Financial Sales Executive for Primeidea',
        'tone': 'short, polite, highly professional, convincing',
        'guidance': 'Steer toward Partha Shah on +918141027000 or the Primeidea portal at https://login.primeidea.in/pages/auth/login.'
    }


def update_state(**kwargs) -> dict:
    state = load_json(STATE_FILE, {
        'initialized': False,
        'initialization_notice_emitted': False,
        'last_run': None,
        'last_sender': None,
        'last_mode': None,
        'status': 'initialized',
        'notes': []
    })
    state.update(kwargs)
    state['last_run'] = now_iso()
    save_json(STATE_FILE, state)
    return state


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--init', action='store_true')
    parser.add_argument('--emp-file', default=str(AGENT_DIR / 'emp_team.txt'))
    parser.add_argument('--sender', default='')
    args = parser.parse_args()

    emp_file = Path(args.emp_file)

    if args.init:
        state = update_state(
            initialized=True,
            initialization_notice_emitted=True,
            status='awaiting-emp-file' if not emp_file.exists() else 'ready',
            notes=[INIT_MESSAGE]
        )
        print(INIT_MESSAGE)
        return

    if not emp_file.exists():
        update_state(
            status='missing-emp-file',
            last_sender=args.sender or None,
            notes=["emp_team.txt missing. Routing halted."]
        )
        print(json.dumps({'error': 'emp_team.txt missing. Routing halted.'}))
        return

    emp_numbers = load_emp_numbers(emp_file)
    mode, profile = classify(args.sender, emp_numbers)
    payload = build_response(mode, profile)
    payload['sender'] = normalize_phone(args.sender)
    update_state(
        initialized=True,
        initialization_notice_emitted=True,
        status='ready',
        last_sender=payload['sender'],
        last_mode=mode,
        notes=[f"Sender classified as {mode}."]
    )
    print(json.dumps(payload, indent=2))


if __name__ == '__main__':
    main()
