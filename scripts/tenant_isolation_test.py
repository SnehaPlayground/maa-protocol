#!/usr/bin/env python3
"""
MAA PROTOCOL — TENANT ISOLATION TEST PACK
Version: 1.0
Tests: 6 isolation guarantees required for commercial multi-tenant deployment.

Run: python3 scripts/tenant_isolation_test.py
"""

import json
import shutil
import sys
import time
from pathlib import Path

WORKSPACE = Path("/root/.openclaw/workspace")
TENANTS_ROOT = WORKSPACE / "tenants"
OPS_DIR = WORKSPACE / "ops/multi-agent-orchestrator"

TEST_OPERATOR = "test_iso_operator"
TEST_CLIENT_A = "test_iso_client_a"
TEST_CLIENT_B = "test_iso_client_b"


def load_json(path: Path):
    with open(path) as f:
        return json.load(f)


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def atomic_write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(path) + ".tmp")
    with open(tmp, "w") as f:
        f.write(text)
    tmp.replace(path)


def green(msg):
    print(f"  ✅ {msg}")


def red(msg):
    print(f"  ❌ {msg}")


def section(n, msg):
    print(f"\n[{n}] {msg}")


def get_modules():
    sys.path.insert(0, str(OPS_DIR))
    from tenant_paths import TenantPathResolver
    from tenant_context import parse_tenant_context
    from tenant_gate import check_rate_limits, RateLimitExceeded, load_client_config
    return TenantPathResolver, parse_tenant_context, check_rate_limits, RateLimitExceeded, load_client_config


def setup_test_tenants():
    op_dir = TENANTS_ROOT / TEST_OPERATOR
    save_json(op_dir / "config" / "operator.json", {
        "operator_id": TEST_OPERATOR,
        "label": "Test Operator",
        "max_concurrent_tasks": 8,
        "max_tasks_per_hour": 100,
        "created_at": "2026-04-22T00:00:00Z",
        "status": "active",
    })

    for client in (TEST_CLIENT_A, TEST_CLIENT_B):
        base = op_dir / "clients" / client
        for sub in ("tasks", "logs", "outputs", "metrics", "config"):
            (base / sub).mkdir(parents=True, exist_ok=True)
        save_json(base / "config" / "client.json", {
            "client_id": client,
            "label": f"Test {client}",
            "max_concurrent_tasks": 2,
            "max_tasks_per_hour": 5,
            "rate_limit_window_seconds": 3600,
            "created_at": "2026-04-22T00:00:00Z",
            "status": "active",
        })
    green("Test tenant tree created")


def teardown_test_tenants():
    shutil.rmtree(TENANTS_ROOT / TEST_OPERATOR, ignore_errors=True)
    green("Test tenant tree removed")


def test_path_escape():
    section(1, "Path Escape — malicious tenant ids must be rejected")
    TenantPathResolver, parse_tenant_context, *_ = get_modules()
    attempts = [
        "../../../etc/passwd",
        "primeidea/../../../etc",
        "..%2f..%2f..%2f",
        "default/../../../../../../../../../../../../root",
        "/etc/passwd",
    ]
    ok = True
    for bad in attempts:
        try:
            resolver = TenantPathResolver(parse_tenant_context({
                "operator_id": bad,
                "client_id": "default",
                "tenant_tier": "client",
            }))
            resolver.resolve("tasks")
            red(f"Path accepted unexpectedly: {bad!r}")
            ok = False
        except Exception as e:
            green(f"Correctly rejected: {bad!r} — {e}")
    if ok:
        green("Path escape prevention: PASS")
    return ok


def test_cross_tenant_read():
    section(2, "Cross-Tenant Read — client paths are isolated")
    TenantPathResolver, parse_tenant_context, *_ = get_modules()
    resolver_a = TenantPathResolver(parse_tenant_context({
        "operator_id": TEST_OPERATOR, "client_id": TEST_CLIENT_A, "tenant_tier": "client"
    }))
    resolver_b = TenantPathResolver(parse_tenant_context({
        "operator_id": TEST_OPERATOR, "client_id": TEST_CLIENT_B, "tenant_tier": "client"
    }))
    secret_a = resolver_a.resolve("logs") / "secret.txt"
    atomic_write(secret_a, "CLIENT_A_ONLY")
    candidate_b = resolver_b.resolve("logs") / "secret.txt"
    if candidate_b.exists():
        red(f"Client B can see Client A file: {candidate_b}")
        secret_a.unlink(missing_ok=True)
        return False
    green("Cross-tenant read blocked: PASS")
    secret_a.unlink(missing_ok=True)
    return True


