from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from email_formatter import format_email


DEFAULT_ACCOUNT = "sneha.primeidea@gmail.com"
DEFAULT_PLAIN_SIGNATURE = "Sneha🥷 | https://Primeidea.in"


def run_command(cmd: list[str]) -> int:
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.stdout:
        print(result.stdout.strip())

    if result.stderr:
        print(result.stderr.strip(), file=sys.stderr)

    return result.returncode


def main() -> None:
    parser = argparse.ArgumentParser(description="Send formatted email via GOG Gmail")
    parser.add_argument("--to", required=True, help="Recipient email")
    parser.add_argument("--subject", required=True, help="Email subject")
    parser.add_argument("--body-file", required=True, help="Path to raw body text file")
    parser.add_argument("--cc", default="", help="CC recipients")
    parser.add_argument("--bcc", default="", help="BCC recipients")
    parser.add_argument("--account", default=DEFAULT_ACCOUNT, help="Gmail account")
    parser.add_argument("--force-format", choices=["plain", "html"], default=None, help="Force email format")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, do not send")

    args = parser.parse_args()

    body_path = Path(args.body_file)
    if not body_path.exists():
        print(f"Body file not found: {body_path}", file=sys.stderr)
        sys.exit(1)

    raw_body = body_path.read_text(encoding="utf-8").strip()
    formatted = format_email(args.subject, raw_body, preferred=args.force_format)

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
        "--subject", formatted.subject,
        "--no-input",
    ]

    if args.cc:
        cmd.extend(["--cc", args.cc])

    if args.bcc:
        cmd.extend(["--bcc", args.bcc])

    if formatted.format == "html":
        cmd.extend(["--body-html", formatted.body])
    else:
        cmd.extend(["--body", formatted.body])

    exit_code = run_command(cmd)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
