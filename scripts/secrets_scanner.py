#!/usr/bin/env python3
"""Scan workspace markdown files for likely secret patterns.
Skips obvious documentation/example-only matches where the matched token is part of explanatory text.
"""

import re
import sys
from pathlib import Path

WORKSPACE = Path("/root/.openclaw/workspace")
EXCLUDED_PATH_PARTS = {
    "/temp/external_orchestration_repo/",
    "/temp/maa-protocol/",
    "/archive/",
}
PATTERNS = [
    (re.compile(r"sk-[A-Za-z0-9]{20,}"), "api_key"),
    (re.compile(r"Bearer\s+[A-Za-z0-9._\-]{16,}"), "bearer_token"),
    (re.compile(r"password\s*[=:]\s*['\"][^'\"]+['\"]", re.I), "password_assignment"),
    (re.compile(r"token\s*[=:]\s*['\"][^'\"]+['\"]", re.I), "token_assignment"),
    (re.compile(r"api[_-]?key\s*[=:]\s*['\"][^'\"]+['\"]", re.I), "api_key_assignment"),
    (re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----"), "private_key"),
]
DOC_HINTS = [
    "patterns detected",
    "possible api_key pattern",
    "bearer token",
    "bearer tokens",
    "example",
    "format:",
    "usage:",
    "openai_api_key",
    "$openai_api_key",
    "source ~/.secrets",
]


def should_ignore(line: str, label: str) -> bool:
    lower = line.lower()
    return any(hint in lower for hint in DOC_HINTS)


def is_excluded(path: Path) -> bool:
    path_str = str(path)
    return any(part in path_str for part in EXCLUDED_PATH_PARTS)


def scan_file(path: Path):
    findings = []
    try:
        lines = path.read_text(errors="ignore").splitlines()
    except Exception:
        return findings
    for lineno, line in enumerate(lines, start=1):
        for pattern, label in PATTERNS:
            for match in pattern.finditer(line):
                if should_ignore(line, label):
                    continue
                findings.append((lineno, label, match.group(0)[:80]))
    return findings


def main():
    md_files = [p for p in WORKSPACE.rglob("*.md") if p.is_file() and not is_excluded(p)]
    flagged = []
    scanned = 0
    for path in md_files:
        scanned += 1
        findings = scan_file(path)
        for lineno, label, snippet in findings:
            flagged.append((path, lineno, label, snippet))
    clean = scanned - len({str(p) for p, *_ in flagged})
    print(f"Scanned: {scanned} files | Flagged: {len(flagged)} | Clean: {clean}")
    if flagged:
        print("Flagged files:")
        for path, lineno, label, snippet in flagged:
            print(f"  {path}#{lineno} — {label}: {snippet}")
        return 1
    print("No secret patterns found in workspace markdown files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
