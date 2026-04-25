#!/usr/bin/env python3
"""Simple guided setup for Maa Protocol."""

import json
import shutil
from pathlib import Path

WORKSPACE = Path("/root/.openclaw/workspace")
TEMPLATES = WORKSPACE / "templates" / "maa-product"
RUNTIME_DIR = WORKSPACE / "knowledge" / "maa-product"
RUNTIME_CONFIG = RUNTIME_DIR / "runtime-config.json"
PROFILES = {
    "1": "laptop.json",
    "2": "small-vps.json",
    "3": "single-tenant.json",
    "4": "community-server.json",
}


def ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or default


def main() -> None:
    print("Maa Setup")
    print("1) laptop")
    print("2) small-vps")
    print("3) single-tenant")
    print("4) community-server")
    choice = ask("Choose profile", "1")
    profile = PROFILES.get(choice, "laptop.json")

    src = TEMPLATES / profile
    if not src.exists():
        raise SystemExit(f"Missing template: {src}")

    data = json.loads(src.read_text())
    operator_label = ask("Operator label", data.get("operator", {}).get("label", "Default Operator"))
    alert_target = ask("Alert target", data.get("notifications", {}).get("alert_target", "telegram:REPLACE_WITH_OWNER_CHAT_ID"))

    data.setdefault("operator", {})["label"] = operator_label
    data.setdefault("notifications", {})["alert_target"] = alert_target

    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIME_CONFIG.write_text(json.dumps(data, indent=2) + "\n")

    print(f"\nWrote: {RUNTIME_CONFIG}")
    print("Next steps:")
    print("  python3 scripts/maa_doctor.py")
    print("  python3 scripts/maa_demo.py")


if __name__ == "__main__":
    main()