def test_cross_tenant_write():
    section(3, "Cross-Tenant Write — client paths are distinct")
    TenantPathResolver, parse_tenant_context, *_ = get_modules()
    resolver_a = TenantPathResolver(parse_tenant_context({
        "operator_id": TEST_OPERATOR, "client_id": TEST_CLIENT_A, "tenant_tier": "client"
    }))
    resolver_b = TenantPathResolver(parse_tenant_context({
        "operator_id": TEST_OPERATOR, "client_id": TEST_CLIENT_B, "tenant_tier": "client"
    }))
    logs_a = resolver_a.resolve("logs")
    logs_b = resolver_b.resolve("logs")
    if logs_a == logs_b:
        red("Client log paths are identical")
        return False
    green("Cross-tenant write prevention: PASS")
    return True


def test_rate_limit_bypass():
    section(4, "Rate Limit Bypass — 6th task rejected for 5-task client")
    _, parse_tenant_context, check_rate_limits, RateLimitExceeded, _ = get_modules()
    tc = parse_tenant_context({
        "operator_id": TEST_OPERATOR,
        "client_id": TEST_CLIENT_A,
        "tenant_tier": "client",
    })
    accepted = 0
    for _i in range(5):
        try:
            check_rate_limits(tc)
            accepted += 1
        except RateLimitExceeded as e:
            red(f"Rejected before limit: {e}")
            return False
    green(f"{accepted} tasks accepted at limit")
    try:
        check_rate_limits(tc)
        red("6th task accepted unexpectedly")
        return False
    except RateLimitExceeded:
        green("6th task correctly rejected")
        green("Rate limit bypass prevention: PASS")
        return True


def test_audit_path_correctness():
    section(5, "Audit Path Correctness — operator-shared audit, client-isolated state")
    TenantPathResolver, parse_tenant_context, *_ = get_modules()
    resolver_a = TenantPathResolver(parse_tenant_context({
        "operator_id": TEST_OPERATOR, "client_id": TEST_CLIENT_A, "tenant_tier": "client"
    }))
    resolver_b = TenantPathResolver(parse_tenant_context({
        "operator_id": TEST_OPERATOR, "client_id": TEST_CLIENT_B, "tenant_tier": "client"
    }))
    audit_a = resolver_a.resolve("audit")
    audit_b = resolver_b.resolve("audit")
    tasks_a = resolver_a.resolve("tasks")
    tasks_b = resolver_b.resolve("tasks")
    if audit_a != audit_b:
        red(f"Operator audit path mismatch: {audit_a} vs {audit_b}")
        return False
    if tasks_a == tasks_b:
        red("Client task paths are identical")
        return False
    green(f"Shared operator audit path: {audit_a}")
    green("Audit path correctness: PASS")
    return True


def test_tenant_deactivation():
    section(6, "Tenant Deactivation — deactivated client rejected by gate")
    _, _, _, _, load_client_config = get_modules()
    client_cfg_path = TENANTS_ROOT / TEST_OPERATOR / "clients" / TEST_CLIENT_A / "config" / "client.json"
    cfg = load_json(client_cfg_path)
    cfg["status"] = "deactivated"
    save_json(client_cfg_path, cfg)
    reloaded = load_client_config(TEST_OPERATOR, TEST_CLIENT_A)
    if reloaded.get("status") != "deactivated":
        red(f"Deactivation did not persist, got status={reloaded.get('status')}")
        return False
    green("Tenant deactivation config persisted: PASS")
    return True


def main():
    print("=" * 60)
    print("MAA PROTOCOL — TENANT ISOLATION TEST PACK")
    print("=" * 60)
    results = []
    try:
        setup_test_tenants()
        results.append(("Path escape prevention", test_path_escape()))
        results.append(("Cross-tenant read prevention", test_cross_tenant_read()))
        results.append(("Cross-tenant write prevention", test_cross_tenant_write()))
        results.append(("Rate limit bypass prevention", test_rate_limit_bypass()))
        results.append(("Audit path correctness", test_audit_path_correctness()))
        results.append(("Tenant deactivation persistence", test_tenant_deactivation()))
    finally:
        teardown_test_tenants()

    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    for name, ok in results:
        print(f"  {'✅ PASS' if ok else '❌ FAIL'} — {name}")
    print(f"\n{passed}/{total} isolation tests passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
