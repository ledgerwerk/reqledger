"""Tests for the reqledger CLI (Typer)."""

from __future__ import annotations

import json
import os
from pathlib import Path

from typer.testing import CliRunner

from reqledger.cli import app

runner = CliRunner()


def _invoke(args: list[str], *, chdir: Path | None = None):
    """Invoke the app, optionally under a specific working directory.

    typer's CliRunner.invoke does not accept ``cwd`` in this version, so we
    chdir around the call.
    """
    if chdir is None:
        return runner.invoke(app, args, catch_exceptions=False)
    previous = Path.cwd()
    os.chdir(chdir)
    try:
        return runner.invoke(app, args, catch_exceptions=False)
    finally:
        os.chdir(previous)


def test_init_creates_expected_layout(tmp_path: Path) -> None:
    result = _invoke(["init"], chdir=tmp_path)
    assert result.exit_code == 0, result.output
    assert (tmp_path / "reqledger.toml").is_file()
    assert (tmp_path / "requirements" / "README.md").is_file()
    assert (tmp_path / "requirements" / "records").is_dir()
    assert (tmp_path / "requirements" / "reports" / "reqledger").is_dir()


def test_init_is_idempotent(tmp_path: Path) -> None:
    _invoke(["init"], chdir=tmp_path)
    readme = tmp_path / "requirements" / "README.md"
    readme.write_text("CUSTOM\n", encoding="utf-8")
    result = _invoke(["init"], chdir=tmp_path)
    assert result.exit_code == 0, result.output
    # Existing user file is preserved without --force.
    assert readme.read_text(encoding="utf-8") == "CUSTOM\n"


def test_init_force_overwrites_config(tmp_path: Path) -> None:
    _invoke(["init"], chdir=tmp_path)
    config = tmp_path / "reqledger.toml"
    original = config.read_text(encoding="utf-8")
    config.write_text("# custom\n", encoding="utf-8")
    result = _invoke(["init", "--force"], chdir=tmp_path)
    assert result.exit_code == 0, result.output
    assert config.read_text(encoding="utf-8") == original


def test_new_creates_deterministic_ids(tmp_path: Path) -> None:
    _invoke(["init"], chdir=tmp_path)
    r1 = _invoke(
        [
            "new",
            "First",
            "--kind",
            "functional",
            "--priority",
            "must",
            "--criterion",
            "c1",
        ],
        chdir=tmp_path,
    )
    r2 = _invoke(
        [
            "new",
            "Second",
            "--kind",
            "functional",
            "--priority",
            "should",
            "--criterion",
            "c2",
        ],
        chdir=tmp_path,
    )
    assert r1.exit_code == 0, r1.output
    assert r2.exit_code == 0, r2.output
    first = (tmp_path / "requirements" / "records" / "req-0001.req.md").read_text(
        encoding="utf-8"
    )
    assert 'id = "REQ-0001"' in first
    assert 'id = "AC-0001"' in first
    second = (tmp_path / "requirements" / "records" / "req-0002.req.md").read_text(
        encoding="utf-8"
    )
    assert 'id = "REQ-0002"' in second


def test_list_and_show(tmp_path: Path) -> None:
    _invoke(["init"], chdir=tmp_path)
    _invoke(
        [
            "new",
            "Auth req",
            "--kind",
            "functional",
            "--priority",
            "must",
            "--tag",
            "auth",
            "--criterion",
            "c",
        ],
        chdir=tmp_path,
    )
    listed = _invoke(["list"], chdir=tmp_path)
    assert listed.exit_code == 0
    assert "REQ-0001" in listed.output
    assert "functional" in listed.output

    shown = _invoke(["show", "REQ-0001"], chdir=tmp_path)
    assert shown.exit_code == 0
    assert "REQ-0001" in shown.output
    assert "AC-0001" in shown.output


def test_list_filter_by_status(tmp_path: Path) -> None:
    _invoke(["init"], chdir=tmp_path)
    _invoke(["new", "A", "--criterion", "c", "--status", "draft"], chdir=tmp_path)
    _invoke(["new", "B", "--criterion", "c", "--status", "draft"], chdir=tmp_path)
    listed = _invoke(["list", "--status", "draft"], chdir=tmp_path)
    assert listed.exit_code == 0
    assert "REQ-0001" in listed.output
    assert "REQ-0002" in listed.output

    other = _invoke(["list", "--status", "accepted"], chdir=tmp_path)
    assert "REQ-0001" not in other.output


