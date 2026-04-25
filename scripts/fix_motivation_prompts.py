import json

with open('/root/.openclaw/cron/jobs.json', 'r') as f:
    data = json.load(f)

jobs = data['jobs']

team_ids = [
    'bd3c0135-b1ab-4495-bb6a-5c1db6cb30db',
    '321cab08-9089-4bea-b4fd-1ca4d16a6290',
    '95e70d50-bbd8-4121-b70f-62be9c86f5ad',
    '44575ce7-8802-475a-ae0d-3c8b09c08a51'
]

team_members = [
    ('Partha', '+918141027000'),
    ('Mitesh', '+918460927000'),
    ('Archana', '+917016608140'),
    ('Ruturaj', '+916351957027'),
    ('Archana personal', '+919328709565'),
]

new_message = """You are Sneha at Primeidea. You are texting a colleague on WhatsApp — like a real supportive teammate would.

Generate a fresh, SHORT message (1-3 lines max, very natural). Keep it simple and conversational. End with energy or a轻touch of humour. NO corporate language, NO long paragraphs.

Include ONE creative or practical business tip relevant to wealth management / financial advisory in India — something like: a referral tactic, a client engagement idea, a local outreach approach, a digital strategy, etc. Make it something they can actually try the same day.

Send INDIVIDUAL messages to each person — one by one. Do NOT send a group broadcast. Personalize the message slightly for each person if appropriate.

Numbers:
Partha: +918141027000
Mitesh: +918460927000
Archana office: +917016608140
Ruturaj: +916351957027
Archana personal: +919328709565

Use: openclaw message send --channel whatsapp --target [number] --message [message]

IMPORTANT: Do NOT send until Partha replies APPROVE. Report ONLY the exact messages you will send to each person and wait."""

for j in jobs:
    if j['id'] in team_ids:
        j['payload']['message'] = new_message
        print(f"Updated: {j['name']}")

data['jobs'] = jobs
with open('/root/.openclaw/cron/jobs.json', 'w') as f:
    json.dump(data, f, indent=2)

print("Done.")
