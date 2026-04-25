#!/bin/bash
echo "=== Session Prune Run: $(date) ===" >> /root/.openclaw/workspace/logs/session-prune.log
python3 /root/.openclaw/workspace/scripts/prune_old_sessions.py >> /root/.openclaw/workspace/logs/session-prune.log 2>&1
echo "Done at $(date)" >> /root/.openclaw/workspace/logs/session-prune.log