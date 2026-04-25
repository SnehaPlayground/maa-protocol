with open('/root/.openclaw/workspace/ops/multi-agent-orchestrator/task_orchestrator.py') as f:
    lines = f.readlines()
print(f'Total lines: {len(lines)}')
for i in range(min(45, len(lines))):
    if lines[i].strip():
        print(f'{i}: {repr(lines[i].rstrip())}')
