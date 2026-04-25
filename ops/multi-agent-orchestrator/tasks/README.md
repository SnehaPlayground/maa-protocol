# Task State

This directory stores global Mother Agent task state.

Every non-trivial task may be tracked here regardless of source channel.
This is not WhatsApp-specific.

Naming convention:
- `{task_id}.json` -> task state

Task state is owned by Mother Agent.
Worker output alone does not mark completion.
