from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from email_formatter import format_email
from email_validator import validate_email


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate, format, and send email safely")
    parser.add_argument("--to", required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--body-file", required=True)
    parser.add_argument("--cc", default="")
    parser.add_argument("--bcc", default="")
    parser.add_argument("--force-format", choices=["plain", "html"], default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    body_path = Path(args.body_file)
    if not body_path.exists():
        print(f"Body file not found: {body_path}", file=sys.stderr)
        sys.exit(1)

    raw_body = body_path.read_text(encoding="utf-8").strip()
    formatted = format_email(args.subject, raw_body, preferred=args.force_format)

    errors = validate_email(args.subject, formatted.body)
    if errors:
        print("BLOCKED EMAIL:")
        for err in errors:
            print(f"- {err}")
        sys.exit(1)

    cmd = [
        "python3",
        "/root/.openclaw/workspace/send_email_via_gog.py",
        "--to", args.to,
        "--subject", args.subject,
        "--body-file", args.body_file,
    ]

    if args.cc:
        cmd.extend(["--cc", args.cc])
    if args.bcc:
        cmd.extend(["--bcc", args.bcc])
    if args.force_format:
        cmd.extend(["--force-format", args.force_format])
    if args.dry_run:
        cmd.append("--dry-run")

    result = subprocess.run(cmd)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
