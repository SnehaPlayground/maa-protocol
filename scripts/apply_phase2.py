#!/usr/bin/env python3
"""Apply Phase 2 tenant isolation: CLI wiring + audit trail + rate limit enforcement."""
import re

with open('/root/.openclaw/workspace/ops/multi-agent-orchestrator/task_orchestrator.py') as f:
    content = f.read()

changes = []

if 'from tenant_gate import' not in content:
    old = 'from tenant_paths import TenantPathResolver\n'
    new = 'from tenant_paths import TenantPathResolver\nfrom tenant_gate import submit_task_gate, task_accepted, task_rejected, RateLimitExceeded\n'
    content = content.replace(old, new, 1)
    changes.append('Edit 1: tenant_gate import — OK')
else:
    changes.append('Edit 1: tenant_gate import — already present')

old_submit_parser = '''    submit_p = subparsers.add_parser("submit", help="Submit a new task")
    submit_p.add_argument("task_type", help=f"Task type: {list(TASK_TYPES.keys())}")
    submit_p.add_argument("task_prompt", help="Task description/prompt")
    submit_p.add_argument("--output-dir", help="Override output directory")
    submit_p.add_argument("--run", action="store_true", help="Run the task chain immediately")
    submit_p.add_argument("--validator-prompt", help="Additional validation criteria")'''

new_submit_parser = '''    submit_p = subparsers.add_parser("submit", help="Submit a new task")
    submit_p.add_argument("task_type", help=f"Task type: {list(TASK_TYPES.keys())}")
    submit_p.add_argument("task_prompt", help="Task description/prompt")
    submit_p.add_argument("--output-dir", help="Override output directory")
    submit_p.add_argument("--run", action="store_true", help="Run the task chain immediately")
    submit_p.add_argument("--validator-prompt", help="Additional validation criteria")
    submit_p.add_argument("--operator", default=None, help="Operator ID (required for non-default tenancy)")
    submit_p.add_argument("--client", default=None, help="Client ID (required for client-level tenancy)")
    submit_p.add_argument("--tenant-json", default=None,
                          help="Full tenant context as JSON")'''

if old_submit_parser in content:
    content = content.replace(old_submit_parser, new_submit_parser, 1)
    changes.append('Edit 2: CLI parser with tenant args — OK')
else:
    changes.append('Edit 2: CLI parser — MISS')

old_submit_handler = '''    if args.command == "submit":
        task_id = submit_task(
            args.task_type,
            args.task_prompt,
            args.output_dir,
            None,
            args.validator_prompt,
        )
        print(f"Task ID: {task_id}")
        if args.run:
            result = run_task_chain(task_id)
            print(f"Final status: {result['status']}")
            if result.get("mother_validation"):
                print(f"Validation: {json.dumps(result['mother_validation'], indent=2)}")'''

new_submit_handler = '''    if args.command == "submit":
        raw_context = None
        if args.tenant_json:
            try:
                raw_context = json.loads(args.tenant_json)
            except json.JSONDecodeError as e:
                print(f"ERROR: --tenant-json is not valid JSON: {e}")
                sys.exit(1)
        elif args.operator:
            raw_context = {
                "operator_id": args.operator,
                "client_id": args.client or args.operator,
            }
        try:
            tenant = submit_task_gate(args.task_prompt, args.task_type, raw_context)
        except RateLimitExceeded as e:
            print(f"RATE LIMIT EXCEEDED: {e.operator_id}/{e.client_id} - max {e.limit} tasks per {e.window_s}s")
            sys.exit(1)
        except ValueError as e:
            print(f"ERROR: {e}")
            sys.exit(1)
        task_id = submit_task(
            args.task_type,
            args.task_prompt,
            args.output_dir,
            None,
            args.validator_prompt,
            tenant_context=raw_context,
        )
        task_accepted(tenant, task_id, args.task_type)
        print(f"Task ID: {task_id} [{tenant}]")
        if args.run:
            result = run_task_chain(task_id)
            print(f"Final status: {result['status']}")
            if result.get("mother_validation"):
                print(f"Validation: {json.dumps(result['mother_validation'], indent=2)}")'''

if old_submit_handler in content:
    content = content.replace(old_submit_handler, new_submit_handler, 1)
    changes.append('Edit 3: CLI tenant_gate wiring — OK')
else:
    changes.append('Edit 3: CLI tenant wiring — MISS')

with open('/root/.openclaw/workspace/ops/multi-agent-orchestrator/task_orchestrator.py', 'w') as f:
    f.write(content)

import ast
try:
    ast.parse(content)
    changes.append('Syntax: PASS')
except SyntaxError as e:
    changes.append(f'Syntax: FAIL - {e}')

for c in changes:
    print(c)