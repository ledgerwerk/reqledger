"""Validation and review finding generation.

This module implements the fail-closed validation checks (used by
``reqledger validate``) and the conservative review findings (used by
``reqledger review``). The same structural checks feed both; the difference is
how severities are interpreted: validation exits non-zero when any ``error``
finding exists, while review writes all findings to Markdown and JSON reports.
"""

from __future__ import annotations

import datetime as _dt
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from ledgercore.atomic import atomic_write_text
from ledgercore.jsonio import dumps_json

from reqledger.model import (
    ALLOWED_SOURCES,
    CRITERION_STATUSES,
    CRITERION_VERIFICATIONS,
    REQ_KINDS,
    REQ_PRIORITIES,
    REQ_STATUSES,
    Finding,
    ReqLedgerConfig,
    Requirement,
)

# Finding codes (per brief).
RQL001 = "RQL001"  # missing required field
RQL002 = "RQL002"  # invalid status / kind / verification
RQL003 = "RQL003"  # invalid priority
RQL004 = "RQL004"  # duplicate requirement id
RQL005 = "RQL005"  # duplicate criterion id
RQL006 = "RQL006"  # malformed requirement id
RQL007 = "RQL007"  # malformed criterion id
RQL008 = "RQL008"  # unresolved parent/supersession id
RQL009 = "RQL009"  # accepted requirement without accepted criteria
RQL010 = "RQL010"  # implemented requirement without downstream verification refs
RQL011 = "RQL011"  # accepted criterion has verification none
RQL012 = "RQL012"  # deprecated requirement without successor
RQL013 = "RQL013"  # rejected requirement without rationale
RQL014 = "RQL014"  # invalid front matter
RQL015 = "RQL015"  # duplicate external reference
RQL016 = "RQL016"  # invalid field type
RQL017 = "RQL017"  # unsupported schema version
RQL018 = "RQL018"  # accepted behavior criterion without spec/evidence refs
RQL019 = "RQL019"  # stale draft/proposed requirement

KNOWN_SOURCE_WARNING = "RQL_SOURCE_WARN"

REQUIRED_RECORD_FIELDS: tuple[str, ...] = (
    "schema_version",
    "id",
    "title",
    "kind",
    "status",
    "priority",
    "tags",
)
REQUIRED_CRITERION_FIELDS: tuple[str, ...] = (
    "id",
    "statement",
    "verification",
    "status",
    "tags",
)


# ---------------------------------------------------------------------------
# Finding constructors.
# ---------------------------------------------------------------------------


def _err(
    code: str, message: str, *, rid: str = "", cid: str = "", path: str = ""
) -> Finding:
    return Finding("error", code, message, rid, cid, path)


def _warn(
    code: str, message: str, *, rid: str = "", cid: str = "", path: str = ""
) -> Finding:
    return Finding("warning", code, message, rid, cid, path)


def _path_str(path: Path) -> str:
    try:
        return path.as_posix()
    except ValueError:
        return str(path)


def _today() -> _dt.date:
    return _dt.datetime.now(_dt.timezone.utc).date()


def _parse_iso_date(value: str) -> _dt.date | None:
    if not value:
        return None
    try:
        return _dt.date.fromisoformat(value)
    except ValueError:
        return None


