"""Tests for reqledger.parser (TOML +++ front matter)."""

from __future__ import annotations

from pathlib import Path

import pytest

from reqledger.errors import ParseError
from reqledger.parser import (
    render_record_text,
    render_toml_front_matter,
    split_front_matter_text,
    update_record_text,
)


def _sample_metadata() -> dict[str, object]:
    return {
        "schema_version": 1,
        "id": "REQ-0001",
        "title": "Reject invalid login passwords",
        "kind": "functional",
        "status": "accepted",
        "priority": "must",
        "tags": ["auth", "login"],
        "criteria": [
            {
                "id": "AC-0001",
                "statement": "Login is rejected when an invalid password is submitted.",
                "verification": "behavior",
                "status": "accepted",
                "tags": ["auth"],
            }
        ],
    }


def test_parse_valid_record() -> None:
    metadata, body = split_front_matter_text(
        '+++\nid = "REQ-0001"\ntitle = "x"\n+++\n# body\n'
    )
    assert metadata["id"] == "REQ-0001"
    assert body == "# body\n"


def test_parse_rejects_malformed_toml() -> None:
    with pytest.raises(ParseError):
        split_front_matter_text("+++\nid = = bad\n+++\nbody\n")


def test_parse_rejects_missing_opening_delim() -> None:
    with pytest.raises(ParseError, match="must start"):
        split_front_matter_text("# just a body\n")


def test_parse_rejects_missing_close() -> None:
    with pytest.raises(ParseError, match="closing"):
        split_front_matter_text('+++\nid = "REQ-0001"\n')


def test_render_is_deterministic() -> None:
    text_a = render_record_text(_sample_metadata())
    text_b = render_record_text(_sample_metadata())
    assert text_a == text_b


def test_render_uses_plusplus_delimiters_and_criteria_tables() -> None:
    text = render_record_text(_sample_metadata())
    assert text.startswith("+++\n")
    assert "[[criteria]]" in text
    assert 'id = "AC-0001"' in text


def test_render_empty_arrays() -> None:
    metadata = {
        "schema_version": 1,
        "id": "REQ-0001",
        "title": "x",
        "tags": [],
        "parent_ids": [],
        "supersedes": [],
    }
    block = render_toml_front_matter(metadata)
    assert "tags = []" in block
    assert "parent_ids = []" in block


def test_update_preserves_body() -> None:
    original = render_record_text(
        {"schema_version": 1, "id": "REQ-0001", "title": "x", "tags": []},
        "# REQ-0001\n\n## Intent\n\nKeep me.\n",
    )
    updated = update_record_text(original, {"title": "y"})
    new_metadata, body = split_front_matter_text(updated)
    assert new_metadata["title"] == "y"
    assert body == "# REQ-0001\n\n## Intent\n\nKeep me.\n"


def test_round_trip(tmp_path: Path) -> None:
    metadata = _sample_metadata()
    text = render_record_text(metadata, "# body\n")
    path = tmp_path / "req-0001.req.md"
    path.write_text(text, encoding="utf-8")
    loaded, body = split_front_matter_text(path.read_text(encoding="utf-8"))
    assert loaded["id"] == metadata["id"]
    assert loaded["criteria"][0]["id"] == "AC-0001"
    assert body == "# body\n"
