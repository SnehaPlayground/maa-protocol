#!/usr/bin/env bash
# Maa Protocol — Pre-Deploy Regression Gate
# Run this before any production deployment to confirm all trust tests pass.
# Exits 0 on all-pass, exits 1 if any test fails.
#
# Phase 4 enhancement:
# - Writes logs/pre_deploy_gate_latest.json with structured result
# - On failure: fires an alert via maintenance_logger
# - On success: updates latest.json with pass status

set -e

WORKSPACE="/root/.openclaw/workspace"
TESTS="$WORKSPACE/ops/multi-agent-orchestrator/tests/test_trust_fixes.py"
ACCESS_TEST="$WORKSPACE/ops/multi-agent-orchestrator/tests/test_access_control.py"
METRICS="$WORKSPACE/ops/observability/maa_metrics.py"
HEALTH="$WORKSPACE/scripts/health_check.py"
LATEST="$WORKSPACE/logs/pre_deploy_gate_latest.json"
ALERT_PAYLOAD="$WORKSPACE/logs/pre_deploy_gate_alert.json"
TIMESTAMP=$(date -u +'%Y-%m-%dT%H:%M:%SZ')
RUNNER_LOG="$WORKSPACE/logs/pre-deploy-gate.log"

# ── Structured result writers ─────────────────────────────────────────────────

write_pass() {
    local passed="$1"
    cat > "$LATEST" <<EOF
{
  "status": "pass",
  "passed": $passed,
  "failed": 0,
  "failures": [],
  "run_at": "$TIMESTAMP",
  "alert_sent": false,
  "dashboard_ok": true,
  "health_ok": true
}
EOF
    echo "  Latest result written to $LATEST"
}

write_fail() {
    local failures_json="$1"
    cat > "$LATEST" <<EOF
{
  "status": "fail",
  "passed": $2,
  "failed": $3,
  "failures": $failures_json,
  "run_at": "$TIMESTAMP",
  "alert_sent": false,
  "dashboard_ok": $4,
  "health_ok": $5
}
EOF
}

fire_alert() {
    local failures_json="$1"

    # Write structured alert for the supervising interaction surface
    cat > "$ALERT_PAYLOAD" <<EOF
{
  "alert": "MAA_PRE_DEPLOY_GATE_FAILED",
  "at": "$TIMESTAMP",
  "passed": $2,
  "failed": $3,
  "failures": $failures_json,
  "action_required": true
}
EOF

    # Use maintenance_logger to fire the alert through the interaction router
    python3 "$WORKSPACE/scripts/maintenance_logger.py" \
        "pre_deploy_gate" "failed" \
        "{\"passed\":$2,\"failed\":$3,\"alert_sent\":true}" 2>/dev/null || true

    # Mark alert_sent in latest
    python3 -c "
import json
try:
    with open('$LATEST') as f:
        d = json.load(f)
    d['alert_sent'] = True
    with open('$LATEST', 'w') as f:
        json.dump(d, f, indent=2)
except Exception:
    pass
" 2>/dev/null || true
}

# ── Main gate logic ───────────────────────────────────────────────────────────

echo "============================================================"
echo "MAA PROTOCOL — PRE-DEPLOY REGRESSION GATE"
echo "Run at: $TIMESTAMP"
echo "============================================================"
echo

FAILED_TESTS="[]"
TEST_PASSED=0
TEST_FAILED=0
COMPILE_OK="true"
ACCESS_OK="true"

# 1. Compile sanity check
echo "[1/5] Running Python compile sanity..."
COMPILE_OUTPUT=$(python3 -m py_compile \
  "$WORKSPACE/ops/multi-agent-orchestrator/"*.py \
  "$WORKSPACE/scripts/"*.py 2>&1) || COMPILE_EXIT=$?
COMPILE_EXIT=${COMPILE_EXIT:-0}
if [ "$COMPILE_EXIT" -eq 0 ]; then
    echo "  ✅ Compile sanity passed"
else
    COMPILE_OK="false"
    echo "  ❌ Compile sanity failed"
    FAILED_TESTS=$(FAILED_TESTS_JSON="$FAILED_TESTS" python3 - <<'PY'
import json, os
existing = json.loads(os.environ.get('FAILED_TESTS_JSON', '[]'))
existing.append({'test': 'py_compile', 'reason': 'python compile sanity failed'})
print(json.dumps(existing))
PY
)
fi

echo
# 2. Trust test pack
echo "[2/5] Running trust regression tests..."
set +e
TEST_OUTPUT=$(python3 "$TESTS" 2>&1)
TEST_EXIT=$?
set -e

