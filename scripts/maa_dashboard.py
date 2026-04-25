#!/usr/bin/env python3
"""
Maa Protocol — HTML Dashboard Builder

Reads from: data/observability/maa_metrics.json
           logs/pre_deploy_gate_latest.json
           scripts/health_check.py --json
           ops/multi-agent-orchestrator/logs/running_children.json

Output: data/reports/maa_dashboard.html
Auto-refresh: every 60 seconds
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

WORKDIR = Path('/root/.openclaw/workspace')
METRICS_JSON = WORKDIR / 'data/observability/maa_metrics.json'
GATE_STATUS = WORKDIR / 'logs/pre_deploy_gate_latest.json'
HEALTH_SCRIPT = WORKDIR / 'scripts/health_check.py'
RUNNING_CHILDREN = WORKDIR / 'ops/multi-agent-orchestrator/logs/running_children.json'
OUTPUT = WORKDIR / 'data/reports/maa_dashboard.html'

# ── Colors — Maa default palette ──────────────────────────────────────────────────
NAVY      = '#0d2137'
DARK_BLUE = '#1a3a5c'
MID_BLUE  = '#2d6a9f'
GREEN     = '#1a7a4a'
RED       = '#c0392b'
AMBER     = '#d68910'
LIGHT_GRAY= '#f4f6f9'
MID_GRAY  = '#b0bec5'
WHITE     = '#ffffff'
TEXT_DARK = '#1a1a2e'
TEXT_MUTED= '#6c7a89'

NOW_UTC = datetime.now(timezone.utc)


# ── Helpers ────────────────────────────────────────────────────────────────────

def load_json(path: Path, default=dict):
    if not path.exists():
        return default()
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default()


def ts_age_minutes(ts_str: str) -> float:
    try:
        ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
        return (NOW_UTC - ts.astimezone(timezone.utc)).total_seconds() / 60
    except Exception:
        return 0


def fmt_age(ts_str: str) -> str:
    m = ts_age_minutes(ts_str)
    if m < 1:   return '<1m ago'
    if m < 60:  return f'{int(m)}m ago'
    h = int(m // 60)
    if h < 24:  return f'{h}h {int(m % 60)}m ago'
    d = int(h // 24)
    return f'{d}d {h % 24}h ago'


def error_rate_class(rate: float) -> str:
    if rate >= 5:   return 'status-red'
    if rate >= 2:   return 'status-amber'
    return 'status-green'


# ── Data Loading ───────────────────────────────────────────────────────────────

def load_metrics():
    return load_json(METRICS_JSON, dict)

def load_gate():
    return load_json(GATE_STATUS, dict)

def load_health():
    try:
        result = subprocess.run(
            [sys.executable, str(HEALTH_SCRIPT), '--json'],
            capture_output=True, text=True, timeout=10
        )
        return json.loads(result.stdout)
    except Exception:
        return {}

def load_running_children():
    return load_json(RUNNING_CHILDREN, dict)

def recent_errors(metrics: dict, limit: int = 10):
    errors = metrics.get('errors', [])
    return sorted(errors, key=lambda e: e.get('timestamp', ''), reverse=True)[:limit]

def agent_breakdown(metrics: dict) -> dict:
    """Compute per-agent call/error/latency counts."""
    calls   = metrics.get('calls',   [])
    errors  = metrics.get('errors',  [])
    latency = metrics.get('latency', [])
    agents = {}
    for c in calls:
        ag = c.get('agent', 'unknown')
        agents.setdefault(ag, {'calls': 0, 'errors': 0, 'latencies': []})['calls'] += 1
    for e in errors:
        ag = e.get('agent', 'unknown')
        agents.setdefault(ag, {'calls': 0, 'errors': 0, 'latencies': []})['errors'] += 1
    for l in latency:
        ag = l.get('agent', 'unknown')
        agents.setdefault(ag, {'calls': 0, 'errors': 0, 'latencies': []})['latencies'].append(l.get('value_ms', 0))
    return agents

def maintenance_actions() -> list[dict]:
    decisions_dir = WORKDIR / 'memory' / 'maintenance_decisions'
    if not decisions_dir.exists():
        return []
    cutoff = NOW_UTC - timedelta(days=7)
    actions = []
    for f in sorted(decisions_dir.glob('*.jsonl'), reverse=True):
        try:
            ts_str = f.stem
            file_date = datetime.strptime(ts_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)
            if file_date < cutoff:
                break
        except ValueError:
            continue
        try:
            for line in f.read_text(encoding='utf-8').strip().split('\n'):
                if line.strip():
                    try:
                        obj = json.loads(line)
                        obj['_file'] = ts_str
                        actions.append(obj)
                    except json.JSONDecodeError:
                        pass
        except Exception:
            pass
    try:
        actions.sort(key=lambda a: a.get('timestamp', ''), reverse=True)
    except Exception:
        pass
    return actions[:15]


# ── Status Payload ─────────────────────────────────────────────────────────────

def get_status_payload(metrics, gate, health, running) -> dict:
    """Single-message status for any interaction surface."""
    agents = agent_breakdown(metrics)

    # Per-agent error rate: only count agents with actual operational calls/tasks
    # Filter out the "audit" agent that only appears in regression test errors
    operational_agents = {ag: d for ag, d in agents.items()
                          if ag != 'audit' or d['calls'] > 0 or d['errors'] > 0}

    real_errors = sum(d['errors'] for ag, d in operational_agents.items() if ag != 'audit')
    real_calls  = sum(d['calls']  for ag, d in operational_agents.items() if ag != 'audit')

    gate_pass = gate.get('status') == 'pass'
    disk_ok   = (health.get('disk', {}).get('usage_pct', 0) or 0) < 85
    mem_ok    = (health.get('resources', {}).get('memory_pct', 0) or 0) < 90

    # Core system status
    system_ok = gate_pass and disk_ok and mem_ok
    status_icon = '✅' if system_ok else '🔴'

    return {
        'status':          f"{status_icon} MAA {'OK' if system_ok else 'DEGRADED'}",
        'operational_errors': f"{real_errors} err / {real_calls} calls",
        'real_error_rate_pct': round((real_errors / real_calls * 100) if real_calls > 0 else 0, 1),
        'disk_pct':        health.get('disk', {}).get('usage_pct', 0),
        'mem_pct':         health.get('resources', {}).get('memory_pct', 0),
        'tasks_running':   len(running.get('task_ids', [])),
        'gate_status':     gate.get('status', 'unknown'),
        'gate_passed':     gate.get('passed', 0),
        'uptime_hrs':      round((NOW_UTC.timestamp() - metrics.get('start_time', 0)) / 3600, 1),
        'health_icon':     status_icon,
    }


# ── Section Builders ───────────────────────────────────────────────────────────

def build_topbar(gate, uptime_hrs_str):
    gate_label = 'PASS ✅' if gate.get('status') == 'pass' else 'FAIL ❌'
    return f"""<div style="background:{NAVY};color:{WHITE};padding:16px 24px;display:flex;justify-content:space-between;align-items:center;font-family:'Segoe UI',system-ui,sans-serif;">
  <div>
    <div style="font-size:18px;font-weight:600;letter-spacing:0.3px;">Maa Protocol — Operations Dashboard</div>
    <div style="font-size:12px;color:{MID_GRAY};margin-top:2px;">Maa Deployment</div>
  </div>
  <div style="text-align:right;">
    <div style="font-size:13px;font-weight:600;">Gate: {gate_label}</div>
    <div style="font-size:11px;color:{MID_GRAY};">Uptime: {uptime_hrs_str} &nbsp;·&nbsp; Auto-refresh: 60s</div>
  </div>
