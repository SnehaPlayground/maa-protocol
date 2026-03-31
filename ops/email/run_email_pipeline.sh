#!/bin/bash

cd /root/.openclaw/workspace || exit 1

if [ -f /root/.config/sneha/env.sh ]; then
  source /root/.config/sneha/env.sh
fi

python3 /root/.openclaw/workspace/ops/email/email_pipeline.py