def test_list_filter_by_tag(tmp_path: Path) -> None:
    _invoke(["init"], chdir=tmp_path)
    _invoke(["new", "A", "--tag", "auth", "--criterion", "c"], chdir=tmp_path)
    _invoke(["new", "B", "--tag", "billing", "--criterion", "c"], chdir=tmp_path)
    listed = _invoke(["list", "--tag", "auth"], chdir=tmp_path)
    assert "REQ-0001" in listed.output
    assert "REQ-0002" not in listed.output


def test_validate_exits_zero_when_clean(tmp_path: Path) -> None:
    _invoke(["init"], chdir=tmp_path)
    _invoke(["new", "X", "--criterion", "c"], chdir=tmp_path)
    result = _invoke(["validate"], chdir=tmp_path)
    assert result.exit_code == 0


def test_validate_exits_one_on_duplicate_criterion(tmp_path: Path) -> None:
    _invoke(["init"], chdir=tmp_path)
    record_path = tmp_path / "requirements" / "records" / "req-0001.req.md"
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.write_text(
        '+++\nschema_version = 1\nid = "REQ-0001"\ntitle = "x"\n'
        'kind = "functional"\nstatus = "draft"\npriority = "must"\ntags = []\n\n'
        '[[criteria]]\nid = "AC-0001"\nstatement = "a"\n'
        'verification = "behavior"\nstatus = "draft"\ntags = []\n\n'
        '[[criteria]]\nid = "AC-0001"\nstatement = "b"\n'
        'verification = "behavior"\nstatus = "draft"\ntags = []\n+++\n# body\n',
        encoding="utf-8",
    )
    result = _invoke(["validate"], chdir=tmp_path)
    assert result.exit_code == 1


def test_validate_exits_one_on_missing_required_field(tmp_path: Path) -> None:
    _invoke(["init"], chdir=tmp_path)
    record_path = tmp_path / "requirements" / "records" / "req-0001.req.md"
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.write_text(
        '+++\nschema_version = 1\nid = "REQ-0001"\ntitle = "x"\n'
        'kind = "functional"\npriority = "must"\ntags = []\n+++\n# body\n',
        encoding="utf-8",
    )
    result = _invoke(["validate"], chdir=tmp_path)
    assert result.exit_code == 1


def test_index_writes_deterministic_manifest(tmp_path: Path) -> None:
    _invoke(["init"], chdir=tmp_path)
    _invoke(["new", "X", "--criterion", "c"], chdir=tmp_path)
    _invoke(["index"], chdir=tmp_path)
    manifest = tmp_path / "requirements" / "manifest.json"
    assert manifest.is_file()
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["tool"] == "reqledger"
    assert payload["requirements"][0]["id"] == "REQ-0001"
    assert payload["requirements"][0]["path"] == "requirements/records/req-0001.req.md"

    # Re-running yields identical bytes.
    first = manifest.read_text(encoding="utf-8")
    _invoke(["index"], chdir=tmp_path)
    assert manifest.read_text(encoding="utf-8") == first


def test_index_refuses_to_write_when_invalid(tmp_path: Path) -> None:
    _invoke(["init"], chdir=tmp_path)
    record_path = tmp_path / "requirements" / "records" / "req-0001.req.md"
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.write_text(
        '+++\nschema_version = 1\nid = "REQ-0001"\ntitle = "x"\n'
        'kind = "functional"\nstatus = "bogus"\npriority = "must"\ntags = []\n'
        "+++\n# body\n",
        encoding="utf-8",
    )
    result = _invoke(["index"], chdir=tmp_path)
    assert result.exit_code == 1
    assert not (tmp_path / "requirements" / "manifest.json").exists()


def test_link_updates_front_matter_and_preserves_body(tmp_path: Path) -> None:
    _invoke(["init"], chdir=tmp_path)
    _invoke(["new", "X", "--criterion", "c"], chdir=tmp_path)
    record_path = tmp_path / "requirements" / "records" / "req-0001.req.md"
    result = _invoke(
        ["link", "REQ-0001", "--task", "task-0001", "--spec", "specs/a.feature"],
        chdir=tmp_path,
    )
    assert result.exit_code == 0, result.output
    content = record_path.read_text(encoding="utf-8")
    assert "task-0001" in content
    assert "specs/a.feature" in content
    # Body preserved (Intent section intact after the front matter).
    body = content.split("+++\n", 2)[2]
    assert body.lstrip().startswith("# REQ-0001")
    assert "## Intent" in body


