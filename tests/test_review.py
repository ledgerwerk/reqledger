"""Tests for reqledger.review report generation."""

from __future__ import annotations

from reqledger.config import load_config
from reqledger.review import build_review_report


def _meta(**overrides) -> dict[str, object]:
    base: dict[str, object] = {
        "schema_version": 1,
        "id": "REQ-0001",
        "title": "t",
        "kind": "functional",
        "status": "accepted",
        "priority": "must",
        "tags": [],
        "spec_refs": ["specs/auth.feature"],
        "criteria": [
            {
                "id": "AC-0001",
                "statement": "s",
                "verification": "behavior",
                "status": "accepted",
                "tags": [],
            }
        ],
    }
    base.update(overrides)
    return base


def _records(config, metas):
    from reqledger.model import Requirement
    from reqledger.parser import render_record_text

    records = []
    for meta in metas:
        path = config.records_dir / f"{meta['id'].lower()}.req.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_record_text(meta, "# body\n"), encoding="utf-8")
        records.append(Requirement.from_dict(meta, path=path))
    return records


def test_flags_accepted_behavior_criterion_without_refs(workspace) -> None:
    config = load_config(start=workspace)
    meta = _meta(spec_refs=[])
    records = _records(config, [meta])
    report = build_review_report(records, config=config)
    codes = {f["code"] for f in report["findings"]}
    assert "RQL018" in codes


def test_flags_accepted_criterion_verification_none(workspace) -> None:
    config = load_config(start=workspace)
    meta = _meta(
        spec_refs=[],
        criteria=[
            {
                "id": "AC-0001",
                "statement": "s",
                "verification": "none",
                "status": "accepted",
                "tags": [],
            }
        ],
    )
    records = _records(config, [meta])
    report = build_review_report(records, config=config)
    codes = {f["code"] for f in report["findings"]}
    assert "RQL011" in codes


def test_flags_deprecated_without_successor(workspace) -> None:
    config = load_config(start=workspace)
    meta = _meta(status="deprecated", superseded_by=[], spec_refs=[])
    records = _records(config, [meta])
    report = build_review_report(records, config=config)
    codes = {f["code"] for f in report["findings"]}
    assert "RQL012" in codes


def test_flags_rejected_without_rationale(workspace) -> None:
    config = load_config(start=workspace)
    # rejected requirements do not require criteria.
    meta = _meta(status="rejected")
    meta.pop("criteria", None)
    records = _records(config, [meta])
    report = build_review_report(records, config=config)
    codes = {f["code"] for f in report["findings"]}
    assert "RQL013" in codes


def test_report_summary_counts(workspace) -> None:
    config = load_config(start=workspace)
    meta = _meta(spec_refs=[])
    records = _records(config, [meta])
    report = build_review_report(records, config=config)
    summary = report["summary"]
    assert summary["requirements"] == 1
    assert isinstance(summary["warnings"], int)
    assert isinstance(summary["errors"], int)
