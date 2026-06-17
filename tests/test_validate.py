"""Tests for reqledger.review validation (fail-closed)."""

from __future__ import annotations

from reqledger.config import load_config
from reqledger.review import validate_records


def _meta(rid: str = "REQ-0001", **overrides) -> dict[str, object]:
    base: dict[str, object] = {
        "schema_version": 1,
        "id": rid,
        "title": "t",
        "kind": "functional",
        "status": "draft",
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
    base.update(overrides)
    return base


def _records_from(config, metas):
    from reqledger.model import Requirement
    from reqledger.parser import render_record_text

    records = []
    for meta in metas:
        path = config.records_dir / f"{meta['id'].lower()}.req.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_record_text(meta, "# body\n"), encoding="utf-8")
        records.append(Requirement.from_dict(meta, path=path))
    return records


def test_rejects_missing_required_field(workspace) -> None:
    config = load_config(start=workspace)
    meta = _meta()
    del meta["status"]
    records = _records_from(config, [meta])
    # Pass the RAW front-matter dict (as the CLI does) so a truly missing
    # field is detected rather than normalized away by from_dict().
    findings = validate_records(
        records, raw_dicts={records[0].id: dict(meta)}, config=config
    )
    codes = {f.code for f in findings if f.severity == "error"}
    assert "RQL001" in codes


def test_rejects_duplicate_requirement_ids(workspace) -> None:
    config = load_config(start=workspace)
    a = _meta("REQ-0001")
    b = _meta("REQ-0001")
    records = _records_from(config, [a, b])
    findings = validate_records(
        records, raw_dicts={r.id: r.to_dict() for r in records}, config=config
    )
    codes = {f.code for f in findings}
    assert "RQL004" in codes


def test_rejects_duplicate_criterion_ids(workspace) -> None:
    config = load_config(start=workspace)
    meta = _meta()
    meta["criteria"] = [
        {
            "id": "AC-0001",
            "statement": "a",
            "verification": "behavior",
            "status": "draft",
            "tags": [],
        },
        {
            "id": "AC-0001",
            "statement": "b",
            "verification": "behavior",
            "status": "draft",
            "tags": [],
        },
    ]
    records = _records_from(config, [meta])
    findings = validate_records(
        records, raw_dicts={r.id: r.to_dict() for r in records}, config=config
    )
    codes = {f.code for f in findings}
    assert "RQL005" in codes


def test_rejects_unknown_status(workspace) -> None:
    config = load_config(start=workspace)
    meta = _meta(status="bogus")
    records = _records_from(config, [meta])
    findings = validate_records(
        records, raw_dicts={r.id: r.to_dict() for r in records}, config=config
    )
    codes = {f.code for f in findings if f.severity == "error"}
    assert "RQL002" in codes


def test_rejects_implemented_without_refs(workspace) -> None:
    config = load_config(start=workspace)
    meta = _meta(
        status="implemented",
        spec_refs=[],
        evidence_refs=[],
        criteria=[
            {
                "id": "AC-0001",
                "statement": "s",
                "verification": "behavior",
                "status": "accepted",
                "tags": [],
            }
        ],
    )
    records = _records_from(config, [meta])
    findings = validate_records(
        records, raw_dicts={r.id: r.to_dict() for r in records}, config=config
    )
    codes = {f.code for f in findings if f.severity == "error"}
    assert "RQL010" in codes


def test_accepted_requirement_without_accepted_criteria_is_error(workspace) -> None:
    config = load_config(start=workspace)
    meta = _meta(
        status="accepted",
        criteria=[
            {
                "id": "AC-0001",
                "statement": "s",
                "verification": "behavior",
                "status": "draft",
                "tags": [],
            }
        ],
    )
    records = _records_from(config, [meta])
    findings = validate_records(
        records, raw_dicts={r.id: r.to_dict() for r in records}, config=config
    )
    codes = {f.code for f in findings if f.severity == "error"}
    assert "RQL009" in codes


def test_unresolved_parent_id(workspace) -> None:
    config = load_config(start=workspace)
    meta = _meta(parent_ids=["REQ-9999"])
    records = _records_from(config, [meta])
    findings = validate_records(
        records, raw_dicts={r.id: r.to_dict() for r in records}, config=config
    )
    codes = {f.code for f in findings}
    assert "RQL008" in codes


def test_clean_record_has_no_errors(workspace) -> None:
    config = load_config(start=workspace)
    meta = _meta(
        status="accepted",
        spec_refs=["specs/auth.feature"],
        criteria=[
            {
                "id": "AC-0001",
                "statement": "s",
                "verification": "behavior",
                "status": "accepted",
                "tags": [],
            }
        ],
    )
    records = _records_from(config, [meta])
    findings = validate_records(
        records, raw_dicts={r.id: r.to_dict() for r in records}, config=config
    )
    errors = [f for f in findings if f.severity == "error"]
    assert errors == []
