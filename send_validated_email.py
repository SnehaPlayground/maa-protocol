from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from email_formatter import format_email


def main() -> None:
    parser = argparse.ArgumentParser(description="Simple email sender (no blocking)")
    parser.add_argument("--to", required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--body-file", required=True)
    parser.add_argument("--force-format", choices=["plain", "html"], default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    body_path = Path(args.body_file)
    if not body_path.exists():
        print(f"Body file not found: {body_path}", file=sys.stderr)
        sys.exit(1)

    raw_body = body_path.read_text(encoding="utf-8").strip()

    formatted = format_email(args.subject, raw_body, preferred=args.force_format)

    # ⚠️ Only warning, no blocking
    if "sneha" in raw_body.lower() and "sneha🥷" in formatted.body.lower():
        print("⚠️ Warning: Possible duplicate signature (not blocking)")

    if "love" in raw_body.lower():
        print("⚠️ Warning: Emotional tone detected (not blocking)")

    if args.dry_run:
        print("DRY RUN")
        print(f"TO: {args.to}")
        print(f"SUBJECT: {formatted.subject}")
        print(f"FORMAT: {formatted.format}")
        print("BODY:\n")
        print(formatted.body)
        sys.exit(0)

    cmd = [
        "python3",
        "/root/.openclaw/workspace/send_email_via_gog.py",
        "--to", args.to,
        "--subject", formatted.subject,
        "--body-file", str(body_path),
    ]

    if args.force_format:
        cmd.extend(["--force-format", args.force_format])

    subprocess.run(cmd)


if __name__ == "__main__":
    main()
