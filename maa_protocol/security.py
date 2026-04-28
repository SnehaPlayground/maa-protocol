"""
MAA Protocol — Security Threat Engine
======================================
Detects and blocks security threats in MAA operations:
- PII / sensitive data detection in text and file content
- Injection attacks (prompt injection, command injection, SQL injection)
- Jailbreak attempt detection
- Path traversal and dangerous path access
- Credential and secrets detection

Components:
- ThreatDetector — scan text/content for threat signatures
- PIIAnalyzer — detect personal/sensitive data patterns
- InjectionDetector — detect prompt/command/SQL injection attempts
- ThreatScanner — orchestrates all scanners, produces structured findings
- ThreatLevel enum + ThreatFinding dataclass for structured output
- redact_pii() — mask detected PII in text for safe logging
- scan_content() — top-level scan API
- ThreatPolicy enum — decide action per threat level
- apply_policy() — enforce threat policy (BLOCK/ESCALATE/LOG/WARN)
- ThreatLedger — record all threats for audit trail
"""

from __future__ import annotations

import enum
import re
import time
from dataclasses import dataclass, field
from typing import Any
# ── Threat level and policy ────────────────────────────────────────────────────

class ThreatLevel(enum.Enum):
    CLEAR = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


class ThreatPolicy(enum.Enum):
    LOG = "log"          # log only, continue execution
    WARN = "warn"        # log + warn, continue
    ESCALATE = "escalate" # log + alert, continue (human review)
    BLOCK = "block"       # stop execution, log


# ── PII patterns ───────────────────────────────────────────────────────────────

# Indian phone numbers: +91, 0-prefix, 10-digit
_PHONE_PATTERNS = [
    r'\+91[\s\-]?[6-9]\d{9}',           # +91 9876543210
    r'(?<!\w)0?[6-9]\d{9}',              # 9876543210 or 09876543210
    r'\b[6-9]\d{2}[\s\-]?\d{3}[\s\-]?\d{4}\b',  # 987 654 3210
]

# Indian PAN: AAAAA0000A (5 letters, 4 digits, 1 letter)
_PAN_PATTERN = r'\b[A-Z]{5}[0-9]{4}[A-Z]\b'

# Indian Aadhaar: 12 digits (with optional spaces)
_AADHAAR_PATTERNS = [
    r'\b\d{4}[\s]?\d{4}[\s]?\d{4}\b',   # 1234 5678 9012
    r'\b\d{12}\b',
]

# Indian bank account: 9-18 digits
_BANK_ACCOUNT_PATTERN = r'\b\d{9,18}\b'

# Indian GSTIN: 15 chars, format 12AAAAA0000A1Z5
_GSTIN_PATTERN = r'\b\d{2}[A-Z]{5}\d{4}[A-Z]\d[Z]\d\b'

# Generic email
_EMAIL_PATTERN = r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b'

# Generic phone (international)
_PHONE_GENERIC = r'\+?\d{1,4}[\s\-]?\(?\d{1,4}\)?[\s\-]?\d{3,4}[\s\-]?\d{3,6}'

# Credit/debit card numbers (16 digits)
_CARD_PATTERN = r'\b(?:\d{4}[\s\-]?){3}\d{4}\b'

# US SSN
_SSN_PATTERN = r'\b\d{3}[\s\-]?\d{2}[\s\-]?\d{4}\b'

# Password-like patterns
_PASSWORD_LIKE = r'(?:password|passwd|pwd|secret|token|api.?key|apikey)[\s]*[=:][^\s,;]{4,}'

# AWS/Azure/GCP keys
_AWS_KEY = r'AKIA[0-9A-Z]{16}'
_AZURE_TOKEN = r'https?://[a-zA-Z0-9.\-_]+/token[s]?/[a-zA-Z0-9._\-]+'
_GCP_KEY = r'[a-zA-Z0-9_-]+@gcp-[a-zA-Z0-9.]+\.iam\.gserviceaccount\.com'

# IP addresses
_IP_PATTERN = r'\b(?:\d{1,3}\.){3}\d{1,3}\b'

# Date of birth patterns
_DOB_PATTERN = r'\b(?:DOB| birth|born|birthday)[\s:]+(?:\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}|\d{4})\b'


def _compile_patterns(patterns: list[str]) -> list[re.Pattern]:
    return [re.compile(p, re.IGNORECASE) for p in patterns]


