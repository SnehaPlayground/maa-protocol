#!/usr/bin/env python3
"""
MAA Disaster Recovery Test / Restore Verification
==================================================
Finds the latest backup in /archive/maa-backups/, extracts it to a test dir,
verifies JSON integrity for all restored task state files, and reports RPO/RTO estimates.

Exit codes:
  0 — all files valid, restore would succeed
  1 — corruption found, restore should NOT proceed
  2 — no backup found

Usage:
  python3 disaster_recovery_test.py
  python3 disaster_recovery_test.py --restore-dir /tmp/maa-restore-test/

Author: Sneha (Mother Agent)
Phase: 11 of MAA Protocol Commercial Deployment Action Plan v1.2
"""

import argparse
import json
import os
import subprocess
import sys
import tarfile
import time
from datetime import datetime, UTC
from pathlib import Path

WORKSPACE = Path("/root/.openclaw/workspace")
ARCHIVE_ROOT = Path("/archive/maa-backups")


def now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _log(msg: str) -> None:
    print(f"[DISASTER_RECOVERY_TEST] {msg}", file=sys.stderr)


def _find_latest_backup() -> tuple[Path | None, str]:
    """Return (path_to_latest_tar, date_string) or (None, '') if none found."""
    if not ARCHIVE_ROOT.exists():
        return None, ""
    backups = []
    for date_dir in ARCHIVE_ROOT.iterdir():
        if not date_dir.is_dir():
            continue
        tar = date_dir / "maa-state.tar.gz"
        if tar.exists():
            backups.append((date_dir.name, tar))
    if not backups:
        return None, ""
    # Sort by date descending
    backups.sort(key=lambda x: x[0], reverse=True)
    return backups[0][1], backups[0][0]


def _extract_to(archive: Path, dest_dir: Path) -> tuple[bool, str]:
    """Extract tar.gz to dest_dir. Returns (success, error_msg)."""
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive, "r:gz") as tf:
            # Security: extract only files within maa-state/ prefix
            for member in tf.getmembers():
                if not member.name.startswith("maa-state/"):
                    raise ValueError(f"Blocked unsafe archive member: {member.name}")
            tf.extractall(dest_dir)
        return True, ""
    except Exception as e:
        return False, str(e)


def _iter_json_files(root: Path) -> list[Path]:
    """Recursively find all .json files under root."""
    files = []
    for f in root.rglob("*.json"):
        if f.is_file():
            files.append(f)
    return files


def _validate_json_file(fp: Path) -> tuple[bool, str]:
    """Return (is_valid, error_reason)."""
    try:
        with open(fp) as f:
            json.load(f)
        return True, ""
    except json.JSONDecodeError as e:
        return False, f"JSONDecodeError: {e}"
    except OSError as e:
        return False, f"OSError: {e}"


def _mark_corrupt(fp: Path, reason: str) -> None:
    """Write a .corrupt marker alongside the corrupt file."""
    marker = fp.with_suffix(fp.suffix + ".corrupt")
    try:
        with open(marker, "w") as f:
            f.write(f"corrupt_detected_at: {now_iso()}\nreason: {reason}\n")
        _log(f"  Written .corrupt marker: {marker}")
    except OSError:
        pass


def _estimate_rpo() -> str:
    """Estimate RPO based on backup frequency. Daily backup → RPO ≤ 24h."""
    return "< 24 hours (daily backup at 02:00 IST)"


def _estimate_rto(archive: Path, file_count: int) -> str:
    """Estimate RTO based on file count and typical restore speed."""
    # Rough estimate: ~2s per file for small JSON state files
    # Archive extraction: ~5s per GB
    estimated_seconds = (file_count * 2) + 10
    minutes = max(1, round(estimated_seconds / 60))
    return f"~{minutes} minutes (estimated for {file_count} files)"


