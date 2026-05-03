from pathlib import Path

from maa_protocol.cli import main
from maa_protocol.persistence import SQLiteBackend


def test_cli_version_runs(capsys):
    assert main(["version"]) == 0
    assert "maa-x" in capsys.readouterr().out


def test_cli_governance_audit_runs(tmp_path: Path, capsys):
    db_path = tmp_path / "governance.db"
    backend = SQLiteBackend(db_path)
    backend.write_audit_event("tenant-1", "invoke", {"ok": True}, caller_tenant_id="tenant-1")
    backend.close()

    assert main(["governance", "audit", "--db", str(db_path)]) == 0
    out = capsys.readouterr().out
    assert "Audit events: 1" in out


def test_cli_governance_approvals_runs(tmp_path: Path, capsys):
    db_path = tmp_path / "governance.db"
    backend = SQLiteBackend(db_path)
    backend.create_approval(
        "tenant-1",
        "trade",
        "hash",
        "op",
        "review",
        0.4,
        caller_tenant_id="tenant-1",
    )
    backend.close()

    assert main(["governance", "approvals", "--db", str(db_path)]) == 0
    out = capsys.readouterr().out
    assert "Approvals: 1" in out


def test_cli_swarm_init_runs(capsys):
    assert main(["swarm", "init"]) == 0
    assert "Swarm compatibility initialized" in capsys.readouterr().out


def test_cli_unknown_governance_command_returns_one():
    assert main(["governance"]) == 1
