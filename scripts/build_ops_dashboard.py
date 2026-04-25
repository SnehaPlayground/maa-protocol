#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

WORKDIR = Path('/root/.openclaw/workspace')
OUT = WORKDIR / 'data/reports/ops_dashboard.html'
EMAIL_MONITOR = WORKDIR / 'agents/email-monitor/state/email-monitor-state.json'
REVENUE = WORKDIR / 'agents/email-monitor/state/revenue-followup-summary.json'
CLIENT = WORKDIR / 'data/email/client_response_actions.json'
COMM_LOG = WORKDIR / 'data/email/communication-log.md'
REPORTS = WORKDIR / 'data/reports'
EMAIL_DATA = WORKDIR / 'data/email'


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default


def latest_report_file() -> str:
    files = sorted(REPORTS.glob('daily_research_*.html'))
    return files[-1].name if files else 'Not found'


def latest_voice_file() -> str:
    candidates = sorted(list(REPORTS.glob('voice_note_*.mp3')) + list(REPORTS.glob('voice_note_*.wav')))
    return candidates[-1].name if candidates else 'Not found'


def latest_send_audit() -> str:
    audits = sorted((EMAIL_DATA / 'send_audit').glob('send_*.json'))
    return audits[-1].name if audits else 'Not found'


def read_comm_log_tail(limit: int = 8) -> list[str]:
    if not COMM_LOG.exists():
        return []
    lines = [line.strip() for line in COMM_LOG.read_text(encoding='utf-8', errors='ignore').splitlines() if line.strip()]
    return lines[-limit:]


def card(title: str, body: str) -> str:
    return f'''<div class="card"><h2>{title}</h2>{body}</div>'''


def list_items(items: list[str]) -> str:
    if not items:
        return '<p class="muted">None</p>'
    return '<ul>' + ''.join(f'<li>{item}</li>' for item in items) + '</ul>'


def main() -> None:
    monitor = load_json(EMAIL_MONITOR, {})
    revenue = load_json(REVENUE, {})
    client = load_json(CLIENT, [])
    escalations = revenue.get('escalations', [])
    followups = revenue.get('followups', [])

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Primeidea Operations Dashboard</title>
<style>
body {{ font-family: Arial, sans-serif; background:#f5f7fb; color:#14213d; margin:0; padding:16px; }}
.wrap {{ max-width: 980px; margin: 0 auto; }}
h1 {{ font-size: 24px; margin: 0 0 8px; color:#001f3f; }}
.sub {{ color:#5b6475; font-size: 13px; margin-bottom: 16px; }}
.grid {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap:16px; }}
.card {{ background:#fff; border-radius:14px; padding:16px; box-shadow:0 4px 18px rgba(0,0,0,0.06); }}
.card h2 {{ margin:0 0 10px; font-size:18px; color:#001f3f; }}
.metric {{ font-size: 28px; font-weight:700; margin: 6px 0; }}
.muted {{ color:#6b7280; }}
ul {{ margin:8px 0 0 18px; padding:0; }}
li {{ margin:6px 0; line-height:1.4; }}
.kv {{ margin: 6px 0; font-size:14px; }}
.badge {{ display:inline-block; padding:4px 8px; border-radius:999px; background:#e8eefc; color:#163a70; font-size:12px; margin-right:6px; }}
</style>
</head>
<body>
<div class="wrap">
<h1>Primeidea Operations Dashboard</h1>
<div class="sub">Updated {datetime.now().strftime('%d %b %Y, %I:%M %p')}</div>
<div class="grid">
{card('Morning Research', f'''<div class="kv"><span class="badge">Report</span> {latest_report_file()}</div><div class="kv"><span class="badge">Audio</span> {latest_voice_file()}</div><div class="kv"><span class="badge">Last Send Audit</span> {latest_send_audit()}</div>''')}
{card('Email Monitor', f'''<div class="metric">{monitor.get('status', 'unknown')}</div><div class="kv"><span class="badge">Last Run</span> {monitor.get('last_run', 'n/a')}</div><div class="kv"><span class="badge">Mode</span> {monitor.get('last_mode', 'n/a')}</div>''')}
{card('Client Response Queue', f'''<div class="metric">{len(client)}</div><div class="muted">Actionable non-sales threads</div>''')}
{card('Revenue Follow-up Queue', f'''<div class="metric">{len(followups)}</div><div class="muted">Follow-up candidates</div><div class="kv"><span class="badge">Escalations</span> {len(escalations)}</div>''')}
{card('Revenue Escalations', list_items([f"{item.get('subject','')} ({item.get('email','')})" for item in escalations]))}
{card('Recent Communication Log', list_items(read_comm_log_tail()))}
</div>
</div>
</body>
</html>'''
    OUT.write_text(html, encoding='utf-8')
    print(str(OUT))


if __name__ == '__main__':
    main()