_PII_PATTERNS = {
    'phone_india': _compile_patterns(_PHONE_PATTERNS),
    'email': _compile_patterns([_EMAIL_PATTERN]),
    'pan': _compile_patterns([_PAN_PATTERN]),
    'aadhaar': _compile_patterns(_AADHAAR_PATTERNS),
    'bank_account': _compile_patterns([_BANK_ACCOUNT_PATTERN]),
    'gstin': _compile_patterns([_GSTIN_PATTERN]),
    'credit_card': _compile_patterns([_CARD_PATTERN]),
    'ssn': _compile_patterns([_SSN_PATTERN]),
    'password_like': _compile_patterns([_PASSWORD_LIKE]),
    'aws_key': _compile_patterns([_AWS_KEY]),
    'azure_token': _compile_patterns([_AZURE_TOKEN]),
    'gcp_key': _compile_patterns([_GCP_KEY]),
    'ip_address': _compile_patterns([_IP_PATTERN]),
    'dob': _compile_patterns([_DOB_PATTERN]),
}

# ── Injection patterns ─────────────────────────────────────────────────────────

_INJECTION_PATTERNS = {
    'command_injection': [
        # Command separators in dangerous contexts
        r'[;\|&`$]\s*\w+',                # ; ls, | cat, `whoami`, $(id)
        r'\$\([^)]+\)',                    # $(command)
        r'`[^`]+`',                        # `command`
        r'\{\{[^{]*\}\}',                  # {{ something }} — template injection
        r'%0a%0d',                          # URL-encoded CRLF
        r'[\n\r][\s]*--',                   # SQL comment injection
    ],
    'sql_injection': [
        r"'\s*(OR|AND)\s+'",              # ' OR '1'='1
        r"'\s*--",                         # SQL comment
        r"'\s*(UNION|SELECT|INSERT|UPDATE|DELETE|DROP)",  # SQL keywords
        r';\s*(DROP|DELETE|TRUNCATE)',    # destructive SQL
        r'1\s*=\s*1',                     # tautology
        r'NULL\s*=\s*NULL',               # null check
        r'EXEC\s*\(',                     # EXEC/proc injection
    ],
    'prompt_injection': [
        # Jailbreak phrases
        r'\b(ignore\s+(all\s+)?previous|forget\s+(all\s+)?instructions)\b',
        r'\b(ignore\s+this|disregard\s+this|override)\b',
        r'\b(you\s+are\s+now|pretend\s+you\s+are|switch\s+to)\b',
        r'\bsudo\s+',                      # privilege escalation in context
        r'\b(pretend\s+no\s+limits|as\s+an\s+AI\s+without\s+restrictions)\b',
        r'\b(DAN|Jailbreak|you\s+are\s+a\s+model\s+with\s+no\s+filter)\b',
        r'system\s*prompt',               # prompt extraction attempt
        r'\b(extract\s+system\s+prompt|reveal\s+your\s+instructions)\b',
        # Multi-turn manipulation
        r'\b(let\'s\s+play\s+a\s+game|new\s+roleplay|imagine\s+you\s+are)\b',
    ],
    'path_traversal': [
        r'\.\.\/',                         # ../
        r'\.\.\\',                         # ..\
        r'%2e%2e',                         # URL-encoded ..
        r'\.\.[\\/]',                      # ..\/ with mixed separators
        r'(?:etc|proc|sys|root)\/',        # access to system directories
    ],
    'xss': [
        r'<script[^>]*>',                 # script tags
        r'javascript:',                    # javascript: protocol
        r'on\w+\s*=',                     # event handlers
        r'<iframe[^>]*>',                 # iframe injection
        r'<img[^>]*src\s*=',             # img src injection
    ],
}


def _scan_patterns(text: str, pattern_groups: dict[str, list[re.Pattern]]) -> list[tuple[str, str]]:
    """Scan text against pattern groups. Returns list of (group, matched_text)."""
    findings = []
    for group, patterns in pattern_groups.items():
        for pat in patterns:
            for m in pat.finditer(text):
                # Don't flag short matches (likely false positives)
                if len(m.group()) >= 3:
                    findings.append((group, m.group()))
    return findings


# ── Threat finding ─────────────────────────────────────────────────────────────

@dataclass
class ThreatFinding:
    id: str
    timestamp: float
    level: ThreatLevel
    category: str          # e.g. 'pii.phone', 'injection.prompt', 'path_traversal'
    description: str
    matched: str           # the matched text (redacted for PII)
    location: str | None   # 'input', 'content', 'file', 'command'
    policy: ThreatPolicy
    remediation: str | None


