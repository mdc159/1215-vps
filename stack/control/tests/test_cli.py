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
    assert "docs/architecture/execution-plan.md" in out


def test_nodes_command_lists_manifest_examples(capsys) -> None:
    assert cli.main(["nodes"]) == 0
    out = capsys.readouterr().out
    assert "linux-prototype: target=prototype-local" in out


def test_services_command_for_prototype_target(capsys) -> None:
    assert cli.main(["services", "--target", "prototype-local"]) == 0
    out = capsys.readouterr().out
    assert "open-webui" in out
    assert "broker" in out
    assert "n8n-mcp" in out
    assert "comfyui" in out


def test_show_target_command(capsys) -> None:
    assert cli.main(["show-target", "vps-hub"]) == 0
    out = capsys.readouterr().out
    assert '"name": "vps-hub"' in out
    assert '"ingress": "cloudflare+tunnel+tailnet"' in out


def test_show_node_command(capsys) -> None:
    assert cli.main(["show-node", "linux-prototype"]) == 0
    out = capsys.readouterr().out
    assert '"name": "linux-prototype"' in out
    assert '"target": "prototype-local"' in out
    assert '"compose_profiles": [' in out
    assert '"role_compose_files": [' in out
    assert '"media"' in out
    assert '"tools"' in out
    assert '"stack/roles/media-cpu/docker-compose.role.yml"' in out
    assert '"stack/roles/tools/docker-compose.role.yml"' in out


def test_compose_cmd_for_node_includes_env_file_and_profiles(capsys) -> None:
    assert cli.main(["compose-cmd", "linux-prototype", "config"]) == 0
    out = capsys.readouterr().out
    assert "--env-file" in out
    assert "stack/prototype-local/.env" in out
    assert "stack/roles/media-cpu/docker-compose.role.yml" in out
    assert "stack/roles/tools/docker-compose.role.yml" in out
    assert "--profile media" in out
    assert "--profile tools" in out
    assert "stack/prototype-local/docker-compose.substrate.yml" in out
    assert out.rstrip().endswith("config")


def test_broker_files_command(capsys) -> None:
    assert cli.main(["broker-files"]) == 0
    out = capsys.readouterr().out
    assert "stack/sql/broker/001_core.sql" in out


def test_broker_ddl_command(capsys) -> None:
    assert cli.main(["broker-ddl"]) == 0
    out = capsys.readouterr().out
    assert "CREATE SCHEMA IF NOT EXISTS broker;" in out
    assert "CREATE TABLE IF NOT EXISTS broker.events" in out