</div>"""


def build_summary_strip(metrics, gate, health, running):
    agents = agent_breakdown(metrics)
    # Real operational metrics (exclude audit regression noise)
    real_errors = sum(d['errors'] for ag, d in agents.items() if ag != 'audit')
    real_calls  = sum(d['calls']  for ag, d in agents.items() if ag != 'audit')
    real_rate   = (real_errors / real_calls * 100) if real_calls > 0 else 0

    disk_pct = health.get('disk', {}).get('usage_pct', 0)
    mem_pct  = health.get('resources', {}).get('memory_pct', 0)
    tasks    = metrics.get('tasks', [])
    completed = sum(1 for t in tasks if t.get('status') == 'completed')
    running_count = len(running.get('task_ids', []))
    gate_pass = gate.get('status') == 'pass'

    def card(label, value, sub=''):
        return (f'<div style="background:{LIGHT_GRAY};border-radius:8px;padding:12px 16px;'
                f'border:1px solid #dde3ea;text-align:center;flex:1;min-width:140px;">'
                f'<div style="font-size:11px;text-transform:uppercase;letter-spacing:0.8px;color:{TEXT_MUTED};margin-bottom:4px;">{label}</div>'
                f'<div style="font-size:26px;font-weight:700;color:{TEXT_DARK};">{value}</div>'
                f'{"<div style=\'font-size:11px;color:" + TEXT_MUTED + ";margin-top:2px;\'>" + sub + "</div>" if sub else ""}'
                f'</div>')

    return (f'<div style="display:flex;gap:12px;padding:16px 24px;background:{WHITE};'
            f'border-bottom:1px solid #dde3ea;flex-wrap:wrap;">'
            f'{card("Total Tasks", len(tasks), f"{completed} completed")}'
            f'{card("Error Rate", f"{real_rate:.1f}%", f"{real_errors} errors")}'
            f'{card("Active Agents", running_count, "child tasks")}'
            f'{card("Disk", f"{disk_pct:.1f}%", "storage used")}'
            f'{card("Memory", f"{mem_pct:.1f}%", "RAM used")}'
            f'{card("Gate", "PASS" if gate_pass else "FAIL", "pre-deploy")}'
            f'</div>')


def build_predeploy_gate(gate):
    status  = gate.get('status', 'unknown')
    passed  = gate.get('passed', 0)
    failed  = gate.get('failed', 0)
    run_at  = gate.get('run_at', 'unknown')
    failures = gate.get('failures', [])

    badge_cls  = 'background:#e8f5ee;color:#1a7a4a;' if status == 'pass' else 'background:#fdf0ef;color:#c0392b;'
    badge_icon = '&#10003;' if status == 'pass' else '&#10007;'
    fail_rows  = ''
    if failures:
        fail_rows = ('<div style="margin-top:8px;"><strong style="font-size:12px;color:#c0392b;">Failed:</strong>'
                     '<ul style="margin-top:4px;font-size:12px;color:#6c7a89;font-family:monospace;padding-left:18px;">'
                     + ''.join(f'<li>{f}</li>' for f in failures) + '</ul></div>')

    return f"""<div style="background:{WHITE};border-radius:10px;border:1px solid #dde3ea;margin-bottom:20px;overflow:hidden;">
  <div style="background:{DARK_BLUE};color:{WHITE};padding:10px 18px;font-size:13px;font-weight:600;letter-spacing:0.5px;text-transform:uppercase;display:flex;justify-content:space-between;align-items:center;">
    Pre-Deploy Gate <span style="background:{MID_BLUE};color:{WHITE};border-radius:10px;padding:2px 8px;font-size:11px;">{fmt_age(run_at)}</span>
  </div>
  <div style="padding:16px 20px;">
    <div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap;">
      <span style="display:inline-flex;align-items:center;gap:6px;border-radius:6px;padding:6px 14px;font-weight:600;font-size:13px;{badge_cls}">
        <span style="font-size:16px;">{badge_icon}</span> {'PASS' if status=='pass' else 'FAIL'}
      </span>
      <span style="font-size:13px;color:{TEXT_MUTED};">
        <strong>{passed}</strong> passed{f'&nbsp;&nbsp;<strong style="color:#c0392b;">{failed}</strong> failed' if failed else ''}
        &nbsp;&nbsp;|&nbsp;&nbsp; Last run: {fmt_age(run_at)}
      </span>
    </div>
    {fail_rows}
  </div>
