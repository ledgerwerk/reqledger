"""ReqLedger command-line interface (Typer).

Commands: init, new, list, show, validate, index, link, review, export.
Global options: ``--version``, ``--config PATH``, ``--json``.

Exit codes follow the brief: 0 success, 1 validation errors, 2 usage/config
errors.
"""

from __future__ import annotations

import datetime as _dt
import json as _json
import sys
from pathlib import Path

import typer

from reqledger import ids as id_utils
from reqledger import manifest as manifest_mod
from reqledger import review as review_mod
from reqledger import store as store_mod
from reqledger.config import load_config
from reqledger.errors import (
    DuplicateIdError,
    NotFoundError,
    ParseError,
    ReqLedgerError,
)
from reqledger.model import ReqLedgerConfig, Requirement
from reqledger.parser import render_record_text, split_front_matter_text

app = typer.Typer(
    name="reqledger",
    help=("ReqLedger: durable record owner for requirements and acceptance criteria."),
    no_args_is_help=True,
    add_completion=False,
)

# Exit codes per brief.
EXIT_OK = 0
EXIT_VALIDATION = 1
EXIT_USAGE = 2

DEFAULT_README_BODY = """# Requirements

ReqLedger stores durable requirement records here as Markdown files with TOML
front matter. Records are the source of truth; the manifest is derived state.
"""

_DEFAULT_CONFIG_BODY = """\
schema_version = 1

[paths]
root = "requirements"
records_dir = "requirements/records"
manifest = "requirements/manifest.json"
reports_dir = "requirements/reports"
reports_state_dir = "requirements/reports/reqledger"

[ids]
requirement_prefix = "REQ"
criterion_prefix = "AC"
width = 4

[review]
draft_stale_days = 90
"""


# ---------------------------------------------------------------------------
# Global option state (populated by the main callback).
# ---------------------------------------------------------------------------


class _State:
    config: ReqLedgerConfig | None = None
    config_arg: str | None = None


_state = _State()


def _utc_today() -> str:
    return _dt.datetime.now(_dt.timezone.utc).date().isoformat()


def _emit_json(payload: object) -> None:
    typer.echo(_json.dumps(payload, indent=2, sort_keys=False, ensure_ascii=False))


def _resolve_config(start: Path | None = None) -> ReqLedgerConfig:
    # Always resolve fresh: each CLI invocation is a single process, and
    # caching would leak state across CliRunner calls in tests.
    return load_config(config=_state.config_arg, start=start or Path.cwd())


def _config_error(code: int = EXIT_USAGE) -> typer.Exit:
    raise typer.Exit(code=code)


def _load_workspace_records(config: ReqLedgerConfig) -> list[Requirement]:
    paths = store_mod.discover_records(config.records_dir)
    records = store_mod.load_records(paths)
    return records


@app.callback(invoke_without_command=True)
def main_callback(
    version: bool = typer.Option(
        False,
        "--version",
        help="Show the ReqLedger version and exit.",
        is_eager=True,
    ),
    config: str | None = typer.Option(
        None,
        "--config",
        help="Path to a reqledger.toml config file.",
        metavar="PATH",
    ),
) -> None:
    """ReqLedger: durable record owner for requirements and acceptance criteria."""
    from reqledger import __version__

    _state.config_arg = config
    if version:
        typer.echo(__version__)
        raise typer.Exit(code=EXIT_OK)


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


