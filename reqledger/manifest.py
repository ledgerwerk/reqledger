"""Deterministic manifest and export generation.

The manifest is derived state. Markdown records remain the source of truth.
Output JSON is byte-stable for a fixed set of records: requirements sorted by
ID, criteria sorted by criterion ID, 2-space indentation, trailing newline.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from ledgercore.atomic import atomic_write_text
from ledgercore.jsonio import dumps_json

from reqledger.model import Requirement

MANIFEST_TOOL_NAME = "reqledger"


def _sorted_requirements(records: Iterable[Requirement]) -> list[Requirement]:
    return sorted(records, key=lambda r: r.id)


def _sorted_entries(
    records: Iterable[Requirement], *, base_path: Path | None = None
) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for record in _sorted_requirements(records):
        entry = record.to_manifest_entry(base_path=base_path)
        # Ensure criteria are sorted by criterion id for determinism.
        entry["criteria"] = sorted(entry["criteria"], key=lambda c: str(c["id"]))
        entries.append(entry)
    return entries


def build_manifest(
    records: Iterable[Requirement],
    *,
    schema_version: int = 1,
    base_path: Path | None = None,
) -> dict[str, object]:
    """Build the deterministic manifest/export dictionary."""
    return {
        "schema_version": schema_version,
        "tool": MANIFEST_TOOL_NAME,
        "requirements": _sorted_entries(records, base_path=base_path),
    }


def render_manifest_json(
    records: Iterable[Requirement],
    *,
    schema_version: int = 1,
    base_path: Path | None = None,
) -> str:
    """Render the manifest as deterministic JSON text (2-space, trailing newline)."""
    payload = build_manifest(
        records, schema_version=schema_version, base_path=base_path
    )
    # sort_keys=False because the manifest shape is explicitly ordered.
    return dumps_json(payload, indent=2, sort_keys=False, final_newline=True)


def write_manifest(
    records: Iterable[Requirement],
    path: Path,
    *,
    schema_version: int = 1,
    base_path: Path | None = None,
) -> None:
    """Atomically write the manifest to ``path``."""
    text = render_manifest_json(
        records, schema_version=schema_version, base_path=base_path
    )
    atomic_write_text(path, text)


def render_export_json(
    records: Iterable[Requirement],
    *,
    schema_version: int = 1,
    base_path: Path | None = None,
) -> str:
    """Render the export JSON.

    Export shares the manifest shape (deterministic ordering, same core fields)
    and is intended for downstream tools such as SpecMason.
    """
    return render_manifest_json(
        records, schema_version=schema_version, base_path=base_path
    )


def write_export(
    records: Iterable[Requirement],
    path: Path,
    *,
    schema_version: int = 1,
    base_path: Path | None = None,
) -> None:
    """Atomically write the export JSON to ``path``."""
    text = render_export_json(
        records, schema_version=schema_version, base_path=base_path
    )
    atomic_write_text(path, text)


__all__ = [
    "MANIFEST_TOOL_NAME",
    "build_manifest",
    "render_export_json",
    "render_manifest_json",
    "write_export",
    "write_manifest",
]
