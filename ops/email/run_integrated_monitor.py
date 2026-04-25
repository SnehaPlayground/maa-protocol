#!/usr/bin/env python3
from __future__ import annotations

import subprocess
from pathlib import Path
import sys

WORKDIR = Path('/root/.openclaw/workspace')
LOG_FILE = WORKDIR / 'logs/email-monitor.log'
METRICS = WORKDIR / 'ops' / 'observability' / 'maa_metrics.py'
HEALTH_CHECK = WORKDIR / 'scripts' / 'health_check.py'


def log(message: str) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open('a', encoding='utf-8') as f:
        f.write(message.rstrip() + '\n')


def record(metric_type: str, label: str, *, value: float | None = None, status: str | None = None, details: str | None = None) -> None:
    cmd = ['python3', str(METRICS), 'record', '--type', metric_type, '--label', label, '--agent', 'email_monitor']
    if value is not None:
        cmd += ['--value', str(value)]
    if status is not None:
        cmd += ['--status', status]
    if details is not None:
        cmd += ['--details', details[:200]]
    subprocess.run(cmd, capture_output=True, text=True)


def run(cmd: list[str], label: str) -> None:
    start = __import__('time').time()
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout:
        log(result.stdout)
    if result.stderr:
        log(result.stderr)
    if result.returncode != 0:
        record('error', f'email_monitor.{label}_failed', details=result.stderr or 'non-zero exit')
        raise SystemExit(result.returncode)
    record('latency', f'email_monitor.{label}', value=(__import__('time').time() - start) * 1000)


def main() -> None:
    record('task', 'email_monitor.integrated_monitor', status='start')
    subprocess.run(['python3', str(HEALTH_CHECK), '--json'], capture_output=True, text=True)
    run(['python3', str(WORKDIR / 'ops/email/read_emails.py')], 'read_emails')
    run(['python3', str(WORKDIR / 'ops/email/classify_emails.py')], 'classify_emails')
    run(['python3', str(WORKDIR / 'ops/email/client_response_coordinator.py')], 'client_response_coordinator')
    run(['python3', str(WORKDIR / 'agents/email-monitor/revenue_followup_coordinator.py')], 'revenue_followup_coordinator')
    record('task', 'email_monitor.integrated_monitor', status='completed')
    print('ok')


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        record('error', 'email_monitor.integrated_monitor_failed', details=str(e))
        record('task', 'email_monitor.integrated_monitor', status='failed')
        raise