</div>"""


def build_agent_breakdown(metrics):
    agents = agent_breakdown(metrics)
    if not agents:
        return ''

    # Separate operational vs audit-regression
    rows = []
    for ag, data in sorted(agents.items(), key=lambda x: -x[1]['calls']):
        c  = data['calls']
        e  = data['errors']
        latencies = data.get('latencies', [])
        rate = (e / c * 100) if c > 0 else 0
        avg_lat = (sum(latencies) / len(latencies)) if latencies else 0
        cls = error_rate_class(rate)
        err_color = RED if e > 0 else TEXT_MUTED
        rows.append(f"""<tr>
  <td><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:{GREEN if rate < 2 else AMBER if rate < 5 else RED};margin-right:6px;"></span>{ag}</td>
  <td style="text-align:right;">{c}</td>
  <td style="text-align:right;color:{err_color};">{e}</td>
  <td style="text-align:right;">{rate:.1f}%</td>
  <td style="text-align:right;color:{TEXT_MUTED};">{avg_lat:.0f}ms</td>
</tr>""")

    total_c  = sum(d['calls'] for d in agents.values())
    total_e  = sum(d['errors'] for d in agents.values())
    total_rate = (total_e / total_c * 100) if total_c > 0 else 0

    return f"""<div style="background:{WHITE};border-radius:10px;border:1px solid #dde3ea;margin-bottom:20px;overflow:hidden;">
  <div style="background:{DARK_BLUE};color:{WHITE};padding:10px 18px;font-size:13px;font-weight:600;letter-spacing:0.5px;text-transform:uppercase;display:flex;justify-content:space-between;align-items:center;">
    Agent Breakdown <span style="background:{MID_BLUE};color:{WHITE};border-radius:10px;padding:2px 8px;font-size:11px;">{len(agents)} agents</span>
  </div>
  <table style="width:100%;border-collapse:collapse;">
    <thead><tr style="background:{LIGHT_GRAY};">
      <th style="text-align:left;padding:8px 16px;font-size:11px;text-transform:uppercase;letter-spacing:0.6px;color:{TEXT_MUTED};border-bottom:1px solid #dde3ea;">Agent</th>
      <th style="text-align:right;padding:8px 16px;font-size:11px;text-transform:uppercase;letter-spacing:0.6px;color:{TEXT_MUTED};border-bottom:1px solid #dde3ea;">Calls</th>
      <th style="text-align:right;padding:8px 16px;font-size:11px;text-transform:uppercase;letter-spacing:0.6px;color:{TEXT_MUTED};border-bottom:1px solid #dde3ea;">Errors</th>
      <th style="text-align:right;padding:8px 16px;font-size:11px;text-transform:uppercase;letter-spacing:0.6px;color:{TEXT_MUTED};border-bottom:1px solid #dde3ea;">Error Rate</th>
      <th style="text-align:right;padding:8px 16px;font-size:11px;text-transform:uppercase;letter-spacing:0.6px;color:{TEXT_MUTED};border-bottom:1px solid #dde3ea;">Avg Latency</th>
    </tr></thead>
    <tbody>
      {''.join(rows)}
      <tr style="background:{LIGHT_GRAY};font-weight:600;border-top:2px solid #dde3ea;">
        <td style="padding:8px 16px;">ALL AGENTS</td>
        <td style="text-align:right;padding:8px 16px;">{total_c}</td>
        <td style="text-align:right;padding:8px 16px;">{total_e}</td>
        <td style="text-align:right;padding:8px 16px;">{total_rate:.1f}%</td>
        <td style="text-align:right;padding:8px 16px;"></td>
      </tr>
    </tbody>
  </table>