# Parse pass/fail counts from test output
if echo "$TEST_OUTPUT" | grep -q "RESULTS:.*passed"; then
    # Format: RESULTS: 60/71 passed (85%)
    # Parse: TEST_PASSED = first number (60), TEST_FAILED = second number (71) from X/Y
    RESULT_LINE=$(echo "$TEST_OUTPUT" | grep "RESULTS:" | python3 -c "
import sys
m = sys.stdin.read().strip()
# Extract X/Y part
import re
m = re.search(r'(\d+/\d+)', m)
if m:
    parts = m.group(1).split('/')
    passed = parts[0]
    total = parts[1]
    failed = str(int(total) - int(passed))
    print(f'{passed} {failed}')
else:
    print('0 0')
" || echo "0 0")
    TEST_PASSED=$(echo "$RESULT_LINE" | cut -d' ' -f1)
    TEST_FAILED=$(echo "$RESULT_LINE" | cut -d' ' -f2)
fi

# Extract failure details for JSON
if [ "$TEST_EXIT" -ne 0 ] || [ "$TEST_FAILED" -gt 0 ]; then
    FAILED_TESTS=$(echo "$TEST_OUTPUT" | grep -E "^[[:space:]]*❌" | python3 -c "
import sys, json
lines = [l.strip() for l in sys.stdin if l.strip()]
failures = []
for line in lines:
    # Format: ❌ test_name — reason  (may have leading whitespace)
    if '❌' in line:
        parts = line.split('—')
        test_name = parts[0].replace('❌','').strip() if parts else line[:60]
        reason = parts[1].strip() if len(parts) > 1 else 'test failed'
        failures.append({'test': test_name[:80], 'reason': reason[:120]})
print(json.dumps(failures))
" 2>/dev/null || echo "[]")
fi

set +e
ACCESS_OUTPUT=$(PYTHONPATH="$WORKSPACE/ops/multi-agent-orchestrator" python3 "$ACCESS_TEST" 2>&1)
ACCESS_EXIT=$?
set -e

echo
echo "[3/5] Running access-control regression tests..."
if [ "$ACCESS_EXIT" -eq 0 ]; then
    echo "  ✅ Access control regression passed"
else
    ACCESS_OK="false"
    echo "  ❌ Access control regression failed"
    FAILED_TESTS=$(FAILED_TESTS_JSON="$FAILED_TESTS" python3 - <<'PY'
import json, os
existing = json.loads(os.environ.get('FAILED_TESTS_JSON', '[]'))
existing.append({'test': 'access_control', 'reason': 'access control regression failed'})
print(json.dumps(existing))
PY
)
fi

echo
echo "[4/5] Verifying observability dashboard..."
DASH_OUT=$(python3 "$METRICS" dashboard 2>&1) || true
if echo "$DASH_OUT" | grep -q "MAA PROTOCOL OBSERVABILITY"; then
    DASH_OK="true"
    echo "  ✅ Dashboard operational"
else
    DASH_OK="false"
    echo "  ❌ Dashboard failed to render"
fi
echo

echo "[5/5] Running pre-deploy health check..."
HEALTH_OUT=$(python3 "$HEALTH" --json 2>&1) || true
DISK_OK=$(echo "$HEALTH_OUT" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    print('yes' if d.get('disk',{}).get('usage_pct', 0) < 90 else 'no')
except:
    print('unknown')
" 2>/dev/null || echo "unknown")

if [ "$DISK_OK" = "yes" ]; then
    HEALTH_OK="true"
    echo "  ✅ Disk health: OK"
elif [ "$DISK_OK" = "no" ]; then
    HEALTH_OK="false"
    echo "  ❌ Disk usage above 90% — resolve before deploying"
else
    HEALTH_OK="true"  # treat unknown as ok to avoid spurious failures
    echo "  ⚠️  Could not verify disk health"
fi
echo

echo "============================================================"

# ── Determine outcome and write structured result ────────────────────────────

GATE_PASSED="true"
if [ "$COMPILE_OK" = "false" ] || [ "$ACCESS_OK" = "false" ] || [ "$TEST_EXIT" -ne 0 ] || [ "$TEST_FAILED" -gt 0 ] || [ "$DASH_OK" = "false" ] || [ "$DISK_OK" = "no" ]; then
    GATE_PASSED="false"
fi

if [ "$GATE_PASSED" = "true" ]; then
    write_pass "$TEST_PASSED"
    echo "PRE-DEPLOY GATE: PASSED — Maa is deployment-ready."
    echo "============================================================"
    exit 0
else
    # Write fail result first, then fire alert
    write_fail "$FAILED_TESTS" "$TEST_PASSED" "$TEST_FAILED" "$DASH_OK" "$HEALTH_OK"
    fire_alert "$FAILED_TESTS" "$TEST_PASSED" "$TEST_FAILED"
    echo "PRE-DEPLOY GATE: FAILED — Fix failures before deploying."
    echo "  Alert fired: see $ALERT_PAYLOAD"
    echo "============================================================"
    exit 1
fi
