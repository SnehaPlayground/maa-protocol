import csv
import json
import os
import re
import shlex
import subprocess
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any


CONFIG_PATH = Path("/root/.openclaw/workspace/ops/email/email_pipeline_config.json")


@dataclass
class EmailRow:
    email_id: str
    date: str
    sender: str
    subject: str
    labels: str
    thread: str
    category: str = ""
    action: str = ""
    reason: str = ""
    draft_reply: str = ""


def load_config() -> Dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def ensure_dir(path: str) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def safe_run(cmd: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True
    )


def fetch_inbox_table(config: Dict[str, Any]) -> str:
    account = shlex.quote(config["gmail_account"])
    query = config["gmail_query"].replace('"', '\\"')
    limit = int(config["gmail_limit"])
    cmd = f'gog email search "{query}" --account={account} --limit={limit}'
    result = safe_run(cmd)

    if result.returncode != 0:
        raise RuntimeError(f"GOG command failed:\n{result.stderr.strip()}")

    if not result.stdout.strip():
        raise RuntimeError("GOG returned empty output.")

    return result.stdout


def parse_gog_table(table_text: str) -> List[EmailRow]:
    lines = [line.rstrip() for line in table_text.splitlines() if line.strip()]
    if not lines:
        return []

    parsed: List[EmailRow] = []

    for line in lines:
        if line.startswith("ID ") or line.startswith("ID\t") or line.startswith("ID  "):
            continue

        parts = re.split(r"\s{2,}", line.strip())
        if len(parts) < 5:
            continue

        email_id = parts[0]
        date = parts[1]
        sender = parts[2]
        subject = parts[3]
        labels = parts[4]
        thread = parts[5] if len(parts) > 5 else ""

        parsed.append(
            EmailRow(
                email_id=email_id,
                date=date,
                sender=sender,
                subject=subject,
                labels=labels,
                thread=thread
            )
        )

    return parsed


def load_state(path: str) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {"seen_ids": [], "last_run": None}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"seen_ids": [], "last_run": None}


def save_state(path: str, state: Dict[str, Any]) -> None:
    Path(path).write_text(json.dumps(state, indent=2), encoding="utf-8")


def is_new_email(email: EmailRow, state: Dict[str, Any]) -> bool:
    return email.email_id not in set(state.get("seen_ids", []))


def classify_email(email: EmailRow) -> str:
    text = f"{email.sender} {email.subject} {email.labels}".lower()

    if any(x in text for x in [
        "github",
        "google drive",
        "shared with you",
        "otp",
        "verification",
        "newsletter",
        "notification",
        "alert"
    ]):
        return "FYI"

    if any(x in text for x in [
        "thank you",
        "thanks",
        "received",
        "noted",
        "confirm",
        "confirmation",
        "meeting",
        "schedule",
        "reschedule",
        "document",
        "statement"
    ]):
        return "LOW_RISK"

    if any(x in text for x in [
        "invest",
        "investment",
        "mutual fund",
        "portfolio",
        "returns",
        "allocation",
        "advice",
        "recommend",
        "sip",
        "small cap",
        "large cap",
        "mid cap",
        "pms",
        "insurance plan",
        "tax saving"
    ]):
        return "NEEDS_APPROVAL"

    if any(x in text for x in [
        "analysis",
        "research",
        "report",
        "factsheet",
        "performance",
        "comparison",
        "review",
        "holdings"
    ]):
        return "NEEDS_RESEARCH"

    return "FYI"


def decide_action(category: str) -> Dict[str, str]:
    if category == "FYI":
        return {
            "action": "NO_ACTION",
            "reason": "Informational only"
        }
    if category == "LOW_RISK":
        return {
            "action": "DRAFT_REPLY",
            "reason": "Simple safe response"
        }
    if category == "NEEDS_APPROVAL":
        return {
            "action": "ESCALATE_TO_PARTHA",
            "reason": "Advice, money, or commitment risk"
        }
    if category == "NEEDS_RESEARCH":
        return {
            "action": "PREPARE_RESEARCH_DRAFT",
            "reason": "Needs factual work before response"
        }
    return {
        "action": "ESCALATE_TO_PARTHA",
        "reason": "Unknown case"
    }


