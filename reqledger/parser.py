"""TOML ``+++`` front matter parsing, rendering, and in-place updates.

ReqLedger records are Markdown documents whose front matter is TOML delimited
by ``+++`` (not YAML ``---``). The standard library ``tomllib`` (Python 3.11+)
or the ``tomli`` fallback parses TOML; because neither ships a writer, ReqLedger
renders TOML with a small deterministic serializer so output is byte-stable.
The Markdown body following the front matter is preserved verbatim.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib as _toml
else:  # pragma: no cover - exercised only on 3.10
    import tomli as _toml

from reqledger.errors import ParseError
from reqledger.model import CRITERION_KEY_ORDER, RECORD_KEY_ORDER

FRONT_MATTER_DELIM = "+++"
_TOMLDecodeError = _toml.TOMLDecodeError

# Keys whose values are always rendered as TOML arrays of inline tables (i.e.
# ``[[criteria]]`` tables when at the top level).
_CRITERIA_KEY = "criteria"

# A safe bare key: ASCII letters, digits, underscore, hyphen.
_BARE_KEY_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _strip_one_leading_newline(value: str) -> str:
    """Strip the single cosmetic blank line that render inserts after +++ ."""
    return value[1:] if value.startswith("\n") else value


# ---------------------------------------------------------------------------
# Split / parse.
# ---------------------------------------------------------------------------


def split_front_matter_text(text: str) -> tuple[dict[str, Any], str]:
    """Split a ``+++``-delimited document into ``(metadata, body)``.

    Raises :class:`ParseError` when the document lacks front matter, the
    delimiters are malformed, or the TOML block is invalid. An empty metadata
    mapping is never returned for documents that claim to have front matter:
    the opening ``+++`` with no closing ``+++`` is an error.
    """
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if (
        not normalized.startswith(FRONT_MATTER_DELIM + "\n")
        and normalized != FRONT_MATTER_DELIM
    ):
        raise ParseError("Document must start with '+++' followed by a newline")

    rest = normalized[len(FRONT_MATTER_DELIM) + 1 :]
    if rest == FRONT_MATTER_DELIM:
        return {}, ""

    # Locate the closing delimiter on its own line.
    close = rest.find("\n" + FRONT_MATTER_DELIM + "\n")
    if close >= 0:
        toml_block = rest[:close]
        body = rest[close + len("\n" + FRONT_MATTER_DELIM + "\n") :]
    elif rest.endswith("\n" + FRONT_MATTER_DELIM):
        toml_block = rest[: -len("\n" + FRONT_MATTER_DELIM)]
        body = ""
    else:
        raise ParseError("No closing '+++' delimiter found")

    if not toml_block.strip():
        return {}, body

    try:
        loaded = _toml.loads(toml_block)
    except _TOMLDecodeError as exc:
        raise ParseError(f"Invalid TOML front matter: {exc}") from exc

    if not isinstance(loaded, dict):
        raise ParseError("TOML front matter must be a table at the top level")
    return dict(loaded), _strip_one_leading_newline(body)


def read_record_document(path: Path) -> tuple[dict[str, Any], str]:
    """Read and split a record file from disk."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ParseError(f"Cannot read {path}: {exc}") from exc
    try:
        return split_front_matter_text(raw)
    except ParseError as exc:
        raise ParseError(f"{exc}: {path}") from exc


# ---------------------------------------------------------------------------
# Render (deterministic TOML serializer).
# ---------------------------------------------------------------------------


def _format_key(key: str) -> str:
    if _BARE_KEY_RE.fullmatch(key):
        return key
    return _format_basic_string(key)


def _format_basic_string(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\b", "\\b")
        .replace("\t", "\\t")
        .replace("\n", "\\n")
        .replace("\f", "\\f")
        .replace("\r", "\\r")
    )
    return f'"{escaped}"'


def _format_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        return _format_basic_string(value)
    raise ParseError(
        f"Unsupported scalar type for TOML front matter: {type(value).__name__}"
    )


def _format_string_array(values: list[Any]) -> str:
    if not values:
        return "[]"
    parts = [_format_scalar(v) for v in values]
    return "[" + ", ".join(parts) + "]"


def _format_inline_table(mapping: Mapping[str, Any], key_order: tuple[str, ...]) -> str:
    ordered_keys = [k for k in key_order if k in mapping]
    ordered_set = set(ordered_keys)
    ordered_keys.extend(k for k in mapping if k not in ordered_set)
    parts = [f"{_format_key(k)} = {_format_scalar(mapping[k])}" for k in ordered_keys]
    return "{ " + ", ".join(parts) + " }"


