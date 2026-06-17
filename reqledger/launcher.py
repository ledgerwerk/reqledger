"""Console-script entry point for ``reqledger``.

This thin shim keeps the existing ``reqledger = reqledger.launcher:main``
console-script declaration working while the Typer app itself lives in
:mod:`reqledger.cli`.
"""

from __future__ import annotations

from reqledger.cli import app


def main() -> None:
    """Run the ReqLedger CLI."""
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
