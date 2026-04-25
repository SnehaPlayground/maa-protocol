#!/usr/bin/env python3
with open('/root/.openclaw/workspace/scripts/tenant_isolation_test.py') as f:
    lines = f.readlines()

# Fix lines 239 and 240 (1-indexed: 239 and 240, 0-indexed: 238 and 239)
lines[238] = "    entry_a = json.dumps({'at': '2026-04-22T10:00:00Z', 'event': 'test_event_a', 'client_id': TEST_CLIENT_A}) + '\\n'\n"
lines[239] = "    entry_b = json.dumps({'at': '2026-04-22T10:00:00Z', 'event': 'test_event_b', 'client_id': TEST_CLIENT_B}) + '\\n'\n"

with open('/root/.openclaw/workspace/scripts/tenant_isolation_test.py', 'w') as f:
    f.writelines(lines)
print("Fixed")
