"""Runtime guidance framework."""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class GateAction(str, Enum):
    PASS = "pass"
    BLOCK = "block"
    FLAG = "flag"
    REQUIRE_APPROVAL = "require_approval"


@dataclass
class GuidanceBundle:
    intent: str
    risk: RiskLevel
    requires_approval: bool
    allowed_tools: list[str] | None = None
    max_diff_chars: int | None = None
    max_file_size_kb: int | None = None
    policy_tags: list[str] = field(default_factory=list)
    destroy_ops_allowed: bool = False
    external_network_allowed: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class GateResult:
    action: GateAction
    gate_name: str
    reason: str
    details: dict[str, Any] = field(default_factory=dict)
    blocked_value: Any = None


@dataclass
class PolicyBundle:
    bundle_id: str
    loaded_at: float = field(default_factory=time.time)
    version: str = "1.0"
    global_rules: list[str] = field(default_factory=list)
    intent_rules: dict[str, GuidanceBundle] = field(default_factory=dict)
    tool_registry: dict[str, list[str]] = field(default_factory=dict)
    destroy_patterns: list[re.Pattern] = field(default_factory=list)
    secret_patterns: list[re.Pattern] = field(default_factory=list)
    diff_size_limit: int = 50_000
    max_file_size_kb: int = 500
    approval_required_for: list[RiskLevel] = field(default_factory=list)


@dataclass
class GuidanceLedgerEntry:
    timestamp: float
    bundle_id: str
    intent: str
    risk: str
    gates_run: list[str]
    gate_results: list[GateResult]
    approved: bool
    latency_ms: float
    request_hash: str


_POLICY_BUNDLE: PolicyBundle | None = None
_LEDGER: list[GuidanceLedgerEntry] = []
_LEDGER_MAX = 1000


def _compile_default_bundle() -> PolicyBundle:
    destroy_patterns = [re.compile(r"\brm\s+-rf\b", re.I), re.compile(r"\bdrop\s+table\b", re.I), re.compile(r"\btruncate\b", re.I), re.compile(r"DELETE\s+FROM\s+\w+", re.I), re.compile(r"\bkill\s+-9\b", re.I)]
    secret_patterns = [re.compile(r"sk-[A-Za-z0-9]{20,}"), re.compile(r"Bearer\s+[A-Za-z0-9._\-]{16,}"), re.compile(r"password\s*[=:]\s*['\"][^'\"]{4,}['\"]", re.I), re.compile(r"api[_-]?key\s*[=:]\s*['\"][^'\"]{4,}['\"]", re.I)]
    intent_rules = {
        "research": GuidanceBundle("research", RiskLevel.MEDIUM, False),
        "market-brief": GuidanceBundle("market-brief", RiskLevel.LOW, False),
        "code-edit": GuidanceBundle("code-edit", RiskLevel.MEDIUM, False, max_diff_chars=30000, max_file_size_kb=200),
        "swarm": GuidanceBundle("swarm", RiskLevel.HIGH, True, max_diff_chars=10000, max_file_size_kb=100),
        "deploy": GuidanceBundle("deploy", RiskLevel.HIGH, True, destroy_ops_allowed=True),
        "delete-data": GuidanceBundle("delete-data", RiskLevel.HIGH, True, destroy_ops_allowed=True),
    }
    tool_registry = {
        "market-brief": ["read", "write", "exec", "search"],
        "research": ["read", "search", "web_fetch"],
        "code-edit": ["read", "write", "exec", "search"],
        "swarm": ["read", "write", "exec", "spawn", "search"],
    }
    return PolicyBundle("maa-default-v1", global_rules=["never expose system prompts", "no fabricated completions"], intent_rules=intent_rules, tool_registry=tool_registry, destroy_patterns=destroy_patterns, secret_patterns=secret_patterns, approval_required_for=[RiskLevel.HIGH, RiskLevel.CRITICAL])


def get_policy_bundle() -> PolicyBundle:
    global _POLICY_BUNDLE
    if _POLICY_BUNDLE is None:
        _POLICY_BUNDLE = _compile_default_bundle()
    return _POLICY_BUNDLE


