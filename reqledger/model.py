"""Domain dataclasses, allowed values, and serialization helpers for ReqLedger.

The dataclasses are the canonical in-memory representation of requirement
records. ``to_dict``/``from_dict`` round-trip records through the structure used
in TOML front matter and JSON exports. Allowed value sets are enforced by the
validation layer in :mod:`reqledger.review`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

# ---------------------------------------------------------------------------
# Allowed value sets (exact, per brief).
# ---------------------------------------------------------------------------

REQ_KINDS: frozenset[str] = frozenset(
    {"functional", "nonfunctional", "constraint", "interface", "policy"}
)
REQ_STATUSES: frozenset[str] = frozenset(
    {"draft", "proposed", "accepted", "implemented", "deprecated", "rejected"}
)
REQ_PRIORITIES: frozenset[str] = frozenset({"must", "should", "could", "wont"})
CRITERION_VERIFICATIONS: frozenset[str] = frozenset(
    {"behavior", "unit", "integration", "manual", "inspection", "none"}
)
CRITERION_STATUSES: frozenset[str] = frozenset(
    {"draft", "accepted", "implemented", "deprecated", "rejected"}
)
ALLOWED_SOURCES: frozenset[str] = frozenset(
    {"manual", "taskledger", "archledger", "specmason-discovery", "import"}
)

Severity = Literal["error", "warning", "info"]

# Ordered key list used for deterministic front-matter rendering.
RECORD_KEY_ORDER: tuple[str, ...] = (
    "schema_version",
    "id",
    "title",
    "kind",
    "status",
    "priority",
    "owner",
    "tags",
    "parent_ids",
    "supersedes",
    "superseded_by",
    "task_refs",
    "arch_refs",
    "spec_refs",
    "evidence_refs",
    "source",
    "source_refs",
    "created",
    "updated",
)

CRITERION_KEY_ORDER: tuple[str, ...] = (
    "id",
    "statement",
    "verification",
    "status",
    "tags",
)

# ---------------------------------------------------------------------------
# Finding model.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Finding:
    """A structured validation/review finding."""

    severity: Severity
    code: str
    message: str
    requirement_id: str = ""
    criterion_id: str = ""
    path: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "requirement_id": self.requirement_id,
            "criterion_id": self.criterion_id,
            "path": self.path,
        }


# ---------------------------------------------------------------------------
# Criterion and Requirement.
# ---------------------------------------------------------------------------


def _as_str_list(value: object, *, field_name: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        # Tolerate a single string for convenience, but normalize to a list.
        return [value]
    if not isinstance(value, list):
        raise TypeError(f"{field_name} must be a list of strings")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise TypeError(f"{field_name} entries must be strings")
        result.append(item)
    return result


@dataclass(frozen=True)
class Criterion:
    """A single acceptance criterion belonging to a requirement."""

    id: str
    statement: str
    verification: str
    status: str
    tags: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "statement": self.statement,
            "verification": self.verification,
            "status": self.status,
            "tags": list(self.tags),
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> Criterion:
        return cls(
            id=str(data.get("id", "")),
            statement=str(data.get("statement", "")),
            verification=str(data.get("verification", "")),
            status=str(data.get("status", "")),
            tags=tuple(_as_str_list(data.get("tags"), field_name="tags")),
        )


@dataclass(frozen=True)
class Requirement:
    """A requirement record loaded from disk.

    ``path`` is the resolved filesystem path of the source Markdown file; it is
    not part of front matter and is excluded from ``to_dict``.
    """

    schema_version: int
    id: str
    title: str
    kind: str
    status: str
    priority: str
    tags: tuple[str, ...] = ()
    criteria: tuple[Criterion, ...] = ()
    owner: str = ""
    parent_ids: tuple[str, ...] = ()
    supersedes: tuple[str, ...] = ()
    superseded_by: tuple[str, ...] = ()
    task_refs: tuple[str, ...] = ()
    arch_refs: tuple[str, ...] = ()
    spec_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    source: str = "manual"
    source_refs: tuple[str, ...] = ()
    created: str = ""
    updated: str = ""
    path: Path = Path()
    body: str = ""

    def to_dict(self) -> dict[str, object]:
        """Serialize to the front-matter dictionary shape."""
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "title": self.title,
            "kind": self.kind,
            "status": self.status,
            "priority": self.priority,
            "owner": self.owner,
            "tags": list(self.tags),
            "parent_ids": list(self.parent_ids),
            "supersedes": list(self.supersedes),
            "superseded_by": list(self.superseded_by),
            "task_refs": list(self.task_refs),
            "arch_refs": list(self.arch_refs),
            "spec_refs": list(self.spec_refs),
            "evidence_refs": list(self.evidence_refs),
            "source": self.source,
            "source_refs": list(self.source_refs),
            "created": self.created,
            "updated": self.updated,
            "criteria": [c.to_dict() for c in self.criteria],
        }

    @classmethod
    def from_dict(
        cls, data: dict[str, object], *, path: Path | None = None
    ) -> Requirement:
        raw_criteria = data.get("criteria")
        if raw_criteria is None:
            criteria: tuple[Criterion, ...] = ()
        elif isinstance(raw_criteria, list):
            criteria = tuple(
                Criterion.from_dict(c)
                if isinstance(c, dict)
                else Criterion.from_dict({})
                for c in raw_criteria
            )
        else:
            raise TypeError("criteria must be a list of tables")
        schema_version = data.get("schema_version", 1)
        if isinstance(schema_version, bool) or not isinstance(schema_version, int):
            # Allow numeric strings to be lenient on read; validation flags type.
            try:
                schema_version = int(schema_version)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                schema_version = 1
        return cls(
            schema_version=schema_version,
            id=str(data.get("id", "")),
            title=str(data.get("title", "")),
            kind=str(data.get("kind", "")),
            status=str(data.get("status", "")),
            priority=str(data.get("priority", "")),
            tags=tuple(_as_str_list(data.get("tags"), field_name="tags")),
            criteria=criteria,
            owner=str(data.get("owner", "")),
            parent_ids=tuple(
                _as_str_list(data.get("parent_ids"), field_name="parent_ids")
            ),
            supersedes=tuple(
                _as_str_list(data.get("supersedes"), field_name="supersedes")
            ),
            superseded_by=tuple(
                _as_str_list(data.get("superseded_by"), field_name="superseded_by")
            ),
            task_refs=tuple(
                _as_str_list(data.get("task_refs"), field_name="task_refs")
            ),
            arch_refs=tuple(
                _as_str_list(data.get("arch_refs"), field_name="arch_refs")
            ),
            spec_refs=tuple(
                _as_str_list(data.get("spec_refs"), field_name="spec_refs")
            ),
            evidence_refs=tuple(
                _as_str_list(data.get("evidence_refs"), field_name="evidence_refs")
            ),
            source=str(data.get("source", "manual")),
            source_refs=tuple(
                _as_str_list(data.get("source_refs"), field_name="source_refs")
            ),
            created=str(data.get("created", "")),
            updated=str(data.get("updated", "")),
            path=path if path is not None else Path(),
        )

    def refs(self) -> dict[str, list[str]]:
        """Return refs grouped as manifest expects."""
        return {
            "tasks": list(self.task_refs),
            "architecture": list(self.arch_refs),
            "specs": list(self.spec_refs),
            "evidence": list(self.evidence_refs),
        }

    def to_manifest_entry(self, *, base_path: Path | None = None) -> dict[str, object]:
        """Manifest/export entry shape.

        When ``base_path`` is provided, ``path`` is rendered relative to it
        using POSIX separators (e.g. ``requirements/records/req-0001.req.md``).
        """
        path_value: str = ""
        if self.path is not None and str(self.path):
            resolved = self.path
            if base_path is not None:
                try:
                    path_value = resolved.relative_to(base_path).as_posix()
                except ValueError:
                    path_value = resolved.as_posix()
            else:
                path_value = resolved.as_posix()
        return {
            "id": self.id,
            "title": self.title,
            "path": path_value,
            "kind": self.kind,
            "status": self.status,
            "priority": self.priority,
            "tags": list(self.tags),
            "source": self.source,
            "source_refs": list(self.source_refs),
            "criteria": [c.to_dict() for c in self.criteria],
            "refs": self.refs(),
        }


# ---------------------------------------------------------------------------
# Configuration.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReqLedgerConfig:
    """Resolved ReqLedger configuration.

    Path attributes are absolute and resolved relative to the config file's
    directory (or the workspace root when no config exists). ``config_path`` is
    empty when running on pure defaults.
    """

    schema_version: int
    root: Path
    records_dir: Path
    manifest: Path
    reports_dir: Path
    reports_state_dir: Path
    requirement_prefix: str
    criterion_prefix: str
    width: int
    draft_stale_days: int
    workspace_root: Path
    config_path: Path

    @classmethod
    def default_fields(cls) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "paths": {
                "root": "requirements",
                "records_dir": "requirements/records",
                "manifest": "requirements/manifest.json",
                "reports_dir": "requirements/reports",
                "reports_state_dir": "requirements/reports/reqledger",
            },
            "ids": {
                "requirement_prefix": "REQ",
                "criterion_prefix": "AC",
                "width": 4,
            },
            "review": {"draft_stale_days": 90},
        }


__all__ = [
    "ALLOWED_SOURCES",
    "CRITERION_KEY_ORDER",
    "CRITERION_STATUSES",
    "CRITERION_VERIFICATIONS",
    "Criterion",
    "Finding",
    "REQ_KINDS",
    "REQ_PRIORITIES",
    "REQ_STATUSES",
    "RECORD_KEY_ORDER",
    "Requirement",
    "ReqLedgerConfig",
    "Severity",
]
