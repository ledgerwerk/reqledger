"""Shared pytest fixtures for ReqLedger tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from reqledger.config import load_config
from reqledger.model import ReqLedgerConfig


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    """An empty workspace directory (no config yet)."""
    return tmp_path


@pytest.fixture()
def initialized_workspace(workspace: Path) -> Path:
    """A workspace that has been `reqledger init`-ed."""
    from typer.testing import CliRunner

    from reqledger.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["init"], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    return workspace


@pytest.fixture()
def config(workspace: Path) -> ReqLedgerConfig:
    """Load the (default) config resolved against the workspace directory."""
    return load_config(start=workspace)


def write_record(
    workspace: Path,
    metadata: dict[str, Any],
    body: str = "# body\n",
    *,
    name: str | None = None,
) -> Path:
    """Helper to drop a raw record file into the workspace records dir."""
    from reqledger.parser import render_record_text

    records_dir = workspace / "requirements" / "records"
    records_dir.mkdir(parents=True, exist_ok=True)
    rid = str(metadata.get("id", "REQ-0001"))
    filename = name or f"{rid.lower()}.req.md"
    path = records_dir / filename
    path.write_text(render_record_text(metadata, body), encoding="utf-8")
    return path


@pytest.fixture()
def write_record_factory(workspace: Path):
    def _factory(
        metadata: dict[str, Any], body: str = "# body\n", *, name: str | None = None
    ) -> Path:
        return write_record(workspace, metadata, body, name=name)

    return _factory