</div>"""


def build_circuit_breaker_status(metrics):
    agents = agent_breakdown(metrics)
    rows = []
    for ag, data in sorted(agents.items(), key=lambda x: -x[1]['errors']):
        c = data['calls']
        e = data['errors']
        rate = (e / c * 100) if c > 0 else 0
        is_open = rate >= 5
        dot_color = GREEN if not is_open else RED
        state_str = 'CLOSED' if not is_open else 'OPEN'
        state_color = TEXT_MUTED if not is_open else RED
        rows.append(f"""<tr>
  <td style="padding:8px 16px;border-bottom:1px solid #f0f4f8;">
    <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:{dot_color};margin-right:6px;"></span>{ag}
  </td>
  <td style="text-align:right;padding:8px 16px;border-bottom:1px solid #f0f4f8;">{rate:.1f}%</td>
  <td style="text-align:right;padding:8px 16px;border-bottom:1px solid #f0f4f8;">
    <span style="font-size:11px;font-weight:600;color:{state_color};">{state_str}</span>
  </td>
</tr>""")

    return f"""<div style="background:{WHITE};border-radius:10px;border:1px solid #dde3ea;margin-bottom:20px;overflow:hidden;">
  <div style="background:{DARK_BLUE};color:{WHITE};padding:10px 18px;font-size:13px;font-weight:600;letter-spacing:0.5px;text-transform:uppercase;display:flex;justify-content:space-between;align-items:center;">
    Circuit Breaker Status <span style="background:{MID_BLUE};color:{WHITE};border-radius:10px;padding:2px 8px;font-size:11px;">5% threshold</span>
  </div>
  <table style="width:100%;border-collapse:collapse;">
    <thead><tr style="background:{LIGHT_GRAY};">
      <th style="text-align:left;padding:8px 16px;font-size:11px;text-transform:uppercase;letter-spacing:0.6px;color:{TEXT_MUTED};border-bottom:1px solid #dde3ea;">Agent</th>
      <th style="text-align:right;padding:8px 16px;font-size:11px;text-transform:uppercase;letter-spacing:0.6px;color:{TEXT_MUTED};border-bottom:1px solid #dde3ea;">Error Rate (1h)</th>
      <th style="text-align:right;padding:8px 16px;font-size:11px;text-transform:uppercase;letter-spacing:0.6px;color:{TEXT_MUTED};border-bottom:1px solid #dde3ea;">State</th>
    </tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</div>"""


def build_recent_errors(metrics):
    errors = recent_errors(metrics, 10)
    if not errors:
        return f"""<div style="background:{WHITE};border-radius:10px;border:1px solid #dde3ea;margin-bottom:20px;overflow:hidden;">
  <div style="background:{DARK_BLUE};color:{WHITE};padding:10px 18px;font-size:13px;font-weight:600;letter-spacing:0.5px;text-transform:uppercase;">Recent Errors <span style="background:{MID_BLUE};color:{WHITE};border-radius:10px;padding:2px 8px;font-size:11px;margin-left:8px;">0</span></div>
  <div style="padding:16px 20px;color:{TEXT_MUTED};font-size:13px;">No errors recorded.</div>
