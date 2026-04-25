import json, os, time, uuid
from pathlib import Path
from tenant_context import TenantContext
from task_orchestrator import submit_task, _task_state_path
from approval_gate import load_state

os.environ['OPENCLAW_OPERATOR_ROLE'] = 'OPERATOR'

base = f'verify_{int(time.time())}_{uuid.uuid4().hex[:4]}'
op = f'{base}_op'

for cl, action in ((f'{base}_cl', 'queue'), (f'{base}_cl2', 'require_approval')):
    client_root = Path(f'/root/.openclaw/workspace/tenants/{op}/clients/{cl}')
    (client_root / 'config').mkdir(parents=True, exist_ok=True)
    with open(client_root / 'config' / 'client.json', 'w') as f:
        json.dump({'max_daily_spend': 1.0, 'exceed_action': action}, f)
    with open(client_root / '.quota.json', 'w') as f:
        json.dump({'_spend_today': 1.0, '_spend_this_month': 1.0, '_last_day_reset': time.time(), '_month_key': int(time.strftime('%Y%m')), '_last_month_reset': time.time()}, f)

queue_id = submit_task('research', 'budget queue verify', tenant_context={'operator_id': op, 'client_id': f'{base}_cl'})
with open(_task_state_path(queue_id, {'operator_id': op, 'client_id': f'{base}_cl'})) as f:
    queue_state = json.load(f)
assert queue_state['status'] == 'queued_budget'

approval_id = submit_task('research', 'budget approval verify', tenant_context={'operator_id': op, 'client_id': f'{base}_cl2'})
with open(_task_state_path(approval_id, {'operator_id': op, 'client_id': f'{base}_cl2'})) as f:
    approval_state = json.load(f)
assert approval_state['status'] == 'waiting_approval'
assert approval_state.get('approval_hash') in load_state().get('approvals', {})

print(json.dumps({'queue_task_id': queue_id, 'queue_status': queue_state['status'], 'approval_task_id': approval_id, 'approval_status': approval_state['status']}, indent=2))
