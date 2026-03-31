import json
import re
from pathlib import Path

INPUT_FILE = Path("/root/.openclaw/workspace/data/email/email_inbox_snapshot.txt")
OUTPUT_FILE = Path("/root/.openclaw/workspace/data/email/email_classification.json")

def classify_email(subject, sender):
    text = f"{subject} {sender}".lower()

    if any(x in text for x in ["github", "google drive", "shared with you", "notification", "alert"]):
        return "FYI"

    if any(x in text for x in ["thank you", "thanks", "received", "noted", "confirm", "meeting"]):
        return "LOW_RISK"

    if any(x in text for x in ["invest", "portfolio", "mutual fund", "returns", "allocation", "advice", "sip", "small cap"]):
        return "NEEDS_APPROVAL"

    if any(x in text for x in ["analysis", "report", "factsheet", "research", "performance"]):
        return "NEEDS_RESEARCH"

    return "FYI"

def parse_table_lines(text):
    lines = text.splitlines()
    data = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("ID"):
            continue

        parts = re.split(r"\s{2,}", line)
        if len(parts) < 5:
            continue

        email_id = parts[0]
        date = parts[1]
        sender = parts[2]
        subject = parts[3]
        labels = parts[4]
        thread = parts[5] if len(parts) > 5 else ""

        category = classify_email(subject, sender)

        data.append({
            "id": email_id,
            "date": date,
            "from": sender,
            "subject": subject,
            "labels": labels,
            "thread": thread,
            "category": category
        })

    return data

def main():
    if not INPUT_FILE.exists():
        print("Input file not found.")
        return

    raw_text = INPUT_FILE.read_text(encoding="utf-8")
    parsed = parse_table_lines(raw_text)

    OUTPUT_FILE.write_text(json.dumps(parsed, indent=2), encoding="utf-8")
    print(f"Saved classified emails to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