@app.command("init")
def init_cmd(
    force: bool = typer.Option(False, "--force", help="Overwrite existing files."),
    json_output: bool = typer.Option(
        False, "--json", help="Emit machine-readable JSON."
    ),
) -> None:
    """Create the requirements workspace layout and default config."""
    config = _resolve_config()
    created: list[str] = []
    existing: list[str] = []
    skipped: list[str] = []

    files: list[tuple[Path, str]] = []
    config_dir = config.workspace_root
    config_file = config_dir / "reqledger.toml"
    files.append((config_file, _DEFAULT_CONFIG_BODY))
    readme = config.root / "README.md"
    files.append((readme, DEFAULT_README_BODY))
    dirs = [
        config.records_dir,
        config.reports_dir,
        config.reports_state_dir,
    ]

    for path, content in files:
        if path.exists() and not force:
            existing.append(path.as_posix())
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        created.append(path.as_posix())

    for directory in dirs:
        if directory.exists() and not force:
            existing.append(directory.as_posix() + "/")
            continue
        directory.mkdir(parents=True, exist_ok=True)
        created.append(directory.as_posix() + "/")

    # records/ may equal reports/ root sibling; ensure records exists too.
    if not config.records_dir.exists():
        config.records_dir.mkdir(parents=True, exist_ok=True)
        created.append(config.records_dir.as_posix() + "/")

    if json_output:
        _emit_json(
            {
                "created": sorted(created),
                "existing": sorted(existing),
                "skipped": sorted(skipped),
                "config": str(config_file),
            }
        )
        raise typer.Exit(code=EXIT_OK)

    typer.echo(f"config: {config_file}")
    for path in sorted(created):
        typer.echo(f"created: {path}")
    for path in sorted(existing):
        typer.echo(f"existing: {path}")
    raise typer.Exit(code=EXIT_OK)


# ---------------------------------------------------------------------------
# new
# ---------------------------------------------------------------------------


@app.command("new")
def new_cmd(
    title: str = typer.Argument(..., help="Requirement title."),
    kind: str = typer.Option("functional", "--kind", help="Requirement kind."),
    priority: str = typer.Option("must", "--priority", help="Requirement priority."),
    tag: list[str] = typer.Option([], "--tag", help="Tag (repeatable).", metavar="TAG"),
    criterion: list[str] = typer.Option(
        [],
        "--criterion",
        help="Acceptance criterion statement (repeatable).",
        metavar="STATEMENT",
    ),
    status: str = typer.Option("draft", "--status", help="Initial requirement status."),
    source: str = typer.Option("manual", "--source", help="Requirement source."),
    json_output: bool = typer.Option(
        False, "--json", help="Emit machine-readable JSON."
    ),
) -> None:
    """Create a new requirement record."""
    config = _resolve_config()
    try:
        records = _load_workspace_records(config)
    except ReqLedgerError as exc:
        typer.echo(f"error: {exc}", err=True)
        _config_error(EXIT_USAGE)

    existing_ids = store_mod.existing_requirement_ids(records)
    new_id = id_utils.next_requirement_id(existing_ids, config)

    # Refuse file/id collisions defensively.
    target_path = config.records_dir / id_utils.requirement_filename(new_id, config)
    if target_path.exists():
        typer.echo(f"error: record file already exists: {target_path}", err=True)
        _config_error(EXIT_USAGE)

    criteria: list[dict[str, object]] = []
    for index, statement in enumerate(criterion, start=1):
        cid = f"{config.criterion_prefix}-{index:0{config.width}d}"
        criteria.append(
            {
                "id": cid,
                "statement": statement,
                "verification": "behavior",
                "status": "accepted" if status == "accepted" else "draft",
                "tags": list(tag),
            }
        )

    today = _utc_today()
    metadata: dict[str, object] = {
        "schema_version": config.schema_version,
        "id": new_id,
        "title": title,
        "kind": kind,
        "status": status,
        "priority": priority,
        "owner": "",
        "tags": list(tag),
        "parent_ids": [],
        "supersedes": [],
        "superseded_by": [],
        "task_refs": [],
        "arch_refs": [],
        "spec_refs": [],
        "evidence_refs": [],
        "source": source,
        "source_refs": [],
        "created": today,
        "updated": today,
        "criteria": criteria,
    }
    body = f"# {new_id}: {title}\n\n## Intent\n\nTODO: describe intent.\n"
    content = render_record_text(metadata, body)

    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(content, encoding="utf-8")

    if json_output:
        _emit_json({"id": new_id, "path": target_path.as_posix()})
        raise typer.Exit(code=EXIT_OK)

    typer.echo(f"created: {new_id} -> {target_path}")
    raise typer.Exit(code=EXIT_OK)


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


