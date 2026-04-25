import subprocess, sys
body_content = open('/root/.openclaw/workspace/tree.txt').read()
tmp_body = '/root/.openclaw/workspace/temp/tree_email_body.txt'
open(tmp_body, 'w').write(body_content)
cmd = [
    'python3', 'ops/email/send_email_via_gog.py',
    '--to', 'partha.shah@gmail.com',
    '--subject', 'Maa Protocol — Full Location Map (2026-04-22)',
    '--body-file', tmp_body,
    '--attach', '/root/.openclaw/workspace/tree.txt',
    '--approval-basis', 'direct_user_request'
]
r = subprocess.run(cmd, capture_output=True, text=True)
print('RC:', r.returncode)
print('OUT:', r.stdout[:500])
print('ERR:', r.stderr[:300])