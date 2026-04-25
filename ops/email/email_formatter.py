from __future__ import annotations

import html
from dataclasses import dataclass
from typing import List, Literal, Optional

EmailFormat = Literal["plain", "html"]

SIGNATURE_TEXT = "Sneha | Primeidea.in"


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
        "sincerely",
        "best,"
    ])


def has_signature(text: str) -> bool:
    t = text.lower()
    return any(x in t for x in [
        "sneha | primeidea.in",
        "sneha | primeidea",
    ])


def choose_format(subject: str, body: str, preferred: Optional[EmailFormat]) -> EmailFormat:
    if preferred in {"plain", "html"}:
        return preferred

    stripped = body.strip().lower()
    if stripped.startswith("<!doctype html") or stripped.startswith("<html"):
        return "html"

    return "plain"


def _strip_legacy_signature_lines(text: str) -> str:
    lines = text.strip().split("\n")
    cleaned: list[str] = []
    skip_lines = {
        "warm regards,",
        "warm regards",
        "best,",
        "best",
        "regards,",
        "regards",
        "thanks,",
        "thanks",
        "sneha",
        "sneha | primeidea",
        "sneha | primeidea.in",
    }
    for line in lines:
        if line.strip().lower() in skip_lines:
            continue
        cleaned.append(line)
    while cleaned and not cleaned[-1].strip():
        cleaned.pop()
    return "\n".join(cleaned).strip()


def build_plain_email(subject: str, body: str) -> FormattedEmail:
    final = _strip_legacy_signature_lines(body)
    if final:
        final += f"\n\n{SIGNATURE_TEXT}"
    else:
        final = SIGNATURE_TEXT
    return FormattedEmail("plain", subject, final)


def _is_html_tag_line(line: str) -> bool:
    """Return True if line appears to be an HTML tag or structural markup.

    Used to avoid double-escaping pre-built HTML markup that was already
    formatted as a complete email body. We deliberately do NOT look for
    doctype/html head/body tags here — that check belongs at the document
    level in the caller. This function handles intra-document HTML.
    """
    stripped = line.strip()
    # Matches: opening/closing tags, self-closing tags, HTML comments
    return stripped.startswith("<") and (
        stripped.endswith(">")
        or stripped.startswith("<!--")
        or stripped.startswith("<!DOCTYPE")
    )


def build_html_email(subject: str, body: str) -> FormattedEmail:
    lines = normalize_lines(body)
    html_parts = ["<html>", "  <body>"]

    for line in lines:
        if _is_html_tag_line(line):
            # Already HTML markup — pass through unchanged
            html_parts.append(f"    {line}")
        elif line.startswith(("-", "*", "•")):
            # Bullet point — escape plain text content only
            html_parts.append("    <ul>")
            html_parts.append(f"      <li>{html.escape(line[2:].strip())}</li>")
            html_parts.append("    </ul>")
        else:
            html_parts.append(f"    <p>{html.escape(line)}</p>")

    body_lower = body.lower()

    # Add exactly one canonical signature only if missing
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

Hope you're doing well. Let's catch up this weekend for a movie."""

    print(preview_email(sample_subject, sample_body))
