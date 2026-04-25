#!/usr/bin/env python3
"""
Mother Agent Self-Healing — Memory Exact Deduplication (M3)
==========================================================
Scans memory/*.md for exact duplicate full-file content.
Keeps the newest file, archives older duplicates as .bak.
Logs every deduplication decision to memory/maintenance_decisions/.

Policy: Do NOT summarize or distill content. Only exact byte-for-byte
duplicate detection is allowed without explicit operator approval.

Usage:
    python3 memory_dedup.py           # dry run (default)
    python3 memory_dedup.py --execute # actually archive duplicates
    python3 memory_dedup.py --list    # list duplicates without archiving
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, UTC
from pathlib import Path

WORKSPACE = Path("/root/.openclaw/workspace")
MEMORY_DIR = WORKSPACE / "memory"
DECISIONS_DIR = WORKSPACE / "memory" / "maintenance_decisions"
CONTROL_FILES = {"AGENTS.md", "SOUL.md", "MEMORY.md", "SECURITY.md", "USER.md",
                 "IDENTITY.md", "HEARTBEAT.md", "EVALS.md", "RUNBOOK_EMAIL.md",
                 "RUNBOOK_SYSTEM.md", "EMAIL_CHECKLIST.md", "EMAIL_DAILY.md",
                 "CONTACTS_PRIVATE.md", "TOOLS.md"}

EXCLUDE_PREFIXES = (".", "_", "BOOTSTRAP")

os.makedirs(DECISIONS_DIR, exist_ok=True)


def _file_hash(path: Path) -> str:
    """Return SHA-256 hex digest of a file's bytes."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _log_decision(action: str, outcome: str, details: dict) -> None:
    """Append a maintenance decision to today's JSONL log."""
    entry = {
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "action": action,
        "outcome": outcome,
        "details": details,
    }
    log_file = DECISIONS_DIR / f"{datetime.now(UTC).strftime('%Y-%m-%d')}.jsonl"
    with open(log_file, "a") as f:
        f.write(json.dumps(entry) + "\n")


def find_duplicates(memory_dir: Path) -> dict[str, list[Path]]:
    """Find groups of files with identical content (by hash).
    Returns: {hash -> [Path, ...]} for groups with size > 1.
    Excludes control files and hidden/underscore-prefixed files.
    """
    hash_to_files: dict[str, list[Path]] = {}

    if not memory_dir.exists():
        return {}

    for path in sorted(memory_dir.iterdir()):
        # Skip control files and system files
        if path.name in CONTROL_FILES:
            continue
        if path.name.startswith(EXCLUDE_PREFIXES):
            continue
        if not path.is_file() or not path.suffix in (".md", ".txt", ".json"):
            continue

        try:
            file_hash = _file_hash(path)
        except (IOError, OSError):
            continue

        hash_to_files.setdefault(file_hash, []).append(path)

    # Return only groups with duplicates (size > 1)
    return {h: paths for h, paths in hash_to_files.items() if len(paths) > 1}


def deduplicate(groups: dict[str, list[Path]], execute: bool = False) -> dict:
    """Archive older duplicates. Keep newest by mtime. Archive others as .bak.
    
    Returns a summary dict of actions taken.
    """
    results = {"groups_found": len(groups), "archived": [], "skipped": [], "errors": []}

    for file_hash, paths in groups.items():
        # Sort by mtime descending: newest first
        sorted_paths = sorted(paths, key=lambda p: p.stat().st_mtime, reverse=True)
        keep = sorted_paths[0]
        archive = sorted_paths[1:]

        for old_path in archive:
            results["archived"].append({"kept": str(keep), "archived": str(old_path)})

            if execute:
                bak_path = old_path.with_suffix(old_path.suffix + ".bak")
                # Avoid collisions
                counter = 1
                while bak_path.exists():
                    bak_path = old_path.with_suffix(f"{old_path.suffix}.bak{counter}")
                    counter += 1

                try:
                    shutil.move(str(old_path), str(bak_path))
                    _log_decision(
                        "memory_dedup",
                        "archived",
                        {
                            "kept": str(keep.name),
                            "archived": str(old_path.name),
                            "bak_path": str(bak_path.name),
                            "hash": file_hash[:16],
                        }
                    )
                except (IOError, OSError) as e:
                    results["errors"].append({"file": str(old_path), "error": str(e)})
                    _log_decision(
                        "memory_dedup",
                        "error",
                        {"file": str(old_path), "error": str(e)}
                    )
            else:
                _log_decision(
                    "memory_dedup",
                    "would_archive",
                    {"kept": str(keep.name), "would_archive": str(old_path.name)}
                )

    return results


def main():
    parser = argparse.ArgumentParser(description="Memory exact deduplication (M3)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--execute", action="store_true",
                      help="Actually archive duplicates (default is dry-run)")
    mode.add_argument("--list", action="store_true",
                      help="List duplicates without archiving")
    args = parser.parse_args()

    execute = bool(args.execute)
    mode_str = "EXECUTE" if execute else ("LIST" if args.list else "DRY RUN")

    print(f"\n[MAA M3] Memory Dedup — {mode_str}")
    print("─" * 50)

    groups = find_duplicates(MEMORY_DIR)

    if not groups:
        print(f"  No duplicate files found.")
        _log_decision("memory_dedup", "clean", {"groups_found": 0})
        return

    print(f"  Found {len(groups)} duplicate group(s):")
    for file_hash, paths in groups.items():
        sorted_paths = sorted(paths, key=lambda p: p.stat().st_mtime, reverse=True)
        print(f"  ─ Hash {file_hash[:12]}... ({len(paths)} files):")
        for i, p in enumerate(sorted_paths):
            marker = "← KEEP" if i == 0 else "← ARCHIVE"
            age_days = (datetime.now().timestamp() - p.stat().st_mtime) / 86400
            print(f"      {p.name}  ({age_days:.1f}d old)  {marker}")

    if execute:
        results = deduplicate(groups, execute=True)
        print(f"\n  Archived {len(results['archived'])} duplicate(s).")
        if results["errors"]:
            print(f"  Errors: {results['errors']}")
    elif args.list:
        print("\n  (dry-run — no files archived)")
    else:
        print("\n  Re-run with --execute to archive duplicates.")
        print("  Re-run with --list to see duplicates without archiving.")
        # Only log in execute mode so dry-runs don't pollute maintenance_decisions/
        results = deduplicate(groups, execute=False)

    print()


if __name__ == "__main__":
    main()
