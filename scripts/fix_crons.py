import json

with open('/root/.openclaw/cron/jobs.json', 'r') as f:
    data = json.load(f)

jobs = data['jobs']
fixed = []

# Fix 1: Healthcheck
for j in jobs:
    if j['id'] == '20dd6135-8228-4cc3-9307-0ce3983a0287':
        j['delivery'] = {'mode': 'announce', 'channel': 'telegram'}
        j['failureAlert'] = {'channel': 'telegram'}
        j['state']['consecutiveErrors'] = 0
        fixed.append('Healthcheck')

# Fix 2: Session prune
for j in jobs:
    if j['id'] == '1893aa85-edb7-400c-a8ff-4186e2879d5a':
        j['delivery'] = {'mode': 'announce', 'channel': 'telegram'}
        j['failureAlert'] = {'channel': 'telegram'}
        j['state']['consecutiveErrors'] = 0
        fixed.append('Session Prune')

# Fix 3-6: Team Motivation - route to main session, announce via telegram
team_ids = [
    'bd3c0135-b1ab-4495-bb6a-5c1db6cb30db',
    '321cab08-9089-4bea-b4fd-1ca4d16a6290',
    '95e70d50-bbd8-4121-b70f-62be9c86f5ad',
    '44575ce7-8802-475a-ae0d-3c8b09c08a51'
]
for j in jobs:
    if j['id'] in team_ids:
        j['sessionKey'] = 'agent:main:main'
        j['delivery'] = {'mode': 'announce', 'channel': 'telegram'}
        j['failureAlert'] = {'channel': 'telegram'}
        j['state']['consecutiveErrors'] = 0
        j['state']['lastError'] = None
        fixed.append(j['name'])

# Fix Market Brief failureAlert
for j in jobs:
    if j['id'] == '6ec2015f-d5bf-4edc-8b97-51ef5d8ab74d':
        if 'failureAlert' not in j:
            j['failureAlert'] = {'channel': 'telegram'}
            fixed.append('Market Brief failureAlert')

data['jobs'] = jobs
with open('/root/.openclaw/cron/jobs.json', 'w') as f:
    json.dump(data, f, indent=2)

print(f"Fixed: {', '.join(fixed)}")