</div>"""

    rows = []
    for e in errors:
        label = e.get('label', 'unknown')
        details = e.get('details', '')
        ts = e.get('timestamp', '')
        stack = e.get('stack_trace', '').strip()
        # Expandable stack trace
        stack_html = ''
        if stack and stack != 'None\n':
            stack_html = (f'<details style="margin-top:4px;"><summary style="cursor:pointer;font-size:11px;color:{MID_BLUE};">Stack trace</summary>'
                          f'<pre style="font-family:monospace;font-size:11px;color:{TEXT_MUTED};background:{LIGHT_GRAY};padding:8px;margin-top:4px;overflow-x:auto;max-height:120px;">{stack[:800]}</pre></details>')

        rows.append(f"""<tr style="border-bottom:1px solid #f0f4f8;">
  <td style="padding:10px 16px;">
    <div style="font-family:'Courier New',monospace;font-size:12px;color:{TEXT_DARK};">{label}</div>
    <div style="font-size:12px;color:{TEXT_MUTED};margin-top:2px;">{details}</div>
    {stack_html}
  </td>
  <td style="text-align:right;padding:10px 16px;white-space:nowrap;font-size:11px;color:{TEXT_MUTED};vertical-align:top;">{fmt_age(ts)}</td>
</tr>""")

    return f"""<div style="background:{WHITE};border-radius:10px;border:1px solid #dde3ea;margin-bottom:20px;overflow:hidden;">
  <div style="background:{DARK_BLUE};color:{WHITE};padding:10px 18px;font-size:13px;font-weight:600;letter-spacing:0.5px;text-transform:uppercase;display:flex;justify-content:space-between;align-items:center;">
    Recent Errors <span style="background:{MID_BLUE};color:{WHITE};border-radius:10px;padding:2px 8px;font-size:11px;">{len(errors)} shown</span>
  </div>
  <table style="width:100%;border-collapse:collapse;">
    <thead><tr style="background:{LIGHT_GRAY};">
      <th style="text-align:left;padding:8px 16px;font-size:11px;text-transform:uppercase;letter-spacing:0.6px;color:{TEXT_MUTED};border-bottom:1px solid #dde3ea;">Error</th>
      <th style="text-align:right;padding:8px 16px;font-size:11px;text-transform:uppercase;letter-spacing:0.6px;color:{TEXT_MUTED};border-bottom:1px solid #dde3ea;">Time</th>
    </tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</div>"""


def build_system_health(health):
    disk = health.get('disk', {})
    res  = health.get('resources', {})

    disk_pct = disk.get('usage_pct', 0)
    mem_pct  = res.get('memory_pct', 0)
    cpu_pct  = res.get('cpu_pct', 0)

    def row(label, value, note, pct):
        dot = GREEN if pct < 70 else AMBER if pct < 85 else RED
        return (f'<tr><td style="padding:8px 16px;border-bottom:1px solid #f0f4f8;">'
                f'<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:{dot};margin-right:6px;"></span>{label}'
                f'</td><td style="text-align:right;padding:8px 16px;border-bottom:1px solid #f0f4f8;"><strong>{value}</strong></td>'
                f'<td style="padding:8px 16px;border-bottom:1px solid #f0f4f8;font-size:12px;color:{TEXT_MUTED};">{note}</td></tr>')

    rows_str = row('Disk Usage', f'{disk_pct:.1f}%', f'{disk.get("free_gb","?")} GB free of {disk.get("total_gb","?")} GB', disk_pct)
    rows_str += row('Memory',    f'{mem_pct:.1f}%',  f'{res.get("memory_used_gb","?")} GB / {res.get("memory_total_gb","?")} GB', mem_pct)
    rows_str += row('CPU',       f'{cpu_pct:.1f}%',   'Current utilization', cpu_pct)

    return f"""<div style="background:{WHITE};border-radius:10px;border:1px solid #dde3ea;margin-bottom:20px;overflow:hidden;">
  <div style="background:{DARK_BLUE};color:{WHITE};padding:10px 18px;font-size:13px;font-weight:600;letter-spacing:0.5px;text-transform:uppercase;">
    System Health
  </div>
  <table style="width:100%;border-collapse:collapse;">{rows_str}</table>
