"""ReqLedger error hierarchy.

All ReqLedger errors derive from :class:`ReqLedgerError`, which in turn derives
from :class:`ledgercore.LedgerCoreError` so the Ledgerwerk family shares a
common exception root. Each error carries a stable ``code`` string.
"""

from __future__ import annotations

from ledgercore.errors import LedgerCoreError


class ReqLedgerError(LedgerCoreError):
    """Base exception for all ReqLedger errors."""

    code: str = "REQLEDGER_ERROR"


class ConfigError(ReqLedgerError):
    """Raised when configuration is missing, malformed, or unresolvable."""

    code: str = "CONFIG_ERROR"


class ParseError(ReqLedgerError):
    """Raised when a requirement record cannot be parsed."""

    code: str = "PARSE_ERROR"


class ValidationError(ReqLedgerError):
    """Raised when a record fails structural validation.

    Structural validation collects findings and reports them as a single error
    to callers that want exception-based control flow. The CLI instead surfaces
    the individual :class:`~reqledger.model.Finding` objects directly.
    """

    code: str = "VALIDATION_ERROR"


class DuplicateIdError(ReqLedgerError):
    """Raised when a requirement ID is not unique within a workspace."""

    code: str = "DUPLICATE_ID_ERROR"


class NotFoundError(ReqLedgerError):
    """Raised when a requirement ID cannot be resolved."""

    code: str = "NOT_FOUND_ERROR"


__all__ = [
    "ConfigError",
    "DuplicateIdError",
    "NotFoundError",
    "ParseError",
    "ReqLedgerError",
    "ValidationError",
]
