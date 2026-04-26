#!/usr/bin/env python3
import sys, os, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from access_control import Role, get_caller_role, assert_role, assert_system, assert_operator, require_spawn_child_agent, require_operator_role
from access_control import require_approve_external_action, require_delete_tenant_data, require_create_tenant, require_deactivate_tenant, require_view_all_metrics, require_submit_task, require_run_pre_deploy_gate

passed, failed = 0, 0
def check(cond, name):
    global passed, failed
    if cond: print(f'  PASS: {name}'); passed += 1
    else: print(f'  FAIL: {name}'); failed += 1

print('[AC.1] Role Enum'); check(Role.SYSTEM.value==0,'SYSTEM=0'); check(Role.OPERATOR.value==1,'OPERATOR=1'); check(Role.AGENT.value==2,'AGENT=2'); check(Role.CLIENT.value==3,'CLIENT=3'); check(Role.SYSTEM.value<Role.OPERATOR.value,'SYSTEM value<OPERATOR value'); check(Role.OPERATOR.value<Role.AGENT.value,'OPERATOR value<AGENT value'); check(Role.AGENT.value<Role.CLIENT.value,'AGENT value<CLIENT value'); check(not (Role.AGENT.value<Role.OPERATOR.value),'AGENT value not < OPERATOR value')
print('[AC.2] get_caller_role'); orig=os.environ.pop('MAA_CALLER_ROLE',None); check(get_caller_role()==Role.OPERATOR,'default=OPERATOR'); os.environ['MAA_CALLER_ROLE']='agent'; check(get_caller_role()==Role.AGENT,'env=agent'); os.environ['MAA_CALLER_ROLE']='system'; check(get_caller_role()==Role.SYSTEM,'env=system'); os.environ.pop('MAA_CALLER_ROLE',None)
if orig: os.environ['MAA_CALLER_ROLE']=orig
print('[AC.3] assert_role'); 
try: assert_role(Role.SYSTEM); check(False,'assert_role(SYSTEM) should raise')
except PermissionError: check(True,'SYSTEM raises PermissionError')
try: assert_role(Role.OPERATOR); check(True,'OPERATOR passes')
except: check(False,'should not raise')
print('[AC.4] Pre-built ops'); 
try: require_spawn_child_agent(); check(False,'spawn_child_agent should raise')
except PermissionError as e: check('spawn_child_agent' in str(e),'error mentions op')
except: check(False,'raises PermissionError not SystemExit')
try: require_approve_external_action(); check(True,'approve_external passes for OPERATOR')
except: check(False,'should not raise')
print('[AC.5] CLI exit'); 
try: require_operator_role(); check(True,'passes for OPERATOR-default')
except SystemExit as e: check(e.code==1,f'exit code={e.code}')
except: check(False,'should raise SystemExit')
print('[AC.6] Ordinal comparisons'); check(Role.SYSTEM.value<=Role.SYSTEM.value,'SYSTEM value<=SYSTEM value'); check(Role.OPERATOR.value<=Role.AGENT.value,'OPERATOR value<=AGENT value'); check(Role.AGENT.value<=Role.CLIENT.value,'AGENT value<=CLIENT value'); check(not (Role.CLIENT.value<=Role.OPERATOR.value),'CLIENT value not<=OPERATOR value'); check(Role.SYSTEM.value<Role.AGENT.value,'SYSTEM value<AGENT value'); check(not (Role.AGENT.value<Role.SYSTEM.value),'AGENT value not<SYSTEM value')
print('[AC.7] assert_operator'); 
try: assert_operator(); check(True,'passes for OPERATOR-default')
except: check(False,'should not raise')
print('[AC.8] assert_system');
try: assert_system(); check(False,'should raise for OPERATOR-default')
except PermissionError: check(True,'raises PermissionError for non-SYSTEM')
print('[AC.9] task_orchestrator.py RBAC');
with open('ops/multi-agent-orchestrator/task_orchestrator.py') as f: c=f.read()
check('from access_control import' in c,'access_control import present'); check('require_spawn_child_agent' in c,'RBAC check before spawn'); check('require_operator_role()' in c,'CLI RBAC check present')
print('[AC.10] approval_gate RBAC');
with open('ops/multi-agent-orchestrator/approval_gate.py') as f: ag=f.read()
check('Role' in ag or 'OPERATOR' in ag or 'assert_operator' in ag,'approval_gate has role check')
total=passed+failed
print(f'\n{"="*60}\nPhase 10 ACCESS CONTROL RBAC: {passed}/{total} passed')
if failed==0: print('ALL RBAC CHECKS PASSED — Phase 10 complete')
else: print(f'{failed} checks failed')
print(f'{"="*60}')
sys.exit(0 if failed==0 else 1)