@app.command("list")
def list_cmd(
    status: str | None = typer.Option(None, "--status", help="Filter by status."),
    tag: str | None = typer.Option(None, "--tag", help="Filter by tag."),
    json_output: bool = typer.Option(
        False, "--json", help="Emit machine-readable JSON."
    ),
) -> None:
    """List requirement records."""
    config = _resolve_config()
    try:
        records = _load_workspace_records(config)
    except ReqLedgerError as exc:
        typer.echo(f"error: {exc}", err=True)
        _config_error(EXIT_USAGE)

    filtered = [
        r
        for r in records
        if (status is None or r.status == status) and (tag is None or tag in r.tags)
    ]

    if json_output:
        _emit_json([r.to_manifest_entry() for r in filtered])
        raise typer.Exit(code=EXIT_OK)

    for record in filtered:
        parts = (record.id, record.status, record.priority, record.kind, record.title)
        typer.echo(" ".join(parts))
    raise typer.Exit(code=EXIT_OK)


# ---------------------------------------------------------------------------
# show
# ---------------------------------------------------------------------------


@app.command("show")
def show_cmd(
    requirement_id: str = typer.Argument(..., help="Requirement ID (e.g. REQ-0001)."),
    json_output: bool = typer.Option(
        False, "--json", help="Emit machine-readable JSON."
    ),
) -> None:
    """Show a single requirement record."""
    config = _resolve_config()
    try:
        records = _load_workspace_records(config)
        record = store_mod.resolve_single(records, requirement_id)
    except (NotFoundError, DuplicateIdError) as exc:
        typer.echo(f"error: {exc}", err=True)
        _config_error(EXIT_VALIDATION)
    except ReqLedgerError as exc:
        typer.echo(f"error: {exc}", err=True)
        _config_error(EXIT_USAGE)

    if json_output:
        _emit_json(record.to_manifest_entry())
        raise typer.Exit(code=EXIT_OK)

    typer.echo(f"id: {record.id}")
    typer.echo(f"title: {record.title}")
    typer.echo(f"kind: {record.kind}")
    typer.echo(f"status: {record.status}")
    typer.echo(f"priority: {record.priority}")
    typer.echo(f"tags: {', '.join(record.tags)}")
    typer.echo(f"source: {record.source}")
    typer.echo(f"path: {record.path.as_posix()}")
    typer.echo("criteria:")
    for crit in record.criteria:
        typer.echo(
            f"  - {crit.id} [{crit.status}/{crit.verification}]: {crit.statement}"
        )
    raise typer.Exit(code=EXIT_OK)


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------


@app.command("validate")
def validate_cmd(
    json_output: bool = typer.Option(
        False, "--json", help="Emit machine-readable JSON."
    ),
) -> None:
    """Validate all requirement records (fail-closed)."""
    config = _resolve_config()
    try:
        paths = store_mod.discover_records(config.records_dir)
        records = store_mod.load_records(paths)
    except ReqLedgerError as exc:
        typer.echo(f"error: {exc}", err=True)
        _config_error(EXIT_USAGE)

    raw_dicts: dict[str, dict[str, object]] = {}
    parse_failures: list[dict[str, object]] = []
    for path in paths:
        try:
            metadata, _body = split_front_matter_text(path.read_text(encoding="utf-8"))
        except ParseError as exc:
            parse_failures.append(
                {
                    "severity": "error",
                    "code": review_mod.RQL014,
                    "message": str(exc),
                    "requirement_id": "",
                    "criterion_id": "",
                    "path": path.as_posix(),
                }
            )
            continue
        rid = str(metadata.get("id", ""))
        raw_dicts[rid] = metadata

    findings = review_mod.validate_records(records, raw_dicts=raw_dicts, config=config)
    errors = [f for f in findings if f.severity == "error"]
    error_payloads = parse_failures + [f.to_dict() for f in errors]

    if json_output:
        _emit_json(
            {
                "ok": not error_payloads,
                "errors": error_payloads,
                "warnings": [f.to_dict() for f in findings if f.severity == "warning"],
            }
        )
        raise typer.Exit(code=EXIT_OK if not error_payloads else EXIT_VALIDATION)

    if parse_failures:
        for item in parse_failures:
            typer.echo(
                f"error: {item['code']} {item['path']}: {item['message']}", err=True
            )
    for finding in findings:
        stream = sys.stderr if finding.severity == "error" else sys.stdout
        text = f"{finding.severity}: {finding.code} {finding.requirement_id}"
        typer.echo(f"{text}: {finding.message}", file=stream)
    if error_payloads:
        typer.echo(f"validation failed with {len(error_payloads)} error(s)", err=True)
        raise typer.Exit(code=EXIT_VALIDATION)
    typer.echo(f"validation ok: {len(records)} record(s)")
    raise typer.Exit(code=EXIT_OK)


