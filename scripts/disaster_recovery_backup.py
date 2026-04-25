#!/usr/bin/env python3
"""
MAA Disaster Recovery Backup
============================
Backs up all critical MAA state to /archive/maa-backups/YYYY-MM-DD/maa-state.tar.gz.

Backup targets:
  data/observability/maa_metrics.json
  data/observability/task_dedup_registry.json
  ops/multi-agent-orchestrator/tasks/*.json
  ops/multi-agent-orchestrator/logs/
  tenants/*/config/
  tenants/*/clients/*/config/

Retention: 90 days — older archives are deleted after each run.
Corruption detection: each JSON is validated with json.loads() before archiving.

Usage:
  python3 disaster_recovery_backup.py [--dry-run] [--remote-dest HOST:PATH]

CRON_TZ=Asia/Calcutta
0 2 * * *  python3 /root/.openclaw/workspace/scripts/disaster_recovery_backup.py

Author: Maa maintainer
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
RETENTION_DAYS = 90

# Paths to back up (relative to WORKSPACE)
BACKUP_PATHS = [
    "data/observability/maa_metrics.json",
    "data/observability/task_dedup_registry.json",
    "ops/multi-agent-orchestrator/tasks",
    "ops/multi-agent-orchestrator/logs",
]

# Tenant config paths added dynamically


def now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _log(msg: str) -> None:
    print(f"[DISASTER_RECOVERY_BACKUP] {msg}", file=sys.stderr)


def _validate_json_file(filepath: Path) -> tuple[bool, str]:
    """Return (is_valid, error_reason).

    Skips directories gracefully (returns False without error for dirs)."""
    try:
        if filepath.is_dir():
            return False, "Is a directory (not a file)"
        with open(filepath) as f:
            json.load(f)
        return True, ""
    except json.JSONDecodeError as e:
        return False, f"JSONDecodeError: {e}"
    except OSError as e:
        return False, f"OSError: {e}"


def _collect_tenant_paths() -> list[str]:
    """Build list of tenant-scoped config/task/log paths to include."""
    tenants_root = WORKSPACE / "tenants"
    paths = []
    if not tenants_root.exists():
        return paths
    for op_dir in tenants_root.iterdir():
        if not op_dir.is_dir():
            continue

        for rel_path in [
            op_dir / "config" / "operator.json",
            op_dir / "tasks",
            op_dir / "logs",
            op_dir / "outputs",
        ]:
            if rel_path.exists():
                paths.append(str(rel_path.relative_to(WORKSPACE)))

        clients_dir = op_dir / "clients"
        if not clients_dir.is_dir():
            continue
        for cl_dir in clients_dir.iterdir():
            if not cl_dir.is_dir():
                continue
            for rel_path in [
                cl_dir / "config" / "client.json",
                cl_dir / "tasks",
                cl_dir / "logs",
                cl_dir / "outputs",
            ]:
                if rel_path.exists():
                    paths.append(str(rel_path.relative_to(WORKSPACE)))
    return paths


def _collect_backup_files() -> tuple[list[Path], list[tuple[Path, str]]]:
    """Return (valid_files, corrupt_files)."""
    valid = []
    corrupt = []

    # Static paths
    for rel in BACKUP_PATHS:
        p = WORKSPACE / rel
        if not p.exists():
            continue
        if p.is_file():
            is_valid, err = _validate_json_file(p)
            if is_valid:
                valid.append(p)
            else:
                corrupt.append((p, err))
        elif p.is_dir():
            for f in p.rglob("*"):
                if f.is_file():
                    if f.suffix == ".json":
                        is_valid, err = _validate_json_file(f)
                        if is_valid:
                            valid.append(f)
                        else:
                            corrupt.append((f, err))
                    else:
                        # Non-JSON files (completion markers, logs) are included without validation
                        valid.append(f)

    # Tenant-scoped configs/tasks/logs/outputs
    for rel in _collect_tenant_paths():
        f = WORKSPACE / rel
        if not f.exists():
            continue
        if f.is_file():
            is_valid, err = _validate_json_file(f)
            if is_valid:
                valid.append(f)
            else:
                corrupt.append((f, err))
        elif f.is_dir():
            for sub in f.rglob("*"):
                if not sub.is_file():
                    continue
                if sub.suffix == ".json":
                    is_valid, err = _validate_json_file(sub)
                    if is_valid:
                        valid.append(sub)
                    else:
                        corrupt.append((sub, err))
                else:
                    valid.append(sub)

    return valid, corrupt


def _build_manifest(file_paths: list[Path], corrupt_info: list[tuple[Path, str]]) -> dict:
    return {
        "created_at": now_iso(),
        "version": "v1.0",
        "retention_days": RETENTION_DAYS,
        "workspace": str(WORKSPACE),
        "file_count": len(file_paths),
        "corrupt_count": len(corrupt_info),
        "corrupt_files": [
            {"path": str(p), "error": err} for p, err in corrupt_info
        ],
        "files": [str(p.relative_to(WORKSPACE)) for p in file_paths],
    }


def _rotate_old_backups(dry_run: bool = False) -> None:
    """Delete archives older than RETENTION_DAYS."""
    if not ARCHIVE_ROOT.exists():
        return
    cutoff = time.time() - RETENTION_DAYS * 86400
    removed = 0
    for date_dir in ARCHIVE_ROOT.iterdir():
        if not date_dir.is_dir():
            continue
        try:
            ts = datetime.strptime(date_dir.name, "%Y-%m-%d").timestamp()
        except ValueError:
            continue
        if ts < cutoff:
            if not dry_run:
                for f in date_dir.iterdir():
                    f.unlink()
                date_dir.rmdir()
            removed += 1
    if removed:
        _log(f"Rotated {removed} old backup(s) older than {RETENTION_DAYS} days")


def _create_archive(file_paths: list[Path], dest_tar: Path,
                    corrupt_info: list[tuple[Path, str]]) -> bool:
    """Create tar.gz archive of all valid files. Returns True on success."""
    manifest = _build_manifest(file_paths, corrupt_info)

    try:
        dest_tar.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(dest_tar, "w:gz") as tf:
            import io
            manifest_bytes = json.dumps(manifest, indent=2).encode("utf-8")
            info = tarfile.TarInfo(name="maa-state/.backup_manifest.json")
            info.size = len(manifest_bytes)
            tf.addfile(info, io.BytesIO(manifest_bytes))

            # Add all files, stripping workspace prefix
            for fp in file_paths:
                arcname = "maa-state/" + str(fp.relative_to(WORKSPACE))
                tf.add(fp, arcname=arcname)

        _log(f"Archive created: {dest_tar} ({dest_tar.stat().st_size} bytes)")
        return True
    except Exception as e:
        _log(f"ERROR: Failed to create archive: {e}")
        return False


def _send_alert(summary: str, details: list[str]) -> None:
    """Send an alert to the configured operator target."""
    import subprocess as sp
    message_lines = ["🚨 MAA Disaster Recovery Backup — ALERT", summary]
    message_lines.extend(details)
    message = "\n".join(message_lines)

    config_file = WORKSPACE / "knowledge" / "maa-product" / "runtime-config.json"
    target = "telegram:6483160"
    try:
        if config_file.exists():
            config = json.loads(config_file.read_text())
            target = str(config.get("alert_target", target))
    except Exception:
        pass

    proc = sp.run(
        ["openclaw", "message", "send",
         "--channel", "telegram",
         "--target", target,
         "--message", message],
        capture_output=True, text=True, timeout=20,
    )
    if proc.returncode != 0:
        _log(f"Operator alert failed: {proc.stderr}")
    else:
        _log("Operator alert sent")


def main():
    parser = argparse.ArgumentParser(description="MAA Disaster Recovery Backup")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be backed up without writing archive")
    parser.add_argument("--remote-dest", default=None,
                        help="rsync destination HOST:PATH for off-site backup")
    args = parser.parse_args()

    _log(f"Starting backup at {now_iso()}")
    mode = "DRY_RUN" if args.dry_run else "BACKUP"

    # Step 1: collect files
    valid_files, corrupt_files = _collect_backup_files()

    if corrupt_files:
        _log(f"WARNING: {len(corrupt_files)} corrupt file(s) will be skipped:")
        for fp, err in corrupt_files:
            _log(f"  SKIP (corrupt): {fp} — {err}")

    _log(f"Found {len(valid_files)} file(s) to back up")

    if args.dry_run:
        print(f"\n[{mode}] Would back up {len(valid_files)} file(s):")
        for fp in valid_files:
            print(f"  {fp.relative_to(WORKSPACE)}")
        if corrupt_files:
            print(f"\n[{mode}] Would SKIP {len(corrupt_files)} corrupt file(s):")
            for fp, err in corrupt_files:
                print(f"  {fp} — {err}")
        return

    # Step 2: rotate old backups
    _rotate_old_backups()

    # Step 3: create today's backup dir
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    backup_dir = ARCHIVE_ROOT / today
    backup_dir.mkdir(parents=True, exist_ok=True)

    archive_path = backup_dir / "maa-state.tar.gz"

    # Step 4: build and write archive
    success = _create_archive(valid_files, archive_path, corrupt_files)

    if not success:
        _send_alert(
            "Backup FAILED — archive creation error",
            [f"Archive path: {archive_path}", "Check logs for details."]
        )
        sys.exit(1)

    # Step 5: log success
    manifest = _build_manifest(valid_files, corrupt_files)
    log_path = backup_dir / "backup.log"
    with open(log_path, "w") as f:
        f.write(f"[{mode}] {now_iso()}\n")
        f.write(f"Archive: {archive_path}\n")
        f.write(f"Files backed up: {len(valid_files)}\n")
        f.write(f"Corrupt files skipped: {len(corrupt_files)}\n")
        f.write(f"Manifest: {json.dumps(manifest, indent=2)}\n")

    # Step 6: optional remote rsync
    if args.remote_dest:
        host, remote_path = args.remote_dest.split(":", 1)
        _log(f"Rsyncing to remote: {host}:{remote_path}")
        try:
            result = subprocess.run(
                ["rsync", "-avz", "--checksum", str(archive_path),
                 f"{host}:{remote_path}/"],
                capture_output=True, text=True, timeout=300,
            )
            if result.returncode == 0:
                _log(f"Remote sync OK: {host}:{remote_path}")
            else:
                _log(f"Remote sync FAILED: {result.stderr}")
        except Exception as e:
            _log(f"Remote sync error: {e}")

    # Step 7: alert if corrupt files found (warning only)
    if corrupt_files:
        _send_alert(
            "Backup COMPLETED with warnings",
            [f"Corrupt files skipped: {len(corrupt_files)}",
             "See backup log for details."]
        )

    _log(f"Backup complete: {archive_path} ({len(valid_files)} files)")


if __name__ == "__main__":
    main()
