from __future__ import annotations

import html
from dataclasses import dataclass
from typing import List, Literal, Optional

EmailFormat = Literal["plain", "html"]

SIGNATURE_TEXT = "Sneha🥷 | https://Primeidea.in"


@dataclass
class FormattedEmail:
    format: EmailFormat
    subject: str
    body: str


def normalize_lines(text: str) -> List[str]:
    return [line.strip() for line in text.replace("\r\n", "\n").split("\n") if line.strip()]


def has_closing(text: str) -> bool:
    t = text.lower()
    return any(x in t for x in [
        "warm regards",
        "regards",
        "thanks",
        "sincerely"
    ])


def has_signature(text: str) -> bool:
    return "primeidea.in" in text.lower()


def choose_format(subject: str, body: str, preferred: Optional[EmailFormat]) -> EmailFormat:
    if preferred in {"plain", "html"}:
        return preferred

    lines = normalize_lines(body)

    if len(lines) >= 3 or any(x.startswith(("-", "*", "•")) for x in lines):
        return "html"

    return "plain"


def build_plain_email(subject: str, body: str) -> FormattedEmail:
    final = body.strip()

    if not has_closing(final):
        final += "\n\nWarm regards,\nSneha"

    if not has_signature(final):
        final += f"\n{SIGNATURE_TEXT}"

    return FormattedEmail("plain", subject, final)


def build_html_email(subject: str, body: str) -> FormattedEmail:
    lines = normalize_lines(body)

    html_parts = ["<html>", "  <body>"]

    for line in lines:
        if line.startswith(("-", "*", "•")):
            # simple bullet handling
            html_parts.append("    <ul>")
            html_parts.append(f"      <li>{html.escape(line[2:].strip())}</li>")
            html_parts.append("    </ul>")
        else:
            html_parts.append(f"    <p>{html.escape(line)}</p>")

    body_lower = body.lower()

    # Add closing if missing
    if not has_closing(body_lower):
        html_parts.append("    <p>Warm regards,</p>")
        html_parts.append("    <p>Sneha</p>")

    # Add signature only if missing
    if not has_signature(body_lower):
        html_parts.append(f"    <p>{SIGNATURE_TEXT}</p>")

    html_parts.append("  </body>")
    html_parts.append("</html>")

    return FormattedEmail("html", subject, "\n".join(html_parts))


def format_email(subject: str, body: str, preferred: Optional[EmailFormat] = None) -> FormattedEmail:
    fmt = choose_format(subject, body, preferred)

    if fmt == "html":
        return build_html_email(subject, body)

    return build_plain_email(subject, body)


def preview_email(subject: str, body: str, preferred: Optional[EmailFormat] = None) -> str:
    formatted = format_email(subject, body, preferred)

    return f"FORMAT: {formatted.format}\nSUBJECT: {formatted.subject}\n\n{formatted.body}"


if __name__ == "__main__":
    sample_subject = "Test Email"
    sample_body = """Hi Rrajal,

Hope you're doing well. Let's catch up this weekend for a movie.

Warm regards,
Sneha"""

    print(preview_email(sample_subject, sample_body))