def _is_string_list(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


# ---------------------------------------------------------------------------
# Structural validation (single record, raw dict).
# ---------------------------------------------------------------------------


def _looks_like_requirement_id(value: str, config: ReqLedgerConfig) -> bool:
    from reqledger.ids import is_valid_requirement_id

    return is_valid_requirement_id(value, config)


def _looks_like_criterion_id(value: str, config: ReqLedgerConfig) -> bool:
    from reqledger.ids import is_valid_criterion_id

    return is_valid_criterion_id(value, config)


def _validate_criterion_struct(
    criterion_dict: dict[str, object],
    *,
    rid: str,
    path_s: str,
    config: ReqLedgerConfig,
) -> list[Finding]:
    findings: list[Finding] = []

    for field_name in REQUIRED_CRITERION_FIELDS:
        if field_name not in criterion_dict:
            findings.append(
                _err(
                    RQL001,
                    f"Criterion missing required field '{field_name}'",
                    rid=rid,
                    cid=str(criterion_dict.get("id", "")),
                    path=path_s,
                )
            )

    cid = str(criterion_dict.get("id", ""))
    if "id" in criterion_dict and not _looks_like_criterion_id(cid, config):
        findings.append(
            _err(
                RQL007, f"Malformed criterion id {cid!r}", rid=rid, cid=cid, path=path_s
            )
        )
    if (
        "status" in criterion_dict
        and str(criterion_dict["status"]) not in CRITERION_STATUSES
    ):
        findings.append(
            _err(
                RQL002,
                f"Criterion status {criterion_dict['status']!r} is not allowed",
                rid=rid,
                cid=cid,
                path=path_s,
            )
        )
        value = criterion_dict["verification"]
        if value not in CRITERION_VERIFICATIONS:
            findings.append(
                _err(
                    RQL002,
                    f"Criterion verification {value!r} is not allowed",
                    rid=rid,
                    cid=cid,
                    path=path_s,
                )
            )

    type_expectations: dict[str, type] = {
        "id": str,
        "statement": str,
        "verification": str,
        "status": str,
        "tags": list,
    }
    for field_name, expected in type_expectations.items():
        if field_name not in criterion_dict:
            continue
        value = criterion_dict[field_name]
        if not isinstance(value, expected):
            got = type(value).__name__
            findings.append(
                _err(
                    RQL016,
                    f"Criterion field '{field_name}' has wrong type {got}",
                    rid=rid,
                    cid=cid,
                    path=path_s,
                )
            )
            continue
        if expected is list and not _is_string_list(value):
            findings.append(
                _err(
                    RQL016,
                    "Criterion field 'tags' must be an array of strings",
                    rid=rid,
                    cid=cid,
                    path=path_s,
                )
            )
    return findings


_SCALAR_TYPES: dict[str, type] = {
    "id": str,
    "title": str,
    "kind": str,
    "status": str,
    "priority": str,
    "owner": str,
    "source": str,
    "created": str,
    "updated": str,
}
_LIST_FIELDS: tuple[str, ...] = (
    "tags",
    "parent_ids",
    "supersedes",
    "superseded_by",
    "task_refs",
    "arch_refs",
    "spec_refs",
    "evidence_refs",
    "source_refs",
)


def _check_required_fields(
    record_dict: dict[str, object], *, rid: str, path_s: str
) -> list[Finding]:
    findings: list[Finding] = []
    for field_name in REQUIRED_RECORD_FIELDS:
        if field_name not in record_dict:
            findings.append(
                _err(
                    RQL001,
                    f"Missing required field '{field_name}'",
                    rid=rid,
                    path=path_s,
                )
            )
    return findings


def _check_field_types(
    record_dict: dict[str, object], *, rid: str, path_s: str
) -> list[Finding]:
    findings: list[Finding] = []
    for field_name, expected in _SCALAR_TYPES.items():
        if field_name not in record_dict:
            continue
        value = record_dict[field_name]
        if not isinstance(value, expected):
            got = type(value).__name__
            findings.append(
                _err(
                    RQL016,
                    f"Field '{field_name}' must be a string, got {got}",
                    rid=rid,
                    path=path_s,
                )
            )
    for field_name in _LIST_FIELDS:
        if field_name not in record_dict:
            continue
        value = record_dict[field_name]
        if not isinstance(value, list):
            got = type(value).__name__
            findings.append(
                _err(
                    RQL016,
                    f"Field '{field_name}' must be a string array, got {got}",
                    rid=rid,
                    path=path_s,
                )
            )
            continue
        if not _is_string_list(value):
            findings.append(
                _err(
                    RQL016,
                    f"Field '{field_name}' must be an array of strings",
                    rid=rid,
                    path=path_s,
                )
            )
    return findings


def _check_schema_version(
    record_dict: dict[str, object], *, rid: str, path_s: str
) -> list[Finding]:
    findings: list[Finding] = []
    sv = record_dict.get("schema_version")
    if sv is None:
        return findings
    if isinstance(sv, bool) or not isinstance(sv, int):
        findings.append(
            _err(
                RQL016,
                "Field 'schema_version' must be an integer",
                rid=rid,
                path=path_s,
            )
        )
    elif sv != 1:
        findings.append(
            _err(RQL017, f"Unsupported schema_version {sv}", rid=rid, path=path_s)
        )
    return findings


def _check_allowed_values(
    record_dict: dict[str, object],
    *,
    rid: str,
    path_s: str,
    config: ReqLedgerConfig,
) -> list[Finding]:
    findings: list[Finding] = []
    rid_value = record_dict.get("id")
    if "id" in record_dict and not _looks_like_requirement_id(str(rid_value), config):
        findings.append(
            _err(
                RQL006, f"Malformed requirement id {rid_value!r}", rid=rid, path=path_s
            )
        )
    if "status" in record_dict and str(record_dict["status"]) not in REQ_STATUSES:
        value = record_dict["status"]
        findings.append(
            _err(
                RQL002,
                f"Requirement status {value!r} is not allowed",
                rid=rid,
                path=path_s,
            )
        )
    if "priority" in record_dict and str(record_dict["priority"]) not in REQ_PRIORITIES:
        value = record_dict["priority"]
        findings.append(
            _err(
                RQL003,
                f"Requirement priority {value!r} is not allowed",
                rid=rid,
                path=path_s,
            )
        )
    if "kind" in record_dict and str(record_dict["kind"]) not in REQ_KINDS:
        value = record_dict["kind"]
        findings.append(
            _err(
                RQL002,
                f"Requirement kind {value!r} is not allowed",
                rid=rid,
                path=path_s,
            )
        )
    return findings


def _check_source(
    record_dict: dict[str, object], *, rid: str, path_s: str
) -> list[Finding]:
    findings: list[Finding] = []
    source = record_dict.get("source")
    if (
        "source" in record_dict
        and isinstance(source, str)
        and source not in ALLOWED_SOURCES
    ):
        findings.append(
            _warn(
                KNOWN_SOURCE_WARNING,
                f"Source {source!r} is not a known MVP source",
                rid=rid,
                path=path_s,
            )
        )
    return findings


def _check_criteria(
    record_dict: dict[str, object],
    *,
    rid: str,
    path_s: str,
    config: ReqLedgerConfig,
) -> list[Finding]:
    findings: list[Finding] = []
    status = str(record_dict.get("status", ""))
    raw_criteria = record_dict.get("criteria")
    if status != "rejected" and "criteria" not in record_dict:
        findings.append(
            _err(
                RQL001,
                "Missing 'criteria' (required unless status is 'rejected')",
                rid=rid,
                path=path_s,
            )
        )
    if raw_criteria is None:
        return findings
    if not isinstance(raw_criteria, list):
        findings.append(
            _err(RQL016, "'criteria' must be an array of tables", rid=rid, path=path_s)
        )
        return findings
    criterion_id_counts: Counter[str] = Counter()
    for raw in raw_criteria:
        if not isinstance(raw, dict):
            findings.append(
                _err(RQL016, "Each criterion must be a table", rid=rid, path=path_s)
            )
            continue
        findings.extend(
            _validate_criterion_struct(raw, rid=rid, path_s=path_s, config=config)
        )
        cid_value = str(raw.get("id", ""))
        if cid_value:
            criterion_id_counts[cid_value] += 1
    for cid_value, count in criterion_id_counts.items():
        if count > 1:
            findings.append(
                _err(
                    RQL005,
                    f"Duplicate criterion id {cid_value!r} within requirement",
                    rid=rid,
                    cid=cid_value,
                    path=path_s,
                )
            )
    return findings


def _check_cross_refs(
    record_dict: dict[str, object],
    *,
    rid: str,
    path_s: str,
    known_requirement_ids: set[str] | None,
) -> list[Finding]:
    findings: list[Finding] = []
    if known_requirement_ids is None:
        return findings
    for ref_field in ("parent_ids", "supersedes"):
        refs = record_dict.get(ref_field, [])
        if not isinstance(refs, list):
            continue
        for ref in refs:
            if isinstance(ref, str) and ref not in known_requirement_ids:
                findings.append(
                    _err(
                        RQL008,
                        f"Unresolved {ref_field} reference {ref!r}",
                        rid=rid,
                        path=path_s,
                    )
                )
    return findings


def validate_record(
    record_dict: dict[str, object],
    *,
    path: Path,
    config: ReqLedgerConfig,
    known_requirement_ids: set[str] | None = None,
) -> list[Finding]:
    """Validate a single record's raw front-matter dict."""
    rid = str(record_dict.get("id", ""))
    path_s = _path_str(path)
    findings: list[Finding] = []
    findings.extend(_check_required_fields(record_dict, rid=rid, path_s=path_s))
    findings.extend(_check_field_types(record_dict, rid=rid, path_s=path_s))
    findings.extend(_check_schema_version(record_dict, rid=rid, path_s=path_s))
    findings.extend(
        _check_allowed_values(record_dict, rid=rid, path_s=path_s, config=config)
    )
    findings.extend(_check_source(record_dict, rid=rid, path_s=path_s))
    findings.extend(_check_criteria(record_dict, rid=rid, path_s=path_s, config=config))
    findings.extend(
        _check_cross_refs(
            record_dict,
            rid=rid,
            path_s=path_s,
            known_requirement_ids=known_requirement_ids,
        )
    )
    return findings


# ---------------------------------------------------------------------------
# Cross-record validation + semantic findings.
# ---------------------------------------------------------------------------


def validate_records(
    records: Sequence[Requirement],
    *,
    raw_dicts: dict[str, dict[str, object]] | None = None,
    config: ReqLedgerConfig,
) -> list[Finding]:
    """Validate all records, including cross-record and semantic checks."""
    findings: list[Finding] = []

    id_counts: Counter[str] = Counter(r.id for r in records)
    known_ids = set(id_counts)

    for record in records:
        rid = record.id
        raw = (raw_dicts or {}).get(rid, record.to_dict())
        findings.extend(
            validate_record(
                raw, path=record.path, config=config, known_requirement_ids=known_ids
            )
        )

    for rid, count in id_counts.items():
        if count > 1:
            findings.append(
                _err(
                    RQL004,
                    f"Duplicate requirement id {rid!r} appears in {count} records",
                    rid=rid,
                )
            )

    findings.extend(_semantic_findings(records, config=config))
    return findings


def _has_downstream(record: Requirement) -> bool:
    return bool(record.spec_refs) or bool(record.evidence_refs)


def _has_rationale(body: str) -> bool:
    lowered = body.lower()
    return "## rationale" in lowered


def _is_stale(record: Requirement, *, config: ReqLedgerConfig) -> bool:
    updated = _parse_iso_date(record.updated) or _parse_iso_date(record.created)
    if updated is None:
        return False
    age = (_today() - updated).days
    return age > config.draft_stale_days


def _duplicate_ref_findings(record: Requirement) -> list[Finding]:
    findings: list[Finding] = []
    path_s = _path_str(record.path)
    ref_fields = (
        ("task_refs", record.task_refs),
        ("arch_refs", record.arch_refs),
        ("spec_refs", record.spec_refs),
        ("evidence_refs", record.evidence_refs),
        ("source_refs", record.source_refs),
    )
    for field_name, values in ref_fields:
        for value, count in Counter(values).items():
            if count > 1:
                findings.append(
                    _warn(
                        RQL015,
                        f"Duplicate external reference {value!r} in {field_name}",
                        rid=record.id,
                        path=path_s,
                    )
                )
    return findings


def _semantic_findings(
    records: Sequence[Requirement], *, config: ReqLedgerConfig
) -> list[Finding]:
    findings: list[Finding] = []
    for record in records:
        rid = record.id
        path_s = _path_str(record.path)
        has_downstream = _has_downstream(record)
        accepted_criteria = [c for c in record.criteria if c.status == "accepted"]

        # RQL009: accepted requirement without accepted criteria (error).
        if record.status == "accepted" and not accepted_criteria:
            findings.append(
                _err(
                    RQL009,
                    "Accepted requirement has no accepted criteria",
                    rid=rid,
                    path=path_s,
                )
            )

        # RQL010: implemented requirement with accepted criteria but no refs.
        if record.status == "implemented" and accepted_criteria and not has_downstream:
            msg = "Implemented req with accepted criteria lacks spec/evidence refs"
            findings.append(_err(RQL010, msg, rid=rid, path=path_s))

        # RQL012: deprecated requirement without superseded_by.
        if record.status == "deprecated" and not record.superseded_by:
            findings.append(
                _warn(
                    RQL012,
                    "Deprecated requirement has no superseded_by successor",
                    rid=rid,
                    path=path_s,
                )
            )

        # RQL013: rejected requirement without a Rationale section.
        if record.status == "rejected" and not _has_rationale(record.body):
            findings.append(
                _warn(
                    RQL013,
                    "Rejected requirement has no Rationale section in the body",
                    rid=rid,
                    path=path_s,
                )
            )

        # RQL019: stale draft/proposed record.
        if record.status in {"draft", "proposed"} and _is_stale(record, config=config):
            days = config.draft_stale_days
            findings.append(
                _warn(
                    RQL019,
                    f"{record.status.capitalize()} requirement older than {days} days",
                    rid=rid,
                    path=path_s,
                )
            )

        findings.extend(_duplicate_ref_findings(record))

        # RQL018 / RQL011: per accepted criterion.
        for crit in accepted_criteria:
            if crit.verification == "behavior" and not has_downstream:
                msg = (
                    f"Accepted behavior criterion {crit.id} without spec/evidence refs"
                )
                findings.append(_warn(RQL018, msg, rid=rid, cid=crit.id, path=path_s))
            if crit.verification == "none":
                findings.append(
                    _warn(
                        RQL011,
                        f"Accepted criterion {crit.id} has verification = 'none'",
                        rid=rid,
                        cid=crit.id,
                        path=path_s,
                    )
                )
    return findings


# ---------------------------------------------------------------------------
# Review report rendering.
# ---------------------------------------------------------------------------


def build_review_report(
    records: Sequence[Requirement], *, config: ReqLedgerConfig
) -> dict[str, object]:
    """Build the review report payload (used for both md and json rendering)."""
    findings = validate_records(records, config=config)
    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warning"]
    infos = [f for f in findings if f.severity == "info"]
    return {
        "tool": "reqledger",
        "summary": {
            "requirements": len(records),
            "errors": len(errors),
            "warnings": len(warnings),
            "infos": len(infos),
        },
        "findings": [f.to_dict() for f in findings],
    }


def render_review_json(
    records: Sequence[Requirement], *, config: ReqLedgerConfig
) -> str:
    payload = build_review_report(records, config=config)
    return dumps_json(payload, indent=2, sort_keys=False, final_newline=True)


def render_review_markdown(
    records: Sequence[Requirement], *, config: ReqLedgerConfig
) -> str:
    payload = build_review_report(records, config=config)
    summary = payload["summary"]
    assert isinstance(summary, dict)
    lines: list[str] = [
        "# ReqLedger Review Report",
        "",
        f"- Requirements: {summary['requirements']}",
        f"- Errors: {summary['errors']}",
        f"- Warnings: {summary['warnings']}",
        f"- Infos: {summary['infos']}",
        "",
    ]
    findings = payload["findings"]
    assert isinstance(findings, list)
    if not findings:
        lines.append("No findings.")
        lines.append("")
        return "\n".join(lines)
    lines.append("| Severity | Code | Requirement | Criterion | Message |")
    lines.append("| --- | --- | --- | --- | --- |")
    for raw in findings:
        assert isinstance(raw, dict)
        lines.append(
            "| {severity} | {code} | {rid} | {cid} | {message} |".format(
                severity=raw["severity"],
                code=raw["code"],
                rid=raw["requirement_id"],
                cid=raw["criterion_id"],
                message=str(raw["message"]).replace("|", "\\|"),
            )
        )
    lines.append("")
    return "\n".join(lines)


def write_review_reports(
    records: Sequence[Requirement],
    *,
    config: ReqLedgerConfig,
    markdown_path: Path,
    json_path: Path,
) -> None:
    atomic_write_text(markdown_path, render_review_markdown(records, config=config))
    atomic_write_text(json_path, render_review_json(records, config=config))


__all__ = [
    "KNOWN_SOURCE_WARNING",
    "RQL001",
    "RQL002",
    "RQL003",
    "RQL004",
    "RQL005",
    "RQL006",
    "RQL007",
    "RQL008",
    "RQL009",
    "RQL010",
    "RQL011",
    "RQL012",
    "RQL013",
    "RQL014",
    "RQL015",
    "RQL016",
    "RQL017",
    "RQL018",
    "RQL019",
    "build_review_report",
    "render_review_json",
    "render_review_markdown",
    "validate_record",
    "validate_records",
    "write_review_reports",
]