@dataclass
class ThreatReport:
    overall_level: ThreatLevel
    findings: list[ThreatFinding]
    scanned_at: float
    scan_duration_ms: float
    clear: bool


# ── ThreatDetector ─────────────────────────────────────────────────────────────

class ThreatDetector:
    """
    Scans text, content, and commands for security threats.

    Usage:
        scanner = ThreatDetector()
        report = scanner.scan("user input text here")
        if report.overall_level > ThreatLevel.LOW:
            apply_policy(report, policy=ThreatPolicy.BLOCK)
    """

    def __init__(
        self,
        pii_policy: ThreatPolicy = ThreatPolicy.LOG,
        injection_policy: ThreatPolicy = ThreatPolicy.BLOCK,
        path_policy: ThreatPolicy = ThreatPolicy.BLOCK,
    ) -> None:
        self._pii_policy = pii_policy
        self._injection_policy = injection_policy
        self._path_policy = path_policy

    def scan(self, text: str, location: str = 'input') -> ThreatReport:
        """
        Scan text for all threat categories.

        Args:
            text: Text to scan
            location: Context — 'input', 'content', 'file', 'command'

        Returns:
            ThreatReport with overall_level and list of findings
        """
        start = time.time()
        findings: list[ThreatFinding] = []

        # 1. PII scan
        pii_findings = self._scan_pii(text, location)
        findings.extend(pii_findings)

        # 2. Injection scan
        inj_findings = self._scan_injection(text, location)
        findings.extend(inj_findings)

        # 3. Path traversal scan
        path_findings = self._scan_path(text, location)
        findings.extend(path_findings)

        # Determine overall level (highest severity)
        overall = ThreatLevel.CLEAR
        for f in findings:
            if f.level.value > overall.value:
                overall = f.level

        duration_ms = (time.time() - start) * 1000
        return ThreatReport(
            overall_level=overall,
            findings=findings,
            scanned_at=time.time(),
            scan_duration_ms=duration_ms,
            clear=(overall == ThreatLevel.CLEAR),
        )

    def _scan_pii(self, text: str, location: str) -> list[ThreatFinding]:
        findings = []
        for pii_type, patterns in _PII_PATTERNS.items():
            for pat in patterns:
                for m in pat.finditer(text):
                    matched_text = m.group()
                    if len(matched_text) < 3:
                        continue
                    # Determine level by PII type
                    level = self._pii_level(pii_type)
                    findings.append(ThreatFinding(
                        id=f"pii.{pii_type}.{time.time_ns()}",
                        timestamp=time.time(),
                        level=level,
                        category=f"pii.{pii_type}",
                        description=f"Potential {pii_type.upper()} detected in {location}",
                        matched=self._redact(matched_text, pii_type),
                        location=location,
                        policy=self._pii_policy,
                        remediation=self._pii_remediation(pii_type),
                    ))
        return findings

    def _pii_level(self, pii_type: str) -> ThreatLevel:
        # Critical PII: national IDs, financial
        critical = {'pan', 'aadhaar', 'gstin', 'credit_card'}
        high = {'bank_account', 'ssn', 'aws_key', 'azure_token', 'gcp_key'}
        medium = {'phone_india', 'email', 'password_like'}
        low = {'ip_address', 'dob'}

        if pii_type in critical:
            return ThreatLevel.HIGH
        if pii_type in high:
            return ThreatLevel.MEDIUM
        if pii_type in medium:
            return ThreatLevel.MEDIUM
        return ThreatLevel.LOW

    def _pii_remediation(self, pii_type: str) -> str:
        return {
            'phone_india': "Mask phone number: show last 4 digits only",
            'email': "Mask email: show first 2 chars + @domain",
            'pan': "Do not log PAN. Validate format only.",
            'aadhaar': "Do not log Aadhaar. Return to sender.",
            'bank_account': "Do not log account number. Mask.",
            'gstin': "Validate format only, do not log full GSTIN",
            'credit_card': "Do not log card numbers. PCI violation.",
            'ssn': "Do not log SSN. Mask.",
            'password_like': "Clear text password pattern detected. Use secrets manager.",
            'aws_key': "Rotate AWS credentials immediately.",
            'azure_token': "Revoke Azure token. Use managed identity.",
            'gcp_key': "Revoke GCP key. Use service account.",
            'ip_address': "Log IP range only, not full address",
            'dob': "Mask date of birth.",
        }.get(pii_type, "Review and mask.")

    def _scan_injection(self, text: str, location: str) -> list[ThreatFinding]:
        findings = []
        scan_text = text  # scan full text

        for inj_type, pattern_strs in _INJECTION_PATTERNS.items():
            for pat in pattern_strs:
                compiled = re.compile(pat, re.IGNORECASE)
                for m in compiled.finditer(text):
                    matched_text = m.group()
                    if len(matched_text) < 2:
                        continue

                    level = self._injection_level(inj_type)
                    # Check location context
                    if location == 'command' and inj_type in ('command_injection', 'sql_injection'):
                        level = ThreatLevel.HIGH

                    findings.append(ThreatFinding(
                        id=f"inj.{inj_type}.{time.time_ns()}",
                        timestamp=time.time(),
                        level=level,
                        category=f"injection.{inj_type}",
                        description=f"Potential {inj_type.replace('_', ' ')} pattern in {location}",
                        matched=matched_text,
                        location=location,
                        policy=self._injection_policy,
                        remediation=self._injection_remediation(inj_type),
                    ))
        return findings

    def _injection_level(self, inj_type: str) -> ThreatLevel:
        critical = {'prompt_injection'}  # jailbreak attempts
        high = {'sql_injection', 'command_injection'}
        medium = {'path_traversal', 'xss'}

        if inj_type in critical:
            return ThreatLevel.HIGH
        if inj_type in high:
            return ThreatLevel.MEDIUM
        if inj_type in medium:
            return ThreatLevel.MEDIUM
        return ThreatLevel.LOW

    def _injection_remediation(self, inj_type: str) -> str:
        return {
            'prompt_injection': "Reject user input. Do not execute. Escalate for review.",
            'sql_injection': "Use parameterized queries. Never interpolate user input into SQL.",
            'command_injection': "Split on separators. Never pass unsanitized input to shell.",
            'path_traversal': "Normalize and validate paths. Reject paths outside allowed scope.",
            'xss': "Escape HTML entities. Use Content-Security-Policy.",
        }.get(inj_type, "Review input before proceeding.")

    def _scan_path(self, text: str, location: str) -> list[ThreatFinding]:
        findings = []
        for pat_str in _INJECTION_PATTERNS['path_traversal']:
            pat = re.compile(pat_str)
            for m in pat.finditer(text):
                matched_text = m.group()
                if len(matched_text) < 2:
                    continue
                findings.append(ThreatFinding(
                    id=f"path.{time.time_ns()}",
                    timestamp=time.time(),
                    level=ThreatLevel.MEDIUM,
                    category="path_traversal",
                    description=f"Path traversal pattern detected in {location}",
                    matched=matched_text,
                    location=location,
                    policy=self._path_policy,
                    remediation="Validate and normalize path. Reject traversal attempts.",
                ))
        return findings

    def _redact(self, text: str, pii_type: str) -> str:
        """Redact PII for safe logging."""
        if pii_type == 'phone_india':
            if len(text) >= 10:
                return text[:len(text)-10] + 'XXXXXXX' + text[-3:]
        if pii_type == 'email':
            parts = text.split('@')
            if len(parts) == 2:
                return parts[0][:2] + '***@' + parts[1]
        if pii_type == 'pan':
            return text[:3] + 'XXXX' + text[-1]
        if pii_type == 'aadhaar':
            return 'XXXX-XXXX-' + text[-4:]
        if pii_type == 'credit_card':
            return 'XXXX-XXXX-XXXX-' + text[-4:]
        # Default: mask middle
        if len(text) > 4:
            return text[:2] + '*' * (len(text) - 4) + text[-2:]
        return '***'