def make_draft(email: EmailRow) -> str:
    if email.action == "DRAFT_REPLY":
        subj = email.subject.lower()

        if "meeting" in subj or "confirm" in subj or "schedule" in subj:
            return "Noted. Thank you. This is confirmed from our end."

        if "document" in subj or "statement" in subj:
            return "Noted. Thank you. Kindly share the relevant document details and we will review them."

        return "Noted. Thank you. We have received your email and will revert if anything further is needed."

    if email.action == "ESCALATE_TO_PARTHA":
        return "Approval required before any response. This appears to involve advice, money, or a business commitment."

    if email.action == "PREPARE_RESEARCH_DRAFT":
        return "Research required before response. Prepare a factual internal note or draft for review."

    return ""


def build_summary(emails: List[EmailRow]) -> str:
    if not emails:
        return "No new email items requiring action."

    lines = []
    lines.append(f"Email pipeline summary at {now_str()}")
    lines.append("")

    grouped = {
        "LOW_RISK": [],
        "NEEDS_APPROVAL": [],
        "NEEDS_RESEARCH": [],
        "FYI": []
    }

    for e in emails:
        grouped.setdefault(e.category, []).append(e)

    for category in ["LOW_RISK", "NEEDS_APPROVAL", "NEEDS_RESEARCH", "FYI"]:
        items = grouped.get(category, [])
        if not items:
            continue

        lines.append(f"{category}:")
        for idx, item in enumerate(items, start=1):
            lines.append(
                f"{idx}. From: {item.sender} | Subject: {item.subject} | Action: {item.action}"
            )
        lines.append("")

    return "\n".join(lines).strip()


def write_outputs(output_dir: Path, raw_table: str, emails: List[EmailRow], summary: str) -> None:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    (output_dir / f"inbox_raw_{timestamp}.txt").write_text(raw_table, encoding="utf-8")
    (output_dir / f"email_actions_{timestamp}.json").write_text(
        json.dumps([asdict(e) for e in emails], indent=2),
        encoding="utf-8"
    )
    (output_dir / f"summary_{timestamp}.txt").write_text(summary, encoding="utf-8")

    latest_json = output_dir / "latest_email_actions.json"
    latest_txt = output_dir / "latest_summary.txt"
    latest_json.write_text(json.dumps([asdict(e) for e in emails], indent=2), encoding="utf-8")
    latest_txt.write_text(summary, encoding="utf-8")


def notify_if_needed(config: Dict[str, Any], summary: str, emails: List[EmailRow]) -> None:
    notify_command = config.get("notify_command", "").strip()
    if not notify_command:
        return

    actionable = [
        e for e in emails
        if e.action in {"ESCALATE_TO_PARTHA", "PREPARE_RESEARCH_DRAFT", "DRAFT_REPLY"}
    ]
    if not actionable:
        return

    escaped_summary = summary.replace('"', '\\"')
    cmd = notify_command.replace("{message}", escaped_summary)
    result = safe_run(cmd)

    if result.returncode != 0:
        print("Notification command failed:")
        print(result.stderr.strip())


def main() -> None:
    config = load_config()
    output_dir = ensure_dir(config["output_dir"])
    state = load_state(config["state_file"])

    raw_table = fetch_inbox_table(config)
    parsed = parse_gog_table(raw_table)

    new_items: List[EmailRow] = [email for email in parsed if is_new_email(email, state)]

    for email in new_items:
        email.category = classify_email(email)
        decision = decide_action(email.category)
        email.action = decision["action"]
        email.reason = decision["reason"]
        email.draft_reply = make_draft(email)

    summary = build_summary(new_items)
    write_outputs(output_dir, raw_table, new_items, summary)
    notify_if_needed(config, summary, new_items)

    seen_ids = set(state.get("seen_ids", []))
    for email in parsed:
        seen_ids.add(email.email_id)

    state["seen_ids"] = sorted(seen_ids)
    state["last_run"] = now_str()
    save_state(config["state_file"], state)

    print("Pipeline completed.")
    print(summary)


if __name__ == "__main__":
    main()
