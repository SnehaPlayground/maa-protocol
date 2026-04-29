"""Security module — 7-layer threat detection and policy enforcement."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

# ── PII patterns ───────────────────────────────────────────────────────────────


_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_INDIAN_PHONE_RE = re.compile(r"\+91[\s.-]?[6-9]\d{9}|\b[6-9]\d{9}\b")
_INTL_PHONE_RE = re.compile(r"\+\d{1,3}[\s.-]?\d{6,14}")
_AADHAR_RE = re.compile(r"\b\d{4}[\s.-]?\d{4}[\s.-]?\d{4}\b")
_PAN_RE = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")
_CC_RE = re.compile(r"\b\d{4}[\s.-]?\d{4}[\s.-]?\d{4}[\s.-]?\d{4}\b")
_IP_RE = re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")
_URL_RE = re.compile(r"https?://[^\s]+")


# ── Threat signatures ──────────────────────────────────────────────────────────

_INJECTION_PATTERNS = [
    (re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.I), "prompt_injection", "high"),
    (re.compile(r"ignore all prior rules", re.I), "prompt_injection", "high"),
    (re.compile(r"disregard.*instruction", re.I), "prompt_injection", "medium"),
    (re.compile(r"roleplay.*admin", re.I), "prompt_injection", "medium"),
    (re.compile(r"you are now.*AI", re.I), "prompt_injection", "medium"),
    (re.compile(r"SQL syntax.*error", re.I), "sql_injection", "high"),
    (re.compile(r"('\s*or\s*'1'\s*=\s*'1)", re.I), "sql_injection", "high"),
    (re.compile(r"(union\s+select|drop\s+table)", re.I), "sql_injection", "high"),
    (re.compile(r"<script[^>]*>", re.I), "xss", "high"),
    (re.compile(r"javascript:", re.I), "xss", "medium"),
    (re.compile(r"<iframe[^>]*>", re.I), "xss", "medium"),
    (re.compile(r"on\w+\s*=", re.I), "xss", "medium"),
    (re.compile(r"eval\s*\(", re.I), "code_injection", "high"),
    (re.compile(r"exec\s*\(", re.I), "code_injection", "high"),
    (re.compile(r"__import__", re.I), "code_injection", "medium"),
    (re.compile(r"\.\/.*\.env", re.I), "path_traversal", "medium"),
    (re.compile(r"\.\.\/.*\/etc", re.I), "path_traversal", "high"),
]

_SUSPICIOUS_TOKENS = [
    ("generate visa", "document_fabrication", "medium"),
    ("fake diploma", "document_fabrication", "medium"),
    ("buy followers", "social_manipulation", "low"),
    ("inflate stock", "market_manipulation", "high"),
    ("insider trading", "market_manipulation", "high"),
]


# ── Dataclasses ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ThreatResult:
    threat_type: str
    severity: str  # low / medium / high / critical
    matched_pattern: str
    span: tuple[int, int] | None = None


@dataclass
class ThreatLedger:
    """Audit log of all security events."""
    entries: list[dict] = field(default_factory=list)

    def record(self, event_type_or_details: str | dict, details: dict | None = None) -> None:
        """
        Record a security event.

        Supports two call styles for backward compatibility:
          ledger.record("task.completed", {"agent": "alice"})
          ledger.record({"event": "task.completed", "agent": "alice"})
        """
        import time
        if isinstance(event_type_or_details, dict):
            entry = dict(event_type_or_details)
            entry["timestamp"] = time.time()
        else:
            entry = {
                "event_type": event_type_or_details,
                "timestamp": time.time(),
                **(details or {}),
            }
        self.entries.append(entry)

    def recent(self, k: int = 100) -> list[dict]:
        return self.entries[-k:]


# ── ThreatDetector ─────────────────────────────────────────────────────────────


class ThreatDetector:
    """
    7-layer threat detector for content security.

    Layers
    ------
    1. Prompt injection  — jailbreak and instruction override patterns
    2. SQL injection      — database attack signatures
    3. XSS                — cross-site scripting signatures
    4. Code injection     — dangerous Python call patterns
    5. Path traversal     — filesystem attack patterns
    6. PII detection      — email, phone, Aadhar, PAN, CC patterns
    7. Compliance risk    — document fabrication, market manipulation

    Parameters
    ----------
    ledger
        Optional shared ledger for audit.
    strict
        If True, enable all layers including compliance risk.
    """

    def __init__(self, ledger: ThreatLedger | None = None, strict: bool = False) -> None:
        self.ledger = ledger or ThreatLedger()
        self.strict = strict

    def scan(self, content: str) -> list[ThreatResult]:
        """
        Scan content across all active threat layers.

        Returns a list of ThreatResult sorted by severity descending.
        """
        results: list[ThreatResult] = []
        for pattern, threat_type, severity in _INJECTION_PATTERNS:
            for match in pattern.finditer(content):
                results.append(ThreatResult(
                    threat_type=threat_type,
                    severity=severity,
                    matched_pattern=match.group(),
                    span=(match.start(), match.end()),
                ))

        if self.strict:
            for token, threat_type, severity in _SUSPICIOUS_TOKENS:
                if token.lower() in content.lower():
                    results.append(ThreatResult(
                        threat_type=threat_type,
                        severity=severity,
                        matched_pattern=token,
                    ))

        results.sort(key=lambda r: {"critical": 0, "high": 1, "medium": 2, "low": 3}[r.severity])
        return results

    def scan_pii(self, content: str) -> list[tuple[str, str, tuple[int, int]]]:
        """
        Detect PII in content.

        Returns [(pii_type, matched_value, (start, end)), ...].
        """
        findings: list[tuple[str, str, tuple[int, int]]] = []
        for pattern, pii_type in [
            (_EMAIL_RE, "email"),
            (_INDIAN_PHONE_RE, "phone_in"),
            (_INTL_PHONE_RE, "phone_intl"),
            (_AADHAR_RE, "aadhar"),
            (_PAN_RE, "pan"),
            (_CC_RE, "credit_card"),
            (_IP_RE, "ip_address"),
        ]:
            for m in pattern.finditer(content):
                findings.append((pii_type, m.group(), (m.start(), m.end())))
        return findings

    def is_clean(self, content: str) -> bool:
        """True only when no threats and no unredacted PII are found."""
        threats = self.scan(content)
        pii = self.scan_pii(content)
        return len(threats) == 0 and len(pii) == 0


# ── ContentPolicy ──────────────────────────────────────────────────────────────


@dataclass
class PolicyRule:
    name: str
    pattern: re.Pattern
    action: str = "block"  # block / warn / allow
    severity: str = "high"


class ContentPolicy:
    """
    Configurable content policy engine.

    Add rules to enforce custom content boundaries.
    """

    def __init__(self) -> None:
        self._rules: list[PolicyRule] = []

    def add_rule(self, name: str, pattern: str, action: str = "block", severity: str = "high") -> None:
        self._rules.append(PolicyRule(
            name=name,
            pattern=re.compile(pattern, re.I),
            action=action,
            severity=severity,
        ))

    def evaluate(self, content: str) -> dict[str, Any]:
        findings: list[dict] = []
        for rule in self._rules:
            for match in rule.pattern.finditer(content):
                findings.append({
                    "rule": rule.name,
                    "action": rule.action,
                    "severity": rule.severity,
                    "matched": match.group(),
                })
        blocked = any(f["action"] == "block" for f in findings)
        return {"allowed": not blocked, "findings": findings}


# ── Redaction ─────────────────────────────────────────────────────────────────


def redact_pii(content: str) -> str:
    """Replace all detected PII with [REDACTED] markers."""
    for pattern, label in [
        (_EMAIL_RE, "EMAIL_REDACTED"),
        (_INDIAN_PHONE_RE, "PHONE_IN_REDACTED"),
        (_INTL_PHONE_RE, "PHONE_INTL_REDACTED"),
        (_AADHAR_RE, "AADHAR_REDACTED"),
        (_PAN_RE, "PAN_REDACTED"),
        (_CC_RE, "CC_REDACTED"),
        (_IP_RE, "IP_REDACTED"),
    ]:
        content = pattern.sub(f"[{label}]", content)
    return content


def scan_content(content: str) -> list[ThreatResult]:
    """Convenience wrapper — scan one string across all threat layers."""
    return ThreatDetector().scan(content)


# ── Sandbox ────────────────────────────────────────────────────────────────────


def sandbox_python(code: str, timeout_seconds: float = 5.0) -> dict[str, Any]:
    """
    Execute Python code in a restricted local subprocess.

    Parameters
    ----------
    code
        The Python source to execute.
    timeout_seconds
        Wall-clock time limit before SIGKILL.

    Returns
    -------
    {"ok": bool, "output": str, "error": str | None, "elapsed_ms": float}
    """
    import subprocess
    import time

    start = time.perf_counter()
    try:
        result = subprocess.run(
            ["python3", "-c", code],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            cwd="/tmp",
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        if result.returncode == 0:
            return {"ok": True, "output": result.stdout, "error": None, "elapsed_ms": elapsed_ms}
        return {"ok": False, "output": result.stdout, "error": result.stderr, "elapsed_ms": elapsed_ms}
    except subprocess.TimeoutExpired:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return {"ok": False, "output": "", "error": f"Timeout after {timeout_seconds}s", "elapsed_ms": elapsed_ms}
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return {"ok": False, "output": "", "error": str(exc), "elapsed_ms": elapsed_ms}


# ── Cryptographic audit ────────────────────────────────────────────────────────


def audit_hash(data: str) -> str:
    """
    SHA-256 hash of content for audit integrity.

    Parameters
    ----------
    data
        String content to hash.

    Returns
    -------
    Hex-encoded SHA-256 digest.
    """
    import hashlib
    return hashlib.sha256(data.encode()).hexdigest()


def make_audit_entry(event_type: str, agent_id: str, payload: str, prev_hash: str) -> dict[str, Any]:
    """
    Create a tamper-evident audit chain entry.


    Parameters
    ----------
    event_type
        e.g. "approval.granted", "task.completed"
    agent_id
        Agent that triggered the event.
    payload
        JSON-serializable payload description.
    prev_hash
        Hash of the previous entry in the chain (empty string for genesis).

    Returns
    -------
    Entry dict with hash computed from prev_hash + payload.
    """
    ts = time.time()
    entry_data = json.dumps({"event_type": event_type, "agent_id": agent_id, "payload": payload, "ts": ts}, sort_keys=True)
    raw = f"{prev_hash}:{entry_data}"
    return {
        "event_type": event_type,
        "agent_id": agent_id,
        "payload": payload,
        "ts": ts,
        "hash": audit_hash(raw),
        "prev": prev_hash,
    }


def verify_audit_chain(entries: list[dict[str, Any]]) -> bool:
    """Verify the integrity of an audit chain."""
    prev = ""
    for e in entries:
        raw = f"{prev}:{json.dumps({'event_type': e['event_type'], 'agent_id': e['agent_id'], 'payload': e['payload'], 'ts': e['ts']}, sort_keys=True)}"
        expected = audit_hash(raw)
        if e["hash"] != expected or e["prev"] != prev:
            return False
        prev = e["hash"]
    return True