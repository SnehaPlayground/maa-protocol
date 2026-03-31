import json
from pathlib import Path

INPUT_FILE = Path("/root/.openclaw/workspace/data/email/email_classification.json")
OUTPUT_FILE = Path("/root/.openclaw/workspace/data/email/email_actions.json")

def decide_action(category, subject, sender):
    if category == "FYI":
        return {
            "action": "NO_ACTION",
            "reason": "Informational only"
        }

    if category == "LOW_RISK":
        return {
            "action": "DRAFT_REPLY",
            "reason": "Simple safe response allowed"
        }

    if category == "NEEDS_APPROVAL":
        return {
            "action": "ESCALATE_TO_PARTHA",
            "reason": "Requires approval before response"
        }

    if category == "NEEDS_RESEARCH":
        return {
            "action": "PREPARE_RESEARCH_DRAFT",
            "reason": "Needs research before response"
        }

    return {
        "action": "ESCALATE_TO_PARTHA",
        "reason": "Unclear case"
    }

def main():
    if not INPUT_FILE.exists():
        print("Classification file not found.")
        return

    items = json.loads(INPUT_FILE.read_text(encoding="utf-8"))
    actions = []

    for item in items:
        decision = decide_action(item["category"], item["subject"], item["from"])
        actions.append({
            **item,
            **decision
        })

    OUTPUT_FILE.write_text(json.dumps(actions, indent=2), encoding="utf-8")
    print(f"Saved action plan to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
