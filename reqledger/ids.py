"""Requirement and criterion ID allocation.

Thin wrappers over :class:`ledgercore.ids.NumericIdFormat` that honor the
configured prefix (``REQ``/``AC``) and width (default 4). IDs are the identity;
filenames derive from IDs but are not identity.
"""

from __future__ import annotations

from collections.abc import Iterable

from ledgercore.ids import NumericIdFormat

from reqledger.errors import NotFoundError
from reqledger.model import ReqLedgerConfig

#: Extension for requirement record files.
RECORD_EXTENSION = ".req.md"


def requirement_format(config: ReqLedgerConfig) -> NumericIdFormat:
    """Return the :class:`NumericIdFormat` for requirement IDs."""
    return NumericIdFormat(
        prefix=config.requirement_prefix,
        separator="-",
        width=config.width,
    )


def criterion_format(config: ReqLedgerConfig) -> NumericIdFormat:
    """Return the :class:`NumericIdFormat` for criterion IDs."""
    return NumericIdFormat(
        prefix=config.criterion_prefix,
        separator="-",
        width=config.width,
    )


def is_valid_requirement_id(value: object, config: ReqLedgerConfig) -> bool:
    fmt = requirement_format(config)
    try:
        number = fmt.parse(str(value))
    except ValueError:
        return False
    # Enforce configured width / canonical form (REQ-0001, not REQ-1).
    return fmt.format(number) == str(value)


def is_valid_criterion_id(value: object, config: ReqLedgerConfig) -> bool:
    fmt = criterion_format(config)
    try:
        number = fmt.parse(str(value))
    except ValueError:
        return False
    return fmt.format(number) == str(value)


def next_requirement_id(existing_ids: Iterable[str], config: ReqLedgerConfig) -> str:
    """Allocate the next stable requirement ID not present in ``existing_ids``."""
    return requirement_format(config).next(existing_ids)


def next_criterion_id(existing_ids: Iterable[str], config: ReqLedgerConfig) -> str:
    """Allocate the next criterion ID within a requirement."""
    return criterion_format(config).next(existing_ids)


def requirement_filename(req_id: str, config: ReqLedgerConfig) -> str:
    """Return the canonical filename for a requirement ID.

    ``REQ-0001 -> req-0001.req.md``.
    """
    lowered = req_id.lower()
    return f"{lowered}{RECORD_EXTENSION}"


def filename_for_id(req_id: str) -> str:
    """Filename for an ID without needing a config (uses default rules)."""
    return f"{req_id.lower()}{RECORD_EXTENSION}"


def parse_requirement_id(value: str, config: ReqLedgerConfig) -> int:
    """Parse a requirement ID and return its numeric part, or raise."""
    try:
        return requirement_format(config).parse(value)
    except ValueError as exc:
        raise NotFoundError(
            f"{value!r} is not a valid requirement id"
            f" ({config.requirement_prefix}-NNNN)"
        ) from exc


__all__ = [
    "RECORD_EXTENSION",
    "criterion_format",
    "filename_for_id",
    "is_valid_criterion_id",
    "is_valid_requirement_id",
    "next_criterion_id",
    "next_requirement_id",
    "parse_requirement_id",
    "requirement_filename",
    "requirement_format",
]
