"""Tests for reqledger.store."""

from __future__ import annotations

import pytest

from reqledger.config import load_config
from reqledger.errors import DuplicateIdError, NotFoundError
from reqledger.model import Requirement
from reqledger.store import (
    detect_duplicate_ids,
    discover_records,
    load_records,
    resolve_single,
    save_requirement,
)


def _make_metadata(rid: str, *, status: str = "draft") -> dict[str, object]:
    return {
        "schema_version": 1,
        "id": rid,
        "title": f"Requirement {rid}",
        "kind": "functional",
        "status": status,
        "priority": "must",
        "tags": [],
        "criteria": [
            {
                "id": "AC-0001",
                "statement": "s",
                "verification": "behavior",
                "status": "draft",
                "tags": [],
            }
        ],
    }


def test_discover_and_load(workspace) -> None:
    config = load_config(start=workspace)
    config.records_dir.mkdir(parents=True)
    (config.records_dir / "req-0001.req.md").write_text(
        '+++\nid = "REQ-0001"\ntitle = "a"\nkind = "functional"\n'
        'status = "draft"\npriority = "must"\ntags = []\n+++\n# body\n',
        encoding="utf-8",
    )
    (config.records_dir / "req-0002.req.md").write_text(
        '+++\nid = "REQ-0002"\ntitle = "b"\nkind = "functional"\n'
        'status = "draft"\npriority = "must"\ntags = []\n+++\n# body\n',
        encoding="utf-8",
    )
    paths = discover_records(config.records_dir)
    assert [p.name for p in paths] == ["req-0001.req.md", "req-0002.req.md"]

    records = load_records(paths)
    assert [r.id for r in records] == ["REQ-0001", "REQ-0002"]


def test_detect_duplicate_ids(workspace) -> None:
    config = load_config(start=workspace)
    config.records_dir.mkdir(parents=True)
    for name in ("req-a.req.md", "req-b.req.md"):
        (config.records_dir / name).write_text(
            '+++\nid = "REQ-0001"\ntitle = "dup"\nkind = "functional"\n'
            'status = "draft"\npriority = "must"\ntags = []\n+++\n# body\n',
            encoding="utf-8",
        )
    records = load_records(discover_records(config.records_dir))
    duplicates = detect_duplicate_ids(records)
    assert "REQ-0001" in duplicates
    assert len(duplicates["REQ-0001"]) == 2


def test_resolve_single_missing_raises(workspace) -> None:
    config = load_config(start=workspace)
    config.records_dir.mkdir(parents=True)
    records = load_records(discover_records(config.records_dir))
    with pytest.raises(NotFoundError):
        resolve_single(records, "REQ-9999")


def test_resolve_single_duplicate_raises(workspace) -> None:
    config = load_config(start=workspace)
    config.records_dir.mkdir(parents=True)
    for name in ("req-a.req.md", "req-b.req.md"):
        (config.records_dir / name).write_text(
            '+++\nid = "REQ-0001"\ntitle = "dup"\nkind = "functional"\n'
            'status = "draft"\npriority = "must"\ntags = []\n+++\n# body\n',
            encoding="utf-8",
        )
    records = load_records(discover_records(config.records_dir))
    with pytest.raises(DuplicateIdError):
        resolve_single(records, "REQ-0001")


def test_save_requirement_round_trips(workspace) -> None:
    config = load_config(start=workspace)
    config.records_dir.mkdir(parents=True)
    path = config.records_dir / "req-0001.req.md"
    record = Requirement.from_dict(_make_metadata("REQ-0001"), path=path)
    record_with_body = Requirement(**{**record.__dict__, "body": "# body\n"})
    save_requirement(record_with_body)
    loaded = load_records([path])[0]
    assert loaded.id == "REQ-0001"
    assert loaded.criteria[0].id == "AC-0001"