# ── Policy enforcement ────────────────────────────────────────────────────────

def apply_policy(report: ThreatReport, policy: ThreatPolicy | None = None) -> PolicyResult:
    """
    Apply threat policy to a scan report.

    Args:
        report: ThreatReport from scanner.scan()
        policy: Override policy (if None, use per-finding policy)

    Returns:
        PolicyResult with decision and any blocked finding
    """
    if report.clear:
        return PolicyResult(decision=PolicyDecision.CLEAR, blocked_finding=None, message="Scan clear — no threats detected")

    # Use highest finding policy if no override
    active_policy = policy
    if active_policy is None:
        # Sort by severity
        policy_order = [ThreatPolicy.BLOCK, ThreatPolicy.ESCALATE, ThreatPolicy.WARN, ThreatPolicy.LOG]
        for p in policy_order:
            for f in report.findings:
                if f.policy == p:
                    active_policy = p
                    break
            if active_policy:
                break

    if active_policy == ThreatPolicy.BLOCK:
        if not report.findings:
            return PolicyResult(decision=PolicyDecision.CLEAR, blocked_finding=None, message="No threats to block")
        worst = max(report.findings, key=lambda f: f.level.value)
        return PolicyResult(
            decision=PolicyDecision.BLOCK,
            blocked_finding=worst,
            message=f"BLOCKED — {worst.category}: {worst.description}",
        )

    if active_policy == ThreatPolicy.ESCALATE:
        if not report.findings:
            return PolicyResult(decision=PolicyDecision.CLEAR, blocked_finding=None, message="No threats to escalate")
        worst = max(report.findings, key=lambda f: f.level.value)
        return PolicyResult(
            decision=PolicyDecision.ESCALATE,
            blocked_finding=worst,
            message=f"ESCALATED — {worst.category} requires human review",
        )

    if active_policy == ThreatPolicy.WARN:
        return PolicyResult(
            decision=PolicyDecision.WARN,
            blocked_finding=None,
            message=f"WARN — {len(report.findings)} threat(s) found, continuing",
        )

    return PolicyResult(
        decision=PolicyDecision.LOG,
        blocked_finding=None,
        message=f"LOG — {len(report.findings)} threat(s) recorded",
    )