</div>"""


def build_task_snapshot(metrics, running):
    from collections import Counter
    tasks = metrics.get('tasks', [])
    status_counts = Counter(t.get('status', 'unknown') for t in tasks)
    total      = len(tasks)
    completed  = status_counts.get('completed', 0)
    running_ct = len(running.get('task_ids', []))

    def chip(count, label):
        return (f'<div style="text-align:center;padding:10px 0;flex:1;min-width:80px;">'
                f'<div style="font-size:22px;font-weight:700;color:{TEXT_DARK};">{count}</div>'
                f'<div style="font-size:11px;color:{TEXT_MUTED};text-transform:uppercase;letter-spacing:0.5px;margin-top:2px;">{label}</div>'
                f'</div>')

    chips = (f'<div style="display:flex;gap:0;flex-wrap:wrap;border-top:1px solid #dde3ea;">'
             f'{chip(total, "Total")}'
             f'<div style="width:1px;background:#dde3ea;"></div>'
             f'{chip(completed, "Completed")}'
             f'<div style="width:1px;background:#dde3ea;"></div>'
             f'{chip(running_ct, "Running")}'
             f'<div style="width:1px;background:#dde3ea;"></div>'
             f'{chip(status_counts.get("pending",0), "Pending")}'
             f'<div style="width:1px;background:#dde3ea;"></div>'
             f'{chip(status_counts.get("queued",0), "Queued")}'
             f'</div>')

    return f"""<div style="background:{WHITE};border-radius:10px;border:1px solid #dde3ea;margin-bottom:20px;overflow:hidden;">
  <div style="background:{DARK_BLUE};color:{WHITE};padding:10px 18px;font-size:13px;font-weight:600;letter-spacing:0.5px;text-transform:uppercase;display:flex;justify-content:space-between;align-items:center;">
    Task Snapshot <span style="background:{MID_BLUE};color:{WHITE};border-radius:10px;padding:2px 8px;font-size:11px;">live</span>
  </div>
  <div style="padding:16px 20px;">{chips}</div>
</div>"""


def build_running_children(running):
    task_ids  = running.get('task_ids', [])
    updated_at = running.get('updated_at', '')

    if not task_ids:
        chip = (f'<span style="display:inline-block;background:#e8f5ee;color:#1a7a4a;border-radius:6px;'
                f'padding:5px 12px;font-size:12px;font-weight:600;">&#10003; No running tasks</span>')
    else:
        chip = (f'<span style="display:inline-block;background:#fff3e0;color:#d68910;border-radius:6px;'
                f'padding:5px 12px;font-size:12px;font-weight:600;">{len(task_ids)} task(s) running</span>')

    rows = ''.join(f'<li style="font-family:monospace;font-size:12px;padding:3px 0;color:{TEXT_DARK};">{tid}</li>'
                   for tid in task_ids)

    inner = chip + (f'<ul style="margin-top:10px;list-style:none;padding:0;">{rows}</ul>' if rows else '')
    return f"""<div style="background:{WHITE};border-radius:10px;border:1px solid #dde3ea;margin-bottom:20px;overflow:hidden;">
  <div style="background:{DARK_BLUE};color:{WHITE};padding:10px 18px;font-size:13px;font-weight:600;letter-spacing:0.5px;text-transform:uppercase;display:flex;justify-content:space-between;align-items:center;">
    Active Child Agents <span style="background:{MID_BLUE};color:{WHITE};border-radius:10px;padding:2px 8px;font-size:11px;">{fmt_age(updated_at)}</span>
  </div>
  <div style="padding:16px 20px;">{inner}</div>