# ---------------------------------------------------------------------------
# index
# ---------------------------------------------------------------------------


@app.command("index")
def index_cmd(
    json_output: bool = typer.Option(
        False, "--json", help="Emit machine-readable JSON."
    ),
) -> None:
    """Validate, then write the deterministic manifest.json."""
    config = _resolve_config()
    try:
        paths = store_mod.discover_records(config.records_dir)
        records = store_mod.load_records(paths)
    except ReqLedgerError as exc:
        typer.echo(f"error: {exc}", err=True)
        _config_error(EXIT_USAGE)

    raw_dicts: dict[str, dict[str, object]] = {}
    parse_failures = False
    for path in paths:
        try:
            metadata, _body = split_front_matter_text(path.read_text(encoding="utf-8"))
        except ParseError as exc:
            typer.echo(f"error: {exc}", err=True)
            parse_failures = True
            continue
        raw_dicts[str(metadata.get("id", ""))] = metadata

    findings = review_mod.validate_records(records, raw_dicts=raw_dicts, config=config)
    errors = [f for f in findings if f.severity == "error"]
    if parse_failures or errors:
        if json_output:
            _emit_json(
                {
                    "ok": False,
                    "errors": [f.to_dict() for f in errors],
                    "manifest_path": None,
                }
            )
        else:
            for finding in errors:
                msg = (
                    f"error: {finding.code} {finding.requirement_id}: {finding.message}"
                )
                typer.echo(msg, err=True)
            typer.echo("validation failed; manifest not written", err=True)
        raise typer.Exit(code=EXIT_VALIDATION)

    manifest_mod.write_manifest(
        records,
        config.manifest,
        schema_version=config.schema_version,
        base_path=config.workspace_root,
    )

    if json_output:
        _emit_json(
            {
                "ok": True,
                "manifest_path": config.manifest.as_posix(),
                "requirements": len(records),
            }
        )
        raise typer.Exit(code=EXIT_OK)

    typer.echo(f"manifest written: {config.manifest} ({len(records)} requirements)")
    raise typer.Exit(code=EXIT_OK)


# ---------------------------------------------------------------------------
# link
# ---------------------------------------------------------------------------


