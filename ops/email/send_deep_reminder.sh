#!/bin/bash
# One-time email sender for Deep KYC reminder
# Scheduled for: 2026-04-08 09:15 AM

TARGET="2026-04-08 09:15:00"
EMAIL_FILE="/root/.openclaw/workspace/data/email/pending_deep_reminder.txt"
LOG="/root/.openclaw/workspace/logs/email-sent.log"
SENT_FLAG="/root/.openclaw/workspace/data/email/deep_reminder_sent.flag"

[ -f "$SENT_FLAG" ] && exit 0

sleep_until=$(date -d "$TARGET" +%s 2>/dev/null) || exit 1
now=$(date +%s)
wait_seconds=$((sleep_until - now))

if [ $wait_seconds -gt 0 ]; then
    sleep $wait_seconds
fi

if [ -f "$EMAIL_FILE" ] && [ ! -f "$SENT_FLAG" ]; then
    TO=$(grep "^To:" "$EMAIL_FILE" | sed 's/^To: //')
    SUBJECT=$(grep "^Subject:" "$EMAIL_FILE" | sed 's/^Subject: //')
    BODY_FILE=$(mktemp)
    sed '1,/^$/d' "$EMAIL_FILE" > "$BODY_FILE"

    if python3 /root/.openclaw/workspace/ops/email/send_email_via_gog.py \
        --to "$TO" \
        --subject "$SUBJECT" \
        --body-file "$BODY_FILE" \
        --account 'sneha.primeidea@gmail.com'; then
        touch "$SENT_FLAG"
        echo "$(date): Deep reminder sent at $TARGET" >> "$LOG"
    fi

    rm -f "$BODY_FILE"
fi