@dataclass
class PolicyResult:
    decision: PolicyDecision
    blocked_finding: ThreatFinding | None
    message: str


class PolicyDecision(enum.Enum):
    CLEAR = "clear"
    LOG = "log"
    WARN = "warn"
    ESCALATE = "escalate"
    BLOCK = "block"


# ── ThreatLedger ──────────────────────────────────────────────────────────────

class ThreatLedger:
    """
    Audit log for all security threats detected.
    Retention: last 1000 entries (configurable).
    """

    def __init__(self, max_entries: int = 1000) -> None:
        self._entries: list[ThreatFinding] = []
        self._max_entries = max_entries

    def record(self, finding: ThreatFinding) -> None:
        self._entries.append(finding)
        if len(self._entries) > self._max_entries:
            self._entries.pop(0)

    def record_report(self, report: ThreatReport) -> int:
        """Record all findings from a report. Returns count recorded."""
        for f in report.findings:
            self.record(f)
        return len(report.findings)

    def query(
        self,
        level: ThreatLevel | None = None,
        category: str | None = None,
        since: float | None = None,
        limit: int = 100,
    ) -> list[ThreatFinding]:
        results = self._entries
        if level:
            results = [f for f in results if f.level == level]
        if category:
            results = [f for f in results if f.category.startswith(category)]
        if since:
            results = [f for f in results if f.timestamp >= since]
        return results[-limit:]

    def stats(self) -> dict[str, Any]:
        if not self._entries:
            return {"total": 0, "by_level": {}, "by_category": {}}
        by_level: dict[str, int] = {}
        by_cat: dict[str, int] = {}
        for f in self._entries:
            lv = f.level.value
            by_level[lv] = by_level.get(lv, 0) + 1
            by_cat[f.category] = by_cat.get(f.category, 0) + 1
        return {"total": len(self._entries), "by_level": by_level, "by_category": by_cat}


# ── Convenience API ───────────────────────────────────────────────────────────

_scanner = ThreatDetector()
_ledger = ThreatLedger()


def scan_content(text: str, location: str = 'input') -> ThreatReport:
    """Scan text for security threats. Convenience wrapper around ThreatDetector."""
    return _scanner.scan(text, location)


def apply_threat_policy(report: ThreatReport, policy: ThreatPolicy) -> PolicyResult:
    """Apply policy to a report. Convenience wrapper."""
    return apply_policy(report, policy)


def redact_pii(text: str) -> str:
    """Redact all PII from text for safe logging."""
    for pii_type, patterns in _PII_PATTERNS.items():
        for pat in patterns:
            text = pat.sub(lambda m: _scanner._redact(m.group(), pii_type), text)
    return text


def audit_threat(finding: ThreatFinding) -> None:
    """Record a finding to the audit ledger."""
    _ledger.record(finding)


def threat_stats() -> dict[str, Any]:
    """Return threat ledger statistics."""
    return _ledger.stats()


def threat_query(level: ThreatLevel | None = None, category: str | None = None, limit: int = 100) -> list[ThreatFinding]:
    """Query the threat ledger."""
    return _ledger.query(level=level, category=category, limit=limit)


def security_capabilities() -> dict[str, Any]:
    """Backward-compatible capability summary."""
    return {
        "threat_scanning": True,
        "pii_detection": True,
        "injection_detection": True,
        "approval_gate": True,
        "policy_enforcement": True,
    }