@app.command("link")
def link_cmd(
    requirement_id: str = typer.Argument(..., help="Requirement ID to link."),
    task: str | None = typer.Option(None, "--task", help="Task reference."),
    arch: str | None = typer.Option(None, "--arch", help="Architecture reference."),
    spec: str | None = typer.Option(
        None, "--spec", help="Spec reference (path or id)."
    ),
    evidence: str | None = typer.Option(None, "--evidence", help="Evidence reference."),
    json_output: bool = typer.Option(
        False, "--json", help="Emit machine-readable JSON."
    ),
) -> None:
    """Link a requirement to external references."""
    config = _resolve_config()
    try:
        records = _load_workspace_records(config)
        record = store_mod.resolve_single(records, requirement_id)
    except (NotFoundError, DuplicateIdError) as exc:
        typer.echo(f"error: {exc}", err=True)
        _config_error(EXIT_VALIDATION)
    except ReqLedgerError as exc:
        typer.echo(f"error: {exc}", err=True)
        _config_error(EXIT_USAGE)

    additions: list[tuple[str, str, list[str]]] = []
    if task:
        additions.append(("task", task, list(record.task_refs)))
    if arch:
        additions.append(("arch", arch, list(record.arch_refs)))
    if spec:
        additions.append(("spec", spec, list(record.spec_refs)))
    if evidence:
        additions.append(("evidence", evidence, list(record.evidence_refs)))

    if not additions:
        typer.echo(
            "error: provide at least one of --task/--arch/--spec/--evidence", err=True
        )
        _config_error(EXIT_USAGE)

    warnings: list[str] = []
    field_map = {
        "task": "task_refs",
        "arch": "arch_refs",
        "spec": "spec_refs",
        "evidence": "evidence_refs",
    }

    raw = record.path.read_text(encoding="utf-8")
    metadata, body = split_front_matter_text(raw)
    for kind, value, _existing in additions:
        # Warn (not fail) on missing local path refs.
        candidate = Path(value)
        if "/" in value and not candidate.exists() and not _looks_like_id(value):
            warnings.append(f"warning: local path ref does not exist: {value}")
        field_name = field_map[kind]
        current = list(metadata.get(field_name, []))  # type: ignore[arg-type]
        if value not in current:
            current.append(value)
        metadata[field_name] = current
    metadata["updated"] = _utc_today()
    new_text = render_record_text(metadata, body)
    record.path.write_text(new_text, encoding="utf-8")

    if json_output:
        _emit_json(
            {
                "id": record.id,
                "path": record.path.as_posix(),
                "warnings": warnings,
                "task_refs": metadata.get("task_refs", []),
                "arch_refs": metadata.get("arch_refs", []),
                "spec_refs": metadata.get("spec_refs", []),
                "evidence_refs": metadata.get("evidence_refs", []),
            }
        )
        raise typer.Exit(code=EXIT_OK)

    for message in warnings:
        typer.echo(message)
    typer.echo(f"linked: {record.id} -> {record.path}")
    raise typer.Exit(code=EXIT_OK)


def _looks_like_id(value: str) -> bool:
    return "-" in value and value.split("-")[0].isalpha()


# ---------------------------------------------------------------------------
# review
# ---------------------------------------------------------------------------


@app.command("review")
def review_cmd(
    json_output: bool = typer.Option(
        False, "--json", help="Emit machine-readable JSON."
    ),
) -> None:
    """Write review.md and review.json reports (fail-closed)."""
    config = _resolve_config()
    try:
        paths = store_mod.discover_records(config.records_dir)
        records = store_mod.load_records(paths)
    except ReqLedgerError as exc:
        typer.echo(f"error: {exc}", err=True)
        _config_error(EXIT_USAGE)

    review_mod.write_review_reports(
        records,
        config=config,
        markdown_path=config.reports_state_dir / "review.md",
        json_path=config.reports_state_dir / "review.json",
    )

    if json_output:
        report = review_mod.build_review_report(records, config=config)
        _emit_json(report)
        raise typer.Exit(code=EXIT_OK)

    typer.echo(
        f"review written: {config.reports_state_dir / 'review.md'} "
        f"({config.reports_state_dir / 'review.json'})"
    )
    raise typer.Exit(code=EXIT_OK)


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------


@app.command("export")
def export_cmd(
    fmt: str = typer.Option("json", "--format", help="Export format (MVP: json only)."),
    output: str | None = typer.Option(
        None, "--output", help="Output file (default: stdout).", metavar="PATH"
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Emit machine-readable JSON."
    ),
) -> None:
    """Export machine-readable JSON for downstream tools."""
    if fmt != "json":
        typer.echo(
            f"error: unsupported format {fmt!r} (MVP supports only 'json')", err=True
        )
        _config_error(EXIT_USAGE)

    config = _resolve_config()
    try:
        paths = store_mod.discover_records(config.records_dir)
        records = store_mod.load_records(paths)
    except ReqLedgerError as exc:
        typer.echo(f"error: {exc}", err=True)
        _config_error(EXIT_USAGE)

    text = manifest_mod.render_export_json(
        records, schema_version=config.schema_version, base_path=config.workspace_root
    )
    if output:
        out_path = Path(output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
        if json_output:
            _emit_json({"exported": True, "path": out_path.as_posix()})
        else:
            typer.echo(f"export written: {out_path}")
        raise typer.Exit(code=EXIT_OK)

    typer.echo(text)
    raise typer.Exit(code=EXIT_OK)


__all__ = ["app"]
