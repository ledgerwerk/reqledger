"""Tests for reqledger.manifest."""

from __future__ import annotations

import json

from reqledger.config import load_config
from reqledger.manifest import build_manifest, render_manifest_json
from reqledger.model import Requirement


def _records(config, metas):
    from reqledger.parser import render_record_text

    records = []
    for meta in metas:
        path = config.records_dir / f"{meta['id'].lower()}.req.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_record_text(meta, "# body\n"), encoding="utf-8")
        records.append(Requirement.from_dict(meta, path=path))
    return records


def _meta(rid: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "id": rid,
        "title": f"Requirement {rid}",
        "kind": "functional",
        "status": "accepted",
        "priority": "must",
        "tags": ["x"],
        "spec_refs": ["specs/a.feature"],
        "criteria": [
            {
                "id": "AC-0001",
                "statement": "s",
                "verification": "behavior",
                "status": "accepted",
                "tags": ["x"],
            }
        ],
    }


def test_manifest_is_deterministic(workspace) -> None:
    config = load_config(start=workspace)
    records = _records(config, [_meta("REQ-0002"), _meta("REQ-0001")])
    text_a = render_manifest_json(records, base_path=workspace)
    text_b = render_manifest_json(records, base_path=workspace)
    assert text_a == text_b
    assert text_a.endswith("\n")


def test_manifest_sorted_by_id(workspace) -> None:
    config = load_config(start=workspace)
    records = _records(config, [_meta("REQ-0002"), _meta("REQ-0001")])
    payload = build_manifest(records, base_path=workspace)
    ids = [r["id"] for r in payload["requirements"]]
    assert ids == ["REQ-0001", "REQ-0002"]


def test_manifest_top_level_shape(workspace) -> None:
    config = load_config(start=workspace)
    records = _records(config, [_meta("REQ-0001")])
    payload = build_manifest(records, base_path=workspace)
    assert payload["schema_version"] == 1
    assert payload["tool"] == "reqledger"
    entry = payload["requirements"][0]
    assert set(entry["refs"]) == {"tasks", "architecture", "specs", "evidence"}
    assert entry["path"] == "requirements/records/req-0001.req.md"


def test_manifest_json_is_valid(workspace) -> None:
    config = load_config(start=workspace)
    records = _records(config, [_meta("REQ-0001")])
    payload = json.loads(render_manifest_json(records, base_path=workspace))
    assert payload["requirements"][0]["id"] == "REQ-0001"
