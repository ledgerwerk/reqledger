"""reqledger: durable record owner for requirements and acceptance criteria.

ReqLedger stores readable Markdown records with TOML front matter and produces
deterministic JSON exports for downstream tools such as SpecMason. It does not
parse or generate Gherkin, discover tests, run tests, or own behavior specs.
"""

from __future__ import annotations

try:
    from reqledger._version import __version__
except ModuleNotFoundError as exc:  # pragma: no cover - dev fallback
    if exc.name != "reqledger._version":
        raise
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
