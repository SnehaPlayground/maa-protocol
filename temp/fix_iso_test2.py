#!/usr/bin/env python3
with open('/root/.openclaw/workspace/scripts/tenant_isolation_test.py') as f:
    lines = f.readlines()

# Remove the dangling '\n' line at 241 (0-indexed: 240)
if lines[240].strip() == '' or lines[240].strip() == '"\'"':
    del lines[240]
    print(f"Deleted line 241 (was: {repr(lines[240+1] if len(lines) > 240 else 'N/A')})")

# Also check line 242 (after deletion, what was 242 is now 241)
if len(lines) > 241:
    print(repr(lines[241]))

with open('/root/.openclaw/workspace/scripts/tenant_isolation_test.py', 'w') as f:
    f.writelines(lines)
print("Done")
