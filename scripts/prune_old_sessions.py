#!/usr/bin/env python3
import json, os, sys, time

sessions_file = os.path.expanduser('~/.openclaw/agents/main/sessions/sessions.json')
cutoff_ms = 36 * 3600 * 1000  # 36 hours in ms

if not os.path.exists(sessions_file):
    sys.exit(0)

with open(sessions_file, 'r') as f:
    sessions = json.load(f)

now_ms = int(time.time() * 1000)  # refresh on each run
removed = 0
remaining = {}
for key, s in sessions.items():
    updated = s.get('updatedAt', 0)
    if updated and (now_ms - updated) > cutoff_ms:
        removed += 1
    else:
        remaining[key] = s

if removed > 0:
    os.rename(sessions_file, sessions_file + f'.bak.{int(now_ms/1000)}')
    with open(sessions_file, 'w') as f:
        json.dump(remaining, f, indent=2)
    print(f'Pruned {removed} sessions older than 36h')
else:
    print('No sessions older than 36h found')