</div>"""


def build_maintenance_actions():
    actions = maintenance_actions()
    if not actions:
        return f"""<div style="background:{WHITE};border-radius:10px;border:1px solid #dde3ea;margin-bottom:20px;overflow:hidden;">
  <div style="background:{DARK_BLUE};color:{WHITE};padding:10px 18px;font-size:13px;font-weight:600;letter-spacing:0.5px;text-transform:uppercase;">Recent Maintenance</div>
  <div style="padding:16px 20px;color:{TEXT_MUTED};font-size:13px;">No maintenance actions in the last 7 days.</div>
</div>"""

    rows = []
    for a in actions[:10]:
        ts     = a.get('timestamp', a.get('_file', ''))
        action = a.get('action', 'unknown')
        outcome= a.get('outcome', '')
        rows.append(f"""<tr>
  <td style="padding:8px 16px;font-size:12px;color:{TEXT_MUTED};white-space:nowrap;border-bottom:1px solid #f0f4f8;">{fmt_age(ts)}</td>
  <td style="padding:8px 16px;border-bottom:1px solid #f0f4f8;"><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:{GREEN};margin-right:6px;"></span>{action}</td>
  <td style="padding:8px 16px;font-size:12px;color:{TEXT_MUTED};border-bottom:1px solid #f0f4f8;">{outcome}</td>
</tr>""")

    return f"""<div style="background:{WHITE};border-radius:10px;border:1px solid #dde3ea;margin-bottom:20px;overflow:hidden;">
  <div style="background:{DARK_BLUE};color:{WHITE};padding:10px 18px;font-size:13px;font-weight:600;letter-spacing:0.5px;text-transform:uppercase;display:flex;justify-content:space-between;align-items:center;">
    Recent Maintenance <span style="background:{MID_BLUE};color:{WHITE};border-radius:10px;padding:2px 8px;font-size:11px;">7 day</span>
  </div>
  <table style="width:100%;border-collapse:collapse;">
    <thead><tr style="background:{LIGHT_GRAY};">
      <th style="text-align:left;padding:8px 16px;font-size:11px;text-transform:uppercase;letter-spacing:0.6px;color:{TEXT_MUTED};border-bottom:1px solid #dde3ea;">Time</th>
      <th style="text-align:left;padding:8px 16px;font-size:11px;text-transform:uppercase;letter-spacing:0.6px;color:{TEXT_MUTED};border-bottom:1px solid #dde3ea;">Action</th>
      <th style="text-align:left;padding:8px 16px;font-size:11px;text-transform:uppercase;letter-spacing:0.6px;color:{TEXT_MUTED};border-bottom:1px solid #dde3ea;">Outcome</th>
    </tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</div>"""


def build_latency_summary(metrics):
    """Average latency per agent from latency bucket."""
    latency = metrics.get('latency', [])
    if not latency:
        return ''
    from collections import defaultdict
    by_agent = defaultdict(list)
    for entry in latency:
        by_agent[entry.get('agent', 'unknown')].append(entry.get('value_ms', 0))

    rows = []
    for ag, values in sorted(by_agent.items(), key=lambda x: -len(x[1])):
        avg = sum(values) / len(values)
        rows.append(f"""<tr>
  <td style="padding:8px 16px;border-bottom:1px solid #f0f4f8;">{ag}</td>
  <td style="text-align:right;padding:8px 16px;border-bottom:1px solid #f0f4f8;">{len(values)}</td>
  <td style="text-align:right;padding:8px 16px;border-bottom:1px solid #f0f4f8;">{avg:.0f} ms</td>
