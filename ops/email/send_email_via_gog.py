from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from auth_env import build_auth_env
from email_formatter import format_email
import sys
import hashlib
from pathlib import Path


DEFAULT_ACCOUNT = "sneha.primeidea@gmail.com"
DEFAULT_PLAIN_SIGNATURE = "Sneha | Primeidea.in"
COMM_LOG_PATH = Path("/root/.openclaw/workspace/data/email/communication-log.md")
SEND_AUDIT_DIR = Path("/root/.openclaw/workspace/data/email/send_audit")
EMAIL_SEND_REGISTRY = Path("/root/.openclaw/workspace/data/email/send_audit/send_registry.json")
EMAIL_SEND_WINDOW_S = 86400  # 24-hour dedup window

# Indicators that the body file is a complete HTML document — not plain text
# to be wrapped. These must NOT be passed through email_formatter.build_html_email().
_HTML_DOCUMENT_SIGNATURES = (
    "<!DOCTYPE html",
    "<!doctype html",
    "<html",
)


def _is_complete_html_document(body: str) -> bool:
    """Return True if body appears to be a full HTML document."""
    stripped = body.strip()
    starts_html = stripped.startswith(_HTML_DOCUMENT_SIGNATURES)
    has_inline_css = 'style="' in stripped or "<style" in stripped
    has_tables = "<table" in stripped or "<td" in stripped or "<tr" in stripped
    return starts_html and (has_inline_css or has_tables)


# ── Phase 11: Side-effect dedup (email send) ─────────────────────────────────

def _body_to_hash(body: str) -> str:
    """Normalize and hash email body for dedup comparison."""
    normalized = " ".join(body.split()).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _load_email_send_registry() -> dict:
    if not EMAIL_SEND_REGISTRY.parent.exists():
        EMAIL_SEND_REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    if not EMAIL_SEND_REGISTRY.exists():
        return {}
    try:
        with open(EMAIL_SEND_REGISTRY) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_email_send_registry(reg: dict) -> None:
    tmp = str(EMAIL_SEND_REGISTRY) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(reg, f, indent=2)
    import os as _os
    _os.replace(tmp, EMAIL_SEND_REGISTRY)


def _side_effect_dedup(action_type: str, target: str, body_hash: str) -> bool:
    """Return True if identical send was registered within 24h window."""
    import time as _time
    reg = _load_email_send_registry()
    key = f"{action_type}:{target}:{body_hash}"
    entry = reg.get(key)
    if not entry:
        return False
    try:
        sent_at = datetime.fromisoformat(str(entry.get("sent_at", "")).replace("Z", "+00:00")).timestamp()
    except Exception:
        return False
    if _time.time() - sent_at > EMAIL_SEND_WINDOW_S:
        return False  # expired
    return True


def _register_side_effect(action_type: str, target: str, body: str) -> None:
    """Register a successful side-effect send for dedup."""
    body_hash = _body_to_hash(body)
    reg = _load_email_send_registry()
    key = f"{action_type}:{target}:{body_hash}"
    reg[key] = {
        "action_type": action_type,
        "target": target,
        "body_hash": body_hash,
        "sent_at": datetime.now().isoformat(),
    }
    _save_email_send_registry(reg)


def _check_and_record_side_effect(to: str, subject: str, body: str) -> bool:
    """
    Phase 11 side-effect dedup check before email send.
    Returns True if this exact email was already sent within 24h → skip send.
    Returns False → caller should proceed and then call _register_side_effect.
    """
    body_hash = _body_to_hash(body)
    if _side_effect_dedup("email_send", to, body_hash):
        return True  # duplicate found — skip
    return False


def run_command(cmd: list[str]) -> tuple[int, str, str]:
    env = build_auth_env()
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)

    if result.stdout:
        print(result.stdout.strip())

    if result.stderr:
        print(result.stderr.strip(), file=sys.stderr)

    return result.returncode, result.stdout.strip(), result.stderr.strip()


def append_comm_log(*, to: str, cc: str, bcc: str, subject: str, action: str, summary: str, approval_basis: str, thread_id: str = "") -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M IST")
    line = f"[{timestamp}] FROM: {DEFAULT_ACCOUNT} | TO: {to} | CC: {cc or '-'} | BCC: {bcc or '-'} | SUBJECT: {subject} | ACTION: {action} | APPROVAL: {approval_basis} | THREAD: {thread_id or '-'} | SUMMARY: {summary}\n"
    COMM_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing = COMM_LOG_PATH.read_text(encoding="utf-8") if COMM_LOG_PATH.exists() else ""
    lines = [x for x in existing.splitlines() if x.strip()]
    lines.append(line.rstrip("\n"))
    COMM_LOG_PATH.write_text("\n".join(lines[-50:]) + "\n", encoding="utf-8")