def run_integrity_check(restore_dir: Path) -> tuple[int, int, list[tuple[Path, str]]]:
    """
    Validate all JSON files in restore_dir.
    Returns (total_files, corrupt_count, corrupt_files).
    """
    json_files = _iter_json_files(restore_dir)
    corrupt = []

    for fp in json_files:
        is_valid, reason = _validate_json_file(fp)
        if not is_valid:
            corrupt.append((fp, reason))
            _mark_corrupt(fp, reason)

    return len(json_files), len(corrupt), corrupt


def main():
    parser = argparse.ArgumentParser(description="MAA Disaster Recovery Test")
    parser.add_argument("--restore-dir", default=None,
                        help="Override extraction dir (default: auto in /tmp)")
    parser.add_argument("--skip-extract", action="store_true",
                        help="Skip extraction, use existing --restore-dir")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    _log(f"Starting DR test at {now_iso()}")

    # Step 1: find latest backup
    archive, backup_date = _find_latest_backup()
    if not archive:
        print("❌ NO BACKUP FOUND — /archive/maa-backups/ is empty or missing")
        sys.exit(2)

    _log(f"Latest backup: {archive} (date: {backup_date})")

    # Step 2: extract to test dir
    if args.skip_extract and args.restore_dir:
        restore_dir = Path(args.restore_dir)
        if not restore_dir.exists():
            print(f"❌ --restore-dir does not exist: {restore_dir}")
            sys.exit(1)
    else:
        test_date = datetime.now(UTC).strftime("%Y-%m-%d")
        restore_dir = Path(f"/tmp/maa-restore-test-{test_date}")

        # Clean any prior test dir
        if restore_dir.exists():
            import shutil
            shutil.rmtree(restore_dir)

        _log(f"Extracting to {restore_dir}...")
        success, err = _extract_to(archive, restore_dir)
        if not success:
            print(f"❌ EXTRACT FAILED: {err}")
            sys.exit(1)
        _log("Extraction complete")

    # Step 3: run integrity checks
    total, corrupt_count, corrupt_files = run_integrity_check(restore_dir)

    # Step 4: check manifest if present
    manifest_path = restore_dir / "maa-state" / ".backup_manifest.json"
    manifest_info = {}
    if manifest_path.exists():
        try:
            with open(manifest_path) as f:
                manifest_info = json.load(f)
        except Exception:
            pass

    # Step 5: compute RPO/RTO
    rpo = _estimate_rpo()
    rto = _estimate_rto(archive, total)

    # Step 6: report
    print()
    print("=" * 55)
    print("  MAA Disaster Recovery — Restore Verification Report")
    print("=" * 55)
    print(f"  Backup date:        {backup_date}")
    print(f"  Archive:            {archive.name}")
    print(f"  Restore dir:        {restore_dir}")
    print(f"  RPO estimate:       {rpo}")
    print(f"  RTO estimate:      {rto}")
    print(f"  JSON files checked: {total}")
    print(f"  Corrupt files:      {corrupt_count}")
    if manifest_info:
        print(f"  Backup manifest:    present ({manifest_info.get('file_count', '?')} files tracked)")
    print("=" * 55)

    if corrupt_count > 0:
        print()
        print("❌ CORRUPTION DETECTED — the following files are invalid JSON:")
        for fp, reason in corrupt_files:
            rel = fp.relative_to(restore_dir) if fp.is_relative_to(restore_dir) else fp
            print(f"  • {rel}")
            print(f"    Reason: {reason}")
        print()
        print("  A .corrupt marker has been written alongside each corrupt file.")
        print("  DO NOT proceed with restore until these files are repaired.")
        print()
        print(f"  ⚠️  STATUS: FAIL — exit code 1")
        sys.exit(1)
    else:
        print()
        print("✅ ALL JSON FILES VALID — restore would succeed")
        print(f"   STATUS: PASS — exit code 0")
        sys.exit(0)


if __name__ == "__main__":
    main()
