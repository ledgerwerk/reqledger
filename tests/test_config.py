"""Tests for reqledger.config."""

from __future__ import annotations

from pathlib import Path

from reqledger.config import discover_config_path, load_config
from reqledger.errors import ConfigError


def test_defaults_when_no_config(workspace: Path) -> None:
    config = load_config(start=workspace)
    assert config.schema_version == 1
    assert config.requirement_prefix == "REQ"
    assert config.criterion_prefix == "AC"
    assert config.width == 4
    assert config.draft_stale_days == 90
    # Defaults anchor under the workspace.
    assert config.root == (workspace / "requirements").resolve()
    assert config.records_dir == (workspace / "requirements" / "records").resolve()
    assert config.config_path == Path()


def test_explicit_config_resolves_paths_relative_to_config(workspace: Path) -> None:
    sub = workspace / "project"
    sub.mkdir()
    (sub / "reqledger.toml").write_text(
        'schema_version = 1\n[paths]\nroot = "docs/reqs"\n'
        'records_dir = "docs/reqs/records"\nmanifest = "docs/reqs/manifest.json"\n'
        'reports_dir = "docs/reqs/reports"\n'
        'reports_state_dir = "docs/reqs/reports/reqledger"\n',
        encoding="utf-8",
    )
    config = load_config(config=sub / "reqledger.toml")
    assert config.root == (sub / "docs" / "reqs").resolve()
    assert config.records_dir == (sub / "docs" / "reqs" / "records").resolve()


def test_visible_config_wins_over_hidden(workspace: Path) -> None:
    (workspace / "reqledger.toml").write_text(
        'schema_version = 1\n[ids]\nrequirement_prefix = "REQ"\n', encoding="utf-8"
    )
    (workspace / ".reqledger.toml").write_text(
        'schema_version = 1\n[ids]\nrequirement_prefix = "R"\n', encoding="utf-8"
    )
    config = load_config(start=workspace)
    assert config.requirement_prefix == "REQ"
    # Discovery returns the visible one.
    assert discover_config_path(workspace) == (workspace / "reqledger.toml").resolve()


def test_invalid_toml_raises(workspace: Path) -> None:
    (workspace / "reqledger.toml").write_text("not = valid = toml", encoding="utf-8")
    with __import__("pytest").raises(ConfigError):
        load_config(start=workspace)


def test_missing_explicit_config_raises(workspace: Path) -> None:
    with __import__("pytest").raises(ConfigError):
        load_config(config=workspace / "does-not-exist.toml")