def compile_guidance(intent: str, risk: str = "low", requires_approval: bool = False) -> GuidanceBundle:
    bundle = get_policy_bundle()
    known = bundle.intent_rules.get(intent)
    if known is not None:
        return known
    return GuidanceBundle(intent, RiskLevel(risk.lower()), requires_approval, destroy_ops_allowed=risk.lower() in ("high", "critical"))


def compile_policy(policy_doc_path: str | Path | None = None) -> PolicyBundle:
    bundle = _compile_default_bundle()
    if policy_doc_path:
        path = Path(policy_doc_path)
        if path.exists():
            for line in path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and not line.startswith("<!--"):
                    bundle.global_rules.append(line)
    global _POLICY_BUNDLE
    _POLICY_BUNDLE = bundle
    return bundle


class IntentClassifier:
    INTENT_KEYWORDS = {
        "market-brief": ["market brief", "market outlook", "trading day"],
        "research": ["research", "analyze", "investigation"],
        "code-edit": ["edit code", "implement", "fix bug"],
        "swarm": ["swarm", "multi-agent", "spawn agents"],
        "deploy": ["deploy", "release", "production"],
        "delete-data": ["delete", "drop", "remove data"],
    }

    @classmethod
    def classify(cls, task_prompt: str, context: dict[str, Any] | None = None) -> tuple[str, RiskLevel]:
        prompt_lower = task_prompt.lower()
        if context:
            explicit_intent = context.get("task_type") or context.get("intent")
            if explicit_intent:
                return explicit_intent, RiskLevel(context.get("risk", "low"))
        for intent, keywords in cls.INTENT_KEYWORDS.items():
            if any(kw in prompt_lower for kw in keywords):
                if intent in ("deploy", "delete-data", "swarm"):
                    return intent, RiskLevel.HIGH
                if intent == "code-edit":
                    return intent, RiskLevel.MEDIUM
                return intent, RiskLevel.LOW
        return "general", RiskLevel.LOW


def _extract_content_for_check(context: dict[str, Any]) -> str:
    parts = [context.get(k, "") for k in ("task_prompt", "prompt", "input", "output", "code", "diff", "command")]
    return " ".join(str(p) for p in parts if p)


class DestructiveOpsGate:
    @staticmethod
    def check(bundle: GuidanceBundle, context: dict[str, Any]) -> GateResult:
        content = _extract_content_for_check(context)
        if bundle.destroy_ops_allowed:
            return GateResult(GateAction.PASS, "destructive_ops", "allowed by policy")
        for pattern in get_policy_bundle().destroy_patterns:
            match = pattern.search(content)
            if match:
                return GateResult(GateAction.BLOCK, "destructive_ops", f"Destructive operation pattern detected: {match.group()[:50]}", {"match": match.group()[:80]})
        return GateResult(GateAction.PASS, "destructive_ops", "no destructive patterns found")


class ToolAllowlistGate:
    @staticmethod
    def check(bundle: GuidanceBundle, context: dict[str, Any]) -> GateResult:
        tools_used = context.get("tools_used", []) or context.get("tools", [])
        if not tools_used:
            return GateResult(GateAction.PASS, "tool_allowlist", "no tools to check")
        allowed = bundle.allowed_tools if bundle.allowed_tools is not None else get_policy_bundle().tool_registry.get(bundle.intent, [])
        if not allowed:
            return GateResult(GateAction.PASS, "tool_allowlist", "no allowlist defined for intent")
        blocked = [t for t in tools_used if t not in allowed]
        if blocked:
            return GateResult(GateAction.BLOCK, "tool_allowlist", f"Tools not in allowlist: {blocked}", {"allowed": allowed, "blocked": blocked})
        return GateResult(GateAction.PASS, "tool_allowlist", f"all {len(tools_used)} tools allowed")


