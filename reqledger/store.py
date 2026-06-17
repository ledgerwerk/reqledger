"""Record discovery, loading, saving, and duplicate detection."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from ledgercore.atomic import atomic_write_text

from reqledger.errors import DuplicateIdError, NotFoundError, ParseError
from reqledger.model import Requirement
from reqledger.parser import (
    RECORD_KEY_ORDER,  # noqa: F401  (re-exported for convenience)
    render_record_text,
    split_front_matter_text,
)


def discover_records(records_dir: Path) -> list[Path]:
    """Return the sorted list of ``*.req.md`` files in ``records_dir``."""
    if not records_dir.is_dir():
        return []
    paths = [
        p for p in records_dir.iterdir() if p.is_file() and p.name.endswith(".req.md")
    ]
    return sorted(paths, key=lambda p: p.name)


def load_requirement(path: Path) -> Requirement:
    """Load a single requirement record from ``path``."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ParseError(f"Cannot read {path}: {exc}") from exc
    metadata, body = split_front_matter_text(raw)
    return Requirement.from_dict(metadata, path=path)


def load_records(paths: Iterable[Path]) -> list[Requirement]:
    """Load all requirements from ``paths``, sorted by requirement ID."""
    records: list[Requirement] = []
    for path in paths:
        records.append(load_requirement(path))
    records.sort(key=lambda r: r.id)
    return records


def save_requirement(requirement: Requirement) -> None:
    """Atomically write a requirement record to its ``path``."""
    if not requirement.path or str(requirement.path) == ".":
        raise ParseError("Requirement has no path; cannot save")
    content = render_record_text(
        requirement.to_dict(),
        requirement.body,
    )
    atomic_write_text(requirement.path, content)


def detect_duplicate_ids(records: Iterable[Requirement]) -> dict[str, list[Path]]:
    """Return a mapping of duplicated requirement ID -> source paths."""
    seen: dict[str, list[Path]] = {}
    for record in records:
        seen.setdefault(record.id, []).append(record.path)
    return {rid: paths for rid, paths in seen.items() if len(paths) > 1}


def resolve_single(records: Iterable[Requirement], requirement_id: str) -> Requirement:
    """Return the unique record matching ``requirement_id``.

    Raises :class:`NotFoundError` when missing and :class:`DuplicateIdError`
    when more than one record shares the ID.
    """
    matches = [r for r in records if r.id == requirement_id]
    if not matches:
        raise NotFoundError(f"No requirement record with id {requirement_id!r}")
    if len(matches) > 1:
        paths = ", ".join(str(r.path) for r in matches)
        raise DuplicateIdError(f"Multiple records share id {requirement_id!r}: {paths}")
    return matches[0]


def existing_requirement_ids(records: Iterable[Requirement]) -> list[str]:
    return [r.id for r in records]


__all__ = [
    "detect_duplicate_ids",
    "discover_records",
    "existing_requirement_ids",
    "load_records",
    "load_requirement",
    "resolve_single",
    "save_requirement",
]