def render_toml_front_matter(
    metadata: Mapping[str, Any],
    *,
    key_order: tuple[str, ...] = RECORD_KEY_ORDER,
    criterion_key_order: tuple[str, ...] = CRITERION_KEY_ORDER,
) -> str:
    """Render a metadata mapping as a TOML block (without delimiters).

    Top-level ordering follows ``key_order``; remaining keys are emitted in
    sorted order for determinism. ``criteria`` is rendered as a series of
    ``[[criteria]]`` tables, each ordered by ``criterion_key_order``.
    """
    ordered_top: list[str] = [
        k for k in key_order if k in metadata and k != _CRITERIA_KEY
    ]
    seen = set(ordered_top)
    remaining = sorted(k for k in metadata if k not in seen and k != _CRITERIA_KEY)
    ordered_top.extend(remaining)

    lines: list[str] = []
    for key in ordered_top:
        value = metadata[key]
        if isinstance(value, list):
            lines.append(f"{_format_key(key)} = {_format_string_array(value)}")
        elif isinstance(value, Mapping):
            raise ParseError(
                f"Nested table {key!r} is not supported; use a flat schema"
            )
        else:
            lines.append(f"{_format_key(key)} = {_format_scalar(value)}")

    raw_criteria = metadata.get(_CRITERIA_KEY)
    if raw_criteria is not None:
        if not isinstance(raw_criteria, list):
            raise ParseError("'criteria' must be an array of tables")
        lines.append("")
        for criterion in raw_criteria:
            if not isinstance(criterion, Mapping):
                raise ParseError("each criterion must be a table")
            lines.append("[[criteria]]")
            ordered_crit: list[str] = [k for k in criterion_key_order if k in criterion]
            crit_seen = set(ordered_crit)
            ordered_crit.extend(sorted(k for k in criterion if k not in crit_seen))
            for ckey in ordered_crit:
                cvalue = criterion[ckey]
                if isinstance(cvalue, list):
                    lines.append(
                        f"{_format_key(ckey)} = {_format_string_array(cvalue)}"
                    )
                else:
                    lines.append(f"{_format_key(ckey)} = {_format_scalar(cvalue)}")
            lines.append("")

    # Trim the trailing blank line added after the final criterion table.
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines) + "\n"


def render_record_text(
    metadata: Mapping[str, Any],
    body: str = "",
    *,
    key_order: tuple[str, ...] = RECORD_KEY_ORDER,
    criterion_key_order: tuple[str, ...] = CRITERION_KEY_ORDER,
) -> str:
    """Render a complete ``+++``-delimited record document."""
    toml_block = render_toml_front_matter(
        metadata, key_order=key_order, criterion_key_order=criterion_key_order
    )
    if body:
        body = body if body.endswith("\n") else body + "\n"
        return f"{FRONT_MATTER_DELIM}\n{toml_block}{FRONT_MATTER_DELIM}\n\n{body}"
    return f"{FRONT_MATTER_DELIM}\n{toml_block}{FRONT_MATTER_DELIM}\n"


# ---------------------------------------------------------------------------
# Update (preserve body).
# ---------------------------------------------------------------------------


def update_record_text(
    text: str,
    updates: Mapping[str, Any],
    *,
    key_order: tuple[str, ...] = RECORD_KEY_ORDER,
    criterion_key_order: tuple[str, ...] = CRITERION_KEY_ORDER,
) -> str:
    """Apply ``updates`` to a record's front matter, preserving the body."""
    metadata, body = split_front_matter_text(text)
    metadata.update(updates)
    return render_record_text(
        metadata,
        body,
        key_order=key_order,
        criterion_key_order=criterion_key_order,
    )


def write_record_document(
    path: Path,
    metadata: Mapping[str, Any],
    body: str = "",
    *,
    key_order: tuple[str, ...] = RECORD_KEY_ORDER,
    criterion_key_order: tuple[str, ...] = CRITERION_KEY_ORDER,
) -> None:
    """Atomically write a record document to disk."""
    from ledgercore.atomic import atomic_write_text

    content = render_record_text(
        metadata,
        body,
        key_order=key_order,
        criterion_key_order=criterion_key_order,
    )
    atomic_write_text(path, content)


__all__ = [
    "FRONT_MATTER_DELIM",
    "read_record_document",
    "render_record_text",
    "render_toml_front_matter",
    "split_front_matter_text",
    "update_record_text",
    "write_record_document",
]