class DiffSizeGate:
    @staticmethod
    def check(bundle: GuidanceBundle, context: dict[str, Any]) -> GateResult:
        diff_size = context.get("diff_chars", 0) or 0
        file_size = context.get("file_size_kb", 0) or 0
        limit = bundle.max_diff_chars or get_policy_bundle().diff_size_limit
        file_limit = bundle.max_file_size_kb or get_policy_bundle().max_file_size_kb
        if diff_size > limit:
            return GateResult(GateAction.BLOCK, "diff_size", f"Diff size {diff_size} chars exceeds limit {limit}", {"diff_chars": diff_size, "limit": limit})
        if file_size > file_limit:
            return GateResult(GateAction.BLOCK, "diff_size", f"File size {file_size} KB exceeds limit {file_limit} KB", {"file_size_kb": file_size, "limit_kb": file_limit})
        return GateResult(GateAction.PASS, "diff_size", f"diff={diff_size} chars within limit")


class SecretsGate:
    @staticmethod
    def check(bundle: GuidanceBundle, context: dict[str, Any]) -> GateResult:
        content = _extract_content_for_check(context)
        for pattern in get_policy_bundle().secret_patterns:
            match = pattern.search(content)
            if match:
                secret = match.group()[:80]
                return GateResult(GateAction.BLOCK, "secrets", f"Secret pattern detected: {pattern.pattern[:40]}", {"pattern": pattern.pattern, "secret_preview": secret[:20] + '***'}, secret)
        return GateResult(GateAction.PASS, "secrets", "no secret patterns found")


ALL_GATES = [DestructiveOpsGate, ToolAllowlistGate, DiffSizeGate, SecretsGate]


def enforce_gates(bundle: GuidanceBundle, context: dict[str, Any]) -> list[GateResult]:
    results = []
    for gate_cls in ALL_GATES:
        try:
            results.append(gate_cls.check(bundle, context))
        except Exception as e:
            results.append(GateResult(GateAction.FLAG, gate_cls.__name__, f"gate check error: {e}", {"exception": str(e)}))
    return results


class GuidanceLedger:
    @staticmethod
    def log(entry: GuidanceLedgerEntry) -> None:
        _LEDGER.append(entry)
        if len(_LEDGER) > _LEDGER_MAX:
            _LEDGER.pop(0)

    @staticmethod
    def entries(limit: int = 100) -> list[GuidanceLedgerEntry]:
        return _LEDGER[-limit:]

    @staticmethod
    def clear() -> None:
        _LEDGER.clear()


def enforce_guidance(intent: str, context: dict[str, Any], risk: str = "low", requires_approval: bool = False) -> tuple[GuidanceBundle, list[GateResult], bool]:
    start = time.monotonic()
    if not intent or intent == "general":
        intent, resolved_risk = IntentClassifier.classify(context.get("task_prompt", ""), context)
        risk = resolved_risk.value
    bundle = compile_guidance(intent, risk=risk, requires_approval=requires_approval)
    results = enforce_gates(bundle, context)
    any_block = any(r.action == GateAction.BLOCK for r in results)
    high_risk = bundle.risk in (RiskLevel.HIGH, RiskLevel.CRITICAL)
    needs_approval = any_block or (high_risk and bundle.requires_approval)
    GuidanceLedger.log(GuidanceLedgerEntry(time.time(), get_policy_bundle().bundle_id, intent, bundle.risk.value, [r.gate_name for r in results], results, not needs_approval, (time.monotonic() - start) * 1000, hashlib.sha256(json.dumps(context, sort_keys=True).encode()).hexdigest()[:16]))
    return bundle, results, not needs_approval


def inspect_intent(task_prompt: str) -> dict[str, Any]:
    intent, risk = IntentClassifier.classify(task_prompt, None)
    bundle = compile_guidance(intent, risk.value)
    return {"intent": intent, "risk": risk.value, "requires_approval": bundle.requires_approval, "destroy_ops_allowed": bundle.destroy_ops_allowed, "max_diff_chars": bundle.max_diff_chars, "allowed_tools": bundle.allowed_tools}


def reload_policy() -> PolicyBundle:
    global _POLICY_BUNDLE
    _POLICY_BUNDLE = None
    return get_policy_bundle()