</tr>""")

    return f"""<div style="background:{WHITE};border-radius:10px;border:1px solid #dde3ea;margin-bottom:20px;overflow:hidden;">
  <div style="background:{DARK_BLUE};color:{WHITE};padding:10px 18px;font-size:13px;font-weight:600;letter-spacing:0.5px;text-transform:uppercase;display:flex;justify-content:space-between;align-items:center;">
    Latency Summary <span style="background:{MID_BLUE};color:{WHITE};border-radius:10px;padding:2px 8px;font-size:11px;">avg ms</span>
  </div>
  <table style="width:100%;border-collapse:collapse;">
    <thead><tr style="background:{LIGHT_GRAY};">
      <th style="text-align:left;padding:8px 16px;font-size:11px;text-transform:uppercase;letter-spacing:0.6px;color:{TEXT_MUTED};border-bottom:1px solid #dde3ea;">Agent</th>
      <th style="text-align:right;padding:8px 16px;font-size:11px;text-transform:uppercase;letter-spacing:0.6px;color:{TEXT_MUTED};border-bottom:1px solid #dde3ea;">Ops</th>
      <th style="text-align:right;padding:8px 16px;font-size:11px;text-transform:uppercase;letter-spacing:0.6px;color:{TEXT_MUTED};border-bottom:1px solid #dde3ea;">Avg Latency</th>
    </tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</div>"""


def build_uptime_strip(metrics):
    start_ts = metrics.get('start_time', 0)
    if start_ts:
        uptime_s = NOW_UTC.timestamp() - start_ts
        h = int(uptime_s // 3600)
        m = int((uptime_s % 3600) // 60)
        uptime_str = f'{h}h {m}m'
    else:
        uptime_str = 'unknown'

    return f"""<div style="background:{WHITE};border-radius:10px;border:1px solid #dde3ea;margin-bottom:20px;overflow:hidden;">
  <div style="background:{DARK_BLUE};color:{WHITE};padding:10px 18px;font-size:13px;font-weight:600;letter-spacing:0.5px;text-transform:uppercase;">System Uptime</div>
  <div style="padding:16px 20px;font-size:22px;font-weight:700;color:{TEXT_DARK};">{uptime_str}</div>
</div>"""


# ── Grid Layout Helper ─────────────────────────────────────────────────────────

def grid_row(left, right):
    """Two-column grid row. Each is a standalone section, not nested."""
    return f"""<div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px;max-width:1400px;padding:0 24px;box-sizing:border-box;">
  <div>{left}</div>
  <div>{right}</div>
</div>"""


def full_width(section):
    return f'<div style="max-width:1400px;padding:0 24px;margin-bottom:20px;box-sizing:border-box;">{section}</div>'


# ── Main Builder ───────────────────────────────────────────────────────────────

def build_dashboard():
    metrics = load_metrics()
    gate    = load_gate()
    health  = load_health()
    running = load_running_children()

    payload = get_status_payload(metrics, gate, health, running)

    # Uptime string for topbar
    start_ts = metrics.get('start_time', 0)
    if start_ts:
        uptime_s = NOW_UTC.timestamp() - start_ts
        h = int(uptime_s // 3600)
        m = int((uptime_s % 3600) // 60)
        uptime_str = f'{h}h {m}m'
    else:
        uptime_str = 'unknown'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <meta http-equiv="refresh" content="60" />
  <title>Maa Protocol — Operations Dashboard</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; background: {LIGHT_GRAY}; color: {TEXT_DARK}; font-size: 14px; line-height: 1.5; }}
    tr:hover td {{ background: #fafcff; }}
    @media (max-width: 768px) {{
      div[style*="grid-template-columns:1fr 1fr"] {{ grid-template-columns: 1fr !important; }}
    }}
  </style>
</head>
<body>
{build_topbar(gate, uptime_str)}
{build_summary_strip(metrics, gate, health, running)}
<div style="padding:20px 24px;max-width:1400px;">
  {full_width(build_predeploy_gate(gate))}
  {grid_row(build_agent_breakdown(metrics), build_recent_errors(metrics))}
  {grid_row(build_circuit_breaker_status(metrics), build_running_children(running))}
  {grid_row(build_task_snapshot(metrics, running), build_maintenance_actions())}
  {grid_row(build_system_health(health), build_latency_summary(metrics))}
  {full_width(build_uptime_strip(metrics))}
</div>
  <script>window.MAA_STATUS = {json.dumps(payload)};</script>
</body>
</html>"""

    OUTPUT.write_text(html, encoding='utf-8')
    print(f"Dashboard written to: {OUTPUT}")


if __name__ == '__main__':
    build_dashboard()