def test_link_dedups(tmp_path: Path) -> None:
    _invoke(["init"], chdir=tmp_path)
    _invoke(["new", "X", "--criterion", "c"], chdir=tmp_path)
    _invoke(["link", "REQ-0001", "--task", "task-0001"], chdir=tmp_path)
    _invoke(["link", "REQ-0001", "--task", "task-0001"], chdir=tmp_path)
    record = (tmp_path / "requirements" / "records" / "req-0001.req.md").read_text(
        encoding="utf-8"
    )
    assert record.count("task-0001") == 1


def test_link_warns_on_missing_local_path(tmp_path: Path) -> None:
    _invoke(["init"], chdir=tmp_path)
    _invoke(["new", "X", "--criterion", "c"], chdir=tmp_path)
    result = _invoke(
        ["link", "REQ-0001", "--evidence", "does/not/exist.json"], chdir=tmp_path
    )
    assert result.exit_code == 0  # warns, does not fail
    assert "does not exist" in result.output


def test_review_writes_reports(tmp_path: Path) -> None:
    _invoke(["init"], chdir=tmp_path)
    _invoke(["new", "X", "--criterion", "c"], chdir=tmp_path)
    result = _invoke(["review"], chdir=tmp_path)
    assert result.exit_code == 0, result.output
    review_md = tmp_path / "requirements" / "reports" / "reqledger" / "review.md"
    review_json = tmp_path / "requirements" / "reports" / "reqledger" / "review.json"
    assert review_md.is_file()
    assert review_json.is_file()
    payload = json.loads(review_json.read_text(encoding="utf-8"))
    assert payload["tool"] == "reqledger"


def test_export_deterministic_json(tmp_path: Path) -> None:
    _invoke(["init"], chdir=tmp_path)
    _invoke(["new", "X", "--criterion", "c"], chdir=tmp_path)
    a = _invoke(["export", "--format", "json"], chdir=tmp_path)
    assert a.exit_code == 0
    payload = json.loads(a.output)
    assert payload["requirements"][0]["id"] == "REQ-0001"

    out = tmp_path / "out.json"
    b = _invoke(["export", "--format", "json", "--output", str(out)], chdir=tmp_path)
    assert b.exit_code == 0
    assert out.is_file()
    assert (
        json.loads(out.read_text(encoding="utf-8"))["requirements"][0]["id"]
        == "REQ-0001"
    )


def test_json_output_is_valid_for_key_commands(tmp_path: Path) -> None:
    _invoke(["init"], chdir=tmp_path)
    _invoke(["new", "X", "--criterion", "c"], chdir=tmp_path)
    for cmd in (
        ["list", "--json"],
        ["validate", "--json"],
        ["index", "--json"],
        ["review", "--json"],
    ):
        result = _invoke(cmd, chdir=tmp_path)
        assert result.exit_code == 0, (cmd, result.output)
        json.loads(result.output)
    show = _invoke(["show", "REQ-0001", "--json"], chdir=tmp_path)
    assert show.exit_code == 0
    json.loads(show.output)


def test_show_fails_on_missing_id(tmp_path: Path) -> None:
    _invoke(["init"], chdir=tmp_path)
    result = _invoke(["show", "REQ-9999"], chdir=tmp_path)
    assert result.exit_code != 0


def test_export_rejects_unknown_format(tmp_path: Path) -> None:
    _invoke(["init"], chdir=tmp_path)
    result = _invoke(["export", "--format", "xml"], chdir=tmp_path)
    assert result.exit_code == 2


def test_version_flag_prints_version() -> None:
    result = _invoke(["--version"])
    assert result.exit_code == 0
    assert result.output.strip()  # non-empty version string


def test_no_specmason_runtime_dependency() -> None:
    """ReqLedger must not import or reference specmason (no runtime dependency)."""
    import sys

    import reqledger
    import reqledger.cli  # noqa: F401
    import reqledger.config  # noqa: F401
    import reqledger.manifest  # noqa: F401
    import reqledger.parser  # noqa: F401
    import reqledger.review  # noqa: F401
    import reqledger.store  # noqa: F401

    assert "specmason" not in sys.modules
    # ReqLedger must never import specmason. The string "specmason-discovery"
    # is an allowed ``source`` enum value (per the brief), not a dependency.
    import re

    pkg_dir = Path(reqledger.__file__).parent
    import_pattern = re.compile(r"^\s*(?:from|import)\s+specmason\b", re.MULTILINE)
    for path in pkg_dir.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert not import_pattern.search(text), f"specmason imported in {path}"