def write_send_audit(*, to: str, cc: str, bcc: str, subject: str, send_format: str, body_path: str, approval_basis: str, exit_code: int, stdout: str, stderr: str) -> None:
    SEND_AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    payload = {
        "timestamp": datetime.now().isoformat(),
        "to": to,
        "cc": cc,
        "bcc": bcc,
        "subject": subject,
        "format": send_format,
        "body_file": body_path,
        "approval_basis": approval_basis,
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
    }
    (SEND_AUDIT_DIR / f"send_{stamp}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Send formatted email via GOG Gmail")
    parser.add_argument("--to", required=True, help="Recipient email")
    parser.add_argument("--subject", required=True, help="Email subject")
    parser.add_argument("--body-file", required=True, help="Path to raw body text file")
    parser.add_argument("--cc", default="", help="CC recipients")
    parser.add_argument("--bcc", default="", help="BCC recipients")
    parser.add_argument("--account", default=DEFAULT_ACCOUNT, help="Gmail account")
    parser.add_argument("--force-format", choices=["plain", "html"], default=None,
                        help="Force email format (irrelevant for HTML documents — they are sent as-is)")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, do not send")
    parser.add_argument("--attach", action="append", default=[], help="Attachment file path (repeatable)")
    parser.add_argument("--approval-basis", default="unspecified", help="Approval basis for audit log, e.g. explicit|routine_courtesy|preapproved_resend")
    parser.add_argument("--verify-only", action="store_true", help="Validate body/attachments/auth path without sending")

    args = parser.parse_args()

    body_path = Path(args.body_file)
    if not body_path.exists():
        print(f"Body file not found: {body_path}", file=sys.stderr)
        sys.exit(1)

    raw_body = body_path.read_text(encoding="utf-8").strip()
    has_attachments = bool(args.attach)

    for attachment in args.attach:
        attachment_path = Path(attachment)
        if not attachment_path.exists():
            print(f"Attachment not found: {attachment_path}", file=sys.stderr)
            sys.exit(1)

    if args.verify_only:
        print("VERIFY OK")
        print(f"TO: {args.to}")
        print(f"SUBJECT: {args.subject}")
        print(f"BODY_FILE: {body_path}")
        if args.attach:
            print("ATTACHMENTS:")
            for attachment in args.attach:
                print(attachment)
        else:
            print("ATTACHMENTS: none")
        sys.exit(0)

    # -------------------------------------------------------------------------
    # Core fix: complete HTML documents (pre-built premium reports with inline
    # CSS, tables, DOCTYPE) must bypass email_formatter entirely.
    # email_formatter.build_html_email() calls html.escape() on every line,
    # which destroys markup in pre-formatted HTML reports.
    # -------------------------------------------------------------------------
    if _is_complete_html_document(raw_body):
        send_subject = args.subject
        if has_attachments:
            send_format = "plain"
            send_body = "Please find the attached HTML research report."
            if args.dry_run:
                print("DRY RUN")
                print(f"FORMAT: {send_format} (HTML document detected, sending as attachment with plain-text body)")
                print(f"TO: {args.to}")
                print(f"SUBJECT: {send_subject}")
                print("BODY:")
                print(send_body)
                print("ATTACHMENTS:")
                for attachment in args.attach:
                    print(attachment)
                sys.exit(0)
        else:
            send_format = "html"
            send_body = raw_body
            if args.dry_run:
                print("DRY RUN")
                print(f"FORMAT: {send_format} (complete HTML document — formatter bypassed)")
                print(f"TO: {args.to}")
                print(f"SUBJECT: {send_subject}")
                print("BODY: <HTML DOCUMENT — NOT PRINTED IN DRY RUN>")
                sys.exit(0)
    else:
        formatted = format_email(args.subject, raw_body, preferred=args.force_format)
        send_format = formatted.format
        send_body = formatted.body
        send_subject = formatted.subject
        if args.dry_run:
            print("DRY RUN")
            print(f"FORMAT: {formatted.format}")
            print(f"TO: {args.to}")
            print(f"SUBJECT: {formatted.subject}")
            print("BODY:")
            print(formatted.body)
            sys.exit(0)

    cmd = [
        "gog",
        "gmail",
        "send",
        "--account", args.account,
        "--to", args.to,
        "--subject", send_subject,
        "--no-input",
    ]

    if args.cc:
        cmd.extend(["--cc", args.cc])

    if args.bcc:
        cmd.extend(["--bcc", args.bcc])

    for attachment in args.attach:
        cmd.extend(["--attach", attachment])

    if send_format == "html":
        cmd.extend(["--body-html", send_body])
    else:
        # Use inline body content, never a filesystem path.
        # Some direct CLI invocations mistakenly pass a file path string as the body value.
        # This wrapper must always read the file first and send the actual content.
        cmd.extend(["--body", send_body])

    # ── Phase 11: side-effect dedup — skip if exact email was sent within 24h ─────
    # Use the actual body that will be sent (send_body), not raw_body, for dedup.
    if _check_and_record_side_effect(args.to, send_subject, send_body):
        print(f"[send_email_via_gog] DUPLICATE SKIPPED: "
              f"same email to {args.to} with subject '{send_subject}' "
              f"was sent within the last 24h.")
        write_send_audit(
            to=args.to, cc=args.cc, bcc=args.bcc,
            subject=send_subject, send_format=send_format,
            body_path=str(body_path), approval_basis=args.approval_basis,
            exit_code=0,
            stdout="duplicate_skipped",
            stderr="side-effect dedup: duplicate within 24h window",
        )
        sys.exit(0)  # clean exit — not an error, just skipped

    exit_code, stdout, stderr = run_command(cmd)
    write_send_audit(
        to=args.to,
        cc=args.cc,
        bcc=args.bcc,
        subject=send_subject,
        send_format=send_format,
        body_path=str(body_path),
        approval_basis=args.approval_basis,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
    )

    if exit_code == 0:
        thread_id = ""
        for line in stdout.splitlines():
            if line.startswith("thread_id"):
                parts = line.split("\t", 1)
                if len(parts) == 2:
                    thread_id = parts[1].strip()
        append_comm_log(
            to=args.to,
            cc=args.cc,
            bcc=args.bcc,
            subject=send_subject,
            action="send",
            summary=f"Sent via send_email_via_gog.py ({send_format})",
            approval_basis=args.approval_basis,
            thread_id=thread_id,
        )
        # ── Phase 11: record send for side-effect dedup ─────────────────────────────
        try:
            _register_side_effect("email_send", args.to, send_body)
        except Exception as ex:
            print(f"[send_email_via_gog] Warning: side-effect dedup registry not updated ({ex})")

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
