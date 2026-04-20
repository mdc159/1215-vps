from __future__ import annotations

from control1215 import cli


def test_targets_command_lists_known_targets(capsys) -> None:
    assert cli.main(["targets"]) == 0
    out = capsys.readouterr().out
    assert "prototype-local" in out
    assert "vps-hub" in out


def test_docs_command_lists_architecture_pack(capsys) -> None:
    assert cli.main(["docs"]) == 0
    out = capsys.readouterr().out
    assert "docs/architecture/overview.md" in out
    assert "docs/architecture/inter-node-data-flow.md" in out


def test_services_command_for_prototype_target(capsys) -> None:
    assert cli.main(["services", "--target", "prototype-local"]) == 0
    out = capsys.readouterr().out
    assert "open-webui" in out
    assert "broker" in out
    assert "paperclip" in out


def test_show_target_command(capsys) -> None:
    assert cli.main(["show-target", "vps-hub"]) == 0
    out = capsys.readouterr().out
    assert '"name": "vps-hub"' in out
    assert '"ingress": "cloudflare+tunnel+tailnet"' in out


def test_broker_files_command(capsys) -> None:
    assert cli.main(["broker-files"]) == 0
    out = capsys.readouterr().out
    assert "stack/sql/broker/001_core.sql" in out


def test_broker_ddl_command(capsys) -> None:
    assert cli.main(["broker-ddl"]) == 0
    out = capsys.readouterr().out
    assert "CREATE SCHEMA IF NOT EXISTS broker;" in out
    assert "CREATE TABLE IF NOT EXISTS broker.events" in out
